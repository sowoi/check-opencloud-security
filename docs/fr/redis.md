# Redis

Redis contient la file d’attente du service web, les résultats temporaires des analyses,
les données de référence et l’état opérationnel partagé. Ce guide couvre l’authentification,
l’accès réseau, la conservation, les limites de mémoire et la récupération après une
perte de connexion.

Ce guide concerne l’**application web** dans [`webapp/`](../../webapp/README.md). Le plugin
en ligne de commande n’utilise pas Redis : `check-opencloud-security` contacte une
instance OpenCloud, affiche une ligne puis se termine.

Les piles fournies utilisent **Valkey** (`valkey/valkey:9.1-alpine`), la
continuation sous licence BSD de Redis. Le protocole est le même : le service
s’appelle toujours `redis` et `COS_WEB_REDIS_URL` garde le schéma `redis://`.
Si vous avez activé la persistance avec l’assistant, videz une fois le
répertoire ou le volume de données avant le premier démarrage de Valkey, qui
refuse un fichier de données écrit par Redis 8.

> **Pour corriger l’avertissement d’authentification**, définissez
> `COS_REDIS_PASSWORD` dans `docker/.env`, puis lancez `docker compose up -d`.
> Les sections suivantes expliquent ce réglage et les autres mesures utiles.

## Sommaire {#table-of-contents}

<!-- TOC -->
* [Rôle de Redis](#what-redis-is-used-for)
* [Données et durées de conservation](#what-is-stored-and-for-how-long)
* [Configurer la connexion](#configuring-the-connection)
* [Fonctionnement sans Redis](#running-without-redis)
* [Mot de passe](#the-password)
* [Isolation réseau](#network-isolation)
* [Persistance désactivée par défaut](#persistence-or-the-deliberate-lack-of-it)
* [Mémoire et éviction](#memory-and-eviction)
* [Redis externe ou géré](#an-external-or-managed-redis)
* [Kubernetes](#kubernetes)
* [État et supervision](#health-and-monitoring)
* [Dépannage](#troubleshooting)
* [Marques et affiliation](#trademarks-and-affiliation)
<!-- TOC -->

## Rôle de Redis {#what-redis-is-used-for}

Redis remplit trois fonctions :

1. **La file d’attente.** Chaque demande acceptée reçoit un uuid, puis rejoint une
   liste lue par le worker ARQ. Si tous les workers sont occupés, la demande attend
   son tour et sa position est indiquée.
2. **L’état de chaque analyse.** Redis stocke son statut, ses paramètres et le
   résultat lorsqu’il est disponible. L’application web lit ces données pour
   répondre à `GET /api/scans/{uuid}` ; elle n’exécute pas elle-même l’analyse.
3. **Les données de référence et compteurs partagés.** Il conserve le calendrier
   des versions et les avis relus chaque jour, le signal de présence du worker
   et les compteurs de limitation des requêtes.

La plupart de ces données peuvent être recréées. Vider Redis supprime toutefois
les demandes en attente, les résultats consultables, les compteurs et les exclusions
ajoutées dans l’espace opérateur. Placez les exclusions permanentes dans
`COS_WEB_BLOCKED_TARGETS`. Les analyses expirent automatiquement, mais toutes les
clés opérationnelles n’ont pas la même durée de vie.

## Données et durées de conservation {#what-is-stored-and-for-how-long}

| Clé | Contenu | Durée de vie |
|:----|:--------------|:---------|
| `scan:{uuid}:status` | `queued`, `running`, `completed` ou `failed` | `COS_WEB_RESULT_TTL` (3600 s par défaut) |
| `scan:{uuid}:result` | Document produit par le scanner | `COS_WEB_RESULT_TTL` |
| `scan:{uuid}:metadata` | Adresse soumise, exemptions, canal de versions, horodatages | `COS_WEB_RESULT_TTL` |
| `cos:web:queue` | Liste FIFO des uuid en attente d’un worker | Durée des résultats, au moins une heure |
| `cos:web:worker:heartbeat` | Signal de présence du worker pour `/healthz` | Renouvelé par le worker |
| `cos:web:rl:client:{fingerprint}` | Compteur de requêtes par client | `COS_WEB_IP_RATE_WINDOW` |
| `cos:web:rl:target:{fingerprint}` | Délai entre deux analyses d’une cible | `COS_WEB_TARGET_COOLDOWN` |
| `scan:{uuid}:prober` | Empreinte du client auquel attribuer le résultat, jusqu’au démarrage du worker | Au plus `COS_WEB_RESULT_TTL` |
| `cos:web:rl:probe:{fingerprint}` | Incidents attribués à un réseau client | `COS_WEB_PROBE_WINDOW` |
| `cos:web:rl:blocked:{fingerprint}` | Blocage d’un réseau client pour sondage abusif | `COS_WEB_PROBE_BLOCK`, jusqu’à `COS_WEB_PROBE_BLOCK_MAX` |
| `cos:web:rl:blocks:{fingerprint}` | Nombre récent de blocages d’un réseau, pour prolonger les suivants | Dernier blocage plus `COS_WEB_PROBE_REPEAT_WINDOW` |
| `cos:web:rl:daily:{fingerprint}` | Compteur quotidien par client | Un jour |
| `cos:web:stats:{blocks,strikes,daily}:{YYYYMMDD}` | Totaux quotidiens pour l’espace opérateur : blocages, incidents et plafonds atteints | Huit jours |
| `cos:web:schedule:document`, `cos:web:schedule:checked` | Calendrier des versions relu chaque jour | Jusqu’à l’actualisation suivante |
| `cos:web:advisories:document`, `cos:web:advisories:checked` | Base d’avis relue chaque jour | Jusqu’à l’actualisation suivante |

**L’uuid suffit pour accéder au résultat.** Chaque analyse possède son espace
`scan:{uuid}:*` et aucune route ne permet de les énumérer. Un uuid inconnu, invalide
ou expiré reçoit le même code 404. Un résultat expiré ne se distingue donc pas
d’un résultat qui n’a jamais existé. Une route de liste rendrait tous les résultats
accessibles publiquement.

**Les clés de limitation contiennent des empreintes, pas les adresses des clients.**
Elles utilisent `COS_WEB_RATE_LIMIT_SALT`. Le journal d’audit utilise une autre
valeur, `COS_WEB_AUDIT_SALT`. Configurez un sel de limitation commun si vous lancez
plusieurs processus web. Voir la [journalisation](../webapp.md#what-gets-logged).

Pendant la durée de conservation, Redis contient les adresses soumises et les
constats de sécurité associés. Il faut donc protéger son accès.

## Configurer la connexion {#configuring-the-connection}

Les deux processus lisent `COS_WEB_REDIS_URL`. L’application web l’utilise
directement et le worker la transmet à ARQ. Le mot de passe et le schéma TLS de
cette URL s’appliquent ainsi aux deux connexions.

| Forme | Utilisation |
|:-----|:-----|
| `redis://redis:6379/0` | Conteneur Redis local, sans mot de passe |
| `redis://:PASSWORD@redis:6379/0` | Avec `requirepass` ; le nom d’utilisateur est vide |
| `redis://user:PASSWORD@host:6379/0` | Utilisateur ACL de Redis 6 ou ultérieur |
| `rediss://user:PASSWORD@host:6380/0` | Connexion TLS ; le second `s` active le chiffrement |
| `memory://` | Sans Redis, voir ci-dessous |

Encodez les caractères `@`, `:`, `/` et `#` du mot de passe avec l’encodage pour
URL, sinon ils seront interprétés comme des éléments de l’adresse.
[`docker/setup-wizard.py`](../../docker/setup-wizard.py) et
[`docker/authentik-env.sh`](../../docker/authentik-env.sh) génèrent des mots de
passe composés uniquement de caractères utilisables tels quels dans une URL.

## Fonctionnement sans Redis {#running-without-redis}

`COS_WEB_REDIS_URL=memory://` utilise un dictionnaire dans le processus web, avec
la même interface que Redis. Ce mode sert aux tests et aux essais locaux :

- **Tests.** `tests/webapp_support.py` le configure afin qu’aucun test n’ait
  besoin d’un serveur Redis.
- **Essai de l’interface.** Un seul processus et une commande suffisent.

Ce mode ne convient pas à un déploiement. Aucun worker ne reçoit les demandes,
l’état disparaît à l’arrêt du processus et un second processus ne voit pas les
analyses du premier. Un service destiné à d’autres utilisateurs nécessite Redis.

## Mot de passe {#the-password}

Sans configuration, Redis répond à tout client qui peut le joindre. Un contrôle
de sécurité de l’hôte peut alors afficher :

```
WARNING: Redis does not require authentication and is not protected by
network restriction
```

Cet avertissement est justifié. Supposer que seuls vos conteneurs utilisent le
réseau ne remplace pas un contrôle d’accès. Redis contient toutes les analyses en
cours et les résultats qui n’ont pas encore expiré.

Définissez un mot de passe :

```bash
cd docker
printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" >> .env
chmod 600 .env
docker compose up -d
```

Les fichiers Compose utilisent `${COS_REDIS_PASSWORD:-}` à deux endroits : Redis
le reçoit via `--requirepass`, et les deux conteneurs applicatifs via
`COS_WEB_REDIS_URL`. Si la variable reste vide, le comportement antérieur est
conservé. Définissez-la pour tout déploiement autre qu’un essai local.

Deux outils le font pour vous :

- [`docker/setup-wizard.py`](../../docker/setup-wizard.py) génère le mot de passe
  dans un fichier `.env` de mode `0600`. Le fichier Compose référence la variable,
  sans contenir sa valeur, et peut donc être versionné.
- [`docker/authentik-env.sh`](../../docker/authentik-env.sh) le génère avec les
  secrets Authentik et conserve toute valeur existante.

Vérifiez son application :

```bash
docker compose exec -e VALKEYCLI_AUTH= redis valkey-cli ping
# NOAUTH Authentication required.        <- what you want to see
docker compose exec redis valkey-cli ping
# PONG                                   <- authenticated, via VALKEYCLI_AUTH
```

Le contrôle de santé lit `VALKEYCLI_AUTH` dans l’environnement. Il ne passe pas le
mot de passe avec `-a`, pour éviter de l’exposer dans la liste des processus.

Après un changement de mot de passe, redémarrez les trois services ensemble : les
conteneurs applicatifs lisent l’URL au démarrage, ce qui empêche une rotation par
redémarrages successifs.

## Isolation réseau {#network-isolation}

Limitez aussi l’accès réseau à Redis. Dans les fichiers Compose fournis, Redis
ne publie aucun port et utilise uniquement un réseau `internal: true` :

```yaml
networks:
  scanner_internal:
    internal: true
```

Docker ne donne pas de passerelle à ce réseau. Ses conteneurs ne peuvent donc pas
joindre l’extérieur par ce réseau, qui n’est pas routable depuis l’extérieur.
Les deux conteneurs applicatifs utilisent aussi le réseau par défaut pour les
requêtes sortantes et le port web publié. Redis reste sur le réseau interne.

Pour un Redis installé séparément, utilisez `bind 127.0.0.1`, un pare-feu ou un
segment réseau privé. Ne publiez pas le port 6379 sur une interface de l’hôte,
ni sur Internet, où des outils de détection le repéreraient rapidement.

## Persistance désactivée par défaut {#persistence-or-the-deliberate-lack-of-it}

Le Redis fourni utilise `--save ""` et `--appendonly no` : il n’écrit pas sur disque.

La persistance et les sauvegardes peuvent conserver les données après leur
expiration dans Redis. La configuration par défaut désactive donc les instantanés
et le journal d’écriture. Un redémarrage supprime les résultats temporaires et
l’état Redis, y compris les exclusions de l’espace opérateur. Conservez les
exclusions permanentes dans l’environnement.

N’ajoutez pas de volume au service `redis`. Avec un Redis géré qui persiste ses
données par défaut, désactivez cette fonction ou acceptez que les sauvegardes
conservent les résultats au-delà de leur durée de vie.

`docker/setup-wizard.py` peut toutefois produire une configuration persistante
pour une instance privée où la conservation des demandes en attente est prioritaire.
Cette option n’est jamais activée par défaut. L’assistant affiche un avertissement
et propose `COS_WEB_ENCRYPT_RESULTS` : les données sont alors chiffrées et la clé
reste dans `.env`. Pour un service public, conservez le choix `none`.

## Mémoire et éviction {#memory-and-eviction}

```
--maxmemory 256mb
--maxmemory-policy allkeys-lru
```

La limite fournie est un point de départ pour le nombre de workers par défaut.
Surveillez la consommation réelle si le volume d’analyses ou la conservation
augmente. Cette limite empêche une file qui ne se vide plus d’épuiser la mémoire
de l’hôte.

`allkeys-lru` peut supprimer toute clé sous pression mémoire, selon une estimation
de son utilisation récente. Cela concerne aussi la file, les compteurs et les
données de l’espace opérateur. Une éviction signale un problème de capacité à
examiner ; la durée de vie des clés ne suffit pas à le prévenir.

Augmentez la limite si vous augmentez fortement `COS_WEB_RESULT_TTL` ou analysez
des centaines d’instances. Surveillez `evicted_keys` :

```bash
docker compose exec redis valkey-cli info stats | grep evicted_keys
```

Des évictions régulières avec une conservation courte indiquent une limite trop
basse : les utilisateurs perdent leurs résultats avant de les consulter.

## Redis externe ou géré {#an-external-or-managed-redis}

Configurez `COS_WEB_REDIS_URL` et retirez le service `redis` du fichier Compose.
Vérifiez les points suivants :

- **Utilisez TLS**, avec `rediss://`, car la connexion transporte les résultats
  et le mot de passe.
- **Réservez une base ou une instance à ce service.** Les clés ont des préfixes
  (`scan:`, `cos:web:`), mais `DELETE /api/purge` parcourt `scan:*:metadata`.
  Une instance partagée très chargée ralentit cette opération.
- **Vérifiez la politique d’éviction.** Avec `noeviction`, Redis refuse les
  écritures quand il est plein. Une demande peut alors échouer au lieu de rejoindre
  la file.
- **Vérifiez la persistance**, comme décrit plus haut.

## Kubernetes {#kubernetes}

Le [guide Kubernetes](kubernetes.md) déploie le service avec un `Deployment` et
un `Service` Redis distincts, ou avec une instance gérée. Les mêmes règles
s’appliquent :

- Stockez le mot de passe dans un `Secret`, référencé par `COS_WEB_REDIS_URL`,
  jamais dans un `ConfigMap`.
- Limitez les connexions entrantes aux pods web et worker avec une `NetworkPolicy`.
- Utilisez `ClusterIP`, sans `Ingress`, `LoadBalancer` ni `NodePort`.
- N’ajoutez pas de `PersistentVolumeClaim` ; voir la section sur la
  [persistance](#persistence-or-the-deliberate-lack-of-it).

## État et supervision {#health-and-monitoring}

`GET /healthz` répond `503` si la file est illisible ou si aucun worker n’a envoyé
son signal de présence. Cette route permet donc de superviser Redis sans contrôle
séparé. Elle indique la longueur de la file et l’état des deux actualisations
quotidiennes, sans révéler les analyses individuelles.

| Signal d’alerte | Signification |
|:-------|:----|
| `/healthz` répond 503 | Redis est inaccessible ou le worker est arrêté ; aucune analyse ne peut s’exécuter |
| La file augmente sans se vider | Workers bloqués ou trop peu nombreux ; les demandes attendent |
| `evicted_keys` augmente | Des clés sont supprimées avant leur expiration |
| `rejected_connections` augmente | Limite de connexions atteinte, souvent à cause de connexions non libérées |

## Dépannage {#troubleshooting}

| Symptôme | Cause ou action |
|:-------------|:--------------|
| `NOAUTH Authentication required` | L’URL ne contient pas le mot de passe Redis. Ajoutez `:PASSWORD@` après le schéma |
| `WRONGPASS invalid username-password pair` | L’URL et `--requirepass` diffèrent. Vérifiez que tous les conteneurs ont redémarré après la modification de `.env` |
| `Connection refused` | Redis est arrêté ou sur un autre réseau. Consultez `docker compose ps` et vérifiez que les deux services applicatifs utilisent `scanner_internal` |
| `Name or service not known: redis` | Le conteneur applicatif n’est pas sur le réseau interne |
| `MISCONF Redis is configured to save RDB snapshots` | La persistance est activée ; voir la section [Persistance](#persistence-or-the-deliberate-lack-of-it) |
| `OOM command not allowed when used memory > 'maxmemory'` | Limite atteinte avec `noeviction`. La politique prévue est `allkeys-lru` |
| `/healthz` indique `unavailable` | Redis répond mais aucun worker n’envoie de signal. Consultez les journaux du worker |
| Un résultat répond 404 trop tôt | La durée de vie a expiré ou une clé a été évincée. Surveillez `evicted_keys` si cela se répète |

Les journaux ne contiennent que les étapes du cycle d’exécution et un uuid, jamais
les adresses cibles ni les résultats. Un problème Redis apparaît donc comme des
analyses qui restent à l’état `queued`. Les journaux ne constituent pas un
historique des cibles analysées.

## Marques et affiliation {#trademarks-and-affiliation}

Ce projet communautaire est indépendant. Il n’est ni affilié à OpenCloud GmbH,
ni approuvé, parrainé ou pris en charge par cette société. Ses résultats ne sont
pas des déclarations officielles sur OpenCloud. Le nom OpenCloud et les marques
associées appartiennent à leurs propriétaires respectifs et servent ici uniquement
à identifier le logiciel contrôlé.

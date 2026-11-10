# Exécuter le scanner comme service web

L’application web exécute le scanner intégré et présente ses résultats avec une note
de **A+** à **F**. Les résultats restent disponibles dans Redis pendant une heure par défaut.
La couche web affiche le résultat du scanner sans définir de notation distincte.

Essayez le service public pour une analyse ponctuelle. Les instructions ci-dessous
expliquent comment héberger votre propre service, notamment l’accès réseau, la conservation
des données et les limites d’utilisation.

Le paquet PyPI ne contient que le plugin et la bibliothèque du scanner.
L’application web est distribuée séparément sous forme de pièce jointe de version
GitHub, `check_opencloud_security_web.tar.gz`, ou peut être construite à partir
d’une copie du dépôt.

| | |
|:--|:--|
| **Exécute** | FastAPI + un worker ARQ + Redis |
| **Stocke** | Rien sur disque. Uniquement Redis, chaque clé avec une durée de vie |
| **Nécessite** | Ni base de données, ni compte, ni clé d’API |
| **Concurrence** | Fixée par l’opérateur, jamais par une requête |

L’interface est disponible en anglais, allemand, français et espagnol. Elle suit
d’abord la préférence de langue du navigateur ; un choix fait avec le sélecteur
de langue est mémorisé dans un cookie `HttpOnly`, `SameSite=Lax`. Le contenu des
guides est disponible dans les quatre langues. Les contrats d’API, les exports et
les preuves mesurées conservent leurs valeurs techniques d’origine.

## Sommaire {#contents}

- [Démarrage](#starting-it)
- [Ce qu’un visiteur peut demander](#what-a-visitor-can-ask-for)
- [Configuration](#configuration)
- [Le parcours d’une analyse](#how-a-scan-flows-through-it)
- [Mettre en file d’attente plutôt que refuser](#queueing-rather-than-refusing)
- [Isolation entre les analyses](#isolation-between-scans)
- [Comparer deux analyses](#comparing-two-scans)
- [La protection SSRF](#the-ssrf-guard)
- [Limitation du débit](#rate-limiting)
- [Ce qui est journalisé](#what-gets-logged)
- [Placer le service derrière un reverse proxy](#putting-it-behind-a-reverse-proxy)
- [L’API HTTP](#the-http-api)
- [Organisation du code](#layout)
- [Marques et affiliation](#trademarks-and-affiliation)

## Démarrage {#starting-it}

L’assistant d’installation crée les trois services nécessaires : l’application
web, le worker d’analyse et Redis. C’est un script Python autonome qui n’utilise
que la bibliothèque standard et ne nécessite aucune copie du dépôt :

```bash
mkdir opencloud-scanner && cd opencloud-scanner

base=https://github.com/sowoi/check-opencloud-security/releases/latest/download
curl -fsSLO "$base/setup-wizard.py" -O "$base/setup-wizard.py.sha256"
sha256sum --check setup-wizard.py.sha256    # macOS: shasum -a 256 --check
chmod +x setup-wizard.py
./setup-wizard.py --version
./setup-wizard.py

docker compose up -d
# http://127.0.0.1:8811
```

Il pose une question à la fois et écrit un fichier compose commenté contenant
directement les réponses non secrètes, ainsi qu’un `.env` lisible uniquement par
son propriétaire, qui contient chaque identifiant auquel ce fichier fait
référence sous la forme `${NAME}` : le mot de passe Redis, le jeton d’effacement,
la clé de signature, le sel d’audit et la clé de chiffrement.
[Un déploiement sur mesure](#a-deployment-of-your-own) décrit les options.

### Ou les fichiers compose fournis par ce projet {#or-the-compose-files-this-project-ships}

Pour utiliser l’image publiée :

```bash
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security/docker

printf 'COS_REDIS_PASSWORD=%s\n' "$(openssl rand -base64 36 | tr -d '/+=')" > .env
chmod 600 .env

docker compose -f docker-compose.dockerhub.yml up -d
# http://127.0.0.1:8811
```

Ou la même pile construite depuis la copie du dépôt, avec
`docker compose up --build -d` et sans `-f`.

Avant de rendre la pile accessible au public, vérifiez ces trois paramètres dans
le fichier `.env` situé à côté du fichier compose :

| Paramètre | Pourquoi il compte |
|:--------|:---------------|
| `COS_WEB_PUBLIC_BASE_URL` | Les URL canoniques, le sitemap et le document de découverte sont construits à partir de lui plutôt que d’un en-tête `Host` entrant. Il vaut `http://localhost:8811` par défaut pour qu’un premier `up` fonctionne ; tout service accessible à des inconnus doit le définir |
| `COS_REDIS_PASSWORD` | Redis contient chaque analyse en cours et chaque résultat encore dans sa durée de vie. Non défini, il ne demande rien. Voir [Redis](redis.md) |
| `COS_WEB_TRUST_FORWARDED_FOR` | `true` uniquement derrière votre propre proxy, sinon chaque client peut falsifier sa propre identité pour la limitation du débit. Définissez `COS_WEB_TRUSTED_PROXY_HOPS` sur le nombre de proxies |

L’image publiée se trouve sur Docker Hub sous le nom **`okxo/opencloud-scanner`** :
un déploiement n’a donc pas besoin d’en construire une. `latest` et
`MAJOR.MINOR.PATCH` suivent la version publiée, `MAJOR.MINOR` suit la ligne, et
`edge` correspond au `main` actuel. Elle est disponible pour `linux/amd64` et
`linux/arm64`, et la même image exécute le service web et le worker - ils ne
diffèrent que par la commande, ce qui empêche le code qui décrit un résultat et
celui qui le produit de diverger d’un déploiement à l’autre.

Lancer un seul conteneur à la main nécessite un Redis partagé avec le worker et
l’adresse publique, car ni l’un ni l’autre n’a de valeur par défaut utile en
dehors d’un fichier compose :

```bash
docker run --rm -p 8811:8811 \
    -e COS_WEB_REDIS_URL="redis://:PASSWORD@redis:6379/0" \
    -e COS_WEB_PUBLIC_BASE_URL=http://127.0.0.1:8811 \
    okxo/opencloud-scanner:latest
```

[`docker/README.md`](../../docker/README.md) décrit les piles en détail, y
compris celle avec Authentik, et la description sur Docker Hub contient une
recette `docker run` simple pour les trois conteneurs.

### Sans conteneurs {#without-containers}

Depuis une copie du dépôt, avec trois terminaux ou trois `&` :

```bash
pip install ".[web,mcp]"    # the mcp extra is optional; it serves /mcp
valkey-server &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 python -m webapp.tasks &
COS_WEB_REDIS_URL=redis://127.0.0.1:6379/0 \
    uvicorn webapp.app:app --host 127.0.0.1 --port 8811
```

Pour construire vous-même l’archive de version :

```bash
python scripts/build_web_bundle.py
# dist/check_opencloud_security_web.tar.gz  (+ .sha256)
```

### Un déploiement sur mesure {#a-deployment-of-your-own}

Utilisez l’assistant pour configurer un autre port, des cibles internes, le
chiffrement des résultats ou l’authentification MCP. Il peut s’exécuter depuis
une copie du dépôt ou sous forme de téléchargement autonome :

```bash
cd docker
./setup-wizard.py --output-dir ~/opencloud-scanner
```

Il explique chaque paramètre, montre un exemple de réponse et écrit un fichier
compose commenté contenant directement les réponses non secrètes, ainsi qu’un
`.env` lisible uniquement par son propriétaire, qui contient les identifiants
auxquels ce fichier fait référence sous la forme `${NAME}`. Répondez `generate`
et il crée pour vous le jeton d’effacement, la clé de signature, le sel d’audit
et la clé de chiffrement. `--preset private` part de ce dont a besoin un parc qui
analyse ses propres instances, et `--non-interactive` accepte toutes les valeurs
par défaut pour une installation sans intervention.

`--sign-in` exige un jeton sur `/mcp` et demande l’émetteur, l’audience et les
clés du fournisseur que vous exploitez déjà. `--with-authentik` en provisionne un
à la place : Authentik et sa base de données rejoignent la pile générée, ces trois
valeurs sont déduites des réponses, et le blueprint est écrit à côté du fichier
compose qui le monte. Les deux options sont indépendantes : provisionner un
fournisseur ne ferme pas le point de terminaison. La démarche habituelle consiste
donc à démarrer Authentik avec `/mcp` encore ouvert, à obtenir un jeton, puis à
activer la protection une fois que cela fonctionne. Aucune des deux options
n’implique l’autre, et rien d’Authentik n’est écrit dans un déploiement qui ne l’a
pas demandé. En mode interactif toutefois, activer `/admin` ou la connexion sur
`/mcp` fait de *oui* la réponse par défaut à la question suivante sur le
fournisseur, car la plupart des déploiements qui demandent l’un ou l’autre n’ont
pas encore de fournisseur. Lorsqu’il est demandé, ses paramètres de messagerie le
sont aussi (`--smtp-host`, `--smtp-from`, `--smtp-security`, etc.), car un
fournisseur d’identité incapable d’envoyer une récupération de mot de passe
bloque le seul compte avec lequel il démarre ; le mot de passe provient de
`AUTHENTIK_EMAIL_PASSWORD` dans l’environnement plutôt que d’une option.
[`docker/README.md`](../../docker/README.md#the-setup-wizard) décrit les options.
Cet assistant n’a rien à voir avec `check-opencloud-security --configure`, qui
configure une vérification de supervision et non un déploiement de conteneurs.

## Ce qu’un visiteur peut demander {#what-a-visitor-can-ask-for}

Quatre choses, et la liste est fermée :

| Champ | Signification |
|:------|:--------|
| `target_url` | L’adresse principale de l’instance : nom d’hôte, `http://` ou `https://` facultatif, et port facultatif. Pas de chemin, de chaîne de requête, de fragment ni d’identifiants. Obligatoire |
| `ignore_hardenings` | Les contrôles à exempter, choisis dans une liste autorisée fixe. Facultatif, répétable |
| `release_track` | `rolling`, `production`, `lts` ou `auto`. Facultatif, `auto` par défaut |
| `output_format` | `dashboard`, `json`, `csv`, `sarif` ou `pdf`. Facultatif, n’affecte que la présentation. Les formats réservés à l’export (`html`, `remediation-md`, `remediation-html`) s’obtiennent plutôt par le point de terminaison d’export |

`release_track` reprend l’idée de l’option `--release-track` du plugin : il
détermine combien de temps la version de l’instance est prise en charge et vers
quelle version l’inviter à mettre à jour. Il vaut `auto` par défaut, ce qui
demande au calendrier des versions à quel canal appartient la version installée -
la bonne réponse pour le serveur d’un inconnu, où toute supposition fixe est
fausse pour quelqu’un : supposer `production` déclare périmée une instance rolling
à jour, et supposer `rolling` annonce une fin de vie qu’une instance de production
n’a pas atteinte. Une valeur inconnue se rabat sur la valeur par défaut au lieu de
faire échouer l’analyse.

Tout autre champ est refusé avec **422**, en le nommant, au lieu d’être ignoré :
un appelant qui envoie `concurrency=50` doit apprendre que cela n’a eu aucun
effet, plutôt que de croire que cela a fonctionné. La concurrence, le nombre de
threads, les délais d’attente et la vérification TLS sont des paramètres de
l’opérateur et n’ont aucun équivalent côté requête.

La cible est une adresse, jamais un modèle de requête. Un chemin comme
`/apps/files`, une chaîne de requête, un fragment, des identifiants intégrés, des
espaces ou des caractères de contrôle de requête sont refusés au lieu d’être
écartés en silence. Le scanner choisit lui-même les chemins OpenCloud qu’il
connaît ; rien de ce qu’ajoute un visiteur ne peut devenir un chemin, un paramètre
ou une charge utile dans une requête sortante.

Les exemptions sont vérifiées par rapport à une liste autorisée construite à partir
du catalogue de durcissement : `*` et `debugPort:*` sont donc écartés au lieu
d’être respectés. Une exemption générique sur un service public serait un bandeau
sur les yeux avec un joli nom. Les indicateurs qu’OpenCloud code en dur ne sont pas
proposés non plus : exempter un constat que personne ne peut corriger laisserait
croire que quelqu’un le pourrait.

## Configuration {#configuration}

Chaque paramètre est une variable d’environnement, lue une fois au démarrage.

| Variable | Valeur par défaut | Effet |
|:---------|:---------|:-------------|
| `COS_WEB_REDIS_URL` | `redis://127.0.0.1:6379/0` | L’emplacement de l’état éphémère. `memory://` fonctionne sans Redis, pour une évaluation en un seul processus. Incluez le mot de passe lorsque Redis en exige un : `redis://:PASSWORD@redis:6379/0` |
| `COS_WEB_RESULT_TTL` | `3600` | Secondes pendant lesquelles une analyse reste lisible. C’est aussi la durée de vie de chaque clé |
| `COS_WEB_COMPARISON_TTL` | `300` | Secondes pendant lesquelles une comparaison avec un rapport téléversé reste lisible. Limitée à 300 ; une valeur plus courte est respectée |
| `COS_WEB_MAX_WORKERS` | `5` | Analyses exécutées simultanément |
| `COS_WEB_SCAN_CONCURRENCY` | `4` | Sondes en cours au sein d’une analyse |
| `COS_WEB_SCAN_TIMEOUT` | `15` | Durée maximale d’une sonde HTTP, en secondes |
| `COS_WEB_JOB_TIMEOUT` | `180` | Durée maximale d’une analyse complète, en secondes |
| `COS_WEB_VERIFY_TLS` | `true` | Vérifier le certificat de la cible. Une chaîne non reconnue devient un constat dans tous les cas |
| `COS_WEB_ALLOW_PRIVATE_TARGETS` | `false` | Autoriser les cibles privées, de bouclage et lien-local. Déploiements sur site uniquement |
| `COS_WEB_ALLOWED_HOSTS` | *(vide)* | Noms d’hôte exemptés de la protection SSRF, séparés par `;` |
| `COS_WEB_BLOCKED_TARGETS` | *(vide)* | Adresses que ce déploiement n’analysera pas, séparées par `;`. Noms d’hôte, domaines `.suffix` et plages CIDR. Prime sur les deux paramètres ci-dessus ; une entrée illisible empêche le démarrage |
| `COS_WEB_CHECK_DEBUG_PORTS` | `false` | Sonder des ports supplémentaires. Désactivé en public : c’est un balayage de ports de l’hôte de quelqu’un d’autre |
| `COS_WEB_IPV6_ENABLED` | `false` | Si ce service dispose de son propre accès IPv6 sortant. Désactivé, les adresses IPv6 ne sont jamais appelées et la comparaison TLS IPv4/IPv6 est ignorée, pour qu’une route manquante sur l’hôte d’analyse ne soit pas présentée comme un défaut de l’instance |
| `COS_WEB_IP_RATE_LIMIT` | `10` | Analyses par adresse cliente et par fenêtre. `0` désactive |
| `COS_WEB_IP_RATE_WINDOW` | `60` | La fenêtre, en secondes |
| `COS_WEB_TARGET_COOLDOWN` | `300` | Secondes avant que la même instance puisse être analysée de nouveau. `0` désactive |
| `COS_WEB_PROBE_LIMIT` | `5` | Analyses d’une même adresse cliente qui peuvent ne trouver aucun OpenCloud dans `COS_WEB_PROBE_WINDOW` avant que cette adresse soit bloquée. Le même hôte analysé à nouveau compte à nouveau. À définir sur le service web **et** sur le worker. `0` désactive |
| `COS_WEB_PROBE_WINDOW` | `300` | La fenêtre dans laquelle ces analyses sont comptées, en secondes |
| `COS_WEB_PROBE_BLOCK` | `3600` | Durée du premier blocage, en secondes |
| `COS_WEB_PROBE_BLOCK_MAX` | `86400` | Durée maximale qu’atteint un blocage répété ; chaque blocage dans la fenêtre de répétition dure six fois le précédent |
| `COS_WEB_PROBE_REPEAT_WINDOW` | `86400` | Délai, après la fin d’un blocage, pendant lequel le suivant s’aggrave, en secondes. `0` n’aggrave jamais |
| `COS_WEB_PROBE_IPV4_PREFIX` | `24` | Le réseau IPv4 que le blocage des sondes compte comme un seul client. `32` compte les adresses individuellement |
| `COS_WEB_CLIENT_IPV6_PREFIX` | `64` | Le réseau IPv6 que chaque limite par client compte comme un seul client |
| `COS_WEB_DAILY_SCAN_LIMIT` | `50` | Analyses par client et par jour, en plus de la limite par minute. `0` désactive |
| `COS_WEB_DNS_CONSISTENCY_CHECK` | `true` | Résoudre deux fois un nom soumis et le refuser lorsque les réponses n’ont aucune adresse en commun |
| `COS_WEB_REQUIRE_APPROVAL` | `false` | N’analyser que les instances approuvées ; voir [Mode d’approbation](#approval-mode) |
| `COS_WEB_APPROVED_TARGETS` | *(vide)* | Noms d’hôte, domaines `.suffix`, adresses et plages CIDR approuvés, séparés par `;`. Une entrée illisible empêche le démarrage |
| `COS_WEB_APPROVAL_DNS` | `true` | En mode d’approbation, accepter un enregistrement TXT `_check-opencloud-security` qui nomme le nom d’hôte de ce service |
| `COS_WEB_MAX_BATCH_TARGETS` | `10` | Nombre de cibles qu’un seul `POST /api/scans/batch` peut contenir. Chacune compte quand même dans toutes les limites |
| `COS_WEB_TRUST_FORWARDED_FOR` | `false` | Lire l’adresse du client dans `X-Forwarded-For` |
| `COS_WEB_TRUSTED_PROXY_HOPS` | `1` | Le nombre de vos propres proxies placés devant. L’en-tête est lu **par la droite**, à ce nombre d’entrées, car c’est la seule partie qu’un proxy écrit |
| `COS_WEB_RATE_LIMIT_SALT` | *(aléatoire par processus)* | Sel des clés de limitation du débit et de délai de carence. Doit avoir la **même valeur dans chaque processus web** d’un déploiement qui en exécute plusieurs : sans cela, chacun dérive ses propres clés, et un client obtient un quota par processus |
| `COS_WEB_PUBLIC_BASE_URL` | *(obligatoire)* | L’origine stable par laquelle ce service est joint, utilisée pour les liens canoniques, `sitemap.xml` et la découverte par les machines. Une valeur non définie empêche le démarrage, pour qu’un en-tête `Host` entrant ne puisse pas publier d’URL contrôlées par un attaquant |
| `COS_WEB_INDEX_META_TAG` | *(vide)* | Jusqu’à 10 paires de métadonnées `name=content` facultatives sur la page d’accueil, séparées par `;`. Les noms et contenus sont échappés séparément ; le HTML brut, les noms en double ou réservés et les métadonnées de plateformes interdites sont refusés |
| `COS_WEB_ALLOW_INDEXING` | `true` | Laisser les moteurs de recherche indexer la page d’accueil et ses pages d’explication. Les pages de résultats ne sont jamais indexables, quelle que soit cette valeur |
| `COS_WEB_RELEASES_MODE` | `off` | Vérification des mises à jour à partir du flux des versions OpenCloud : `off`, `auto`, `feed`, `bundled` |
| `COS_WEB_RELEASES_TOKEN` | *(aucun)* | Jeton GitHub qui relève la limite de débit du flux |
| `COS_WEB_SCHEDULE_REFRESH` | `true` | Relire une fois par jour la page du cycle de vie des versions OpenCloud et noter les analyses selon son contenu. Une requête par jour pour tout le déploiement, pas une par visiteur |
| `COS_WEB_SCHEDULE_REFRESH_URL` | *(la page du cycle de vie OpenCloud)* | L’endroit où ce calendrier est lu. Configuration de l’opérateur, qui peut donc pointer vers un miroir ; jamais un champ de requête |
| `COS_WEB_SCHEDULE_REFRESH_HOUR` | `4` | L’heure (UTC) de la lecture quotidienne. Utile à faire varier entre déploiements pour qu’ils n’arrivent pas tous en même temps |
| `COS_WEB_ADVISORY_REFRESH` | `true` | Demander une fois par jour au flux d’avis quelles vulnérabilités concernent OpenCloud et noter les analyses selon la réponse. Une actualisation ne fait qu’ajouter des avis, et ne croit jamais un avis sans bornes de version |
| `COS_WEB_ADVISORY_REFRESH_URL` | `https://api.osv.dev/v1/query` | L’endroit où les avis sont lus. Configuration de l’opérateur, qui peut donc pointer vers un miroir ; jamais un champ de requête |
| `COS_WEB_ADVISORY_REPOSITORY_URL` | `https://api.github.com/repos/opencloud-eu/opencloud/security-advisories` | Les avis du dépôt OpenCloud, lus à chaque actualisation pour ajouter ceux qu’OSV n’a jamais reçus ([ADR 0071](../../adr/0071-repository-advisories-are-a-second-advisory-source.md)). `off` les ignore ; un échec de lecture conserve la réponse d’OSV |
| `COS_WEB_FRONTEND_DIR` | *à côté de `webapp/`* | L’emplacement des modèles et des ressources statiques |
| `COS_WEB_ENABLE_DOCS` | `false` | Servir les pages consultables `/docs` et `/redoc`. Les documents lisibles par machine sont publics quelle que soit cette valeur |
| `COS_WEB_ENABLE_MCP` | `true` | Servir le point de terminaison MCP sur `/mcp` et enregistrer les outils WebMCP du navigateur. Ignoré lorsque l’extra facultatif `mcp` n’est pas installé |
| `COS_WEB_MCP_ALLOWED_HOSTS` | *(vide)* | Valeurs `Host` acceptées par le point de terminaison MCP, séparées par `;`. Vide, la vérification anti DNS rebinding est désactivée, ce qui convient lorsqu’un proxy fixe déjà l’hôte |
| `COS_WEB_MCP_MAX_CONCURRENT_WAITS` | `8` | Nombre d’appels d’outils MCP qui peuvent attendre une analyse en même temps. Atteindre ce plafond ne refuse rien : l’analyse est soumise et l’uuid est renvoyé pour être interrogé |
| `COS_WEB_MCP_AUTH_ENABLED` | `false` | Exiger un jeton porteur sur `/mcp`. Désactivé, car le service est fait pour répondre à tout le monde ; un déploiement qui veut l’inverse l’active et nomme un émetteur. Voir [une connexion sur le point de terminaison MCP](authentik.md) |
| `COS_WEB_MCP_AUTH_ISSUER` | *(vide)* | L’émetteur OIDC dont les jetons sont acceptés, exactement comme l’écrit son document de découverte. Une barre oblique finale est acceptée dans les deux cas |
| `COS_WEB_MCP_AUTH_AUDIENCE` | *(vide)* | Ce que le claim `aud` d’un jeton doit contenir, normalement l’ID client sous lequel les agents s’authentifient. **Obligatoire** lorsque la connexion est activée : vide, le service refuse de démarrer, car un jeton émis pour une autre application derrière le même fournisseur ouvrirait sinon celle-ci |
| `COS_WEB_MCP_AUTH_JWKS_URL` | *(déduite)* | L’endroit où les clés de signature sont publiées. Vaut par défaut `<issuer>/jwks/`, ce que répond un fournisseur qui suit la spécification de découverte |
| `COS_WEB_MCP_AUTH_RESOURCE_URL` | *(déduite)* | L’URL que ce point de terminaison revendique comme ressource protégée. Vaut par défaut `<COS_WEB_PUBLIC_BASE_URL>/mcp` ; l’audience d’un jeton est vérifiée par rapport à elle |
| `COS_WEB_MCP_AUTH_SCOPES` | *(vide)* | Les portées qu’un jeton doit porter, séparées par `;`. Vide, tout jeton valide de l’émetteur suffit |
| `COS_WEB_ADMIN_ENABLED` | `false` | Servir l’espace opérateur sur `/admin`. Désactivé, les routes ne sont pas enregistrées du tout : le chemin renvoie 404 comme tout autre chemin inconnu |
| `COS_WEB_ADMIN_PROXY_SECRET` | *(non défini)* | Le secret que l’outpost authentik ajoute sous `X-COS-Admin-Proxy`, et la seule raison de croire les en-têtes d’identité. Obligatoire lorsque l’espace est activé, d’au moins 32 caractères, sinon le démarrage est refusé |
| `COS_WEB_ADMIN_USERS` | *(vide)* | Qui peut utiliser l’espace, par nom d’utilisateur authentik, séparés par `;`. Vide avec l’espace activé, le service refuse de démarrer au lieu de comprendre « tout le monde » |
| `COS_WEB_ADMIN_SIGN_OUT_URL` | *(non défini)* | La destination du lien de déconnexion de l’espace. Ce service ne détient aucune session à terminer : la sortie appartient au fournisseur placé devant - pour la pile fournie, `/outpost.goauthentik.io/sign_out`. Non défini, le bandeau nomme l’opérateur sans proposer de sortie. Seuls un chemin local ou une URL `http(s)` sont acceptés ; toute autre valeur empêche le démarrage, car elle est rendue comme `href` sur une page dont la politique de contenu interdit les scripts |
| `COS_WEB_ADMIN_AUDIT_BUFFER` | `200` | Enregistrements d’audit récents conservés en mémoire pour la vue en direct, pour un déploiement qui journalise sur stdout. `0` n’en conserve aucun |
| `COS_WEB_ADMIN_REFRESH_COOLDOWN` | `60` | Intervalle minimal entre deux actualisations des mêmes données de référence déclenchées par l’opérateur. L’essai à blanc de l’espace - qui lit les deux sources sans rien appliquer - est retenu pendant le même intervalle sous sa propre clé, pour rester disponible juste après une actualisation qui a signalé un échec |
| `COS_WEB_UPDATE_CHECK` | `true` | Demander à GitHub si une version plus récente de ce service existe, uniquement pour l’espace opérateur et au plus toutes les six heures. Définissez `false` sans accès sortant |
| `COS_WEB_ADMIN_UPDATE_DIR` | *(non défini)* | Un tmpfs accessible en écriture (les fichiers compose en montent un sur `/var/lib/opencloud-scan/update`). Défini, l’espace opérateur peut installer une version plus récente : l’archive web est téléchargée depuis GitHub, vérifiée par rapport à son attestation de construction, décompressée ici, et les processus web et worker redémarrent dessus - une courte interruption, jusqu’au redémarrage des conteneurs. Non défini, l’espace se contente d’indiquer qu’une mise à jour existe |
| `COS_WEB_AUDIT_LOG` | `false` | Écrire un enregistrement d’audit pour chaque demande d’analyse, refus et limite déclenchée |
| `COS_WEB_AUDIT_LOG_TARGETS` | `false` | Enregistrer le nom d’hôte de la cible en clair plutôt que sous forme d’empreinte. Déploiements sur site uniquement |
| `COS_WEB_AUDIT_SALT` | *(aléatoire par processus)* | Sel des empreintes d’audit. En définir un permet de corréler les enregistrements après un redémarrage ; le changer y met fin |
| `COS_WEB_AUDIT_LOG_FILE` | *(la sortie du processus)* | Écrire plutôt les enregistrements d’audit dans ce fichier, sur un volume conservé après la suppression du conteneur. Lisible uniquement par son propriétaire, et le journal ordinaire n’en contient alors aucune copie. Un chemin impossible à écrire empêche le démarrage |
| `COS_WEB_AUDIT_LOG_MAX_BYTES` | `10000000` | Taille à partir de laquelle ce fichier est renouvelé. `0` ne le renouvelle jamais |
| `COS_WEB_AUDIT_LOG_BACKUPS` | `5` | Générations renouvelées conservées à côté. Avec la taille ci-dessus, cela fixe l’espace maximal occupé par la piste |
| `COS_WEB_AUDIT_LOG_ROTATION` | `service` | Qui renouvelle ce fichier : `service` (ce processus, selon la taille) ou `external` (logrotate sur l’hôte ; ce processus rouvre seulement le fichier remplacé). Une valeur inconnue empêche le démarrage |
| `COS_WEB_PURGE_TOKEN` | *(aucun)* | Active `DELETE /api/purge` et constitue le secret qu’il exige. Non défini, le point de terminaison répond 404 comme tout chemin inexistant. Au moins 32 caractères, sinon le démarrage est refusé : c’est toute l’autorisation de l’unique appel qui supprime les résultats d’autres personnes. Cinq mauvaises réponses d’une même adresse en cinq minutes sont suivies de `429` |
| `COS_WEB_PURGE_SIGNING_KEY` | *(aucune)* | Signe la preuve de suppression. Non définie, l’effacement a quand même lieu, mais le reçu ne peut pas être vérifié ensuite |
| `COS_WEB_EXPORT_SIGNING_KEY` | *(aucune)* | Ajoute un en-tête HMAC-SHA256 `X-COS-Signature` à chaque export JSON, CSV, SARIF et PDF |
| `COS_WEB_ENCRYPT_RESULTS` | `false` | Chiffrer le document de résultat stocké avec AES-256-GCM. Exige une clé ; un processus à qui l’on demande de chiffrer sans clé refuse de démarrer |
| `COS_WEB_WEBHOOK_SECRET` | *(aucun)* | Lu au démarrage mais non utilisé par le service web, qui n’envoie aucun webhook ; les webhooks signés relèvent de l’option `--webhook-secret` du plugin. Listé pour que sa définition ne soit pas prise pour une faute de frappe |
| `COS_WEB_ENCRYPTION_KEY_<n>` | *(aucune)* | Une clé de 32 octets sous forme de 64 caractères hexadécimaux. Le `<n>` le plus élevé chiffre, les plus bas déchiffrent encore : c’est ainsi qu’une clé est renouvelée |

`COS_WEB_RELEASES_MODE` vaut `off` par défaut, volontairement : un déploiement
public qui interroge le flux des versions à chaque visiteur est limité en débit,
et la vérification des mises à jour de tous les visiteurs échoue alors d’un coup.
Le calendrier des versions décide toujours de la fin de vie sans lui.

`COS_WEB_SCHEDULE_REFRESH` est le cas inverse, et il est activé par défaut. Le
calendrier livré dans l’image est écrit par la CI : un service en fonctionnement
depuis six semaines note donc les instances selon une image du monde vieille de
six semaines. Il qualifie la version de la semaine dernière d’« en avance sur le
calendrier » et une ligne expirée depuis la construction d’« encore prise en
charge ». Le worker relit donc une fois par jour la page publiée du cycle de vie -
également au démarrage, pour qu’un nouveau déploiement n’attende pas le milieu de
la nuit - et conserve le résultat dans Redis, où les tâches d’analyse le
récupèrent.

Une actualisation ne peut qu’ajouter des connaissances. Un document qui a perdu
une ligne connue du calendrier fourni est refusé, car une ligne manquante
transforme une instance en fin de vie en instance inconnue ; une page injoignable,
remaniée ou un tableau tronqué laissent tous le calendrier précédent exactement
tel quel ; et un fichier fourni plus récent après un redéploiement l’emporte sur
ce qui reste dans Redis. Rien n’est écrit dans le dépôt : `README.md` et le JSON
fourni restent l’affaire de la CI. Désactivez l’actualisation pour un déploiement
sans accès sortant, qui se comporte alors exactement comme avant. `/healthz`
indique la date du calendrier et l’heure de la dernière lecture réussie, et
[l’ADR 0016](../../adr/0016-the-release-schedule-refreshes-itself.md) en expose
le raisonnement.

`COS_WEB_ADVISORY_REFRESH` fait de même pour l’autre moitié de ce qui compose une
note, et c’est encore plus important. La base des avis décide si une instance est
*signalée comme vulnérable* : une base qui ignore l’avis du mois dernier ne se
contente pas de noter une instance avec indulgence, elle dit au visiteur qu’une
instance vulnérable va bien, sans qu’il puisse distinguer cette réponse d’une
vraie. Le worker interroge donc le flux une fois par jour, également au
démarrage, et les tâches d’analyse notent selon la dernière réponse acceptée.

Les règles sont le reflet de celles du calendrier, car l’échec peut aller dans les
deux sens. Une actualisation **ne fait qu’ajouter** : la réponse est fusionnée dans
la base dont dispose déjà le déploiement, si bien qu’un flux renvoyant une liste
vide ne change rien et qu’une entrée rédigée à la main est conservée. Rien de
**non borné** n’est jamais cru - un avis qui ne nomme aucune version
correspondrait à toutes les versions ayant jamais existé, et des flux publics
publient bien cette forme -, et une réponse contenant un nombre absurde d’avis est
refusée en bloc. Tout échec laisse la base exactement telle qu’elle était. Rien
n’est écrit sur disque ; le JSON fourni reste l’affaire de la CI, actualisé par
`.github/workflows/vulnerability-db.yml`. Désactivez-la pour un déploiement sans
accès sortant, qui note alors selon le fichier fourni, exactement comme le fait le
plugin sur un hôte de supervision. `/healthz` indique le nombre d’avis utilisés
pour noter et la date de la dernière interrogation - des décomptes et des dates,
jamais un constat -, et
[l’ADR 0017](../../adr/0017-the-advisory-database-refreshes-itself.md) en expose
le raisonnement.

## Le parcours d’une analyse {#how-a-scan-flows-through-it}

```text
POST /api/scans ──► client rate limit ──► SSRF guard ──► waiver allow-list
                                                              │
                          target cooldown ◄────────────────────┘
                                 │
                                 ▼
                    uuid4 ──► Redis (queued) ──► ARQ ──► 303 /scan/{uuid}
                                                          │
   worker: re-resolve ──► scan() ──► Redis (completed) ◄───┘
```

La limite par client s’applique en premier, car c’est un seul `INCR` et elle
empêche que le résolveur derrière la protection SSRF serve d’amplificateur. Le
délai de carence s’applique en dernier, pour qu’une requête qui allait de toute
façon être refusée ne consomme pas le créneau d’une cible jamais analysée.

## Mettre en file d’attente plutôt que refuser {#queueing-rather-than-refusing}

Plus de visiteurs que de workers, c’est une file d’attente, pas une panne. Chaque
requête qui passe la validation reçoit un uuid et une réponse **202** (ou **303**
depuis le formulaire), puis attend dans une file FIFO. La page d’analyse affiche
la position - *« Analyse en file d’attente. Position : n° 2 sur 7 »* - et le
script d’interrogation la met à jour toutes les deux secondes jusqu’à ce qu’un
worker prenne la tâche.

Rien dans la requête ne permet de passer devant ni d’élargir la file.
`COS_WEB_MAX_WORKERS` est le seul élément qui décide du nombre d’analyses
simultanées, et il est lu dans l’environnement au démarrage du worker.

## Isolation entre les analyses {#isolation-between-scans}

Chaque analyse reçoit un `uuid4` et trois clés qui lui sont propres :

```text
scan:{uuid}:status      queued | running | completed | failed
scan:{uuid}:result      the result document
scan:{uuid}:metadata    target, waivers, timestamps
```

L’uuid est une capacité : le connaître est le seul moyen d’atteindre l’analyse.

- il n’existe **aucun** point de terminaison de liste, et il n’en existera
  jamais ; une seule requête réduirait toute la conception à néant.
  `GET /api/scans` se contente de renvoyer un navigateur vers le formulaire, sans
  rien transmettre ;
- un uuid inconnu, invalide ou expiré donne une réponse **404** avec un corps
  identique dans les trois cas : un inconnu ne peut donc pas apprendre qu’un uuid
  a existé ;
- chaque clé porte la durée de vie, y compris celle écrite pendant que l’analyse
  est encore en file d’attente. Les données expirent après la durée de
  conservation indiquée sur la page d’accueil.

## Comparer deux analyses {#comparing-two-scans}

`GET /compare` répond à la question qui suit un plan de correction : *cela a-t-il
servi ?* Il prend deux uuid que le lecteur possède déjà - `?baseline=` pour
l’analyse antérieure, `?current=` pour la plus récente - et montre ce qui a été
résolu, ce qui est nouveau, ce qui reste ouvert et comment la note a évolué. Une
page de résultat terminée y renvoie avec son propre uuid déjà rempli : seul
l’uuid antérieur doit être collé.

Les comparaisons utilisent `opencloud_local_scan.baseline` via
`workflows.compare_documents`, le même calcul que celui de la CLI et de l’outil
MCP `compare_scans`. Voir
[l’ADR 0029](../../adr/0029-a-comparison-is-two-live-results-and-one-arithmetic.md).

**Rien n’est stocké.** La comparaison est calculée à partir de deux résultats qui
existent encore tous deux et n’est écrite nulle part : ce service ne conserve
aucun historique d’analyses ([ADR 0002](../../adr/0002-no-scan-result-caching.md))
et un uuid est une capacité avec une durée de vie
([ADR 0007](../../adr/0007-erasure-on-request.md)). Une comparaison stockée serait
un résultat d’analyse sous un autre nom, qui survivrait aux résultats qu’elle
décrit et échapperait à leur effacement. Le seul cas où une comparaison *est*
conservée - parce que le fichier dont elle est tirée n’existe plus et que rien ne
pourrait la recalculer - est décrit [ci-dessous](#comparing-against-a-report-you-uploaded),
et elle est conservée cinq minutes, sous une capacité, et soumise à l’effacement
auquel elle échapperait sinon.

Les réponses possibles :

| Situation | Réponse |
|:----------|:-------|
| Les deux uuid correspondent à des analyses terminées | **200**, la comparaison |
| L’un des uuid est inconnu ou expiré | **404**, en indiquant *lequel* a disparu - « l’un des deux a expiré » obligerait à les vérifier tous les deux |
| L’une des analyses n’est pas terminée | **409** : il n’y a encore rien à comparer, et une réponse 404 pousserait le lecteur à relancer une analyse alors que la sienne tourne encore |
| Deux fois le même uuid | **422**. Une comparaison vide d’une analyse avec elle-même se lirait comme « tout va bien » |
| Les deux analyses décrivent des instances différentes | **422**, pas de comparaison. « La correction a-t-elle fonctionné ? » est une question sur une seule instance, et comparer deux hôtes par erreur donne une mauvaise réponse que personne ne remarque - `check-opencloud-scanner diff` les refuse aussi. Voir [l’ADR 0059](../../adr/0059-a-comparison-refuses-two-different-instances.md) |

Comme `/scan/{uuid}`, et pour la même raison, la page affiche des résultats : elle
n’est donc jamais indexée ni présente dans le schéma OpenAPI, et chaque uuid
reste l’unique autorisation d’accès au résultat correspondant.

## Comparer avec un rapport téléversé {#comparing-against-a-report-you-uploaded}

La comparaison ci-dessus exige que les deux analyses existent encore, et la
référence intéressante est généralement plus ancienne que l’heure de vie d’un
résultat. `POST /compare` prend donc le côté antérieur sous forme de **fichier** :
le JSON ou le CSV téléchargé depuis une page de résultat, téléversé depuis le
disque du lecteur, comparé à une analyse de ce service qui n’a pas expiré. Même
page, même calcul, mêmes verdicts - seule change la provenance du document
antérieur. Voir [l’ADR 0057](../../adr/0057-an-uploaded-report-is-evidence-not-a-scan.md).
Un rapport portant sur une autre instance que l’analyse à laquelle il est
comparé, ou qui ne nomme aucune instance, est refusé de la même façon avec 422.

C’est une fonction du navigateur et elle le reste : HTML uniquement, jamais dans
le schéma OpenAPI, et aucun outil MCP ne la propose. Un agent dispose déjà de
`compare_scans`, qui prend deux uuid - la forme qu’un agent est en mesure de
fournir.

**Le fichier est la seule structure non fiable que ce service analyse.** Tout le
reste de ce qu’il compare provient de son propre scanner quelques minutes plus
tôt, où la partie non fiable est une *chaîne à l’intérieur* d’un document
construit par ce service. Un téléversement franchit donc une seule frontière,
`webapp/imports.py`, et ce qui en sort n’est pas ce qui y est entré : un document
de résultat reconstruit clé par clé à partir d’une liste autorisée - les champs
que lit `baseline.snapshot_of`, chacun vérifié en type, en longueur et en forme.
Une clé non nommée à cet endroit n’atteint rien en aval.

| Protection | Valeur |
|:------|:------|
| Taille maximale lue | 256 Ko, bien en dessous de la limite de corps de 1 Mo qui a déjà refusé tout ce qui est plus gros |
| Encodage | UTF-8 strict ; un octet NUL ou une séquence invalide est refusé plutôt que réparé |
| Format | déterminé en examinant les octets, jamais d’après le nom du fichier - qui n’est lu par rien et jamais reproduit dans une page |
| Lignes CSV | 2 000 |
| Imbrication JSON | 20 niveaux |
| Entrées par bloc, caractères par chaîne | 500 et 300 ; un bloc comportant davantage d’entrées est refusé plutôt que lu en partie |
| Identifiants de constats | écartés s’ils ne sont pas écrits comme ce scanner écrit les siens, et le nombre d’éléments illisibles est affiché |
| Limitation du débit | un compteur propre, avec les mêmes valeurs que la limite par client - une analyse de fichier utilise les ressources de ce service sans contacter d’instance |
| POST intersite | refusé avant le limiteur et avant l’analyse du fichier |
| Réseau soumis à un blocage des sondes | refusé avant les deux, et avant la lecture du fichier : le blocage est un jugement sur le client, pas sur un point de terminaison |

**Un fait que le format n’a jamais enregistré est retiré des deux côtés plutôt
que deviné.** Le CSV est un tableau plat de constats ; le fait qu’une mise à jour
était en attente et que HTTPS était imposé se trouve en dehors de ce tableau. Les
deux sont désormais écrits sous forme de lignes, mais un fichier téléchargé avant
cela ne dit rien à leur sujet - et le silence ne vaut pas « non ». Ces mesures
sont neutralisées dans *les deux* documents avant la comparaison, et la page
indique ce qu’elle a laissé de côté. JSON permet un aller-retour sans perte ; le
CSV est un tableur qu’il se trouve possible de relire.

**Le fichier n’est jamais stocké. La comparaison l’est, pendant cinq minutes.** Le
téléversement est lu une fois en mémoire et écrit nulle part. Ce qui subsiste est
la comparaison qui en est tirée, conservée sous un nouvel uuid4 dans son propre
espace de noms `compare:{token}:*`, pour qu’un rechargement et un lien partagé
continuent de fonctionner - la seule chose ici qui ne peut pas être recalculée,
puisque le fichier d’origine n’existe plus. Le jeton se comporte comme un uuid
d’analyse : inconnu, mal formé ou expiré donnent la même réponse 404, rien ne les
liste, et le chiffrement des résultats s’applique lorsqu’il est configuré.
`COS_WEB_COMPARISON_TTL` peut raccourcir ce délai, pas l’allonger.

**Une demande d’effacement l’atteint.** `DELETE /api/purge` parcourt l’espace de
noms des comparaisons comme celui des analyses et supprime chaque comparaison en
cache qui nomme cette instance de l’un ou l’autre côté, en comptant les clés dans
le même reçu pour que `remaining: 0` garde son sens. Une durée de vie de cinq
minutes n’est pas une raison d’exclure quelque chose d’un effacement : c’est
l’argument que [l’ADR 0007](../../adr/0007-erasure-on-request.md) rejette pour le
résultat lui-même.

| Situation | Réponse |
|:----------|:-------|
| Un rapport lisible et une analyse terminée | **303** vers `/compare/{token}` |
| Pas de fichier, ou pas d’uuid | **422**, en indiquant la moitié manquante |
| L’uuid récent est inconnu ou expiré | **404** |
| L’analyse récente n’est pas terminée | **409** |
| Le fichier est vide, trop volumineux, pas en UTF-8, ou ni JSON ni CSV | **422**, ou **413** pour la taille, dans les termes propres de ce service - un téléversement refusé n’est jamais cité |
| Le fichier est lisible mais n’est pas un rapport d’analyse | **422** |
| Trop de téléversements depuis un même réseau | **429** avec `Retry-After` |
| Le réseau fait l’objet d’un blocage des sondes | **429** avec `Retry-After`, pendant toute la durée restante du blocage |
| `GET /compare/{token}` après cinq minutes | **404**, exactement comme pour un jeton qui n’a jamais existé |

## La protection SSRF {#the-ssrf-guard}

Un service d’analyse public transmet des requêtes par définition : la cible est
donc vérifiée avant toute connexion.

- le schéma doit être `http` ou `https` ;
- la soumission peut contenir un simple chemin de base pour une instance
  installée dans un sous-dossier, mais ni chaîne de requête, ni fragment, ni
  identifiants, ni paramètres de chemin, ni séquences d’échappement ou de
  remontée. Les redirections envoyées par l’instance peuvent contenir des chemins
  ordinaires, mais elles sont revalidées indépendamment avant d’être suivies ;
- le nom d’hôte doit se résoudre, et **toutes** les adresses vers lesquelles il se
  résout doivent être des adresses unicast publiques. Une seule réponse privée
  parmi plusieurs fait rejeter la cible, ce qui rend inutile l’astuce des
  enregistrements multiples ;
- `localhost`, `*.internal`, `*.local` et les noms de métadonnées cloud sont aussi
  refusés par leur nom, car un résolveur qui y répond par une adresse publique est
  défaillant ou ment ;
- `169.254.169.254`, `100.100.100.200` et `fd00:ec2::254` sont refusés
  explicitement. Le lien-local couvre déjà la première, mais les nommer rend le
  refus lisible et résiste à une future exception ;
- les noms relevant de services DNS génériques et de rebinding - `nip.io`,
  `sslip.io`, `xip.io`, `traefik.me`, `localtest.me`, `lvh.me`, `vcap.me`,
  `lacolhost.com`, `localhost.direct`, `local.gd`, `rbndr.us`, `1u.ms` - sont
  refusés par leur nom. Ils existent pour faire pointer un nom là où son lecteur
  ne s’y attend pas ; l’adresse publique qui se trouve derrière peut toujours être
  analysée en la saisissant directement ;
- un nom soumis est résolu deux fois simultanément, et refusé lorsque les deux
  réponses n’ont aucune adresse en commun (`COS_WEB_DNS_CONSISTENCY_CHECK`).
  Chaque adresse des deux réponses est soumise aux règles ci-dessus.

Le **DNS rebinding** est contré par une double résolution : une fois lorsque la
requête est acceptée, puis dans le worker juste avant l’analyse. La fenêtre que
peut viser un attaquant se réduit alors à une seule résolution, et rien dans la
requête ne peut l’élargir, car rien dans la requête n’influe sur le moment où un
worker se libère.

`COS_WEB_ALLOW_PRIVATE_TARGETS=true` désactive tout cela. Ce paramètre existe pour
un déploiement sur site qui analyse son propre parc. Ne le définissez sur rien
d’accessible à un inconnu.

### Adresses que ce déploiement n’analysera pas {#addresses-this-deployment-will-not-scan}

Tout ce qui précède est une propriété de l’adresse. `COS_WEB_BLOCKED_TARGETS` est
une décision prise par quelqu’un - le propriétaire d’une instance qui a demandé à
être laissé tranquille, un hôte que quelqu’un soumet sans cesse au point que le
service le martèle, une plage qui n’est pas une cible d’analyse ici, aussi
publique qu’elle paraisse :

```bash
COS_WEB_BLOCKED_TARGETS="opencloud.example.com;.example.org;203.0.113.0/24"
```

- une entrée est un **nom d’hôte**, un **suffixe de domaine** précédé d’un point
  (`.example.org`, ou `*.example.org` - les deux désignent le domaine *et* tout ce
  qui se trouve en dessous, et aucun ne correspond à `notexample.org`), une
  **adresse** ou une **plage CIDR** ;
- les noms d’hôte sont comparés sur le nom, les plages sur **chaque adresse vers
  laquelle le nom se résout**. Une entrée de nom d’hôte refuse donc ce nom, mais
  pas un second nom pointant vers la même machine : excluez la plage lorsque
  l’engagement doit tenir quel que soit le nom de l’instance ;
- la vérification a lieu à la soumission, de nouveau dans le worker avant
  l’analyse, et à chaque étape de redirection : une cible exclue pendant que sa
  tâche attendait dans la file est refusée plutôt qu’analysée ;
- elle **prime sur `COS_WEB_ALLOWED_HOSTS` et `COS_WEB_ALLOW_PRIVATE_TARGETS`**.
  Ces paramètres existent pour assouplir la protection ; celui-ci décide si le
  service analyse cette adresse, et un assouplissement ne doit pas la rouvrir.
  Voir [l’ADR 0043](../../adr/0043-an-operators-exclusion-outranks-every-allowance.md) ;
- une entrée qui n’a aucune de ces quatre formes **empêche le démarrage**, dans le
  processus web comme dans le worker. Une faute de frappe serait sinon invisible :
  le service démarre, répond normalement et analyse exactement ce qu’on lui avait
  demandé de ne pas analyser.

Le refus que voit un visiteur indique seulement que le service a été prié de ne
pas analyser cette adresse. L’entrée correspondante relève de la configuration de
l’opérateur, et la reproduire ferait de chaque refus une lecture de la liste.

**La liste a une seconde moitié modifiable pendant que le service tourne.** La
demande à l’origine de la plupart des exclusions - quelqu’un qui écrit pour
demander à ne pas être analysé - arrive rarement à un moment opportun, et « après
la prochaine fenêtre de déploiement » n’est pas une réponse acceptable. L’espace
opérateur sur `/admin` dispose donc d’une carte *Exclusions* qui ajoute et retire
des entrées, et :

- une entrée prend effet **dès la requête suivante, dans chaque processus**, sans
  aucun redémarrage : l’API lit la liste à chaque soumission et le worker au début
  de chaque tâche, si bien qu’une analyse qui attend déjà dans la file est refusée
  plutôt qu’exécutée ;
- ce que déclare `COS_WEB_BLOCKED_TARGETS` **ne peut pas y être retiré**. Ces
  entrées sont affichées sans commande à côté, et une tentative de suppression est
  refusée avec un renvoi vers l’environnement : votre fichier compose reste la
  source de vérité pour ce qu’il déclare ;
- les entrées ajoutées dans l’espace sont stockées dans **Redis** : elles sont donc
  aussi durables que votre Redis. Tout ce qui doit survivre à un vidage relève de
  la variable d’environnement ;
- une entrée compte au plus **253 caractères**, la longueur maximale d’un nom
  d’hôte, ici comme dans `COS_WEB_BLOCKED_TARGETS`. Au-delà, elle ne pourrait
  jamais correspondre à une cible acceptée par le service : elle est donc refusée
  comme la faute de frappe qu’elle est ;
- les deux moitiés sont comparées **après analyse, et non comme du texte** :
  `Example.COM` dans l’environnement et `example.com` dans l’espace constituent
  une seule exclusion, pas deux. L’espace refuse d’enregistrer ce que
  l’environnement contient déjà, et refuse de le retirer sous quelque graphie que
  ce soit ;
- si le stockage ne peut pas être lu, une soumission est **refusée plutôt
  qu’analysée** sans la liste - `503`, avec la raison dans la langue du visiteur
  et un renvoi vers l’auto-hébergement, et une ligne `exclusions_unreadable` dans
  la piste d’audit plutôt qu’une cible rejetée.

Cette carte est le seul élément de l’espace qui écrit ; voir
[l’ADR 0044](../../adr/0044-the-operator-area-may-write-the-exclusions.md) pour
les quatre propriétés qui l’ont rendue acceptable à cet endroit, et
[ADMIN.md](../../ADMIN.md#the-operators-area-at-admin) pour l’espace lui-même.

## Limitation du débit {#rate-limiting}

Chaque limite est stockée dans Redis et expire d’elle-même :

- **par client** - `COS_WEB_IP_RATE_LIMIT` analyses par `COS_WEB_IP_RATE_WINDOW`,
  et au plus `COS_WEB_DAILY_SCAN_LIMIT` par jour. Protège le service d’un
  visiteur, et le plafond quotidien protège de la version patiente d’une rafale
  qui reste toute la nuit juste sous la limite par minute ;
- **par cible** - une analyse par `COS_WEB_TARGET_COOLDOWN`. Protège une instance
  OpenCloud contre le service. Réservée avec `SET NX`, pour que deux requêtes
  simultanées sur la même instance ne puissent pas toutes deux l’emporter ;
- **le blocage des sondes** - `COS_WEB_PROBE_LIMIT` infractions dans
  `COS_WEB_PROBE_WINDOW` bloquent le réseau du client pendant
  `COS_WEB_PROBE_BLOCK`. Protège les hôtes de tous les autres contre l’utilisation
  de ce service pour découvrir ce qui répond où.

Toutes répondent **429** avec un `Retry-After`. L’adresse du client n’est jamais
stockée : une clé contient un HMAC tronqué avec un secret (pepper), ce qui suffit
pour compter et ne sert à rien ensuite.

**Ce qui compte comme un client.** Une seule adresse IPv4 pour les limites par
minute et par jour, car des inconnus derrière un même /24 ne doivent pas partager
un quota ; un /64 IPv6 (`COS_WEB_CLIENT_IPV6_PREFIX`) pour toutes les limites, car
un abonné reçoit un /64 entier et pourrait sinon le parcourir gratuitement. Le
blocage des sondes compte aussi le réseau IPv4 `COS_WEB_PROBE_IPV4_PREFIX` (`/24`
par défaut), pour qu’un blocage ne puisse pas être contourné en passant à
l’adresse voisine.

**Ce qui constitue une infraction.** Une analyse qui se termine par le verdict du
scanner *pas d’OpenCloud ici* - `status.php` injoignable, pas du JSON, ou un autre
produit - ou qui dépasse son délai ; et une soumission que la protection refuse à
cause de ce qu’elle vise : une adresse privée ou interne, une exclusion de
l’opérateur, un nom DNS générique ou de rebinding, un nom dont les résolutions ne
concordent pas, ou - en mode d’approbation - une instance que personne n’a
approuvée. Le même hôte à nouveau est une nouvelle infraction, car demander sans
cesse à une même adresse si elle répond enfin, c’est aussi sonder. Une analyse
terminée ne compte jamais, quelle que soit sa note, pas plus qu’une faute de
frappe, un nom qui ne se résout pas ou un schéma non pris en charge.

**Les blocages s’allongent lorsqu’ils sont de nouveau mérités.** Un réseau bloqué
de nouveau dans les `COS_WEB_PROBE_REPEAT_WINDOW` qui suivent la fin de son dernier
blocage attend six fois plus longtemps - une heure, six heures, un jour - jusqu’à
`COS_WEB_PROBE_BLOCK_MAX`. Les infractions dues à des analyses qui se terminent
pendant un blocage ne changent rien, et un réseau qui reste à l’écart pendant la
fenêtre de répétition recommence à une heure.

**Le blocage est décidé après coup.** Seul le worker apprend si un hôte était un
OpenCloud : la soumission lui transmet donc l’empreinte du réseau - jamais
l’adresse - sous `scan:{uuid}:prober`, que le worker lit et supprime dès le début
de l’analyse. Le worker compte ces infractions, l’API compte les cibles refusées,
et tous deux imposent le blocage par les mêmes clés ; l’API le lit avant la limite
par client, pour que les refus pendant un blocage ne consomment pas aussi le quota
dont le visiteur disposera à son retour. MCP et les workflows attendent
d’eux-mêmes un `Retry-After` allant jusqu’à cinq minutes et rendent à l’appelant
tout délai plus long - un blocage ou un plafond quotidien épuisé.

**Un hôte qui n’est pas un OpenCloud n’est interrogé qu’une fois.** Le scanner lit
`status.php` avant toute autre chose, et le service web définit
`ScannerSettings.stop_when_not_opencloud` : une réponse HTTPS qui ne vient pas
d’OpenCloud met fin à l’analyse, au lieu d’une nouvelle tentative sans
vérification du certificat puis sur le port 80, comme le fait le plugin pour un
opérateur qui cherche le point de terminaison qui fonctionne. L’absence de réponse
donne toujours lieu à une nouvelle tentative, car il peut ne s’agir que d’un
certificat non reconnu.

Un opérateur légitime dont l’instance est hors service peut lui aussi rencontrer
le blocage, après cinq tentatives. C’est le compromis : le message en donne la
raison et suggère d’exécuter le scanner localement, ce qui n’a pas cette limite.

**L’espace opérateur montre la protection à l’œuvre** - réseaux actuellement
bloqués, ainsi que blocages, infractions et plafonds quotidiens épuisés du jour et
des sept derniers jours - sous forme de décomptes. Les clés de blocage sont
comptées, jamais lues ni listées.

### Mode d’approbation {#approval-mode}

`COS_WEB_REQUIRE_APPROVAL=true` transforme le scanner public en scanner qui
n’analyse que les instances approuvées et refuse les autres avec **403**. Une
instance est approuvée lorsqu’elle correspond à `COS_WEB_APPROVED_TARGETS` - noms
d’hôte, domaines `.suffix`, adresses et plages CIDR, les mêmes formes que les
exclusions - ou, avec `COS_WEB_APPROVAL_DNS` (activé par défaut), lorsque sa
propre zone publie

```text
_check-opencloud-security.opencloud.example.com. TXT "check-opencloud-security=scan.example.net"
```

en nommant le nom d’hôte de ce service tiré de `COS_WEB_PUBLIC_BASE_URL`.
L’enregistrement approuve un déploiement, pas toutes les copies du projet, et ne
nécessite aucun secret : quiconque peut publier un enregistrement TXT sous un nom
contrôle ce nom, ce qui est exactement ce que l’approbation demande de prouver. La
résolution passe uniquement par le résolveur système, comme le contrôle CAA du
scanner (ADR 0024), et une résolution qui échoue vaut refus. L’approbation est
vérifiée à la soumission. Un déploiement qui exige l’approbation avec une liste
vide et la preuve DNS désactivée, ou avec une entrée illisible, refuse de
démarrer.

**Une page de rapport décompte l’attente.** Un rapport terminé comporte un bouton
**Analyser de nouveau**, et à côté le temps restant avant que ce soit autorisé.
Chaque limite en jeu est lue - `RateLimiter.peek_client`, `peek_daily`,
`peek_target` et le blocage des sondes, qui sont les vérifications ordinaires sans
le comptage - et la plus longue est affichée, car un compte à rebours qui
aboutirait à un refus dû à *une autre* limite serait pire que rien. Lire une limite
ne doit jamais la consommer, sinon montrer son attente à quelqu’un serait
précisément la requête qui la provoque.

Le nom d’hôte provient de l’enregistrement que l’uuid a déjà déverrouillé : cela
ne demande rien que l’appelant n’ait apporté lui-même. Il est impossible de se
renseigner sur une cible dont on ne détient pas l’uuid, et l’uuid reste
l’unique autorisation. Le bouton lui-même est un formulaire ordinaire qui envoie à
`/` la cible, les exemptions, le canal de versions et le format de sortie de la
première analyse : la vérification intersite, les deux limites, la protection SSRF
et la piste d’audit s’y appliquent exactement comme à toute autre soumission, et
le second résultat est noté dans les mêmes conditions que le premier.

**Ce qu’un refus apprend à un inconnu.** Le délai de carence par cible est
partagé : sa réponse 429 indique qu’une instance a été analysée récemment - par
n’importe qui. C’est inhérent à un délai de carence par cible, et non une fuite de
l’implémentation, et c’est limité par ce que cela coûte : chaque sonde, y compris
au sein d’un lot, consomme une analyse de la propre fenêtre du client qui sonde,
et une cible qui répond « pas récemment » vient d’être réservée par lui. Un
déploiement qui ne veut pas du tout que la question ait une réponse définit
`COS_WEB_TARGET_COOLDOWN=0` et s’en remet à la seule limite par client. Rien, nulle
part, n’indique *qui* l’a analysée.

## Ce qui est journalisé {#what-gets-logged}

Des marqueurs de cycle de vie et un uuid :

```text
scan_created 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_started 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
scan_completed 0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa
```

Ni URL cible, ni adresse client, ni résultat. Un journal qui enregistre ce que
tout le monde a analysé *est* une base de données de ce que tout le monde a
analysé, aussi courte soit sa durée de conservation.

### La piste d’audit facultative {#the-optional-audit-trail}

Un opérateur qui exploite ce service pour d’autres personnes finit par devoir
répondre à des questions que les lignes ci-dessus ne permettent pas de trancher :
un réseau a-t-il soumis des analyses toute la nuit, les limites ont-elles tenu,
quelqu’un sonde-t-il le point de terminaison avec des champs qu’il n’accepte pas ?
`COS_WEB_AUDIT_LOG=true` active un second journal, distinct, exactement pour
cela - le logger `check_opencloud.web.audit`, un objet JSON par ligne, pour qu’il
puisse être acheminé et conservé séparément :

```json
{"client": "9f2c1b7d4e6a0c58", "event": "scan_requested", "outputFormat": "dashboard", "releaseTrack": "production", "target": "1a4b9e0f7c23d865", "timestamp": "2026-08-19T10:14:02+00:00", "uuid": "0f4a1f22-7ce0-4f74-8a01-4d1d5b60e2aa", "waivers": 0}
{"client": "9f2c1b7d4e6a0c58", "event": "rate_limited", "retryAfter": 42, "scope": "rate_limit_client", "timestamp": "2026-08-19T10:14:44+00:00"}
{"client": "3c80d5f21ab94e77", "event": "submission_rejected", "fields": ["workers"], "reason": "unsupported_fields", "status": 422, "timestamp": "2026-08-19T10:15:09+00:00"}
```

Trois événements : `scan_requested` pour une soumission acceptée, `rate_limited`
pour une limite par client, un délai de carence par cible, un plafond quotidien
(`rate_limit_daily`), un blocage des sondes (`rate_limit_probe`) ou un
téléversement de rapport (`rate_limit_upload`) réellement déclenché, et
`submission_rejected` pour une soumission qui n’est jamais devenue une analyse -
`unsupported_fields`, `target_rejected`, `target_not_approved` - ou pour un
rapport téléversé que l’analyseur a refusé de lire (`report_rejected`, qui porte
dans `fields` la clé du refus propre à ce service et aucune partie du fichier).

L’intérêt de la conception tient à ce qu’elle n’écrit toujours pas :

- **Une adresse client est toujours une empreinte**, un HMAC tronqué avec le sel
  d’audit, et aucun paramètre ne change cela. Deux requêtes d’un même réseau
  partagent une empreinte, ce dont un audit a besoin ; rien ne permet de remonter
  de l’une à l’adresse.
- **La cible est aussi une empreinte**, sauf si `COS_WEB_AUDIT_LOG_TARGETS=true`
  indique que le déploiement analyse son propre parc et veut le nom d’hôte.
- **Le sel est aléatoire par processus**, sauf si `COS_WEB_AUDIT_SALT` est défini.
  Corréler les enregistrements après un redémarrage est un choix délibéré, et
  changer le sel l’annule. **Traitez un sel que vous définissez comme un secret**,
  avec le même soin que `COS_WEB_PURGE_TOKEN` : une empreinte n’est un pseudonyme
  que tant que le sel est inconnu, et quiconque l’apprend peut retrouver les
  adresses clientes d’un journal en hachant l’espace d’adressage. Un sel aléatoire
  par processus n’a pas cette propriété, c’est pourquoi il est la valeur par
  défaut.
- **Un nom de champ soumis est enregistré, pas exécuté** : raccourci, débarrassé
  des caractères de contrôle et échappé en JSON, pour qu’un saut de ligne dans un
  corps de requête ne puisse pas forger un second enregistrement.

Le laisser désactivé ne change rien : le journal de cycle de vie ordinaire est
exactement celui décrit ci-dessus.

#### Conserver la piste au-delà du conteneur {#keeping-the-trail-past-the-container}

Par défaut, ces enregistrements vont sur la sortie du processus, c’est-à-dire,
pour un conteneur, dans `docker logs` — et un `docker compose down` les emporte
avec lui. Une question d’audit arrive des mois après les faits : un déploiement
qui veut pouvoir y répondre doit placer la piste à un endroit qui survit à la
pile.

```yaml
services:
  web_app:
    environment:
      COS_WEB_AUDIT_LOG: "true"
      COS_WEB_AUDIT_LOG_FILE: "/var/log/opencloud-scan/audit.log"
      # Rotated at this size, keeping this many generations. Together they are
      # the most the trail can ever occupy: an audit log nobody rotates fills
      # the volume it sits on and takes the service down with it.
      COS_WEB_AUDIT_LOG_MAX_BYTES: "10000000"
      COS_WEB_AUDIT_LOG_BACKUPS: "5"
    volumes:
      - audit_log:/var/log/opencloud-scan

volumes:
  audit_log:
```

Trois conséquences en découlent, toutes voulues :

- **Les enregistrements vont dans le fichier au lieu de la sortie, et non en plus
  d’elle.** Le journal ordinaire est le seul endroit que ce service garde exempt de
  cibles et d’empreintes de clients, et un déploiement qui l’expédie vers un
  système central ne doit pas y trouver la piste d’audit.
- **Le fichier est lisible uniquement par son propriétaire**, générations
  renouvelées comprises. Un volume monté est lisible par quiconque accède à l’hôte
  qui l’héberge.
- **Un fichier impossible à écrire arrête le processus**, avec le chemin dans le
  message. Annoncer une piste d’audit qui ne mène discrètement nulle part est pire
  que de ne pas en avoir, selon le même raisonnement que
  [l’ADR 0008](../../adr/0008-refuse-to-start-without-the-encryption-key.md).

Un volume nommé est la solution la plus simple, et celle que
[`docker/setup-wizard.py`](../../docker/setup-wizard.py) propose en premier. Un
montage lié vers un répertoire de l’hôte fonctionne de la même façon — pour une
expédition de journaux ou des sauvegardes existantes —, mais le répertoire doit
exister et appartenir à l’uid `10001`, l’utilisateur non privilégié de l’image,
avant le démarrage de la pile :

```bash
mkdir -p /srv/opencloud-scan/audit
sudo chown 10001 /srv/opencloud-scan/audit
```

Avec un Docker **rootless**, l’uid 10001 du conteneur est un uid subordonné sur
l’hôte : exécutez donc le `chown` dans un conteneur - en tant que root de l’espace
de noms utilisateur, c’est-à-dire vous, et sans sudo :

```bash
docker run --rm --user 0 --entrypoint chown \
  -v /srv/opencloud-scan/audit:/target valkey/valkey:9.1-alpine 10001 /target
```

Séparez-le d’un répertoire de données Redis : Redis écrit avec l’uid 999, et un
répertoire ne peut appartenir qu’à l’un des deux.

#### Confier la rotation au logrotate de l’hôte {#letting-the-hosts-logrotate-keep-it}

Un fichier sur le système de fichiers de l’hôte est une chose dont l’hôte sait
déjà s’occuper, et un parc doté d’une politique de conservation préfère
l’exprimer au même endroit que pour tous les autres journaux.
`COS_WEB_AUDIT_LOG_ROTATION=external` transfère cette tâche : le service cesse de
renouveler le fichier selon sa taille et remarque plutôt que le fichier qu’il
tient a été déplacé, puis rouvre le fichier de remplacement.

C’est la moitié qui se trouve dans ce processus. L’autre moitié est une politique
que l’hôte installe — `docker/setup-wizard.py` en écrit une à côté du fichier
compose lorsque vous la choisissez, et elle ressemble à ceci :

```
/srv/opencloud-scan/audit/audit.log {
    daily
    rotate 30
    dateext
    missingok
    notifempty
    compress
    delaycompress
    create 0600 10001 10001
}
```

```bash
sudo install -m 0644 -o root -g root opencloud-scan-audit.logrotate \
    /etc/logrotate.d/opencloud-scan-audit
sudo logrotate --debug /etc/logrotate.d/opencloud-scan-audit   # changes nothing
```

Deux lignes de cette politique sont essentielles :

- **`create 0600 10001 10001`.** logrotate renomme le fichier et crée lui-même le
  remplaçant : celui-ci doit donc être accessible en écriture à l’utilisateur non
  privilégié du conteneur et lisible par personne d’autre.
- **Pas de `copytruncate`.** Tronquer le fichier sous un processus qui écrit
  encore perd tout ce qui a été écrit entre la copie et la troncature. Rouvrir le
  fichier lorsque son inode change ne perd rien, et c’est un fichier dont toute la
  raison d’être est d’être complet.

**Une seule chose doit renouveler le fichier.** Laisser
`COS_WEB_AUDIT_LOG_ROTATION` sur `service` tout en installant une politique en
donne deux, ce qui fait perdre des enregistrements à une piste ; le définir sur
`external` sans rien installer n’en donne aucune, et le fichier grossit jusqu’à
remplir le disque. Une valeur inconnue empêche le démarrage plutôt que de deviner
ce que vous vouliez.

Les corps de requête sont limités à **1 Mio** et **30 secondes** avant l’analyse
du formulaire, du JSON ou de MCP. Les corps trop volumineux renvoient 413 ; les
corps incomplets expirent avec 408. Ces limites fixes côté service ne modifient ni
la file d’analyse ni son comportement en cas de surcharge. Appliquez aussi des
limites de connexions et de bande passante au niveau du reverse proxy.

Chaque analyse en cours utilise un processus enfant. Un dépassement de délai ou
une annulation de tâche arrête et récupère ce processus et ses threads de sondes
avant que le worker prenne une autre tâche. Le worker doit donc avoir le droit de
créer des processus ; prévoyez un processus Python supplémentaire par analyse
active lors du dimensionnement de la mémoire et des limites de PID. Voir
[l’ADR 0053](../../adr/0053-a-scan-timeout-ends-its-process.md).

## Placer le service derrière un reverse proxy {#putting-it-behind-a-reverse-proxy}

Des configurations complètes pour nginx, Apache httpd, Caddy, Traefik et HAProxy -
y compris le flux continu dont a besoin le point de terminaison MCP et les chemins
qu’un proxy ne doit pas réécrire - se trouvent dans
[Reverse proxies](reverse-proxy.md).

[`docker/setup-wizard.py`](../../docker/setup-wizard.py) écrit ce fichier pour vous
pour les quatre premiers : répondez à sa question sur le reverse proxy et la
configuration est placée à côté du fichier compose généré, avec TLS, le flux
`/mcp` sans mise en tampon, un `X-Forwarded-For` qu’un client ne peut pas choisir
et - lorsque cette pile fournit l’outpost - l’authentification déléguée devant
`/admin`. Voir [les notes de l’assistant](../../docker/README.md#the-reverse-proxy).

En résumé :

Terminez TLS devant le service, transmettez `X-Forwarded-For`, et seulement alors
définissez `COS_WEB_TRUST_FORWARDED_FOR=true`.

L’en-tête est lu **par la droite**, à `COS_WEB_TRUSTED_PROXY_HOPS` entrées (`1` par
défaut, soit un reverse proxy). Cette extrémité est la seule partie qu’un proxy
écrit : `proxy_add_x_forwarded_for` de nginx, Traefik et la plupart des réseaux de
diffusion de contenu *ajoutent* une entrée, si bien que tout ce qui se trouve à
gauche de la dernière entrée est ce que le client a envoyé. Un CDN devant un
ingress représente deux sauts et nécessite `COS_WEB_TRUSTED_PROXY_HOPS=2`.

En compter trop peu est sans danger : l’adresse enregistrée est alors celle d’un
proxy plutôt que celle du visiteur. Ce qu’il faut éviter, c’est d’en compter plus
qu’il n’y en a réellement : la lecture remonte alors dans la partie de l’en-tête
contrôlée par le client, ce qui est exactement la falsification que ce paramètre
doit empêcher. En cas de doute, comptez les proxies que vous exploitez, et aucun
autre.

Une entrée qui n’est pas une adresse IP est ignorée plutôt que comptée, pour qu’un
identifiant masqué ne puisse pas devenir le compteur de limitation de quelqu’un.

L’application envoie ses propres en-têtes de sécurité, dont
`Content-Security-Policy: default-src 'self'` sans aucun `unsafe-inline`. Tout ce
que chargent les pages - CSS, JavaScript, icônes, polices - est servi depuis
`/static` : il n’y a rien à assouplir. Si votre proxy ajoute sa propre politique,
assurez-vous qu’elle n’affaiblit pas celle-ci.

## L’API HTTP {#the-http-api}

### `POST /api/scans` {#post-apiscans}

```bash
curl -sS -X POST http://127.0.0.1:8811/api/scans \
  -H 'Content-Type: application/json' \
  -d '{"target_url": "https://opencloud.example.com",
       "ignore_hardenings": ["cspWithoutUnsafeInline"]}'
```

```json
{"uuid": "0f4a1f22-...", "state": "queued", "url": "/scan/0f4a1f22-..."}
```

`target_url` peut être un simple nom d’hôte ; `https://` est supposé lorsqu’aucun
schéma n’est indiqué.

**202** en cas de succès, **400** pour une cible qui ne peut pas être analysée,
**403** pour une instance qu’un déploiement en mode d’approbation n’a pas
approuvée, **422** pour un champ que le service n’accepte pas, **429** lorsqu’une
limite de débit ou le blocage des sondes s’applique.

Le formulaire du navigateur envoie vers `/` plutôt qu’ici, et reçoit **303** vers
`/scan/{uuid}`. Les deux chemins utilisent le même gestionnaire : une soumission
refusée est réaffichée là où elle a été envoyée, et `/` est une URL qui survit à un
rechargement. `Accept: text/html` sélectionne le comportement HTML sur l’un ou
l’autre chemin.

### `GET /api/scans/{uuid}` {#get-apiscansuuid}

```json
{
  "uuid": "0f4a1f22-...",
  "state": "queued",
  "target": "https://opencloud.example.com",
  "expiresIn": 3574,
  "queue": {"position": 2, "length": 7}
}
```

Une fois l’analyse terminée, le même point de terminaison contient `result` - le
document du scanner, inchangé - et `summary`, les mêmes données regroupées pour le
tableau de bord. **404** lorsque l’uuid est inconnu ou expiré.

### `POST /api/scans/batch` {#post-apiscansbatch}

Pour un appelant qui a tout un parc à vérifier plutôt qu’une seule instance :

```bash
curl -sS -X POST http://127.0.0.1:8811/api/scans/batch \
  -H 'Content-Type: application/json' \
  -d '{"targets": ["https://one.example.com", "https://two.example.com"]}'
```

```json
{
  "accepted": [
    {"uuid": "0f4a1f22-...", "target": "https://one.example.com",
     "state": "queued", "url": "/scan/0f4a1f22-..."}
  ],
  "rejected": [
    {"target": "https://two.example.com", "status": 429,
     "detail": "That instance was scanned very recently...", "retryAfter": 284}
  ],
  "counts": {"submitted": 2, "accepted": 1, "rejected": 1}
}
```

Chaque cible d’un lot passe par la même validation, la même limite par client et
le même délai de carence par cible qu’une soumission unique, dans l’ordre de la
saisie. Dix cibles consomment dix analyses du quota. La réponse sépare les cibles
acceptées et refusées, car certaines peuvent être mises en file d’attente tandis
que d’autres sont refusées.

Les mêmes quatre champs sont acceptés, avec `targets` à la place de `target_url`,
et tout autre champ donne une réponse **422** qui le nomme.
`COS_WEB_MAX_BATCH_TARGETS` plafonne la liste ; une liste plus longue est refusée
en bloc, avant toute mise en file d’attente, pour qu’aucune cible ne subisse un
délai de carence pour un lot qui ne s’est jamais exécuté.

**202** lorsqu’au moins une cible a démarré. Lorsqu’aucune n’a démarré, le statut
est la raison du refus de la première cible - **429** avec `Retry-After` et
l’indication d’auto-hébergement s’il s’agit d’une limite, **400** ou **422**
sinon.

### `GET /api/scans/{uuid}/export/{format}` {#get-apiscansuuidexportformat}

Une analyse terminée peut être téléchargée au format `json`, `csv`, `sarif`,
`pdf` ou `html`. Les kits `remediation-md` et `remediation-html` contiennent
uniquement les constats encore ouverts pouvant être corrigés et les extraits
de configuration proposés pour nginx, Caddy, Traefik, Compose et `.env`.
Utilisez un rapport complet pour consulter la note, les contrôles réussis
et les avis de sécurité.

```bash
curl -sS -OJ http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
```

Le rapport `html` est **un fichier autonome unique** dont les styles sont
inclus. Son ouverture ne déclenche aucune requête réseau : il ne contient
ni scripts, ni images, ni polices ou feuilles de style externes. Les liens
de documentation s’ouvrent uniquement si vous les suivez. Le rapport comprend
les constats, les constats exemptés et leurs motifs, le plan de correction,
les lacunes de couverture et les données de référence utilisées pour évaluer
l’analyse. Il ne contient ni formulaires, ni commandes de nouvelle analyse,
ni interrogation périodique, ni jeton d’effacement.

Les rapports complets comprennent le plan de correction : lignes de résumé
et d’étapes dans le CSV, `runs[0].properties.remediation` dans le SARIF,
section du plan dans les formats PDF et HTML, et `remediationPlan` dans le
JSON. Les détails de transport figurent dans le bloc d’en-tête du CSV,
`runs[0].properties.tls` dans le SARIF, les sections de transport des formats
PDF et HTML, et `tls` dans le JSON. Ils couvrent le protocole, le chiffrement,
la validité du certificat et les jours restants, la complétude de la chaîne
et l’agrafage OCSP. La valeur `null` signifie que la mesure n’a pas pu être
établie, et non que le contrôle a réussi.

Les téléchargements sont générés à la demande à partir du résultat enregistré.
Leurs liens cessent de fonctionner à l’expiration de l’analyse. Les fichiers
déjà enregistrés restent disponibles, ne se mettent pas à jour et ne sont pas
supprimés lors de l’effacement de l’analyse. La réponse de
`GET /api/scans/{uuid}` pour une analyse terminée indique les URL de
téléchargement sous `exports` ; la page de résultat propose les mêmes formats
sous forme de boutons de téléchargement.

#### Exports signés {#signed-exports}

Lorsque `COS_WEB_EXPORT_SIGNING_KEY` est défini, chaque réponse d’export porte une
signature de ses octets exacts :

```text
X-COS-Signature: HMAC-SHA256=d68d9da7f04a4dcf38de5c64545141dc02c50c7476e76687e74c015383f34258
```

C’est un HMAC-SHA256 calculé sur le corps tel qu’envoyé, avec le texte de la clé
encodé en UTF-8. PDF et CSV sont couverts de la même façon que JSON et SARIF. Cela
permet à une tâche CI ou à une archive de montrer plus tard qu’un fichier est bien
celui produit par ce service, et que personne ne l’a modifié depuis.

**C’est un secret partagé, pas une signature publique.** La vérification exige la
même clé : seule une personne qui la détient peut vérifier un fichier - l’opérateur,
ou un pipeline qui reçoit la clé par son coffre de secrets. Un visiteur ne peut pas
vérifier seul un téléchargement, et il ne faut jamais lui envoyer la clé pour qu’il
le fasse. Traitez-la comme un mot de passe, et générez-en une longue et aléatoire :

```bash
openssl rand -hex 32
```

Enregistrez l’en-tête avec le fichier, car la signature n’est pas intégrée au
fichier lui-même :

```bash
curl -sS -D headers.txt -o result.pdf \
  http://127.0.0.1:8811/api/scans/0f4a1f22-.../export/pdf
grep -i '^x-cos-signature' headers.txt
```

Vérifiez les **octets téléchargés**, jamais une copie analysée ou resérialisée.
Reformater le JSON modifie les octets et invalide la signature. Depuis une copie de
ce dépôt :

```bash
COS_WEB_EXPORT_SIGNING_KEY='<key-from-secret-store>' \
  uv run python scripts/verify_export.py result.pdf 'HMAC-SHA256=<hex-from-header>'
```

Le script affiche `signature verified` et se termine avec `0`, ou affiche
`signature verification failed` et se termine avec `1`. `--key-env NAME` lit la clé
dans une autre variable d’environnement. Sans copie du dépôt, `openssl` calcule le
même condensat, à comparer avec la valeur hexadécimale qui suit `HMAC-SHA256=` :

```bash
openssl dgst -sha256 -hmac "$COS_WEB_EXPORT_SIGNING_KEY" -r result.pdf
```

Changer la clé invalide toutes les signatures faites avec l’ancienne, car il n’y a
pas de gestion de versions des clés comme pour `COS_WEB_ENCRYPTION_KEY_<n>`.
Conservez l’ancienne clé partout où d’anciens fichiers peuvent encore devoir être
vérifiés. Sans la variable, les exports sont envoyés sans signature et sans
en-tête.

**200** avec un `Content-Disposition` qui nomme l’uuid, **409** tant que l’analyse
n’est pas terminée - elle existe, donc une réponse 404 lancerait l’appelant dans
une boucle de nouvelles tentatives sur le mauvais point de terminaison - et **404**
pour un uuid ou un format inconnus.

### `GET /api/scans/{uuid}/badge.svg` {#get-apiscansuuidbadgesvg}

La note sous forme de badge SVG, à intégrer dans une page pour afficher
le résultat sans ouvrir le rapport.

```bash
curl -sS http://127.0.0.1:8811/api/scans/0f4a1f22-.../badge.svg
```

```markdown
![OpenCloud security](https://scan.example.com/api/scans/0f4a1f22-.../badge.svg)
```

Il est écrit par `webapp/badge.py`, comme le PDF est écrit par `reports.py` -
sans service de badges, sans police externe, sans script. Une balise `<img>`
pointant vers le serveur de quelqu’un d’autre lui transmettrait l’URL du résultat
dans un referer à chaque affichage, et l’uuid de cette URL est l’unique
autorisation d’accès au résultat complet.

Le badge porte la lettre et rien de ce qu’a choisi l’instance analysée : ni nom
d’hôte, ni chaîne de produit, ni version. La couleur est celle que le tableau de
bord utilise pour cette note : un badge et la page vers laquelle il renvoie ne
peuvent donc pas se contredire.

**Il dure exactement aussi longtemps que l’analyse.** Avec la valeur par défaut
d’une heure de `COS_WEB_RESULT_TTL`, une image intégrée quelque part de façon
permanente cesse de s’afficher dans l’heure et répond **404** comme tout autre
uuid expiré. Il convient donc à un ticket, à un message de chat ou à un tableau de
bord d’état tant qu’un résultat est actuel, mais pas à un README - sauf si le
déploiement qui le sert conserve les résultats bien plus longtemps, une décision
qui a ses propres conséquences pour toutes les personnes dont il stocke les
analyses. Il n’existe volontairement aucun point de terminaison qui produit un
badge pour un *nom d’hôte* : ce serait une poignée permanente et devinable sur
l’instance de quelqu’un, et ce service n’en a aucune.

**200** avec `image/svg+xml` et `Cache-Control: no-store`, **409** tant que
l’analyse n’est pas terminée, **404** pour un uuid inconnu ou expiré. `no-store`
est la valeur par défaut de tout le service, à laquelle il ne déroge jamais ici :
chaque route mise en cache publiquement publie des métadonnées sur *ce service*
([ADR 0031](../../adr/0031-a-response-is-uncacheable-until-a-route-opts-in.md)),
alors qu’un badge est une affirmation sur l’instance de quelqu’un.

### `DELETE /api/purge` {#delete-apipurge}

L’effacement sur demande - le versant opérateur d’une demande au titre de
l’article 17 du RGPD - avec un reçu à classer ensuite dans le dossier.

```bash
curl -sS -X DELETE \
  -H "Authorization: Bearer $COS_WEB_PURGE_TOKEN" \
  "http://127.0.0.1:8811/api/purge?target=opencloud.example.com"
```

```json
{
  "receiptId": "8f14e45f-...",
  "issuedAt": "2025-01-30T11:04:07+00:00",
  "target": "opencloud.example.com",
  "targetFingerprint": "6c1f...",
  "deleted": {"scans": 2, "keys": 5, "queueEntries": 1, "rateLimitKeys": 1},
  "remaining": 0,
  "complete": true,
  "statement": "All scan records held for this target were deleted ...",
  "notes": ["..."],
  "signature": {"algorithm": "HMAC-SHA256", "value": "b91c..."}
}
```

Il supprime chaque espace de noms `scan:{uuid}:*` dont les propres métadonnées
nomment ce nom d’hôte, les entrées de la cible dans la file d’attente, et la clé
de délai de carence qui en est dérivée. `target` accepte un simple nom d’hôte ou
une URL complète, sans tenir compte de la casse, avec ou sans port.

`targetFingerprint` n’est présent que si `COS_WEB_PURGE_SIGNING_KEY` est défini,
et vaut `null` sinon : un hachage sans clé d’un nom d’hôte n’est pas un pseudonyme,
car l’espace des noms d’hôte est assez petit pour être énuméré.

Le reçu enregistre ce que la suppression a trouvé et retiré. `deleted` compte les
clés supprimées ; `remaining` provient d’une seconde inspection effectuée
ensuite, et `complete` signifie `remaining == 0`. `notes` identifie les données
hors de portée de l’opération, notamment les rapports téléchargés et toute piste
d’audit conservée. Vérifiez un reçu signé avec :

```python
from webapp.purge import verify
verify(receipt, key)      # the value of COS_WEB_PURGE_SIGNING_KEY
```

**Il exige une autorisation et reste désactivé tant qu’il n’est pas configuré.**
C’est le seul appel qui parcourt l’espace des clés et le seul qui détruit des
résultats appartenant à ceux qui les consultent : une version sans
authentification serait un outil de déni de service au nom sympathique. Une
personne concernée écrit à l’opérateur ; l’opérateur - le responsable du
traitement - exécute l’effacement et lui transmet le reçu. **200** avec le reçu,
**401** pour un mauvais secret, **422** pour une cible qui n’est pas un nom
d’hôte, et **404** chaque fois que `COS_WEB_PURGE_TOKEN` n’est pas défini.

Si aucune donnée correspondante n’est trouvée, le point de terminaison renvoie
200 avec des décomptes nuls. Le reçu décrit le stockage au moment de cette
inspection.

### `GET /llms.txt`, `GET /openapi.json`, `GET /arazzo.json`, `GET /.well-known/ai.json` {#get-llmstxt-get-openapijson-get-arazzojson-get-well-knownaijson}

Ces documents de découverte et de contrat sont toujours publics.
`COS_WEB_ENABLE_DOCS` ne contrôle que les vues interactives `/docs` et `/redoc`.

Le document [OpenAPI](https://spec.openapis.org/oas/latest.html) indique ce que
chaque point de terminaison accepte et renvoie, jusqu’à la forme de chaque
réponse ; le document [Arazzo](https://spec.openapis.org/arazzo/latest.html) qui
l’accompagne indique comment ces opérations s’utilisent ensemble - soumettre puis
interroger jusqu’à `done`, parcourir les uuid acceptés d’un lot, attendre la fin
d’une réponse 409 avant de télécharger un fichier, et effacer une instance contre
un reçu. Les deux sont construits à partir de la même application, et un test
échoue si un workflow décrit une opération qui n’existe plus.

`/.well-known/ai.json` est le point d’entrée : nom, description, les deux URL de
spécification, le point de terminaison MCP, les limites d’utilisation qu’un agent
doit respecter et le lien d’auto-hébergement. C’est une **convention au niveau de
l’application**, pas une norme enregistrée : elle existe pour qu’un agent qui ne
connaît que l’origine puisse trouver le reste en une seule requête.

`/llms.txt` est la carte Markdown plus courte. Elle liste les contrats publics,
les principales opérations, les outils WebMCP et les règles concernant les
analyses asynchrones et les UUID. Elle ne contient aucune donnée d’analyse ni
aucun mécanisme de liste.

### `POST /mcp` {#post-mcp}

Le point de terminaison [Model Context Protocol](https://modelcontextprotocol.io),
en streamable HTTP, sans état, avec des réponses JSON. C’est la couche
d’exécution destinée aux agents, pas une seconde implémentation : chaque outil
appelle dans le même processus l’API HTTP de cette application, si bien qu’un
agent rencontre exactement les mêmes limites de débit, la même protection SSRF et
la même autorisation d’effacement qu’un navigateur.

Sept outils, un par tâche utilisateur plutôt qu’un par point de terminaison :
`scan_instance`, `scan_instances`, `get_scan_result`, `plan_remediation`,
`compare_scans`, `export_scan` et `erase_instance_data`. Sept prompts nomment les
tâches réellement demandées - `audit_instance`, `audit_estate`,
`explain_scan_result`, `triage_findings`, `review_transport_security`,
`check_release_support` et `verify_remediation` -, pour qu’un client puisse
proposer « auditer cette instance et rédiger un plan de correction » comme un seul
choix. Cinq ressources sont publiées sous des URI `spec://` : les documents
OpenAPI, Arazzo et de découverte, et deux qui constituent une base de
connaissances plutôt qu’un contrat - `catalogue`, chaque indicateur de
durcissement et contrôle supplémentaire du scanner expliqué, avec le paramètre
OpenCloud associé, la correction et la documentation officielle ; et
`advisories`, toute la base des avis de sécurité par rapport à laquelle une
analyse est notée. Les deux sont construites à partir des mêmes fonctions que la
page `/catalogue` : un agent peut donc expliquer un constat, ou voir ce que le
scanner détecterait, sans jamais soumettre de cible - et sans qu’une ressource
contredise jamais la page sur la signification d’un contrôle. La sémantique
d’interrogation, de nouvelles tentatives et d’erreurs provient de
`webapp/workflows.py`, à partir duquel le document Arazzo est aussi généré : les
deux ne peuvent donc pas diverger.

`erase_instance_data` est marqué comme destructif et exige le même identifiant
`Authorization: Bearer` que le point de terminaison HTTP. L’identifiant est lu
dans les en-têtes de la requête de l’agent, jamais dans un argument d’outil : ce
n’est donc jamais une valeur que le modèle a vue. Lorsque le point de terminaison
exige lui-même une connexion, il passe dans `X-Purge-Authorization`, car
`Authorization` porte alors le jeton d’identité de l’agent, et lire l’un comme
l’autre serait une confusion qu’il faut refuser.

**Le point de terminaison est ouvert, sauf décision contraire de l’opérateur.**
Définissez `COS_WEB_MCP_AUTH_ENABLED` et un émetteur : il devient un serveur de
ressources OAuth 2.0. Un jeton est vérifié hors ligne à l’aide des clés publiées
par le fournisseur - signature, émetteur, audience, expiration, portées - et une
requête sans jeton reçoit une réponse 401 dont l’en-tête `WWW-Authenticate` désigne
`/.well-known/oauth-protected-resource/mcp`, le document public RFC 9728 qui
indique quel fournisseur interroger. `/.well-known/ai.json` indique la même chose
avant la première requête, sous `mcp.authentication`.

Ce service n’émet rien, ne stocke rien et ne gère aucun compte : il vérifie un
jeton signé par quelqu’un d’autre. Et cela n’apporte rien d’autre à un agent - la
limite par client, le délai de carence par cible, la protection SSRF et la file
d’attente sont identiques après connexion. Une erreur de configuration qui
laisserait le point de terminaison ouvert alors que l’opérateur le croit protégé
empêche le démarrage. [Authentik devant le point de terminaison MCP](authentik.md)
décrit une configuration complète.

La configuration d’un client - Claude Code, Claude Desktop, GitHub Copilot dans VS
Code et en CLI, Cursor, Zed, Windsurf - est décrite dans [Intégration MCP](mcp.md),
qui explique aussi comment désactiver le point de terminaison.

### `GET /scan/{uuid}`, `GET /`, `GET /healthz` {#get-scanuuid-get-get-healthz}

La page de résultat, la page d’accueil, et une sonde de santé fondée sur Redis qui
ne dit rien d’aucune analyse.

Une page de résultat terminée propose aussi d’**analyser de nouveau** - la même
cible dans les mêmes conditions, avec l’attente décomptée à côté (voir
[Limitation du débit](#rate-limiting)) - et affiche les constats qu’elle vient de
lister **sous forme de configuration** : un fragment Compose, `.env`, nginx, Caddy
ou Traefik construit par `opencloud_local_scan.snippets` à partir des paires
`env_fix` et `header_fix` du catalogue, la variante choisie étant mémorisée dans le
navigateur. Les cinq sont rendus côté serveur et un script les réunit dans un
sélecteur : un lecteur sans JavaScript obtient donc tous les fragments, plutôt
qu’un seul bloc visible et quatre boutons inertes. Rien n’est généré dans le
navigateur : les fragments proviennent du module couvert par les tests de la
bibliothèque, et une seconde implémentation en JavaScript est la seule chose qui
ne doit pas exister sur cette page. Les explications que contenait autrefois la
page d’accueil se trouvent sur leurs propres pages - `GET /how-it-works`,
`GET /grades`, `GET /documentation`, `GET /search`, `GET /api`, `GET /privacy` et
`GET /about` -, qui sont uniquement HTML et restent hors du schéma OpenAPI. Il en
va de même pour `GET /compare`, pour une seconde raison : cette page affiche deux
résultats et n’est donc jamais indexable, exactement comme `/scan/{uuid}`.
`/grades` explique la véritable correspondance 0-5 du plugin et ses plafonds de
correction ; `/documentation` est la référence rapide de la CLI locale et l’index
des guides, et c’est aussi la page qui oriente hors de ce service : les commandes
Docker en une ligne qui exécutent la même analyse sur la machine du visiteur se
trouvent juste sous son démarrage rapide, documentées en détail dans
[Analyser en une ligne de commande](docker.md). Elles avaient autrefois leur
propre onglet `/cli` ; ce chemin est désormais une redirection permanente vers
`/documentation#oneliner`. `GET /healthz` ne renvoie 200 qu’après que le backend
configuré a répondu à `PING`, que la profondeur de sa file a pu être lue et qu’un
signal de vie de courte durée d’un worker est présent. Son corps de réussite ne
contient que le total `queueDepth` et `worker: "ok"` ; il renvoie une réponse 503
sans détail tant qu’une dépendance est indisponible.

Chaque page `/documentation/{slug}` sous l’index est générée lors de la
construction à partir des guides d’exploitation en Markdown. Le HTML versionné est
vérifié en CI et livré dans `frontend/` ; le service en fonctionnement n’analyse
pas de Markdown et n’a pas besoin des fichiers sources. L’ADR 0018 consigne cette
frontière.

`/search` filtre dans le navigateur un index JSON versionné, servi par la même
origine. Son manifeste nomme explicitement les modèles publics et ne peut voir ni
Redis, ni l’API, ni les pages de résultats, ni les exports, ni les UUID, ni les
adresses soumises. Chaque pull request vers `main` reconstruit ce fichier et le
valide dans la branche, et le workflow de publication le reconstruit de nouveau
avant de construire les artefacts : une version déployée a donc un seul index de
recherche immuable. L’ADR 0019 consigne cette frontière et l’ADR 0050 le moment de
sa reconstruction.

Lorsque `COS_WEB_ENABLE_MCP` est activé, la page d’accueil et les pages de
résultat exposent aussi leurs actions existantes aux navigateurs compatibles via
le [brouillon WebMCP](https://webmachinelearning.github.io/webmcp/). La page
d’accueil enregistre `scan_opencloud_security` ; une page de résultat enregistre
`get_scan_result` et `export_scan_report` pour l’UUID affiché. Leurs schémas sont
rendus à partir des mêmes catalogues que les commandes de la page. L’exécution
utilise l’API publique avec `Accept: application/json` : WebMCP ne contourne donc
ni la protection SSRF, ni les limites de débit, ni le délai de carence, ni la file
d’attente, ni les vérifications de capacité.

Un outil de navigateur répond à un échec au lieu de lever une exception :
`ok: false` avec `status`, `error` et `retryable`, plus `retryAfter` en secondes
lorsque le service en a envoyé un. C’est le contrat qu’utilisaient déjà les outils
`/mcp`, et les statuts correspondants sont rendus dans la page à partir de
`webapp/workflows.py` au lieu d’être écrits dans le script. Voir
[l’ADR 0041](../../adr/0041-a-browser-tool-answers-a-failure-rather-than-throwing.md).

`POST /` et `GET /scan/{uuid}` négocient le JSON pour les outils côté navigateur
et les autres clients. `Accept: application/json` demande une réponse structurée,
tout comme `output_format=json`. Le HTML reste la valeur par défaut pour la
navigation ordinaire.

Le paramètre facultatif `COS_WEB_INDEX_META_TAG=name=content;name=content` ajoute
jusqu’à dix éléments `<meta name="..." content="...">` à la page d’accueil. Docker
Compose le transmet depuis l’environnement du déploiement. L’application analyse
et échappe chaque paire au lieu d’accepter du HTML brut, et refuse les noms en
double, les noms déjà utilisés par la page et les métadonnées de plateformes
interdites. Un point-virgule littéral n’est pas pris en charge dans une valeur.

### `GET /advisories.atom`, `GET /release-schedule.atom` {#get-advisoriesatom-get-release-scheduleatom}

Les deux documents qui s’actualisent chaque jour, sous forme de flux Atom 1.0.

```bash
curl -sS http://127.0.0.1:8811/advisories.atom
```

`/advisories.atom` est la base des avis de sécurité par rapport à laquelle une
analyse est notée - une entrée par avis, avec sa gravité, les plages de versions
concernées sous la forme semi-ouverte utilisée par le scanner, et un lien vers
l’avis publié. `/release-schedule.atom` contient une entrée par ligne de version
OpenCloud, datée de sa publication, indiquant les canaux sur lesquels elle a été
publiée et la date à laquelle elle cesse de recevoir des correctifs.

Les deux sont construits à partir des mêmes fonctions que les pages : un flux ne
peut donc pas décrire un avis autrement que `/catalogue`. Ils expliquent pourquoi
une analyse effectuée aujourd’hui peut noter une instance plus sévèrement que la
même analyse le mois dernier, ce qui mérite d’être signalé : un abonné apprend que
la base a changé sans avoir à relancer une analyse pour le découvrir.

Les titres et descriptions des avis proviennent d’un flux public que ce projet ne
contrôle pas. Ils sont transmis échappés en `type="text"`, jamais comme balisage :
un lecteur ne peut donc pas être amené à afficher le HTML de quelqu’un d’autre.

Ce sont les seules routes de données de référence qui acceptent un cache public
(`max-age=3600`). Elles ne nomment aucune instance, ne portent aucun uuid et ne
prennent aucun paramètre - le critère que fixe
[l’ADR 0031](../../adr/0031-a-response-is-uncacheable-until-a-route-opts-in.md)
pour pouvoir être mis en cache - et elles ne doivent jamais en accepter : un flux
filtré par nom d’hôte serait une question sur l’instance de quelqu’un. Les
identifiants d’entrée sont des URN de l’avis ou de la ligne de version plutôt que
des URL de ce déploiement : l’historique d’un lecteur survit donc à un changement
d’hôte du service.

### `GET /robots.txt`, `GET /agents.txt`, `GET /sitemap.xml` {#get-robotstxt-get-agentstxt-get-sitemapxml}

Les trois sont générés, jamais des fichiers sur disque. Le sitemap liste la page
d’accueil, les neuf pages d’explication et d’index et chaque document CLI généré,
et tire chaque `lastmod` du modèle qui le rend : il ne peut donc pas s’écarter des
pages qui existent réellement. Aucun ne mentionne jamais un résultat : l’uuid est
l’unique autorisation, et une liste est précisément ce que ce service n’a pas.
`robots.txt` interdit `/scan/`, `/api/`, le schéma et la sonde de santé, et
renvoie au sitemap.

`agents.txt` suit plutôt la convention [agents-txt.com](https://agents-txt.com) :
des blocs de capacités formés de directives `Key: value` plutôt que la liste
d’autorisations de `robots.txt`, si bien qu’un analyseur conçu pour cette
convention lit directement les outils de ce déploiement. Il déclare
`MCP: <url>` et `WebMCP: <url>` lorsque ce déploiement les sert,
`Authorization: oauth2` et `Identity: required` uniquement lorsque le point de
terminaison MCP exige lui-même un jeton porteur, et rien pour
`Protocols`/`Payments`/`A2A`/`Skills`/`UCP`, car rien de cela ne s’applique ici.
Comme `/.well-known/ai.json`, c’est une convention informelle plutôt qu’une norme
enregistrée, et les contrats OpenAPI, Arazzo et MCP font foi sur tout ce qu’il
affirme.

`GET /agents.json` est le document structuré que la convention recommande à côté
du fichier texte - le même document que sert `/.well-known/ai.json`, publié de
nouveau sous le nom auquel renvoie `agents.txt`.

`COS_WEB_PUBLIC_BASE_URL` détermine l’origine dans les trois, ainsi que le lien
canonique de chaque page. Derrière un proxy, le service ne voit que sa propre
adresse interne, et sans ce paramètre il publierait des URL que personne à
l’extérieur ne peut atteindre.

`COS_WEB_ALLOW_INDEXING=false` désactive l’ensemble : `robots.txt` devient un
refus pur et simple, `agents.txt` devient le fichier minimal de la convention sans
aucune capacité déclarée, `sitemap.xml` répond 404 et chaque page porte `noindex`.
Une page de résultat porte `noindex` et un `X-Robots-Tag` dans tous les cas.

## Organisation du code {#layout}

```text
webapp/                 the service
├── app.py              routes, security headers, request validation
├── settings.py         every COS_WEB_* variable
├── ssrf.py             the target guard
├── ratelimit.py        the two limits
├── audit.py            the optional audit trail, pseudonymised
├── store.py            the per-scan Redis namespace
├── queue.py            handing a scan to the worker pool
├── tasks.py            the ARQ worker
├── runner.py           the seam where a request becomes ScannerSettings
├── redis_backend.py    Redis, and the in-process stand-in for tests
├── reports.py          the CSV, SARIF and PDF exports
├── arazzo.py           the API described as executable workflows
├── documentation.py    the manifest for the generated browser documentation
├── purge.py            erasure on request, and the signed receipt for it
├── seo.py              the public page list, robots.txt, agents.txt and sitemap.xml
└── catalog.py          the waiver allow-list and the dashboard grouping

frontend/
├── static/{css,js,img} vanilla CSS, small scripts, hand-drawn SVG
└── templates/          base, index, scan, 404, and the content pages

docker/
├── Dockerfile.web      the image both web_app and arq_worker run
├── docker-compose.yml            locally built frontend, worker and Redis
├── docker-compose.dockerhub.yml  published-image frontend, worker and Redis
├── Dockerfile                    the plugin image, unrelated to the web application
└── docker-compose.monitoring.yml the plugin's own stack, also unrelated
```

[`webapp/README.md`](../../webapp/README.md) couvre le même terrain vu de l’autre
côté : la surface de l’API, l’accès à Swagger, ce qu’une requête ne peut pas
demander et la façon d’exécuter votre propre frontend.

La frontière que respecte le reste du projet s’applique aussi ici :
`opencloud_local_scan` mesure, le plugin juge et `webapp` sert. Si une modification
amène la couche web à décider si un constat est acceptable, elle a sa place dans
le scanner ou dans le plugin.

## Marques et affiliation {#trademarks-and-affiliation}

Ce projet est un projet communautaire indépendant. Il n’est **pas** affilié à
OpenCloud GmbH, ni approuvé, parrainé ou soutenu par elle, et rien de ce qu’il
signale ne constitue une déclaration officielle concernant les logiciels
OpenCloud.

« OpenCloud », le logo OpenCloud ainsi que tous les noms et marques associés
appartiennent à leurs propriétaires respectifs. Ils ne figurent ici que pour
identifier le logiciel que vérifie cet outil, ce qui constitue un usage nominatif
et n’implique aucune relation. Tous les droits sur OpenCloud restent la propriété
d’OpenCloud GmbH.

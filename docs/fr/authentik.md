# Protéger MCP avec Authentik

Ce guide exécute le service d’analyse et Authentik dans une seule pile Compose, avec
l’authentification par jeton activée sur `/mcp` dès le démarrage. Utilisez-le lorsque MCP
ne doit être accessible qu’aux agents autorisés par votre fournisseur d’identité.

Le site web et l’API HTTP restent publics. L’authentification contrôle l’accès à MCP ;
elle n’augmente pas les quotas d’analyse et ne contourne ni le délai de carence par cible,
ni les contrôles SSRF, ni la file d’attente.

<!-- TOC -->
* [Authentik devant le point de terminaison MCP](#authentik-in-front-of-the-mcp-endpoint)
  * [Fonctionnement](#how-it-works)
  * [Lancer la pile](#running-the-stack)
  * [Envoyer des e-mails](#sending-mail)
  * [Ce que le blueprint a créé](#what-the-blueprint-created)
  * [Un second facteur pour tout le monde](#a-second-factor-for-everybody)
    * [Ce que voit la personne](#what-the-person-sees)
    * [Comment il est imposé](#how-it-is-enforced)
  * [Des comptes sans l’interface d’administration](#accounts-without-the-admin-interface)
  * [Un opérateur pour /admin](#an-operator-for-admin)
    * [Avec l’assistant](#with-the-wizard)
    * [À la main, dans l’interface Authentik](#by-hand-in-the-authentik-interface)
    * [Vérifier](#checking-it)
  * [Relier le scanner au fournisseur](#pointing-the-scanner-at-it)
  * [Autoriser une personne à utiliser le point de terminaison](#adding-somebody-who-may-use-the-endpoint)
    * [Un groupe, et l’association qui lui donne un sens](#a-group-and-the-binding-that-makes-it-mean-something)
    * [La personne](#the-person)
    * [L’agent avec un compte de service](#the-agent-that-is-nobody)
  * [Obtenir un jeton](#getting-a-token)
    * [En tant que compte de service](#as-a-service-account)
    * [Sans nommer de compte](#without-naming-an-account-at-all)
    * [En tant que personne](#as-a-person)
    * [Lire le jeton obtenu](#reading-the-token-you-got)
  * [Configurer un agent](#configuring-an-agent)
  * [L’effacement, qui est un autre identifiant](#erasure-which-is-a-different-credential)
  * [Derrière un reverse proxy](#behind-a-reverse-proxy)
  * [Sauvegarder](#backing-it-up)
  * [Restaurer](#restoring-it)
  * [Quand cela ne fonctionne pas](#when-it-does-not-work)
  * [Utiliser un autre fournisseur qu’Authentik](#using-a-provider-that-is-not-authentik)
<!-- TOC -->

## Fonctionnement {#how-it-works}

Le service d’analyse joue le rôle de serveur de ressources OAuth 2.0. Il vérifie les
jetons émis par le fournisseur et n’a ni page de connexion, ni sessions, ni base
d’utilisateurs, ni secret client :

1. Un agent présente `Authorization: Bearer <token>` dans ses requêtes MCP.
2. Le service récupère les clés de signature publiées par le fournisseur - le
   JWKS - et vérifie la signature du jeton avec elles.
3. Il vérifie l’émetteur, l’audience, l’expiration et les portées éventuellement
   exigées par le déploiement.
4. Tout ce qui échoue à l’une de ces vérifications n’est pas un jeton, et la
   requête reçoit une réponse **401** qui indique où en obtenir un vrai.

Rien n’est stocké, rien n’est journalisé, et aucune requête n’est envoyée au
fournisseur pour chaque jeton : les clés sont mises en cache et la vérification
se fait hors ligne. Une clé de signature renouvelée est prise en compte sans
redémarrage.

Un agent qui arrive sans jeton reçoit le traitement prévu par la RFC 9728 : une
réponse `401` dont l’en-tête `WWW-Authenticate` désigne
`/.well-known/oauth-protected-resource/mcp`, un document public qui nomme le
serveur d’autorisation. `/.well-known/ai.json` indique la même chose avant la
première requête : un agent bien conçu sait donc qu’il lui faut un jeton sans
dépenser un aller-retour pour le découvrir.

## Lancer la pile {#running-the-stack}

`docker/docker-compose.authentik.yml` n’est pas une surcouche de la pile
ordinaire ; c’est le déploiement complet en un seul fichier. Six services -
l’application web, le worker, Redis, Authentik, sa propre base PostgreSQL et le
worker d’Authentik - et une seule commande :

```bash
cd docker
./authentik-env.sh                                  # writes .env, once
docker compose -f docker-compose.authentik.yml up -d
```

Ouvrez ensuite **<http://127.0.0.1:9000/if/flow/initial-setup/>** - la barre
oblique finale est obligatoire, sans elle vous obtenez une erreur 404 - et
définissez le mot de passe du compte `akadmin`. Ce flux n’est proposé qu’une
fois.

La première connexion suivante demande à `akadmin` d’enregistrer un second
facteur - une application d’authentification ou une clé de sécurité - avant de
se terminer ; voir [un second facteur pour tout le monde](#a-second-factor-for-everybody).

Le blueprint crée le fournisseur et l’application. Dans ce fichier Compose,
`COS_WEB_MCP_AUTH_ENABLED` suit `${COS_WEB_ENABLE_MCP:-true}` : activer MCP
exige donc aussi l’authentification, et désactiver MCP désactive les deux.

`authentik-env.sh` écrit six secrets dans `docker/.env` et n’écrase jamais un
secret existant : l’exécuter deux fois est sans danger.

| Variable | Ce que c’est |
|:---------|:-----------|
| `COS_REDIS_PASSWORD` | Le mot de passe exigé par Redis. Redis contient chaque analyse en cours et chaque résultat encore dans sa durée de vie - voir [Redis](redis.md) |
| `AUTHENTIK_SECRET_KEY` | Signe tout le contenu de la base de données d’Authentik |
| `AUTHENTIK_PG_PASS` | Le mot de passe de la base PostgreSQL d’Authentik |
| `AUTHENTIK_CLIENT_ID` | L’ID client OAuth, et donc l’audience |
| `AUTHENTIK_CLIENT_SECRET` | Le secret client OAuth |
| `COS_WEB_PURGE_TOKEN` | L’identifiant d’opérateur pour l’effacement, qui est tout autre chose |

Sauvegardez `.env` avec les données d’Authentik. Conservez `AUTHENTIK_SECRET_KEY`
lors d’une restauration, pour que l’installation restaurée puisse utiliser son
état cryptographique existant.

Accessible depuis ailleurs que votre ordinateur portable ? Deux variables, et
rien d’autre ne change :

```bash
AUTHENTIK_URL=https://sso.example.com \
COS_WEB_PUBLIC_BASE_URL=https://scanner.example.com \
  docker compose -f docker-compose.authentik.yml up -d
```

C’est un fichier séparé plutôt qu’un profil Compose, car ces secrets sont
déclarés *obligatoires*, et Compose valide une variable obligatoire dans
**chaque fichier qu’il lit**, que le service qui l’utilise soit sélectionné ou
non. Sous forme de profil, il casserait `docker compose up` pour tous ceux qui
n’ont jamais voulu d’Authentik.

Remarques sur la pile, et sur ses différences avec celle d’origine :

- **Authentik n’a pas besoin de Redis.** Il conserve les sessions, le cache et
  sa file de tâches dans PostgreSQL depuis la version 2025.10. Le Redis du
  scanner est un cache sans persistance avec une politique d’éviction : ce
  serait le mauvais choix même si Authentik en avait besoin.
- **PostgreSQL est `postgres:18.6-alpine`**, fixé à cette version, et
  séparé de tout ce que vous exécutez par ailleurs. Authentik lui-même n’a
  **pas d’image Alpine** : `ghcr.io/goauthentik/server` n’est publié qu’en
  version basée sur Debian, sans variante possible.
- **Le worker ne reçoit pas le socket Docker.** La pile d’origine le monte pour
  que le worker puisse gérer les conteneurs d’avant-postes (outposts) ; cette
  pile n’exécute aucun outpost, et donner à un conteneur le socket du démon
  revient à lui donner l’hôte.
- **L’état se trouve dans des volumes nommés** - `authentik_database`,
  `authentik_media`, `authentik_templates`, `authentik_certs` - et non dans des
  montages liés sous `docker/`.
- **Ne montez pas `/etc/localtime` ni `/etc/timezone`** dans ces conteneurs.
  Authentik a besoin d’UTC en interne, et monter un fuseau horaire casse OAuth.

## Envoyer des e-mails {#sending-mail}

Configurez SMTP avant de compter sur la récupération de compte. Sans serveur de
messagerie externe, les messages de récupération sont livrés localement dans le
conteneur et n’atteignent pas les boîtes de réception des utilisateurs.

Chaque paramètre est une variable de `docker/.env`, et les deux services
Authentik les lisent : le serveur envoie le message de test, le worker envoie
tout le reste. Si vous n’en configurez qu’un, certains messages partent et d’autres
non.

| Variable | Valeur par défaut | Ce que c’est |
|:---------|:--------|:-----------|
| `AUTHENTIK_EMAIL_HOST` | *(vide)* | Le serveur de messagerie. Vide, la livraison locale reste en place |
| `AUTHENTIK_EMAIL_PORT` | `587` | `587` pour STARTTLS, `465` pour TLS implicite, `25` pour aucun des deux |
| `AUTHENTIK_EMAIL_USERNAME` | *(vide)* | Le compte utilisé pour s’authentifier, le cas échéant |
| `AUTHENTIK_EMAIL_PASSWORD` | *(vide)* | Le mot de passe de ce compte |
| `AUTHENTIK_EMAIL_USE_TLS` | `true` | STARTTLS sur une connexion en clair |
| `AUTHENTIK_EMAIL_USE_SSL` | `false` | TLS dès le premier octet |
| `AUTHENTIK_EMAIL_TIMEOUT` | `10` | Secondes avant d’abandonner |
| `AUTHENTIK_EMAIL_FROM` | `authentik@localhost` | L’adresse `From:` que voient les destinataires |

**`USE_TLS` et `USE_SSL` ne sont pas deux noms pour la même chose, et ne valent
jamais `true` tous les deux.** STARTTLS commence en clair sur le port 587 puis
passe en chiffré ; TLS implicite est chiffré dès le premier octet, sur le
port 465. Activer les deux donne une session qui ne négocie ni l’un ni l’autre.

```bash
cat >> docker/.env <<'EOF'
AUTHENTIK_EMAIL_HOST=smtp.example.com
AUTHENTIK_EMAIL_PORT=587
AUTHENTIK_EMAIL_USERNAME=authentik@example.com
AUTHENTIK_EMAIL_PASSWORD=the-password
AUTHENTIK_EMAIL_USE_TLS=true
AUTHENTIK_EMAIL_USE_SSL=false
AUTHENTIK_EMAIL_FROM=authentik@example.com
EOF
docker compose -f docker-compose.authentik.yml up -d
```

`authentik-env.sh` écrit ces noms en commentaire dans `docker/.env`, pour que la
liste soit sous vos yeux quand vous la cherchez, et ne décommente ni n’écrase
jamais ce que vous y avez mis. Vérifiez le résultat depuis **System → Settings →
Email** dans l’interface d’Authentik, qui envoie un message de test par le
conteneur serveur, et lisez le journal du worker pour le reste :

```bash
docker compose -f docker-compose.authentik.yml logs -f authentik_worker
```

`docker/setup-wizard.py` pose toutes ces questions lorsqu’il génère sa propre
pile, et lit le mot de passe dans la variable d’environnement
`AUTHENTIK_EMAIL_PASSWORD` plutôt que dans une option : un mot de passe sur une
ligne de commande est un mot de passe visible dans `ps` et dans l’historique du
shell.

## Ce que le blueprint a créé {#what-the-blueprint-created}

`authentik/blueprints/opencloud-scanner.yaml` est monté dans les deux conteneurs
Authentik sous `/blueprints/custom`, et le worker l’applique au démarrage. C’est
ce qui réduit la mise en place ci-dessus à une commande au lieu d’une page de
clics : le fournisseur OAuth2, sa clé de signature, ses portées et l’application
dont le slug devient l’émetteur existent tous avant votre première connexion.

Il ne provisionne **qu’une fois**. Chaque entrée est en `state: created` :
Authentik crée ce qui manque puis n’y touche plus. Modifiez ensuite une URI de
redirection, un flux ou une portée dans l’interface d’administration, et la
modification reste. Le blueprint ne rétablit pas l’ancienne valeur au démarrage
suivant.

Ce qu’il crée, sous **Applications → Applications** :

| | Valeur |
|:--|:-----|
| **Application** | `OpenCloud security scanner`, slug `opencloud-scanner` |
| **Fournisseur** | `check-opencloud-security`, OAuth2/OpenID Connect, confidentiel |
| **ID / secret client** | `AUTHENTIK_CLIENT_ID` et `AUTHENTIK_CLIENT_SECRET` depuis `.env` |
| **Types d’octroi** | `authorization_code`, `refresh_token`, `client_credentials` |
| **Clé de signature** | `authentik Self-signed Certificate` |
| **Portées** | `openid`, `profile`, `email`, `offline_access` |
| **Mode d’émetteur** | par fournisseur |

Deux de ces lignes méritent qu’on s’y attarde.

**La clé de signature est le paramètre le plus important de cette page.** Avec
elle, les jetons sont signés de façon asymétrique et vérifiés à l’aide du JWKS
publié. *Sans* elle, Authentik signe avec le secret client (HS256), et aucun
serveur de ressources ne peut vérifier un tel jeton sans recevoir ce secret - ce
que ce service refuse. Le blueprint la définit ; si vous recréez un jour le
fournisseur à la main, définissez-la aussi.

**L’ID client est l’audience.** Il se trouve dans `.env`, où l’application web
le lit sous le nom `COS_WEB_MCP_AUTH_AUDIENCE` : les deux côtés concordent parce
qu’ils lisent la même ligne, et il n’y a rien à recopier.

Le mode d’émetteur par fournisseur donne :

| | Valeur |
|:--|:-----|
| **Émetteur** | `https://sso.example.com/application/o/opencloud-scanner/` |
| **Document de découverte** | `https://sso.example.com/application/o/opencloud-scanner/.well-known/openid-configuration` |
| **JWKS** | `https://sso.example.com/application/o/opencloud-scanner/jwks/` |
| **Point de terminaison des jetons** | `https://sso.example.com/application/o/token/` |

Le point de terminaison des jetons n’est volontairement pas propre à chaque
application : Authentik l’aiguille selon le `client_id`. Les points de
terminaison de découverte et JWKS sont propres à chaque slug, et il n’existe pas
de document de découverte à la racine.

Lisez l’émetteur dans le document de découverte plutôt que de le saisir. C’est
ce que les jetons contiendront réellement, et c’est la valeur à laquelle le
scanner compare.

Un blueprint en échec n’empêche **pas** Authentik de démarrer : l’erreur est
enregistrée sur l’instance du blueprint. Si `/mcp` refuse tous les jetons sur
une pile toute neuve, regardez sous **Customisation → Blueprints** avant de
chercher ailleurs.

Pour le faire à la main - sur un Authentik que vous exploitez déjà, par
exemple -, l’assistant sous **Applications → Applications → Create with wizard**
demande les mêmes informations dans le même ordre, et le tableau ci-dessus donne
les réponses.

## Un second facteur pour tout le monde {#a-second-factor-for-everybody}

`authentik/blueprints/opencloud-mfa.yaml` est monté avec les autres et intègre
un second facteur à chaque connexion. Le flux d’authentification par défaut
d’Authentik contient déjà une étape qui le vérifie -
`default-authentication-mfa-validation` -, mais elle est livrée réglée pour
*ignorer* un compte qui n’en a pas, c’est-à-dire tous les comptes d’un annuaire
neuf. Le blueprint règle cette même étape sur *configurer* :

| | Valeur |
|:--|:-----|
| **Compte sans facteur** | Conduit à en enregistrer un avant la fin de la connexion |
| **Proposés** | TOTP (une application d’authentification) et WebAuthn (une clé de sécurité ou une passkey) |
| **Acceptés ensuite** | TOTP, WebAuthn, et les codes de récupération statiques créés depuis les paramètres de l’utilisateur |
| **Réappliqué** | Toutes les heures (`state: present`), pour qu’on ne puisse pas le désactiver dans l’interface puis l’oublier |

### Ce que voit la personne {#what-the-person-sees}

1. **La première connexion après le mot de passe** s’arrête sur *Configure an
   authenticator* et propose les deux types.
2. **Une application d’authentification** (TOTP) : scannez le code QR avec
   n’importe quelle application d’authentification, puis saisissez le code à six
   chiffres qu’elle affiche pour confirmer.
3. **Une clé de sécurité ou une passkey** (WebAuthn) : le navigateur demande de
   toucher la clé ou d’utiliser la passkey de l’appareil, puis de la nommer.
4. **Chaque connexion suivante** demande un code ou un toucher après le mot de
   passe.
5. **Les codes de récupération** méritent d’être créés tout de suite : dans les
   paramètres de l’utilisateur - l’avatar, puis **Settings → MFA Devices →
   Enroll → Static tokens** -, Authentik affiche une série de codes à usage
   unique. Conservez-les ailleurs qu’avec le téléphone.

Plusieurs facteurs peuvent être enregistrés depuis la même page, et un second
appareil - une clé en plus d’une application - est la récupération la moins
coûteuse qui soit.

### Comment il est imposé {#how-it-is-enforced}

Le blueprint modifie l’étape du flux par défaut au lieu d’en associer une
seconde : une personne disposant d’un authentificateur n’est sollicitée qu’une
fois, pas deux. Pour lever l’exigence, retirez le fichier du répertoire des
blueprints ; l’étape conserve son dernier réglage jusqu’à ce que vous le
modifiiez.

Deux choses ne sont pas concernées. **Les agents** qui utilisent
`client_credentials` se connectent avec un mot de passe d’application et
n’exécutent jamais de flux : un jeton pour `/mcp` ne demande donc de code sur le
téléphone de personne. Et **un authentificateur perdu** est récupéré par un
administrateur : connectez-vous en tant qu’`akadmin`, ouvrez **Directory →
Users** et supprimez l’appareil de la personne sous *MFA Authenticators* ; sa
connexion suivante en enregistre un nouveau.

## Des comptes sans l’interface d’administration {#accounts-without-the-admin-interface}

Une pile générée par `docker/setup-wizard.py` va plus loin : personne ne crée de
compte à la main. L’assistant demande **qui se connecte**, par nom
d’utilisateur - toutes les personnes de la liste d’invités de l’opérateur,
`COS_WEB_ADMIN_USERS`, y figurent qu’elles soient répétées ou non - et écrit
trois choses :

| Où | Quoi |
|:------|:-----|
| `.env` | `AUTHENTIK_ENROLLMENT_TOKEN`, un UUID aléatoire, et `AUTHENTIK_BOOTSTRAP_PASSWORD` pour `akadmin` |
| Le fichier compose | `COS_AUTHENTIK_ACCOUNTS`, les noms d’utilisateur, et `COS_WEB_ADMIN_USERS`, pour les deux conteneurs Authentik |
| `authentik/blueprints/` | `opencloud-enrollment.yaml` et `opencloud-mfa.yaml`, à côté des deux autres |

et termine en affichant un lien :

```
https://sso.example.com/if/flow/opencloud-scanner-enrollment/?itoken=<AUTHENTIK_ENROLLMENT_TOKEN>
```

Le jeton est un identifiant : l’assistant affiche donc le paramètre fictif et
non la valeur, et à côté la commande qui assemble le vrai lien à partir de
`.env` :

```
echo "https://sso.example.com/if/flow/opencloud-scanner-enrollment/?itoken=$(sed -n 's/^AUTHENTIK_ENROLLMENT_TOKEN=//p' .env)"
```

Chaque personne nommée l’ouvre, saisit son nom d’utilisateur, une adresse e-mail
et un mot de passe, enregistre une application d’authentification ou une clé de
sécurité, et se retrouve connectée. Une personne de la liste d’invités de
l’opérateur est placée au passage dans `opencloud-scanner-operators`, le groupe
auquel `/admin` est associé. Rien n’est cliqué dans Authentik, ni par elles ni
par vous.

Le lien est une porte d’entrée ; trois règles l’encadrent :

- **Seuls les noms listés.** Un nom d’utilisateur absent de
  `COS_AUTHENTIK_ACCOUNTS` est refusé dès le formulaire, et une liste vide
  n’admet personne.
- **Chaque nom une seule fois.** Le champ du nom d’utilisateur refuse un nom qui
  existe déjà : un nom déjà enregistré ne peut pas être revendiqué à nouveau, et
  le lien devient inutile une fois que tout le monde sur la liste l’a utilisé.
- **Uniquement avec le jeton.** Sans lui - ou avec un autre -, le flux répond
  *access denied* avant d’afficher le moindre champ.

Traitez-le comme un mot de passe tant que tout le monde ne l’a pas utilisé. Pour
ajouter quelqu’un plus tard, relancez l’assistant, ajoutez le nom et envoyez le
même lien ; pour retirer le lien, remplacez `AUTHENTIK_ENROLLMENT_TOKEN` dans
`.env` par un nouvel UUID et redémarrez les conteneurs Authentik : l’invitation
est réappliquée avec le nouveau jeton. Une personne qui s’arrête après le mot de
passe et avant le second facteur a déjà un compte : une connexion normale la
conduit alors à enregistrer le facteur.

**`akadmin` est conservé pour la récupération.** `AUTHENTIK_BOOTSTRAP_PASSWORD`
lui attribue un mot de passe aléatoire au tout premier démarrage, ce qui ferme
aussi le flux `/if/flow/initial-setup/` - sans cela, la première personne à
l’atteindre deviendrait administrateur. Lui aussi doit enregistrer un second
facteur à sa première connexion. La variable n’a aucun effet sur une base de
données qui contient déjà `akadmin`.

`docker-compose.authentik.yml`, lancé à la main, monte aussi le blueprint
d’inscription mais n’a pas de jeton : aucune invitation n’est créée et le flux
est inutilisable ; les comptes y sont créés comme décrit sous
[autoriser une personne](#adding-somebody-who-may-use-the-endpoint).

Le lien n’est pas affiché avec `--non-interactive`, qui n’affiche rien ;
construisez-le à partir de l’adresse publique d’Authentik et de
`AUTHENTIK_ENROLLMENT_TOKEN` dans `.env`, comme le montre le commentaire en tête
du fichier compose généré.

## Un opérateur pour /admin {#an-operator-for-admin}

L’espace opérateur exige que deux éléments concordent au sujet d’une même
personne, et ils se trouvent de part et d’autre de l’authentification déléguée :

| Où | Ce qui est décidé |
|:------|:----------------|
| Authentik : appartenance à `opencloud-scanner-operators` | Si la connexion peut seulement atteindre `scan.example.com`. L’application `/admin` est associée à ce groupe : toute personne extérieure est arrêtée chez Authentik |
| Le service d’analyse : `COS_WEB_ADMIN_USERS` | Si le nom d’utilisateur transmis par l’outpost est un opérateur de *ce* déploiement |

Une personne a besoin des deux : le même nom d’utilisateur dans le groupe et sur
la liste. Voici le même résultat obtenu de deux façons ; la vérification finale
s’applique à l’une comme à l’autre.

### Avec l’assistant {#with-the-wizard}

Lancez `docker/setup-wizard.py`, activez l’espace opérateur et répondez :

- **la liste d’invités de l’opérateur** (`admin_users`) avec le nom
  d’utilisateur, par exemple `scanokko` ;
- **qui se connecte** (`authentik_accounts`) : la liste d’invités y est ajoutée
  de toute façon, il n’y a donc rien à répéter.

Démarrez la pile, construisez le lien d’inscription à partir de `.env` avec la
commande affichée par l’assistant (voir [des comptes sans l’interface
d’administration](#accounts-without-the-admin-interface)), et envoyez-le à cette
personne. Elle l’ouvre et :

1. saisit le nom d’utilisateur exactement comme sur la liste d’invités, une
   adresse e-mail et un mot de passe ;
2. enregistre un second facteur - en scannant le code QR avec une application
   d’authentification, ou en enregistrant une clé de sécurité ou une passkey
   (voir [ce que voit la personne](#what-the-person-sees)) ;
3. est connectée, et déjà membre de `opencloud-scanner-operators`.

Elle peut alors ouvrir `https://scan.example.com/admin`. Pour ajouter un
opérateur plus tard, relancez l’assistant sur le même annuaire, ajoutez le nom à
la liste d’invités, redémarrez les conteneurs Authentik pour qu’ils lisent la
nouvelle liste, et envoyez le même lien.

### À la main, dans l’interface Authentik {#by-hand-in-the-authentik-interface}

Pour un compte qui existait avant d’être placé sur la liste d’invités, une base
de données sur laquelle le flux d’inscription n’a jamais été exécuté, ou un
Authentik que vous exploitez vous-même.

**1. Accédez à `akadmin`.** Sur une pile générée par l’assistant, le mot de passe
est `AUTHENTIK_BOOTSTRAP_PASSWORD` dans `.env` - mais seulement si la base de
données a été créée par cette pile. La variable est appliquée au tout premier
démarrage et ignorée sur une base qui contient déjà `akadmin` : un `.env`
régénéré à côté d’un volume plus ancien contient donc un mot de passe que rien
n’accepte. Générez plutôt un accès à usage unique :

```bash
docker compose exec authentik_worker ak create_recovery_key 10 akadmin
```

La commande affiche un chemin, valable dix minutes. Ouvrez-le sur l’adresse
publique d’Authentik - `https://sso.example.com` suivi de ce chemin - et vous
êtes connecté en tant qu’`akadmin` sans mot de passe ; définissez-en un dans les
paramètres de l’utilisateur. À la première connexion, `akadmin` doit
enregistrer un second facteur comme tout le monde.

**2. Créez le compte utilisateur.** **Directory → Users → New User → Internal User**. Le
nom d’utilisateur doit être écrit exactement comme dans `COS_WEB_ADMIN_USERS` :
le service compare le nom transmis, pas l’e-mail ni le nom affiché. Donnez-lui
une adresse e-mail, pour qu’une récupération de mot de passe puisse aboutir
quelque part.

**3. Donnez-lui un mot de passe.** Sur la page de l’utilisateur, **Set
password**, ou mieux **Email recovery link** si [la messagerie](#sending-mail)
est configurée, ou **Create recovery link** pour transmettre le lien par un
autre moyen. Avec un lien, le mot de passe ne passe jamais par votre
presse-papiers.

**4. Ajoutez-la au groupe.** Sur la page de l’utilisateur, **Groups → Add to
existing group → `opencloud-scanner-operators`**. Ou depuis le groupe :
**Directory → Groups → opencloud-scanner-operators → Users → Add existing
user**. Ne cochez *Superuser* nulle part : un superutilisateur Authentik
administre Authentik, ce qui n’a rien à voir avec le rôle d’opérateur du
scanner.

**5. Elle se connecte.** Elle ouvre `https://scan.example.com/admin`, est
redirigée vers Authentik, se connecte, enregistre un second facteur et revient.

Les étapes 2 et 4 peuvent aussi se faire depuis un shell - chaque commande sur
une seule ligne, telle qu’écrite, car `ak shell -c` exécute la chaîne comme un
script et une indentation collée provoque une erreur de syntaxe :

```bash
# Create the account with no usable password; hand them a recovery link after.
docker compose exec authentik_worker ak shell -c "from authentik.core.models import User; u = User(username='scanokko', email='scanokko@example.com', name='scanokko'); u.set_unusable_password(); u.save(); print('CREATED')" 2>&1 | grep -E 'CREATED|Error'
docker compose exec authentik_worker ak create_recovery_key 60 scanokko

# Put it in the operator group.
docker compose exec authentik_worker ak shell -c "from authentik.core.models import Group, User; Group.objects.get(name='opencloud-scanner-operators').users.add(User.objects.get(username='scanokko')); print('ADDED')" 2>&1 | grep -E 'ADDED|Error|DoesNotExist'
```

Le lien de récupération produit par `create_recovery_key` permet à cette
personne de définir son propre mot de passe ; il expire après le nombre de
minutes indiqué.

### Vérifier {#checking-it}

L’appartenance au groupe est ce qui échoue en silence : la personne se connecte,
et Authentik affiche une erreur au lieu de la renvoyer :

```bash
docker compose exec authentik_worker ak shell -c "from authentik.core.models import Group; g = Group.objects.get(name='opencloud-scanner-operators'); print('IN_GROUP', g.users.filter(username='scanokko').exists())" 2>&1 | grep -E 'IN_GROUP|Error|DoesNotExist'
```

Et le cas négatif, qui vaut bien une minute : un compte qui n’est *pas* dans le
groupe doit recevoir l’erreur d’Authentik, et non l’espace opérateur. **Events →
Logs** enregistre chaque refus avec le compte et l’application concernés.

## Relier le scanner au fournisseur {#pointing-the-scanner-at-it}

La pile ci-dessus le fait pour vous : les valeurs ci-dessous figurent déjà dans
`docker-compose.authentik.yml`, lues depuis `.env`. Cette section sert à relier
le service à un Authentik, ou à tout autre fournisseur, que vous exploitez déjà.
Sur `web_app`, dans `docker/docker-compose.yml` ou dans `docker/.env` :

```yaml
COS_WEB_PUBLIC_BASE_URL: "https://scanner.example.com"
COS_WEB_MCP_AUTH_ENABLED: "true"
COS_WEB_MCP_AUTH_ISSUER: "https://sso.example.com/application/o/opencloud-scanner/"
COS_WEB_MCP_AUTH_AUDIENCE: "<the provider's client ID>"
```

| Paramètre | Signification |
|:--------|:--------|
| `COS_WEB_MCP_AUTH_ENABLED` | Si `/mcp` exige un jeton. Désactivé par défaut |
| `COS_WEB_MCP_AUTH_ISSUER` | L’émetteur, exactement comme l’écrit le document de découverte. Une barre oblique finale est acceptée dans les deux cas |
| `COS_WEB_MCP_AUTH_AUDIENCE` | Ce que le `aud` d’un jeton doit contenir. Dans Authentik, c’est l’ID client. **Obligatoire** dès que la connexion est activée |
| `COS_WEB_MCP_AUTH_JWKS_URL` | Uniquement lorsque les clés ne se trouvent pas à `<issuer>/jwks/` |
| `COS_WEB_MCP_AUTH_RESOURCE_URL` | Uniquement lorsque `/mcp` ne se trouve pas à `<public base URL>/mcp` |
| `COS_WEB_MCP_AUTH_SCOPES` | Les portées qu’un jeton doit porter, séparées par `;`. Vide, tout jeton valide de cet émetteur suffit |

Quatre erreurs de configuration **empêchent le démarrage** plutôt que de servir
`/mcp` sans protection, car un opérateur qui croit le point de terminaison
protégé alors qu’il ne l’est pas est le pire scénario possible ici :

- authentification activée sans émetteur : il n’y aurait rien à vérifier ;
- authentification activée sans URL de base publique ni URL de ressource : la
  réponse 401 nomme cette URL et les métadonnées RFC 9728 sont publiées
  en dessous, la deviner enverrait donc chaque client ailleurs ;
- une URL de ressource qui n’est ni en HTTPS ni en bouclage : un jeton porteur
  sur un tronçon non chiffré est un identifiant en clair ;
- authentification activée sans audience - voir ci-dessous.

Demander l’authentification alors que `COS_WEB_ENABLE_MCP` vaut `false` n’est
*pas* une erreur. Désactiver le point de terminaison est un très bon moyen de le
protéger, et faire échouer au démarrage la configuration la plus sûre
n’apprendrait qu’à désactiver le garde-fou.

**L’audience est obligatoire.** Un Authentik qui sert d’autres applications
émet des jetons pour toutes, avec le même émetteur et la même clé de signature :
un `aud` jamais comparé ferait de chacun de ces jetons une clé pour `/mcp`, y
compris un jeton émis pour une application que n’importe qui dans l’annuaire
peut utiliser. Laisser `COS_WEB_MCP_AUTH_AUDIENCE` vide arrête donc le service
au lieu d’élargir l’accès, et un jeton sans aucun `aud` est refusé
pour la même raison. La pile de `docker/docker-compose.authentik.yml` la définit
à partir de `AUTHENTIK_CLIENT_ID` et ne démarre pas sans elle.

## Autoriser une personne à utiliser le point de terminaison {#adding-somebody-who-may-use-the-endpoint}

**Lisez ceci avant que la pile soit accessible à d’autres personnes.** Le
blueprint provisionne un fournisseur et une application, et une application sans
association peut être utilisée par **tous** les comptes de cet Authentik. Sur
une pile dont le rôle est de protéger `/mcp`, c’est généralement acceptable le
premier jour, quand le seul compte est l’`akadmin` créé au premier démarrage, et
rarement le deuxième.

Rien de l’identité d’un appelant n’atteint le service d’analyse. Il vérifie une
signature, un émetteur, une audience, une expiration et les portées qu’on lui a
demandé d’exiger ; il ne regarde jamais le sujet, le nom d’utilisateur ni un
claim de groupe, et n’a aucune table d’utilisateurs où les chercher. Qui peut
détenir un jeton relève donc entièrement d’Authentik, décidé dans les deux étapes
ci-dessous, et c’est le seul endroit où cette décision existe.

### Un groupe, et l’association qui lui donne un sens {#a-group-and-the-binding-that-makes-it-mean-something}

Faites-le une fois, avant le premier utilisateur. Une association sur un groupe
est un seul élément à réexaminer plus tard ; les associations par personne
s’accumulent et sont rarement nettoyées.

1. **Directory → Groups → Create**. Nommez-le `opencloud-scanner`. Laissez
   *Superuser privileges* désactivé : ce groupe concerne une application, et un
   superutilisateur Authentik est un administrateur d’Authentik.
2. **Applications → Applications → OpenCloud security scanner**, onglet
   **Policy / Group / User Bindings**, **Bind existing Group/User**.
3. Choisissez le groupe, laissez le mode du moteur de politiques sur **any**, et
   créez l’association.

Dès lors, l’application est fermée à toute personne extérieure au groupe, et une
demande de jeton de quelqu’un d’autre échoue chez Authentik plutôt que sur
`/mcp`. L’échec est journalisé sous **Events → Logs** comme une autorisation
refusée : c’est la page à consulter quand quelqu’un jure que son mot de passe est
correct.

Testez le cas négatif au lieu de le supposer : un compte extérieur au groupe ne
doit *pas* pouvoir obtenir de jeton. Une application qui semble associée mais ne
l’est pas est la seule défaillance qui mérite qu’on y consacre deux minutes.

### La personne {#the-person}

**Directory → Users → New User → Internal User.** Le nom d’utilisateur et
l’e-mail sont les deux champs importants ; l’e-mail est la destination d’une
récupération de mot de passe, et un compte sans e-mail ne peut être récupéré que
par un administrateur.

Ensuite, sur la page de l’utilisateur :

- **Set password**, ou **Email recovery link** si vous avez configuré
  [la messagerie](#sending-mail) - la seconde option est la meilleure habitude,
  car le mot de passe n’est alors jamais passé par votre presse-papiers, votre
  terminal ou le message de chat dans lequel vous l’auriez envoyé. **Create
  recovery link** produit le même lien, à transmettre par un autre moyen
  lorsqu’il n’y a pas de serveur de messagerie.
- **Groups → Add to existing group** → `opencloud-scanner`.

Une personne qui se connecte dans un navigateur n’a besoin de rien d’autre : son client MCP
la conduit chez Authentik, elle se connecte, et le client obtient un jeton. Rien
n’est à copier, et il n’y a aucune configuration par utilisateur côté scanner.

**Un second facteur est déjà exigé.** La personne est conduite à en enregistrer
un lors de sa première connexion - voir
[un second facteur pour tout le monde](#a-second-factor-for-everybody) -, il n’y a
donc rien à activer pour elle.

### L’agent avec un compte de service {#the-agent-that-is-nobody}

Une tâche cron, un pipeline CI ou un assistant exécuté sur un serveur n’a pas de
navigateur par lequel passer, et ne devrait pas détenir le mot de passe d’une
personne. Il reçoit un **compte de service** : un compte doté d’identifiants et
sans connexion interactive.

**Directory → Users → New User → Service Account.** L’écran de confirmation
affiche le nom d’utilisateur et un **mot de passe d’application**, une seule
fois : conservez ce secret dès sa création, car vous ne pourrez pas
l’afficher de nouveau. Ajoutez le compte à `opencloud-scanner` comme pour une personne, car une
association s’applique aux deux types de comptes ; *Create group* dans le
formulaire fait l’équivalent dans l’autre sens si vous préférez associer un
compte isolément.

Deux détails à noter tout de suite plutôt qu’à découvrir plus tard. Le mot de
passe d’application **expire au bout de 360 jours** si vous ne décochez pas
*Expiring* : un agent qui a fonctionné toute l’année s’arrête alors sans raison
visible. Émettez-en un nouveau depuis **Directory → Tokens and App passwords**
avant cette échéance. Et un compte de service ne peut utiliser ni l’interface
d’administration ni l’interface utilisateur, et c’est voulu : il a des
identifiants, pas de connexion.

Donnez-en un à chaque appelant plutôt que d’en partager un. Ils ne coûtent rien,
et vous pouvez ainsi en révoquer un seul sans toucher aux autres.

## Obtenir un jeton {#getting-a-token}

L’identifiant utilisé par un appelant dépend de sa nature, et les trois cas
aboutissent au même point de terminaison des jetons :

| L’appelant | Ce qu’il présente | D’où vient l’identifiant |
|:-----------|:-----------------|:--------------------------------|
| Une personne au clavier | Le flux par code d’autorisation, dans un navigateur | Son propre mot de passe et son second facteur |
| Un agent agissant pour une personne | Le nom d’utilisateur de cette personne et un mot de passe d’application | **Directory → Tokens and App passwords** |
| Un agent utilisant son propre compte de service | Le nom d’utilisateur et le mot de passe d’application d’un compte de service | Affichés une fois à la création du compte de service |

Pour un compte de service explicitement nommé, utilisez son nom d’utilisateur et
son mot de passe d’application avec l’ID et le secret client du fournisseur.
Authentik accepte aussi la requête avec les seuls identifiants client décrite
ci-dessous, qui crée un compte de service partagé. Choisissez un compte distinct
par appelant si vous avez besoin d’une révocation individuelle.

### En tant que compte de service {#as-a-service-account}

Le cas ordinaire pour un agent, et celui à privilégier :

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$AUTHENTIK_CLIENT_SECRET" \
  -d username="scanner-agent" \
  -d password="$APP_PASSWORD" \
  -d scope="openid" | jq -r .access_token
```

`username` est le compte de service, `password` son mot de passe
d’application, et `client_id` et `client_secret` sont ceux du fournisseur, tirés
directement de `docker/.env`. Demandez les portées exigées par le déploiement :
`openid` seul suffit tant que `COS_WEB_MCP_AUTH_SCOPES` est vide, ce qui est la
valeur par défaut.

Pour un client auquel on ne peut donner qu’un seul secret, la même chose avec le
nom d’utilisateur intégré :

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$(printf '%s:%s' scanner-agent "$APP_PASSWORD" | base64 -w0)" \
  -d scope="openid" | jq -r .access_token
```

### Sans nommer de compte {#without-naming-an-account-at-all}

Omettez le nom d’utilisateur et n’envoyez que l’ID et le secret client du
fournisseur : Authentik émet alors le jeton pour un compte de service qu’il crée
à cet effet, nommé `ak-check-opencloud-security-client_credentials` :

```bash
curl -s https://sso.example.com/application/o/token/ \
  -d grant_type=client_credentials \
  -d client_id="$AUTHENTIK_CLIENT_ID" \
  -d client_secret="$AUTHENTIK_CLIENT_SECRET" \
  -d scope="openid" | jq -r .access_token
```

C’est le chemin le plus court vers un jeton fonctionnel, et le bon pour essayer
le point de terminaison. C’est un mauvais choix à long terme : tous les appelants
qui l’utilisent sont le même compte, en révoquer un les révoque tous, et
l’identifiant qu’il active est le secret du fournisseur que lit aussi le service
d’analyse. Une fois l’association ci-dessus en place, pensez à ajouter aussi ce
compte généré au groupe, sinon ce chemin cesse de fonctionner. C’est le résultat
attendu, et une bonne occasion de passer à votre propre compte de service.

### En tant que personne {#as-a-person}

Un client MCP qui implémente le flux OAuth n’a besoin que de l’URL : il reçoit la
réponse `401`, lit `/.well-known/oauth-protected-resource/mcp`, trouve
Authentik, ouvre un navigateur et revient avec un jeton. Le blueprint autorise
déjà la redirection de bouclage qu’utilise un tel client -
`http://127.0.0.1:<port>/...`, uniquement sur 127.0.0.1 -, et le flux
d’autorisation est celui à consentement implicite : il n’y a donc pas d’écran de
consentement entre la connexion et l’accès.

Si un client demande à être enregistré, enregistrez-le à la main sous
**Applications → Providers** : Authentik prend en charge l’enregistrement
dynamique des clients, mais il est désactivé par défaut et protégé par un jeton
d’enregistrement.

### Lire le jeton obtenu {#reading-the-token-you-got}

Avant de vous demander pourquoi `/mcp` en refuse un, regardez ce qu’il contient :

```bash
python -c 'import base64,json,sys;p=sys.argv[1].split(".")[1];print(json.dumps(json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))),indent=2))' "$TOKEN"
```

| Claim | Ce qu’il doit être |
|:------|:----------------|
| `iss` | `COS_WEB_MCP_AUTH_ISSUER`, à la barre oblique finale près |
| `aud` | Contient `COS_WEB_MCP_AUTH_AUDIENCE`, c’est-à-dire l’ID client |
| `exp` | Dans le futur - la durée de vie par défaut d’un jeton d’accès Authentik se compte en minutes, pas en jours |
| `scope` | Contient tout ce que liste `COS_WEB_MCP_AUTH_SCOPES`, le cas échéant |
| `sub` | Ce qu’Authentik a décidé. **Le service d’analyse ne le lit pas** |

Utilisez-le ensuite ; c’est la seule étape qui fait intervenir ce service :

```bash
curl -s https://scanner.example.com/mcp \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Une liste d’outils signifie que toute la chaîne fonctionne. Une réponse `401`
signifie que le jeton n’a pas été accepté, et l’en-tête de cette réponse nomme le
document qui indique pourquoi il le serait. Un jeton émis reste valable jusqu’à
son expiration : émettez-en un par exécution plutôt qu’un par requête.

Authentik émet toujours des jetons d’accès JWT, quelle que soit la façon dont
vous les demandez : il n’y a donc jamais de chaîne opaque à introspecter, et le
service d’analyse n’a jamais rien à demander à Authentik.

## Configurer un agent {#configuring-an-agent}

La plupart des clients MCP acceptent un en-tête statique, ce qui est la solution
la plus simple :

```json
{
  "servers": {
    "opencloud-scan": {
      "type": "http",
      "url": "https://scanner.example.com/mcp",
      "headers": { "Authorization": "Bearer ${input:token}" }
    }
  }
}
```

Un client qui implémente la spécification d’autorisation MCP n’a besoin d’aucune
configuration en dehors de l’URL : il recevra la réponse 401, lira
`/.well-known/oauth-protected-resource/mcp`, trouvera Authentik et conduira
l’utilisateur à travers le flux. Authentik prend bien en charge
l’enregistrement dynamique des clients, mais il est désactivé par défaut et
protégé par un jeton d’enregistrement : enregistrer le client à la main dans
l’interface d’administration est la méthode qui fonctionne toujours.

Consultez [le guide MCP](mcp.md) pour les fichiers de configuration propres à
chaque client ; le seul ajout ici est l’en-tête.

## L’effacement, qui est un autre identifiant {#erasure-which-is-a-different-credential}

`erase_instance_data` exige l’identifiant d’effacement de l’opérateur -
`COS_WEB_PURGE_TOKEN` -, qui n’a jamais été une identité. Lorsque le point de
terminaison est ouvert, il circule dans `Authorization`, car rien d’autre
n’utilise cet en-tête.

**Lorsqu’une connexion est configurée, `Authorization` appartient au
fournisseur d’identité, et l’identifiant d’effacement passe dans
`X-Purge-Authorization`.** L’ancien comportement n’est pas
conservé, afin que le jeton d’identité d’un agent ne soit jamais lu comme un
identifiant d’opérateur.

```json
"headers": {
  "Authorization": "Bearer ${input:token}",
  "X-Purge-Authorization": "Bearer ${input:purge_token}"
}
```

Ni l’un ni l’autre n’atteint jamais le modèle : l’outil les lit dans les
en-têtes de la requête, jamais dans un argument.

## Derrière un reverse proxy {#behind-a-reverse-proxy}

Deux hôtes, deux exigences.

**Authentik construit l’émetteur à partir de l’en-tête `Host` qu’il reçoit.** Un
proxy qui le réécrit donne à chaque jeton un `iss` qui sera refusé, et
le symptôme est déroutant parce que tout le reste fonctionne. Transmettez `Host`
et `X-Forwarded-Proto` sans modification, et ajoutez l’adresse de sortie du proxy
à `AUTHENTIK_LISTEN__TRUSTED_PROXY_CIDRS` si elle est en dehors des plages
privées. Authentik ne peut pas fonctionner sous un sous-chemin : donnez-lui un
nom d’hôte.

Définissez `COS_WEB_PUBLIC_BASE_URL` sur l’adresse publique du scanner pour les
métadonnées de ressource. L’audience des jetons se configure séparément avec
`COS_WEB_MCP_AUTH_AUDIENCE`. Le [guide des reverse proxies](reverse-proxy.md)
contient des configurations fonctionnelles.

## Sauvegarder {#backing-it-up}

**Authentik n’a pas de sauvegarde intégrée.** Celle qui existait a été retirée il
y a des années : c’est donc à vous de la mettre en place. Quatre éléments
comptent, et les deux premiers sont ceux qui rendent une restauration possible :

| Quoi | Où | Pourquoi |
|:-----|:------|:----|
| `AUTHENTIK_SECRET_KEY` | `docker/.env` | Signe tout le contenu de la base. Une autre clé rend une base restaurée inutilisable |
| PostgreSQL | le volume `authentik_database` | Utilisateurs, groupes, flux, politiques, fournisseurs, jetons, certificats. La perdre, c’est tout perdre |
| Médias | le volume `authentik_media` | Icônes et arrière-plans téléversés |
| Certificats et modèles | `authentik_certs`, `authentik_templates` | Uniquement si vous y avez placé quelque chose qui n’est pas dans la base |

```bash
cd docker
stack="-f docker-compose.authentik.yml"
stamp=$(date +%F)

# The database, as SQL, with the drop-and-create statements a clean restore
# needs.
docker compose $stack exec -T authentik_postgresql \
  pg_dump -U authentik -d authentik --clean --create \
  > "authentik-db-$stamp.sql"

# The volumes that are not the database.
for volume in media templates certs; do
  docker run --rm \
    -v "$(basename "$PWD")_authentik_$volume:/from:ro" \
    -v "$PWD:/to" alpine \
    tar czf "/to/authentik-$volume-$stamp.tar.gz" -C /from .
done

# And the secrets, without which none of the above is worth anything.
cp .env "authentik-env-$stamp.backup"
```

Les noms des volumes sont préfixés par le nom du projet Compose, qui est le nom
du répertoire sauf si vous définissez `COMPOSE_PROJECT_NAME`. `docker volume ls`
vous indique les noms réellement obtenus.

La sauvegarde contient des identifiants et des clés de signature. Chiffrez-la,
conservez-en une copie hors de l’hôte et testez une restauration avec la version
de base de données et le `.env` correspondants.

## Restaurer {#restoring-it}

```bash
cd docker
stack="-f docker-compose.authentik.yml"

# The secret key first, and it must be the one that was in use when the dump
# was taken.
cp authentik-env-2026-08-21.backup .env

docker compose $stack down
docker compose $stack up -d authentik_postgresql

docker compose $stack exec -T authentik_postgresql \
  psql -U authentik -d postgres < authentik-db-2026-08-21.sql

for volume in media templates certs; do
  docker run --rm \
    -v "$(basename "$PWD")_authentik_$volume:/to" \
    -v "$PWD:/from:ro" alpine \
    tar xzf "/from/authentik-$volume-2026-08-21.tar.gz" -C /to
done

docker compose $stack up -d
```

La restauration dans une autre version majeure n’est pas prise en charge ;
restaurez dans la version qui a produit la sauvegarde, puis mettez à jour.

Rien n’est à restaurer côté scanner. Il ne conserve aucun état concernant le
fournisseur en dehors des paramètres du fichier compose, et les clés de signature
sont récupérées à nouveau à la première requête.

## Quand cela ne fonctionne pas {#when-it-does-not-work}

| Symptôme | Cause |
|:--------|:------|
| Le service refuse de démarrer en citant `ISSUER`, `RESOURCE_URL` ou `HTTPS` | Exactement ce qui est indiqué ; voir [relier le scanner au fournisseur](#pointing-the-scanner-at-it) |
| Chaque requête reçoit 401, et le jeton semble correct | Le `iss` du jeton ne correspond pas à `COS_WEB_MCP_AUTH_ISSUER`. Généralement un proxy qui réécrit `Host`, ou un slug d’application différent de ce que vous pensiez |
| Chaque requête reçoit 401, `iss` est correct | `aud` ne contient pas l’audience. Dans Authentik, c’est l’ID client, pas le nom de l’application |
| 401 au bout d’un moment, après avoir fonctionné | Le jeton a expiré. Les jetons d’accès ont une courte durée de vie par conception ; le client doit le renouveler |
| 401 et le jeton contient `"alg": "HS256"` | Pas de clé de signature sur le fournisseur. Définissez-en une et émettez un nouveau jeton : un jeton signé de façon symétrique ne peut pas être vérifié sans le secret client, et ce service ne l’accepte pas |
| 401 alors que tout semble correct | Une portée exigée par `COS_WEB_MCP_AUTH_SCOPES` manque dans le claim `scope` du jeton |
| N’importe qui avec un compte Authentik peut obtenir un jeton | L’application n’a pas d’association, ce qui signifie tout le monde. Voir [autoriser une personne à utiliser le point de terminaison](#adding-somebody-who-may-use-the-endpoint) |
| La demande de jeton elle-même est refusée, avant même d’atteindre `/mcp` | Le compte n’est pas associé à l’application. **Events → Logs** l’enregistre comme une autorisation refusée, avec le nom du compte |
| Cela fonctionnait jusqu’à l’ajout d’une association de groupe, avec le seul secret client | Ce chemin s’exécute sous le compte de service généré par Authentik, `ak-check-opencloud-security-client_credentials`, qui n’est pas non plus dans le groupe. Ajoutez-le, ou passez à votre propre compte de service |
| `invalid_grant` sur une requête `client_credentials` | Le `password` est un **mot de passe d’application**, ni le mot de passe de connexion de l’utilisateur ni un jeton d’API. Créez-en un sous **Directory → Tokens and App passwords** |
| Le lien d’inscription répond *access denied* | Le jeton n’est pas celui de `.env`, ou la pile a été démarrée sans `AUTHENTIK_ENROLLMENT_TOKEN`. Cherchez `check-opencloud-security - enrollment` sous **Customisation → Blueprints** |
| « This username is not one this invitation was issued for. » | Le nom ne figure pas dans `COS_AUTHENTIK_ACCOUNTS`. Relancez l’assistant et ajoutez-le ; la liste est lue à la soumission du formulaire, après un redémarrage des conteneurs Authentik |
| « Username is already taken. » sur le lien d’inscription | Ce nom est déjà inscrit. Connectez-vous normalement |
| Quelqu’un a perdu son authentificateur | Connectez-vous en tant qu’`akadmin` (mot de passe `AUTHENTIK_BOOTSTRAP_PASSWORD` dans `.env`) et supprimez son appareil sous **Directory → Users** |
| `AUTHENTIK_BOOTSTRAP_PASSWORD` est refusé pour `akadmin` | La base de données est plus ancienne que ce `.env` : la variable n’est appliquée qu’au premier démarrage. `docker compose exec authentik_worker ak create_recovery_key 10 akadmin` affiche une connexion à usage unique ; voir [un opérateur pour /admin](#by-hand-in-the-authentik-interface) |
| La connexion à `/admin` fonctionne chez Authentik, qui affiche ensuite une erreur au lieu de vous renvoyer | Le compte n’est pas dans `opencloud-scanner-operators`. Voir [vérifier](#checking-it) |
| Le compte est dans le groupe Authentik et `/admin` refuse toujours | Le nom d’utilisateur ne figure pas dans `COS_WEB_ADMIN_USERS`, ou y est écrit différemment |
| `password authentication failed for user "authentik"` dans le journal d’Authentik | `AUTHENTIK_PG_PASS` dans `.env` n’est pas le mot de passe avec lequel le volume de base de données a été créé : PostgreSQL ne lit `POSTGRES_PASSWORD` qu’à l’initialisation d’un volume vide. Remettez l’ancienne valeur, ou changez le mot de passe de l’utilisateur de la base avec `ALTER USER authentik WITH PASSWORD '...'` via `docker compose exec authentik_postgresql psql -U authentik` |
| L’e-mail de récupération de mot de passe n’arrive jamais | Pas de serveur de messagerie : Authentik l’a livré localement. Voir [envoyer des e-mails](#sending-mail) |
| Pas de `WWW-Authenticate` sur la réponse 401 | Un élément placé devant le supprime. Cet en-tête est ce qui permet à un client de trouver le fournisseur |
| Le point de terminaison est ouvert alors qu’il ne devrait pas l’être | `COS_WEB_MCP_AUTH_ENABLED` n’a pas atteint le conteneur. `/.well-known/ai.json` indique ce que le service croit réellement : `mcp.authentication.type` |
| 401, et le journal indique que le JWKS n’a pas pu être récupéré | L’URL se résout mais Authentik répond **404**. Un nom de service Compose contenant un tiret bas n’est pas un nom d’hôte valide, et Authentik le refuse ; utilisez l’alias `authentik-server`, comme le fait la pile fournie |
| Le blueprint n’apparaît jamais sous **Customisation → Blueprints** | Authentik le lit avec l’uid 1000. Un répertoire `authentik/blueprints` non lisible par tous - un `umask` restrictif lors du clonage du dépôt - est ignoré en silence. `chmod 755 authentik/blueprints && chmod 644 authentik/blueprints/*.yaml` |
| Le conteneur de base de données est en mauvaise santé et se plaint de `/var/lib/postgresql/data` | PostgreSQL 18 se monte un niveau plus haut, sur `/var/lib/postgresql`, et refuse l’ancien chemin au lieu de l’ignorer. Un volume d’une pile 16 ou 17 doit passer par `pg_upgrade`, pas être remonté |
| L’un des conteneurs Authentik se termine avec `Address family not supported by protocol` | L’hôte n’a pas d’IPv6, et Authentik écoute sur `[::]` par défaut. Les trois variables `AUTHENTIK_LISTEN__*` de la pile fournie le limitent à IPv4 - y compris `__METRICS`, facile à oublier et suffisante à elle seule pour faire planter le worker |

La dernière vérification mérite d’être faite après chaque modification :

```bash
curl -s https://scanner.example.com/.well-known/ai.json | jq .mcp.authentication
curl -s https://scanner.example.com/.well-known/oauth-protected-resource/mcp | jq
curl -si https://scanner.example.com/mcp -X POST -d '{}' | grep -i www-authenticate
```

## Utiliser un autre fournisseur qu’Authentik {#using-a-provider-that-is-not-authentik}

Rien ici n’est propre à Authentik. Tout fournisseur qui émet des jetons d’accès
JWT signés et publie un JWKS convient : Keycloak, Zitadel, Authelia, Auth0,
Okta. Définissez l’émetteur selon son document de découverte, l’audience selon
ce qu’il place dans `aud`, et s’il publie ses clés ailleurs qu’à
`<issuer>/jwks/`, indiquez leur emplacement dans `COS_WEB_MCP_AUTH_JWKS_URL`.
Seuls les algorithmes asymétriques sont acceptés - RS256, RS384, RS512, ES256,
ES384, ES512 -, ce qui exclut `HS256` et, surtout, `none`.

Authentik est fourni ici parce qu’il est open source, auto-hébergé, fonctionne
dans deux conteneurs à côté de la pile, et ne demande de compte auprès de
personne pour l’essayer.

---

Ce projet est un projet communautaire indépendant. Il n’est ni affilié à
OpenCloud GmbH ni à Authentik Security, Inc., ni approuvé ou soutenu par elles.
« OpenCloud » et toutes les marques associées appartiennent à leurs
propriétaires respectifs et ne sont utilisés ici que pour identifier le logiciel
que cet outil vérifie.

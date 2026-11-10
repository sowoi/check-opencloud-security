# Fournisseurs d’identité

[Exploiter OpenCloud dans une infrastructure sécurisée](secure-deployment.md#1-put-a-real-identity-provider-in-front)
explique *pourquoi* un fournisseur d’identité externe a sa place devant une
instance OpenCloud, et résume ce dont chacun des trois fournisseurs courants a
besoin. Cette page en est la version longue : trois tutoriels complets, de zéro
jusqu’à une connexion fonctionnelle, pour **Keycloak**, **Authentik** et
**Authelia**.

Choisissez-en un. Ils font le même travail, et en exécuter deux est le meilleur
moyen de n’en avoir aucun correctement configuré.

> **Cette page change qui peut se connecter, pas la façon dont OpenCloud est
> exposé.** Un fournisseur d’identité n’est qu’une mesure parmi d’autres. Le
> pare-feu, le journal d’audit, le reverse proxy et le cycle de vie des versions
> constituent le reste du travail, et [Exploiter OpenCloud dans une
> infrastructure sécurisée](secure-deployment.md) les traite ensemble.

<!-- TOC -->
* [Placer un fournisseur d’identité devant OpenCloud, étape par étape](#putting-an-identity-provider-in-front-of-opencloud-step-by-step)
  * [Avant de commencer](#before-you-start)
  * [Ce que chaque fournisseur doit produire](#what-every-provider-has-to-produce)
    * [Les quatre clients](#the-four-clients)
    * [Pourquoi ce sont tous des clients publics](#why-they-are-all-public-clients)
  * [Ce dont OpenCloud a besoin, quel que soit le fournisseur](#what-opencloud-needs-whichever-provider-you-pick)
  * [Tutoriel A : Keycloak](#tutorial-a-keycloak)
  * [Tutoriel B : Authentik](#tutorial-b-authentik)
  * [Tutoriel C : Authelia](#tutorial-c-authelia)
  * [Vérifier que tout fonctionne réellement](#verifying-it-actually-worked)
  * [Migrer une instance qui a déjà des comptes](#moving-an-instance-that-already-has-accounts)
  * [Dépannage](#troubleshooting)
  * [Pour aller plus loin](#where-to-go-next)
  * [Marques et affiliation](#trademarks-and-affiliation)
<!-- TOC -->

## Avant de commencer {#before-you-start}

Trois noms, décidés maintenant et non modifiés ensuite. Toutes les URL
ci-dessous en sont dérivées, et un émetteur qui change après que des personnes
se sont connectées invalide d’un coup toutes les sessions et tous les jetons
enregistrés par les clients de bureau :

| Nom | Exemple | Ce que c’est |
|:-----|:--------|:-----------|
| L’instance | `opencloud.example.com` | L’adresse où répond OpenCloud |
| Le fournisseur | `id.example.com` | L’adresse de la page de connexion |
| Le realm ou le slug d’application | `opencloud` | Le nom que le fournisseur donne à cette application |

Il vous faut aussi :

- **Une instance OpenCloud fonctionnelle en HTTPS.** Pas une instance que vous
  construisez en même temps. Si la connexion échoue, vous voulez savoir que le
  problème vient du fournisseur, et une instance à moitié construite vous prive
  de cette certitude.
- **Un vrai certificat sur les deux noms.** La découverte OpenID Connect est
  une requête HTTPS d’OpenCloud vers le fournisseur ; un certificat auto-signé
  à cet endroit échoue avec un message d’erreur qui mentionne rarement le certificat.
- **Les deux noms résolus depuis le réseau des conteneurs comme depuis
  l’extérieur.** C’est la cause la plus fréquente du problème « ça fonctionne
  dans le navigateur mais le client de bureau reste bloqué » - voir
  [Dépannage](#troubleshooting).
- **Un moyen de revenir en arrière.** Conservez un administrateur OpenCloud
  local jusqu’à ce que la nouvelle connexion ait fait ses preuves, et ne retirez
  pas `idp` des services en cours d’exécution avant cela.

## Ce que chaque fournisseur doit produire {#what-every-provider-has-to-produce}

Les clients, les URI de redirection et les portées (scopes) sont des propriétés
des **applications propres à OpenCloud**, pas du fournisseur. Ils sont
identiques pour Keycloak, Authentik et Authelia, et une erreur sur l’un d’eux
produit la même défaillance quel que soit le fournisseur choisi. Configurez ces
quatre clients, à chaque fois.

### Les quatre clients {#the-four-clients}

| Client | ID client par défaut | URI de redirection | Portées |
|:-------|:------------------|:--------------|:-------|
| Web | `web` | `https://opencloud.example.com/`, `https://opencloud.example.com/oidc-callback.html`, `https://opencloud.example.com/oidc-silent-redirect.html` | `openid profile email groups` |
| Bureau | `OpenCloudDesktop` | `http://127.0.0.1`, `http://localhost` | `openid profile email groups offline_access` |
| Android | `OpenCloudAndroid` | `oc://android.opencloud.eu` | `openid profile email groups offline_access` |
| iOS | `OpenCloudIOS` | `oc://ios.opencloud.eu`, `oc.ios://ios.opencloud.eu` | `openid profile email groups offline_access` |

Trois éléments de ce tableau sont essentiels :

**Le client web a besoin des trois URI de redirection.** `oidc-callback.html`
termine la connexion ; `oidc-silent-redirect.html` permet à l’onglet de
renouveler un jeton sans renvoyer quelqu’un vers un écran de connexion en plein
téléversement. N’enregistrez que la première, et la connexion fonctionne, mais
les sessions expirent ensuite à des intervalles difficiles à reproduire.

**Seuls les clients hors navigateur reçoivent `offline_access`.** C’est cette
portée qui délivre le jeton de rafraîchissement dont un client de bureau ou
mobile a besoin pour survivre à un redémarrage. Le navigateur n’en
reçoit pas, car un onglet ne peut pas stocker un jeton de rafraîchissement
de manière sûre.

**Les ID client sont configurables, et les deux côtés doivent concorder.** Le
fournisseur les connaît parce que vous les y avez saisis ; OpenCloud les publie
à ses propres clients par WebFinger, à partir de
`WEBFINGER_WEB_OIDC_CLIENT_ID` et de ses équivalents `ANDROID`, `IOS` et
`DESKTOP`. Modifiez l’un sans l’autre, et le client de bureau demande au
fournisseur un client qui n’existe pas.

### Pourquoi ce sont tous des clients publics {#why-they-are-all-public-clients}

Chaque client OpenCloud - l’application web dans un onglet, l’application de
bureau sur un portable, les deux applications mobiles - s’exécute entièrement
sur la machine de quelqu’un d’autre. Aucun ne peut garder de secret, car tout ce
qui leur est livré est un secret dont chacun de leurs utilisateurs possède une
copie.

Les quatre sont donc des **clients publics utilisant le flux par code
d’autorisation avec PKCE**, et PKCE est obligatoire : il remplace
le secret client que ces clients ne peuvent pas détenir.
Choisissez la méthode de challenge `S256`, jamais `plain`. Ne délivrez de secret
client à aucun d’eux : un fournisseur qui en exige un pour un client public est
mal configuré, et coller un secret dans une application de bureau pour le
satisfaire revient à publier ce secret.

## Ce dont OpenCloud a besoin, quel que soit le fournisseur {#what-opencloud-needs-whichever-provider-you-pick}

Définissez ces variables côté OpenCloud une fois le fournisseur en service. Le
[guide des IdP externes](https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp)
est la référence officielle ; les remarques ci-dessous concernent les points qui
méritent réflexion.

```shell
# The provider, and turning the built-in one off.
OC_OIDC_ISSUER="https://id.example.com/realms/opencloud"
OC_EXCLUDE_RUN_SERVICES="idp"

# Verify tokens against the provider's published keys rather than asking it
# on every single request.
PROXY_OIDC_ACCESS_TOKEN_VERIFY_METHOD="jwt"
PROXY_OIDC_REWRITE_WELLKNOWN="true"

# Who a token belongs to, and the OpenCloud attribute it is matched against.
PROXY_USER_OIDC_CLAIM="preferred_username"
PROXY_USER_CS3_CLAIM="username"

# Create the account on first sign-in, and where its fields come from.
PROXY_AUTOPROVISION_ACCOUNTS="true"
PROXY_AUTOPROVISION_CLAIM_USERNAME="preferred_username"
PROXY_AUTOPROVISION_CLAIM_EMAIL="email"
PROXY_AUTOPROVISION_CLAIM_DISPLAYNAME="name"
PROXY_AUTOPROVISION_CLAIM_GROUPS="groups"

# Roles from a claim - and the default role switched off, or everybody gets
# that one as well.
PROXY_ROLE_ASSIGNMENT_DRIVER="oidc"
PROXY_ROLE_ASSIGNMENT_OIDC_CLAIM="roles"
GRAPH_ASSIGN_DEFAULT_USER_ROLE="false"

# The client IDs, published to OpenCloud's own clients through WebFinger.
WEBFINGER_WEB_OIDC_CLIENT_ID="web"
WEBFINGER_DESKTOP_OIDC_CLIENT_ID="OpenCloudDesktop"
WEBFINGER_ANDROID_OIDC_CLIENT_ID="OpenCloudAndroid"
WEBFINGER_IOS_OIDC_CLIENT_ID="OpenCloudIOS"
```

Deux de ces variables sont des décisions de contrôle d’accès déguisées en
configuration, et toutes deux sont traitées plus en détail dans
[secure-deployment.md](secure-deployment.md#what-opencloud-needs-whichever-provider-you-pick) :

- **`PROXY_AUTOPROVISION_ACCOUNTS=true` signifie que toute personne
  authentifiée par votre fournisseur obtient un compte OpenCloud lors de sa
  première visite.** C’est correct lorsque le fournisseur limite cette
  application à un groupe, et incorrect lorsqu’il authentifie toute votre
  organisation. Limitez l’accès côté fournisseur. Désactiver le provisionnement
  automatique et créer les comptes à la main n’est pas la solution : c’est la
  même décision, aggravée par le travail manuel.
- **`PROXY_ROLE_ASSIGNMENT_DRIVER=oidc` avec
  `GRAPH_ASSIGN_DEFAULT_USER_ROLE=true` est l’erreur de configuration qui donne
  à tout le monde un rôle que vous n’aviez pas prévu.** Définir la première
  implique de désactiver la seconde.

Redémarrez OpenCloud après avoir modifié l’une de ces variables.
`OC_EXCLUDE_RUN_SERVICES` en particulier n’est lu qu’une fois, au démarrage.

## Tutoriel A : Keycloak {#tutorial-a-keycloak}

Le choix le plus courant lorsqu’une organisation en exploite déjà un, et le plus
lourd des trois. Choisissez-le si vous avez besoin d’un realm complet -
fédération, courtage d’identité, correspondance fine des rôles - ou si Keycloak
est déjà en place.

**1. Lancez-le.** Un service compose minimal, conçu comme en production, derrière
le reverse proxy qui termine déjà TLS pour vous :

```yaml
services:
  keycloak:
    image: quay.io/keycloak/keycloak:latest
    command: ["start", "--optimized"]
    environment:
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME: keycloak
      KC_DB_PASSWORD_FILE: /run/secrets/kc_db_password
      KC_HOSTNAME: https://id.example.com
      KC_PROXY_HEADERS: xforwarded
      KC_HTTP_ENABLED: "true"
      # Bootstrap only. Create a real administrator, then remove these two
      # and restart - they are a password in an environment variable.
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD_FILE: /run/secrets/kc_bootstrap
    secrets: [kc_db_password, kc_bootstrap]
    depends_on: [keycloak-db]
```

`KC_PROXY_HEADERS: xforwarded` est important : sans cette option, Keycloak
construit son émetteur et ses URL de redirection à partir de l’adresse interne,
et toutes sont fausses d’une manière qui n’apparaît qu’au moment de la
redirection.

**2. Créez le realm.** *Realms → Create realm*, nommé `opencloud`. N’utilisez
pas le realm `master` pour des applications : c’est le realm qui administre
Keycloak lui-même, et un client d’application à cet endroit est un client
d’application sur votre plan d’administration.

Votre émetteur est désormais :

```
https://id.example.com/realms/opencloud
```

**3. Créez les quatre clients.** *Clients → Create client*, quatre fois, avec
les ID et URI de redirection du [tableau ci-dessus](#the-four-clients). Pour
chacun :

- **Client type** : OpenID Connect.
- **Client authentication** : **désactivé**. C’est ce qui en fait un client
  public.
- **Authentication flow** : *Standard flow* uniquement. Désactivez *Direct
  access grants* : c’est l’octroi par mot de passe, et il contourne tous les
  seconds facteurs que vous allez configurer.
- **Valid redirect URIs** : celles du tableau. Le client de bureau a besoin de
  `http://127.0.0.1/*` et `http://localhost/*` : le port est choisi à
  l’exécution, le joker est donc réellement utile ici et non une facilité.
- **Web origins** : `https://opencloud.example.com`, pour le client web
  uniquement.
- Sous *Advanced → Advanced settings*, réglez **Proof Key for Code Exchange
  Code Challenge Method** sur `S256`.

**4. Créez les claims que lit OpenCloud.** *Client scopes → `<client>-dedicated`
→ Add mapper → By configuration* :

- Mapper **Group Membership**, nom de claim `groups`, *Full group path*
  **désactivé**. Sans ce dernier réglage, vos groupes arrivent sous la forme
  `/finance` et toute comparaison avec `finance` échoue.
- Mapper **User Client Role**, nom de claim `roles`, si vous attribuez les rôles
  OpenCloud depuis Keycloak.

Ajoutez les deux au **jeton d’accès** et à la réponse **userinfo**. OpenCloud
lit le jeton ; un claim présent uniquement dans le jeton d’identité est un claim
qu’il ne voit jamais.

**5. Exigez un second facteur.** *Authentication → Required actions* → activez
*Configure OTP*, puis *Authentication → Flows* → associez un flux navigateur qui
l’exige. Vérifiez que le second facteur est bien demandé lors de la connexion.

**6. Faites pointer OpenCloud vers lui** avec les variables ci-dessus, puis
redémarrez.

## Tutoriel B : Authentik {#tutorial-b-authentik}

Authentik permet une configuration par fichiers et des politiques propres à
chaque application. Une seule installation peut assurer la connexion de
plusieurs applications.

> Ce dépôt fournit déjà une pile Authentik, mais dans un autre but : elle
> protège [le point de terminaison MCP du service d’analyse](authentik.md) et
> l’[espace opérateur](../../ADMIN.md), pas OpenCloud.
> [`authentik/blueprints/`](../../authentik/blueprints/) est un exemple complet
> de provisionnement d’un fournisseur à partir d’un fichier, utile à reprendre
> quel que soit ce que vous configurez.

**1. Lancez-le.** Authentik publie un fichier compose et un générateur
associé ; suivez [leur guide
d’installation](https://docs.goauthentik.io/install-config/install/docker-compose)
pour les instructions à jour. Vérifiez ensuite que `https://id.example.com`
l’atteint en HTTPS avec un certificat valide.

**2. Créez la correspondance de portée pour les groupes.** *Customisation →
Property mappings → Create → Scope mapping* :

- **Name** : `OpenCloud groups`
- **Scope name** : `groups`
- **Expression** :
  ```python
  return {"groups": [group.name for group in request.user.ak_groups.all()]}
  ```

Authentik fournit des correspondances pour `openid`, `profile` et `email` ;
`groups` est celle que vous devez généralement ajouter, et c’est celle dont
OpenCloud a besoin pour les rôles.

**3. Créez quatre fournisseurs.** *Applications → Providers → Create →
OAuth2/OpenID Provider*, une fois par client du
[tableau ci-dessus](#the-four-clients) :

- **Client type** : **Public**.
- **Client ID** : celui du tableau.
- **Redirect URIs** : celles du tableau. Authentik les compare comme des
  expressions régulières : échappez donc les points, par exemple
  `http://127\.0\.0\.1(:[0-9]+)?` pour la plage de bouclage du client de bureau.
- **Scopes** : les trois correspondances intégrées plus `OpenCloud groups`.
- **Signing key** : votre certificat, pour que les jetons soient signés.
- **Authorization flow** : `implicit consent` pour une application interne : on
  ne devrait pas demander aux gens de consentir à votre propre serveur de
  fichiers à chaque connexion.

**4. Créez l’application et associez-la à un groupe.** *Applications →
Applications → Create*, slug `opencloud`, avec comme fournisseur le fournisseur
web de l’étape 3. Associez-la ensuite : *Policies / Group / User bindings* →
associez le groupe qui doit avoir accès à OpenCloud.

**Cette association est le contrôle d’accès qui rend le provisionnement
automatique sûr.** Grâce à elle, `PROXY_AUTOPROVISION_ACCOUNTS=true` ne crée des
comptes que pour les personnes dont vous avez déjà décidé qu’elles devaient en
avoir un.

**5. Relevez l’émetteur sur le fournisseur.** Il s’agit de :

```
https://id.example.com/application/o/opencloud/
```

**La barre oblique finale en fait partie.** OpenID Connect compare la chaîne de
l’émetteur à l’identique : un émetteur configuré sans elle échoue à la
validation des jetons qui la contiennent, et l’erreur ne mentionne ni la barre
oblique ni l’émetteur.

**6. Faites pointer OpenCloud vers lui** avec les variables ci-dessus, puis
redémarrez.

## Tutoriel C : Authelia {#tutorial-c-authelia}

Le plus léger des trois, entièrement configuré dans un fichier, et bien adapté
lorsque le reverse proxy assure déjà l’authentification déléguée (forward auth)
pour d’autres services. Choisissez-le si vous voulez un petit binaire plutôt
qu’un serveur de realms.

**1. Lancez-le**, avec son stockage de sessions :

```yaml
services:
  authelia:
    image: ghcr.io/authelia/authelia:latest
    volumes:
      - ./authelia:/config
    environment:
      AUTHELIA_IDENTITY_PROVIDERS_OIDC_HMAC_SECRET_FILE: /run/secrets/oidc_hmac
      AUTHELIA_IDENTITY_PROVIDERS_OIDC_ISSUER_PRIVATE_KEY_FILE: /run/secrets/oidc_key
    secrets: [oidc_hmac, oidc_key]
```

Générez les deux secrets avant le premier démarrage : Authelia ne les invente
pas pour vous.

```shell
docker run --rm ghcr.io/authelia/authelia:latest \
    authelia crypto rand --length 64 --charset alphanumeric
docker run --rm -v "$PWD/authelia:/keys" ghcr.io/authelia/authelia:latest \
    authelia crypto pair rsa generate --bits 4096 --directory /keys
```

**2. Enregistrez les quatre clients** sous `identity_providers.oidc.clients`
dans `configuration.yml`. Voici le client web complet ; les trois autres ne
diffèrent que par `client_id`, `redirect_uris` et l’absence de navigateur :

```yaml
identity_providers:
  oidc:
    clients:
      - client_id: 'web'
        client_name: 'OpenCloud'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups']
        redirect_uris:
          - 'https://opencloud.example.com/'
          - 'https://opencloud.example.com/oidc-callback.html'
          - 'https://opencloud.example.com/oidc-silent-redirect.html'
        response_types: ['code']
        grant_types: ['authorization_code']

      - client_id: 'OpenCloudDesktop'
        client_name: 'OpenCloud Desktop'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['http://127.0.0.1', 'http://localhost']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']

      - client_id: 'OpenCloudAndroid'
        client_name: 'OpenCloud Android'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['oc://android.opencloud.eu']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']

      - client_id: 'OpenCloudIOS'
        client_name: 'OpenCloud iOS'
        public: true
        authorization_policy: 'two_factor'
        require_pkce: true
        pkce_challenge_method: 'S256'
        token_endpoint_auth_method: 'none'
        scopes: ['openid', 'profile', 'email', 'groups', 'offline_access']
        redirect_uris: ['oc://ios.opencloud.eu', 'oc.ios://ios.opencloud.eu']
        response_types: ['code']
        grant_types: ['authorization_code', 'refresh_token']
```

`authorization_policy: 'two_factor'` est l’endroit où le second facteur est
exigé, client par client, et c’est la raison de préférer ce réglage à une règle
globale : le client de bureau et le navigateur sont soumis à la même exigence
sans dépendre de quelqu’un qui se souviendrait d’une règle de contrôle d’accès.

**3. Ajoutez la règle de contrôle d’accès** pour l’instance elle-même, afin que
tout ce qui n’est pas couvert par le flux OpenID Connect soit aussi protégé :

```yaml
access_control:
  default_policy: 'deny'
  rules:
    - domain: 'opencloud.example.com'
      policy: 'two_factor'
```

**4. L’émetteur est l’hôte seul**, sans chemin ni barre oblique finale :

```
https://id.example.com
```

**5. Faites pointer OpenCloud vers lui** avec les variables ci-dessus, puis
redémarrez.

## Vérifier que tout fonctionne réellement {#verifying-it-actually-worked}

Quatre vérifications, dans cet ordre. Chacune échoue différemment : les exécuter
dans le désordre fait perdre du temps.

**1. Le fournisseur publie un document de découverte.**

```shell
curl -fsS https://id.example.com/.well-known/openid-configuration | \
    python3 -m json.tool | head -20
```

Le champ `issuer` de la réponse doit être **identique octet pour octet** à ce
que vous avez mis dans `OC_OIDC_ISSUER`. Une barre oblique finale compte.

**2. OpenCloud pointe vers lui.** Avec `PROXY_OIDC_REWRITE_WELLKNOWN=true`,
interroger OpenCloud renvoie le document du fournisseur :

```shell
curl -fsS https://opencloud.example.com/.well-known/openid-configuration | \
    python3 -c 'import json,sys; print(json.load(sys.stdin)["issuer"])'
```

Si la réponse est l’adresse propre d’OpenCloud, l’`idp` intégré tourne
toujours : `OC_EXCLUDE_RUN_SERVICES` n’a pas pris effet, ou le conteneur n’a pas
été redémarré.

**3. Une personne peut se connecter.** Dans une fenêtre de navigation privée,
pour ne pas tester une session déjà ouverte. Vérifiez ensuite que le compte a
été créé, si vous avez activé le provisionnement automatique.

**4. Analysez l’instance.** C’est à cela que sert le reste de ce dépôt. Le
scanner indique quel fournisseur il a trouvé et lit quatre propriétés du
document de découverte publié par ce fournisseur :

```shell
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

Vérifiez que `identityProviderDetected` réussit, et regardez
`oidcPkceSupported`, `oidcImplicitFlowDisabled`, `oidcSigningAlgorithmStrong`
et `oidcEndpointsUseHttps`. [Authentification](authentication.md) explique ce
que signifie chacun et pourquoi il est vérifié. Un fournisseur qui échoue à
`oidcImplicitFlowDisabled` propose encore un flux qui place des jetons dans une
URL, ce qu’il vaut la peine de corriger avant que quiconque l’utilise.

Notez ce que cela ne prouve **pas** : le scanner lit ce que publie le
fournisseur sans se connecter, il ne peut donc pas vous dire si votre
correspondance de groupes est correcte ni si votre second facteur est
appliqué. Ce sont les deux points à tester à la main.

## Migrer une instance qui a déjà des comptes {#moving-an-instance-that-already-has-accounts}

Basculer une instance déjà utilisée est un travail différent de la
configuration d’une nouvelle instance, et toute la différence tient à la
correspondance des identités.

**Les comptes doivent correspondre.** `PROXY_USER_OIDC_CLAIM` et
`PROXY_USER_CS3_CLAIM` relient une personne connue du fournisseur à son compte
OpenCloud existant et à tout ce qu’il contient. Si `preferred_username` chez le
fournisseur n’est pas égal à `username` dans OpenCloud, le provisionnement
automatique crée un *second* compte, vide, pour une personne qui en avait déjà
un, et ses fichiers restent dans le premier.

Dans l’ordre, donc :

1. **Exportez les noms d’utilisateur existants** et comparez-les à ceux du
   fournisseur, avant de modifier quoi que ce soit. Corrigez les différences
   côté fournisseur.
2. **Laissez `idp` en service** et configurez le fournisseur externe à côté.
3. **Testez avec un compte** qui existe des deux côtés, et vérifiez qu’il
   aboutit dans l’espace existant et non dans un nouveau.
4. **Ensuite seulement**, ajoutez `idp` à `OC_EXCLUDE_RUN_SERVICES` et
   redémarrez.
5. **Conservez `PROXY_ENABLE_BASIC_AUTH=false`.** Les montages WebDAV, les
   clients CalDAV et les tâches de sauvegarde s’authentifient en HTTP Basic et
   contournent le fournisseur ainsi que tous ses seconds facteurs. Lorsque
   quelque chose en a réellement besoin, la solution est d’utiliser des jetons
   d’application plutôt que les mots de passe des comptes - voir
   [secure-deployment.md](secure-deployment.md#basic-authentication-is-the-hole-in-all-of-this).

## Dépannage {#troubleshooting}

| Ce que vous constatez | Cause habituelle |
|:-------------|:-------------------|
| `invalid issuer` ou échecs de validation des jetons | `OC_OIDC_ISSUER` ne correspond pas exactement à la chaîne `issuer` du fournisseur. Authentik exige la barre oblique finale ; Authelia n’en a pas |
| La connexion fonctionne dans le navigateur, le client de bureau reste bloqué | Le nom du fournisseur ne se résout pas depuis le réseau des conteneurs, ou l’URI de redirection du client de bureau n’a pas de joker pour le port |
| La connexion fonctionne, puis les sessions expirent à des intervalles irréguliers | Il manque `oidc-silent-redirect.html` dans les URI de redirection du client web |
| Le client de bureau ne reste jamais connecté | `offline_access` manque dans les portées de ce client : aucun jeton de rafraîchissement n’est délivré |
| Tout le monde a plus de droits que prévu | `GRAPH_ASSIGN_DEFAULT_USER_ROLE` vaut encore `true` alors que les rôles proviennent d’un claim |
| Un second compte vide pour une personne qui en avait déjà un | Le claim de `PROXY_USER_OIDC_CLAIM` n’est pas égal à l’attribut de `PROXY_USER_CS3_CLAIM` |
| Les groupes arrivent mais ne correspondent jamais | *Full group path* est activé dans Keycloak : `finance` arrive sous la forme `/finance` |
| Des personnes qui ne devraient pas avoir de compte s’authentifient | Le provisionnement automatique est activé et l’application n’est pas limitée à un groupe chez le fournisseur |
| Le scanner signale toujours le fournisseur intégré | `OC_EXCLUDE_RUN_SERVICES` n’inclut pas `idp`, ou OpenCloud n’a pas été redémarré |

## Pour aller plus loin {#where-to-go-next}

| Page | Pourquoi |
|:-----|:----|
| [Exploiter OpenCloud dans une infrastructure sécurisée](secure-deployment.md) | Le journal d’audit, le pare-feu et le reste du travail dont cette page n’est qu’une partie |
| [Authentification](authentication.md) | Tous les contrôles d’authentification et OpenID Connect du scanner, en détail |
| [Reverse proxies](reverse-proxy.md) | Terminer TLS devant les deux noms |
| [TLS et certificats](tls.md) | À quoi ressemble un bon certificat, et tous les contrôles de transport |
| [Authentik devant le point de terminaison MCP](authentik.md) | Le même fournisseur, qui protège ce service d’analyse plutôt qu’OpenCloud |
| [Mesures de durcissement](hardening.md) | Ce que signifient réellement `basicAuthDisabled` et les autres |

## Marques et affiliation {#trademarks-and-affiliation}

Ce projet est un projet communautaire indépendant. Il n’est **pas** affilié à
OpenCloud GmbH, ni approuvé, parrainé ou soutenu par elle, et rien sur cette
page ne constitue une déclaration officielle concernant les logiciels
OpenCloud.

« OpenCloud », le logo OpenCloud ainsi que tous les noms et marques associés
appartiennent à leurs propriétaires respectifs. Il en va de même pour Keycloak,
Authentik et Authelia. Ils ne figurent ici que pour identifier les logiciels
décrits sur cette page. Tous les droits sur OpenCloud restent la propriété
d’OpenCloud GmbH.

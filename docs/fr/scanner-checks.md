# Vérifications du scanner

Cet inventaire décrit tout ce qu’une analyse lit sur une instance : les paramètres
consultés, chaque contrôle supplémentaire et son niveau, les observations enregistrées
mais jamais notées, ainsi que les questions auxquelles une analyse externe ne peut pas
répondre.

Le [README principal](../../README.md#the-built-in-scanner) résume le sujet ; les contrôles
sont expliqués par groupe dans
[TLS](tls.md), [CSP](csp.md), [cookies](cookies.md),
[authentification](authentication.md), [partage](sharing.md),
[exposition](exposure.md), [intégration](embedding.md) et
[cycle de vie](lifecycle.md).

<!-- TOC -->
* [Ce que le scanner lit, et ce qu’il ne lit volontairement pas](#what-the-scanner-reads-and-what-it-deliberately-does-not)
  * [Ce que vérifie le scanner](#what-the-scanner-checks)
  * [Lire correctement la version](#reading-the-version-correctly)
  * [Ports de débogage](#debug-ports)
  * [Toutes les adresses résolues](#every-resolved-address)
<!-- TOC -->


## Ce que vérifie le scanner {#what-the-scanner-checks}

Lu directement sur l’instance :

- le produit, `productversion` et l’édition depuis `/status.php`. Les autres
  produits sont refusés, car leurs versions et leurs avis de sécurité ne
  correspondent pas à la base de ce scanner. OpenCloud code en dur
  `maintenance`, `installed` et `needsDbUpgrade` : ces champs ne sont donc pas
  traités comme de véritables contrôles d’état ; voir
  [le point de terminaison de statut](status-php.md).
- les adresses IPv4 et IPv6 vers lesquelles le nom s’est résolu pendant
  l’analyse, indiquées sous `addresses` dans le document de résultat et
  affichées sous **Résolu en** sur une page de résultat web. C’est un contexte,
  jamais un constat, et la liste est vide lorsqu’un nom ne se résout pas ou
  qu’une adresse a été analysée directement.
- les capacités depuis `/ocs/v1.php/cloud/capabilities` (les deux points de
  terminaison sont accessibles sans authentification dans OpenCloud)
- les en-têtes de sécurité `Strict-Transport-Security`,
  `Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`,
  `X-Permitted-Cross-Domain-Policies`, `X-Robots-Tag`, `X-XSS-Protection` et
  `Referrer-Policy`, indiqués sous `setup.headers` - voir
  [`docs/csp.md`](csp.md) pour ce que recherchent les contrôles de
  `Content-Security-Policy`, et pourquoi
- quatre autres en-têtes qu’**aucune** instance OpenCloud n’envoie -
  `Permissions-Policy`, `Cross-Origin-Opener-Policy`,
  `Cross-Origin-Resource-Policy` et `Cross-Origin-Embedder-Policy` - indiqués
  séparément sous `setup.advisoryHeaders`. Un reverse proxy peut ajouter les
  quatre, et l’instance s’en porte mieux, mais leur absence est l’état livré de
  toute instance OpenCloud et non un fait propre à ce déploiement : ils sont
  donc expliqués par `--debug`, jamais comptés comme durcissement manquant,
  jamais signalés par une alerte et jamais autorisés à modifier un code de
  sortie. Voir
  [l’ADR 0028](../../adr/0028-headers-no-opencloud-sends-are-reported-but-never-alerted.md).
  Testez `Cross-Origin-Embedder-Policy: require-corp` avant de le déployer :
  une intégration bureautique qui embarque Collabora ou un hôte WOPI cesse de
  se charger si cette origine n’envoie pas sa propre
  `Cross-Origin-Resource-Policy`
- si `/.well-known/security.txt` indique à quiconque découvre une faille où la
  signaler, sous `securityTxtPublished` dans `setup.advisoryChecks`. OpenCloud
  ne publie pas ce fichier par défaut. Comme pour les en-têtes consultatifs
  ci-dessus, le résultat explique son absence sans affecter la note. Le fichier
  doit contenir le champ `Contact` exigé par la RFC 9116 : une réponse 200 seule
  ne signifie rien sur une instance dont le frontend répond à tout chemin
  inconnu avec sa propre coquille applicative. Voir
  [l’ADR 0034](../../adr/0034-an-advisory-observation-need-not-be-a-header.md)
- si l’en-tête `Strict-Transport-Security` serait réellement accepté pour le
  préchargement par les navigateurs, sous `hstsPreloadEligible` dans le même
  `setup.advisoryChecks`. `hstsPreload` indique déjà si l’en-tête *demande* le
  préchargement ; ce contrôle indique si la demande pourrait aboutir, ce qui
  exige à la fois un max-age d’au moins un an, `includeSubDomains` et `preload`.
  Le proxy d’OpenCloud envoie dix ans et `preload`, mais pas
  `includeSubDomains` : toute instance non modifiée demande donc quelque chose
  que la liste refuse. C’est un fait concernant OpenCloud et non le
  déploiement, d’où une explication sans comptage. L’inscription sur la liste
  n’est volontairement pas mesurée : le seul moyen de la connaître serait
  d’interroger un tiers ou de livrer des dizaines de mégaoctets de liste. Voir
  [l’ADR 0037](../../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md)
- les `hardenings` déduits de ces en-têtes et capacités
- les vulnérabilités connues issues de la [base des avis de sécurité](../../README.md#advisory-database)
  et la note qui en résulte (`0`-`5`)

S’y ajoutent les contrôles supplémentaires (`extraChecks` dans le JSON,
désactivables avec `--no-extra-checks`) :

| Contrôle                                                                                                                                   | Gravité       | Objet                                                                                                       |
|:-------------------------------------------------------------------------------------------------------------------------------------------|:--------------|:------------------------------------------------------------------------------------------------------------|
| `httpsAvailable`, `tlsHandshake`, `tlsProtocol`                                                                                            | critical/high | Instance accessible uniquement en HTTP, TLS défaillant ou protocole antérieur à TLS 1.2                     |
| `tlsCertificate`, `tlsTrusted`                                                                                                             | high/medium   | Certificat expiré, expirant dans moins de `scanner.tls_min_days` jours, ou non reconnu                      |
| `tlsDeprecatedProtocol`                                                                                                                    | high          | Le serveur accepte encore TLS 1.0 ou 1.1, bien qu’il ait négocié une version plus récente avec le scanner   |
| `tlsHostname`                                                                                                                              | high          | Le certificat ne couvre pas le nom demandé                                                                  |
| `tlsChain`                                                                                                                                 | medium        | Il manque un certificat intermédiaire dans la chaîne : elle n’est validée que par les clients qui l’ont déjà en cache |
| `tlsCertificateLifetime`                                                                                                                   | low           | Le certificat est valide plus longtemps que le seuil de 398 jours du scanner                                |
| `tlsCipherSuite`                                                                                                                           | medium        | La suite de chiffrement négociée par cette analyse est faible ou n’offre pas de confidentialité persistante |
| `tlsCertificatePolicy`                                                                                                                     | medium        | Le certificat a une clé faible ou une signature MD5/SHA-1                                                   |
| `tlsAddressParity`                                                                                                                          | medium        | IPv4 et IPv6 présentent des services TLS différents, ou l’une des deux adresses est injoignable              |
| `addressParity`                                                                                                                             | high/medium   | Avec `--all-addresses` : les adresses résolues servent une version, des en-têtes, un durcissement ou un état des comptes de démonstration différents, ou l’une ne répond pas |
| `tlsCaaRecord`                                                                                                                             | low           | Aucun enregistrement DNS CAA ne limite les autorités de certification autorisées à émettre pour ce nom      |
| `tlsDnssec`                                                                                                                                | low           | La zone qui répond pour ce nom n’est pas signée : une adresse falsifiée ne peut donc pas être détectée. Absent, jamais en échec, lorsque le résolveur utilisé ne gère pas DNSSEC |
| `companionAdminConsole`                                                                                                                    | high          | Un backend de collaboration publié sur cette origine répond sur le chemin de sa console d’administration    |
| `companionEditorHttps`                                                                                                                     | high          | Ce backend annonce des adresses d’éditeur en HTTP simple dans son document de découverte WOPI              |
| `cookieSecure`, `cookieHttpOnly`, `cookieSameSite`                                                                                        | high - low    | Un cookie observé n’a pas l’attribut Secure, HttpOnly ou SameSite                                           |
| `cookiePrefix`                                                                                                                             | low           | Aucun cookie observé n’utilise le préfixe de nom `__Host-`/`__Secure-`, ou un cookie revendique un préfixe dont il ne respecte pas les règles |
| `tlsOcspStapling`                                                                                                                          | low           | Aucune réponse OCSP agrafée à la négociation, alors que le certificat désigne un répondeur                  |
| `tlsCertificateTransparency`                                                                                                               | medium        | Un certificat reconnu publiquement ne contient aucun horodatage de certificat signé intégré                 |
| `tlsEarlyData`                                                                                                                             | low           | Les tickets de session du serveur invitent à un envoi TLS 1.3 0-RTT, qui n’a pas de protection contre le rejeu |
| `corsOriginRestricted`                                                                                                                     | critical/medium | N’importe quelle origine peut lire les réponses de l’API ; critical lorsque les identifiants sont autorisés en même temps |
| `traceMethodDisabled`                                                                                                                      | medium        | Le serveur répond à `TRACE` en renvoyant la requête                                                         |
| `forwardedHostIgnored`                                                                                                                     | medium        | Un nom d’hôte fourni par l’appelant revient dans le document de découverte : l’appelant choisit donc où aboutit une connexion |
| `header:<name>`                                                                                                                            | high - low    | L’un des en-têtes ci-dessus est absent ou trop faible                                                       |
| `authentication:/remote.php/dav/files/`, `/graph/v1.0/users`, `/ocs/v1.php/cloud/user`                                                     | critical/high | Un point de terminaison qui doit exiger une authentification a répondu malgré tout                          |
| `exposed:/opencloud.yaml`, `/proxy/server.key`, `/idm/opencloud.boltdb`, `/.env`, `/docker-compose.yml`, `/storage/users/`, `/.git/config` | critical/high | Éléments internes du déploiement publiés par un reverse proxy mal configuré                                 |
| `directoryListing`                                                                                                                         | critical      | Un index de répertoire servi à la place du frontend web                                                     |
| `demoUsersDisabled`                                                                                                                        | critical      | Le fournisseur d’identité intégré accepte encore les comptes de démonstration documentés, dont l’un est administrateur |
| `debugEndpoint:/metrics`, `/config`, `/debug/pprof/`                                                                                       | critical/high | Gestionnaires de débogage accessibles sur l’adresse publique                                                |
| `debugPort:<port>`                                                                                                                         | high          | Un port de débogage de service répond depuis l’extérieur                                                    |
| `backendPortClosed`                                                                                                                        | high          | La même instance OpenCloud est accessible directement sur le port backend 9200, en contournant son reverse proxy |
| `webEmbedDelegatedAuthenticationRestricted`                                                                                                | critical      | L’authentification déléguée par iframe accepte des messages sans origine de confiance explicite             |
| `webEmbedMessageOriginRestricted`                                                                                                          | high          | Les messages d’intégration du client web font confiance à toute origine parente                             |
| `basicAuthDisabled`                                                                                                                        | medium        | Le proxy propose encore l’authentification HTTP Basic                                                       |
| `identityProviderDetected`                                                                                                                 | low           | Ni document de découverte OpenID Connect ni redirection depuis celui-ci : impossible d’établir qui connecte les utilisateurs |
| `reverseProxyDetected`                                                                                                                     | low           | Rien n’indique la présence d’un reverse proxy devant l’instance                                             |
| `versionDisclosure:Server`, `webfingerVersionDisclosure`                                                                                   | low           | Versions exactes divulguées à des appelants non authentifiés                                                |

Un contrôle supplémentaire en échec limite la note (critical -> `D`, high ->
`C`, medium -> `A`, low -> `A+`) ; définissez `scanner.extra_checks_rating: false`
pour les signaler sans toucher à la note. Pour la logique de chaque groupe de
contrôles ci-dessus, consultez [`docs/cookies.md`](cookies.md),
[`docs/authentication.md`](authentication.md),
[`docs/sharing.md`](sharing.md), [`docs/exposure.md`](exposure.md),
[`docs/embedding.md`](embedding.md) et
[`docs/lifecycle.md`](lifecycle.md), en plus de
[`docs/csp.md`](csp.md) et [`docs/tls.md`](tls.md) cités plus haut.

OpenCloud est un binaire Go unique qui sert son frontend web à partir de
ressources intégrées, et ce frontend est une application monopage : les chemins
inconnus renvoient la coquille de l’application avec HTTP 200 au lieu d’une
erreur 404. Un contrôle naïf du type « `/opencloud.yaml` renvoie-t-il 200 ? »
signalerait donc toutes les instances saines. Le scanner demande d’abord un
chemin qui ne peut pas exister et enregistre la réponse générique. Il ne
signale un chemin exposé que lorsque sa réponse diffère de cette référence.

### Qui connecte les utilisateurs {#who-signs-users-in}

L’analyse lit aussi `/.well-known/openid-configuration` - le document de
découverte OpenID Connect, ou la redirection par laquelle l’instance y répond -
pour savoir quel fournisseur d’identité émet ses jetons. Un émetteur sur un autre
hôte signifie qu’un fournisseur externe, tel que Keycloak, Authentik ou
Authelia, se trouve devant l’instance, et le document de résultat l’enregistre :

```json
{"identityProvider": {"detected": true, "external": true,
                      "issuer": "https://id.example.com", "vendor": "Keycloak"}}
```

C’est un contexte, jamais un verdict : utiliser le fournisseur intégré ne fait
rien échouer, et aucun contrôle n’exige de fournisseur externe. Cela atténue
seulement `basicAuthDisabled`, dont la gravité est normalement `medium` et
`low` lorsque la connexion interactive passe par un fournisseur externe.

La détection du fournisseur lit le document de découverte et son en-tête
`Location` sans soumettre de connexion. Le contrôle distinct des comptes de
démonstration, ci-dessous, est la seule sonde qui envoie des identifiants.

Lorsqu’aucun fournisseur n’est trouvé, `identityProviderDetected` échoue avec la
gravité `low` et `--debug` renvoie à [la documentation
d’OpenCloud][opencloud-idp] : la cause habituelle est un reverse proxy qui ne
transmet pas `/.well-known/`.

### Les comptes de démonstration {#the-demo-accounts}

Lorsque le document de découverte désigne le fournisseur *propre* à l’instance
(la gestion d’identité intégrée plutôt qu’un Keycloak ou un Authentik placé
devant elle), l’analyse vérifie en plus si les utilisateurs de démonstration
sont toujours actifs. `IDM_CREATE_DEMO_USERS=true` crée cinq comptes dont les
noms et mots de passe figurent dans [la documentation
d’OpenCloud][opencloud-demo-users], et `dennis` est administrateur. Laissé
actif sur une instance accessible, c’est un compte administrateur dont tout le
monde connaît déjà le mot de passe : `demoUsersDisabled` est donc un constat
`critical`, qui fait échouer le contrôle et limite la note à `D`.

C’est le seul endroit où l’analyse envoie un identifiant, et elle le fait parce
qu’il n’existe aucun autre moyen de voir ces comptes depuis l’extérieur : rien
de ce qu’OpenCloud expose sans authentification ne liste ses utilisateurs. Ce
qui est envoyé est une valeur par défaut publiée, pas une tentative de deviner
le mot de passe de quelqu’un. Seuls les couples documentés sont essayés, et
uniquement auprès du fournisseur propre à l’instance : avec un fournisseur
d’identité externe, les comptes proviennent de celui-ci, le contrôle ne
s’applique pas et aucune connexion n’est jamais envoyée à un tiers. Désactiver
le paramètre ne supprime pas les comptes existants : une instance en échec doit
donc aussi les supprimer.

### Ce qui se trouve devant l’instance {#what-is-in-front-of-the-instance}

`reverseProxy` indique si quelque chose répond avant OpenCloud : un en-tête
`Server` nommant Nginx, Caddy, Cloudflare ou un autre proxy, ou un en-tête que
seul un intermédiaire ajoute, comme `Via`.

```json
{"reverseProxy": {"detected": true, "vendor": "Nginx", "evidence": "Server: nginx"}}
```

`reverseProxyDetected` échoue lorsque rien n’a été trouvé, mais seulement
avec la gravité `low` : Traefik et HAProxy n’annoncent rien par défaut, et
supprimer l’en-tête `Server` est en soi une bonne pratique. L’absence de cet en-tête ne
prouve donc pas l’absence de proxy. Le constat est affiché, mais ne réduit
jamais la note.

`forwardedHostIgnored` pose l’autre question sur cette même frontière : non pas
s’il y a quelque chose devant l’instance, mais si l’instance laisse l’appelant
décider de ce qu’elle considère comme sa propre adresse. L’analyse demande deux
fois `/.well-known/openid-configuration` avec un hôte qui n’existe pas - une
fois comme `Host` de la requête, une fois comme `X-Forwarded-Host` - et vérifie
si cet hôte revient dans le `Location` de la redirection ou dans les champs
`issuer`, `authorization_endpoint`, `token_endpoint`, `end_session_endpoint` ou
`jwks_uri` publiés par le document.

```json
{"id": "forwardedHostIgnored", "severity": "medium", "passed": false,
 "detail": "A host name the caller supplied is published back: X-Forwarded-Host comes back as the issuer it publishes"}
```

Ces URL orientent les requêtes d’authentification. Un nom d’hôte contrôlé par
l’appelant affecte d’abord la réponse de cet appelant, d’où la gravité
`medium`. Un cache partagé ou un proxy qui transmet des valeurs
`X-Forwarded-Host` non fiables peut étendre l’effet à d’autres utilisateurs.
Définissez `OC_URL` et faites fournir les en-têtes transmis par le proxy à
partir de sa propre configuration.

Lorsque seul `Host` revient, comme adresse de redirection, examinez le proxy
avant l’instance : sans serveur par défaut, un nom pour lequel le proxy n’a pas
de site reçoit la réponse du premier site chargé pour ce port, et une
redirection construite à partir de `$host` y reprend l’hôte de la sonde, quelle
que soit la valeur d’`OC_URL`. Un serveur par défaut explicite qui refuse les
noms inconnus corrige le problème - voir
[Pas de serveur par défaut](reverse-proxy.md#mistakes-that-cost-a-grade).

Seule compte une URL vers laquelle un client serait *envoyé*. Un hôte virtuel
par défaut qui refuse un nom inconnu affiche souvent ce nom dans sa page
d’erreur, et chercher ce nom dans le corps de la réponse signalerait le bon
comportement comme un constat. Une instance qui ne publie aucun document de
découverte n’est jugée ni dans un sens ni dans l’autre : avec deux erreurs,
l’analyse n’a rien à évaluer.

### Services alternatifs (HTTP/3) {#alternative-services-http3}

`alternativeServices` enregistre ce que l’instance annonce dans son en-tête
`Alt-Svc`. Une entrée `h3` indique à chaque navigateur d’essayer HTTP/3 sur
**UDP** au port indiqué : un écouteur qu’un pare-feu conçu pour TCP 443 peut ne
pas couvrir, et qu’un reverse proxy peut activer sans que personne l’ait décidé.

```json
{"alternativeServices": {"advertised": true, "http3": true,
  "entries": [{"protocol": "h3", "host": "", "port": 443, "udp": true}],
  "header": "h3=\":443\"; ma=86400"}}
```

C’est une observation, jamais notée : HTTP/3 n’est pas une faiblesse, seulement
un élément dont le pare-feu doit tenir compte. Le plugin affiche une ligne de
détail lorsqu’il en voit une. L’adresse annoncée n’est jamais sondée : c’est la
parole de la cible, pas une origine vers laquelle l’analyse a été dirigée
([ADR 0036](../../adr/0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md)).
`Alt-Svc: clear` n’enregistre aucune annonce, et sans réponse dans laquelle lire
l’en-tête, la clé vaut `null`.

### Connexions échouées (sur demande) {#failed-sign-ins-opt-in}

Avec `--login-throttling` (`COS_LOGIN_THROTTLING`, ou
`scanner.check_login_throttling`), l’analyse envoie six connexions échouées à
la suite, pour un compte aléatoire qui ne peut pas exister, et enregistre si
l’instance les a ralenties - par une réponse HTTP `429` ou un en-tête
`Retry-After` :

```json
{"loginThrottling": {"tested": true, "attempts": 4, "throttled": true,
  "evidence": "HTTP 429, Retry-After: 30", "statuses": [401, 401, 401, 429]}}
```

Cette sonde est désactivée par défaut, n’interroge que le fournisseur
d’identité intégré, s’exécute après toutes les autres sondes pour ne pas masquer
les comptes de démonstration derrière une réponse `429`, et n’est jamais notée :
de nombreux déploiements limitent les tentatives sur une période plus longue ou
à un niveau qu’une courte rafale n’atteint pas. « Non limité » invite donc à
regarder de plus près, ce n’est pas un verdict. Le service web public ne
l’envoie jamais
([ADR 0069](../../adr/0069-login-throttling-is-observed-only-when-the-operator-asks.md)).
Sans l’option, la clé vaut `null`.

### Intégrations bureautiques et d’agenda {#office-and-calendar-integrations}

Deux intégrations sont visibles sans connexion, et toutes deux sont signalées
comme observations plutôt que comme verdicts :

- `/app/list` n’est pas protégé par la politique du proxy d’OpenCloud et nomme
  les fournisseurs d’applications réellement enregistrés dans le registre
  d’applications - Collabora, OnlyOffice, etc. Le bloc `app_providers` du
  document des capacités est codé en dur et n’indique rien : il n’est donc pas
  utilisé.
- `/.well-known/caldav` ne répond par une redirection ou une demande
  d’authentification que lorsqu’un service y est relié, ce qui permet de
  repérer un Radicale derrière le proxy. Une instance non modifiée répond 404.

```json
{"integrations": {"office": {"detected": true, "apps": ["Collabora"], "groupware": false},
                  "calendar": {"detected": true, "advertised": true}}}
```

Aucune ne devient un contrôle et aucune ne peut modifier la note.

Ce que le déploiement *publie* est une autre question, et celle-ci devient un
contrôle. Lorsqu’un reverse proxy sert le backend de collaboration sur
l’origine même de l’instance, `/hosting/discovery` répond avec le document
défini par le protocole WOPI, et deux constats en découlent : la console
d’administration de l’éditeur est-elle accessible (`companionAdminConsole`), et
les adresses d’éditeur qu’il annonce utilisent-elles HTTPS
(`companionEditorHttps`) ?

Le scanner ne sonde que l’origine soumise. Il ne suit pas un nom d’hôte
d’éditeur indiqué dans le document de découverte, car cela permettrait à la
cible de choisir une autre destination de connexion. Un éditeur hébergé
séparément ne reçoit donc aucun constat de ces contrôles. Évaluez ce service
avec des outils adaptés à l’éditeur ; voir [l’ADR
0036](../../adr/0036-a-companion-service-is-probed-only-where-the-scan-was-pointed.md).

### Ce à quoi l’analyse ne répond volontairement pas {#what-the-scan-deliberately-does-not-answer}

- **La journalisation d’audit.** Le service d’audit d’OpenCloud ne fait que
  consommer le bus d’événements interne. Il ne publie aucun point de
  terminaison, et aucun document non authentifié ne le mentionne : il est donc
  impossible d’établir depuis l’extérieur s’il est activé. **Ce n’est pas
  vérifié**, et un rapport sans constat n’en dit rien.
- **Si une intégration est configurée *correctement*.** L’analyse signale qu’un
  fournisseur d’applications est enregistré, ou que quelque chose répond sur le
  chemin CalDAV. Les secrets WOPI, les droits de partage et la configuration
  propre de l’autre service se trouvent derrière une connexion et ne sont pas
  vérifiés.
- **Tout ce qui exige des identifiants.** Aucun formulaire de connexion n’est
  jamais soumis et aucun mot de passe n’est jamais deviné. La seule exception
  concerne les comptes de démonstration ci-dessus : les mots de passe publiés
  par OpenCloud sont envoyés, tels que publiés, au fournisseur d’identité propre
  à l’instance, car c’est le seul moyen de voir depuis l’extérieur si ces
  comptes existent encore.
- **Votre pare-feu, la politique de votre fournisseur d’identité, vos
  sauvegardes.** Tout cela compte davantage que plusieurs des éléments
  ci-dessus, et rien de cela n’est visible par HTTP.

[Exploiter OpenCloud dans une infrastructure sécurisée](secure-deployment.md)
couvre ces vérifications opérationnelles distinctes : politiques du fournisseur
d’identité, journalisation d’audit, règles de pare-feu, consignes aux
utilisateurs et supervision planifiée.

[opencloud-idp]: https://docs.opencloud.eu/docs/admin/configuration/authentication-and-user-management/external-idp
[opencloud-demo-users]: https://docs.opencloud.eu/docs/admin/resources/demo-user/

## Lire correctement la version {#reading-the-version-correctly}

`/status.php` indique trois champs de version, dont deux sont des pièges :

```json
{"version":"0.1.0.0","versionstring":"0.1.0","productversion":"7.4.0"}
```

`version` et `versionstring` sont des valeurs de compatibilité. La version
réelle est `productversion`. Le scanner privilégie ce champ, se rabat sur les
capacités et définit `legacyVersion: true` si seule une valeur de substitution
est disponible. Vérifiez aussi quel champ lisent vos propres scripts de
supervision.

## Ports de débogage {#debug-ports}

Chaque service OpenCloud dispose d’un écouteur de débogage qui sert `/healthz`,
`/readyz`, `/metrics`, `/config` et `/debug/pprof`. `/metrics` contient
`opencloud_proxy_build_info` (la version exacte), `/config` affiche la
configuration effective du service, et `/debug/pprof` permet à n’importe qui de
déclencher un profilage.

Ces écouteurs sont liés à l’interface de bouclage par défaut : un port de
débogage qui répond depuis votre hôte de supervision est donc un vrai constat,
généralement un conteneur qui a publié toute la plage de ports. Le scanner sonde
les cinq plus révélateurs :

| Port | Service  |
|:-----|:---------|
| 9205 | proxy    |
| 9141 | frontend |
| 9124 | graph    |
| 9134 | idp      |
| 9239 | idm      |

Chaque sonde est une seule connexion TCP avec un délai d’attente de trois
secondes : un hôte protégé par un pare-feu coûte donc jusqu’à 15 secondes.
Désactivez les sondes avec `--no-debug-ports`, exécutez-les en parallèle avec
[`--concurrency`](#speeding-the-scan-up), ou ajustez-les :

```yaml
scanner:
  check_debug_ports: true
  debug_ports: [9205, 9141]
  debug_port_timeout: 1
```

### Accélérer l’analyse {#speeding-the-scan-up}

Une analyse passe presque tout son temps à attendre les réponses de
l’instance : une vingtaine de requêtes HTTP et cinq connexions TCP, l’une après
l’autre. `scanner.concurrency` exécute ces sondes en parallèle pour l’analyse
d’un seul hôte ; l’augmenter raccourcit nettement une exécution, au prix d’une
rafale de requêtes parallèles vers l’instance, et l’effet est le plus sensible
lorsque les sondes des ports de débogage butent sur un pare-feu qui absorbe les
connexions. `--concurrency` contrôle en revanche le plafond externe de workers
par hôte décrit dans
[Vérifier plusieurs hôtes](../../README.md#checking-multiple-hosts).

Ce paramètre ne change que la durée, jamais le verdict : le document de
résultat liste les mêmes constats dans le même ordre, quelle que soit la valeur.
Les valeurs supérieures à `32` sont ramenées à `32`. Il peut aussi être défini
une fois pour tous les hôtes :

```yaml
scanner:
  concurrency: 8
```

## Toutes les adresses résolues {#every-resolved-address}

Une analyse se connecte au nom une seule fois et voit l’adresse que le résolveur
a placée en premier. Pour un nom derrière un groupe de nœuds, c’est un seul
nœud, et le nœud qui a manqué un déploiement de configuration - pas de HSTS,
comptes de démonstration toujours actifs, version plus ancienne - reste
invisible. [`tlsAddressParity`](tls.md) ne compare que l’identité TLS d’une
adresse IPv4 et d’une adresse IPv6, que plusieurs nœuds derrière un même
certificat partagent quoi qu’ils servent.

`--all-addresses` (`COS_ALL_ADDRESSES`, `scanner.check_all_addresses`) répète
sur chaque adresse résolue, l’une après l’autre, la partie de l’analyse qu’un
déploiement modifie :

- la version dans `/status.php` (ou dans le document des capacités),
- les en-têtes de sécurité notés, comparés par verdict et non par valeur, pour
  qu’un nonce CSP ne compte pas comme une différence,
- les mesures de durcissement lues sur la page racine, les capacités, la
  demande d’authentification et le fournisseur d’identité,
- si un compte de démonstration documenté permet de se connecter.

Ce que les nœuds partagent - chaîne de certificats, CAA, DNSSEC, ports de
débogage - n’est pas redemandé. Chaque requête conserve le nom d’hôte dans
`Host` et SNI ; seule l’adresse de connexion change, et les adresses sont la
réponse du résolveur pour ce nom, jamais une information fournie par
l’instance. Les adresses IPv6 sont ignorées lorsque `scanner.ipv6_enabled` est
désactivé.

Le résultat est `addressParity`, avec la première adresse comme référence :

| Différence sur une autre adresse                       | Gravité                                   |
|:-------------------------------------------------------|:------------------------------------------|
| Un compte de démonstration s’y connecte, contrairement à la référence | celle de `demoUsersDisabled` seul |
| Une version différente                                 | high                                      |
| Un en-tête ou une mesure de durcissement réussit/échoue | medium                                   |
| L’adresse se résout mais ne répond pas                 | medium                                    |

Les en-têtes et contrôles exemptés ne sont pas comparés. Un nom avec une seule
adresse ne donne lieu à aucun constat - une absence, pas une réussite - ni à
aucune requête supplémentaire. Ce que chaque adresse a servi figure dans le
document de résultat sous `addressObservations`.

Cette option est désactivée par défaut : environ une douzaine de requêtes par
adresse, dont une connexion de démonstration. Elle voit ce que voit le DNS :
des nœuds derrière une seule adresse de répartiteur de charge, un résolveur qui
renvoie un sous-ensemble tournant ou un GeoDNS qui répond selon l’emplacement de
l’hôte de supervision limitent tous ce qui peut être comparé. Le service web
public ne l’exécute jamais
([ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md)).

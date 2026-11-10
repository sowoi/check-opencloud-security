# Authentification et comptes de démonstration

Le scanner vérifie l'accès aux points de terminaison protégés, l'authentification HTTP Basic,
les comptes de démonstration documentés et les paramètres publiés dans les capacités OpenCloud
et les documents de découverte OpenID Connect. Il ne devine pas les identifiants. Le contrôle
des comptes de démonstration utilise uniquement les identifiants publiés ci-dessous ; voir les
[limites de l’analyse](scanner-checks.md#what-the-scan-deliberately-does-not-answer) pour le
périmètre complet.

<!-- TOC -->
* [Authentification : ce que vérifie ce scanner, et pourquoi](#authentication-what-this-scanner-checks-and-why)
  * [1. Les points de terminaison protégés exigent-ils vraiment une session : `authentication:<path>`](#1-do-protected-endpoints-actually-require-a-session-authenticationpath)
  * [2. Le proxy propose-t-il encore l’authentification HTTP Basic : `basicAuthDisabled`](#2-does-the-proxy-still-offer-http-basic-authentication-basicauthdisabled)
  * [3. Les comptes de démonstration documentés permettent-ils encore de se connecter : `demoUsersDisabled`](#3-do-the-documented-demo-accounts-still-sign-in-demousersdisabled)
  * [4. La recherche de comptes est-elle limitée aux groupes partagés : `userEnumerationRestricted`](#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted)
  * [5. La politique de mot de passe des liens est-elle assez stricte : `passwordPolicyEnforced`](#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced)
  * [5a. Exige-t-elle encore plus qu’une longueur : `passwordPolicyComplexity`](#5a-does-it-still-ask-for-more-than-length-passwordpolicycomplexity)
  * [6. Le fournisseur d’identité est-il seulement identifiable : `identityProviderDetected`](#6-can-the-identity-provider-be-found-at-all-identityproviderdetected)
  * [7. Ce que le document de découverte indique sur la protection de la connexion](#7-what-the-discovery-document-says-about-how-sign-in-is-protected)
  * [Les autres champs de ce document, et pourquoi aucun n’est vérifié](#what-else-is-in-that-document-and-why-none-of-it-is-checked)
  * [Gravité et effet sur la note](#severity-and-rating-impact)
<!-- TOC -->


## 1. Les points de terminaison protégés exigent-ils vraiment une session : `authentication:<path>` {#1-do-protected-endpoints-actually-require-a-session-authenticationpath}

Trois points de terminaison qui ne doivent jamais renvoyer de contenu à une
requête non authentifiée sont interrogés sans identifiants :

| Chemin                         | Gravité  |
|:-------------------------------|:---------|
| `/remote.php/dav/files/`       | critical |
| `/graph/v1.0/users`             | critical |
| `/ocs/v1.php/cloud/user`        | high     |

Une réponse HTTP `401`, `403`, `405` ou `501`, une redirection vers une page de
connexion ou une réponse `404` comptent toutes comme « authentification
exigée ». `405`/`501` apparaissent lorsqu’un reverse proxy, et non OpenCloud
lui-même, répond à un `GET` sur une collection WebDAV ; `404` couvre un proxy
qui masque entièrement le chemin au lieu de demander une authentification.
Toute autre réponse - avant tout un `200` contenant les données que ce chemin
doit protéger - fait échouer le contrôle. Un point de terminaison injoignable
est considéré comme réussi : une panne réseau ne prouve pas que le point de
terminaison est ouvert, et ce scanner préfère se taire plutôt que de fabriquer
un constat à partir d’un délai d’attente dépassé.

**En cas d’échec :** interrogez vous-même le chemin signalé et regardez ce qui
répond réellement. L’explication habituelle est un cache, un CDN ou une règle
de proxy mal configurée qui sert sa propre page d’erreur devant OpenCloud. Un
point de terminaison réellement accessible sans session est un incident en
cours, pas une lacune de durcissement : renouvelez tout ce que la réponse a
exposé et corrigez immédiatement le routage.

## 2. Le proxy propose-t-il encore l’authentification HTTP Basic : `basicAuthDisabled` {#2-does-the-proxy-still-offer-http-basic-authentication-basicauthdisabled}

Le scanner demande à l’instance le défi `WWW-Authenticate` d’un point de
terminaison protégé. Un défi `Basic` signifie `PROXY_ENABLE_BASIC_AUTH=true` :
un nom d’utilisateur et un mot de passe peuvent être rejoués à chaque requête
sans jamais passer par le fournisseur d’identité, ce qui contourne
l’authentification unique et tout second facteur qu’il impose.

Ce n’est pas traité comme une simple erreur, car l’alternative est souvent
pire en pratique : les clients CalDAV, CardDAV et la plupart des clients WebDAV
ne savent pas utiliser OpenID Connect et n’ont aucun autre moyen de
s’authentifier. C’est pourquoi la gravité est `medium` et non `critical`, et
`low` dès qu’un fournisseur d’identité externe gère de façon confirmée la
connexion interactive (voir [Qui connecte les utilisateurs](scanner-checks.md#who-signs-users-in)) :
les mots de passe de comptes protégés par ce fournisseur ne sont alors pas ceux
qui sont rejoués ici.

**Correction :** définissez `PROXY_ENABLE_BASIC_AUTH=false` (la valeur par
défaut) si rien n’en a besoin. Si un client d’agenda, de contacts ou WebDAV en
a besoin, laissez-la active et donnez à ces clients des jetons d’application
plutôt que les mots de passe des comptes : ce qui est rejoué à chaque requête
peut alors être révoqué séparément et n’est jamais l’identifiant de
l’authentification unique.

## 3. Les comptes de démonstration documentés permettent-ils encore de se connecter : `demoUsersDisabled` {#3-do-the-documented-demo-accounts-still-sign-in-demousersdisabled}

`IDM_CREATE_DEMO_USERS=true` crée sur une nouvelle instance cinq comptes - dont
un administrateur - dont les noms et mots de passe figurent dans
[la documentation d’OpenCloud][opencloud-demo-users]. Ce contrôle ne s’exécute
qu’une fois que l’analyse a établi que le fournisseur d’identité *propre* à
l’instance gère la connexion (un Keycloak, Authentik ou Authelia externe n’a
pas de tels comptes à tester). Il envoie à ce fournisseur exactement ces
couples publiés : rien n’est deviné et rien n’est envoyé à un tiers.

Laissé actif au-delà d’une phase d’évaluation, c’est un constat `critical` :
il s’agit d’un compte administrateur dont le mot de passe est public, et il
limite à lui seul la note à `D`, quels que soient les autres résultats de
l’analyse.

**Correction :** définissez `IDM_CREATE_DEMO_USERS=false` **et** supprimez les
comptes déjà créés : désactiver le paramètre ne les supprime pas. Partout où
ce contrôle échoue, considérez l’instance comme compromise tant que le compte
administrateur n’a pas été supprimé ou doté d’un vrai mot de passe : ces
identifiants ne sont pas secrets, ils sont publiés.

## 4. La recherche de comptes est-elle limitée aux groupes partagés : `userEnumerationRestricted` {#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted}

Le document des capacités d’OpenCloud indique si la recherche d’utilisateurs
est limitée aux membres d’un groupe partagé. L’état restreint est codé en dur
dans les versions actuelles : ce contrôle réussit donc sur pratiquement toutes
les instances. Il est conservé pour qu’une future version rendant ce paramètre
configurable soit repérée dès qu’elle annonce autre chose que l’état
restreint.

**En cas d’échec :** il n’existe actuellement aucun paramètre à modifier. Le
constat décrit la configuration propre d’OpenCloud, pas un réglage vers lequel
les indications de correction de `--debug` pourraient vous orienter.

## 5. La politique de mot de passe des liens est-elle assez stricte : `passwordPolicyEnforced` {#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced}

Le scanner lit `password_policy.min_characters` dans le document des
capacités et le compare à 8. Cette valeur régit les mots de passe qu’un
utilisateur peut définir sur un **lien de partage public**, pas ceux des
comptes du fournisseur d’identité. Consultez [Partage par lien public](sharing.md)
pour les contrôles qui déterminent si un lien exige un mot de passe.

**Correction :** définissez `OC_PASSWORD_POLICY_DISABLED=false` et
`OC_PASSWORD_POLICY_MIN_CHARACTERS` à `8` ou plus (`8` est déjà la valeur par
défaut : un échec signifie donc généralement que quelqu’un l’a abaissée).
`OC_PASSWORD_POLICY_MIN_{LOWERCASE,UPPERCASE,DIGITS,SPECIAL}_CHARACTERS` et une
liste de mots de passe interdits la renforcent encore - voir
[la documentation sur la politique de mot de passe des liens][link-password].

## 5a. Exige-t-elle encore plus qu’une longueur : `passwordPolicyComplexity` {#5a-does-it-still-ask-for-more-than-length-passwordpolicycomplexity}

Une longueur minimale ne suffit pas à faire une politique de mot de passe. La
politique par défaut d’OpenCloud exige aussi **une minuscule, une majuscule,
un chiffre et un caractère spécial**, et chacun de ces minimums est un
paramètre que quelqu’un peut ramener à zéro. Une politique de douze caractères
dont les quatre minimums ont été abaissés accepte `aaaaaaaaaaaa`, ce qui
satisfait `passwordPolicyEnforced` et rien d’autre.

Les quatre champs `min_*_characters` sont lus dans le même document des
capacités, et le contrôle réussit lorsque chacun vaut au moins 1.

**Il s’agit volontairement d’un second indicateur plutôt que d’un
`passwordPolicyEnforced` plus strict.** L’ancien indicateur répond à « existe-t-il
une politique, et est-elle assez longue ? » ; celui-ci répond à « est-ce encore
la politique livrée avec OpenCloud ? ». Les fusionner changerait le sens d’une
alerte existante sans changer son nom.

**Signalé uniquement lorsque l’instance publie les quatre minimums.** Une
politique désactivée n’en publie aucun - ce cas fait échouer
`passwordPolicyEnforced`, pas celui-ci - et une mesure absente reste une
inconnue au lieu de devenir un échec, comme partout ailleurs dans l’analyse.

**Correction :** remettez `OC_PASSWORD_POLICY_MIN_LOWERCASE_CHARACTERS`,
`OC_PASSWORD_POLICY_MIN_UPPERCASE_CHARACTERS`,
`OC_PASSWORD_POLICY_MIN_DIGITS` et
`OC_PASSWORD_POLICY_MIN_SPECIAL_CHARACTERS` à `1` ou plus. Chacun vaut déjà `1`
par défaut : sur une instance qui échoue à ce contrôle, ils ont donc été
abaissés.

## 6. Le fournisseur d’identité est-il seulement identifiable : `identityProviderDetected` {#6-can-the-identity-provider-be-found-at-all-identityproviderdetected}

Tous les contrôles ci-dessus demandent si un identifiant est accepté. Celui-ci
pose la question préalable - *qui émet les jetons ?* - et y répond en lisant
une seule fois `/.well-known/openid-configuration`, sans suivre les
redirections :

- une réponse `200` contenant du JSON : le champ `issuer` est retenu ;
- une redirection : l’en-tête `Location` est résolu par rapport à l’instance et
  retenu à la place, ce qui permet de reconnaître un proxy qui confie le chemin
  well-known à un fournisseur externe ;
- toute autre réponse, ou un émetteur qui n’est pas une URL `http(s)` absolue
  avec un nom d’hôte : l’indicateur échoue.

Rien n’est soumis pour le découvrir. Aucun formulaire de connexion n’est rempli
et aucun identifiant n’est envoyé : déterminer qui connecte les utilisateurs ne
doit pas devenir une tentative de connexion.

Un échec vient bien plus souvent d’un **proxy qui ne transmet pas
`/.well-known/`** que d’une instance sans aucune connexion. C’est pourquoi il ne
limite jamais la note.

L’émetteur trouvé est aussi enregistré comme contexte, pas comme verdict. Un
émetteur situé sur un autre hôte que l’instance est signalé comme fournisseur
**externe** - Keycloak, Authentik ou Authelia devant OpenCloud - et l’éditeur
est nommé pour que le résultat puisse renvoyer aux avis de sécurité de ce
projet. Utiliser le fournisseur intégré d’OpenCloud n’est pas un constat :
aucune des deux configurations n’est exigée, et aucune ne fait échouer quoi que
ce soit.

**En cas d’échec :** vérifiez que le reverse proxy transmet `/.well-known/` au
service qui émet les jetons - voir [Reverse proxies](reverse-proxy.md). Si la
connexion n’est réellement pas configurée, OpenCloud fournit son propre
fournisseur et peut être relié à un fournisseur externe.

## 7. Ce que le document de découverte indique sur la protection de la connexion {#7-what-the-discovery-document-says-about-how-sign-in-is-protected}

La requête ci-dessus a déjà été faite. Le document qu’elle renvoie est une
preuve publique au sens de l’[ADR 0022](../../adr/0022-identity-provider-versions-require-public-evidence.md) -
non authentifié, en lecture seule et destiné à être public - et quatre de ses
champs indiquent quelque chose sur quoi un opérateur peut agir. Les lire ne
coûte **aucune requête HTTP supplémentaire** : la réponse qui a fourni
l’émetteur fournit aussi les quatre champs.

| Indicateur | Champ | Échoue lorsque |
|:--|:--|:--|
| `oidcPkceSupported` | `code_challenge_methods_supported` [^rfc8414] | `S256` ne figure pas parmi les méthodes |
| `oidcImplicitFlowDisabled` | `response_types_supported` | un type renvoie un jeton depuis le point de terminaison d’autorisation (`token`, `id_token`) |
| `oidcSigningAlgorithmStrong` | `id_token_signing_alg_values_supported` | il contient `none` ou un algorithme `HS` |
| `oidcEndpointsUseHttps` | `issuer` et les URL des points de terminaison | l’une d’elles est une adresse `http://` |

[^rfc8414]: Les fournisseurs le publient dans le document de découverte, mais
    ce champ est défini par [OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414.html#section-2)
    et non par OpenID Connect Discovery : un fournisseur purement OIDC peut donc
    légitimement l’omettre.

**Chacun est ignoré lorsque le document ne publie pas le champ.** C’est la même
règle que pour `passwordPolicyComplexity` : une mesure absente est une
inconnue, jamais un échec. Cela compte encore plus ici, car le fournisseur
intégré d’OpenCloud omet entièrement `code_challenge_methods_supported` :
traiter cette absence comme « pas de PKCE » ferait échouer toutes les instances
non modifiées pour quelque chose que leur opérateur ne peut pas changer.

**`oidcImplicitFlowDisabled` n’est signalé que pour un fournisseur externe.**
Le fournisseur intégré d’OpenCloud ([libregraph/lico][lico]) publie
`response_types_supported` sous la forme `id_token token`, `id_token`,
`code id_token` et `code id_token token` - flux implicite et hybride, sans
`code` seul - et rien de cela n’est configurable. Un constat sur lequel un
opérateur ne peut pas agir est pire que pas de constat : il n’est donc émis que
là où l’on peut agir, devant Keycloak, Authentik ou Authelia, où les flux sont
réellement des options distinctes. [Sécuriser un déploiement](secure-deployment.md#keycloak)
vous demande déjà d’y exiger PKCE et le flux par code ; ce contrôle vérifie
enfin que vous l’avez fait.

**`oidcEndpointsUseHttps` n’est mesuré que lorsque l’instance elle-même a
répondu en HTTPS.** Une instance analysée en HTTP simple publie des points de
terminaison `http://` parce que c’est ainsi qu’elle a été interrogée, et le
signaler répéterait ce que `httpsEnforced` dit déjà une fois, au bon endroit.
Le constat utile est le désaccord : une instance HTTPS dont le fournisseur
annonce encore `http://`, c’est-à-dire un fournisseur placé derrière un proxy
de terminaison TLS à qui l’on n’a jamais indiqué son URL publique.

**Pourquoi ces quatre-là et pas le cinquième évident.** `none` dans
`id_token_signing_alg_values_supported` signifie qu’un jeton d’identité non
signé est acceptable : n’importe qui peut donc en écrire un. Un algorithme `HS`
signe avec le secret client ; or les clients d’OpenCloud sont des clients
publics qui ne peuvent pas garder de secret, si bien que toute partie qui le
détient peut forger un jeton pour n’importe quel utilisateur. Le fournisseur
intégré d’OpenCloud signe avec `PS256` et réussit ce contrôle.

## Les autres champs de ce document, et pourquoi aucun n’est vérifié {#what-else-is-in-that-document-and-why-none-of-it-is-checked}

Le document de découverte publie bien plus que ce que lisent ces quatre
indicateurs. Vérifié par rapport à `oidc/provider/provider.go`
(`InitializeMetadata`) de [libregraph/lico][lico], c’est-à-dire ce que sert le
fournisseur intégré d’OpenCloud :

| Champ | Pourquoi il n’y a pas de contrôle |
|:--|:--|
| `token_endpoint_auth_methods_supported` | Le candidat évident, et pourtant pas un constat. Ne proposer que `client_secret_basic` n’est pas une faiblesse, et `none` - la valeur qui semble alarmante - est exactement ce dont ont besoin les clients publics d’OpenCloud (bureau, mobile et web). lico publie les deux. Un indicateur ici ne se déclencherait jamais, ou se déclencherait sur toutes les instances. |
| `request_object_signing_alg_values_supported` | lico y inclut `none`, mais ce champ régit les *objets de requête* signés, pas les jetons d’identité. Un objet de requête non signé n’est pas un jeton non signé, et les clients d’OpenCloud n’envoient aucun objet de requête. |
| `scopes_supported`, `claims_supported` | Indiquent ce que l’on peut demander au fournisseur, pas ce qu’il accorde. Les portées autorisées pour un *client* relèvent d’une configuration propre à chaque client, que le document ne montre pas. |
| `subject_types_supported` | lico publie `public` et rien d’autre. `pairwise` est une fonction de confidentialité pour les fournisseurs multi-locataires ; l’exiger d’un déploiement OpenCloud à locataire unique ne serait que du bruit. |
| `registration_endpoint` | Sa présence ne signifie pas un enregistrement dynamique ouvert : le document ne dit pas si l’enregistrement exige un jeton d’accès initial. Le deviner reviendrait à affirmer avec assurance à partir d’une preuve faible, ce que l’[ADR 0022](../../adr/0022-identity-provider-versions-require-public-evidence.md) existe précisément pour interdire. |

## Gravité et effet sur la note {#severity-and-rating-impact}

`authentication:<path>` et `demoUsersDisabled` sont des `extraChecks`,
signalés et limitant la note chaque fois qu’ils s’exécutent, avec les gravités
indiquées plus haut - voir le tableau des contrôles supplémentaires dans
[Contrôles du scanner](scanner-checks.md#what-the-scanner-checks).
`basicAuthDisabled`, `userEnumerationRestricted`, `passwordPolicyEnforced`,
`passwordPolicyComplexity`, `identityProviderDetected` et les quatre
indicateurs `oidc*` sont des indicateurs de durcissement, signalés uniquement
avec `--check-hardening` (ou toujours dans le résultat web). Un indicateur de
durcissement en échec ne limite pas la note à lui seul : il fait passer un
résultat Icinga autrement `OK` à `WARNING` et figure sur la ligne
`hardenings_missing` - voir [Vérifications de durcissement](../../README.md#hardening-checks).

[opencloud-demo-users]: https://docs.opencloud.eu/docs/admin/resources/demo-user/
[link-password]: https://docs.opencloud.eu/docs/admin/configuration/link-password-policy
[lico]: https://github.com/libregraph/lico

# Vérifications de durcissement

Ce guide explique les identifiants de durcissement utilisés dans les alertes : ce que
vérifie chaque contrôle, quel paramètre permet de le corriger et quand une exclusion est
justifiée. Il signale aussi les valeurs codées en dur qu’un opérateur OpenCloud ne peut pas
modifier.

`--debug` affiche la même explication à côté de chaque constat. Le
[README principal](../README.md#hardening-checks) décrit la façon dont ces mesures
apparaissent dans la sortie et les métriques.

<!-- TOC -->
* [Les mesures de durcissement une par une](#hardening-measures-one-by-one)
  * [Signification de chaque mesure](#what-each-measure-means)
  * [Mesures qui ne sont pas des paramètres](#measures-that-are-not-settings)
  * [Accepter un constat que vous ne corrigerez pas](#accepting-a-finding-you-are-not-going-to-fix)
<!-- TOC -->


## Signification de chaque mesure {#what-each-measure-means}

| Durcissement                   | Signification d’un échec                                                                                                                                                                                                                                                                                                                         | Paramètre à modifier                                                                                                                                           |
|:-------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|:---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `basicAuthDisabled`            | L’instance accepte l’authentification HTTP Basic : les identifiants peuvent être rejoués à chaque requête et l’authentification unique (avec un éventuel second facteur) est contournée. C’est souvent voulu : les clients CalDAV, CardDAV et WebDAV ne savent pas utiliser OpenID Connect. C’est pourquoi la gravité est `medium`, et `low` lorsqu’un fournisseur d’identité externe gère la connexion interactive. | [`PROXY_ENABLE_BASIC_AUTH=false`][proxy-env] si rien n’en a besoin ; sinon, conservez-la et donnez à ces clients des jetons d’application plutôt que les mots de passe des comptes. |
| `cspWithoutUnsafeInline`       | La `Content-Security-Policy` contient `'unsafe-inline'` : du balisage injecté peut donc s’exécuter. **C’est la valeur par défaut livrée avec OpenCloud** - voir la remarque ci-dessous.                                                                                                                                                          | [`PROXY_CSP_CONFIG_FILE_LOCATION`][proxy-env] pointant vers votre propre `csp.yaml` (ou `PROXY_CSP_CONFIG_FILE_OVERRIDE_LOCATION` pour remplacer entièrement la valeur par défaut). |
| `publicLinkPasswordEnforced`   | Des liens publics peuvent être créés sans mot de passe : l’URL seule donne alors accès. OpenCloud impose un mot de passe aux liens en lecture seule, mais pas aux liens modifiables.                                                                                                                                                             | [`OC_SHARING_PUBLIC_SHARE_MUST_HAVE_PASSWORD=true`][sharing-env] et `OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD=true`.                               |
| `passwordPolicyEnforced`       | Les mots de passe des liens publics peuvent compter moins de 8 caractères. (Cette politique concerne les mots de passe des liens, pas ceux des comptes, qui relèvent de votre fournisseur d’identité.)                                                                                                                                           | [`OC_PASSWORD_POLICY_MIN_CHARACTERS`][link-password] (par défaut `8`), avec les paramètres associés `MIN_LOWERCASE`/`MIN_UPPERCASE`/`MIN_DIGITS`/`MIN_SPECIAL_CHARACTERS`. |
| `passwordPolicyComplexity`     | La politique de mot de passe des liens n’exige plus une minuscule, une majuscule, un chiffre et un caractère spécial. Chacun vaut `1` par défaut : un échec signifie donc que quelqu’un a abaissé l’une de ces valeurs. Une politique désactivée est signalée comme inconnue, pas comme un échec.                                                  | [`OC_PASSWORD_POLICY_MIN_LOWERCASE_CHARACTERS`][link-password] et les paramètres associés `MIN_UPPERCASE`/`MIN_DIGITS`/`MIN_SPECIAL_CHARACTERS`, à remettre à `1` ou plus. |
| `hstsLongMaxAge`               | `Strict-Transport-Security` porte un `max-age` inférieur à un an.                                                                                                                                                                                                                                                                                | Aucun dans OpenCloud : son proxy envoie dix ans, donc une valeur courte vient d’un reverse proxy placé devant lui.                                              |
| `hstsPreload`                  | Le même en-tête n’a pas de directive `preload` : la toute première requête vers l’hôte n’est donc pas protégée.                                                                                                                                                                                                                                  | Aucun dans OpenCloud : là encore, un reverse proxy réécrit l’en-tête. N’ajoutez `preload` que lorsque tous les sous-domaines sont exclusivement en HTTPS.      |
| `hstsPreloadEligible`          | L’en-tête ne serait pas accepté pour le préchargement par les navigateurs : la liste exige à la fois un `max-age` d’au moins un an, `includeSubDomains` *et* `preload`, et le proxy d’OpenCloud omet `includeSubDomains`. `hstsPreload` ci-dessus indique que la directive est présente ; cette mesure indique qu’une demande serait refusée. Elle figure sous `setup.advisoryChecks` et **ne déclenche jamais d’alerte**, car le manque vient de ce que livre OpenCloud. L’inscription effective sur la liste n’est pas mesurée - voir l’[ADR 0037](../../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md). | Ajoutez `includeSubDomains` au niveau du reverse proxy, puis soumettez le domaine sur [hstspreload.org](https://hstspreload.org/) : l’acceptation exige les deux. Vérifiez d’abord que tous les sous-domaines sont exclusivement en HTTPS. |
| `publicLinkExpirationEnforced` | Cela ne dit rien de votre instance : OpenCloud code cette capacité en dur à `false`. **Ne déclenche jamais d’alerte** - voir ci-dessous.                                                                                                                                                                                                         | Il n’en existe aucun.                                                                                                                                          |
| `userEnumerationRestricted`    | La recherche de comptes n’est pas limitée aux groupes partagés. OpenCloud code l’état restreint en dur : ce contrôle réussit donc partout.                                                                                                                                                                                                       | Il n’en existe aucun.                                                                                                                                          |
| `oidcPkceSupported`            | Le document de découverte du fournisseur d’identité publie `code_challenge_methods_supported` sans `S256` : le flux par code d’autorisation fonctionne donc sans PKCE. Signalé uniquement lorsque le fournisseur publie ce champ : le fournisseur intégré d’OpenCloud l’omet, et une réponse absente n’est pas un échec.                          | Exigez PKCE avec `S256` auprès du fournisseur : *Proof Key for Code Exchange* dans Keycloak, client public avec PKCE obligatoire dans Authentik, `require_pkce` dans Authelia. |
| `oidcImplicitFlowDisabled`     | `response_types_supported` propose encore un type qui renvoie un jeton depuis le point de terminaison d’autorisation (`token` ou `id_token`), c’est-à-dire le flux implicite. **Fournisseurs externes uniquement** : le fournisseur intégré d’OpenCloud propose ces types et ne peut pas être reconfiguré.                                         | Limitez le client au flux par code d’autorisation ; dans Keycloak, activez le Standard flow et désactivez l’Implicit flow.                                      |
| `oidcSigningAlgorithmStrong`   | `id_token_signing_alg_values_supported` propose `none` (un jeton d’identité non signé que n’importe qui peut écrire) ou un algorithme `HS` (signé avec le secret client, qu’un client public ne peut pas garder secret). Le fournisseur intégré d’OpenCloud signe avec `PS256` et réussit ce contrôle.                                            | Ne proposez que des algorithmes asymétriques - `RS256`, `PS256`, `ES256` ou `EdDSA` - et retirez `none` et la famille `HS`.                                     |
| `oidcEndpointsUseHttps`        | Un point de terminaison du document de découverte est une adresse `http://`. Vérifié uniquement lorsque l’instance elle-même a répondu en HTTPS : une instance analysée en HTTP simple publie `http://` parce que c’est ainsi qu’elle a été interrogée, ce que `httpsEnforced` signale déjà.                                                      | Publiez le fournisseur en HTTPS et définissez son émetteur (issuer) sur l’adresse `https://` ; un émetteur `http://` est généralement un fournisseur placé derrière un proxy de terminaison TLS à qui l’on n’a jamais indiqué son URL publique. |

[proxy-env]: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
[sharing-env]: https://docs.opencloud.eu/docs/dev/server/services/sharing/environment-variables
[frontend-env]: https://docs.opencloud.eu/docs/dev/server/services/frontend/environment-variables
[link-password]: https://docs.opencloud.eu/docs/admin/configuration/link-password-policy

## Mesures qui ne sont pas des paramètres {#measures-that-are-not-settings}

Deux des lignes ci-dessus échappent à toute action :

- **`publicLinkExpirationEnforced`** est signalé à `false` par *toutes* les
  instances OpenCloud. La capacité est une constante codée en dur dans le service
  frontend, pas une valeur de configuration : il n’y a donc aucune variable à
  définir et aucune version qui réussisse ce contrôle.
- **`userEnumerationRestricted`** est le même cas, en sens inverse : l’état
  restreint est codé en dur, donc le contrôle réussit toujours.

Ces deux mesures restent enregistrées dans le document de résultat, car
l’observation est réelle, mais elles sont **exclues de la ligne « Missing
hardening », de la métrique `hardenings_missing` et du webhook**. Un
avertissement qu’aucun réglage ne permet de corriger risque de détourner
l’attention des problèmes qui peuvent être corrigés. `--debug` les liste toujours, avec
l’explication.

`cspWithoutUnsafeInline` est une version atténuée du même problème : la **CSP
par défaut d’OpenCloud contient `'unsafe-inline'`**, si bien qu’elle échoue sur
une instance non modifiée. Celle-ci *peut* être changée : elle est donc signalée
plutôt qu’excusée. Sachez toutefois que l’interface web s’appuie actuellement
sur des scripts et des styles en ligne : une politique stricte risque de casser
l’interface ainsi que les services bureautiques ou d’identité connectés. Testez
avant de la déployer. Consultez [`docs/csp.md`](csp.md) pour l’explication
complète des deux contrôles CSP.

Les lignes issues des capacités n’apparaissent que si l’instance publie
effectivement la capacité correspondante : une version plus ancienne n’accumule
donc pas de constats fantômes.

## Accepter un constat que vous ne corrigerez pas {#accepting-a-finding-you-are-not-going-to-fix}

Certains constats sont réels mais ne peuvent pas être traités dans votre
environnement : une CSP que vous ne pouvez pas durcir sans casser l’interface
web, un en-tête HSTS géré par votre reverse proxy, ou une authentification Basic
dont un outil de migration a réellement besoin. Laissés tels quels, ils
abaissent la note et maintiennent le contrôle en jaune en permanence, et l’on
cesse de regarder un contrôle qui ne change jamais.

`--ignore-hardening` accepte un constat par son nom. La note est recalculée sans
lui : accepter un constat change donc réellement la note :

```bash
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening cspWithoutUnsafeInline \
    --ignore-hardening basicAuthDisabled
```

L’option peut être répétée, accepte aussi une liste séparée par des virgules et
comprend les jokers de type shell pour les identifiants qui contiennent un
chemin ou un port :

```bash
--ignore-hardening 'debugPort:*,exposed:/status.php'
```

Elle s’applique aux mesures de durcissement, aux noms des en-têtes de sécurité,
à `httpsEnforced` et aux identifiants des contrôles supplémentaires. Une seule
option couvre tout cela, car `basicAuthDisabled` est à la fois une mesure de
durcissement et un contrôle supplémentaire : l’accepter à un endroit mais pas à
l’autre serait déroutant.

Un constat faisant l’objet d’une exemption :

- n’abaisse plus la note,
- n’apparaît plus dans `Missing hardening:` ni dans `Additional checks failed`,
- n’est plus compté dans les métriques `hardenings_missing` et
  `extra_checks_failed`,
- est exclu de la charge utile du webhook,
- mais **reste dans le document de résultat JSON**, marqué `"ignored": true`,
  et figure dans la sortie du plugin sous la forme `Ignored by configuration (n): ...`.

Une exemption supprime l’alerte et conserve la preuve :
l’analyse enregistre toujours ce qu’elle a vu, `--debug` l’explique toujours et
toute personne qui lit la sortie voit ce qui est ignoré.

Une exemption ne permet pas deux choses :

- **Exempter un contrôle qui réussit.** Une exemption ne s’applique qu’à un
  constat réellement en échec : une régression ultérieure de la mesure ne
  passe donc pas inaperçue.
- **Exempter une version en fin de vie.** Faire tourner une version qui ne
  reçoit plus de correctifs de sécurité l’emporte sur tous les autres signaux, y
  compris `--ignore-hardening '*'`.

Les exemptions ont leur place dans un fichier de configuration, où chacune peut
être accompagnée d’un commentaire expliquant sa raison d’être :

```yaml
scanner:
  release_track: production
  ignore_hardenings:
    - cspWithoutUnsafeInline   # default csp.yaml, tightening it breaks the web UI
    - hstsPreload              # the reverse proxy sets its own HSTS header
```

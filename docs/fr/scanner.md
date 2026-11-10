# Bibliothèque et CLI JSON du scanner

Le moteur d’analyse de `check-opencloud-security` et du service
`check-opencloud-scanner`.

Le scanner se connecte directement à l’instance en HTTP(S), vérifie les paramètres
observables publiquement et renvoie un document de résultat noté de `0` à `5`. Il teste
également les identifiants de démonstration documentés auprès du fournisseur d’identité
de l’instance.

L’échelle reprend celle de l’API de scan Nextcloud afin de préserver la signification
des seuils, données de performance, webhooks et tableaux de bord existants.

| Module | Rôle |
|:-------|:--------|
| `scanner.py` | Le moteur d’analyse ; produit le document de résultat |
| `releases.py` | Vérification des mises à jour à partir du flux des versions OpenCloud |
| `vulndb.py`, `data/` | Base des avis de sécurité et correspondance des plages de versions |
| `versions.py` | Analyse et comparaison des versions, période des versions prises en charge |
| `config.py`, `secrets.py` | Configuration YAML / environnement / fournisseur de secrets |
| `service.py`, `cli.py` | Le service d’analyse HTTP et la commande `check-opencloud-scanner` |
| `factory.py` | Construit les objets de paramètres à partir d’une `Configuration` |
| `tls.py` | Sécurité du transport : négociation, protocole, certificat, chaîne, agrafage |

## Ce qui est lu sur l’instance {#what-it-reads-from-the-instance}

Deux points de terminaison sont accessibles sans authentification dans OpenCloud,
et les deux sont nécessaires :

- **`/status.php`** : produit, édition, `productversion`. Il contient aussi
  `maintenance`, `installed` et `needsDbUpgrade`, mais le gestionnaire
  d’OpenCloud code ces trois valeurs en dur au lieu de lire l’état réel : ce
  paquet ne les vérifie donc pas - voir [`docs/status-php.md`](status-php.md).
- **`/ocs/v1.php/cloud/capabilities`** : les indicateurs de fonctionnalités dont
  est déduite la section sur le durcissement ci-dessous

Tout le reste est déduit des en-têtes de réponse, des codes de statut et des
connexions TCP.

Une réponse de `/status.php` seule n’identifie pas OpenCloud. Le scanner vérifie
le produit annoncé et lève `ScanError` pour un autre produit, dont les versions,
les avis de sécurité et les valeurs par défaut ne correspondraient pas à cette
base. Voir [Qu’est-ce qu’OpenCloud](what-is-opencloud.md).

### Le piège de la version {#the-version-trap}

`/status.php` indique trois champs de version :

```json
{"version": "0.1.0.0", "versionstring": "0.1.0", "productversion": "7.4.0"}
```

`version` et `versionstring` sont des **constantes codées en dur** (`pkg/version`
dans le code source d’OpenCloud). Elles existent pour que les anciens clients de
synchronisation qui attendent une chaîne de version de type ownCloud continuent
de fonctionner, et elles sont identiques sur toutes les instances jamais livrées.
Seul `productversion` correspond à la version réelle.

`versions.select_version()` privilégie donc `productversion`, se rabat sur le
point de terminaison des capacités et considère les valeurs de substitution
connues comme inutilisables. Lorsqu’une instance ne propose que la valeur de
substitution, le document de résultat contient `legacyVersion` et les contrôles
de fin de vie, de mise à jour et d’avis de sécurité sont ignorés au lieu d’être
exécutés sur `0.1.0`.

Si vous analysez déjà `/status.php` dans un autre script, c’est ce champ qu’il
faut vérifier.

## Algorithme de notation {#rating-algorithm}

Évalué dans cet ordre :

| Note | Grade | Condition |
|:------:|:-----:|:----------|
| 0 | F | Fin de vie |
| 1 | E | Vulnérabilité de gravité critique ou élevée |
| 2 | D | Toute autre vulnérabilité connue |
| 3 | C | En retard d’une ligne de version entière |
| 4 | A | Mise à jour disponible dans la ligne de version |
| 5 | A+ | À jour |

puis **plafonné** par le pire contrôle supplémentaire en échec : `critical` -> au
plus `2` (D), `high` -> `3` (C), `medium` -> `4` (A), `low` -> `5` (A+).

Un plafond ne peut qu’abaisser la note de départ : un constat de configuration ne
peut donc pas améliorer un résultat de fin de vie. Notez la conséquence pour la
supervision : un constat critique plafonne la note à `2` (`D`), ce que la valeur
par défaut `--critical 1` signale comme WARNING. Utilisez `--critical 2` pour en
faire un CRITICAL.

Pour signaler les constats sans toucher du tout à la note :

```yaml
scanner:
  extra_checks_rating: false
```

Ou supprimez entièrement les contrôles supplémentaires avec `--no-extra-checks`.

Chaque analyse enregistre dans `ratingExplanation` comment elle est parvenue à sa
note :

```json
{
  "rating": 4,
  "base": {"rating": 5, "reason": "the installed release is current and no advisory matches this version"},
  "caps": [
    {"check": "basicAuthDisabled", "severity": "medium", "cap": 4,
     "detail": "PROXY_ENABLE_BASIC_AUTH is on", "applied": true}
  ]
}
```

`base` est la note produite par la version et la base des avis de sécurité
seules ; `caps` liste chaque contrôle supplémentaire en échec avec le plafond
qu’impose sa gravité. Un contrôle en échec qui n’a pas déterminé le résultat est
conservé avec `applied: false` : un constat n’est donc jamais absent du
raisonnement sans le dire. La liste est triée par gravité, ce qui rend
l’explication indépendante de l’ordre dans lequel les contrôles se sont
exécutés.

## Ce qui améliorerait la note {#what-would-raise-the-rating}

Le même résultat contient un `remediationPlan`, construit par `remediation.py` à
partir des plafonds ci-dessus : une liste ordonnée de corrections, avec la note
que chaque étape permettrait d’atteindre.

```json
{
  "currentRating": 3,
  "achievableRating": 5,
  "summary": "Two fixes would raise this instance from 3/5 to 5/5.",
  "steps": [
    {"order": 1, "id": "exposed:/opencloud.yaml", "kind": "finding",
     "severity": "high", "title": "A deployment file is publicly readable",
     "action": "Stop serving the deployment directory ...",
     "ratingBefore": 3, "ratingAfter": 4, "ratingGain": 1}
  ],
  "blocked": [],
  "waived": []
}
```

C’est une réexécution de `_compute_rating` en retirant un constat à la fois, et
non un second modèle de la note : une note prévue ne peut donc pas contredire la
note réelle. Rien de nouveau n’est stocké : le plan est déduit du document qui le
contient.

Trois propriétés sont essentielles et couvertes par des tests :

- L’**ordre** suit le plafond, puis la gravité, puis l’identifiant : il ne
  dépend donc pas de l’ordre d’exécution des contrôles. Une étape qui ne fait
  rien gagner à elle seule - la première de plusieurs constats partageant un
  même plafond - reste dans la liste avec `ratingGain: 0` au lieu d’être
  masquée.
- Une **mise à jour est aussi une étape**, insérée à la première position où
  elle commence à apporter quelque chose. Corriger des constats ne peut pas
  élever une note au-delà de ce que permet la version installée : un plan qui
  placerait la mise à jour en premier promettrait un gain impossible.
- **Les constats impossibles à corriger** - `actionable: false`, les indicateurs
  qu’OpenCloud code en dur - vont dans `blocked` et restent dans chaque reste
  simulé, ce qui borne correctement `achievableRating`.

Une version en fin de vie ramène directement la note à `0` sans enregistrer de
plafonds : dans ce seul cas, le plan les reconstruit à partir d’`extraChecks`.
Sinon, il promettrait une note parfaite après une mise à jour alors qu’un
constat critique resterait ouvert.

## Le problème de l’application monopage {#the-single-page-application-problem}

OpenCloud est un binaire Go unique qui sert un frontend monopage intégré. Ce
frontend répond **aux chemins inconnus par HTTP 200 et la coquille de
l’application** : le contrôle naïf des chemins exposés (« `/opencloud.yaml`
renvoie-t-il 200 ? ») signale donc quelques expositions fantômes sur toutes les
instances saines.

Avant toute sonde, le scanner demande un chemin qui ne peut pas exister
(`/check-opencloud-security-probe-404`) et enregistre la réponse. Un chemin
n’est signalé comme exposé que lorsque sa réponse diffère réellement de cette
référence générique. La même protection couvre les reverse proxies configurés
avec une réponse de repli générale.

## Détection de fin de vie {#end-of-life-detection}

OpenCloud maintient trois types de versions en même temps, chacun avec sa propre
période de support :

| Canal | Rythme | Pris en charge jusqu’à |
|:------|:--------|:----------------|
| `rolling` | environ toutes les 3 semaines | la sortie de la version suivante |
| `production` | environ tous les 6 mois | la version de production suivante |
| `lts` | une ligne de production | 2 ans après l’ouverture de la ligne |

Un numéro de version seul ne répond donc pas à la question « est-ce encore pris
en charge ? ». `7.2.3` est la version de production actuelle alors que le canal
rolling en est déjà à `7.4.0`, et `7.3.0` - une version *plus élevée* - a cessé
de recevoir des correctifs le jour de la sortie de `7.4.0`.

L’unité de support est la **ligne de version** (`MAJOR.MINOR`), car c’est ce
qu’OpenCloud maintient : `7.2.3` est un correctif de la ligne `7.2`. Une ligne
peut être publiée sur plusieurs canaux, et elle est jugée selon celui qui la
prend en charge le plus longtemps :

- `7.2` est sortie en version rolling puis a été promue en production. En tant
  que version rolling, elle est abandonnée (7.3 existe) ; en tant que version de
  production, elle est à jour. **À jour** est la réponse qui compte.
- `4.0` est la ligne de production précédente *et* la ligne LTS actuelle. Sa
  période de production a pris fin avec l’arrivée de `7.2`, mais ses
  rétroportages LTS courent jusqu’à deux ans après `4.0.0`.

`schedule_source.py` lit les dates de publication dans la
[documentation d’administration d’OpenCloud][lifecycle] - la seule source qui
indique le *type* de version ; la liste des versions GitHub ne permet pas de
distinguer une version rolling d’une version de production.
`scripts/update_release_schedule.py` l’exécute en CI et écrit le résultat dans
`data/release_schedule.json`, qui est le fichier livré :

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

```json
{
  "lifetime_days": {"rolling": 21, "production": 183, "lts": 730},
  "latest_release": {"production": "7.2.3", "rolling": "7.4.0"},
  "lines": [
    {"line": "7.4", "tracks": ["rolling"], "released": "2026-08-03", "latest": "7.4.0"},
    {"line": "7.2", "tracks": ["production", "rolling"], "released": "2026-06-25", "latest": "7.2.3"},
    {"line": "4.0", "tracks": ["lts", "production"], "released": "2025-12-01", "latest": "4.0.8"}
  ]
}
```

Les lignes rolling et production prennent fin à la sortie de la ligne suivante
sur le même canal ; `lifetime_days` borne la ligne la plus récente d’un canal et
donne à LTS la période de deux ans promise par la documentation. Une ligne qui
n’est plus prise en charge reçoit `EOL: true` et la note `F`.

Deux cas ne sont volontairement *pas* considérés comme une fin de vie :

- une version plus récente que tout ce que contient le calendrier, car le fichier
  fourni vieillit entre deux mises à jour et une nouvelle version ne doit pas
  déclencher l’alarme ;
- la ligne la plus récente d’un canal, qui n’a rien vers quoi se mettre à jour.

Lorsque l’instance est plus récente que le calendrier, le résultat contient
`scheduleStale`, `scheduleUpdated`, `scheduleSource` et une `scheduleNote` qui
renvoie à la [page du cycle de vie][lifecycle]. Ces champs décrivent les données
de référence sans modifier la note ni la recommandation de mise à jour.
`ReleaseSchedule.is_behind()` expose la même comparaison.

Le plugin conserve le calendrier livré avec lui : un hôte de supervision exécute
la vérification toutes les quelques minutes et ne doit pas la transformer en
téléchargement de documentation ; le fichier est donc actualisé par une mise à
jour du paquet. L’application web est l’autre cas - un processus qui reste en
service pendant des mois - et relit la même page une fois par jour via
`schedule_source.fetch_schedule_document()`, en transmettant le résultat à
`ScannerSettings.release_schedule`. Dans les deux cas, le scanner *reçoit* un
calendrier et ne décide rien de nouveau quant à sa provenance.

```yaml
scanner:
  use_release_schedule: true       # false skips the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/release_schedule.json
```

Le verdict complet apparaît sous `lifecycle` dans le document de résultat -
ligne, canal, date de publication, fin du support, jours restants, version vers
laquelle mettre à jour, et âge du calendrier qui a décidé de tout cela -, si bien
qu’un calendrier périmé ou remplacé est visible au lieu de passer inaperçu.

## Vérification des mises à jour {#update-check}

Une instance OpenCloud ne signale pas les mises à jour en attente : il n’y a ni
commande `occ` ni point de terminaison de mise à jour. La version la plus récente
est donc recherchée à l’extérieur et comparée à `productversion`.

La recommandation **tient compte du canal**. Un flux ne connaît que la version la
plus récente tous canaux confondus, qui est toujours une version rolling : la
proposer à une instance production ou LTS la ferait passer sur une période de
support de trois semaines. Ces instances se voient donc proposer la version la
plus récente de leur propre canal, et la version la plus récente tous canaux
confondus est signalée séparément sous `newestRelease`.

| Mode | Comportement |
|:-----|:----------|
| `auto` | Essaie le flux ; en cas d’échec, utilise `latest_release` des données fournies |
| `feed` | Uniquement le flux ; un échec est signalé comme inconnu |
| `pinned` | Utilise la `latest_version` configurée ; aucun accès réseau |
| `bundled` | Utilise la `latest_release` livrée ; aucun accès réseau |
| `off` | Ignore la vérification des mises à jour |

`auto` est la valeur par défaut et ne fait jamais échouer une vérification : un
GitHub limité en débit ou injoignable se rabat sur la version fournie, aussi
récente que le paquet installé. `feed` est le mode à choisir lorsqu’un repli
silencieux serait pire qu’un état inconnu explicite.

Le flux est par défaut l’API des versions GitHub. `parse_release_feed()` comprend
aussi un simple document `{"tag_name": ...}` et une liste de versions : un miroir
interne n’a donc besoin d’aucun format particulier. Les brouillons et les
préversions sont ignorés.

## Vulnérabilités {#vulnerabilities}

À côté de `vulnerabilities`, un résultat contient `upgradePath` lorsque la
version installée est concernée par des avis de sécurité connus et qu’une
version plus récente est recommandée : la `target`, les avis qu’elle `fixes`,
ceux par lesquels elle reste `stillAffected`, et `safeVersion`, la plus ancienne
version postérieure à tous les correctifs manquants (`null` lorsque l’un d’eux
n’en a pas encore). Sinon, il vaut `null`. Voir
[La mise à niveau lève-t-elle les avis de sécurité ?](release-lifecycle.md#does-the-upgrade-clear-the-advisories)

`upgradeRehearsal` va plus loin : pour chaque version candidate (le dernier
correctif de la ligne installée et la dernière version de chaque ligne
ultérieure, limitées au canal déclaré), il indique ce que la version `fixes`,
laisse `stillAffected` et `introduces`, si elle est `endOfLife`, et la note
`rating` de 0 à 5 que l’analyse lui attribuerait - les règles de version
rejouées, toujours plafonnées par les contrôles en échec de l’instance. La liste
est vide lorsqu’aucune version plus récente n’est connue. Voir
[Répéter chaque mise à niveau](release-lifecycle.md#rehearse-every-upgrade).

`alternativeServices` enregistre l’en-tête `Alt-Svc` de l’instance - si elle
annonce HTTP/3 sur UDP - comme une observation jamais notée. Voir
[Services alternatifs](scanner-checks.md#alternative-services-http3).

`loginThrottling` vaut `null` sauf si `check_login_throttling` est activé ; il
indique alors si six connexions échouées pour un compte inexistant ont été
ralenties. Jamais noté. Voir
[Connexions échouées](scanner-checks.md#failed-sign-ins-opt-in).

### Actualiser les données de référence sur un hôte de supervision {#refreshing-reference-data-on-a-monitoring-host}

Le paquet contient une commande distincte, `refresh-data`, pour les
installations qui ne peuvent pas attendre une mise à jour du paquet :

```console
$ check-opencloud-scanner refresh-data \
    --output-dir /var/lib/check-opencloud-security
/var/lib/check-opencloud-security/release_schedule.json
/var/lib/check-opencloud-security/vulnerabilities.json
```

Elle lit les deux documents dans le dépôt de ce projet - les fichiers examinés
et fusionnés par un mainteneur, pas une requête en direct vers un tiers - et
**vérifie une attestation Sigstore** portant sur eux avant de leur faire
confiance. Elle rejette ensuite un document de cycle de vie qui perd une ligne de
version fournie, refuse les avis de sécurité sans bornes et remplace chaque
fichier de façon atomique. Elle n’écrit jamais dans le paquet installé. Faites
pointer `scanner.release_schedule` et `scanner.vulnerability_db` vers les deux
fichiers générés, puis exécutez chaque jour le timer fourni
[`check-opencloud-security-refresh.timer`](../../contrib/systemd/check-opencloud-security-refresh.timer).
Une panne réseau laisse les fichiers précédents intacts.

La vérification de signature nécessite l’extra `signing` :

```console
$ pip install 'check-opencloud-security[signing]'
```

Sans lui, l’actualisation s’exécute quand même : elle se rabat sur les seules
protections structurelles et le signale par un avertissement dans le journal.
Notez ce que cela implique : un hôte sans cet extra ne vérifie pas du tout la
provenance, installez-le donc partout où l’actualisation compte réellement.

Avec l’extra installé, trois issues sont possibles. Un
document vérifié est écrit. Une signature qui n’a pas pu être *vérifiée* -
attestation pas encore publiée, GitHub injoignable, racine de confiance
impossible à charger - produit un avertissement et un repli sur les protections
structurelles. Une signature présente et *incorrecte* arrête net l’actualisation
et laisse les fichiers précédents exactement à leur place.

Passer `--schedule-url` ou `--advisory-url` interroge cette source en direct et
sans vérification, pour un miroir isolé ou un fork, et l’indique dans le
journal. Voir
[l’ADR 0027](../../adr/0027-refreshed-reference-data-is-attested-not-merely-fetched.md).

`data/vulnerabilities.json` contient les avis de sécurité publiés pour OpenCloud
et est régénéré chaque jour par `.github/workflows/vulnerability-db.yml`, qui
exécute `scripts/update_vulnerability_db.py` sur l’API de requête OSV et ouvre
une pull request lorsque la réponse a changé. L’actualisation **ne fait
qu’ajouter** : un avis que le flux a oublié reste dans le fichier, et une entrée
rédigée à la main est conservée. Une entrée n’est supprimée qu’à la
main.

La base n’est toutefois complète que dans la mesure où les flux dont elle est
issue le sont. `vulnerabilities: []` dans une analyse signifie *« rien dans la
base configurée n’a correspondu »*, et non *« cette instance n’a aucune
vulnérabilité connue »*, et une grande partie de la note vient de toute façon
des contrôles de configuration. Ajoutez votre propre source si vous en avez
une :

```yaml
scanner:
  vulnerability_db: /etc/check-opencloud-security/advisories.json
  vulnerability_feed: https://api.osv.dev/v1/query
```

Trois formats d’entrée sont acceptés - le format natif
(`{"advisories": [{"id": ..., "introduced": ..., "fixed": ...}]}`), le format de
l’API GitHub Advisory et les documents OSV -, si bien qu’une installation isolée
peut copier un flux dans un fichier sans conversion. Les entrées correspondent à
la plage de versions semi-ouverte `[introduced, fixed)` et sont dédupliquées par
identifiant entre les sources. Les sources réellement chargées apparaissent sous
`advisorySources` dans le document de résultat : un chemin mal configuré est
donc visible au lieu de passer inaperçu.

Un avis peut concerner plusieurs lignes de version corrigées séparément.
`GHSA-vf5j-r2hw-2hrw` a été corrigé à la fois dans `4.0.3` et dans `5.0.2` : c’est
un seul avis avec deux plages disjointes, et non deux avis. Une entrée peut donc
porter une liste `ranges` :

```json
{
  "id": "GHSA-vf5j-r2hw-2hrw",
  "severity": "high",
  "ranges": [
    {"introduced": "4.0.0", "fixed": "4.0.3"},
    {"introduced": "5.0.0", "fixed": "5.0.2"}
  ]
}
```

Une correspondance indique le correctif propre à la ligne de l’instance
analysée : une instance `5.0.1` est invitée à passer à `5.0.2` plutôt qu’à une
version qui ne corrige rien pour elle. `introduced` et `fixed` restent à côté,
comme première plage, ce qu’a toujours été un avis à plage unique.

**Un avis sans aucune borne de version est écarté**, quelle que soit sa
provenance. Une plage ouverte aux deux extrémités correspond à toutes les
versions ayant jamais existé, et des flux publics publient bien cette forme : la
base des vulnérabilités Go enregistre cet avis précis avec `introduced: "0"` et
sans correctif. Le croire reviendrait à signaler toutes les instances OpenCloud
du monde comme vulnérables : l’analyseur le refuse donc au lieu de compter sur
le bon sens du flux.

## Durcissements {#hardenings}

Ce paquet n’a **pas de matrice de durcissement**. Il ne déduit pas « cette
version prend en charge la fonction X, donc X est activée » : il ne signale que
ce que l’instance a réellement indiqué.

| Durcissement | Preuve |
|:----------|:---------|
| `hstsLongMaxAge` | `Strict-Transport-Security` avec un `max-age` >= un an |
| `hstsPreload` | Le même en-tête contenant `preload` |
| `cspWithoutUnsafeInline` | Une `Content-Security-Policy` sans `'unsafe-inline'` |
| `basicAuthDisabled` | `WWW-Authenticate` sur un point de terminaison protégé, sans proposition `Basic` |
| `publicLinkPasswordEnforced` | Capacités : mot de passe exigé pour les liens publics |
| `publicLinkExpirationEnforced` | Capacités : expiration imposée sur les liens publics |
| `userEnumerationRestricted` | Capacités : recherche d’utilisateurs restreinte |
| `passwordPolicyEnforced` | Capacités : politique activée et longueur minimale du mot de passe >= 8 |
| `passwordPolicyComplexity` | Capacités : la politique exige encore une minuscule, une majuscule, un chiffre et un caractère spécial |
| `oidcPkceSupported` | Document de découverte : `code_challenge_methods_supported` contient `S256` |
| `oidcImplicitFlowDisabled` | Document de découverte : `response_types_supported` ne renvoie aucun jeton depuis le point de terminaison d’autorisation (fournisseurs externes uniquement) |
| `oidcSigningAlgorithmStrong` | Document de découverte : `id_token_signing_alg_values_supported` ne contient ni `none` ni algorithme `HS` |
| `oidcEndpointsUseHttps` | Document de découverte : chaque point de terminaison publié est en `https://` (mesuré uniquement lorsque l’instance elle-même a répondu en HTTPS) |

Une clé est entièrement omise lorsque la preuve correspondante est
indisponible : en-tête absent, ou instance dont le point de terminaison des
capacités ne signale pas cette fonction. Une version plus ancienne n’accumule
donc pas de constats fantômes, et `capabilitiesAvailable` dans le document de
résultat indique si la seconde moitié du tableau a pu être évaluée.

Les clés omises, et la raison de leur omission, sont enregistrées dans
`coverage` - voir [Ce que l’analyse a couvert](#what-the-scan-covered).

Les sondes supplémentaires lisent aussi la configuration web publique : des
origines de messages d’intégration génériques font échouer
`webEmbedMessageOriginRestricted`, une authentification déléguée par iframe
sans origine explicite fait échouer `webEmbedDelegatedAuthenticationRestricted`,
et un écouteur OpenCloud correspondant sur le port backend direct fait échouer
`backendPortClosed`.

Notez les points suivants avant d’activer
`--check-hardening` :

- **`cspWithoutUnsafeInline` échoue sur une instance OpenCloud non modifiée.**
  Le `csp.yaml` par défaut contient `'unsafe-inline'` dans `script-src` et
  `style-src`. C’est signalé plutôt qu’excusé, mais le corriger implique de
  livrer votre propre CSP, et le frontend web dépend actuellement de scripts et
  de styles en ligne.
- **`basicAuthDisabled` est réellement observable à distance.** Avec
  `PROXY_ENABLE_BASIC_AUTH=true`, le proxy ajoute `Basic realm="<host>"` à son
  défi `WWW-Authenticate`, à côté de `Bearer`. La gravité est `medium`, et
  `low` lorsque `identityProvider.external` vaut true : les clients CalDAV,
  CardDAV et WebDAV ne savent pas utiliser OpenID Connect, une instance qui en
  a besoin doit donc laisser l’authentification Basic active, et la présenter
  comme une défaillance grave disait aux opérateurs quelque chose qu’ils avaient
  raison de ne pas croire.
- **`publicLinkExpirationEnforced` et `userEnumerationRestricted` ne sont pas des
  paramètres.** OpenCloud écrit ces deux capacités comme des constantes codées
  en dur : la première échoue sur toutes les instances et la seconde réussit sur
  toutes. Elles sont marquées `actionable=False` dans le catalogue ci-dessous,
  ce qui les exclut des alertes et des décomptes tout en les conservant dans le
  document de résultat.

### Observations qui ne sont pas des constats {#observations-that-are-not-findings}

`scan()` signale aussi deux intégrations visibles sans connexion. Elles se
trouvent sous `integrations`, ne produisent aucune entrée dans `extraChecks` et
ne peuvent pas modifier la note :

| Clé | Preuve |
|:----|:---------|
| `integrations.office.detected` | `/app/list` - non protégé par la politique du proxy d’OpenCloud - nomme au moins un fournisseur d’applications enregistré |
| `integrations.office.apps` | Les noms de fournisseurs renvoyés, par exemple `Collabora` |
| `integrations.office.groupware` | La capacité `groupware.enabled` |
| `integrations.calendar.detected` | `/.well-known/caldav` répond par une redirection ou un défi plutôt que par 404 |
| `integrations.calendar.advertised` | La capacité `core.support_radicale`, qui vaut `true` par défaut et ne sert donc que de confirmation |

La capacité `files.app_providers` est une constante codée en dur et est ignorée.

`setup.advisoryChecks` est l’autre bloc qui ne peut pas modifier la note, pour
une raison différente : non pas parce que l’observation est neutre, mais parce
qu’OpenCloud ne la satisfait sur aucune instance ; la compter reviendrait à
présenter l’état livré du logiciel comme un défaut de ce déploiement. Il
contient deux entrées :

- `securityTxtPublished` : si `/.well-known/security.txt` contient le champ
  `Contact` exigé par la RFC 9116, pour que quelqu’un qui découvre une faille
  sache où la signaler. C’est le corps qui est lu, pas le code de statut : une
  instance dont le frontend répond à tout chemin inconnu avec sa propre coquille
  renvoie aussi 200 pour ce chemin.
- `hstsPreloadEligible` : si l’en-tête `Strict-Transport-Security` serait
  réellement accepté pour le préchargement par les navigateurs, ce qui exige à
  la fois un max-age d’au moins un an, `includeSubDomains` et `preload`.
  `hstsPreload`, dans le bloc `hardenings`, répond à la question plus étroite de
  la présence de la directive ; le proxy d’OpenCloud l’envoie avec dix ans et
  sans `includeSubDomains` : l’en-tête de toute instance non modifiée demande
  donc quelque chose que la liste de préchargement refuse. La présence du
  domaine *sur* la liste n’est volontairement pas mesurée - voir
  [l’ADR 0037](../../adr/0037-preload-eligibility-is-measured-list-membership-is-not.md).

Le bloc vaut `{}` plutôt qu’un dictionnaire de `false` lorsque les contrôles
supplémentaires sont désactivés, car une observation que personne n’a faite
n’est pas une observation en échec. Voir
[l’ADR 0034](../../adr/0034-an-advisory-observation-need-not-be-a-header.md).

L’observation `identityProvider` nomme un fournisseur externe lorsque son
émetteur OIDC l’identifie. Pour Keycloak, Authelia et Authentik, elle contient
aussi `advisoryUrl`, qui renvoie à la page officielle GitHub Security Advisories
du fournisseur. `version` est présent mais vide, car aucun de ces fournisseurs
n’expose sa version par un point de terminaison non authentifié et activé par
défaut. Le scanner ne devine rien à partir des chemins d’URL, des ressources ou
des en-têtes de proxy ; si une preuve publique fiable de version devient
disponible, ce champ pourra la porter sans changer la forme du résultat.

### Ce que le scanner ne peut pas mesurer {#what-the-scanner-cannot-measure}

Deux questions reviennent souvent et sont hors du périmètre :

- **La journalisation d’audit ne peut pas être vérifiée.** Le service d’audit
  d’OpenCloud consomme le bus d’événements interne et n’expose aucune surface
  HTTP ; aucune capacité, aucun en-tête ni aucun document non authentifié ne
  révèle s’il fonctionne. Faute de signal à lire, aucun contrôle n’existe,
  et aucun ne peut être ajouté sans identifiants.
- **« Correctement configuré » est hors du périmètre des intégrations
  ci-dessus.** Qu’un fournisseur soit enregistré ne dit rien des secrets WOPI,
  des droits de partage ni de la configuration propre du second service, qui se
  trouvent tous derrière une connexion.

Le scanner n’utilise pas d’identifiants d’utilisateurs ordinaires. L’exception
documentée est `_demo_user_finding` : avec le fournisseur intégré, il teste les
comptes de démonstration publiés via `/ocs/v1.php/cloud/user`. Une connexion
réussie produit le constat critique `demoUsersDisabled`. Aucun identifiant n’est
envoyé à un fournisseur externe. Un refus confirme seulement que ces
identifiants de démonstration ont échoué, pas que l’authentification est sûre à
tous égards.

### Expliquer les indicateurs {#explaining-the-flags}

`hardening.py` est le catalogue qui transforme ces identifiants en informations
exploitables par un opérateur. Pour chaque indicateur, il contient une
signification en langage clair, la variable d’environnement OpenCloud qui le
régit et un lien vers la documentation officielle :

```python
from opencloud_local_scan import describe_hardening

print(describe_hardening("basicAuthDisabled").describe())
```

```text
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so ...
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default). ...
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
```

Le catalogue couvre aussi les en-têtes de sécurité de `setup.headers`, les
observations consultatives de `setup.advisoryHeaders` et
`setup.advisoryChecks`, ainsi que `httpsEnforced`, et renvoie une entrée de
substitution nommée pour un identifiant inconnu : un futur contrôle ne peut donc
jamais faire planter un rapport. Un test analyse l’instance factice et vérifie
que chaque indicateur produit a une entrée : ajouter un durcissement sans le
documenter fait échouer la suite de tests.

Le même catalogue est disponible en commande, pour le cas bien plus fréquent où
l’on a un identifiant mais pas d’invite Python :

```shell
$ check-opencloud-scanner explain basicAuthDisabled
$ check-opencloud-scanner explain exposed:/config/opencloud.yaml
$ check-opencloud-scanner explain --category transport
$ check-opencloud-scanner explain --list
$ check-opencloud-scanner explain --format json cookieSecure
```

La commande fonctionne hors ligne et ne lit que le catalogue installé. Elle
accepte les noms d’en-têtes et les identifiants propres à un chemin, comme
`exposed:/config/opencloud.yaml`. Sans identifiant, elle affiche tout le
catalogue. Un identifiant inconnu renvoie le code de sortie 1 et suggère des noms
proches.

### La même correction, sous forme de configuration {#the-same-fix-as-configuration}

`snippets.py` transforme les entrées `env_fix` et `header_fix` du catalogue en
extraits de configuration :

```python
from opencloud_local_scan import configuration_fragment

print(configuration_fragment(["basicAuthDisabled", "demoUsersDisabled"], "compose").text)
```

```yaml
services:
  opencloud:
    environment:
      PROXY_ENABLE_BASIC_AUTH: "false"
      IDM_CREATE_DEMO_USERS: "false"
```

Cinq variantes : `compose`, `env`, `nginx`, `caddy`, `traefik`. Chacune exprime
un type de correction, car les deux types se trouvent dans des fichiers
différents, généralement sur des machines différentes : les affectations de
variables d’environnement vont sur l’instance OpenCloud, les en-têtes de réponse
sur ce qui termine TLS devant elle. Rendre un en-tête dans un bloc d’environnement
Compose produirait une ligne sans effet : une variante indique donc ce qu’elle
ne peut pas exprimer dans `Fragment.elsewhere`, et `flavours_for` nomme les
variantes qui le peuvent.

Tous les noms et valeurs de configuration proviennent du catalogue. Les
paramètres qui dépendent du déploiement, comme une origine CORS ou le chemin d’un
fichier CSP, figurent dans `Fragment.undecided` : ils exigent un choix de
l’opérateur avant de pouvoir générer un extrait utilisable.

## Ce que l’analyse a couvert {#what-the-scan-covered}

Un contrôle réussi et un contrôle jamais exécuté laissent la même trace dans ce
document : rien. `coverage` est l’endroit où la différence est consignée. Voir
[l’ADR 0064](../../adr/0064-a-scan-records-what-it-did-not-measure.md).

```json
{
  "coverage": {
    "schema": 1,
    "counts": {"passed": 49, "failed": 10, "not_checked": 12, "inconclusive": 0, "total": 71},
    "checks": [
      {"id": "Content-Security-Policy", "group": "header", "state": "passed"},
      {"id": "directoryListing", "group": "extraCheck", "state": "failed"},
      {"id": "tlsInspection", "group": "tls", "state": "not_checked",
       "reason": "not_applicable", "detail": "The instance answered over plain HTTP."}
    ]
  }
}
```

Chaque contrôle envisagé par l’analyse apparaît exactement une fois, dans l’un de
quatre états :

| État | Signification |
|:--|:--|
| `passed` | Le contrôle s’est exécuté et l’instance y a satisfait |
| `failed` | Le contrôle s’est exécuté et l’instance n’y a pas satisfait |
| `not_checked` | Le scanner n’a pas exécuté le contrôle |
| `inconclusive` | Le scanner a exécuté le contrôle sans pouvoir trancher |

`passed` et `failed` ne portent aucune raison : une mesure effectuée n’a pas
besoin d’excuse. Les deux autres en portent toujours une, choisie dans un
ensemble fermé :

| Raison | Signification |
|:--|:--|
| `not_applicable` | Le contrôle ne peut pas s’appliquer à ce déploiement : pas de certificat sur une instance en HTTP simple, pas de seconde adresse à comparer |
| `probe_disabled` | Un paramètre a désactivé la sonde pour cette analyse |
| `prerequisite_missing` | L’instance n’a pas publié ce que lit le contrôle |
| `timeout` | Rien n’a répondu à temps |
| `unreadable` | Quelque chose a répondu, mais la réponse n’a pas pu être comprise |
| `no_route` | Aucune route vers cette famille d’adresses depuis l’endroit où l’analyse s’est exécutée |

Deux propriétés comptent ici :

- **Le total est ce que cette analyse a envisagé**, pas une constante. Les
  contrôles sont dynamiques - les chemins sondés, les ports de débogage appelés
  et les adresses comparées dépendent de l’instance et des paramètres - : il n’y
  a donc pas de dénominateur fixe.
- **La couverture ne change jamais une note.** Rien dans ce bloc n’atteint la
  note, les gravités, la ligne d’alerte ni le code de sortie. La charge utile du
  webhook contient les décomptes, mais seulement comme compte rendu de ce qui a
  été mesuré : aucun destinataire n’a besoin de les lire pour connaître le
  verdict. Un échec exempté reste `failed` ici ; l’acceptation figure dans
  `extraChecks[].ignored`, car une exemption est une décision sur les alertes,
  pas sur les preuves.

Un document écrit avant l’existence de ce bloc n’a pas de clé
`coverage` : c’est un rapport qui ne dit pas ce qu’il a couvert, pas une analyse
sans lacune. Lisez-le avec `coverage.coverage_of(result)`, qui renvoie `None`
pour un bloc absent comme pour un bloc mal formé.

### Le résumé en une ligne {#the-one-line-summary}

`coverage.summary(result)` réduit le bloc aux quatre nombres dont un lecteur a
besoin, et `coverage.summary_line(result)` les écrit sous forme d’une phrase en
anglais :

```
84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited
```

Chaque contrôle figure dans exactement l’une des quatre catégories. `evaluated`
est une conclusion, réussite ou échec ; `skipped` est un contrôle que le scanner
a décidé de ne pas exécuter ; `indeterminate` est un contrôle exécuté qui n’a pas
pu trancher ; `networkLimited` est extrait des deux derniers, car un délai
dépassé ou une route manquante est la seule lacune qu’un autre point
d’observation pourrait combler - DNSSEC depuis un résolveur qui valide, un
fournisseur d’identité externe accessible depuis ailleurs. Les décomptes nuls
sont omis de la phrase, mais le nombre de contrôles évalués est toujours
indiqué. Les deux fonctions renvoient `None` / `""` pour un document sans bloc de
couverture : « rien n’a été manqué » et « ce rapport ne le dit pas » ne se lisent
donc jamais de la même façon.

Le plugin affiche la phrase sur une ligne de détail `Coverage:`, la charge utile
du webhook contient les mêmes nombres sous `coverage` (en snake_case, comme le
reste de la charge utile), et l’application web les affiche sous *Ce que cette
analyse n’a pas mesuré*.

## Les conditions d’exécution d’une analyse {#the-conditions-a-scan-ran-under}

Deux analyses de la même instance peuvent diverger sans que l’instance ait
changé : la base des avis a appris une CVE, une période de support s’est
terminée, le scanner a été mis à jour, une exemption a expiré. `provenance`
enregistre ce qui était connu à ce moment-là, pour qu’une comparaison puisse
distinguer ces cas d’une vraie régression. Voir
[l’ADR 0066](../../adr/0066-a-result-records-the-conditions-it-was-produced-under.md).

```json
{
  "provenance": {
    "schema": 1,
    "scannerVersion": "1.25.0",
    "scannedAt": "2026-09-17T19:56:35.852320+00:00",
    "releaseTrack": "auto",
    "advisoryData": {"digest": "7ffa242f...", "count": 1},
    "scheduleData": {"digest": "6e9468bf...", "updated": "2026-09-15"},
    "waivers": {"active": [], "expired": []},
    "coverage": {"measured": 59, "total": 71}
  }
}
```

`digest` est un SHA-256 calculé sur les champs d’identification propres aux
données de référence, sous forme canonique : les mêmes avis donnent donc la même
empreinte, quelle que soit la façon dont ils ont été sérialisés, fusionnés ou
ordonnés. C’est une empreinte plutôt qu’une copie - intégrer la base mettrait des
mégaoctets d’avis rédigés par d’autres dans chaque rapport - et plutôt qu’un
chemin de fichier, qui révélerait où la machine range ses fichiers.
`scheduleData.updated` est la date de *génération* du calendrier, pas celle de sa
lecture ; `scannedAt` est la date de l’analyse.

`waivers` enregistre les motifs et les états, jamais le texte de la raison : une
raison est de la prose écrite pour une personne, et une comparaison qui la
confronterait signalerait une faute de frappe corrigée comme un changement de
politique.

### Comparer deux résultats {#comparing-two-results}

`check-opencloud-scanner diff` affiche les changements contributifs sous le
résumé existant, et `--format json` les transmet sous `explanation` :

| Catégorie | Ce qui a changé |
|:--|:--|
| `instance` | La version, un contrôle qui a commencé ou cessé d’échouer, ou un groupe de configuration dont l’empreinte a changé |
| `referenceData` | Les avis de sécurité, le calendrier des versions, le canal de versions, ou une période de support qui s’est simplement écoulée |
| `scanner` | La version du scanner, ou le nombre de contrôles ayant abouti à une conclusion |
| `policy` | Une exemption a expiré, a été ajoutée ou retirée |
| `unknown` | Quelque chose a changé et rien d’enregistré ne l’explique |

La formulation est prudente. Une empreinte modifiée établit que
les données de référence différaient ; elle n’établit pas qu’elles ont provoqué
le changement d’une note en particulier, et la phrase en tient compte. Plusieurs
changements peuvent y contribuer sans que l’un soit désigné comme *la* cause.

`--format json` contient aussi `findings`, une entrée par constat figurant dans
l’un ou l’autre document, avec la gravité, l’état d’exemption et la catégorie de
chaque côté, ainsi que `severityTotals`, les constats en échec comptés par
gravité avant et après. C’est ce que calcule `opencloud_local_scan.findings` et ce
qu’affichent les lignes `~` et `--format side-by-side`. Cela conserve ce que
l’ensemble des noms en échec perd : un constat resté ouvert qui passe de `high` à
`critical` ne modifie pas cet ensemble, mais modifie la note qu’il plafonne.

Un côté vaut `null` lorsque le document n’a pas du tout enregistré ce constat, et
le statut indique `appeared` ou `disappeared` plutôt qu’`introduced` ou
`resolved` : absent ne veut pas dire réussi ([ADR
0064](../../adr/0064-a-scan-records-what-it-did-not-measure.md)). Les gravités sont
lues dans les documents et limitées à `critical`, `high`, `medium`, `low` et
`unknown` ; un rapport archivé est une preuve de ce qui était vrai au moment de
sa rédaction, et le catalogue actuel ne le remplace donc jamais.

`limitations` liste ce que la comparaison n’a pas pu établir - le plus souvent
que l’un des deux rapports est antérieur à ces blocs et ne peut donc pas dire
par rapport à quoi il a été jugé ni quelle part de l’analyse s’est exécutée.
C’est signalé plutôt que supposé.

## Le déploiement a-t-il changé ? {#has-the-deployment-changed}

Une note indique si une instance est en bon état. Elle ne dit pas s’il s’agit
encore de la même instance que la semaine dernière. Une politique réécrite sans
gagner `unsafe-inline`, un proxy remplacé par un autre produit qui définit les
mêmes en-têtes, des liens publics qui ont cessé d’exiger un mot de passe puis en
exigent de nouveau un, un certificat passé chez un autre émetteur : rien de tout
cela n’a à modifier la note, et un opérateur qui ne surveille que la note n’en
voit rien.

`configuration` est une **empreinte** : des condensats groupés de la façon dont
le déploiement est configuré, et rien de ce sur quoi il est configuré. Voir
[l’ADR 0073](../../adr/0073-a-result-fingerprints-the-configuration-it-measured.md).

```json
{
  "configuration": {
    "schema": 1,
    "digest": "9e3c4428...",
    "groups": {
      "tls": {"digest": "89a97538...", "scope": "1d0f4b77...", "facts": 12},
      "headers": {"digest": "cb25144c...", "scope": "b8e1a930...", "facts": 13},
      "sharing": {"digest": "7b8a1ced...", "scope": "44c0ae51...", "facts": 3},
      "authentication": {"digest": "588d045f...", "scope": "0a7be2cc...", "facts": 6},
      "proxy": {"digest": "b7db6daf...", "scope": "ff31c084...", "facts": 5}
    }
  }
}
```

Deux analyses ayant le même condensat de groupe observaient la même
configuration pour ce groupe ; deux analyses dont les condensats diffèrent, non.
Rien d’autre n’est affirmé, et les règles suivantes lui donnent sa valeur :

- **Des condensats uniquement, jamais la configuration.** Une politique de
  sécurité du contenu nomme les origines auxquelles un déploiement fait
  confiance, un document de découverte peut nommer un locataire, une bannière de
  serveur nomme une version interne. Chaque fait est haché dans son groupe puis
  écarté ; un lecteur apprend *que* le partage a changé, jamais *comment* il est
  réglé. Le bloc peut figurer sur une page publique pour la même raison qu’il
  peut figurer dans un ticket.
- **Les groupes correspondent aux questions que pose un opérateur.** « TLS
  a-t-il changé ? » est utile ; « le fait 37 a-t-il changé ? » ne l’est pas.
- **Uniquement ce que le déploiement décide.** Le groupe transport hache
  l’émetteur, la clé, l’algorithme de signature et les protocoles négociés - pas
  le numéro de série, les dates ni l’empreinte du certificat, car un
  renouvellement est une routine. Le groupe proxy hache l’éditeur, pas la
  bannière, dont le numéro de build change à chaque correctif.
- **Les paramètres propres à une analyse ne sont jamais un fait.** `scope` est
  un condensat des faits *examinés* par un groupe, sans leurs valeurs. Deux
  groupes ne sont comparés que si leurs portées concordent : une exécution qui a
  cessé d’inspecter TLS signale donc « non comparable » plutôt qu’une dérive. Un
  groupe sans rien à hacher vaut `none`.
- **Elle ne change jamais une note.** Rien ici n’atteint la note, les gravités,
  la ligne d’alerte ni le code de sortie.

Lisez-la avec `fingerprint.fingerprint_of(result)`, qui renvoie `None` pour un
bloc absent comme pour un bloc mal formé : un rapport qui ne peut pas le dire
n’est pas un déploiement qui n’a pas changé. `fingerprint.digests(result)` la
réduit à une chaîne opaque `scope:digest` par groupe, ce que stockent un fichier
de référence, un destinataire de webhook et une comparaison, et
`fingerprint.drift(before, after)` nomme les groupes qui diffèrent :

```python
from opencloud_local_scan.fingerprint import digests, drift

changed = drift(digests(last_week), digests(today))  # ('headers',)
```

Le plugin affiche `Configuration fingerprint: 9e3c4428` à chaque analyse, et
`--baseline` transforme les mêmes condensats en `No new findings, but the
configuration changed (headers)`.

## Ports de débogage {#debug-ports}

Chaque service OpenCloud exécute un écouteur de débogage qui sert `/healthz`,
`/readyz`, `/metrics`, `/config` et `/debug/pprof`. `/metrics` expose la version
exacte via `opencloud_proxy_build_info`, `/config` affiche la configuration
effective du service, et `/debug/pprof` permet à n’importe qui de déclencher un
profilage.

Ils sont liés à l’interface de bouclage sauf si `<SERVICE>_DEBUG_ADDR` en
dispose autrement : un écouteur qui répond depuis un hôte de supervision est donc
un vrai constat, le plus souvent un conteneur qui a publié toute une plage de
ports. Cinq sont sondés par défaut :

| Port | Service |
|:-----|:--------|
| 9205 | proxy |
| 9141 | frontend |
| 9124 | graph |
| 9134 | idp |
| 9239 | idm |

Chaque sonde est une seule connexion TCP avec un délai d’attente de trois
secondes : un hôte protégé par un pare-feu coûte donc jusqu’à quinze secondes
par analyse. `check_debug_ports: false`, `debug_port_timeout`, une liste
`debug_ports` plus courte et `concurrency` sont tous disponibles.

Les mêmes gestionnaires sont aussi sondés sur l’adresse principale, où ils ne
doivent jamais apparaître (constats `debugEndpoint:`).

## Toutes les adresses résolues {#every-resolved-address}

`check_all_addresses=True` (`--all-addresses` pour `scan`) répète la partie de
l’analyse qui dépend du nœud - `status.php`, les en-têtes notés de la page
racine, les capacités, le défi d’authentification, le fournisseur d’identité et
les comptes de démonstration - sur chaque adresse vers laquelle le nom s’est
résolu, l’une après l’autre, et produit `addressParity`. Chaque requête conserve
le nom d’hôte dans `Host` et SNI et est rattachée à une adresse par sa propre
session. Les adresses sont la réponse du résolveur, ou `pinned_addresses`
lorsqu’elles sont fournies : une analyse épinglée ne va donc jamais au-delà de ce
que l’appelant a validé ; IPv6 est ignoré lorsque `ipv6_enabled` vaut false. Ce
que chaque adresse a servi est listé sous `addressObservations` :

```json
{"addressObservations": [
  {"address": "198.51.100.1", "reachable": true, "version": "7.2.3",
   "headers": {"Strict-Transport-Security": true}, "hardenings": {},
   "demoUsersDisabled": true, "error": ""}
]}
```

La première adresse sert de référence ; la gravité suit la pire différence
(comptes de démonstration comme `demoUsersDisabled`, autre version `high`, tout
le reste `medium`) ; les noms exemptés ne sont pas comparés. Avec une seule
adresse, ou avec le paramètre désactivé (valeur par défaut), il n’y a aucun
constat et la liste est vide. Voir
[l’ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

## Concurrence {#concurrency}

Une analyse est dominée par l’attente : une vingtaine de requêtes HTTP plus les
connexions aux ports de débogage, émises l’une après l’autre. `concurrency`
exécute en parallèle celles qui sont indépendantes :

```python
result = scan("opencloud.example.com", settings=ScannerSettings(concurrency=8))
```

La valeur par défaut est `1`, qui n’utilise aucun thread, et les valeurs
supérieures à `32` sont ramenées à `32`. Chaque worker reçoit sa propre
`requests.Session`, car une session ne peut pas être partagée sans risque entre
threads.

Le paramètre n’affecte que la durée. Les résultats sont rassemblés dans l’ordre
d’émission des sondes : une analyse parallèle signale donc exactement les mêmes
constats, exactement dans le même ordre, qu’une analyse séquentielle.

## TLS {#tls}

Le proxy d’OpenCloud termine lui-même TLS sur le port 9200, et `opencloud init`
génère un certificat auto-signé. Le scanner se dégrade en trois étapes au lieu
d’échouer à la première :

1. HTTPS avec vérification du certificat.
2. HTTPS sans vérification : l’analyse se poursuit et `tlsTrusted` est signalé
   en échec.
3. HTTP simple : signalé comme `httpsAvailable` (critical).

`verify_tls: false` (ou `--insecure`) commence à l’étape 2. La chaîne non
reconnue apparaît toujours dans les constats ; elle cesse simplement de peser
sur la note : une instance auto-signée peut ainsi être supervisée sans note
dégradée en permanence, tandis qu’un certificat réellement défaillant ailleurs
reste visible.

Pour une autorité de certification interne, laissez la vérification active et
définissez `scanner.tls_ca_file` (ou `COS_SCANNER_TLS_CA_FILE`) sur son paquet
PEM ; `check-opencloud-scanner scan` accepte aussi `--ca-file`. Cette autorité
est alors reconnue sans désactiver la vérification.

### Ce qui est mesuré {#what-is-measured}

`tls.py` effectue l’inspection et transmet à `scanner.py` une liste de
contrôles ; il ne sait rien des notes. En plus de la négociation et de la
confiance, il signale :

| Constat | Question posée |
|:--------|:-------------|
| `tlsProtocol` | La version négociée est-elle au moins TLS 1.2 ? |
| `tlsDeprecatedProtocol` | Le serveur *accepte-t-il encore* TLS 1.0 ou 1.1, alors qu’il a négocié une version plus récente avec le scanner ? |
| `tlsHostname` | Le certificat couvre-t-il le nom demandé, jokers et adresses IP compris ? |
| `tlsChain` | Le serveur envoie-t-il ses certificats intermédiaires, ou seulement un certificat final qui n’est validé que par chance ? |
| `tlsCertificate` | Expire-t-il dans moins de `tls_min_days` jours, ou a-t-il déjà expiré ? |
| `tlsCertificateLifetime` | Est-il valide plus longtemps que le seuil de 398 jours du scanner ? |
| `tlsCipherSuite` | La suite de chiffrement négociée par cette analyse est-elle moderne et offre-t-elle la confidentialité persistante ? |
| `tlsCertificatePolicy` | Le certificat utilise-t-il une clé de taille suffisante et une signature moderne ? |
| `tlsAddressParity` | Les points de terminaison IPv4 et IPv6 publiés présentent-ils la même identité TLS utilisable ? |
| `tlsCaaRecord` | Le nom a-t-il un enregistrement DNS CAA désignant au moins un émetteur autorisé ? |
| `tlsDnssec` | La zone est-elle signée, pour que l’adresse sur laquelle reposent tous les contrôles ci-dessus soit digne de confiance ? Absent plutôt qu’en échec lorsque le résolveur utilisé ne gère pas DNSSEC |
| `cookieSecure`, `cookieHttpOnly`, `cookieSameSite` | Les cookies réellement observés dans la réponse publique portent-ils ces attributs ? |
| `tlsOcspStapling` | Une réponse de révocation est-elle agrafée à la négociation ? |

Les mesures correspondantes figurent dans un bloc `tls` du document de résultat :
protocole et suite de chiffrement, sujet, émetteur, période de validité, jours
restants et noms du certificat, longueur de la chaîne, et ce qu’ont trouvé les
sondes des protocoles obsolètes et de l’agrafage.

```json
{
  "host": "opencloud.example.com",
  "port": 443,
  "reachable": true,
  "protocol": "TLSv1.3",
  "cipher": "TLS_AES_256_GCM_SHA384",
  "cipherBits": 256,
  "trusted": true,
  "hostnameMatch": true,
  "chainComplete": true,
  "chainLength": 2,
  "deprecatedProtocolsProbed": ["TLSv1", "TLSv1.1"],
  "deprecatedProtocolsAccepted": [],
  "ocspStapled": false,
  "ocspNote": "the certificate names no OCSP responder",
  "certificate": {
    "subject": "opencloud.example.com",
    "issuer": "Example CA R3",
    "serialNumber": "03A1...",
    "notBefore": "2026-06-01T00:00:00+00:00",
    "notAfter": "2026-08-30T00:00:00+00:00",
    "daysRemaining": 9,
    "lifetimeDays": 90,
    "altNames": ["opencloud.example.com"],
    "ocspResponders": [],
    "selfSigned": false,
    "keyType": "RSA",
    "keyBits": 2048,
    "signatureAlgorithm": "sha256WithRSAEncryption"
  }
}
```

**`null` signifie « non déterminé », jamais « correct ».** Un contrôle qui n’a
pas pu être effectué - `get_unverified_chain()` exige Python 3.13, la sonde des
protocoles obsolètes exige une version compilée qui les prend encore en charge, l’agrafage exige la
commande `openssl` et un certificat qui désigne un répondeur - est entièrement
omis des constats au lieu d’être enregistré comme réussi. Voir
[l’ADR 0013](../../adr/0013-transport-security-is-measured-not-assumed.md).

Le certificat est décodé à partir de ce que le serveur a présenté, qu’il ait été
vérifié ou non : une instance avec le certificat auto-signé généré par
`opencloud init` voit donc quand même son expiration, ses noms et sa durée de
validité vérifiés. Deux sondes sont facultatives à l’appel : `probe_deprecated`
ouvre une négociation supplémentaire par ancien protocole, et `check_stapling`
exécute un `openssl s_client` avec une liste d’arguments fixe et sans shell.

## Ce que ce paquet ne fait pas {#what-this-package-does-not-do}

- **Pas de choix de backend.** Il n’y a pas de scanner distant à sélectionner :
  il n’y a donc ni `--scan-backend`, ni `--scan-url`, ni `--scan-token`, et rien
  dont il faudrait forcer une nouvelle analyse, puisque rien n’est jamais mis en
  cache.
- **Pas de contrôle du journal d’audit.** Le service d’audit n’a ni surface HTTP
  ni capacité propre : il n’y a rien à observer. Voir [Ce que le scanner ne peut
  pas mesurer](#what-the-scanner-cannot-measure).
- **Pas de matrice de durcissement.** Les durcissements sont observés, pas
  déduits de la version (voir ci-dessus).
- **Pas d’identifiants sur l’instance.** Chaque contrôle fonctionne avec ce que
  peut voir un client non authentifié. La vérification des mises à jour lit un
  flux public.
- **Aucune hypothèse héritée de l’ère PHP.** OpenCloud est un binaire Go unique
  avec des ressources intégrées : il n’y a ni `config/config.php`, ni `/data/`,
  ni `/3rdparty/`. Les constats visent ce qu’OpenCloud expose réellement :
  l’authentification de l’API Graph et d’OCS, les ports de débogage,
  `opencloud.yaml`, `proxy/server.key` et la base boltdb d’idm.

## Utilisation directe {#using-it-directly}

```python
from opencloud_local_scan import ScannerSettings, scan

result = scan("opencloud.example.com", settings=ScannerSettings(timeout=10))
print(result["rating"], result["version"], result["extraChecks"])
```

`scan()` lève `ScanError` lorsqu’il ne peut pas identifier OpenCloud : point de
terminaison injoignable, réponse qui n’est pas un JSON exploitable, champs de
version manquants ou produit différent. Les cas où un service a répondu lèvent
`NotOpenCloud`. Par défaut, après une réponse HTTPS inexploitable, le scanner
fait une nouvelle tentative sans vérification du certificat, puis en HTTP.
`ScannerSettings(stop_when_not_opencloud=True)` s’arrête après la première
réponse de ce type ; l’application web publique l’active.

Le document contient aussi `addresses`, les adresses IPv4 et IPv6 vers
lesquelles le nom d’hôte s’est résolu pendant l’analyse :

```json
{"addresses": {"ipv4": ["198.51.100.7"], "ipv6": ["2001:db8::7"]}}
```

C’est un contexte plutôt qu’un constat, et cela ne modifie jamais la note. Les
adresses épinglées via `ScannerSettings.pinned_addresses` sont signalées telles
quelles : l’application web valide un nom avant de lancer une analyse et se
connecte exactement à ces adresses, si bien qu’une seconde résolution ici
pourrait nommer une adresse à laquelle l’analyse ne s’est jamais connectée.

Chaque paramètre de `ScannerSettings` et de `ReleaseSettings` peut aussi provenir
d’un fichier de configuration (YAML, ou JSON lorsque le nom se termine par
`.json`), d’une variable d’environnement ou d’un fournisseur de secrets - voir
[`config/check-opencloud-security.example.yml`](../../config/check-opencloud-security.example.yml)
et la section [Fichier de configuration et secrets](../../README.md#configuration-file-and-secrets)
du README principal. `check-opencloud-scanner configure` écrit un tel fichier de
façon interactive.

Pour une analyse qui ne doit pas accéder au réseau au-delà de l’instance
elle-même :

```python
from opencloud_local_scan import ReleaseSettings, ScannerSettings, scan

result = scan(
    "opencloud.example.com",
    settings=ScannerSettings(verify_tls=False, vulnerability_feed=None),
    release_settings=ReleaseSettings(mode="bundled"),
)
```

## Vérifier une correction sans analyse complète {#verifying-a-fix-without-a-full-scan}

`opencloud_local_scan.verification.verify` ne remesure que les constats qui lui
sont indiqués, en exécutant pour eux les sondes propres du scanner et rien
d’autre. C’est la base de `--verify-remediation` (voir
[l’ADR 0072](../../adr/0072-remediation-verification-re-measures-named-findings-without-a-full-scan.md)).

```python
from opencloud_local_scan.verification import verify

document = verify(
    "opencloud.example.com",
    ["Strict-Transport-Security", "exposed"],
)
for entry in document["results"]:
    print(entry["id"], entry["passed"], entry["reason"])
```

Le document contient `domain`, `url`, `verifiedAt`, `probeGroups` (les groupes
réellement exécutés) et `results`, une entrée par identifiant demandé, dans
l’ordre indiqué :

| Clé | Signification |
|:----|:--------|
| `id` | L’identifiant demandé ; une racine de famille comme `exposed` couvre tous les membres `exposed:...` |
| `verifiable` | False pour un identifiant que seule une analyse complète peut trancher (`eol`, `vulnerability:...`, `httpsAvailable`, les contrôles de parité d’adresses) ou que cette version ne prend pas en charge |
| `passed` | True ou false lorsqu’il a été mesuré, `None` lorsque rien ne l’a été |
| `group` | Le groupe de sondes qui l’a mesuré |
| `checks` | Les constats mesurés, sous la même forme que les entrées d’`extraChecks` |
| `reason` | Pourquoi `passed` vaut `None`, vide sinon |

Comme `scan()`, cette fonction mesure et ne juge jamais : ni note, ni exemptions,
ni plan de correction. `probe_group(id)` indique à l’avance à quel groupe
correspond un identifiant, le cas échéant. Elle lève `ScanError` lorsque
l’instance est injoignable.

## Comparer une analyse avec la précédente {#comparing-a-scan-with-the-last-one}

`opencloud_local_scan.baseline` réduit un document de résultat aux constats qui
méritent d’être comparés - vulnérabilités, mesures de durcissement manquantes
exploitables et non exemptées, contrôles supplémentaires en échec et mise à jour
en attente - et les mémorise par hôte. C’est la base de `--baseline` /
`--warn-on-new`.

```python
from opencloud_local_scan import load_baseline, scan, snapshot_of

result = scan("opencloud.example.com")
store = load_baseline("/var/lib/check_opencloud/baseline.json")
comparison = store.compare("opencloud.example.com", snapshot_of(result))

if comparison.regressed:
    print(comparison.summary())

store.record("opencloud.example.com", snapshot_of(result))
store.save()
```

`Comparison.regressed` est vrai à la première exécution (il n’y a rien à quoi
comparer, et rester silencieux masquerait un vrai problème), lorsqu’un constat
est nouveau, lorsque la note a baissé, et chaque fois que la version a dépassé sa
fin de vie - ce dernier cas quelle que soit sa durée, car une version qui ne
reçoit plus de correctifs de sécurité se dégrade chaque jour où elle reste en
production.

L’horodatage de l’analyse, sa durée et la chaîne de version ne font
volontairement pas partie d’un instantané : ils changent d’eux-mêmes et feraient
paraître chaque exécution nouvelle. L’écriture est atomique et réservée au
propriétaire, et un fichier corrompu ou d’un format futur est lu comme « pas
encore de référence » au lieu de lever une erreur : revenir à la vérification
normale n’est jamais pire que refuser de s’exécuter.

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

# La commande `check-opencloud-scanner`

Le paquet installe deux commandes.

- **`check-opencloud-security`** est le plugin de supervision. Il analyse une
  instance, *juge* le résultat par rapport à des seuils et se termine avec
  `0`-`3` pour Nagios ou Icinga. Ses options figurent dans la
  [référence des options de la CLI](cli-reference.md).
- **`check-opencloud-scanner`** est tout le reste. Il fournit le document de
  résultat brut, en compare deux, explique un constat, actualise les données
  de référence et exécute le service de scan. Il n'applique jamais de seuil
  d'avertissement ni de seuil critique.

Cette page est la référence de la seconde.

<!-- TOC -->
* [La commande `check-opencloud-scanner`](#the-check-opencloud-scanner-command)
  * [Options globales](#global-options)
  * [`scan` - afficher le document de résultat](#scan---print-the-result-document)
  * [`diff` - ce qui a changé entre deux résultats enregistrés](#diff---what-changed-between-two-saved-results)
  * [`fleet` - un tableau de bord à partir de résultats enregistrés](#fleet---a-dashboard-from-saved-results)
  * [`explain` - ce que signifie un constat et comment le corriger](#explain---what-a-finding-means-and-how-to-fix-it)
  * [`review-waivers` - les exemptions à revoir](#review-waivers---waivers-that-need-attention)
  * [`refresh-data` - actualiser le calendrier des versions et les avis de sécurité](#refresh-data---update-the-release-schedule-and-advisories)
  * [`serve` - le service de scan](#serve---the-scan-service)
  * [`configure` - écrire un fichier de configuration](#configure---write-a-configuration-file)
  * [Codes de sortie](#exit-codes)
<!-- TOC -->


## Options globales {#global-options}

Elles se placent **avant** le sous-commande :

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml -v scan opencloud.example.com
```

| Option | Fonction |
|:--|:--|
| `-c, --config` | Fichier de configuration. `.json` est lu comme du JSON, tout le reste comme du YAML |
| `-v, --verbose` | Plus de journalisation sur stderr : `-v` pour info, `-vv` pour debug |

Sans `-c`, le premier fichier existant est utilisé, dans cet ordre :

1. `./.env.json`
2. `./check-opencloud-security.yml`
3. `./check-opencloud-security.yaml`
4. `~/.config/check-opencloud-security/.env.json`
5. `/etc/check-opencloud-security/.env.json`
6. `/etc/check-opencloud-security/config.yml`
7. `/etc/check-opencloud-security/config.yaml`

C'est la même recherche que celle du plugin. Les variables d'environnement
`COS_` s'appliquent par-dessus le fichier, et les options par-dessus les deux.
Voir [Secrets dans la configuration](configuration.md).

## `scan` - afficher le document de résultat {#scan-print-the-result-document}

```bash
check-opencloud-scanner scan opencloud.example.com
check-opencloud-scanner scan --compact opencloud.example.com > result.json
check-opencloud-scanner scan cloud1.example.com cloud2.example.com | jq '.[].rating'
```

Il affiche le document de résultat JSON du scanner : la note et son
explication, le cycle de vie, chaque contrôle, le TLS et les avis de sécurité
correspondants, le tout avec des clés en camelCase. Il n'émet aucun verdict.
Un hôte produit un objet. Plusieurs hôtes produisent un tableau, dans l'ordre
indiqué.

| Option | Fonction |
|:--|:--|
| `--compact` | Afficher le document sur une seule ligne plutôt qu'indenté |
| `--scheme {https,http}` | Comment joindre l'instance |
| `--port` | Remplacer le port |
| `--timeout` | Secondes accordées à chaque requête |
| `--insecure` | Ne pas vérifier le certificat TLS de l'instance |
| `--ca-file` | Paquet d'autorités de certification PEM pour vérifier un certificat interne |
| `--no-extra-checks` | Uniquement le produit, la version et les en-têtes |
| `--no-debug-ports` | Ne pas sonder les ports de débogage d'OpenCloud |
| `--all-addresses` | Répéter les contrôles principaux sur chaque adresse à laquelle le nom se résout |
| `--concurrency` | Les sondes s'exécutent en parallèle au sein d'un même scan. Valeur par défaut `1` |
| `--no-update-check` | Ne pas rechercher la version OpenCloud la plus récente |

Les exclusions, la branche de versions et les sources d'avis de sécurité
proviennent du fichier de configuration ou de l'environnement, exactement
comme pour le plugin.

Une instance impossible à analyser n'interrompt pas l'exécution. Son entrée
devient `{"host": ..., "error": ...}`, les autres hôtes sont analysés malgré
tout et la commande se termine avec `1` :

```json
{
  "host": "opencloud.example.com",
  "error": "https://opencloud.example.com/status.php is unreachable"
}
```

Ce document est celui que consomment les [pipelines d'intégration
continue](ci.md) et [Prometheus](prometheus.md), et celui que `diff` compare
ci-dessous. Le [README de la bibliothèque du
scanner](../../opencloud_local_scan/README.md) en décrit les champs.

## `diff` - ce qui a changé entre deux résultats enregistrés {#diff-what-changed-between-two-saved-results}

```bash
check-opencloud-scanner scan opencloud.example.com > before.json
# ... change something on the instance ...
check-opencloud-scanner scan opencloud.example.com > after.json
check-opencloud-scanner diff before.json after.json
```

```text
opencloud.example.com: 2026-09-15 17:42:21.524291 -> 2026-09-15 17:42:22.737103
New since last run (15): check:debugEndpoint:/config, check:debugEndpoint:/debug/pprof/, check:debugEndpoint:/metrics, check:demoUsersDisabled, check:directoryListing (+10 more)
Security check: + debugEndpoint:/config
Security check: + demoUsersDisabled
...
Hardening: + Content-Security-Policy
...
Rating: A+ (5) -> D (2)
```

Il lit deux fichiers et n'effectue aucun scan. `+` signale un constat apparu,
`-` un constat corrigé et `~` un constat toujours ouvert mais dont la gravité
a changé. Le résultat indique aussi les variations de la note, de la version
et de la période de support. Il répond à « la correction a-t-elle fonctionné ? »
et « qu'a changé la mise à niveau ? » sans fichier de référence. Pour un
contrôle qui mémorise lui-même son dernier passage, voir [Signaler uniquement
ce qui a changé](baseline.md).

| Option | Fonction |
|:--|:--|
| `--format text` | Lignes lisibles, comme ci-dessus ; format par défaut |
| `--format markdown` | Tableau Markdown pour un ticket ou un commentaire de pull request |
| `--format side-by-side` | Les deux scans en deux colonnes, un constat par ligne |
| `--format json` | Comparaison structurée transmise par le webhook du plugin |
| `--format slack` | JSON Slack Block Kit |
| `--category NAME` | N'afficher qu'un domaine ; option répétable |
| `--all-findings` | Lister tous les constats mesurés, pas seulement ceux qui ont changé |
| `--exit-zero` | Toujours terminer avec `0` |
| `--allow-different-hosts` | Comparer les résultats de deux instances différentes |

### Gravité, constat par constat {#severity-finding-by-finding}

Chaque comparaison se termine par le nombre de constats échoués, regroupés par gravité :

```text
~ exposed:/config/opencloud.yaml [exposure]: severity high -> critical
Failing by severity: critical 0 -> 1, high 1 -> 1, medium 0 -> 1, low 1 -> 0
```

La ligne `~` exprime ce qu'une comparaison de deux listes de noms ne peut pas
montrer. Un contrôle qui échouait avec la gravité `high` et échoue maintenant
avec `critical` n'est ni entré dans l'ensemble des contrôles en échec ni sorti
de celui-ci ; [la référence](baseline.md) reste donc silencieuse - à juste
titre, puisqu'aucune régression n'est apparue selon sa définition - alors que
la note plafonnée par ce contrôle a baissé. La gravité de chaque côté vient des
documents eux-mêmes, jamais du catalogue actuel : un scan archivé le mois
dernier décrit ce qui était vrai le mois dernier.

Un constat exclu est compté ici et affiché comme `waived`, car une exclusion
décide de ne pas déclencher d'alerte ; elle ne prétend pas que le constat a
disparu.

### Côte à côte {#side-by-side}

```bash
check-opencloud-scanner diff before.json after.json --format side-by-side
```

```text
opencloud.example.com
Rating: A+ (5) -> C (3)
Lifecycle: EOL: False -> True
Version: 3.4.0 -> 3.3.0

Finding                           2026-09-15T17:42:21+00:00  2026-09-22T09:03:11+00:00
--------------------------------  -------------------------  -------------------------
+ CVE-2026-0001                   not listed                 FAIL high
+ cspWithoutUnsafeInline          ok                         FAIL medium
~ exposed:/config/opencloud.yaml  FAIL high                  FAIL critical
- Referrer-Policy                 FAIL low                   ok
```

Chaque ligne présente les deux côtés, afin que la personne qui lit le résultat
n'ait pas à les reconstituer depuis une liste de changements.
`--all-findings` ajoute les constats inchangés : la vue passe ainsi de « ce qui
a changé » à « ce que les deux scans ont trouvé ».

`not measured` et `not listed` sont des réponses différentes qui ne sont
jamais fusionnées : un contrôle absent d'un document n'a pas été exécuté
([ADR 0064](https://github.com/sowoi/check-opencloud-security/blob/main/adr/0064-a-scan-records-what-it-did-not-measure.md)),
tandis qu'un avis absent ne concernait pas cette version. Aucun des deux ne
constitue une réussite.

### Un domaine à la fois {#one-area-at-a-time}

`--category` restreint la comparaison et accepte une valeur appartenant à l'un
de deux espaces de noms :

- **une catégorie de constat** - `cookies`, `authentication`, `sharing`, `exposure`, `embedding`, `lifecycle`, `proxy`, `headers`, `transport`, `advisory` - ne conserve que les constats concernant ce domaine de l'instance ;
- **une catégorie de changement** - `instance`, `referenceData`, `scanner`, `policy`, `unknown` - ne conserve que l'explication de *pourquoi* les deux scans diffèrent. Voir [Données de référence](reference-data.md) pour comprendre pourquoi une note peut changer sans modification de l'instance.

```bash
check-opencloud-scanner diff before.json after.json --category transport
check-opencloud-scanner diff before.json after.json --category instance
```

Chaque espace de noms n'est filtré que lorsqu'une valeur lui est fournie :
`--category transport` laisse l'explication intacte et `--category instance`
laisse les constats intacts. L'option est répétable et une valeur inconnue est
refusée avec le code de sortie `2` plutôt que d'afficher silencieusement une
page vide ; une faute de frappe qui produirait une comparaison vide serait
interprétée comme « rien n'a changé ».

Une explication filtrée omet les lignes `[limitation]`, car elles qualifient
la comparaison entière et non une seule de ses catégories.

**Il se termine avec `1` lorsque le second résultat est moins bon**, ce qui
permet à un pipeline de s'en servir comme barrière. Il se termine avec `0`
lorsque rien n'a empiré, y compris lorsque des constats ont seulement été
corrigés. `--exit-zero` désactive cette barrière.

Il se termine avec `2`, sans rien comparer, dans l'un de ces deux cas :

- **les deux fichiers décrivent des instances différentes.** Pour vérifier
  qu'une correction a fonctionné, comparez des scans de la même instance.
  Passez `--allow-different-hosts` si vous avez bien l'intention de comparer
  des hôtes différents.
- **un fichier n'est pas un document de résultat** produit par `scan`. Par
  exemple, il ne contient pas de note, ou il s'agit de l'entrée d'erreur d'une
  instance qui n'a pas pu être analysée.

## `fleet` - un tableau de bord à partir de résultats enregistrés {#fleet-a-dashboard-from-saved-results}

```bash
today="/var/lib/opencloud-reports/$(date +%F)"
mkdir -p "$today"
for host in cloud1.example.com cloud2.example.com cloud3.example.com; do
  check-opencloud-scanner scan "$host" > "$today/$host.json"
done
check-opencloud-scanner fleet /var/lib/opencloud-reports
check-opencloud-scanner fleet /var/lib/opencloud-reports --format html > fleet.html
```

Elle lit les documents de résultat écrits par `scan` - des fichiers, ou des
répertoires parcourus récursivement à la recherche de `*.json` - et résume le
**rapport le plus récent de chaque hôte**. Elle n'analyse rien et ne stocke
rien : la collecte des rapports, par une tâche cron, un stockage d'artefacts
de CI ou un répertoire partagé, reste à l'outil que vous utilisez déjà.

| Section | Ce qu'elle montre |
|:--|:--|
| Hosts | Une ligne par hôte : version, note, ligne de version, constats en échec et exemptés, lacunes de couverture et âge du rapport |
| Unsupported releases | Les versions en fin de vie, celles dont le support se termine dans la fenêtre, et les versions que le calendrier ne connaît pas |
| Waiver deadlines | Les exemptions temporaires après lesquelles un contrôle en échec alertera de nouveau dans la fenêtre, ou alerte déjà |
| Common findings | Les constats en échec partagés par le plus d'hôtes, les plus graves d'abord |
| Missing coverage | Les hôtes attendus sans rapport, ceux dont le dernier scan a échoué, les rapports trop anciens et ceux sans bloc de couverture |
| Checks not evaluated | Les contrôles que les scans ont ignorés ou n'ont pas pu trancher, et sur combien d'hôtes |

Un rapport décrit le jour où il a été écrit ; deux éléments sont donc
réévalués par rapport à **aujourd'hui** :

- **La version.** La version enregistrée est replacée dans le calendrier des
  versions de cette installation - celui fourni, ou le fichier indiqué dans la
  configuration, comme pour le plugin. Une ligne dont le support s'est terminé
  après le rapport porte la mention `since the scan`. La fin de vie est
  définitive : un rapport qui l'indiquait déjà est toujours listé.
- **L'échéance d'une exemption.** Une exemption active dans le rapport a pu
  expirer depuis. Seule une échéance après laquelle un contrôle alerte
  réellement de nouveau est listée, selon la même règle que
  `--waiver-warning` du plugin.

Les constats fréquents omettent ce qu'aucun administrateur ne peut changer :
les indicateurs qu'OpenCloud fixe en dur et les en-têtes qu'aucun OpenCloud
n'envoie. Un constat exempté est compté, et la colonne `Waived` indique sur
combien d'hôtes.

| Option | Effet |
|:--|:--|
| `--format text` | Des tableaux alignés. Par défaut |
| `--format markdown` | Des tableaux Markdown, pour un ticket ou un wiki |
| `--format html` | Une page autonome : aucun script, aucune police, rien n'est téléchargé, modes clair et sombre |
| `--format json` | Le résumé structuré, en camelCase comme le document de résultat |
| `--window DAYS` | Afficher les exemptions et les périodes de support qui se terminent dans `DAYS` jours. Par défaut `30` |
| `--stale-after DAYS` | Considérer un hôte comme non couvert si son rapport le plus récent est plus ancien. Par défaut `7`, `0` désactive |
| `--top N` | Lister les `N` constats les plus fréquents. Par défaut `10`, `0` les liste tous |
| `--expect HOST` | Un hôte qui devrait avoir un rapport. Répétable, ou séparé par des virgules |
| `--inventory FILE` | Les hôtes attendus, depuis un fichier, un par ligne, `#` commençant un commentaire |

Un hôte est identifié par son nom et son port : `https://opencloud.example.com/`
et `opencloud.example.com` sont le même hôte, `opencloud.example.com:9200` en
est un autre. Indiquez le port dans `--expect` lorsque l'instance est analysée
sur un port particulier.

La commande se termine avec `0` dès qu'elle a affiché un résumé, quel que soit
l'état de la flotte. Elle se termine avec `2` si elle n'a trouvé aucun
document de résultat et qu'aucun hôte n'était attendu. Un fichier qui n'est
pas un document de résultat n'est pas une erreur ; il est nommé sous
*Files skipped*.

## `explain` - ce que signifie un constat et comment le corriger {#explain-what-a-finding-means-and-how-to-fix-it}

```bash
check-opencloud-scanner explain basicAuthDisabled
```

```text
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so usernames and passwords can be replayed on every request without going through the identity provider, ...
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs it. ...
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
```

Il recherche les identifiants dans le catalogue intégré au paquet. C'est le
même texte que celui affiché par la sortie `--debug` du plugin, par le
résultat de scan et par l'application web. Il ne lit aucune configuration,
n'a besoin d'aucun réseau et n'analyse rien : il fonctionne donc sur n'importe
quel hôte où le paquet est installé.

```bash
check-opencloud-scanner explain cspWithoutUnsafeInline Referrer-Policy   # plusieurs à la fois
check-opencloud-scanner explain exposed:/config/opencloud.yaml          # identifiants paramétrés aussi
check-opencloud-scanner explain --list                                  # tous les identifiants, un par ligne
check-opencloud-scanner explain --list --category cookies               # une seule catégorie
check-opencloud-scanner explain --format json cookieSecure              # pour un script
check-opencloud-scanner explain                                         # le catalogue entier
```

| Option | Fonction |
|:--|:--|
| `--list` | Afficher les identifiants bruts au lieu des explications |
| `--category` | Une seule catégorie : `cookies`, `authentication`, `sharing`, `exposure`, `embedding`, `lifecycle`, `proxy`, `headers` ou `transport` |
| `--format {text,json}` | Le JSON fournit `id`, `category`, `title`, `meaning`, `remediation`, `reference`, `setting` et `actionable` pour chaque entrée |

Un identifiant inconnu du catalogue se termine avec `1` et propose les plus
proches :

```text
ERROR check_opencloud.cli: No catalogue entry for 'cookieSecur'. Did you mean: cookieSecure, cookieSameSite, cookiePrefix? Run `explain --list` for every identifier this build knows.
```

Les identifiants sont ceux que portent les constats dans la ligne d'alerte,
dans `extraChecks[].id` et dans `hardenings`, ainsi que ceux que désigne une
exclusion. Pour un traitement plus long, page par page, voir [Les mesures de
durcissement, une par une](hardening.md) et [Ce que lit le
scanner](scanner-checks.md).

## `review-waivers` - les exemptions à revoir {#review-waivers-waivers-that-need-attention}

```bash
check-opencloud-scanner -c /etc/check-opencloud-security/config.yml review-waivers
```

La commande lit les exemptions que le plugin utiliserait - `scanner.ignore_hardenings` et `scanner.temporary_waivers` dans le fichier de configuration ou leurs variables d'environnement `COS_` - et liste celles qui demandent votre attention, chacune avec une proposition de nettoyage. **Elle ne modifie jamais la configuration.** Décider si un échec reste acceptable revient à la personne qui l'a accepté.

| Type | Signification |
|:--|:--|
| Expired | Une exemption temporaire dont l'échéance est passée. La sortie indique si la vérification alerte de nouveau ou si une exemption plus large la masque encore. |
| Expiring soon | Une exemption temporaire qui expire dans moins de `--expiring-within` jours : le `--waiver-warning` du plugin pour tous les enregistrements à la fois. |
| Unused | Ne correspond à aucune vérification en échec dans le document `--result`. Sans `--result` : ne correspond à aucun identifiant connu, souvent une faute de frappe. Une exemption pour un indicateur qu'OpenCloud fixe dans le code compte aussi, car il n'alerte jamais. |
| Overlapping | Une autre exemption active la couvre déjà : un doublon, un motif plus étroit sous un motif plus large ou, avec `--result`, deux motifs pour la même vérification en échec. Une exemption temporaire sous une exemption permanente est signalée, car son échéance ne change rien. |
| Permanent | Un motif sans raison ni échéance, avec un enregistrement `--waive-until` à copier à sa place. |

```bash
check-opencloud-scanner scan opencloud.example.com > result.json
check-opencloud-scanner review-waivers --result result.json          # tell used from unused
check-opencloud-scanner review-waivers --at 2026-12-01T00:00:00Z     # what will have expired by then
check-opencloud-scanner review-waivers --format json --exit-zero     # for a script
```

| Option | Effet |
|:--|:--|
| `--result FILE` | Un document de résultat de `scan`, pour distinguer les exemptions utilisées des autres ; indique aussi la prochaine échéance qui fera alerter une vérification |
| `--ignore-hardening`, `--waive-until` | Revoir ces valeurs au lieu de celles configurées, comme les options homonymes du plugin les remplacent |
| `--expiring-within DAYS` | Fenêtre de *Expiring soon*. Par défaut : le réglage `waiver_warning`, ou `14` s'il est désactivé ; `0` désactive la section |
| `--at TIMESTAMP` | Revoir à un autre moment ; exige un fuseau horaire, comme une échéance |
| `--format {text,json}` | JSON avec `counts` par type et une entrée par élément avec `kind`, `pattern`, `reason`, `expiresAt`, `detail`, `suggestion` et `related` |
| `--exit-zero` | Toujours terminer avec `0` |

Une exemption peut apparaître sous plusieurs types ; un motif permanent mal orthographié, par exemple, est à la fois *Unused* et *Permanent*.

## `refresh-data` - actualiser le calendrier des versions et les avis de sécurité {#refresh-data-update-the-release-schedule-and-advisories}

```bash
check-opencloud-scanner refresh-data --output-dir /var/lib/check-opencloud-security
```

Il récupère le calendrier des versions et la base d'avis de sécurité
vérifiés depuis le dépôt de ce projet, contrôle leur signature et les écrit
dans `--output-dir`. Il affiche les deux chemins et se termine avec `0`. En
cas d'échec, il n'écrit rien et se termine avec `1`.

| Option | Valeur par défaut | Fonction |
|:--|:--|:--|
| `--output-dir` | `~/.cache/check-opencloud-security` | Emplacement des deux fichiers |
| `--timeout` | `30` | Secondes accordées à chaque requête |
| `--schedule-url` | *(aucune)* | Une page de cycle de vie ou un miroir, récupéré sans vérification |
| `--advisory-url` | *(aucune)* | Un point d'accès OSV ou un miroir, récupéré sans vérification |

Ces fichiers restent sans effet tant que la configuration ne les désigne pas.
La vérification de signature nécessite l'extra `signing`. Un piège est facile
à manquer : un fichier de calendrier que le contrôle ne peut pas lire
désactive la vérification de fin de vie. Tout cela est traité dans [Maintenir
à jour le calendrier des versions et les avis de
sécurité](reference-data.md).

## `serve` - le service de scan {#serve-the-scan-service}

```bash
check-opencloud-scanner serve
check-opencloud-scanner serve --listen 0.0.0.0 --token "$(cat /run/secrets/scanner_token)"
```

Il exécute le scanner comme un petit service HTTP, afin que plusieurs
consommateurs partagent un résultat mis en cache par instance au lieu de
l'analyser chacun de leur côté.

| Option | Valeur par défaut | Réglage |
|:--|:--|:--|
| `--listen` | `127.0.0.1` | `service.listen` / `COS_SERVICE_LISTEN` |
| `--port` | `8811` | `service.port` / `COS_SERVICE_PORT` |
| `--cache-ttl` | `900` secondes | `service.cache_ttl` / `COS_SERVICE_CACHE_TTL` |
| `--token` | *(aucun)* | `service.token` / `COS_SERVICE_TOKEN` |
| `--concurrency` | `1` | Sondes en parallèle au sein d'un même scan |
| `--insecure` | désactivé | Ne pas vérifier les certificats des instances analysées |

**Écouter ailleurs que sur la boucle locale sans jeton empêche le démarrage.**
Le service affiche `UNKNOWN: ...` sur stderr et se termine avec `3`, un code
qu'un superviseur ne relancera pas indéfiniment. Les points d'accès sont
listés dans le [README principal](../../README.md#running-the-scanner-as-a-service),
et l'exécution en conteneur est traitée dans [Exécuter le scanner comme un
service](scan-service.md).

Le jeton doit alors compter au moins 32 caractères et ne pas être l'exemple de
`secrets/scanner_token.example` : rien ne limite le nombre de tentatives, sa
longueur est donc sa seule protection. `openssl rand -hex 32` en produit un.

Il ne s'agit pas de l'application web publique. Celle-ci est décrite dans
[le service de scan public](../webapp.md).

## `configure` - écrire un fichier de configuration {#configure-write-a-configuration-file}

```bash
check-opencloud-scanner configure
check-opencloud-scanner -c /etc/check-opencloud-security/.env.json configure
```

Il demande les réglages de façon interactive, explique chacun d'eux et les
enregistre en JSON, lisible par le seul propriétaire. Il propose
`./.env.json`, `~/.config/check-opencloud-security/.env.json` et
`/etc/check-opencloud-security/.env.json`, tous des emplacements que la
recherche ci-dessus trouve automatiquement. `-c` indique le chemin à la place.
C'est le même assistant que `check-opencloud-security --configure`.

| Option | Fonction |
|:--|:--|
| `--all` | Parcourir les réglages optionnels sans demander au préalable |
| `--force` | Remplacer un fichier existant sans confirmation |
| `--no-test-scan` | Ne pas proposer de scan de test de l'hôte avant l'enregistrement |
| `--export-monitoring` | Écrire aussi la vérification planifiée : `icinga`, `systemd`, `both` ou `none` |

Il propose ensuite d'écrire également la vérification planifiée, à côté de la
configuration qu'il vient d'enregistrer :

```text
Also write a monitoring configuration (Icinga service, systemd timer)? [y/N]
```

`--export-monitoring` répond à cette question d'avance, ce dont un script de
provisionnement a besoin. Les fichiers portent les seuils, la série de
publication et toutes les autres réponses qui viennent d'être données : la
vérification qui s'exécute chaque jour est donc celle qui a été configurée, et
non un exemple ajusté de mémoire :

```bash
check-opencloud-scanner configure --export-monitoring both
```

| Fichier | Ce que c'est |
|:--|:--|
| `opencloud-security-<host>.conf` | Un objet `Service` Icinga 2. Il lui faut aussi le `CheckCommand` de [`contrib/icinga2/`](../../contrib/icinga2/check_opencloud_security.conf) - le service définit des variables, la commande en fait des options |
| `check-opencloud-security.service` | Une unité `oneshot`, avec les mêmes directives de durcissement que celle de [`contrib/systemd/`](../../contrib/systemd/check-opencloud-security.service) |
| `check-opencloud-security.timer` | `OnCalendar=daily`, avec un délai aléatoire pour que de nombreux hôtes derrière une même adresse n'atteignent pas la limite de débit du flux de publications à la même seconde |
| `check-opencloud-security.env` | Les variables `COS_` de l'unité, écrites en lecture réservée au propriétaire |

La commande écrit les fichiers à côté du fichier de configuration et affiche
les commandes d’installation. Elle n’installe rien. Lisez les fichiers avant
de les installer dans `/etc`.

Les fichiers générés ne contiennent aucun secret. L’URL du webhook et le jeton
de publication restent dans le fichier de configuration, accessible uniquement
à son propriétaire. L’objet Icinga et l’unité systemd désignent ce fichier avec
`vars.opencloud_config` et `COS_CONFIG_FILE`. La commande indique les paramètres
qu’elle exclut des fichiers générés.

## Codes de sortie {#exit-codes}

Ce ne sont **pas** les codes Nagios du plugin. Un `scan` qui trouve une
instance notée F se termine quand même avec `0`, car juger le résultat est le
travail du plugin.

| Sous-commande | `0` | `1` | `2` | `3` |
|:--|:--|:--|:--|:--|
| `scan` | Tous les hôtes ont été analysés | Au moins un hôte n'a pas pu être analysé | Configuration invalide | - |
| `diff` | Rien n'a empiré | Le résultat le plus récent est moins bon | Les fichiers ne peuvent pas être comparés | - |
| `fleet` | Résumé affiché | - | Aucun document de résultat trouvé, ou inventaire illisible | - |
| `explain` | Affiché | Identifiant inconnu ou catégorie vide | - | - |
| `review-waivers` | Rien à nettoyer | Au moins une exemption listée | Exemption, horodatage ou fichier `--result` invalide | - |
| `refresh-data` | Les deux fichiers ont été écrits | Rien n'a été écrit, voir stderr | - | - |
| `serve` | Arrêt normal | - | Configuration invalide | Démarrage refusé, p. ex. une écoute large sans jeton |

Des arguments de ligne de commande invalides se terminent avec `2` pour chaque
sous-commande, comme il est d'usage avec argparse.

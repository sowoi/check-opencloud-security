# Référence de la CLI du scanner
## Démarrage rapide {#quick-start}
Installez le plugin et lancez une vérification, une commande pour chaque étape :

```shell
pipx install check-opencloud-security     # or: uv tool install / pip install
check-opencloud-security --host opencloud.example.com
```

Une instance OpenCloud toute neuve créée avec `opencloud init` sert TLS sur le
port 9200 avec un certificat auto-signé. Dirigez la vérification vers elle et
indiquez-lui de ne pas retenir ce certificat contre l’instance :

```shell
check-opencloud-security --host opencloud.example.com:9200 --insecure
```

Pour une installation permanente (Icinga2, timer systemd, cron, Docker, ...),
voir [Installation](#installation) ci-dessous.

# Fonctionnalités {#features}
- **Ni API, ni tiers.** Chaque contrôle s’exécute dans le processus du plugin,
  contre votre instance. Adresses IP, ports personnalisés et noms d’hôte
  internes fonctionnent tous, et il n’y a aucune limite de débit
- **Détection des mises à jour en attente et de la fin de vie** à partir du
  [flux des versions OpenCloud](#update-check) : une version plus récente
  est-elle disponible sur votre canal, et la version en service reçoit-elle
  encore des correctifs de sécurité - avec des modes hors ligne `pinned` et
  `bundled` pour la supervision isolée
- **Contrôles propres à OpenCloud** : points de terminaison Graph/WebDAV/OCS
  accessibles sans authentification, fichiers `opencloud.yaml`,
  `proxy/server.key` et boltdb exposés, ports de débogage de services
  accessibles (`/metrics`, `/config`, `/debug/pprof`), authentification Basic
  activée et divulgation de version
- **Inspection TLS** : négociation, version du protocole, expiration et
  reconnaissance du certificat, plus un repli automatique HTTPS -> HTTP qui
  signale la dégradation au lieu de la masquer - voir
  [TLS et certificats](tls.md)
- **Durcissement déduit de ce que l’instance signale réellement**, et non deviné
  à partir de son numéro de version : robustesse de HSTS, qualité de la CSP,
  obligation de mot de passe et d’expiration pour les liens publics, paramètres
  d’énumération des utilisateurs et de politique de mot de passe
- Configuration par fichier YAML, variables d’environnement ou fournisseur de
  secrets (secrets Docker/Kubernetes, fichiers, environnement, commandes)
- Codes de sortie Nagios/Icinga standard (OK, WARNING, CRITICAL, UNKNOWN) et
  données de performance (note, nombre de vulnérabilités, durée de l’analyse)
- Seuils de notation configurables pour WARNING et CRITICAL
- Contrôles facultatifs du durcissement et des en-têtes de sécurité
  (`--check-hardening`)
- Notification facultative par webhook lorsqu’une vérification passe en critique
- Nouvelle tentative automatique avec attente exponentielle en cas d’erreur
  réseau passagère
- Prise en charge des proxies web, débogage, exécutions sur plusieurs hôtes
- Installable avec pipx/uv/pip - ou sous forme d’image Docker prête à l’emploi

# Prérequis {#prerequisites}
- Python 3.11 ou plus récent - ou Docker, si vous préférez la voie conteneurisée.
- `requests` et `PyYAML`, installés automatiquement par pipx/uv/pip.
- Un accès réseau de l’hôte de supervision vers l’instance OpenCloud.
  Contrairement à un scanner hébergé, ce plugin doit atteindre l’instance
  elle-même - c’est précisément ce qui le rend utilisable pour des instances qui
  ne sont pas sur Internet.

# Installation {#installation}
Deux commandes couvrent le cas courant. Tout le reste - maintenir le paquet à
jour, la complétion dans le shell, l’installation depuis une copie du dépôt, la
construction de l’image par vos soins et les définitions d’objets
Icinga2/Nagios - se trouve dans **[Installer le plugin](installation.md)**.

```shell
pipx install check-opencloud-security          # or: uv tool install / pip install
check-opencloud-security --host opencloud.example.com
```

Sur un hôte de supervision, où les logiciels doivent arriver par le gestionnaire
de paquets et figurer dans l’inventaire, chaque version fournit aussi un `.deb`
et un `.rpm` :

```shell
sudo apt install ./check-opencloud-security_<version>_all.deb       # Debian, Ubuntu
sudo dnf install ./check-opencloud-security-<version>-1.noarch.rpm  # RHEL, Fedora
```

Les deux installent la vérification dans `/usr/lib/nagios/plugins/`. La
configuration de la supervision est une étape distincte ; voir [Installer le
plugin](installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm).

Vous préférez ne pas installer Python sur l’hôte ? L’image publiée contient les
deux points d’entrée :

```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

Cette ligne, sa variante JSON et les options utiles qui l’accompagnent sont
réunies dans [Analyser en une ligne de commande](docker.md). La
commande par défaut de l’image démarre l’application web, c’est pourquoi le
plugin est sélectionné avec `--entrypoint`.

| Méthode | Où elle est décrite |
|:------|:-----------------------|
| pipx / uv / pip, et `--upgrade-self` | [Installer le plugin](installation.md#using-pipx-uv-pip-recommended) |
| `.deb` et `.rpm`, pour un hôte de supervision | [Installer le plugin](installation.md#debian-ubuntu-rhel-fedora-deb-and-rpm) |
| Complétion dans le shell | [Installer le plugin](installation.md#shell-completion) |
| Docker, et construction de l’image | [Installer le plugin](installation.md#docker) |
| Objets Icinga2 et Nagios | [Installer le plugin](installation.md#icinga2-nagios) |
| Icinga Director, par l’interface web | [Icinga Director](icinga-director.md) |
| Ansible, systemd, cron, Kubernetes | [Guides de déploiement](../README.md#deploying-it) |

Chaque version est livrée avec un SBOM CycloneDX et une attestation de
provenance Sigstore ; voir
[Vérifier ce que vous avez téléchargé](../../SECURITY.md#verifying-what-you-downloaded)
si vous préférez ne pas faire confiance à l’artefact sans vérification.

Maintenir le paquet à jour compte davantage ici que pour un plugin qui interroge
un service hébergé : le calendrier des versions OpenCloud et la dernière version
connue sont livrés *dans* le paquet (voir
[Détection de fin de vie](#end-of-life-detection)).

# Utilisation de la CLI {#cli-usage}
- `check-opencloud-security -h` affiche le manuel.

## Commande {#command}
```shell
check-opencloud-security --host <Hostname> --check-hardening
```

## Options {#options}

La [référence des options de la CLI](cli-reference.md) liste chaque option,
sa valeur par défaut et la variable d’environnement correspondante. Utilisez
`--help` pour voir les mêmes options regroupées par tâche.

Les principaux groupes couvrent les cibles, les sondes, les seuils de notation,
les informations de version, les comparaisons, l’exécution, la sortie et les
notifications.

Les quelques options que vous taperez le plus souvent :

| Option | Description |
|:-------|:------------|
| `-H, --host` | L’instance à vérifier. Nom d’hôte, IP ou URL, éventuellement avec un port ; séparées par des virgules pour plusieurs |
| `-d, --debug` | Expliquer en détail la note et chaque constat |
| `--check-hardening` | Signaler aussi les mesures de durcissement et en-têtes de sécurité manquants |
| `-w, --warning` / `-c, --critical` | Les notes (0-5) à partir desquelles, ou en dessous desquelles, la vérification avertit ou passe en critique |
| `--profile` | Juger selon un profil de seuils nommé - `strict`, `ops` ou `lenient` - au lieu de définir chaque option |
| `--policy` | Fichier de politique des exigences de l’organisation ; toute exigence non satisfaite est CRITICAL |
| `--format` | `nagios`, `prometheus`, `otlp`, `checkmk`, `summary`, `json`, `sarif` ou `junit` |
| `--ignore-hardening` | Accepter, par son nom, un constat que vous ne corrigerez pas |
| `--waive-until` | En accepter un jusqu’à une échéance, avec une raison ; il déclenche de nouveau une alerte ensuite |
| `--baseline` / `--warn-on-new` | N’alerter que sur les constats nouveaux ou aggravés depuis la dernière exécution |
| `--verify-remediation` | Après une correction, ne remesurer que les constats indiqués au lieu d’une analyse complète |

L’ordre de priorité est toujours **option de ligne de commande > variable
d’environnement > [fichier de configuration](#configuration-file-and-secrets) >
valeur par défaut**.

# Vérifier une correction {#verifying-a-fix}
Après avoir modifié un paramètre - un en-tête dans le reverse proxy, un chemin
qu’il devrait cesser de servir -, inutile d’attendre une analyse complète pour
savoir si cela a fonctionné. `--verify-remediation` prend les identifiants de
constats indiqués par la sortie complète et n’exécute que les sondes qui les
mesurent :

```shell
check-opencloud-security --host opencloud.example.com \
  --verify-remediation Strict-Transport-Security,corsOriginRestricted
```

L’option peut être répétée et accepte des identifiants séparés par des virgules.
Une racine de famille comme `exposed`, `authentication`, `debugEndpoint` ou
`versionDisclosure` revérifie chaque membre (`exposed:/.env`, ...). Le code de
sortie indique si la correction a pris effet :

| Résultat | Code de sortie |
|:-------|:----------|
| Chaque identifiant réussit désormais | `OK` |
| Un identifiant échoue encore | `WARNING`, ou `CRITICAL` lorsque ce contrôle est de gravité élevée ou critique |
| Un identifiant ne peut être tranché que par une analyse complète | `UNKNOWN` |

Les constats qui dépendent de l’ensemble - `eol`, `vulnerability:...`,
`httpsAvailable` et les contrôles de parité d’adresses - sont signalés comme non
vérifiables au lieu d’être devinés ; c’est aussi le cas d’un identifiant que
cette version ne connaît pas. L’exécution ne produit aucune note, ne touche
jamais à une référence et n’envoie jamais de webhook : une mesure partielle n’est
pas un état de l’instance. Les exemptions ne sont pas appliquées non plus, car la
question est de savoir si le contrôle lui-même réussit désormais.
`--format json` affiche plutôt le document de mesure ; la même fonction est
disponible en Python sous `opencloud_local_scan.verification.verify`.

# Vérifier plusieurs hôtes {#checking-multiple-hosts}
`--host` (et `COS_HOST`) accepte une liste de noms d’hôte séparés par des
virgules, par exemple :

```shell
check-opencloud-security --host opencloud1.example.com,opencloud2.example.com
```

Les hôtes sont analysés en parallèle : le plugin crée un worker par hôte,
jusqu’au plafond par défaut de cinq. Une vérification sur un seul hôte reste
strictement monothread, sans groupe de workers. Définissez `--concurrency` ou
`COS_CONCURRENCY` pour abaisser ou relever ce plafond (jusqu’à 32), par exemple
`--concurrency 2` pour au plus deux hôtes à la fois. Chaque worker conserve son
résultat et ses données de performance Nagios séparément ; la sortie commence par
un résumé d’une ligne (par exemple
`Checked 2 host(s): overall CRITICAL (1 CRITICAL, 1 OK)`), suivi d’un bloc de
résultat par hôte, dans l’ordre de la saisie. Le plugin se termine avec le pire
état rencontré sur l’ensemble des hôtes, selon la priorité habituelle de
Nagios/Icinga : `CRITICAL` > `WARNING` > `UNKNOWN` > `OK`. Un hôte unique produit
toujours la sortie d’origine en un seul bloc et le même code de sortie : les
configurations existantes à un seul hôte ne sont pas affectées. Dès que les
instances cessent de se ressembler, un fichier de configuration par instance
passe mieux à l’échelle - voir
[Analyser plusieurs instances](many-instances.md).

Les espaces autour de chaque nom d’hôte sont ignorés, et les entrées vides (par
exemple dues à une virgule finale) sont écartées. Comme aucune API hébergée
n’intervient, chaque entrée peut être un nom d’hôte, une adresse IPv4, une
adresse IPv6 entre crochets ou une URL complète, avec ou sans port :
`--host 10.0.0.5:9200,[2001:db8::1],https://cloud.example.com/`.

# Toute une flotte dans un seul tableau {#reading-a-fleet-in-one-table}

Les blocs de résultat par hôte sont écrits pour un système de supervision, et
une douzaine d’entre eux, c’est beaucoup à lire. `--format summary` affiche la
même exécution sous la forme d’une ligne alignée par hôte :

```shell
check-opencloud-security \
  --host opencloud1.example.com,opencloud2.example.com \
  --format summary
```

```text
HOST                    GRADE  VERSION  EOL   VULNS  NEW
opencloud1.example.com  A+     7.2.4    no    0      -
opencloud2.example.com  F      6.9.1    YES   3      -

Checked 2 host(s): overall CRITICAL (1 CRITICAL, 1 OK)
```

Les colonnes sont la note décidée par ce plugin, la version mesurée par
l’analyse, l’état du cycle de vie, le nombre d’avis de sécurité applicables et ce
qui a changé depuis la référence. Les lignes conservent l’ordre dans lequel les
hôtes ont été indiqués, et la dernière ligne reprend le décompte par lequel
commence la sortie Nagios. Le code de sortie est inchangé - le pire état de la
flotte - : ce format reste donc utilisable depuis une tâche cron qui envoie sa
sortie par e-mail.

`EOL` affiche `YES` après la fin de vie, `soon` dans la fenêtre
[`--eol-warning-days`](#options), et `no` sinon. `NEW` nécessite
[`--baseline`](#options) : sans référence, la colonne affiche `-`, car « rien de
nouveau » et « impossible de le savoir » sont deux réponses différentes. Avec une
référence, elle affiche `new` lors de l’exécution qui enregistre la référence,
puis `+n` pour les constats qui n’existaient pas auparavant. Un hôte dont
l’analyse a échoué n’a pas de note : sa cellule `GRADE` contient alors l’état
Nagios (`UNKNOWN`).

Ce format est destiné aux personnes. Pour une machine, utilisez
[`json`, `sarif` ou `junit`](#machine-readable-output-for-ci-jsonsarifjunit),
qui contiennent les mêmes constats sous une forme analysable.

# Mode politique CI {#ci-policy-mode}

`-w`/`-c` et `--profile` jugent une instance sur sa **note**, un nombre unique
qui résume tout ce que l’analyse a mesuré. C’est la bonne forme pour un système
de supervision et la mauvaise pour une barrière de déploiement : une équipe qui
exige l’application de HTTPS et l’absence de comptes de démonstration ne peut pas
l’exprimer sous forme de note.

`--policy` désigne un fichier qui le dit explicitement :

```yaml
minimum_rating: 4
required_hardenings:
  - httpsEnforced
  - corsOriginRestricted
forbidden:
  - demoUsersDisabled
```

```shell
check-opencloud-security --host opencloud.example.com --policy policy.yml
```

```text
CRITICAL: 2 policy violation(s) - required hardening 'httpsEnforced' is not in place (+1 more)
OpenCloud 7.2.4 on opencloud.example.com, rating: A, last scanned: ...
Policy violations (2):
  - required hardening 'httpsEnforced' is not in place
  - forbidden finding 'demoUsersDisabled' is present
```

Les trois clés sont facultatives :

| Clé | Signification |
|:--|:--|
| `minimum_rating` | Un plancher pour la note, de `0` (F) à `5` (A+) |
| `required_hardenings` | Les mesures qui doivent être en place |
| `forbidden` | Les identifiants de constats qui ne doivent pas être présents - un durcissement manquant, un contrôle en échec ou un identifiant de vulnérabilité |

Les identifiants sont ceux que signale l’analyse elle-même ; `--format json` les
liste pour une instance et `--debug` explique chacun d’eux. Un fichier `.json`
est lu comme du JSON, tout autre fichier comme du YAML, et
[`config/policy.example.yml`](../../config/policy.example.yml) est un point de départ
commenté.

Une violation est **CRITICAL**, car il est peu utile de faire échouer un pipeline
avec un état que le pipeline pourrait être configuré pour tolérer. Une politique
ne fait qu’aggraver un verdict : une instance qui satisfait toutes les exigences
conserve ce que les règles de seuils, de durcissement, de cycle de vie et de
référence avaient déjà décidé, et la sortie indique
`Policy: every requirement met`. La charge utile du webhook et `--format json`
contiennent le même verdict sous `policy` : une tâche CI n’a donc pas besoin
d’analyser la ligne d’alerte.

Deux règles sont bonnes à connaître avant d’en écrire une :

* **Une exemption n’excuse pas une exigence.** `--ignore-hardening` et
  `--waive-until` sont l’opérateur local qui accepte un constat ; une politique
  est l’organisation qui dit qu’il ne peut pas être accepté. Si une exemption
  pouvait faire taire une mesure exigée, une politique ne décrirait rien
  d’applicable.
* **Une faute de frappe est une erreur d’utilisation, pas une réussite
  silencieuse.** Une clé inconnue, une note hors de `0`-`5` ou une mesure
  inconnue du catalogue termine l’exécution en `UNKNOWN` avec la raison. Une
  politique existe pour faire échouer des déploiements : une règle qui n’exige
  discrètement rien est le pire résultat possible.

# Intégration Prometheus et Kubernetes {#prometheus-kubernetes-integration}

`--format=prometheus` produit une charge utile texte ponctuelle ; l’exportateur
intégré sert `/metrics` pour une supervision en mode pull, en actualisant chaque
cible configurée lors de la première collecte puis à l’intervalle
`--scrape-interval` (60 secondes par défaut) :

```shell
check-opencloud-security --host opencloud.example.com --format=prometheus

check-opencloud-security --host opencloud.example.com \
  --prometheus-listen-port 9102
```

L’exportateur n’écoute par défaut que sur `127.0.0.1`. Ne définissez
`--prometheus-listen-addr 0.0.0.0` que lorsqu’un pare-feu ou une politique réseau
limite qui peut le collecter - c’est aussi ce dont un conteneur ou un Deployment
Kubernetes a besoin, en plus de la publication du port `9102`.

Il publie `opencloud_security_rating_score`,
`opencloud_security_vulnerabilities_total`,
`opencloud_security_hardenings_missing_total`,
`opencloud_security_failed_extra_checks_total`,
`opencloud_security_support_days_remaining`,
`opencloud_security_update_available`,
`opencloud_security_scan_duration_seconds` et
`opencloud_security_scrape_success`. Le label `host` identifie la cible
configurée ; la note porte aussi `domain`, `product` et `version`.

`--format=otlp` fournit ces mêmes métriques au format OTLP/JSON - une seule
`ExportMetricsServiceRequest` quel que soit le nombre d’hôtes analysés, ce
qu’accepte un collecteur OpenTelemetry sur `/v1/metrics` :

```shell
check-opencloud-security --host opencloud.example.com --format=otlp \
  | curl -sf -X POST http://collector.example.com:4318/v1/metrics \
      -H 'Content-Type: application/json' --data-binary @-
```

Les deux formats de métriques signalent une analyse échouée par
`opencloud_security_scrape_success 0` et se terminent avec `0`, car un collecteur
qui ne reçoit plus d’échantillons ne peut pas distinguer une instance injoignable
d’une tâche cron arrêtée sans que personne ne le remarque. Utilisez
`--format nagios` lorsque c’est le code de sortie qui compte.

Le [guide Prometheus et Grafana](prometheus.md) contient le ServiceMonitor,
les règles d’alerte, ce qu’il faut représenter en graphique, la recette OTLP et
les anciennes méthodes textfile/Pushgateway ; [Kubernetes](kubernetes.md)
contient les manifestes et le chart Helm.

# Sortie lisible par machine pour la CI (json/sarif/junit) {#machine-readable-output-for-ci-jsonsarifjunit}

`--format json`, `--format sarif` ou `--format junit` affichent un seul document
combiné pour tous les hôtes analysés - jamais un par hôte, même pour un seul -,
si bien que la sortie est toujours un JSON/SARIF/XML valide. **Le code de sortie
conserve sa signification Nagios quel que soit le format** (`0`/`1`/`2`/`3`) :
une étape de CI peut donc s’appuyer dessus exactement comme une vérification
Icinga ; le document est un artefact séparé et supplémentaire.

- `json` est un tableau JSON du document décrit dans
  [Notifications par webhook](#webhook-notifications), un objet par hôte.
- `sarif` est du SARIF 2.1.0, destiné à un tableau de bord d’analyse de code.
  Ses constats proviennent des mêmes faits que la sortie texte du plugin : un
  résultat SARIF ne dit donc jamais rien que la ligne Nagios ne dirait pas.
  Chacun porte la phrase de correction et le lien de documentation du catalogue,
  sa gravité et sa catégorie, la plage de versions concernée par un avis de
  sécurité, et une empreinte qui fait qu’un même constat reste une seule alerte
  d’une exécution à l’autre.
- `junit` est du XML JUnit avec un `<testsuite>` par hôte et un `<testcase>` par
  constat, plus un cas `rating` toujours présent pour qu’un hôte sans problème
  apparaisse quand même.

```shell
check-opencloud-security --host opencloud.example.com --format sarif \
  > opencloud-security.sarif
```

[`docs/output-formats.md`](output-formats.md) compare toutes les valeurs de
`--format`, y compris `nagios` et `prometheus`, et
[Pipelines CI](ci.md) contient les étapes GitHub Actions et GitLab CI qui
téléversent le fichier.

# Checkmk {#checkmk}

Checkmk peut exécuter ce plugin de deux façons, et le choix dépend de l’endroit
d’où il doit s’exécuter :

- **Comme vérification active sur le serveur Checkmk.** Rien de particulier
  n’est nécessaire : Checkmk lit nativement la ligne Nagios et ses données de
  performance. Ajoutez la ligne de commande sous *Setup > Services > Other
  services > Integrate Nagios plugins*.
- **Comme vérification locale sur un hôte doté de l’agent**, ce qu’il vous faut
  lorsque l’instance n’est accessible que depuis un réseau où le serveur Checkmk
  ne se trouve pas. `--format checkmk` écrit la ligne propre à l’agent - état,
  nom du service, métriques, détail -, une par hôte de `--host` :

  ```shell
  check-opencloud-security --host opencloud.example.com --format checkmk
  ```

  ```text
  0 "OpenCloud_Security_opencloud.example.com" rating=5|vulnerabilities=0|… OK: Server is up to date…
  ```

  [`contrib/checkmk/opencloud_security`](../../contrib/checkmk/opencloud_security) est
  cet appel sous forme de script prêt à installer.

C’est l’instance analysée qui donne son nom au service, car l’hôte qui exécute
l’agent est rarement l’instance analysée. **Installez la vérification locale dans
un sous-répertoire numérique** - `local/3600/` -, sinon elle s’exécute à chaque
appel de l’agent, une fois par minute, contre l’instance de production de
quelqu’un. [`docs/checkmk.md`](checkmk.md) décrit en détail les deux
méthodes, les métriques et la signification des états.

# Action GitHub {#github-action}

[`action.yml`](../../action.yml) exécute la même vérification sous forme d’étape : un
workflow peut ainsi analyser une instance de façon planifiée sans rien installer
lui-même. **L’exécuteur doit pouvoir atteindre l’instance** : un exécuteur
hébergé ne voit rien derrière votre pare-feu, c’est à cela que sert un
exécuteur auto-hébergé, et ce que l’analyse mesure concernant TLS, l’application
de HTTPS et les ports de débogage accessibles correspond à ce que voit une
personne extérieure depuis le réseau de l’exécuteur.

```yaml
name: OpenCloud security check

on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: sowoi/check-opencloud-security@v1.18.2
        with:
          target: opencloud.example.com
          # Raises GitHub's anonymous rate limit for the release feed. The
          # token the job already has is enough; it needs no scopes.
          releases-token: ${{ github.token }}
```

**Fixez le tag.** Le calendrier des versions et la dernière version OpenCloud
connue sont livrés *dans* le paquet : la version exécutée fait donc partie du
verdict. `@v1.18.2` installe la 1.18.2, tandis qu’une branche ou un SHA de
commit installe la dernière version publiée le jour de l’exécution du workflow,
et le signale par une annotation d’avertissement.

| Entrée | Valeur par défaut | Fonction |
| --- | --- | --- |
| `target` | *obligatoire* | L’instance à analyser, sous forme de nom d’hôte ou d’URL. |
| `version` | le tag fixé | La version de la vérification à installer. |
| `format` | `json` | `json`, `sarif`, `junit` ou `nagios`. |
| `output-file` | `opencloud-security.json` | Le fichier dans lequel la sortie est écrite. |
| `fail-on` | `warning` | `warning`, `critical` ou `never`. |
| `warning` | valeur par défaut du plugin | Note à partir de laquelle, ou en dessous de laquelle, le résultat est WARNING. |
| `critical` | valeur par défaut du plugin | Note à partir de laquelle, ou en dessous de laquelle, le résultat est CRITICAL. |
| `check-hardening` | `true` | Prendre en compte les mesures de durcissement dans le résultat. |
| `ignore-hardening` | aucune | Identifiants de durcissement à exempter, séparés par des virgules. |
| `waive-until` | aucune | Exempter un constat jusqu’à une échéance : `PATTERN\|EXPIRES\|REASON`. Répétable. |
| `release-track` | `auto` | `auto`, `rolling`, `production` ou `lts`. |
| `releases-token` | aucun | Un jeton pour la limite de débit du flux des versions ; aucune portée nécessaire. |
| `summary` | `true` | Écrire le résultat dans le résumé de la tâche. |
| `extra-args` | aucun | D’autres options du plugin, transmises telles quelles. |

Par défaut, l’étape échoue pour tout résultat pire qu’OK. `fail-on: critical`
tolère un WARNING mais échoue toujours sur CRITICAL et sur UNKNOWN, car une
analyse qui ne s’est pas exécutée n’est pas une réussite ; `fail-on: never`
réussit toujours et laisse la décision à une étape ultérieure qui lit les
sorties :

| Sortie | Contenu |
| --- | --- |
| `exit-code` | Le code de sortie Nagios : `0` OK, `1` WARNING, `2` CRITICAL, `3` UNKNOWN. |
| `status` | `OK`, `WARNING`, `CRITICAL` ou `UNKNOWN`. Uniquement avec `format: json`. |
| `rating` | La note, de 0 à 5. Uniquement avec `format: json`. |
| `rating-label` | La note en lettres : `A+`, `A`, `C`, `D`, `E` ou `F`. Uniquement avec `format: json`. |
| `message` | Le résumé d’une ligne. Uniquement avec `format: json`. |
| `result-file` | Le fichier dans lequel la sortie a été écrite. |

La configuration est transmise au plugin par des variables d’environnement
`COS_*` plutôt que sur la ligne de commande, pour qu’une cible ne se retrouve pas
dans un journal public.

[Pipelines CI](ci.md) couvre le reste : envoyer `format: sarif` au tableau
de bord d’analyse de code, publier le résultat sans faire échouer la tâche, et
l’équivalent GitLab CI.

# Variables d’environnement {#environment-variables}
Chaque option a un équivalent sous forme de variable d’environnement préfixée
par `COS_` (voir le tableau ci-dessus). C’est particulièrement utile pour Docker,
systemd et cron, où définir des variables d’environnement est souvent plus
pratique que modifier une ligne de commande. **Une option explicite de la ligne
de commande l’emporte toujours sur sa variable d’environnement.**

```shell
export COS_HOST=opencloud.example.com
export COS_PROXY=http://proxy.example.com:3128
check-opencloud-security
```

Les analyses ne lisent ni `.netrc`, ni `HTTP_PROXY`, ni `HTTPS_PROXY`, ni les
variables d’environnement de bundle CA de Requests. Configurez explicitement un
proxy avec `--proxy`/`COS_PROXY` et une autorité de certification privée avec
`--ca-file`/`COS_SCANNER_TLS_CA_FILE`. L’envoi restreint des webhooks épingle ses
adresses validées et ne peut pas utiliser de proxy qui résout les noms ; faire
passer un webhook par un proxy exige la dérogation explicite
`--allow-private-webhooks`.

Les variables booléennes (`COS_DEBUG`, `COS_CHECK_HARDENING`, `COS_INSECURE`,
...) acceptent `1`, `true`, `yes` ou `on` (sans tenir compte de la casse) pour
activer l’option correspondante ; toute autre valeur (y compris une variable non
définie ou vide) est considérée comme désactivée.

Les mêmes valeurs peuvent aussi provenir d’un fichier YAML ou d’un fournisseur de
secrets - voir [Fichier de configuration et secrets](#configuration-file-and-secrets).

# Le scanner intégré {#the-built-in-scanner}
Le plugin n’a **qu’un seul** backend : le scanner de
[`opencloud_local_scan/`](scanner.md), qui s’exécute dans le
processus du plugin et établit lui-même le verdict.

Le scanner se connecte depuis l’hôte où vous exécutez le plugin. Il peut donc
vérifier des adresses privées et des noms d’hôte internes sans envoyer la cible
ni ses résultats à un service d’analyse hébergé.

Il n’y a rien à activer et aucune option `--scan-backend` à passer. Tout ce qui
suit décrit ce que fait le scanner intégré et comment l’ajuster.

## Ce que vérifie le scanner {#what-the-scanner-checks}

Le scanner lit `/status.php`, les capacités, les en-têtes de sécurité et la
découverte OIDC, puis sonde des chemins et des ports qui devraient exiger une
authentification ou rester privés. Des contrôles supplémentaires couvrent TLS,
DNS, les cookies, CORS, TRACE, les fichiers exposés, les services de débogage et
les paramètres d’iframe. Il teste aussi les identifiants de démonstration publiés
auprès du fournisseur d’identité propre à l’instance. Utilisez
`--no-extra-checks` pour désactiver les sondes supplémentaires.

Un contrôle supplémentaire en échec limite la note (critical -> `D`, high -> `C`,
medium -> `A`, low -> `A+`) ; définissez `scanner.extra_checks_rating: false`
pour les signaler sans toucher à la note.

**[Ce que le scanner lit, et ce qu’il ne lit volontairement pas](scanner-checks.md)**
est l’inventaire complet : chaque point de terminaison, chaque contrôle et sa
gravité, les observations enregistrées mais jamais notées - qui connecte les
utilisateurs, ce qui se trouve devant l’instance, quelles intégrations
bureautiques et d’agenda sont visibles -, la façon de lire correctement la
version, les ports de débogage sondés, et les questions auxquelles une analyse
externe ne peut pas répondre.

La logique de chaque groupe de contrôles a sa propre page :
[`docs/csp.md`](csp.md), [`docs/tls.md`](tls.md),
[`docs/cookies.md`](cookies.md),
[`docs/authentication.md`](authentication.md),
[`docs/sharing.md`](sharing.md), [`docs/exposure.md`](exposure.md),
[`docs/embedding.md`](embedding.md),
[`docs/lifecycle.md`](lifecycle.md) et
[`docs/status-php.md`](status-php.md).

Tout ce qu’une analyse ne peut pas voir - le journal d’audit, le pare-feu, la
politique de votre fournisseur d’identité, vos sauvegardes - est traité dans
**[Exploiter OpenCloud dans une infrastructure sécurisée](secure-deployment.md)**.

## TLS et certificats auto-signés {#tls-and-self-signed-certificates}

Le proxy d’OpenCloud termine lui-même TLS sur le port 9200, et `opencloud init`
génère un certificat auto-signé pour lui. De nombreux déploiements placent
ensuite devant lui un reverse proxy doté d’un vrai certificat ; beaucoup d’autres
non. Consultez [`docs/tls.md`](tls.md) pour tous les contrôles TLS et de
certificat de ce scanner, et l’importance de chacun.

Le scanner gère les deux cas sans qu’on lui dise lequel il observe :

1. HTTPS avec vérification du certificat. Si cela fonctionne, tout va bien.
2. HTTPS sans vérification. L’analyse continue et signale `tlsTrusted` comme
   contrôle en échec : vous obtenez quand même le résultat complet, ainsi que le
   fait que la chaîne n’est pas reconnue.
3. HTTP simple, signalé comme `httpsAvailable` (critical).

`--insecure` (`COS_INSECURE`) saute l’étape 1. La chaîne non reconnue figure
toujours dans la sortie ; elle cesse simplement de peser sur la note. Utilisez-la
pour une instance que vous savez auto-signée, afin qu’un certificat réellement
défaillant ailleurs reste visible.

## Ports de débogage {#debug-ports}

Chaque service OpenCloud dispose d’un écouteur de débogage qui sert `/healthz`,
`/readyz`, `/metrics`, `/config` et `/debug/pprof`. Ces écouteurs sont liés à
l’interface de bouclage par défaut : un port de débogage qui répond depuis votre
hôte de supervision est donc un vrai constat, généralement un conteneur qui a
publié toute la plage de ports. Le scanner sonde les cinq plus révélateurs
(9205, 9141, 9124, 9134, 9239), chacun par une seule connexion TCP avec un délai
d’attente de trois secondes : un hôte protégé par un pare-feu coûte donc jusqu’à
15 secondes.

```yaml
scanner:
  check_debug_ports: true
  debug_ports: [9205, 9141]
  debug_port_timeout: 1
  concurrency: 8            # run the probes in parallel instead
```

Désactivez-les entièrement avec `--no-debug-ports`. La correspondance entre ports
et services, et la façon dont `scanner.concurrency` raccourcit une exécution sans
changer le verdict, sont décrites dans
[Ports de débogage](scanner-checks.md#debug-ports).

## Toutes les adresses résolues {#every-resolved-address}

Une analyse se connecte au nom une seule fois et voit l’adresse que le résolveur
a placée en premier. Derrière un groupe de nœuds, c’est un seul nœud : celui qui a
manqué un déploiement de configuration - pas de HSTS, comptes de démonstration
toujours actifs, version plus ancienne - sert une partie de vos visiteurs et
aucune de vos analyses. `tlsAddressParity` ne le voit pas non plus, car il ne
compare que l’identité TLS des points de terminaison IPv4 et IPv6.

`--login-throttling` (`COS_LOGIN_THROTTLING`, `scanner.check_login_throttling`)
envoie six connexions échouées pour un compte qui ne peut pas exister et indique
si elles ont été limitées - jamais noté, désactivé par défaut ; voir
[Connexions échouées](scanner-checks.md#failed-sign-ins-opt-in).

`--all-addresses` (`COS_ALL_ADDRESSES`, `scanner.check_all_addresses`) répète les
contrôles de version, d’en-têtes, de durcissement et de comptes de démonstration
sur chaque adresse vers laquelle le nom se résout, et signale `addressParity`
lorsqu’ils divergent :

```
addressParity (high): Differs from 198.51.100.1 - 198.51.100.4: version 7.1.0 (expected 7.2.3); headers Strict-Transport-Security fails
```

Chaque requête porte toujours votre nom d’hôte dans `Host` et SNI ; seule
l’adresse de connexion change, et les adresses proviennent uniquement de la
réponse du résolveur pour ce nom. La première adresse sert de référence. La
gravité du constat est celle de la pire différence - des comptes de démonstration
actifs sur un nœud prennent la gravité de ce constat, une autre version est
`high`, toute autre dérive est `medium` -, et une adresse qui se résout mais ne
répond pas le fait aussi échouer. Les en-têtes et contrôles exemptés sont exclus
de la comparaison.

Cette option est désactivée par défaut : elle coûte environ une douzaine de
requêtes par adresse, dont une connexion de démonstration, et un nom avec une
seule adresse - la plupart des déploiements - n’a rien à comparer et ne reçoit
aucun constat. Elle voit ce que voit le DNS : des nœuds derrière une seule adresse
de répartiteur de charge, ou un résolveur qui renvoie un sous-ensemble tournant
du groupe, restent hors de portée. Les adresses IPv6 sont ignorées lorsque
`scanner.ipv6_enabled` est désactivé. Le service web public ne la propose jamais ;
voir [l’ADR 0042](../../adr/0042-every-resolved-address-is-compared-only-when-the-operator-asks.md).

## Détection de fin de vie {#end-of-life-detection}

Un numéro de version seul ne vous dit pas si une instance OpenCloud reçoit encore
des correctifs de sécurité, car OpenCloud maintient trois types de versions en
même temps :

| Canal          | Rythme                          | Pris en charge jusqu’à                 | Support         |
|:---------------|:--------------------------------|:---------------------------------------|:----------------|
| **Rolling**    | environ toutes les 3 semaines   | la sortie de la version suivante       | communauté      |
| **Production** | environ tous les 6 mois         | la version de production suivante      | professionnel   |
| **LTS**        | une ligne de production         | 2 ans après l’ouverture de la ligne    | professionnel   |

Consultez le [cycle de vie des versions OpenCloud][lifecycle] pour la description
de référence.

[lifecycle]: https://docs.opencloud.eu/docs/admin/resources/lifecycle/

L’état actuel des canaux, tiré directement du calendrier fourni :

<!-- release-schedule:start -->
<!-- Generated by scripts/update_release_schedule.py. Do not edit by hand: the release workflow rewrites this block. -->

| Track | Current release | Line | Line opened | Supported until |
|:------|:----------------|:-----|:------------|:----------------|
| **Rolling** | `8.0.1` | `8.0` | 2026-09-15 | the next rolling release |
| **Production** | `7.2.4` | `7.2` | 2026-06-25 | the next production release |
| **LTS** | `4.0.8` | `4.0` | 2025-12-01 | 2027-12-01 |

Read from the [OpenCloud release lifecycle][lifecycle] on 2026-09-21.
<!-- release-schedule:end -->

Une ligne qui n’est plus prise en charge est notée `F` et signalée en
`CRITICAL` :

```
CRITICAL: The 7.3 rolling release line is end-of-life and has no security fixes. Upgrade to 7.4.0.
OpenCloud 7.3.0 on cloud.example.com, rating: F, last scanned: 2026-08-12 15:18:08.839323
Release lifecycle: 7.3 (rolling), out of support since 2026-08-03, upgrade to 7.4.0
```

Une ligne prise en charge indique le temps restant, ce qui donne tout son intérêt
à la supervision d’une instance LTS :

```
Release lifecycle: 4.0 (lts), supported until 2027-12-01 (476 days left)
```

La période restante est aussi publiée dans la valeur de performance
`support_days_left` : un graphique la montre diminuer, puis devenir négative
une fois la ligne dépassée. Avec `--eol-warning DAYS`, cette valeur porte cette
période comme plage d’avertissement et la fin de vie elle-même comme plage
critique.

```yaml
scanner:
  use_release_schedule: true      # false disables the EOL check entirely
  # release_schedule: /etc/check-opencloud-security/schedule.json
```

Ou par l’environnement : `COS_SCANNER_USE_RELEASE_SCHEDULE`,
`COS_SCANNER_RELEASE_SCHEDULE`.

Pourquoi la *même* version peut être à jour sur un canal et abandonnée depuis
longtemps sur un autre, comment le calendrier est construit et actualisé, et ce
qui se passe lorsqu’une instance est plus récente que le fichier auquel elle est
comparée : tout cela est expliqué dans
**[Canaux de versions, fin de vie et recommandation de mise à jour](release-lifecycle.md)**.

## Base des avis de sécurité {#advisory-database}
Les vulnérabilités connues sont mises en correspondance avec la plage de
versions `[introduced, fixed)` d’une base locale d’avis de sécurité. Les sources
sont fusionnées dans cet ordre et dédupliquées par identifiant :

1. le fichier fourni avec le paquet,
2. chaque fichier de `scanner.vulnerability_db`,
3. le flux JSON de `scanner.vulnerability_feed`.

Le format natif (`{"advisories": [{"id": ..., "introduced": ...,
"fixed": ...}]}`), le format de l’API GitHub Advisory et les documents OSV sont
tous compris : une installation isolée peut donc copier un flux dans un fichier
sans conversion. Un flux injoignable est journalisé puis ignoré ; il ne
transforme jamais une instance saine en `UNKNOWN`.

> **La base fournie n’est complète que dans la mesure où les avis publiés le
> sont.** Peu d’avis ont été publiés pour OpenCloud jusqu’ici.
> `GHSA-vf5j-r2hw-2hrw` (corrigé dans 4.0.3 et 5.0.2) en fait partie, et la base
> est régénérée à partir d’OSV à mesure que de nouveaux avis paraissent.
> `vulnerabilities: []` signifie donc « rien dans la base configurée n’a
> correspondu », et non « cette version est connue comme sûre ». L’essentiel de
> la note vient des contrôles de configuration ci-dessus. Pour prendre en compte
> les avis publiés après la construction de votre paquet, voir
> [Maintenir à jour le calendrier des versions et les avis](reference-data.md),
> ou faites pointer `scanner.vulnerability_feed` vers OSV ou votre propre miroir
> d’avis.

## Exécuter le scanner comme service {#running-the-scanner-as-a-service}

Le paquet fournit un second point d’entrée, `check-opencloud-scanner`. Il exécute
exactement le même scanner, soit une fois, soit comme service :

```shell
# one-shot: print the full result document as JSON
check-opencloud-scanner scan opencloud.example.com

# as a service, on this machine only
check-opencloud-scanner serve --port 8811
```

| Point de terminaison               | Comportement                                        |
|:-----------------------------------|:----------------------------------------------------|
| `POST /api/queue` (`url=<host>`)   | Analyse l’hôte, renvoie `{"uuid": ...}`             |
| `GET /api/result/<uuid>`           | Renvoie le résultat enregistré                      |
| `POST /api/requeue` (`url=<host>`) | Vide le cache et relance l’analyse                  |
| `GET /api/scan?url=<host>`         | Raccourci : analyse et renvoie le document          |
| `GET /healthz`                     | Sonde de vivacité                                   |

Le plugin n’utilise **pas** ce service : il n’a pas de backend distant et analyse
toujours dans son propre processus. Le service existe pour que plusieurs
consommateurs (un tableau de bord, un script, un second système de supervision)
puissent partager un même résultat en cache, et pour que les analyses puissent
s’exécuter depuis un hôte plus proche de l’instance que le serveur de
supervision. Les résultats sont mis en cache par hôte pendant
`service.cache_ttl` secondes, 15 minutes par défaut.

**Il écoute sur `127.0.0.1` sauf indication contraire, et toute autre adresse
exige un jeton.** Le service analyse tout hôte nommé dans une requête, sans le
valider par rapport à quoi que ce soit : c’est le modèle de confiance du plugin,
où un opérateur nomme ses propres instances. Accessible à des inconnus et sans
authentification, cette même propriété permettrait de lire l’intérieur du réseau
sur lequel il s’exécute. `--listen`/`COS_SERVICE_LISTEN` sur une autre adresse
que le bouclage, sans `--token`/`COS_SERVICE_TOKEN`, refuse donc de démarrer
plutôt que de servir sans protection. Voir
[l’ADR 0030](../../adr/0030-a-listener-binds-loopback-and-a-wide-bind-needs-a-credential.md).

L’exécution dans un conteneur, ainsi que le fichier prêt à l’emploi
[`docker/docker-compose.monitoring.yml`](../../docker/docker-compose.monitoring.yml)
qui démarre le scanner et un conteneur de vérification avec des secrets Docker,
sont décrits dans **[Exécuter le scanner comme service](scan-service.md)**.

Un simple `docker compose up` dans ce répertoire démarre en revanche
l’application web publique - voir [l’application web](web-service.md).

# Vérification des mises à jour {#update-check}
Une instance OpenCloud n’a pas de point de terminaison de mise à jour : la
question « est-ce la version la plus récente ? » est donc tranchée en comparant
le `productversion` annoncé par l’instance au flux des versions OpenCloud sur
GitHub. `--update-source` choisit la provenance de ce numéro :

| Mode                         | Comportement                                                                        |
|:-----------------------------|:------------------------------------------------------------------------------------|
| `auto` (valeur par défaut)   | Essaie le flux ; en cas d’échec, se rabat sur la version fournie avec le paquet     |
| `feed`                       | Uniquement le flux. Un échec est signalé comme inconnu au lieu d’être ignoré        |
| `pinned`                     | Utilise `--latest-version`. Aucun accès réseau                                      |
| `bundled`                    | Utilise la version enregistrée dans le fichier de données livré. Aucun accès réseau |
| `off`                        | Ignore entièrement la vérification des mises à jour (comme `--no-update-check`)     |

```shell
# ask GitHub, with a token to stay clear of the anonymous rate limit
check-opencloud-security --host opencloud.example.com \
  --release-token 'secret://releases_token'

# fully offline: compare against a version you control
check-opencloud-security --host opencloud.example.com --latest-version 7.4.0
```

L’API GitHub anonyme autorise soixante requêtes par heure et par adresse IP,
partagées avec tout le reste du trafic de cette adresse. Un jeton - un jeton à
granularité fine sans aucune permission suffit - relève nettement cette limite.
En mode `auto`, une recherche limitée en débit n’est pas une erreur : la
vérification se rabat sur la version fournie, aussi récente que le paquet
installé.

Le résultat est signalé sur une ligne de sortie supplémentaire et par la
métrique de performance `update_available` ; avec `--update-warning`, une mise à
jour en attente transforme un résultat autrement `OK` en `WARNING`. Un échec de
la vérification des mises à jour n’interrompt jamais le contrôle de sécurité.

Avec `--eol-warning DAYS` (`COS_EOL_WARNING`, YAML `eol_warning`), un résultat
autrement `OK` devient `WARNING` dès qu’il reste `DAYS` jours de support ou moins
à la ligne en service, avec la date et la version cible : la mise à niveau est
ainsi planifiée avant que la ligne ne passe en `CRITICAL` à sa fin de vie.

**Les recommandations de mise à jour restent sur votre canal de versions.** Les
installations production et LTS se voient proposer une version de leur propre
canal, tandis que la version la plus récente tous canaux confondus est signalée
séparément. Définissez `--release-track` pour remplacer la détection
automatique. Voir [Canaux de versions, fin de vie et recommandation de mise à
jour](release-lifecycle.md).

# Fichier de configuration et secrets {#configuration-file-and-secrets}
Tous les paramètres peuvent figurer dans un fichier plutôt que sur la ligne de
commande, et le moyen le plus rapide d’en écrire un est de laisser le plugin
poser les questions :

```shell
check-opencloud-security --configure
```

L’assistant demande le seul paramètre obligatoire - l’hôte -, explique à quoi il
sert et montre un exemple. Tout le reste a une valeur par défaut fonctionnelle :
les paramètres facultatifs sont donc proposés groupe par groupe et demandés
uniquement si vous répondez oui. Le résultat est écrit en JSON avec le mode
`0600`, puis trouvé automatiquement :

```shell
check-opencloud-security          # no arguments needed any more
```

Utilisez `--config` pour indiquer où l’écrire, par exemple
`--configure --config /etc/check-opencloud-security/.env.json`. Un fichier
existant est affiché et doit être confirmé avant d’être remplacé. L’équivalent
pour le scanner seul est `check-opencloud-scanner configure`.

Le fichier est lu depuis `--config`, `COS_CONFIG_FILE`, `./.env.json`,
`./check-opencloud-security.yml`, `~/.config/check-opencloud-security/.env.json`
ou `/etc/check-opencloud-security/` (la première correspondance l’emporte). Un
suffixe `.json` est lu comme du JSON, tout le reste comme du YAML - les deux sont
interchangeables. Voir
[`config/check-opencloud-security.example.yml`](../../config/check-opencloud-security.example.yml)
pour un exemple entièrement commenté.

```yaml
host: opencloud.example.com
check_hardening: true

scanner:
  verify_tls: false        # self-signed instance
  target_port: 9200
  tls_min_days: 21
  check_debug_ports: true

releases:
  mode: auto
  token: secret://releases_token
```

Les clés imbriquées correspondent une à une aux variables d’environnement :
`scanner.target_port` est `COS_SCANNER_TARGET_PORT`, `releases.token` est
`COS_RELEASES_TOKEN`, `scanner.tls_min_days` est `COS_SCANNER_TLS_MIN_DAYS`.
L’ordre de priorité est **ligne de commande > variable d’environnement > fichier
de configuration > valeur par défaut**.

**Les secrets n’ont jamais besoin d’être écrits dans le fichier ni dans
l’environnement du processus.** Toute valeur peut être remplacée par une
référence `secret://`, `file://`, `env://` ou `exec://`, ou être nommée avec un
suffixe `_file` pointant vers un fichier - voir
**[Les secrets dans la configuration](configuration.md)**.

# Seuils de notation {#rating-thresholds}
Le scanner note une instance de `A+` (la meilleure) à `F`. Le plugin convertit
cette note en valeur numérique et la compare à deux seuils inclusifs :

| Note   | 5    | 4   | 3   | 2   | 1   | 0   |
|:-------|:-----|:----|:----|:----|:----|:----|
| Grade  | `A+` | `A` | `C` | `D` | `E` | `F` |

- `-c, --critical` / `COS_CRITICAL` (par défaut `1`, soit `E`) : une note égale
  ou inférieure à cette valeur est `CRITICAL`.
- `-w, --warning` / `COS_WARNING` (par défaut `3`, soit `C`) : une note égale ou
  inférieure à cette valeur est `WARNING`.

Deux règles s’appliquent toujours en plus des seuils :

- **Les vulnérabilités connues élèvent l’état au moins à `WARNING`**, même
  lorsque la note globale semble encore acceptable. Les identifiants signalés
  sont listés dans la sortie.
- **Une version en fin de vie est toujours `CRITICAL`**, car elle ne reçoit plus
  aucun correctif de sécurité.

> **Un seul constat critique ne déclenche pas d’astreinte par défaut.** Le pire
> constat plafonne la note au lieu de la fixer : un constat critique la plafonne
> à `2` (`D`), ce que la valeur par défaut `--critical 1` signale encore comme
> `WARNING`. C’est voulu : cela évite qu’un seul chemin exposé soit impossible à
> distinguer d’une instance en fin de vie. Si un constat critique doit réveiller
> quelqu’un, utilisez `--critical 2`.

Une note hors de la plage documentée `0-5` donne `UNKNOWN`. `--critical` ne doit
pas être supérieur à `--warning`, et les deux doivent être compris entre `0` et
`5` ; sinon, le plugin refuse de s’exécuter.

```shell
# Only alert once the instance is actually end-of-life
check-opencloud-security --host opencloud.example.com --warning 1 --critical 0

# Page on any critical finding
check-opencloud-security --host opencloud.example.com --warning 4 --critical 2
```

## Profils de seuils {#threshold-profiles}
Chaque équipe finit par écrire la même poignée d’options dans sa définition de
supervision, puis par débattre de laquelle. `--profile` / `COS_PROFILE` en
nomme une :

| Profil | `--warning` | `--critical` | `--check-hardening` | `--update-warning` | `--eol-warning` |
|:--------|:------------|:-------------|:--------------------|:-------------------|:----------------|
| `strict` | `4` (`A`) | `2` (`D`) | activé | activé | `90` |
| `ops` | `3` (`C`) | `1` (`E`) | activé | désactivé | `30` |
| `lenient` | `2` (`D`) | `0` (`F`) | désactivé | désactivé | `0` |

Un profil détermine **comment les mêmes mesures sont jugées, jamais l’intensité
avec laquelle l’instance est sondée** : aucun profil n’analyse davantage, et
aucun n’analyse moins. Sans `--profile`, les valeurs par défaut documentées
ci-dessus s’appliquent : une définition de supervision existante se comporte
exactement comme avant.

C’est aussi la source de valeur la plus faible : tout ce que vous écrivez
vous-même l’emporte.

```shell
# The strict set, except that a critical finding should not page here
check-opencloud-security --host opencloud.example.com --profile strict --critical 1
```

L’option, la variable d’environnement et la clé `profile:` du fichier de
configuration sont le même paramètre, et l’explication de `--debug` nomme le
profil selon lequel une note a été jugée.

# Vérifications de durcissement {#hardening-checks}
En plus des contrôles réussite/échec ci-dessus, le scanner indique quelles
mesures de durcissement l’instance a mises en place. Avec `--check-hardening` /
`COS_CHECK_HARDENING`, elles sont également évaluées.

Les noms sont brefs, car ils se retrouvent dans le texte des alertes. Lancez le
plugin avec `--debug` pour obtenir l’explication à côté du constat, ou lisez-les
toutes d’un coup : **[Les mesures de durcissement une par une](hardening.md)**
indique ce que signifie chaque identifiant, ce qu’un échec révèle réellement et
quelle variable d’environnement OpenCloud le modifie - ainsi que les deux mesures
sur lesquelles personne n’a de prise, et la façon d’accepter avec
`--ignore-hardening` un constat que vous ne corrigerez pas.

Deux autres entrées peuvent apparaître sur la ligne « Missing hardening » :
`httpsEnforced` lorsque l’instance n’impose pas HTTPS, et le nom de tout en-tête
de sécurité de `setup.headers` absent ou trop faible (par exemple
`Strict-Transport-Security`). `--debug` les explique aussi.

Tout ce qui est signalé comme manquant est listé dans la sortie et exporté dans
la métrique de performance `hardenings_missing`. Un résultat qui serait sinon
`OK` passe à `WARNING` ; un `WARNING`/`CRITICAL` existant n’est jamais abaissé.

```shell
check-opencloud-security --host opencloud.example.com --check-hardening
```

Certains constats sont réels mais ne peuvent pas être traités dans votre
environnement : une CSP que vous ne pouvez pas durcir sans casser l’interface
web, un en-tête HSTS géré par votre reverse proxy. `--ignore-hardening` en
accepte un par son nom, et la note est recalculée sans lui - mais le constat
reste dans le résultat JSON, marqué `"ignored": true`, car une exemption
supprime une alerte, pas la preuve :

```bash
check-opencloud-security --host opencloud.example.com --check-hardening \
    --ignore-hardening 'cspWithoutUnsafeInline,hstsPreload'
```

Une exemption sans échéance reste active jusqu’à ce que vous la retiriez.
`--waive-until` accepte les mêmes motifs et ajoute les deux éléments qui règlent
ce problème, une raison et une date d’expiration :

```bash
check-opencloud-security --host opencloud.example.com --check-hardening \
    --waive-until 'debugPort:9205|2026-12-31T00:00:00Z|Firewall change, OPS-412'
```

La date d’expiration doit comporter un fuseau horaire et la raison ne peut pas
être vide ; un enregistrement auquel manque l’un des deux est refusé au lieu
d’être traité discrètement comme permanent. À `2026-12-31T00:00:00Z`, la
vérification déclenche de nouveau une alerte sans aucune modification de la
configuration. Chaque exemption configurée - active, expirée ou sans aucune
correspondance - est listée sous `waivers` dans le document de résultat.

Voir
[Accepter un constat que vous ne corrigerez pas](hardening.md#accepting-a-finding-you-are-not-going-to-fix)
pour les jokers, ce qu’une exemption ne permet pas, et pourquoi un fichier de
configuration est le meilleur endroit où la placer.

# Expliquer une note {#explaining-a-rating}
Utilisez `--debug` (`COS_DEBUG=1`) pour voir comment la note a été calculée et ce
que signifie chaque constat. L’explication indique la note de départ et chaque
contrôle qui la limite.

```shell
check-opencloud-security --host opencloud.example.com --check-hardening --debug
```

```text
--- Why this rating ---
Starting point: 5/5 - the installed release is current and no advisory matches this version
Failed check basicAuthDisabled [medium] caps the rating at 4/5 - WWW-Authenticate: Basic realm="..."
Final rating: 4/5 (B). WARNING at or below C, CRITICAL at or below E.

--- Missing hardening measures ---
basicAuthDisabled: HTTP Basic authentication is enabled
    The instance answers with a 'WWW-Authenticate: Basic' challenge, so usernames
    and passwords can be replayed on every request without going through the
    identity provider ... It is often deliberate: CalDAV, CardDAV and WebDAV
    clients cannot speak OpenID Connect and have nothing else to authenticate
    with, which is why this counts as a medium finding rather than a serious one.
    Setting: PROXY_ENABLE_BASIC_AUTH
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs it. If
    calendar, contact or WebDAV clients do, keep it on and give them app tokens
    rather than account passwords.
    Docs: https://docs.opencloud.eu/docs/dev/server/services/proxy/environment-variables
--- end of explanation ---
```

Le point de départ est ce que donneraient la version et la base des avis seules :
`5` à jour, `4` correctif en attente, `3` en retard d’une ligne de version
entière, `2` vulnérabilités connues, `1` vulnérabilités critiques ou élevées,
`0` fin de vie. Les contrôles supplémentaires en échec la plafonnent ensuite
selon leur gravité : `critical` à `2`, `high` à `3`, `medium` à `4`, `low` à `5`.
Un contrôle en échec qui n’a pas déterminé le résultat est tout de même listé,
avec une mention en ce sens : rien ne semble écarté discrètement.

Sans `--debug`, la sortie garde la taille qui convient à un système de
supervision. La même décomposition est toujours présente dans le résultat de
l’analyse sous `ratingExplanation` : elle peut donc être lue sans relancer la
vérification.

```shell
python -m opencloud_local_scan.cli scan opencloud.example.com | jq .ratingExplanation
```

Notez que `--debug` fait aussi passer la journalisation au niveau `DEBUG` : les
détails HTTP vont sur stderr, tandis que l’explication va sur stdout avec le
reste de la sortie du plugin.

# Ce qui améliorerait la note {#what-would-raise-the-rating}

Le plan de correction liste les modifications qui amélioreraient la note, dans
l’ordre selon lequel le scanner calcule leur effet.

Chaque résultat contient `remediationPlan`, calculé avec la même fonction de
notation en retirant les constats une étape à la fois. Le plan est déduit du
résultat et n’a besoin d’aucun stockage séparé.

```shell
python -m opencloud_local_scan.cli scan opencloud.example.com | jq .remediationPlan
```

`--debug` affiche la même liste sous l’explication :

```text
--- What would raise the rating ---
Two fixes would raise this instance from 3/5 to 5/5.
1. exposed:/opencloud.yaml [high] - then 4/5 (B)
    A deployment file is publicly readable (/opencloud.yaml)
    Observed: HTTP 200 with 4.1 kB of YAML
    Fix: Stop serving the deployment directory. Proxy to OpenCloud's own
    address rather than exposing the filesystem ...
2. basicAuthDisabled [medium] - then 5/5 (A+)
    HTTP Basic authentication is enabled
    Fix: Set PROXY_ENABLE_BASIC_AUTH=false (the default) if nothing needs it ...
```

Trois points sur cette liste méritent d’être connus avant d’agir :

- **L’ordre n’est pas arbitraire.** Les constats de même gravité partagent un
  même plafond : corriger le premier de trois constats medium ne change donc
  rien. Les étapes qui ne font rien gagner à elles seules sont tout de même
  listées - avec `still 4/5` au lieu de `then 5/5` -, car les omettre laisserait
  croire qu’on peut les ignorer.
- **Une mise à jour peut être l’une des étapes.** Corriger des constats ne peut
  jamais élever une note au-delà de ce que permet la version installée : le plan
  insère donc la mise à niveau à l’endroit où elle commence réellement à
  apporter quelque chose.
- **Certains constats ne peuvent jamais être corrigés.** Les indicateurs
  qu’OpenCloud code en dur sont listés séparément comme bloqués, et ils limitent
  la portée du plan. Voir
  [Mesures qui ne sont pas des paramètres](hardening.md#measures-that-are-not-settings).

Les constats exemptés sont aussi listés, marqués comme tels : une exemption fait
taire une alerte, elle ne corrige rien, et le plan le dit.

Le même plan figure sur le tableau de bord web, dans les exports JSON, CSV,
SARIF et PDF, et dans l’outil MCP `plan_remediation`.

### Regroupé par configuration {#grouped-by-where-the-change-is-made}

`remediationPlan.groups` classe les constats ouverts selon le système à
modifier pour les corriger : **proxy inverse**, **fournisseur d’identité**,
**OpenCloud** ou **zone DNS**. Les constats qui ne limitent pas la note, comme
un en-tête manquant, y figurent aussi.

Les constats qu’une seule modification résout forment une seule modification :
tous les en-têtes de sécurité manquants sont un bloc d’en-têtes, plusieurs
problèmes de certificat un nouveau certificat, tous les chemins `exposed:/...`
une correction, et la mise à jour ferme tous les avis correspondants. Chaque
modification nomme ses constats, `resolvesSeveral` et la note qu’elle
donnerait seule, recalculée avec la même fonction de notation. `groupSummary`
nomme les modifications qui résolvent plusieurs constats à la fois. Les
constats ignorés ou codés en dur ne sont pas proposés. `--debug`, le tableau de
bord, le lot de remédiation et `plan_remediation` affichent aussi ces groupes.

# Notifications par webhook {#webhook-notifications}
Le plugin peut envoyer une notification JSON à un point de terminaison HTTP(S)
lorsqu’une vérification atteint un niveau critique. La fonction est
**facultative et désactivée par défaut** : elle ne s’active qu’une fois
`--webhook-url` (ou `COS_WEBHOOK_URL`) défini.

```shell
check-opencloud-security --host opencloud.example.com \
  --webhook-url https://hooks.example.com/opencloud
```

- `--webhook-on` / `COS_WEBHOOK_ON` (par défaut `critical`) choisit l’état le
  plus bas qui déclenche une notification. Chaque niveau inclut les plus graves :
  `critical`, `warning` (WARNING + CRITICAL), `unknown` (UNKNOWN + WARNING +
  CRITICAL) et `always`.
- `--webhook-format` / `COS_WEBHOOK_FORMAT` (par défaut `generic`) envoie le
  corps sous forme de pièce jointe Slack Block Kit (`slack`, également acceptée
  par Mattermost et les passerelles de webhooks Matrix courantes), d’embed
  Discord (`discord`), ou de notification push pour un serveur
  [ntfy](https://ntfy.sh) (`ntfy`) ou [Gotify](https://gotify.net) (`gotify`), au
  lieu du document plat propre au plugin. La valeur par défaut est inchangée :
  c’est donc entièrement facultatif.
  ```shell
  check-opencloud-security --host opencloud.example.com \
    --webhook-url https://hooks.slack.com/services/... \
    --webhook-format slack

  check-opencloud-security --host opencloud.example.com \
    --webhook-url https://ntfy.example.com/opencloud \
    --webhook-format ntfy
  ```
  Avec `ntfy`, faites pointer `--webhook-url` vers l’URL du **sujet** (topic) :
  le sujet y est lu, et la publication elle-même va à la racine du serveur, le
  seul endroit où ntfy lit du JSON. Une URL sans sujet est refusée au démarrage
  au lieu d’échouer à chaque notification. Tout autre destinataire -
  Alertmanager, un récepteur personnalisé - attend toujours le document
  `generic` ; les [exemples de webhooks](webhooks.md) en proposent un
  pour chacun.
- `--webhook-header` / `COS_WEBHOOK_HEADERS` ajoute des en-têtes de requête, par
  exemple pour l’authentification. Répétez l’option, ou séparez les entrées par
  `;` dans la variable d’environnement :
  `COS_WEBHOOK_HEADERS="X-Auth-Token: abc; X-Env: prod"`.
- `--webhook-timeout` / `COS_WEBHOOK_TIMEOUT` (par défaut `10`) limite la durée
  de l’appel au webhook ; il est indépendant du `--timeout` de l’analyse.
- Les destinations de webhook qui se résolvent en adresses privées, de bouclage
  ou lien-local sont bloquées pour empêcher la falsification de requêtes côté
  serveur. Ne définissez `--allow-private-webhooks` ou
  `COS_ALLOW_PRIVATE_WEBHOOKS=true` que pour un récepteur interne voulu.

L’envoi réutilise `--retries` / `--backoff-factor`. **Un webhook en échec ne
change jamais le résultat de la vérification** : le plugin ajoute
`Webhook delivery failed` à sa sortie et se termine quand même avec l’état
mesuré, si bien qu’un canal de notification défaillant ne peut ni masquer ni
simuler une instance vulnérable.

Lorsque plusieurs hôtes sont vérifiés en une seule exécution, chaque hôte qui
atteint l’état configuré produit sa propre notification. Les analyses qui
échouent complètement (hôte injoignable, TLS défaillant) déclenchent aussi une
notification lorsque `--webhook-on` vaut `unknown` ou `always`.

> **Remarque :** considérez le webhook comme un complément à votre système de
> supervision, pas comme un remplacement. Il est envoyé sans suivi et n’est pas
> renvoyé au-delà du nombre de tentatives configuré.

**[Exemples de webhooks](webhooks.md)** décrit la charge utile champ
par champ, la vérification de sa signature, et un adaptateur pour chaque
destinataire qui veut son propre JSON - Slack, Discord, ntfy, Alertmanager -,
ainsi qu’[Uptime Kuma](webhooks.md#uptime-kuma), dont le moniteur
Push accepte le document tel quel et traite le silence comme un échec : une
vérification qui a cessé de s’exécuter apparaît donc aussi.

# Ne signaler que ce qui a changé {#reporting-only-what-changed}
Utilisez `--baseline` pour enregistrer les constats de chaque exécution et y
comparer l’exécution suivante. Avec `--warn-on-new`, un résultat inchangé est
signalé OK ; un nouveau constat ou une note plus basse rétablit l’état d’alerte
normal.

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json \
    --warn-on-new
```

L’état complet est affiché dans tous les cas : seule l’alerte est supprimée,
jamais la preuve. **Une version en fin de vie déclenche toujours une alerte**,
quelle que soit la durée de sa présence dans la référence.

Une référence enregistre l’**empreinte de configuration** de l’analyse : des
condensats de la configuration, regroupés par domaine. Elle n’enregistre aucune
valeur de configuration. Ces condensats permettent de repérer un changement de
configuration même lorsqu’aucun contrôle n’échoue :

```
Baseline: No new findings since 2026-09-14T06:00:00Z, but the configuration changed (headers, proxy)
```

Seuls les noms des groupes sont signalés ; les paramètres correspondants sont
hachés puis écartés. Une dérive ne crée jamais de constat et ne change jamais le
code de sortie.

**[Ne signaler que ce qui a changé](baseline.md)** décrit les formats de
comparaison (`text`, `markdown`, `slack`, `json`), ce qui compte comme une
régression, les groupes de configuration et les règles qui empêchent une
référence de masquer quoi que ce soit.

# Le plugin lui-même est-il à jour ? {#is-the-plugin-itself-up-to-date}
`--self-update-check` interroge PyPI au plus une fois par jour et ajoute une
remarque lorsqu’une version plus récente du plugin est disponible. Mettre à jour
le plugin actualise aussi ses données de versions et d’avis fournies.

```
Plugin update available: check-opencloud-security 1.2.0 is published, this is 1.1.0 (upgrade with --upgrade-self)
```

Cette option est désactivée par défaut, mise en cache sous
`${XDG_CACHE_HOME:-~/.cache}/check-opencloud-security/`, et **ne change jamais le
code de sortie** : la réponse de PyPI ne dit rien de la santé de l’instance
supervisée. Tout échec - pas de réseau, un proxy qui bloque, PyPI indisponible -
est silencieux.

Mettez à jour avec [`--upgrade-self`](installation.md#updating), ou regardez
d’abord ce qu’il ferait avec `--upgrade-self check` (`--upgrade-self --check-only`
est équivalent).

# Nouvelles tentatives et attente {#retries-and-backoff}
Les erreurs réseau passagères (délais dépassés, connexions réinitialisées,
réponses `5xx` de l’instance) sont automatiquement réessayées avec une attente
exponentielle avant que la vérification abandonne et signale `UNKNOWN`.

- `--retries` / `COS_RETRIES` (par défaut `2`) : nombre de nouvelles tentatives
  après la première (la valeur par défaut effectue donc jusqu’à 3 tentatives au
  total).
- `--backoff-factor` / `COS_BACKOFF_FACTOR` (par défaut `0.5`) : délai de base en
  secondes ; l’attente avant chaque nouvelle tentative double
  (`backoff_factor * 2^attempt`), par exemple `0.5s`, `1s`, `2s`, ...
- `--timeout` / `COS_TIMEOUT` (par défaut `10`) : durée maximale d’une requête
  avant qu’elle compte comme un échec. Augmentez-la sur des liaisons lentes ou
  lors d’une analyse à travers un proxy.

Définissez `--retries 0` pour désactiver entièrement les nouvelles tentatives et
échouer rapidement. Une nouvelle tentative relance toute l’analyse : un nombre
élevé de tentatives sur un hôte injoignable allonge donc nettement la
vérification par rapport au seul délai d’attente.

# Données de performance {#performance-data}
La sortie contient des données de performance Nagios/Icinga standard après un
caractère `|`, pour qu’Icinga2, Grafana, etc. puissent représenter les résultats
dans le temps :

```
rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.234s;;;0;
```

La métrique `rating` porte les seuils WARNING et CRITICAL configurés dans la
syntaxe de plages de Nagios (`@0:3` signifie « avertir entre 0 et 3 ») :
Icinga2 les trace donc sur le graphique sans configuration supplémentaire.

| Métrique              | Signification                                                                         |
|:----------------------|:--------------------------------------------------------------------------------------|
| `rating`              | Note numérique de l’analyse, `0`-`5` (`5`=A+ ... `0`=F), `U` si inconnue               |
| `vulnerabilities`     | Nombre de vulnérabilités connues signalées pour la version analysée                    |
| `time`                | Durée de l’analyse, en secondes                                                        |
| `hardenings_missing`  | Mesures de durcissement manquantes (uniquement avec `--check-hardening`)              |
| `extra_checks_failed` | Nombre de contrôles supplémentaires en échec                                           |
| `update_available`    | `1` lorsqu’une version OpenCloud plus récente existe                                   |
| `support_days_left`   | Jours restants avant la fin du support de la ligne de version (négatif en cas de dépassement) |
| `cert_days_left`      | Jours restants avant l’expiration du certificat TLS (négatif une fois expiré)          |
| `upgrade_path_complete` | `1` lorsque la mise à niveau recommandée lève tous les avis connus, `0` lorsqu’elle en laisse un ouvert ; absente sans avis |
| `waiver_days_left`    | Jours avant la fin d’une exemption `--waive-until` qui laisse un contrôle en échec alerter de nouveau ; absente si aucun contrôle en échec ne dépend d’une échéance |
| `coverage_inconclusive` | Contrôles exécutés par l’analyse sans conclusion |
| `coverage_not_checked` | Contrôles que l’analyse n’a pas exécutés |

`cert_days_left` est absente plutôt que nulle lorsque rien n’a été mesuré : une
analyse en HTTP simple, un hôte qui a refusé la négociation ou un certificat
dont les dates n’ont pas pu être lues. Elle porte les seuils de l’analyse
elle-même plutôt qu’un second avis inventé pour le graphique : avertissement à
partir de `scanner.tls_min_days`, la même marge que celle du constat
`tlsCertificate`, et critique une fois le certificat réellement expiré.

`waiver_days_left` compte depuis l’analyse jusqu’au prochain moment où une
exemption temporaire cesse de masquer un contrôle en échec. Avec
`--waiver-warning DAYS`, la valeur porte cette fenêtre comme plage
d’avertissement. `coverage_inconclusive` et `coverage_not_checked` expliquent
la note sans jamais la modifier, et n’ont donc pas de seuils.

En dehors d’Icinga2, les mêmes nombres atteignent Prometheus par le collecteur
textfile de node_exporter ou un Pushgateway - voir
[Prometheus et Grafana](prometheus.md).

# Mise en cache {#caching}
Le plugin ne conserve aucun cache : chaque exécution analyse l’instance à
nouveau, il n’y a donc rien à invalider ni aucune option pour forcer une nouvelle
analyse.

Le seul endroit où un cache existe est le
[service d’analyse](#running-the-scanner-as-a-service) facultatif, qui réutilise
un résultat pendant `service.cache_ttl` secondes. `POST /api/requeue` le vide et
relance l’analyse.

# Exemples de sortie {#example-output}

Une instance saine :

```Shell
$ check-opencloud-security -H opencloud.example.com
OK: Server is up to date. No known vulnerabilities.
OpenCloud 7.4.0 on opencloud.example.com, rating: A+, last scanned: 2026-05-29 08:50:58.000000
Additional checks: all passed
Coverage: 84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited
Configuration fingerprint: 9e3c4428 | rating=5;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.731s;;;0; extra_checks_failed=0;;;0;
```

Entre les lignes de détail et les données de performance, une ligne `Coverage:`
indique quelle part de la vérification a réellement abouti à une conclusion -
`84 checks evaluated, 6 skipped, 2 indeterminate, 1 network-limited`. Un
contrôle réussi et un contrôle jamais exécuté laissent sinon la même trace : la
ligne nomme donc les lacunes. `skipped` est une sonde que l’analyse n’a pas
exécutée, `indeterminate` une sonde exécutée sans trancher, et `network-limited`
une sonde qui a dépassé son délai ou n’a pas trouvé de route - DNSSEC, un
fournisseur d’identité externe, un point de terminaison facultatif -, à laquelle
un autre point d’observation pourrait répondre. Elle ne change jamais la note ni
le code de sortie, et un document d’analyse antérieur au bloc de couverture
n’affiche aucune ligne, car « ce rapport ne le dit pas » n’est pas « rien n’a été
manqué ».

La ligne `Configuration fingerprint:` est un condensat de la façon dont ce
déploiement est configuré - transport, en-têtes, partage, authentification et
proxy hachés ensemble -, jamais de ce sur quoi il est configuré. Deux exécutions
qui affichent les mêmes huit caractères ont trouvé la même configuration ; deux
qui diffèrent, non, même lorsque la note n’a pas bougé. Avec `--baseline`, la
comparaison nomme les groupes qui ont changé ; seule, la ligne sert à comparer
les exécutions entre elles. Elle ne change jamais la note ni le code de sortie,
et un document d’analyse sans empreinte n’affiche aucune ligne.

Une version majeure qui ne reçoit plus de correctifs - toujours CRITICAL, quels
que soient les seuils :

```Shell
$ check-opencloud-security -H opencloud.example.com
CRITICAL: The 7.3 rolling release line is end-of-life and has no security fixes. Upgrade to 7.4.0.
OpenCloud 1.0.0 on opencloud.example.com, rating: F, last scanned: 2026-05-30 07:48:58.000000
Additional checks: all passed | rating=0;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.842s;;;0; extra_checks_failed=0;;;0;
```

Un seul constat critique plafonne la note à `D`, ce que les seuils par défaut
signalent comme WARNING - voir [Seuils de notation](#rating-thresholds) :

```Shell
$ check-opencloud-security -H opencloud.example.com
WARNING: Rating D is at or below the warning threshold C, but no known vulnerabilities.
OpenCloud 7.4.0 on opencloud.example.com, rating: D, last scanned: 2026-05-29 08:51:33.000000
Additional checks failed (1): exposed:/opencloud.yaml | rating=2;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=0.860s;;;0; extra_checks_failed=1;;;0;
```

Avec `--check-hardening`, sur une instance de production dont le proxy propose
encore l’authentification HTTP Basic :

```Shell
$ check-opencloud-security -H opencloud.example.com --check-hardening
WARNING: 3 hardening measure(s) missing, but no known vulnerabilities.
OpenCloud 7.2.3 on opencloud.example.com, rating: B, last scanned: 2026-08-12 15:58:04.138671
Release lifecycle: 7.2 (production), current release
Missing hardening: basicAuthDisabled, cspWithoutUnsafeInline, publicLinkPasswordEnforced (run with --debug for what each means and how to fix it)
Additional checks failed (1): basicAuthDisabled
Update check (feed, installed 7.2.3): up to date | rating=4;@0:3;@0:1;0;5 vulnerabilities=0;;;0; time=1.835s;;;0; hardenings_missing=3;;;0; extra_checks_failed=1;;;0; update_available=0;;;0;1
```

Le contrôle `medium` en échec limite la note à `4` (`A`). Une mesure évaluée
uniquement par `--check-hardening` peut faire passer l’état de supervision à
WARNING sans changer la note. Utilisez `--debug` pour voir quelle règle
s’applique ; voir [Expliquer une note](#explaining-a-rating).

# Guides de déploiement {#deployment-guides}
L’[index de la documentation](../README.md) regroupe par tâche les instructions
de déploiement et les exemples détaillés. Voici les points de départ les plus
courants :

| Guide | Ce qu’il couvre |
|:------|:---------------|
| [Exploiter OpenCloud dans une infrastructure sécurisée](secure-deployment.md) | Tout ce qu’une analyse ne peut pas voir : un fournisseur d’identité externe, le journal d’audit, le pare-feu, et la place de la supervision continue |
| [Installer le plugin](installation.md) | pipx/uv/pip, mises à jour, complétion dans le shell, Docker, et les objets Icinga2 et Nagios |
| [Référence des options de la CLI](cli-reference.md) | Chaque option, sa valeur par défaut et la variable d’environnement qui définit la même chose |
| [Exemples détaillés](examples.md) | Des appels complets pour les situations les plus fréquentes |
| [Le service d’analyse public](web-service.md) | L’application web : FastAPI, un worker ARQ et Redis, avec file d’attente, protection SSRF et limites de débit |
| [Utiliser le scanner depuis un agent IA](mcp.md) | Le point de terminaison MCP, configuré pour Claude Code, Claude Desktop, Copilot, Cursor, Zed et Windsurf |
| [Dépannage](troubleshooting.md) | Les erreurs réellement rencontrées, et la référence des codes de sortie |

Quelque chose ne fonctionne pas ? Commencez par le
[Dépannage](troubleshooting.md), qui contient aussi la référence des codes
de sortie.

# Exemples {#examples}
Des appels complets, à copier-coller, pour les situations les plus fréquentes -
les bases, les canaux de versions, les exemptions, les instances qui ne sont pas
sur Internet, les seuils et les notifications, une règle apply Icinga2 et le
scanner seul - sont réunis dans **[Exemples détaillés](examples.md)**.

```bash
# A production instance, hardening reported, two findings accepted,
# notified on anything worse than OK - a realistic complete invocation
check-opencloud-security --host opencloud.example.com \
    --release-track production \
    --check-hardening \
    --ignore-hardening 'cspWithoutUnsafeInline,hstsPreload' \
    --update-warning \
    --warning 4 --critical 2 \
    --webhook-url https://hooks.example.com/opencloud \
    --webhook-on warning
```

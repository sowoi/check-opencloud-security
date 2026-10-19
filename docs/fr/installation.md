# Installation

Toutes les façons d’installer `check-opencloud-security` sur un hôte, ainsi que
les objets de supervision qui l’appellent une fois installé. Le
[README principal](../../README.md#installation) contient les deux commandes qui
couvrent le cas courant ; cette page couvre tout le reste : maintenir le paquet
à jour, la complétion dans le shell, l’installation depuis une copie du dépôt,
la construction de l’image par vos soins et les définitions d’objets Icinga2 et
Nagios.

<!-- TOC -->
* [Installer le plugin](#installing-the-plugin)
  * [Avec pipx / uv / pip (recommandé)](#using-pipx-uv-pip-recommended)
  * [Debian, Ubuntu, RHEL, Fedora (.deb et .rpm)](#debian-ubuntu-rhel-fedora-deb-and-rpm)
  * [Docker](#docker)
  * [Icinga2 / Nagios](#icinga2-nagios)
<!-- TOC -->


## Avec pipx / uv / pip (recommandé) {#using-pipx-uv-pip-recommended}
Le paquet est publié sur
[PyPI](https://pypi.org/project/check-opencloud-security/) et installe deux
commandes dans votre `PATH` : `check-opencloud-security` (la vérification
elle-même) et `check-opencloud-scanner` (le même scanner, sous forme d’outil JSON
ponctuel ou de service permanent).

**[pipx](https://pipx.pypa.io/) - recommandé pour les outils en ligne de
commande**, installe le plugin dans son propre environnement virtuel :
```shell
pipx install check-opencloud-security
```

**[uv](https://docs.astral.sh/uv/)** - même principe, en plus rapide :
```shell
uv tool install check-opencloud-security
```

**pip** - dans le système ou dans un environnement virtuel existant :
```shell
pip install check-opencloud-security
```

Chaque version est livrée avec un SBOM CycloneDX et une attestation de
provenance Sigstore ; voir
[Vérifier ce que vous avez téléchargé](../../SECURITY.md#verifying-what-you-downloaded)
si vous préférez ne pas faire confiance à l’artefact sans vérification.

Pour installer les dernières modifications non publiées, indiquez plutôt le
dépôt à l’un de ces outils :
`pipx install git+https://github.com/sowoi/check-opencloud-security.git`
(de même `uv tool install git+https://...` et `pip install git+https://...`).

### Mettre à jour {#updating}
```shell
check-opencloud-security --upgrade-self
```

Cette commande détermine comment le plugin a été installé et exécute la
commande adaptée. Utilisez `--upgrade-self=check` pour voir ce qu’elle
exécuterait sans l’exécuter. Une copie git est refusée : mettez-la à jour avec
`git pull`.

Voici les commandes entre lesquelles elle choisit, si vous préférez les lancer
vous-même :

```shell
pipx upgrade check-opencloud-security          # pipx
pipx upgrade-all                               # ... or every pipx tool at once

uv tool upgrade check-opencloud-security       # uv
uv tool upgrade --all                          # ... or every uv tool at once

pip install --upgrade check-opencloud-security # pip
```

Vérifiez la version utilisée avec `check-opencloud-security --version`, et
consultez [CHANGELOG.md](../../CHANGELOG.md) pour les changements. Une
installation git se met à jour en relançant la même commande `install` avec
`--force` (pipx/uv) ou `--upgrade --force-reinstall` (pip).

Maintenir le paquet à jour compte davantage ici que pour un plugin qui
interroge un service hébergé : le calendrier des versions OpenCloud et la
dernière version connue sont livrés *dans* le paquet (voir
[Détection de fin de vie](../../README.md#end-of-life-detection)).

Pour désinstaller le plugin : `pipx uninstall check-opencloud-security`,
`uv tool uninstall check-opencloud-security` ou
`pip uninstall check-opencloud-security`.

**Depuis une copie du dépôt (développement ou installation hors ligne) :**

Le projet utilise [uv](https://docs.astral.sh/uv/) comme gestionnaire de
dépendances ; `uv.lock` fixe chaque dépendance, ce qui rend l’installation
reproductible :

```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security

uv sync                                       # create .venv from uv.lock
uv run check-opencloud-security --host opencloud.example.com
```

Sans `uv`, installez la copie avec pip. Les dépendances sont déclarées dans
`pyproject.toml` : aucun fichier requirements séparé n’est nécessaire.

```shell
pip install .
# or, without installing, run the script in place:
pip install requests PyYAML
python3 check_opencloud_security.py --host opencloud.example.com
```

Si l’un de vos outils de déploiement exige un `requirements.txt`, générez-le à
partir du fichier de verrouillage au lieu de le maintenir à la main :

```shell
uv export --no-dev --no-emit-project --format requirements.txt -o requirements.txt

# without the hashes, if your tooling cannot handle them:
uv export --no-dev --no-emit-project --no-hashes --format requirements.txt -o requirements.txt

# including the development and test dependencies:
uv export --no-emit-project --format requirements.txt -o requirements-dev.txt
```

Un tel fichier est un produit de construction : ne le versionnez pas, il est
périmé dès que `uv.lock` change.

### Complétion dans le shell {#shell-completion}
La complétion est facultative et désactivée par défaut ; elle nécessite une
dépendance supplémentaire :

```shell
pipx install 'check-opencloud-security[completion]'
uv tool install 'check-opencloud-security[completion]'
# or, into an existing install:
pipx inject check-opencloud-security argcomplete
uv tool install --with argcomplete check-opencloud-security --force
```

Enregistrez ensuite les deux commandes auprès de votre shell. Pour **bash**,
dans `~/.bashrc` :

```shell
eval "$(register-python-argcomplete check-opencloud-security)"
eval "$(register-python-argcomplete check-opencloud-scanner)"
```

Pour **zsh**, les deux mêmes lignes dans `~/.zshrc`, précédées une fois de
`autoload -U bashcompinit && bashcompinit`. Pour **fish**, écrivez plutôt la
sortie dans un fichier de complétion :

```shell
register-python-argcomplete --shell fish check-opencloud-security \
  > ~/.config/fish/completions/check-opencloud-security.fish
```

La complétion propose les noms des options, les valeurs des options qui
acceptent un ensemble fixe (`--webhook-on`, `--release-track`,
`--update-source`, `--upgrade-self`) et les identifiants de durcissement
acceptés par `--ignore-hardening`,
avec leurs longs noms en camelCase.

Sans `argcomplete`, rien n’est enregistré et le plugin se comporte exactement
comme avant : ce n’est jamais une dépendance obligatoire d’un plugin de
supervision.

## Debian, Ubuntu, RHEL, Fedora (.deb et .rpm) {#debian-ubuntu-rhel-fedora-deb-and-rpm}

Utilisez cette méthode sur un hôte de supervision, où l’intérêt est que la
vérification figure dans la base des paquets comme tout le reste de la
machine : dans l’inventaire, dans la tâche de mises à jour automatiques, et
visible avec `apt list --installed`. Chaque version fournit les deux paquets en
pièces jointes. Ils sont indépendants de l’architecture (`all` / `noarch`) : un
seul fichier convient donc à tous les hôtes.

```shell
VERSION=$(curl -fsSL https://api.github.com/repos/sowoi/check-opencloud-security/releases/latest \
          | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p')
BASE=https://github.com/sowoi/check-opencloud-security/releases/download/v$VERSION

# Debian, Ubuntu
curl -fsSLO "$BASE/check-opencloud-security_${VERSION}_all.deb"
sudo apt install "./check-opencloud-security_${VERSION}_all.deb"

# RHEL, Rocky, Alma, Fedora, openSUSE
curl -fsSLO "$BASE/check-opencloud-security-${VERSION}-1.noarch.rpm"
sudo dnf install "./check-opencloud-security-${VERSION}-1.noarch.rpm"
```

Chaque paquet est accompagné d’un fichier `.sha256`, et tous deux sont couverts
par la même attestation de provenance Sigstore que le wheel - voir
[Vérifier ce que vous avez téléchargé](../../SECURITY.md#verifying-what-you-downloaded).

### Ce qui est installé {#what-it-installs}

| Chemin | |
|:--|:--|
| `/usr/bin/check-opencloud-security` | la vérification |
| `/usr/bin/check-opencloud-scanner` | le même scanner, en outil JSON |
| `/usr/lib/nagios/plugins/check_opencloud_security` | lien symbolique vers la vérification (`/usr/lib64/...` sur les systèmes RPM) |
| `/usr/lib/check-opencloud-security/` | le code |
| `/etc/check-opencloud-security/` | créé vide ; `config.yml` y est recherché |
| `/usr/lib/systemd/system/` | quatre unités, aucune activée |
| `/usr/share/doc/check-opencloud-security/` | l’exemple de configuration, le fichier d’environnement et l’entrée cron |

Comme le répertoire des plugins est déjà rempli, un `CheckCommand` Icinga2 ou
Nagios utilisant `PluginDir + "/check_opencloud_security"` fonctionne sans autre
configuration de chemin - voir [Icinga2 / Nagios](#icinga2-nagios) ci-dessous.

### Le configurer {#configuring-it}

**Le paquet ne configure volontairement rien.** L’exemple de configuration
désigne un hôte qui n’est pas le vôtre, et
`/etc/check-opencloud-security/config.yml` est un chemin que le plugin lit
réellement : installer l’exemple à cet endroit donnerait à chaque appel sur
l’hôte une cible par défaut que personne n’a choisie. Copiez ce dont vous avez
besoin :

```shell
sudo cp /usr/share/doc/check-opencloud-security/config.example.yml \
        /etc/check-opencloud-security/config.yml

sudo cp /usr/share/doc/check-opencloud-security/env.example \
        /etc/check-opencloud-security/env      # for the systemd units
```

`check-opencloud-security --configure` pose les mêmes questions de façon
interactive.

Les unités sont livrées désactivées et ont d’abord besoin de ce fichier `env` :

```shell
sudo systemctl enable --now check-opencloud-security.timer
sudo systemctl enable --now check-opencloud-security-refresh.timer
```

La seconde maintient à jour le calendrier des versions et la base des avis de
sécurité fournis, ce qui compte plus qu’il n’y paraît : tous deux sont livrés
*dans* le paquet (voir [Détection de fin de vie](../../README.md#end-of-life-detection)).

### Le mettre à jour et le supprimer {#updating-and-removing-it}

Avec `apt` et `dnf`, comme tout le reste sur l’hôte. `--upgrade-self` détecte un
paquet de distribution et refuse d’agir plutôt que de laisser pip installer une
seconde copie à côté, une copie que les commandes installées n’exécuteraient
jamais.

```shell
sudo apt install --only-upgrade check-opencloud-security   # or: dnf upgrade
sudo apt remove check-opencloud-security                   # or: dnf remove
```

La suppression ne touche pas à `/etc/check-opencloud-security/` : ce que vous y
avez placé vous appartient.

### L’interpréteur utilisé {#the-interpreter-it-uses}

Les commandes installées sont de petits lanceurs shell qui trouvent eux-mêmes un
Python 3.11 ou plus récent : d’abord `$COS_PYTHON`, puis `python3`, puis de
`python3.15` à `python3.11`, en vérifiant la version de chacun plutôt qu’en se
fiant à son nom. C’est pourquoi le RPM n’exige pas `python3 >= 3.11` : RHEL 9
répond 3.9 pour `python3` et fournit 3.11 et 3.12 à côté, et une dépendance
versionnée refuserait de s’installer sur un hôte qui exécute parfaitement cette
vérification.

Le `.deb`, lui, exige `python3 >= 3.11`, ce que Debian 12 et Ubuntu 24.04
satisfont. Sous Ubuntu 22.04, `python3` est la version 3.10, qui n’est plus
maintenue depuis octobre 2026 : apt y refuse le paquet. Installez-y le plugin
avec pipx sur un Python plus récent.

Si aucun interpréteur adapté n’est trouvé, la vérification se termine avec
**3 (UNKNOWN)** plutôt que de rendre un verdict qu’elle n’a jamais mesuré.
Indiquez un interpréteur dans `COS_PYTHON` pour régler le problème :

```shell
sudo dnf install python3.12
COS_PYTHON=/usr/bin/python3.12 check-opencloud-security --host opencloud.example.com
```

### Construire les paquets vous-même {#building-the-packages-yourself}

Ils sont construits à partir du wheel : une copie du dépôt produit donc la même
chose qu’une version publiée. Il faut [nfpm](https://nfpm.goreleaser.com/install/)
dans le `PATH` :

```shell
uv build                                        # the wheel first
python scripts/build_distro_packages.py         # both, into distro-packages/
python scripts/build_distro_packages.py --packager deb
```

L’arborescence, les dépendances et tout ce que déclarent les paquets se trouvent
dans [`packaging/nfpm.yaml`](../../packaging/nfpm.yaml). Les raisons de ce mode de
construction sont expliquées dans
[l’ADR 0039](../../adr/0039-the-plugin-ships-as-a-distribution-package-built-from-the-wheel.md).

## Postes de travail macOS et Linux (Homebrew) {#macos-and-linux-workstations-homebrew}

Utilisez cette méthode sur un ordinateur portable plutôt que sur un hôte de
supervision, par exemple pour tester une instance à la main avant d’intégrer la
vérification à Icinga. L’argument est le même que pour le `.deb` et le `.rpm`,
transposé à une autre plateforme : `brew` est la base des paquets sur ces
machines, et un `pip install --user` n’y figure pas et reste invisible pour
`brew outdated`.

```shell
brew install sowoi/tap/check-opencloud-security
check-opencloud-security --host opencloud.example.com
```

La formule se trouve dans un tap plutôt que dans Homebrew core, qui impose des
critères de notoriété que ce projet ne prétend pas remplir. `brew upgrade` la
maintient à jour ; `--upgrade-self` refuse volontairement d’agir sur une
installation Homebrew et l’indique, car pip écrirait dans le Cellar et la
prochaine opération `brew` l’annulerait discrètement.

La formule elle-même est générée à partir de ce que PyPI a publié, par
[`scripts/build_homebrew_formula.py`](../../scripts/build_homebrew_formula.py) -
voir [`packaging/README.md`](../../packaging/README.md#homebrew) si vous
maintenez le tap plutôt que d’installer à partir de celui-ci.

## Docker {#docker}
Utilisez cette méthode si vous préférez ne rien installer sur l’hôte. L’image
contient aussi le service d’analyse (voir
[Exécuter le scanner comme service](../../README.md#running-the-scanner-as-a-service)).

L’image publiée contient les deux points d’entrée : une vérification tient donc
en une commande, sans rien construire ni installer :
```shell
docker run --rm --entrypoint check-opencloud-security \
  okxo/opencloud-scanner:latest --host opencloud.example.com
```

Cette ligne, sa variante JSON et les options utiles qui l’accompagnent sont
réunies dans [Analyser en une ligne de commande](docker.md). La
commande par défaut de l’image démarre l’application web, c’est pourquoi le
plugin est sélectionné avec `--entrypoint`.

Construisez plutôt l’image vous-même si vous voulez exécuter votre propre copie
du dépôt. Tout ce qui concerne Docker se trouve dans [`docker/`](../../docker/),
et le contexte de construction est la racine du dépôt :
```shell
git clone https://github.com/sowoi/check-opencloud-security.git
cd check-opencloud-security
docker build -f docker/Dockerfile -t check-opencloud-security .
```

Lancer une vérification :
```shell
docker run --rm check-opencloud-security --host opencloud.example.com
```

Ou configurez-la entièrement par des [variables d’environnement](../../README.md#environment-variables)
(pratique, car vous n’avez pas à modifier la commande `docker run` pour chaque
hôte) :
```shell
docker run --rm -e COS_HOST=opencloud.example.com check-opencloud-security
```

L’image contient un `HEALTHCHECK` qui vérifie l’image et non une instance : que
le paquet s’importe et que le calendrier des versions et la base des avis de
sécurité fournis s’analysent correctement. Il n’a pas besoin du réseau et réussit
donc aussi sur un hôte isolé. Il sert au service d’analyse permanent ; un
conteneur de vérification ponctuelle se termine avant que Docker ne l’exécute.
Le service de `docker/docker-compose.monitoring.yml` le remplace par la sonde
HTTP `/healthz`, plus utile dès que quelque chose écoute réellement.

Le conteneur de vérification n’a besoin d’aucun port réseau, mais il doit pouvoir
atteindre l’instance OpenCloud elle-même. Si l’instance n’est accessible que sur
le réseau propre à l’hôte Docker, ajoutez `--network host` ou l’option
`--add-host` appropriée. Il s’exécute avec l’utilisateur non privilégié `nagios`
et se termine avec les mêmes codes de style Nagios (`0`/`1`/`2`/`3`) que le script
natif : il peut donc s’intégrer directement à toute chaîne de supervision qui
accepte déjà `docker run` comme commande de vérification (voir
[Icinga2 / Nagios](#icinga2-nagios) et [Icinga Director](icinga-director.md)
ci-dessous).

Si vous préférez ne pas construire localement, publiez l’image construite dans
votre propre registre (par exemple
`docker tag check-opencloud-security registry.example.com/check-opencloud-security`
suivi de `docker push ...`) et utilisez cette image sur vos hôtes de supervision.

## Icinga2 / Nagios {#icinga2-nagios}

Le `CheckCommand` complet, avec un argument pour chaque option utile sur un service, est fourni dans [`contrib/icinga2/check_opencloud_security.conf`](../../contrib/icinga2/check_opencloud_security.conf) ; l’exemple ci-dessous montre les plus courantes.
- Si vous avez installé le paquet avec pipx/uv/pip, repérez l’exécutable `check-opencloud-security` installé (par exemple avec `which check-opencloud-security`) et indiquez ce chemin dans `PluginDir`, ou copiez-le ou créez un lien symbolique dans votre dossier de plugins (généralement `/usr/lib/nagios/plugins/`).
- Si vous exécutez le script manuellement, placez plutôt `check_opencloud_security.py` dans votre dossier de plugins.
- Créez une nouvelle commande personnalisée :

```
object CheckCommand "check_opencloud_security" {
    import "plugin-check-command"
    command = [ PluginDir + "/check-opencloud-security" ]

    arguments += {
        "--host" = {
            description = "OpenCloud hostname, IP or URL"
            required = true
            value = "$address$"
        }

        "--port" = {
            description = "Port the instance listens on, e.g. 9200 (optional)"
            value = "$opencloud_port$"
        }

        "--proxy" = {
            description = "HTTP/HTTPS proxy (optional)"
            required = false
        }

        "--insecure" = {
            description = "Do not verify the instance's TLS certificate (optional)"
            set_if = "$opencloud_insecure$"
        }

        "--no-debug-ports" = {
            description = "Skip probing the OpenCloud debug ports (optional)"
            set_if = "$opencloud_no_debug_ports$"
        }

        "--debug" = {
            description = "Enable debugging output (optional)"
            set_if = "$opencloud_debug$"
        }

        "--warning" = {
            description = "Rating (0-5) at or below which the check warns (optional)"
            value = "$opencloud_warning$"
        }

        "--critical" = {
            description = "Rating (0-5) at or below which the check is critical (optional)"
            value = "$opencloud_critical$"
        }

        "--profile" = {
            description = "Profil de seuils nommé - strict, ops ou lenient - définit les réglages de notation non fixés (facultatif)"
            value = "$opencloud_profile$"
        }

        "--check-hardening" = {
            description = "Also check hardening measures and security headers (optional)"
            set_if = "$opencloud_check_hardening$"
        }

        "--update-source" = {
            description = "Where the newest release is looked up: auto, feed, pinned, bundled, off"
            value = "$opencloud_update_source$"
        }
    }
}
```

- Créez un nouvel objet Service.

```
object Service "Service: OpenCloud Security Scan" {
   import               "generic-service"
   host_name =          "YOUR OPENCLOUD HOST"
   check_command =      "check_opencloud_security"
   check_interval = 24h
}
```

L’analyse ne communique qu’avec votre propre instance : il n’y a donc aucune
limite de requêtes externe à respecter, et un intervalle inférieur à 24 h est
techniquement possible. Une analyse complète envoie toutefois quelques dizaines
de requêtes en plus des sondes des ports de débogage : une vérification toutes
les heures est donc un minimum raisonnable. Si la
[vérification des mises à jour](../../README.md#update-check) utilise le flux
GitHub, limitez-vous à quelques exécutions par jour ou fournissez un jeton.

### Utiliser plutôt l’image Docker {#using-the-docker-image-instead}

Si vous avez installé la vérification avec [Docker](#docker), faites pointer le
`CheckCommand` vers `docker` pour qu’il lance le conteneur à la demande au lieu
d’un binaire local :

```
object CheckCommand "check_opencloud_security_docker" {
    import "plugin-check-command"
    command = [ "/usr/bin/docker" ]

    arguments += {
        "run" = {
            order = -5
            value = "run"
        }
        "--rm" = {
            order = -4
            value = "--rm"
        }
        "image" = {
            order = -3
            skip_key = true
            value = "check-opencloud-security"
        }
        "--host" = {
            description = "OpenCloud hostname, IP or URL"
            required = true
            value = "$address$"
        }
        "--port" = {
            description = "Port the instance listens on, e.g. 9200 (optional)"
            value = "$opencloud_port$"
        }
        "--proxy" = {
            description = "HTTP/HTTPS proxy (optional)"
            required = false
        }
        "--insecure" = {
            description = "Do not verify the instance's TLS certificate (optional)"
            set_if = "$opencloud_insecure$"
        }
        "--debug" = {
            description = "Enable debugging output (optional)"
            set_if = "$opencloud_debug$"
        }
        "--warning" = {
            description = "Rating (0-5) at or below which the check warns (optional)"
            value = "$opencloud_warning$"
        }
        "--critical" = {
            description = "Rating (0-5) at or below which the check is critical (optional)"
            value = "$opencloud_critical$"
        }
        "--profile" = {
            description = "Profil de seuils nommé - strict, ops ou lenient - définit les réglages de notation non fixés (facultatif)"
            value = "$opencloud_profile$"
        }
        "--check-hardening" = {
            description = "Also check hardening measures and security headers (optional)"
            set_if = "$opencloud_check_hardening$"
        }
    }
}
```

Cela suppose que l’image `check-opencloud-security` a déjà été construite (ou
téléchargée) sur l’hôte Icinga2, que l’utilisateur qui exécute le démon Icinga2
a le droit de communiquer avec le socket Docker, et que le conteneur peut
atteindre l’instance OpenCloud.

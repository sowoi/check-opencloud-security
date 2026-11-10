# Analyser plusieurs instances

Plusieurs instances ont souvent besoin de ports, de canaux de versions et d’exemptions
différents. Ce guide montre quand utiliser une commande partagée, comment conserver un
fichier de configuration par instance et comment planifier les vérifications qui en
résultent.

<!-- TOC -->
* [Analyser un parc d’instances](#checking-a-fleet-of-instances)
  * [Une commande, plusieurs hôtes](#one-command-several-hosts)
  * [Un fichier de configuration par instance](#one-configuration-file-per-instance)
  * [Une boucle sur les fichiers](#a-loop-over-the-files)
  * [D’où lancer les vérifications](#where-the-checks-should-run-from)
  * [Garder les exemptions sous contrôle](#keeping-the-waivers-honest)
  * [N’alerter que sur ce qui a changé](#only-alerting-on-what-changed)
  * [Un tableau de bord pour toute la flotte](#one-dashboard-for-the-whole-fleet)
  * [Planifier l’ensemble](#scheduling-the-whole-thing)
<!-- TOC -->


## Une commande, plusieurs hôtes {#one-command-several-hosts}

`--host` accepte une liste séparée par des virgules. Le plugin analyse les hôtes
l’un après l’autre, affiche un résumé d’une ligne suivi d’un bloc par hôte, et
se termine avec le pire état rencontré - voir
[Vérifier plusieurs hôtes](../../README.md#checking-multiple-hosts).

```shell
check-opencloud-security --check-hardening \
  --host opencloud1.example.com,opencloud2.example.com:9200,[2001:db8::1]
```

C’est la bonne solution lorsque les instances se ressemblent. Tout ce qui suit
`--host` s’applique à toutes : dès qu’une instance a besoin de `--insecure` ou
d’une exemption que les autres n’ont pas, cette approche ne suffit plus.

L’agrégation fait aussi perdre l’historique par hôte que votre système de
supervision conserverait sinon. Si vous voulez un service en rouge par instance
défaillante plutôt qu’un seul service en rouge pour le groupe, utilisez plutôt
une vérification par hôte.

Ajoutez ici `--webhook-digest` : le webhook se déclenche alors au plus une fois
pour toute la liste `--host`, au lieu d’une fois par hôte répondant à
`--webhook-on`. C’est utile lorsque le destinataire du webhook est une personne
qui préfère recevoir un seul message sur trois instances défaillantes plutôt
que trois notifications séparées. L’option ne regroupe que ce qui se passe
*à l’intérieur de ce seul processus* : comme il s’agit d’une option sur un seul
`ScanContext`, elle n’a aucun effet sur les méthodes « un fichier de
configuration par instance » et « une boucle sur les fichiers » ci-dessous, où
chaque instance s’exécute dans son propre processus sans rien à regrouper.
Chacune envoie alors toujours son propre webhook, exactement comme sans
l’option.

## Un fichier de configuration par instance {#one-configuration-file-per-instance}

Chaque instance a son fichier, et ce fichier contient tout ce qui la distingue.
Rien n’est répété sur la ligne de commande : une modification se fait donc à un
seul endroit.

```yaml
# /etc/check-opencloud-security/prod-eu.yml
host: opencloud-eu.example.com
check_hardening: true
update_warning: true

scanner:
  target_port: 9200
  release_track: production
  ignore_hardenings:
    # The reverse proxy owns this header; the instance cannot set it.
    - hstsPreload

releases:
  mode: auto
  token: secret://releases_token
```

```shell
check-opencloud-security --config /etc/check-opencloud-security/prod-eu.yml
```

L’ordre de priorité est **ligne de commande > variable d’environnement >
fichier de configuration > valeur par défaut** : un fichier propre à une
instance peut donc être surchargé le temps d’une exécution sans le modifier. La
syntaxe complète, y compris `secret://`, est décrite dans
[Fichier de configuration et secrets](../../README.md#configuration-file-and-secrets).

Créez le premier fichier avec `check-opencloud-security --configure --config
/etc/check-opencloud-security/prod-eu.yml`, puis copiez-le pour les autres.

## Une boucle sur les fichiers {#a-loop-over-the-files}

Avec un fichier par instance, analyser le parc revient à une boucle `for`, et ce
sont les codes de sortie qui servent au compte rendu :

```shell
#!/bin/sh
# Scan every configured instance; exit with the worst state seen.
set -u

worst=0
rank() { case "$1" in 2) echo 3 ;; 1) echo 2 ;; 3) echo 1 ;; *) echo 0 ;; esac; }

for config in /etc/check-opencloud-security/*.yml; do
  check-opencloud-security --config "$config" || state=$?
  state="${state:-0}"
  [ "$(rank "$state")" -gt "$(rank "$worst")" ] && worst="$state"
  unset state
done

exit "$worst"
```

`rank` est nécessaire, car les codes de sortie Nagios ne sont pas classés par
gravité : `CRITICAL` (2) l’emporte sur `WARNING` (1), qui l’emporte sur
`UNKNOWN` (3), qui l’emporte sur `OK` (0). Un tri numérique présenterait un hôte
injoignable comme plus grave qu’un hôte en fin de vie.

## D’où lancer les vérifications {#where-the-checks-should-run-from}

Le plugin analyse par le réseau, depuis l’endroit où il s’exécute : cet endroit
détermine donc ce qu’il peut voir.

- Une instance derrière un pare-feu a besoin d’une vérification exécutée à
  l’intérieur de ce pare-feu, pas d’une vérification sur le serveur de
  supervision passant par une ouverture percée pour l’occasion.
- L’application de HTTPS et la confiance accordée au certificat dépendent du
  chemin emprunté jusqu’à l’instance. Une analyse à travers un répartiteur de
  charge qui termine TLS mesure le répartiteur de charge.
- Les sondes des ports de débogage n’ont de sens que depuis un réseau qui n’est
  *pas censé* les atteindre. Depuis l’hôte même de l’instance, elles trouveront
  des ports qu’aucune personne extérieure ne pourrait atteindre.

Si plusieurs consommateurs de supervision ont besoin du même résultat, exécutez
le [service d’analyse](../../README.md#running-the-scanner-as-a-service) près des
instances et laissez-les partager son cache. Le plugin lui-même ne l’utilise
jamais (il analyse toujours dans son propre processus) : le service sert donc
aux tableaux de bord et aux scripts.

## Garder les exemptions sous contrôle {#keeping-the-waivers-honest}

Réexaminez régulièrement les entrées `ignore_hardenings` pour que les constats
acceptés ne masquent pas de nouveaux problèmes. Les exemptions disposent de deux
garde-fous :

- Une exemption ne supprime jamais que l’alerte. Le constat reste dans le
  document de résultat avec `"ignored": true`, et `--debug` l’explique toujours ;
  voir [Accepter un constat que vous ne corrigerez pas](hardening.md#accepting-a-finding-you-are-not-going-to-fix).
- Seul un contrôle *réellement en échec* peut être exempté : une exemption ne
  peut donc pas couvrir discrètement une mesure qui régresse plus tard en un
  autre constat.

Pour les réexaminer, lancez une analyse sans les exemptions et comparez :

```shell
for config in /etc/check-opencloud-security/*.yml; do
  echo "== $config"
  COS_SCANNER_IGNORE_HARDENINGS="" check-opencloud-security --config "$config" --debug \
    | grep -E 'ignored|waived|FAIL'
done
```

Un identifiant n’apparaîtra jamais dans cette liste, quel que soit le nombre
d’instances : `publicLinkExpirationEnforced` est codé en dur par OpenCloud et
échoue sur toutes les instances. Il est donc enregistré mais exclu de l’alerte,
de la métrique `hardenings_missing` et du webhook. Il n’a pas besoin
d’exemption ; voir
[Mesures qui ne sont pas des paramètres](hardening.md#measures-that-are-not-settings).

## N’alerter que sur ce qui a changé {#only-alerting-on-what-changed}

Des alertes répétées pour des constats inchangés peuvent masquer les nouveaux
problèmes. Donnez à chaque hôte une référence (baseline) pour ne signaler que
les régressions :

```shell
for config in /etc/check-opencloud-security/*.yml; do
  check-opencloud-security --config "$config" \
      --baseline /var/lib/check_opencloud/baseline.json \
      --warn-on-new
done
```

Un seul fichier suffit pour tout le parc : il contient une entrée par hôte,
identifiée par l’hôte tel qu’il a été indiqué sur la ligne de commande. Une
liste `--host` séparée par des virgules fonctionne de la même façon.

Deux points à respecter :

- L’utilisateur de la supervision doit être propriétaire du répertoire. Le
  fichier est écrit de façon atomique avec des droits réservés à son
  propriétaire, et une référence impossible à écrire est signalée par une ligne
  de sortie, sans plus : elle ne change jamais le verdict.
- Écrivez l’hôte de la même façon partout. `opencloud.example.com` et
  `https://opencloud.example.com/` sont normalisés vers le même hôte, mais
  `10.0.0.5` ne correspond pas au nom qui se résout vers cette adresse, et la
  vérification le traiterait comme un hôte jamais vu.

Une version ayant dépassé sa fin de vie continue de déclencher une alerte à
chaque exécution, quelle que soit la référence, car elle ne reçoit
plus de correctifs de sécurité et le risque augmente tant qu’elle
reste en service. Voir
[Ne signaler que ce qui a changé](../../README.md#reporting-only-what-changed).

Ajoutez `--self-update-check` sur un seul hôte du parc - pas sur tous - pour être
averti lorsqu’une nouvelle version du plugin est publiée. Le résultat est mis en
cache pendant un jour et ne change jamais le code de sortie.

## Un tableau de bord pour toute la flotte {#one-dashboard-for-the-whole-fleet}

La supervision répond, hôte par hôte, à la question « cette instance est-elle
en panne maintenant ». Une revue de flotte en pose d'autres : quelles
instances utilisent une version qui ne reçoit plus de correctifs, quelles
exemptions expirent ce mois-ci, quel constat échoue partout, et quelle
instance personne n'a examinée récemment. Conservez les documents de résultat
écrits par `scan`, et `fleet` répond aux quatre à partir des seuls fichiers :

```shell
dir="/var/lib/opencloud-reports/$(date +%F)"
mkdir -p "$dir"
for host in opencloud1.example.com opencloud2.example.com; do
  check-opencloud-scanner scan "$host" > "$dir/$host.json"
done
check-opencloud-scanner fleet /var/lib/opencloud-reports \
    --inventory /etc/check-opencloud-security/hosts.txt --format html > fleet.html
```

Elle n'analyse rien et ne stocke rien ; seul le rapport le plus récent de
chaque hôte compte, et la version comme les échéances des exemptions sont
évaluées par rapport à aujourd'hui plutôt qu'au jour du rapport. Avec un
inventaire, un hôte sans aucun rapport apparaît comme manquant. Voir
[`fleet` - un tableau de bord à partir de résultats enregistrés](scanner-cli.md#fleet-a-dashboard-from-saved-results).

## Planifier l’ensemble {#scheduling-the-whole-thing}

- Avec Icinga2 : un `Service` par hôte, appliqué depuis un groupe d’hôtes - voir
  [Icinga Director](icinga-director.md) ou
  [Déploiement automatisé avec Ansible](ansible.md).
- Sans Icinga2 : un timer systemd ou une entrée cron qui exécute la boucle
  ci-dessus, voir [Planification](scheduling.md).
- Sur un cluster : un `CronJob`, voir [Kubernetes](kubernetes.md).

Échelonnez les planifications. Vingt instances analysées à `0 6 * * *`
signifient vingt analyses simultanées depuis une seule adresse, et la
vérification des mises à jour atteindra en chemin la limite de requêtes anonymes
de GitHub.

---

[Retour à l’index de la documentation](../README.md) | [Retour au README principal](../../README.md)

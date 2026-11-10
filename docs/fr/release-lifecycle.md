# Cycle de vie des versions

OpenCloud maintient les canaux Rolling, Production et LTS en parallèle. Le support d’une version
dépend donc de son canal et de son numéro. Ce guide explique comment le
scanner utilise les lignes de version et le calendrier fourni, choisit une mise à jour et applique
`--release-track`.

Le [README principal](../../README.md#end-of-life-detection) indique l’état actuel
de chaque canal et les paramètres qui désactivent ce contrôle.

<!-- TOC -->
* [Canaux de versions, fin de vie et recommandation de mise à jour](#release-tracks-end-of-life-and-the-update-recommendation)
  * [Pourquoi un numéro de version ne suffit pas](#why-a-version-number-is-not-an-answer)
  * [Ce que le calendrier fourni peut et ne peut pas vous dire](#what-the-bundled-schedule-can-and-cannot-tell-you)
  * [La version recommandée suit votre canal](#the-recommended-release-follows-your-track)
  * [Déclarer votre canal de versions](#declaring-your-release-track)
<!-- TOC -->


## Pourquoi un numéro de version ne suffit pas {#why-a-version-number-is-not-an-answer}

OpenCloud publie les versions rolling, production et LTS à partir de la même
séquence de numéros. Conséquence pour la supervision : la *même* version peut
être parfaitement à jour ou abandonnée depuis longtemps selon le canal sur
lequel elle a été publiée. `7.2.3` est la version de production actuelle alors
que le canal rolling en est déjà à `7.4.0`, tandis que `7.3.0` - une version
*plus élevée* - a cessé de recevoir des correctifs le jour où `7.4.0` est sortie.

Le plugin raisonne donc en **lignes de version** (`MAJOR.MINOR`), l’unité
qu’OpenCloud maintient : `7.2.3` est un correctif de la ligne `7.2`. Une ligne
peut appartenir à plusieurs canaux - `7.2` est sortie en version rolling avant
d’être promue en production, et `4.0` est à la fois la ligne de production
précédente et la ligne LTS actuelle - et elle est jugée selon le canal qui la
prend en charge le plus longtemps.

Le calendrier est livré dans `opencloud_local_scan/data/release_schedule.json`
et extrait des dates de publication de la documentation d’administration
d’OpenCloud, la seule source qui indique le *type* de version ; la liste des
versions GitHub ne permet pas de distinguer une version rolling d’une version de
production. Il est actualisé à chaque publication et chaque semaine par un
[workflow planifié](../../.github/workflows/release-schedule.yml), et la même
exécution réécrit le tableau du README : les versions citées sont donc celles
auxquelles le plugin compare réellement, et non celles qui étaient actuelles
lors de la rédaction de cette page. Tout le reste de cette section, y compris
les exemples détaillés ci-dessous, est rédigé à la main et peut citer des
versions plus anciennes pour illustrer un point.

## Ce que le calendrier fourni peut et ne peut pas vous dire {#what-the-bundled-schedule-can-and-cannot-tell-you}

Voici ce qu’il faut savoir sur le calendrier fourni :

- **Les versions LTS ne sont disponibles qu’avec un abonnement** : une ligne LTS
  est reconnue grâce à la documentation, mais ses versions peuvent ne jamais
  apparaître publiquement. Si votre fournisseur s’est engagé sur une autre
  période, faites pointer `release_schedule` vers votre propre fichier plutôt que
  de laisser décider le fichier fourni.
- **Une version plus récente que le calendrier n’est jamais notée `F` et n’est
  jamais retenue contre l’instance.** Le fichier vieillit entre deux mises à jour
  de ce paquet : une instance corrigée rapidement est donc souvent plus récente
  que les données auxquelles elle est comparée. Elle conserve sa note, ne reçoit
  aucune recommandation de mise à jour et n’est jamais déclarée en fin de vie
  pour cette raison.
- **Le scanner le signale lorsque cela se produit.** Une version plus récente que
  la dernière version enregistrée pour sa ligne - ou située sur une ligne plus
  récente que toutes les lignes connues - active `lifecycle.scheduleStale` dans
  le document de résultat, renseigne `scheduleNote`, `scheduleUpdated` et
  `scheduleSource`, et ajoute une ligne à la sortie du plugin :

  ```
  Release schedule: 7.4.1 is newer than anything in the bundled release schedule (generated 2026-08-12), so that schedule is probably out of date. This is not counted against the instance. Check the current support window at https://docs.opencloud.eu/docs/admin/resources/lifecycle/, and regenerate the schedule with scripts/update_release_schedule.py.
  ```

  C’est une remarque sur le fichier fourni, pas sur l’instance : la période de
  support calculée provient de données plus anciennes que la version évaluée, et
  il vaut donc la peine de la vérifier à la [source][lifecycle]. Mettre à jour le
  paquet, ou exécuter `python scripts/update_release_schedule.py`, fait
  disparaître cette remarque. Une ligne réellement expirée le reste : appliquer
  un correctif dans une ligne abandonnée ne la rouvre pas, et la remarque
  explique les données sans renverser le verdict.

## La version recommandée suit votre canal {#the-recommended-release-follows-your-track}

Un flux de versions ne connaît que la version la plus récente *tous canaux
confondus*, et chez OpenCloud c’est toujours une version rolling. La recommander
à une instance production ou LTS la ferait passer sur un canal dont
la période de support est de trois semaines, ce qu’un opérateur du canal
production n’a pas choisi.

La vérification des mises à jour utilise donc le
[calendrier des versions](../../README.md#end-of-life-detection) pour choisir une
cible sur le canal propre à l’instance :

| Installée | Canal      | Recommandée | Pourquoi                                                              |
|:----------|:-----------|:------------|:----------------------------------------------------------------------|
| `7.2.3`   | production | *rien*      | Version de production actuelle, même si rolling en est à `7.4.0`      |
| `7.2.0`   | production | `7.2.3`     | Le correctif le plus récent de la même ligne                          |
| `7.3.0`   | rolling    | `7.4.0`     | Sur rolling, la version la plus récente est la bonne                  |
| `4.0.0`   | LTS        | `4.0.8`     | C’est là que se trouvent les rétroportages                            |

La version la plus récente tous canaux confondus reste signalée, sous
`newestRelease` dans le résultat JSON et la charge utile du webhook : rien n’est
masqué, elle n’est simplement pas présentée comme la version à installer. Si le
flux annonce un correctif plus récent de la ligne sur laquelle vous êtes déjà,
le flux l’emporte, car il est plus récent que le calendrier fourni.

## Déclarer votre canal de versions {#declaring-your-release-track}

Par défaut, le calendrier des versions détermine à quel canal appartient une
version et la juge aussi favorablement que les faits le permettent : `7.2.3`
figure à la fois sur le canal rolling et sur le canal production, elle est donc
traitée comme une version de production et considérée comme à jour.

C’est le bon choix par défaut tant qu’aucun canal n’est déclaré, mais il ne
convient pas à toutes les instances. Si vous suivez délibérément le canal rolling, `7.2.3` n’est plus
prise en charge depuis la sortie de `7.4.0`, et vous voulez en être informé.
`--release-track` indique votre canal, et la version est alors jugée sur ce seul
canal :

```bash
check-opencloud-security --host opencloud.example.com --release-track rolling
```

`--release-track auto` est la valeur par défaut : le calendrier des versions
détermine à quel canal appartient la version installée. C’est la même réponse
que sans l’option, mais formulée explicitement, et c’est ce qui permet
d’utiliser une même configuration pour des instances sur des canaux différents :

```bash
check-opencloud-security --host opencloud.example.com --release-track auto
```

| Installée | Déclaré             | Verdict                                                                            |
|:----------|:--------------------|:-----------------------------------------------------------------------------------|
| `7.2.3`   | *rien* ou `auto`    | Prise en charge - version de production actuelle                                   |
| `7.2.3`   | `production`        | Prise en charge - version de production actuelle                                   |
| `7.2.3`   | `rolling`           | **Fin de vie** - remplacée par `7.4.0`, mettre à jour vers `7.4.0`                 |
| `7.4.0`   | `production`        | Prise en charge - en avance sur le canal production, dont la version actuelle est `7.2.3` |
| `2.3.0`   | `production`        | **Fin de vie** - en retard sur le canal production, mettre à jour vers `7.2.3`     |
| `4.0.8`   | `lts`               | Prise en charge jusqu’à la fin de la période de deux ans                           |

Il en découle deux conséquences :

- **Être en avance sur votre canal n’est pas un constat.** Une instance
  production passée à la version rolling actuelle dispose de tout ce que livre
  le canal production, et plus encore : elle est donc signalée comme en avance
  sur son canal au lieu d’être notée `F`. Seule une version *antérieure* à la
  version actuelle de votre canal n’est plus prise en charge.
- **La vérification ne recommande jamais de rétrogradation.** Si votre canal
  déclaré ne propose aucune version *supérieure*, la recommandation de mise à
  jour reste vide et la raison explique la situation. Revenir de `7.4.0` à
  `7.2.3` est une décision humaine, pas celle d’un plugin de supervision.

Le canal déclaré oriente aussi la recommandation de mise à jour décrite dans
[la section ci-dessus](#the-recommended-release-follows-your-track), et la sortie
le signale comme déclaré pour le distinguer d’un canal déduit :

```
Release lifecycle: 7.2 (rolling track declared), out of support since 2026-07-14, upgrade to 7.4.0
```

Une valeur inconnue est ignorée plutôt que traitée comme une erreur : une faute
de frappe dans un fichier de configuration ramène au comportement par défaut au
lieu de mettre la vérification hors service.

## Avertir avant la fin de vie {#warning-before-the-end-of-life}

La fin de vie devient `CRITICAL` le jour même, ce qui est trop tard pour
planifier une mise à niveau. `--eol-warning DAYS` (`COS_EOL_WARNING`, YAML
`eol_warning`) transforme un résultat autrement `OK` en `WARNING` dès qu’il reste
`DAYS` jours de support ou moins à la ligne en service :

```text
WARNING: The 7.2 release line reaches end of life on 2026-10-14 (20 days left). Upgrade to 7.4.0.
```

Cette option ne fait qu’élever un résultat `OK` ; un résultat déjà `WARNING` ou
`CRITICAL` conserve sa propre ligne. Une ligne sans date de fin de vie publiée
n’a rien à décompter et n’avertit jamais. `0`, la valeur par défaut, désactive
l’option.

## La mise à niveau lève-t-elle les avis de sécurité ? {#does-the-upgrade-clear-the-advisories}

Lorsque la version installée est concernée par des avis de sécurité connus,
l’analyse enregistre `upgradePath` : l’effet du passage à la version recommandée
sur chacun d’eux.

```json
{"upgradePath": {"target": "7.2.4", "fixes": ["GHSA-aaaa"],
  "stillAffected": ["GHSA-bbbb"], "safeVersion": "7.3.0"}}
```

Chaque plage de versions d’un avis est comparée à la cible : un correctif
rétroporté sur une autre ligne compte donc. `safeVersion` est la plus ancienne
version postérieure à tous les correctifs qui manquent encore à la cible, ou
`null` lorsque l’un d’eux n’a pas encore de correctif. Le plugin l’affiche sur
une ligne de détail :

```text
Upgrade path: 7.2.4 fixes GHSA-aaaa but is still affected by GHSA-bbbb; 7.3.0 is the first release that clears them all.
```

## Répéter chaque mise à niveau {#rehearse-every-upgrade}

`upgradePath` couvre la version unique recommandée par le scan.
`upgradeRehearsal` couvre chaque version qui mérite une mise à niveau : le
dernier correctif de la ligne installée et la dernière version de chaque ligne
ultérieure (uniquement les lignes du canal déclaré, si l'instance en déclare
un). Pour chacune, il indique les avis qu'elle `fixes`, ceux par lesquels elle
reste `stillAffected`, ceux qu'elle `introduces`, si elle est `endOfLife` et le
`rating` que le scan lui attribuerait.

```json
{"upgradeRehearsal": [
  {"version": "7.2.4", "line": "7.2", "recommended": false,
   "fixes": ["GHSA-aaaa"], "stillAffected": ["GHSA-bbbb"], "introduces": [],
   "endOfLife": false, "versionRating": 2, "rating": 2}
]}
```

La note utilise les mêmes règles de version que le scan. Les contrôles échoués
de l'instance continuent de la plafonner (`versionRating` indique ce que la
version seule permettrait), car une mise à niveau change la version, pas le
proxy qui se trouve devant elle. Le plugin affiche une ligne de détail avec
ses propres lettres de notation :

```text
Upgrade rehearsal: 7.2.4 fixes 1 finding, leaves 1, reaches rating D; 7.3.0 fixes 2 findings, leaves 0, reaches rating A+.
```

La simulation utilise uniquement le calendrier et la base des avis, intégrés ou
actualisés. Une version ou un avis publié ultérieurement peut modifier le
résultat.

L'application web affiche les mêmes entrées sous **Ce qu'une mise à niveau
vous apporterait** : une ligne par version candidate, avec les avis qu'elle
lève, ceux qu'elle laisse et la note qu'elle atteindrait. Lorsque la version
seule obtiendrait mieux, l'écart vient des constats de cette instance, qu'une
mise à niveau ne touche pas.

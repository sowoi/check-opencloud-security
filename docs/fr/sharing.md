# Partage par lien public : ce que ce scanner vérifie, et pourquoi

Pour un lien de partage public, la seule possession de l'URL peut suffire à
accéder à son contenu. Le scanner lit les capacités annoncées par OpenCloud pour
vérifier si les liens exigent un mot de passe et si une expiration automatique
est signalée.

<!-- TOC -->
* [Partage par lien public : ce que ce scanner vérifie, et pourquoi](#public-link-sharing-what-this-scanner-checks-and-why)
  * [1. Un lien public peut-il être créé sans mot de passe : `publicLinkPasswordEnforced`](#1-can-a-public-link-be-created-without-a-password-publiclinkpasswordenforced)
  * [2. Les liens publics expirent-ils automatiquement : `publicLinkExpirationEnforced`](#2-do-public-links-expire-automatically-publiclinkexpirationenforced)
  * [Ce que contient encore ce document, et pourquoi rien d'autre n'est contrôlé](#what-else-is-in-that-document-and-why-none-of-it-is-checked)
  * [Gravité et effet sur la note](#severity-and-rating-impact)
<!-- TOC -->


## 1. Un lien public peut-il être créé sans mot de passe : `publicLinkPasswordEnforced` {#1-can-a-public-link-be-created-without-a-password-publiclinkpasswordenforced}

Le document de capacités indique, pour chaque type de partage, si un mot de
passe est exigé : les liens en lecture seule, en dépôt seul et en modification
sont chacun couverts par leur propre indicateur `enforced_for`. Ce contrôle ne
réussit que lorsque **tous** exigent un mot de passe - si ne serait-ce qu'un
type de partage peut être créé sans, quiconque détient cette URL dispose des
données qu'elle expose, indéfiniment, sans le moindre identifiant.

**L’échec peut concerner certains types de liens seulement.** OpenCloud impose
un mot de passe sur les liens en lecture seule par défaut, mais pas sur ceux en
écriture : la raison habituelle de cet échec est donc que les liens en dépôt
seul ou en modification sont restés à leur valeur par défaut. Un lien en
écriture sans mot de passe est la plus grave des deux lacunes : il permet à un
visiteur anonyme d'ajouter ou d'écraser des fichiers, et pas seulement de les
lire.

**Correction :** définissez
`OC_SHARING_PUBLIC_SHARE_MUST_HAVE_PASSWORD=true` et
`OC_SHARING_PUBLIC_WRITEABLE_SHARE_MUST_HAVE_PASSWORD=true`. Préférez ces noms
globaux `OC_SHARING_*` aux formes obsolètes `FRONTEND_OCS_*` encore citées dans
certains guides anciens. Le mot de passe finalement défini sur un lien est
lui-même régi par `passwordPolicyEnforced` - voir [Authentification : la
politique de mot de passe des liens est-elle assez
robuste](authentication.md#5-is-the-link-password-policy-strong-enough-passwordpolicyenforced).

## 2. Les liens publics expirent-ils automatiquement : `publicLinkExpirationEnforced` {#2-do-public-links-expire-automatically-publiclinkexpirationenforced}

Le champ `files_sharing.public.expire_date.enabled` du document de capacités est
lu directement. Dans les versions actuelles d'OpenCloud, il s'agit d'un `false`
figé dans le service frontend - une constante, non un réglage - si bien que
toutes les instances renvoient la même valeur, quelle que soit leur
configuration. **Ce contrôle ne déclenche jamais d'alerte** pour
cette raison : il est exclu de la ligne « Missing hardening », de la métrique
`hardenings_missing` et de la charge utile du webhook, car un avertissement que
aucun réglage ne permet de corriger risque de détourner l’attention des
problèmes qui peuvent être corrigés - voir [Mesures qui ne sont pas des
réglages](hardening.md#measures-that-are-not-settings). `--debug` continue de
l'afficher, avec l'explication.

Il est conservé dans le catalogue plutôt que supprimé, afin qu'une future
version d'OpenCloud rendant l'expiration automatique configurable soit détectée
dès que le document de capacités renverra autre chose que `false` - le
même raisonnement que celui documenté pour `userEnumerationRestricted` dans
[Authentification](authentication.md#4-is-account-search-restricted-to-shared-groups-userenumerationrestricted).

**Si l'expiration compte réellement pour un déploiement aujourd'hui :** aucun
réglage ne permet de l'obtenir. Une expiration doit être définie partage par
partage au moment de la création, ou la durée de vie effective du lien doit être
régie par un élément entièrement extérieur à OpenCloud - par exemple une règle
de proxy inverse ou un processus externe qui révoque les partages selon un
calendrier.

## Ce que contient encore ce document, et pourquoi rien d'autre n'est contrôlé {#what-else-is-in-that-document-and-why-none-of-it-is-checked}

Le document de capacités décrit d’autres aspects du partage. Le tableau
ci-dessous explique pourquoi ils ne font pas l’objet de contrôles. Ces
explications ont été vérifiées dans
`services/frontend/pkg/revaconfig/config.go` dans
[opencloud-eu/opencloud](https://github.com/opencloud-eu/opencloud) :

| Capacité | Pourquoi il n'y a pas de contrôle |
|:--|:--|
| `auto_accept_share`, `share_with_group_members_only`, `share_with_membership_groups_only`, `group_sharing`, `sharing_roles`, `api_enabled` | Constantes figées dans la table des capacités. Toutes les instances renvoient la même valeur : un contrôle ne dirait donc rien du déploiement - la même raison que pour `publicLinkExpirationEnforced`, qui ne déclenche jamais d'alerte. |
| `public.upload`, `public.send_mail`, `public.social_share`, `public.alias`, `public.multiple`, `public.supports_upload_only`, `public.can_edit` | Figées de la même manière. |
| `federation.incoming`, `federation.outgoing` | Configurables via `OC_ENABLE_OCM`, mais la description d'OpenCloud elle-même indique que sa modification n'est **pas prise en charge** et que « le comportement du backend n'est pas modifié » : cela régit ce qui est annoncé aux clients, non ce que fait le serveur. Un constat sur lequel un exploitant ne peut pas agir avec un effet réel est pire que pas de constat du tout. |
| `public.default_permissions` | Réellement configurable (`FRONTEND_DEFAULT_LINK_PERMISSIONS` : `0` interne, `1` visiteur public, `1` par défaut). Pas encore contrôlée : toutes les instances avec la configuration par défaut échoueraient. Il reste à déterminer si cette alerte aiderait les exploitants. |
| `deny_access`, `search_min_length` | Configurables, mais il s'agit respectivement d'une expérimentation obsolète et d'un réglage d'ergonomie de recherche, dont aucun ne change qui peut accéder aux données. |

La règle que suit ce tableau est celle d'`AGENTS.md` : avant d'ajouter un
contrôle de durcissement, vérifier dans le code source d'OpenCloud qu'un
exploitant peut réellement le modifier.

## Gravité et effet sur la note {#severity-and-rating-impact}

Les deux sont des indicateurs de durcissement, signalés uniquement avec
`--check-hardening` (ou systématiquement dans le résultat web).
`publicLinkPasswordEnforced` se comporte comme tout autre indicateur de
durcissement : un échec ne plafonne pas la note à lui seul, mais fait passer un
résultat Icinga sinon `OK` en `WARNING` et l'inscrit dans la ligne « Missing
hardening ». `publicLinkExpirationEnforced` est entièrement exclu de cette
ligne, pour la raison exposée plus haut - voir [Les mesures de durcissement, une
par une](hardening.md) pour le tableau complet et la règle générale.

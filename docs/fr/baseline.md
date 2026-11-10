# Signaler uniquement ce qui a changé

Utilisez `--baseline` pour enregistrer les constats de chaque scan et les
comparer à ceux de l'exécution suivante. Ajoutez `--warn-on-new` pour n'alerter
que lorsque des constats sont nouveaux ou se sont aggravés. Les problèmes
existants restent visibles dans le rapport.

Le [README principal](reference.md#reporting-only-what-changed) en donne la
version courte. Cette page décrit le comportement complet : les formats de
comparaison, ce qui compte comme une régression, et les règles qui empêchent une
référence de masquer quoi que ce soit.

<!-- TOC -->
* [Signaler uniquement ce qui a changé](#reporting-only-what-changed)
  * [Écrire et comparer une référence](#writing-and-comparing-a-baseline)
  * [Ce qui compte comme une régression](#what-counts-as-a-regression)
  * [Points à connaître](#points-worth-knowing)
<!-- TOC -->


## Écrire et comparer une référence {#writing-and-comparing-a-baseline}

`--baseline` désigne le fichier dans lequel les constats de chaque exécution
sont écrits, et le fichier auquel l'exécution suivante est comparée :

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json
```

À lui seul, cela n'ajoute qu'une ligne à la sortie (`Baseline: ...`). Ajoutez
`--warn-on-new` pour en tirer parti :

```bash
check-opencloud-security -H opencloud.example.com \
    --check-hardening \
    --baseline /var/lib/check_opencloud/baseline.json \
    --warn-on-new
```

Le contrôle signale alors `OK` tant que la situation est inchangée, et son état
habituel dès que quelque chose est nouveau ou plus grave. L'état complet reste
affiché dans les deux cas : seule l'alerte est supprimée, jamais les éléments
constatés :

```
OK: nothing new since the last run (WARNING state unchanged).
OpenCloud 7.2.3 on opencloud.example.com, rating: C, last scanned: 2026-01-14
Missing hardening: cspWithoutUnsafeInline (run with --debug for what each means and how to fix it)
Baseline: No new findings since 2026-01-14T09:00:00+00:00 (1 known issue(s) unchanged)
Suppressed by --warn-on-new: this run would otherwise be WARNING (WARNING: 1 hardening measure(s) missing, but no known vulnerabilities.)
```

Chaque comparaison énumère également les CVE ajoutées et corrigées, les
changements de durcissement et de contrôles supplémentaires, les variations de
note, de fin de vie et d'horizon de support, ainsi que les évolutions de la
version installée ou visée. `text` est le format par défaut, adapté aux
journaux. Pour un résumé d'étape GitHub Actions ou un commentaire de pull
request, choisissez Markdown :

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format markdown >> "$GITHUB_STEP_SUMMARY"
```

Utilisez `--diff-format slack` (ou `json`) pour du JSON Slack Block Kit.
Lorsqu'un webhook est configuré, chaque comparaison de référence y est incluse
sous `baseline_diff` ; le format Slack place en outre les blocs et la bannière
de couleur au niveau racine, pour les webhooks entrants :

```shell
check-opencloud-security -H opencloud.example.com \
  --baseline /var/lib/check_opencloud/baseline.json \
  --diff-format slack --webhook-url 'https://hooks.slack.com/services/<token>' \
  --webhook-on always
```


## Ce qui compte comme une régression {#what-counts-as-a-regression}


- un constat absent la fois précédente - un nouvel avis de sécurité, une mesure
  de durcissement qui a régressé, un contrôle supplémentaire qui s'est mis à
  échouer, une mise à jour nouvellement disponible ;
- une note inférieure à celle enregistrée ;
- **une version au-delà de sa fin de vie, toujours.** Elle ne reçoit plus aucun
  correctif de sécurité : elle empire donc chaque jour qu'elle passe en
  production et ne peut jamais être tolérée au titre de l'existant par une
  référence.

## Dérive de configuration {#configuration-drift}


Une référence mémorise aussi l'**empreinte de configuration** du scan : des
condensats regroupés décrivant la façon dont l'instance est configurée -
transport, en-têtes, partage, authentification, proxy - et rien de ce sur quoi
elle est configurée. Une exécution dont la note et les constats n'ont pas bougé
le signale tout de même lorsque le déploiement, lui, a changé :

```text
Baseline: No new findings since 2026-09-14T06:00:00Z, but the configuration changed (headers, proxy)
```

Le rapport nomme les groupes dont la configuration a changé. Le fichier de
référence, la sortie et le webhook contiennent des empreintes, sans les valeurs
de configuration correspondantes.

La dérive est signalée, jamais jugée : elle ne crée pas de constat, ne fait pas
régresser une exécution et ne modifie jamais le code de sortie. Une référence
écrite avant l'existence des empreintes ne peut pas détecter les changements
de configuration, faute d'empreintes à comparer. Elle ne signale donc aucun
changement ; cela ne prouve pas que la configuration est restée identique.

## Régressions de couverture {#coverage-regressions}


Une référence retient aussi les contrôles pour lesquels l'analyse **est
parvenue à une conclusion**. Lorsqu'un contrôle mesuré auparavant est
désormais `inconclusive` - il s'est exécuté sans pouvoir conclure, par exemple
parce qu'une requête DNS n'a pas répondu à temps -, l'exécution le signale,
même si la note n'a pas bougé :

```text
WARNING: 1 previously measured check(s) are now inconclusive; the rating is unchanged (Server is up to date. No known vulnerabilities.)
Coverage regressed (1): previously measured, now inconclusive: caaRecord (timeout) - the rating is unaffected.
```

Ce signal est séparé de la note de sécurité. La note, les
perfdata et les constats restent ceux que les mesures ont donnés ; seul l'état
d'alerte change, et uniquement de `OK` à `WARNING`. Une exécution déjà en
`WARNING` ou `CRITICAL` garde son message et reçoit la ligne en plus.
`--warn-on-new` ne la supprime pas : une analyse qui voit soudain moins est
une nouveauté.

- Seul `inconclusive` compte. Un contrôle devenu `not_checked` - désactivé
  par vous, ou devenu sans objet - n'est pas une régression de l'analyse.
- Un contrôle perdu reste « mesuré auparavant » jusqu'à ce qu'une exécution
  ultérieure le mesure de nouveau : l'avertissement dure autant que la lacune.
- Le webhook porte la liste dans `baseline_diff` sous `coverage_regressed` ;
  la comparaison de deux documents la signale comme `coverageRegressed`.
- Une référence plus ancienne sans couverture ne peut signaler aucune perte à
  la première exécution après la mise à jour ; elle enregistre alors ce qui a
  été mesuré.

## Contrôles qu'une seule exécution a effectués {#checks-only-one-run-made}

Un constat n'est nouveau que si l'exécution précédente aurait pu le signaler.
Quand l'analyseur gagne un contrôle - après une mise à jour, ou parce que vous
avez activé les contrôles supplémentaires -, un échec qu'il trouve maintenant
n'était *pas contrôlé* la fois précédente, pas réussi, et l'exécution le dit
ainsi :

```text
Baseline: Newly measured (1): hardening:basicAuthDisabled - the last run did not check these
Hardening: + basicAuthDisabled (not checked before)
```

Il alerte quand même, et `--warn-on-new` ne le supprime pas : personne n'a
encore été informé de cet échec. À l'inverse, un échec que l'exécution
actuelle ne contrôle plus apparaît comme `(not checked now)` et non comme
résolu.

- Ce qu'une exécution aurait pu signaler vient de son bloc de couverture,
  jamais d'une clé absente. Un rapport qui n'énumère pas ses contrôles est
  comparé comme avant : une vraie régression n'est jamais renommée.
- Le webhook porte les listes dans `baseline_diff` sous `newly_measured` et
  `no_longer_measured` ; la comparaison web sous `newlyMeasured` et
  `noLongerMeasured`.
- Une référence plus ancienne ne peut pas dire ce qu'elle a contrôlé : la
  première exécution après la mise à jour compare donc comme avant.

## Points à connaître {#points-worth-knowing}


- La première exécution n'a rien à quoi se comparer : elle signale normalement
  et devient la référence. Commencer à utiliser l'option ne masque jamais rien.
- Un fichier contient une entrée par hôte : une liste `--host` séparée par des
  virgules peut donc le partager.
- Les constats exclus par `--ignore-hardening`, ainsi que les mesures
  qu'OpenCloud fige, sont laissés de côté - exactement comme ils le sont dans la
  ligne d'alerte.
- `--warn-on-new` sans `--baseline` est refusé : sans endroit où mémoriser
  l'exécution précédente, l'option signalerait indéfiniment « rien de nouveau ».
- Une référence qui ne peut pas être écrite donne lieu à une ligne de sortie et
  à rien de plus. La tenue de registres ne décide jamais du verdict sur une
  instance.
- Le fichier est écrit de façon atomique, avec des permissions réservées au
  propriétaire. Placez-le à un endroit appartenant à l'utilisateur de
  supervision, p. ex. `/var/lib/check_opencloud/`.

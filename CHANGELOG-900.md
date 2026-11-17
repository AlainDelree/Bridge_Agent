# CHANGELOG — bridge_agent (issue #900, à fusionner)

## 17 novembre 2026 — issue #900

Mode interactif, étape 1 (étude #888) : pose le marqueur « interactif » et
l'exclut de la calibration automatique du TIMEOUT, sans rien changer au
lancement de CCL — les étapes suivantes de l'étude #888 branchent le
comportement réel.

Nouveau label `mode_interactif` (`watcher.LABEL_INTERACTIF`), orthogonal aux
labels de mode (`mode_write`/`mode_scratch` — une issue peut porter les
deux) : `_deduire_mode` reste inchangée, à trois valeurs. Provisionné
d'office sur tout dépôt (`labels_github.LABELS`, même patron que
`mode_scratch`/`sans-redacteur`, issue #816).

`watcher.est_interactif(labels, mode)` indique si le marqueur est
EFFECTIVEMENT retenu, avec les deux cas de repli décidés avec Alain, jamais
un rejet bloquant (même esprit que `sans-redacteur`/`sans-complexite`) :
- la lecture seule n'est jamais interactive (sa durée dépend de la tâche,
  pas d'Alain) ;
- le mode interactif ne concerne que le ThinkPad (CCL) — une issue
  destinée à Windows (label `for-windows`) reste automatique même marquée.

Dans les deux cas, un avertissement informatif est journalisé
(`_deduire_mode_et_logguer`), jamais un échec.

Dans le dépôt d'issues par fichier (`issues_inbox/`), nouveau champ
d'en-tête `| INTERACTIF | oui |` (`scripts/watcher_issues_inbox.py`) : pose
le label à la création, même principe que `MODE` — toute autre valeur ou
champ absent laisse l'issue automatique, sans rejet. Jamais réinséré dans
`construire_body` (pas un format supporté pour la création, comme `MODE`) ;
jamais corrigible par `RELANCE` (absent de la liste des champs corrigibles,
comme `MODE`).

Exclusion de la calibration du TIMEOUT (§19 de `BRIDGE_AGENT_DOC.md`) : une
issue interactive retenue n'appelle plus ni `enregistrer_duree` (historique
des durées) ni `maj_calibration_timeout` (EWMA par combinaison), ni à la
clôture réussie (`_finaliser_succes`) ni à chaque tentative expirée
(`_tracer_tentative_expiree`, qui reçoit désormais `labels` en paramètre).

Documentation : `BRIDGE_AGENT_DOC.md` §4 (label), §6 (champ `INTERACTIF`) et
§19 (exclusion de la calibration), + ligne « Dernière mise à jour ».

Tests ajoutés : `tests/test_mode_interactif_900.py` (19 scénarios) — label
provisionné, `est_interactif` (absent/retenu/deux replis), avertissement
journalisé par `_deduire_mode_et_logguer`, `construire_labels` (champ
`INTERACTIF` reconnu/non reconnu/absent, casse tolérée), exclusion de la
calibration dans `_finaliser_succes`/`_tracer_tentative_expiree` et
non-régression (comportement inchangé sans le label).

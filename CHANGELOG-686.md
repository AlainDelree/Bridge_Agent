## #686 — Forcer encoding="utf-8" sur les appels subprocess (git/gh) d'app/issues.py

Constaté le 28/09/2026, en conditions réelles sur `new_issue.py` tournant
nativement sur CCW (issue D) : les titres d'issues contenant des accents
s'affichaient corrompus (« RÃ©concilier », « dÃ©tecter »...), avec une
`UnicodeDecodeError: 'charmap' codec can't decode byte...` dans le log du
serveur. Cause : `app/issues.py` appelait `subprocess.run(..., text=True,
...)` sur `git`/`gh` sans préciser `encoding` — sous Windows ça retombe sur
l'encodage de la console (`cp1252` en français) alors que `git`/`gh`
produisent toujours de l'UTF-8, d'où la corruption dès qu'un accent
apparaît. Sous Linux ça marchait par hasard (UTF-8 système).

`watcher.py` avait déjà résolu ce même besoin ailleurs dans le dépôt
(`encoding="utf-8", errors="replace"` sur chacun de ses appels
`subprocess.run`). Même pattern appliqué ici aux 18 appels d'`app/issues.py`
(lignes 324, 391, 613, 625, 634, 655, 663, 670, 688, 704, 785, 891, 942,
1130, 1338, 1407, 1456, 1489). `app/notifications_poller.py` (lignes 165,
188) avait déjà été corrigé lors d'un commit antérieur — vérifié, rien à
faire dessus cette fois.

Vérification élargie au reste du dépôt (hors `watcher.py`, déjà correct,
et hors tests) : d'autres fichiers présentent le même défaut latent
(`text=True` sans `encoding=`) — `etat_rate_limit.py`, `app/interruption.py`,
`app/ccw.py`, `app/projet_ccw.py`, `backfill_historique.py`,
`nouveau_projet.py`, `regenerer_tableaux_projets.py`,
`scripts/watcher_issues_inbox.py`, `provisioning/windows/creer_vm_ccw.py`,
`provisioning/windows/lancer_provisioning.py` — hors du périmètre précis de
cette issue (qui ne visait que `app/issues.py` et
`app/notifications_poller.py`), donc non modifiés ; à traiter par une
future issue si souhaité.

Comportement Linux inchangé (UTF-8 explicite au lieu d'UTF-8 implicite,
même résultat) ; corrige la corruption d'accents sous Windows.

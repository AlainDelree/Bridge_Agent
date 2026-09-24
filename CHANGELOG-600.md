## 24 septembre 2026 — issue #600

Factorisation de l'enrobage « redémarrer le watcher s'il est éteint »,
dupliqué à 5 endroits avec des comportements divergents en cas d'échec
(diagnostic #579) — nouveau helper `redemarrer_si_eteint()` dans
`app/watchers.py`.

- `app/watchers.py` : nouvelle fonction `redemarrer_si_eteint(cfg, *,
  tracer=False)`, enrobage de `demarrer_watcher(cfg, forcer=False)`.
  Retourne `(demarre, pid, trace)` — `demarre` distingue désormais
  `True` (relancé), `False` (tournait déjà) et `None` (échec, repris
  d'`app/interruption.py`) ; `trace` est une chaîne prête à insérer dans
  un commentaire GitHub (non vide seulement si `tracer=True`). Un échec
  produit systématiquement un `log.warning` — jamais silencieux, à la
  différence de l'ancien `except: pass` d'`app/projet_ccw.py`.
- 5 sites remplacés par des appels à ce helper : `app/issues.py`
  (~l.356), `app/interruption.py` (~l.531), `app/projet_ccw.py` (~l.416),
  `scripts/watcher_issues_inbox.py` (~l.621 et ~l.864).
- Garde `for-linux` **non** internalisée dans le helper : dans
  `app/issues.py` et `app/interruption.py`, elle porte sur le routage de
  l'issue (labels for-linux/for-windows, #164), une décision propre à
  l'appelant — le helper ne reçoit qu'un `cfg` de projet, sans notion de
  labels. Les 3 autres sites ne l'avaient jamais eue (contexte déjà
  filtré sur bridge_agent) : rien à y ajouter.
- `tests/test_champ_redacteur_599.py` et `tests/test_champ_relance_516.py` :
  les scénarios qui substituaient `w.demarrer_watcher` (attribut copié
  au moment de l'import dans `watcher_issues_inbox.py`) substituent
  désormais `app.watchers.demarrer_watcher` directement, puisque
  `redemarrer_si_eteint()` résout `demarrer_watcher` par lookup dans son
  propre module (`app.watchers`) et non plus dans celui de l'appelant.
  Suite de tests (21 fichiers scénarios) toujours verte.

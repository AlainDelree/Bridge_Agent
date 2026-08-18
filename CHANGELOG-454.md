## 18 août 2026 — issue #454

FEATURE — Bandeau d'avertissement d'échéance de l'éval Windows CCW dans
`new_issue.py`.
- `app/eval_windows.py` (nouveau) : `etat_eval_windows()` lit
  `provisioning/windows/eval-expiration.json`, recalcule la date
  d'expiration (`date_installation` + `eval_jours`, même logique que
  `provisioning/windows/verifier_expiration_ccw.py`) et retourne `None`
  si le fichier est absent/invalide ou si l'échéance est encore lointaine
  (> 14 jours), sinon un état `{jours_restants, date_expiration, niveau,
  message}` avec `niveau` = `orange` (≤ 14 j) ou `rouge` (≤ 5 j ou
  échéance dépassée).
- `app/vues.py` : la route `index()` passe `eval_windows=etat_eval_windows()`
  au gabarit.
- `templates/index.html` : bandeau `{% if eval_windows %}` inséré juste
  après l'en-tête, en dehors des panneaux d'onglets → visible sur tous
  les onglets sans dupliquer le HTML.
- `static/css/style.css` : styles `.bandeau-eval-windows.orange` (fond
  `#fff3cd`) et `.rouge` (fond `#f8d7da`), cohérents avec les couleurs
  d'alerte déjà utilisées ailleurs dans l'interface.
- Vérifié par test manuel (`create_app()` + `test_client`) avec état
  forcé orange/rouge/absent : bandeau présent avec le bon texte et la
  bonne classe, absent quand l'échéance est lointaine (cas réel actuel :
  89 jours restants au 18/08/2026) ou quand le fichier est absent/invalide.

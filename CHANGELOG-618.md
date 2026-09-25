## 25 septembre 2026 — issue #618

Diagnostic #579 (bas niveau, point 2) : extraction de `TEMPLATE_LOGIN`
(`app/auth.py`) vers `templates/login.html`, sans changement fonctionnel.

- La chaîne Python `TEMPLATE_LOGIN` (~42 lignes HTML+CSS+Jinja inline)
  est déplacée telle quelle vers `templates/login.html`, cohérent avec
  `templates/index.html` (déjà un fichier Jinja séparé).
- `app/auth.py` : les trois appels `render_template_string(TEMPLATE_LOGIN,
  ...)` (`login()`, `login_post()` ×2) remplacés par
  `render_template("login.html", ...)`. Import Flask allégé
  (`render_template_string` → `render_template`). Constante
  `TEMPLATE_LOGIN` et docstring module mis à jour en conséquence.
- Vérification : `py_compile` OK, suite de tests existante verte
  (14 passed), rendu réel testé via `app.test_client()` — page login
  affichée (200, contenu attendu), variables Jinja `erreur` et `bloque`
  bien transmises (message d'erreur, `disabled` sur input/bouton).

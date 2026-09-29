## #687 — Favicon bleu distinct quand `new_issue.py` tourne nativement sur Windows

Trois interfaces web coexistent maintenant dans le navigateur d'Alain :
Bridge_Agent Linux (rouge, existant), Relecture_Bridge (vert) et désormais
Bridge_Agent tournant nativement sur Windows (issue D) — sans distinction
visuelle possible entre les deux premières instances Bridge_Agent puisque
le favicon SVG était un fichier unique et statique, indépendant de l'OS.

- **`static/img/favicon-windows.svg`** (nouveau) : même forme de pont
  stylisé que `favicon.svg`, couleur bleu Windows `#0078D4` à la place du
  rouge `#C0645C`. `favicon.svg` (Linux) reste inchangé.
- **`app/statique.py`** : nouvelle fonction `favicon_svg()` — retourne
  `img/favicon-windows.svg` si `platform.system() == "Windows"`, sinon
  `img/favicon.svg` ; exposée comme globale Jinja (même mécanisme que
  `url_statique`/`importmap_socle`, avec cache-busting `?v=<mtime>` via
  `url_statique()`).
- **`templates/index.html`** : le `<link rel="icon" type="image/svg+xml">`
  utilise désormais `{{ url_statique(favicon_svg()) }}` au lieu d'un chemin
  statique en dur. Le `<link>` `favicon.ico` (type image/x-icon) n'est pas
  concerné — non demandé par l'issue, les navigateurs modernes priorisent
  le SVG pour l'onglet.

Vérifié par rendu Jinja direct (`render_template_string`) avec
`platform.system` mocké sur "Windows" et non mocké (Linux) : URL générée
correcte dans les deux cas.

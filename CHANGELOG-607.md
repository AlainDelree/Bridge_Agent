## 24 septembre 2026 — issue #607

Indicateur compact du rate limit GitHub GraphQL dans le bandeau
supérieur de `new_issue.py`, toujours visible quel que soit l'onglet
actif (entre le titre « Bridge Agent » et le compteur « N projet(s)
disponible(s) ») — répond au cas concret du 24/09 (13 watchers
démarrés simultanément) où l'onglet Résultats affichait « Aucune
issue à afficher » sans explication pendant que le quota était épuisé.

- **`app/rate_limit.py`** (nouveau) : route `GET /rate-limit`, exécute
  `gh api rate_limit --jq '.resources.graphql'` côté serveur et
  renvoie `{ok, used, limit, remaining, reset}` — ou `{ok: false,
  erreur}` en cas d'échec (gh absent, timeout, rate limit REST atteint)
  sans jamais lever d'erreur HTTP. Cet appel ne consomme NI le quota
  `core` NI le quota `graphql` (vérifié empiriquement, issue #263,
  `scripts/mesurer_api.py`) : son polling ne peut donc pas lui-même
  épuiser le quota qu'il surveille.
- **`app/__init__.py`** : enregistrement de la route (`login_requis`,
  comme `/watchers`/`/statut`).
- **`templates/index.html`** : `<span id="rate-limit-widget">` inséré
  entre `<h1>` et `.statut`.
- **`static/js/app.js`** : `rafraichirRateLimit()`, polling global
  indépendant de l'onglet actif (`setInterval`, 30s — même cadence que
  le monitoring infrastructure de la sidebar Résultats), format
  `⚡ 132 / 5000 · reset 20:15` (heure de reset convertie en local côté
  navigateur via `toLocaleTimeString`). État dégradé `⚡ ? / 5000` en
  gris si l'appel échoue, sans faire disparaître le widget.
- **`static/css/style.css`** : classes `.rate-limit` + `.rl-vert` /
  `.rl-orange` / `.rl-rouge` / `.rl-gris` (mêmes teintes que les
  badges de temps restant existants). Seuils de couleur : vert < 70%
  utilisé, orange 70-90%, rouge > 90% (risque immédiat). Le
  `margin-left:auto` qui poussait `.statut` à droite est déplacé sur
  `.rate-limit` : le widget, le compteur de projets et les boutons
  d'en-tête restent groupés à droite, comme avant.

Vérification : valeurs de `/rate-limit` comparées à `gh api rate_limit
--jq '.resources.graphql'` en terminal (identiques) ; seuils de
couleur testés à 69/70/90/91% ; état d'erreur simulé (PATH sans `gh`)
→ `{ok: false, erreur: "gh introuvable dans le PATH."}`, HTTP 200 (pas
de plantage) ; `py_compile` sur tous les modules Python touchés +
suite de tests existante (`pytest tests/`, 14 passed) toujours verts.

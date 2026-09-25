## 25 septembre 2026 — issue #625

Refonte de l'interface web, **étape 1/n : socle**. Architecture retenue par
Alain : modules JavaScript natifs (`<script type="module">`), **sans étape de
build**, briques partagées + modules par fonctionnalité (à venir). Cette étape
pose les fondations pour que les étapes suivantes tournent **en parallèle** dans
des worktrees distincts. **Contrainte absolue tenue : aucun changement visible
pour l'utilisateur** — corps de `index.html` vérifié byte-identique après rendu
Flask (hors entête/scripts), CSS reconcaténé byte-identique à l'ancien
`style.css`.

### 1. Briques partagées — `static/js/socle/`

Nouveau sous-dossier de modules ES, **inertes à cette étape** (chargés, testés,
mais ne remplacent rien) :

- `store.js` — source de vérité unique : tranches issues (indexées par
  `projet#numero`), sélection, filtres, projets, watchers, issues_inbox, son,
  rate-limit ; `get`/`set`/`maj`/`abonner`/`abonnerCle` + aides issues.
  `creerStore()` fabrique générique testable.
- `api.js` — accès unique aux routes Flask, vérifie **systématiquement**
  `response.ok`, lève `ErreurApi` et remonte via toasts (plus d'erreur avalée).
- `sse.js` — canaux `/stream` et `/events` centralisés, **NON connectés** (pas de
  double connexion tant que l'ancien code gère les siennes).
- `toasts.js` — notifications non bloquantes (jamais de « OK » à cliquer) + LA
  seule modale, réservée aux confirmations destructives. Styles auto-injectés.
- `dom.js` — utilitaires (`$`, `$$`, `creerElement`, `echapperHtml`) + registre
  de délégation d'événements (`surAction`) destiné à remplacer les handlers
  inline.
- `persistance.js` — localStorage restreint aux préférences d'interface.
- `index.js` — point d'entrée module ; `pont.js` — mécanisme de transition.

### 2. Coexistence avec l'ancien code

`app.js` reste chargé comme **script CLASSIQUE** (ses ~233 fonctions restent
globales pour les >70 gestionnaires inline). Le module d'entrée est chargé **à
côté** (différé ⇒ après app.js). `pont.js` est l'unique point de contact
(`window.Bridge` pour ancien→socle, `appelerAncien()` pour socle→ancien), conçu
pour être **retiré entièrement à la dernière étape**. Ordre de chargement
préservé (variables Jinja disponibles pour les deux mondes).

### 3. Découpage des fichiers

- `templates/index.html` → squelette + `templates/fragments/` (un fragment par
  onglet, panneau latéral, bandeaux, entête, chaque modale, scripts).
- `static/css/style.css` → 6 feuilles par zone (`base`, `composants`,
  `resultats`, `modales`, `recherche-interruption`, `inbox`), chargées dans
  l'ordre qui **préserve exactement la cascade** (reconcaténation byte-identique
  vérifiée). `app.js` reste d'un seul tenant (vidé par les étapes suivantes).

### 4. Fichiers servis (cache-busting)

Nouveau `app/statique.py` : `url_statique()` (ajoute `?v=<mtime>` aux CSS/JS) et
`importmap_socle()` (import map versionnant les imports relatifs entre modules ES,
sans build). Vérifié : modules servis en `text/javascript` et CSS en `text/css`,
statut 200, en local / `--lan` / `--externe`, **y compris session expirée** (les
statiques ne sont pas derrière `login_requis`).

### 5. Filet de sécurité

- Tests de logique pure avec le module intégré de Node (`node:test`, aucune
  dépendance) : `store`, `persistance`, `dom` — **20 tests, tous verts**.
  Lancement : `node --test static/js/socle/tests/` (cf. README des tests).
- `VERIFICATIONS_MANUELLES.md` (racine) : liste de non-régression à rejouer par
  Alain après chaque étape (tous onglets, panneau latéral, modes `--lan`/externe).

### 6. Documentation

- `ARCHITECTURE.md` §6 : carte de migration complète (arborescence, rôle de
  chaque brique, mécanisme de transition, correspondance zones↔fichiers,
  versionnage, procédure type pour sortir une fonctionnalité de l'ancien code).
- `CONTEXTE.md` mis à jour et ramené sous le plafond de 4000 caractères.

Fichiers : +`static/js/socle/*` (8 modules + package.json), +`static/js/socle/tests/*`,
+`templates/fragments/*` (18 fragments), +`static/css/{base,composants,resultats,
modales,recherche-interruption,inbox}.css`, +`app/statique.py`,
+`VERIFICATIONS_MANUELLES.md` ; ~`templates/index.html`, ~`app/__init__.py`,
~`ARCHITECTURE.md`, ~`CONTEXTE.md` ; −`static/css/style.css` (découpé).

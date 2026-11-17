# CONTEXTE — bridge_agent

Injecté en tête de chaque prompt CCL (`FICHIER_CONTEXTE`, plafond 4000 car.).
Référence complète : `BRIDGE_AGENT_DOC.md` (+ `ARCHITECTURE.md`).

## Règles
- Bridge inter-agents : Claude Chat (CC) délègue des tâches à Claude Code
  Linux (CCL) — et Windows (CCW) — via des GitHub Issues. Flux : CC crée une
  issue → `watcher.py` la détecte → l'agent exécute → poste le résultat en
  commentaire → ferme l'issue → notification. Bridge_Agent se développe
  lui-même par ses propres issues (dogfooding).
- Maintenance de ce fichier : si ta tâche modifie une règle, une
  convention, l'architecture ou une dépendance, mets à jour ce CONTEXTE.md
  dans le même commit, en 1 à 3 lignes (jamais un récit — il va dans
  `CHANGELOG-<N>.md`). S'il dépasse déjà 4000 caractères, ne le grossis pas :
  déplace plutôt le détail dans un fichier `docs/contexte/<domaine>.md`,
  référencé dans l'index ci-dessous.

## Architecture
- **`watcher.py`** — watcher générique unique (`--config configs/<nom>.conf`),
  partagé par tous les projets et les deux plateformes (un watcher + un log
  par projet). En début de cycle : `git pull --ff-only` du clone de travail
  (`REP_TRAVAIL`), sinon poursuit sur le code local sans rien écraser.
- **`new_issue.py`** — point d'entrée mince de l'interface web Flask (port
  5100), tourne en permanence sur le ThinkPad. `--externe` → tunnel
  cloudflared (`app/tunnel.py`, configuré par l'utilisateur) + login.
- **`app/`** — package Flask. `create_app()` (`__init__.py`) : état partagé
  dans `app.config`, routes via `add_url_rule`. Modules : `auth`, `projets`
  (`.conf`), `watchers`, `issues`, `journal`, `cycle_vie` (heartbeat/SSE),
  `ccw` (pilotage Windows), `notifications_poller` (bip/notify-send/ntfy),
  `tunnel`, `etat`, `vues`, `statique` (cache-busting).
- **`templates/`** — `index.html` + `fragments/` (un par onglet/panneau/
  modale, Jinja2). **`static/`** — `css/` par zone (cascade), `js/app.js`
  (hérité, classique) + `js/socle/` (modules ES sans build, refonte
  #625→#632 — détail : `ARCHITECTURE.md §6`).
- **`configs/`** (gitignoré, un `.conf`/projet) ; **`provisioning/windows/`**
  + **`systemd/`** (`watcher@.service`) pour le déploiement ; **`scripts/`**
  (bip).

## Conventions
- **Français** pour tout ce qui est nommé librement (identifiants,
  commentaires, clés de config) ; anglais gardé pour les contrats existants
  (labels GitHub, drapeaux CLI, mots-clés Python).
- **Mode par défaut : lecture seule.** N'armer l'écriture que si la tâche le
  demande explicitement. **CCL ne pousse JAMAIS** : il committe
  `backup + fix` en local, Alain vérifie puis pousse lui-même.
- Issues : `#Titre:` en première ligne du corps.
- **Scripts `.ps1` : BOM UTF-8 obligatoire** (octets `EF BB BF`) dès la
  création, sinon PowerShell 5.1 plante sur les accents.

## Index des fichiers de domaine
Entrées pointant vers leur section (la plupart vivent encore dans les
documents de référence ci-dessous, voir issue #890) :
- `docs/contexte/mode_interactif.md` — à lire avant de toucher au mode
  interactif (session tmux, surveillance non bloquante, issue #901).
- `ARCHITECTURE.md §6` — à lire avant de toucher au socle web
  (`static/js/socle/`).
- `BRIDGE_AGENT_DOC.md §19` — à lire avant de toucher à la calibration du
  `TIMEOUT`.
- `BRIDGE_AGENT_DOC.md §12.1` — à lire avant de toucher aux consignes à
  trois couches (`consignes/`).
- `BRIDGE_AGENT_DOC.md §18` — à lire avant de toucher aux pièces jointes
  d'issue.
- `BRIDGE_AGENT_DOC.md §4.1` — à lire avant de toucher aux notifications.
- `BRIDGE_AGENT_DOC.md §16` — à lire avant de toucher à l'agent Windows /
  l'onglet CCW.
- `BRIDGE_AGENT_DOC.md §3.16` — à lire avant de toucher au champ `ATTENTE`
  d'`issues_inbox/`.

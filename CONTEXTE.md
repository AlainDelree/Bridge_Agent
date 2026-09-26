# CONTEXTE — bridge_agent

Injecté en tête de chaque prompt CCL (`FICHIER_CONTEXTE`, plafond 4000 car.).
Référence complète : `BRIDGE_AGENT_DOC.md` (+ `ARCHITECTURE.md`).

## Objectif
Bridge inter-agents : Claude Chat (CC) délègue des tâches à Claude Code
Linux (CCL) — et Windows (CCW) — via des GitHub Issues. Flux : CC crée une
issue → `watcher.py` la détecte → l'agent exécute → poste le résultat en
commentaire → ferme l'issue → notification. Bridge_Agent se développe
lui-même par ses propres issues (dogfooding).

## Architecture
- **`watcher.py`** — watcher générique unique (`--config configs/<nom>.conf`),
  partagé par tous les projets et les deux plateformes (un watcher + un log
  par projet). En début de cycle : `git pull --ff-only` du clone de travail
  (`REP_TRAVAIL`), sinon poursuit sur le code local sans rien écraser.
- **`new_issue.py`** — point d'entrée mince de l'interface web Flask (port
  5100), tourne en permanence sur le ThinkPad. `--externe` → tunnel
  cloudflared (`app/tunnel.py`, https://bridge.frederiqueferette.be) + login.
- **`app/`** — package Flask. `create_app()` (`__init__.py`) : état partagé
  dans `app.config`, routes via `add_url_rule`. Modules : `auth`, `projets`
  (`.conf`), `watchers`, `issues`, `journal`, `cycle_vie` (heartbeat/SSE),
  `ccw` (pilotage Windows), `notifications_poller` (bip/notify-send/ntfy),
  `tunnel`, `etat`, `vues`, `statique` (cache-busting).
- **`templates/`** — `index.html` + `fragments/` (un par onglet/panneau/
  modale, Jinja2). **`static/`** — `css/` par zone (cascade), `js/app.js`
  (hérité, classique) + `js/socle/` (modules ES sans build, refonte
  #625→#632 — détail ci-dessous).
- **`configs/`** (gitignoré, un `.conf`/projet) ; **`provisioning/windows/`**
  + **`systemd/`** (`watcher@.service`) pour le déploiement ; **`scripts/`**
  (bip).

## Conventions de code (§11 du DOC)
- **Français** pour tout ce qui est nommé librement (identifiants,
  commentaires, clés de config) ; anglais gardé pour les contrats existants
  (labels GitHub, drapeaux CLI, mots-clés Python).
- **Mode par défaut : lecture seule.** N'armer l'écriture que si la tâche le
  demande explicitement. **CCL ne pousse JAMAIS** : il committe
  `backup + fix` en local, Alain vérifie puis pousse lui-même.
- Issues : `#Titre:` en première ligne du corps.
- **Scripts `.ps1` : BOM UTF-8 obligatoire** (octets `EF BB BF`) dès la
  création, sinon PowerShell 5.1 plante sur les accents.

## État d'avancement (récent, cf. changelog en bas du DOC)
- #625→#641 (refonte web) : socle de modules ES dans `static/js/socle/`
  (store/api/sse/toasts/dom/persistance/pont), et modules par fonctionnalité
  sortis d'app.js (onglets, resultats, panneau latéral, resultats_coches —
  case « traité/lu » serveur #636, actions_ligne — étape 6 #641 : badges
  ⚠️/✏️ d'une ligne OUVERTE cliquables + son par issue déplacé du panneau à
  la ligne) communiquant entre eux par le store. Détail : `ARCHITECTURE.md §6`.
- #221 (calibration TIMEOUT, 2/3) : `watcher.py` journalise `TIMEOUT_suggéré`
  à la clôture (EWMA par projet+TYPE+mode dans `logs/etat_timeout.json` +
  `logs/etat_ambiance.json` pour F_reseau/F_local) — n'affecte pas encore le
  TIMEOUT appliqué (en-tête seul décisif).
- §12.1 (#209/#211) : `consignes/` (globales/type/projet) injecté dans le
  PROMPT CCL par `watcher.py` (point de passage unique) ; `globales.md`
  obligatoire, le reste facultatif.
- §18 (#191/#192) : pièces jointes image → `issue-attachments/` + URL raw.
- §17 (#187) : notifications centralisées via `new_issue.py` (tous projets,
  CCW).
- §16 (#174…) : onglet « CCW » — pilotage du PC Windows physique depuis
  Linux.

## Maintenance de ce fichier
Si ta tâche modifie l'architecture, les dépendances, les conventions ou
l'état d'avancement majeur, mets à jour ce CONTEXTE.md dans le même commit
(≤ 4000 car.).

# CONTEXTE — bridge_agent

Injecté en tête de chaque prompt CCL (`FICHIER_CONTEXTE`, plafond 4000 car.).
Référence complète : `BRIDGE_AGENT_DOC.md` (+ `ARCHITECTURE.md`).

## Objectif
Bridge inter-agents : Claude Chat (CC) délègue des tâches à Claude Code
Linux (CCL) — et à Claude Code Windows (CCW) — via des GitHub Issues.
Flux : CC crée une issue → `watcher.py` la détecte → l'agent exécute →
poste le résultat en commentaire → ferme l'issue → notification.
Bridge_Agent se développe lui-même par ses propres issues (dogfooding).

## Architecture
- **`watcher.py`** — watcher générique unique (`--config configs/<nom>.conf`),
  partagé par TOUS les projets et les deux plateformes (CCL/CCW). Un watcher +
  un log par projet. En début de cycle : `git pull --ff-only` du clone de travail
  (`REP_TRAVAIL`), sinon poursuit sur le code local sans rien écraser.
- **`new_issue.py`** — point d'entrée mince de l'interface web Flask (port
  5100). Tourne en permanence sur le ThinkPad. `--externe` → tunnel
  cloudflared (`app/tunnel.py`, https://bridge.frederiqueferette.be) + login.
- **`app/`** — package Flask. `create_app()` (`__init__.py`) : état partagé dans
  `app.config`, routes via `add_url_rule`. Modules : `auth`, `projets` (`.conf`),
  `watchers`, `issues`, `journal`, `cycle_vie` (heartbeat/SSE), `ccw` (pilotage
  Windows), `notifications_poller` (bip/notify-send/ntfy), `tunnel`, `etat`,
  `vues`, `statique` (versionnage cache-busting des statiques).
- **`templates/`** — `index.html` (squelette) + `fragments/` (un par onglet /
  panneau / modale, Jinja2). **`static/`** — `css/` découpé par zone (ordre de
  chargement = cascade), `js/app.js` (hérité, script classique) + `js/socle/`
  (modules ES : store/api/sse/toasts/dom/persistance ; refonte issue #625).
- **`configs/`** (gitignoré) — un `.conf` par projet. **`provisioning/windows/`**
  + **`systemd/`** (`watcher@.service`) — déploiement. **`scripts/`** (bip).

## Conventions de code (§11 du DOC)
- **Français** pour tout ce qui est nommé librement (identifiants, commentaires,
  clés de config) ; anglais gardé pour les contrats existants (labels GitHub,
  drapeaux CLI, mots-clés Python).
- **Mode par défaut : lecture seule.** N'armer l'écriture que si la tâche le
  demande explicitement. **CCL ne pousse JAMAIS** : il committe `backup + fix`
  en local, Alain vérifie puis pousse lui-même.
- Issues : `#Titre:` en première ligne du corps.
- **Scripts `.ps1` : BOM UTF-8 obligatoire** (octets `EF BB BF`) dès la
  création, sinon PowerShell 5.1 plante sur les accents.

## État d'avancement (récent, cf. changelog en bas du DOC)
- #625 (refonte interface web, étape 1/n) : socle de modules ES natifs sans build
  dans `static/js/socle/` (store/api/sse/toasts/dom/persistance + pont de
  transition), `index.html` et `style.css` découpés en fragments/feuilles,
  versionnage `?v=<mtime>` des statiques + import map. INERTE : ne remplace rien
  encore (app.js reste seul aux commandes). Détail : `ARCHITECTURE.md`.
- #221 (calibration TIMEOUT, 2/3) : `watcher.py` maintient `logs/etat_timeout.json`
  (EWMA par projet+TYPE+mode) et `logs/etat_ambiance.json` (F_reseau/F_local) ;
  `TIMEOUT_suggéré` journalisé à chaque clôture — n'affecte PAS encore le TIMEOUT
  appliqué (en-tête seul décisif ; exposition à venir).
- §12.1 (#209/#211) : dossier `consignes/` (globales/type/projet) injecté dans le
  PROMPT CCL par `watcher.py`, point de passage UNIQUE de tous les chemins de
  création. `globales.md` non-optionnel, `type_*`/`projet_*` facultatifs.
- §18 (#191/#192) : pièces jointes image → `issue-attachments/` + URL raw.
- §17 (#187) : notifications centralisées via `new_issue.py` (tous projets, CCW inclus).
- §16 (#174…) : onglet « CCW » — pilotage du PC Windows physique depuis Linux.

## Maintenance de ce fichier
Si ta tâche modifie l'architecture, les dépendances, les conventions ou l'état
d'avancement majeur, mets à jour ce CONTEXTE.md dans le même commit (≤ 4000 car.).

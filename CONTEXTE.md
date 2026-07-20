# CONTEXTE — bridge_agent

Ce fichier est injecté automatiquement en tête de chaque prompt CCL
(via `FICHIER_CONTEXTE`, plafonné à 4000 caractères). Il résume le projet.
Référence complète : `BRIDGE_AGENT_DOC.md` (+ `ARCHITECTURE.md`).

## Objectif
Bridge inter-agents : Claude Chat (CC) délègue des tâches à Claude Code
Linux (CCL) — et à Claude Code Windows (CCW) — via des GitHub Issues.
Flux : CC crée une issue → `watcher.py` la détecte → l'agent exécute →
poste le résultat en commentaire → ferme l'issue → notification.
Bridge_Agent se développe lui-même par ses propres issues (dogfooding).

## Architecture
- **`watcher.py`** — watcher générique unique (`--config configs/<nom>.conf`),
  partagé par TOUS les projets et les deux plateformes (CCL/CCW). Un watcher
  et un log (`logs/watcher-<nom>.log`) par projet. En début de chaque cycle :
  `git pull --ff-only` du clone de travail (`REP_TRAVAIL`) — fast-forward si
  possible, sinon poursuit sur le code local sans rien écraser.
- **`new_issue.py`** — point d'entrée mince de l'interface web Flask (port
  5100). Tourne en permanence sur le ThinkPad. `--externe` → tunnel
  cloudflared (`app/tunnel.py`, https://bridge.frederiqueferette.be) + login.
- **`app/`** — package Flask. `create_app()` (`__init__.py`) : état partagé
  dans `app.config`, routes via `add_url_rule`. Modules : `auth`, `projets`
  (config `.conf`), `watchers` (start/stop/état), `issues` (création/suivi,
  pièces jointes image), `journal`, `cycle_vie` (heartbeat/SSE), `ccw`
  (onglet pilotage VM Windows), `notifications_poller` (thread démon
  détectant les transitions d'issues pour bip/notify-send/ntfy), `tunnel`,
  `etat`, `vues`.
- **`templates/`** (`index.html`, Jinja2), **`static/`** (css/js/img).
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
- §18 (#191) : pièces jointes image PNG/JPEG dans les issues → commit+push dans
  `issue-attachments/` + URL raw insérée. #192 : support GIF + affichage des
  formats/limite dans l'UI.
- §17 (#187) : notifications centralisées — `new_issue.py` détecte lui-même les
  transitions d'issues (tous projets, y compris CCW) et notifie localement.
- §16 (#174…) : onglet « CCW » — pilotage complet de la VM Windows depuis Linux.
- #186/#185 : `git pull --ff-only` automatique en début de cycle du watcher.

## Maintenance de ce fichier
Si la tâche que tu exécutes modifie l'architecture, les dépendances, les
conventions de code, ou l'état d'avancement majeur de ce projet, mets à
jour ce CONTEXTE.md en conséquence, dans le même commit.

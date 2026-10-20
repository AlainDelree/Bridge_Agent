# Déploiement de Mistral Vibe comme agent d'exécution (issue #760)

Ce dossier verse dans le dépôt Bridge_Agent ce qui, côté Mistral Vibe,
vivrait sinon uniquement dans `~/.vibe/` (dossier personnel de
l'utilisateur) : invisible, non sauvegardé par git, non relu en revue de
code. Même esprit que `consignes/` ou `provisioning/windows/` pour la
plateforme Windows.

**Cette issue n'a fait basculer aucun projet sur Vibe.** Elle rend
seulement l'agent disponible (`AGENT = vibe` dans un `configs/<projet>.conf`,
voir `watcher.py` / `AGENTS_CONNUS`). Le basculement effectif d'un projet
reste une action manuelle, décrite en bas de ce document.

## 1. Profil d'agent en écriture (`agents/bridge_ecriture.toml`)

Vibe n'a pas d'option en ligne de commande équivalente à
`--dangerously-skip-permissions` de Claude Code (constaté par essai manuel) :
l'écriture se débloque outil par outil via un profil décrit en TOML, désigné
ensuite par son nom (`--agent bridge_ecriture`). `watcher.py` construit déjà
cette commande pour le mode écriture (voir
`AGENTS_CONNUS["vibe"]["construire_cmd"]`) — encore faut-il que le fichier
existe réellement à l'emplacement que Vibe va chercher.

Le périmètre (`REP_TRAVAIL` du projet, ou le worktree en cours) est transmis
explicitement via `--workdir` (issue #761) — Vibe refuse d'écrire hors de ce
répertoire, constaté par essai manuel.

**Mode lecture active (`mode_scratch`) indisponible pour cet agent** (issue
#761) : ce mode a besoin d'écrire dans un dossier scratch situé HORS de
`--workdir`, mais la seule option qui étendrait ce périmètre (`--add-dir`) ne
distingue pas lecture et écriture — elle ouvrirait le projet à l'écriture
tout autant que le scratch (confirmé en lisant `vibe.core.workspace.Workspace`,
dont `authorized_roots` est décrit comme « the whole of the write boundary »).
Une issue en lecture active confiée à un projet basculé sur Vibe échoue donc
proprement (`ModeAgentIndisponible`, voir `_construire_cmd_vibe`) plutôt que
de donner une fausse impression de confinement — à revoir si une future
version de Vibe expose une telle distinction.

**Déploiement** (une fois, sur chaque machine qui exécutera Vibe) :

```bash
mkdir -p ~/.vibe/agents
cp provisioning/vibe/agents/bridge_ecriture.toml ~/.vibe/agents/bridge_ecriture.toml
```

Toute modification future des permissions de ce profil se fait dans
`provisioning/vibe/agents/bridge_ecriture.toml` (versionné), puis se
redéploie avec la même commande — jamais l'inverse (éditer directement
`~/.vibe/agents/bridge_ecriture.toml` ferait diverger silencieusement la
copie réellement utilisée de celle du dépôt).

## 2. Dossiers de confiance (`trusted_folders.toml`)

Vibe tient une liste de dossiers de travail approuvés
(`~/.vibe/trusted_folders.toml`) et peut demander une confirmation
interactive pour un dossier inconnu — ce qui bloquerait une session
automatisée lancée par `watcher.py` (aucune interaction possible). Le
répertoire de travail d'un projet (`REP_TRAVAIL` du `.conf`, et chaque
worktree créé sous celui-ci pour la parallélisation `mode_write`, issue
#337) doit donc être pré-approuvé **avant** la première tâche confiée à Vibe
sur ce projet.

**Déploiement**, pour chaque projet basculé sur Vibe : ajouter son
`REP_TRAVAIL` (chemin absolu) à la liste `trusted` de
`~/.vibe/trusted_folders.toml` :

```toml
trusted = [
    "/chemin/absolu/vers/REP_TRAVAIL/du/projet",
]
untrusted = []
```

Un worktree git de ce projet (`git worktree add`, sous le même répertoire
parent que `REP_TRAVAIL`) hérite normalement de la confiance accordée au
dossier parent — à vérifier lors de la première bascule réelle d'un projet
utilisant la parallélisation `mode_write` sur Vibe ; si ce n'est pas le cas,
ajouter aussi le chemin du worktree.

## 3. Authentification

Clé API Mistral, par variable d'environnement `MISTRAL_API_KEY` ou fichier
`~/.vibe/.env` (`MISTRAL_API_KEY=...`) — lu par Vibe lui-même au démarrage.
Pas de session qui expire d'elle-même (à la différence du token OAuth de
Claude Code) : `watcher.py` vérifie seulement, sans appel réseau, que cette
clé est présente et d'une forme plausible avant de lancer une tâche (voir
`verifier_preflight_cle_api_vibe` dans `watcher.py`) — ce n'est qu'au moment
d'un appel réel qu'une clé révoquée ou un quota/crédit épuisé se révèlent
(voir §5 de l'issue #760 : détection en cours d'exécution, qui arrête alors
le traitement immédiatement).

## 4. Modèle actif (`~/.vibe/config.toml`, issue #766)

Le modèle que Vibe utilise (`active_model` + bloc `[[models]]` déclarant
chaque alias) est géré depuis l'onglet **Agent Vibe** de l'interface web
(`app/vibe_modele.py`) — réglage de COMPTE, pas de projet : le choix
s'applique à tous les projets basculés sur cet agent sur cette machine,
jamais dans un `configs/<projet>.conf`.

Vibe réécrit ce fichier à chaque démarrage, réconcilié avec le compte : toute
écriture depuis l'interface préserve ce qu'elle ne gère pas (écriture
chirurgicale au niveau ligne, pas de régénération du fichier), et une
sauvegarde datée est écrite avant chaque modification
(`~/.vibe/bridge_sauvegardes/`). Un alias identique à un modèle intégré
connu de Vibe (`mistral-medium-3.5` au minimum — la liste complète dépend du
compte et n'est pas énumérable sans appel réseau) est signalé avant tout
ajout : Vibe l'écraserait silencieusement à son prochain démarrage.

## 5. Basculer un projet existant sur Vibe

1. Déployer le profil d'écriture (§1) et pré-approuver le `REP_TRAVAIL` du
   projet, et de chaque worktree déjà existant le cas échéant (§2), sur la
   machine qui exécute le watcher de ce projet.
2. Vérifier que `vibe` est installé et que la clé API Mistral est
   accessible (`MISTRAL_API_KEY` ou `~/.vibe/.env`) sur cette même machine.
3. Ajouter `AGENT = vibe` dans `configs/<projet>.conf` — **réservé à Alain**,
   CCL/CCW ne modifient jamais ce fichier (garde-fou existant, inchangé).
4. Relancer le watcher du projet pour qu'il recharge sa configuration.
5. Vérifier en conditions réelles sur une tâche simple avant de confier une
   tâche conséquente — le mapping des trois modes (lecture seule → profil
   `plan`, écriture et lecture active → profil `bridge_ecriture`) et les
   signatures d'erreur bloquante côté Vibe sont des choix best-effort, non
   vérifiés en conditions réelles pendant l'issue #760 (consigne explicite :
   ne pas lancer de session Vibe réelle, facturée).

## 6. Interface CLI figée (`VIBE_CLI=python`, issue #779)

Incident chesscoach #126 : l'issue a échoué en 3,4 secondes, pour toute
sortie un message de Vibe annonçant qu'une nouvelle interface (TUI Rust,
encore en préversion) était utilisée par défaut et indiquant comment revenir
à l'ancienne. Vérifié par lecture du code source installé (`vibe.cli.
launcher`, module minimal choisi par le script `vibe`) : Vibe choisit entre
deux implémentations CLI (Python, historique, et Rust, nouvelle) via la
variable d'environnement `VIBE_CLI` — `python` ou `rust` la fixent
explicitement ; **absente, elle suit une bascule distante** (cache
GrowthBook `vibe_cli_rust_tui_rollout`, relu à chaque lancement de `vibe`),
donc susceptible de changer de choix d'un jour à l'autre **sans la moindre
mise à jour de paquet**. Seule l'implémentation Python expose, à ce jour,
les options construites par `_construire_cmd_vibe` dans `watcher.py`
(`--agent`, `--workdir`, `--prompt`) telles que ce fichier les attend.

**Décision :** `watcher.py` pose `VIBE_CLI=python` dans l'environnement du
seul subprocess `vibe` qu'il lance (`AGENTS_CONNUS["vibe"]["env"]`, fusionné
sur une copie de `os.environ` — voir `lancer_claude`), jamais dans
l'environnement du watcher lui-même ni d'un autre agent. Choisi plutôt
qu'un endroit plus global (service systemd, profil shell) car c'est le seul
point qui centralise déjà tout ce qui est propre à cet agent — un futur
agent n'a qu'à ajouter sa propre clé `"env"` au même endroit.

Best-effort et non définitif : si Mistral retire un jour l'implémentation
Python, cette variable n'aura plus d'effet et `_construire_cmd_vibe` devra
être réécrite pour la Rust TUI de l'époque — aucune garantie à long terme,
seulement la neutralisation de la bascule distante *actuelle*.

## 7. Figer la version installée (issue #779)

Deuxième protection, contre une mise à jour de PAQUET (par opposition à la
bascule distante du §6, qui ne change pas la version installée) :
`~/.local/share/uv/tools/mistral-vibe/uv-receipt.toml` déclare aujourd'hui
`requirements = [{ name = "mistral-vibe" }]`, SANS version — `uv tool
upgrade mistral-vibe` bascule donc sur la dernière version publiée dès qu'il
est lancé, sans qu'aucune revue n'ait eu lieu.

**Pistes examinées :**
- *Sonde de compatibilité avant chaque lancement* (ex. `vibe --help` comparé
  à la liste d'options attendue) : rejetée — un appel subprocess
  supplémentaire sur CHAQUE tentative de CHAQUE issue confiée à Vibe, pour
  un événement qui ne s'est produit qu'une fois en plusieurs mois
  d'utilisation ; la table d'options attendues vieillirait d'ailleurs
  elle-même avec les versions de l'outil, exactement comme l'a montré le
  pré-vol d'authentification (`verifier_preflight_cle_api_vibe`) — un coût
  systématique pour une protection qui resterait, elle aussi, best-effort.
- *Version figée* : retenue. Une mise à jour ne peut plus survenir qu'à
  travers une action délibérée (relire le changelog de Vibe, vérifier que
  `_construire_cmd_vibe` est toujours valide, puis republier la version
  choisie) — précisément le but recherché, au prix d'une seule chose :
  Alain doit penser à relancer explicitement cette mise à jour de temps en
  temps (Vibe évolue vite), plutôt que de compter sur une bascule automatique.

**Déploiement** (sur chaque machine qui exécute Vibe pour ce watcher) :

```bash
uv tool install --force "mistral-vibe==2.26.1"
```

Toute mise à jour future se fait en changeant ce numéro de version
DÉLIBÉRÉMENT (jamais via `uv tool upgrade mistral-vibe` seul, qui ignorerait
le pin), après avoir vérifié que l'interface attendue par
`_construire_cmd_vibe` (options `--agent`/`--workdir`/`--prompt` avec
`VIBE_CLI=python`, §6 ci-dessus) est toujours celle produite par la nouvelle
version.

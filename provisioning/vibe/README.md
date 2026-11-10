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

**Correction (issue #873) : l'affirmation ci-dessous (« Vibe n'a pas
d'option... ») était FAUSSE**, contredite par simple lecture de `vibe
--help` (version 2.26.1 installée localement, CONSTATÉ directement, sans
lancer de session) : `--auto-approve`/`--yolo` (« Approves all tool calls
without prompting for the selected agent ») est bien un équivalent de
`--dangerously-skip-permissions` côté Claude Code, et `--smart-approve`
(« Classify each tool call and auto-run the safe ones, prompting only for
risky ones ») offre un palier intermédiaire. De même, sans `--agent` du
tout, l'approbation suit le `default_agent` de la config (`vibe --help` :
« Defaults to the 'default_agent' config setting... »), qui peut lui-même
valoir un agent d'auto-approbation — cohérent avec ce que rapporte l'issue
#873 (« le mode non interactif sans `--agent` retombe sur l'approbation
automatique, selon la documentation Mistral »).

**Décision inchangée malgré cette correction (issue #873, consigne
explicite) : ne PAS retirer `--agent bridge_ecriture`, ne PAS basculer sur
`--auto-approve`/`--yolo` ni sur l'absence de `--agent`.** C'est une
décision d'Alain, pas un correctif automatique — les conséquences de
sécurité sont réelles : `--auto-approve` lève TOUTE barrière (y compris les
syntaxes bash refusées qui motivent la clause de prompt du §9 ci-dessous),
alors que le profil `bridge_ecriture.toml` reste un allow-list explicite,
versionné et relu. Option documentée ici pour mémoire, non appliquée.

Profil TOML décrit ci-dessous (ancien texte, toujours valable pour la partie
qu'il décrit vraiment) : l'écriture se débloque outil par outil via un
profil décrit en TOML, désigné ensuite par son nom (`--agent
bridge_ecriture`). `watcher.py` construit déjà cette commande pour le mode
écriture (voir `AGENTS_CONNUS["vibe"]["construire_cmd"]`) — encore faut-il
que le fichier existe réellement à l'emplacement que Vibe va chercher.

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

### 1.1. Permissions plus fines : commandes précises en liste (examiné, PAS appliqué — issue #873)

Un essai réel (Vibe 3.1.1, Windows, `--agent bridge_ecriture`) a vu deux
commandes bash refusées malgré `[tools.bash] permission = "always"` (§1
ci-dessus) : une substitution de commande + une redirection (motif affiché
« shell syntax requiring approval: command substitution, redirection »), et
un `date /T` final pris pour un chemin de disque (« outside workdir: T:\\ »).
L'issue #873 demandait d'examiner, par lecture seule, si le profil peut
autoriser des commandes PRÉCISES plutôt que l'outil `bash` en entier, et si
cela éviterait ce genre de refus.

**Réponse (établie par lecture de ce dépôt et de `vibe --help`, version
2.26.1 installée localement — AUCUNE session vibe lancée) : NON, et même si
le schéma le permettait, cela n'aurait pas empêché les deux refus observés.**

- Le format TOML réellement utilisé (`bridge_ecriture.toml`, §1) ne
  déclare la permission qu'au niveau de l'OUTIL entier (`[tools.bash]
  permission = "always"`) — aucune syntaxe de motif/commande plus fine n'a
  été trouvée dans ce dépôt ni dans `vibe --help`.
- `vibe --help` (2.26.1) expose bien `--enabled-tools`/`--disabled-tools`
  avec motifs glob/regex (« Can use exact names, glob patterns (e.g.,
  'bash*'), or regex with 're:' prefix ») — mais ces motifs matchent des
  NOMS D'OUTILS (ex. `bash*` désignerait plusieurs outils nommés `bash...`,
  pas des commandes `bash` précises), pas le contenu d'une commande.
  Confirme la même granularité « outil entier » que le TOML, pas plus fine.
- **Point décisif, indépendant de l'existence ou non d'une telle liste** :
  les deux refus observés ne sont PAS des refus de « telle commande
  nommée », mais des refus de CLASSES DE SYNTAXE (substitution, redirection)
  et d'une heuristique de détection de chemin (`/T` pris pour `T:\`) —
  d'après la documentation Mistral citée par l'issue #873, ce classement
  s'applique en session non interactive indépendamment de la permission
  accordée à l'outil `bash` lui-même (renforcé par le correctif de sécurité
  de septembre 2026, avis MAI-2026-003). Une liste de commandes précises
  autorisées (`git commit`, `ls`...) n'aurait donc rien changé à CES deux
  refus : le vrai correctif est le changement de PROMPT (§9 ci-dessous), pas
  une permission de profil plus large.
- Non vérifié ici (aucun accès réseau, aucune session réelle) : si une
  version future de Vibe expose un jour un motif de commande plus fin (ex.
  un sous-champ `[tools.bash.allow]`), à revérifier avant de le supposer.

**Pistes proposées pour mémoire, NON appliquées à `bridge_ecriture.toml`**
(si un tel mécanisme venait à exister) — risque par commande, pour une
future décision d'Alain :

| Commande candidate                                  | Risque proposé |
|------------------------------------------------------|----------------|
| `git status`, `git diff`, `git log`, `git show`      | nul (lecture)  |
| `ls`, `pwd`, `cat <fichier>`                          | nul (lecture)  |
| `git add <chemin>`                                    | faible (réversible, `git reset`) |
| `git commit -m "<message littéral>"`                  | faible (local, jamais de push, réversible par `git revert`/`reset --soft`) |
| `mkdir -p <sous-dossier relatif>`                      | faible (création dans le périmètre `--workdir`) |
| toute commande avec substitution (`$(...)`, backticks) ou redirection (`>`, `>>`, `<`, `\|`) | **à ne jamais autoriser** — précisément la classe que Mistral elle-même juge risquée ; la réponse est le prompt (§9), pas une permission plus large |
| `rm -rf`, `git reset --hard`, `git clean -fd`, `git push` | **à ne jamais autoriser** — déjà proscrites partout ailleurs dans ce dépôt (irréversibilité) |

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

**Mise à jour (issue #873) — à nuancer, non tranché :**
- **Établi par la documentation Mistral** (citée par l'issue #873) : le mode
  non interactif ne demande JAMAIS de confiance de dossier — ce paragraphe
  entier pourrait donc ne plus être nécessaire pour un agent lancé par
  `watcher.py` (toujours non interactif).
- **Constaté directement** (lecture de `vibe --help`, version 2.26.1
  installée localement, AUCUNE session lancée) : un drapeau `--trust`
  existe, décrit littéralement comme fait pour ce cas : « Trust the working
  directory for this invocation only (not persisted to
  `trusted_folders.toml`). Skips the trust prompt. **Use this for
  non-interactive automation.** ». Son existence même suggère qu'au moins
  une version de Vibe a pu avoir besoin de ce rappel explicite — en
  tension avec le point précédent (« jamais de prompt »), sans qu'on sache
  laquelle des deux affirmations est la plus à jour. `_construire_cmd_vibe`
  ne pose actuellement PAS `--trust` : non appliqué par cette issue
  (changement de commande non demandé par l'issue #873 ; candidat pour une
  future issue, à valider par un essai réel).
- **Supposé, non vérifié** : la pré-approbation via `trusted_folders.toml`
  documentée ci-dessus reste donc, en l'état, une mesure défensive qui
  pourrait être redondante (doc Mistral) ou insuffisante seule (existence de
  `--trust` suggérant un besoin réel) — gardée telle quelle par prudence
  tant qu'aucun essai réel ne tranche. L'essai réel de l'issue #873 (Windows,
  Vibe 3.1.1) n'a lui-même rien isolé sur ce point précis : les deux refus
  observés étaient de nature différente (syntaxe bash, chemin mal parsé —
  voir §1.1 et §9), pas des refus de confiance de dossier.

## 3. Authentification

**Connexion par compte (sign-in navigateur), mode en usage depuis l'issue
#780.** La clé API statique (`MISTRAL_API_KEY`, par variable d'environnement
ou fichier `~/.vibe/.env`) a été abandonnée : elle facturait l'usage sur un
forfait distinct de celui du compte, lequel s'est épuisé et bloquait tout
traitement.

Vérifié en lisant le code source installé de Vibe
(`vibe.setup.auth.api_key_persistence.persist_api_key`) : les deux modes
(clé API saisie à la main, ou connexion par compte) finissent persistés par
le **même** mécanisme, qui privilégie toujours le trousseau système de la
machine (OS keyring, service `ai.mistral.vibe`, via le paquet tiers
`keyring`) et ne retombe sur `~/.vibe/.env` en clair que si aucun trousseau
n'est disponible. Une fois connecté par compte, ni `MISTRAL_API_KEY` ni
`~/.vibe/.env` ne portent donc la moindre trace de l'authentification
réelle — le fichier peut exister, vide, sans que cela signifie quoi que ce
soit.

> **Sous Windows (CCW) : le trousseau est lié au COMPTE Windows (issue
> #860).** Le trousseau système sollicité ci-dessus est le Credential
> Manager / DPAPI du compte Windows connecté au moment de `vibe` login — un
> service NSSM tournant sous `LocalSystem` (comportement historique de
> `ajouter_projet_ccw.ps1`) n'y a PAS accès, même si le fichier
> `~\.vibe\…` existe bien sur le disque : constaté sur un essai réel. Le
> service CCW du projet basculé sur Vibe doit tourner sous le MÊME compte
> Windows que celui utilisé pour `vibe` login — poser `-CompteService
> <compte>` à `ajouter_projet_ccw.ps1` (voir
> `provisioning/windows/REINSTALLATION_CCW.md`, étape 7).

**Conséquence pour `watcher.py` :** `verifier_preflight_cle_api_vibe` ne
vérifie plus que `MISTRAL_API_KEY`/`~/.vibe/.env`, quand l'un des deux est
présent, a une forme plausible (best-effort hérité de #760) — leur absence
n'est **plus** signalée, puisqu'elle ne prouve plus rien. Lire le trousseau
système directement depuis `watcher.py` a été envisagé et écarté (issue
#780) : cela demanderait une dépendance tierce que ce fichier n'a jamais eue
(bibliothèque standard uniquement, cf. `CONTEXTE.md`), avec un risque réel de
blocage si le trousseau est verrouillé sans agent de déverrouillage
disponible (cas plausible pour le service systemd `--user` de ce watcher,
démarré via `enable-linger` avant toute connexion graphique) — précisément
ce qu'un pré-vol n'a jamais le droit de faire. `~/.vibe/whoami_cache.json` a
aussi été examiné : ce n'est qu'un cache d'appels réseau passés (TTL 6h),
pas la preuve d'une authentification utilisable maintenant. En l'absence de
tout indice local fiable, ce pré-vol ne vérifie donc plus la présence d'une
authentification pour cet agent — seulement, best-effort, la forme d'une
éventuelle clé API encore présente.

Dans les deux modes, pas de session qui expire d'elle-même (à la différence
du token OAuth de Claude Code) : ce n'est qu'au moment d'un appel réel qu'une
clé révoquée ou un quota/crédit épuisé se révèlent (voir §5 de l'issue #760 :
détection en cours d'exécution, qui arrête alors le traitement immédiatement).

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
uv tool install --force "mistral-vibe==3.1.0"
```

**Mise à jour du numéro (issue #873) :** établi par l'énoncé de cette
tâche (essai réel sur le PC fixe d'Alain et sur un compte de test) — la
version validée est désormais la **3.1.0**, pas 2.26.1 (ancien pin de
l'issue #779, laissé ci-dessus jusqu'ici sans avoir été remis en cause).
**Constaté directement sur la machine qui a traité l'issue #873 (CCL)** :
`vibe --version` y rapporte encore `2.26.1`, et
`~/.local/share/uv/tools/mistral-vibe/uv-receipt.toml` y est toujours figé
sur ce numéro — cette machine n'a donc PAS été réalignée sur 3.1.0 par
cette issue (aucune commande d'installation/mise à jour exécutée : ce
README documente le pin à appliquer, il ne le déploie pas lui-même). À
vérifier/aligner par Alain avant de confier un vrai projet à Vibe depuis
cette machine précise.

Par ailleurs (issue #873, observation non expliquée) : un essai réel sur
la version **3.1.1** a vu des tentatives d'écriture dans un dossier de
travail git (worktree) rester SANS AUCUNE RÉPONSE (ni refus, ni sortie, ni
code de retour — simple silence), alors que la même opération a fonctionné
sur la **3.1.0**. Cause non identifiée (aucune session réelle relancée
pour investiguer, consigne de cette issue) : à surveiller si une future
mise à jour du pin vise une version ≥ 3.1.1 — tester d'abord explicitement
l'écriture dans un worktree avant de généraliser le nouveau pin à un projet
réel utilisant la parallélisation `mode_write` (issue #337).

Toute mise à jour future se fait en changeant ce numéro de version
DÉLIBÉRÉMENT (jamais via `uv tool upgrade mistral-vibe` seul, qui ignorerait
le pin), après avoir vérifié que l'interface attendue par
`_construire_cmd_vibe` (options `--agent`/`--workdir`/`--prompt` avec
`VIBE_CLI=python`, §6 ci-dessus) est toujours celle produite par la nouvelle
version.

## 8. Clause de prompt contre les commandes bash refusées (issue #873)

Un essai réel (Vibe 3.1.1, Windows, `--agent bridge_ecriture`, donc
approbation automatique non utilisée) a vu deux commandes bash refusées
faute de quelqu'un pour les approuver en session non interactive — voir
§1.1 pour le détail des deux refus et pourquoi une permission de profil
plus fine ne les aurait pas évités. Après le premier refus, le modèle avait
retenté la même commande telle quelle.

**Correctif appliqué (prompt, pas profil) :** `watcher.py` injecte
désormais, pour l'agent `vibe` uniquement (`AGENTS_CONNUS["vibe"]
["clause_bash"]`, constante `_CLAUSE_BASH_VIBE`), une consigne courte dans
le prompt de chaque issue confiée à Vibe — même mécanisme et même
emplacement que la clause « sous-agents » déjà existante
(`clause_sous_agents`) : créer/modifier des fichiers avec `write_file`/
`edit` plutôt que par bash, ne jamais utiliser de substitution de commande
ni de redirection dans une commande bash, ne jamais faire précéder une
commande d'un `cd` vers le dossier de travail (déjà le dossier courant via
`--workdir`), préférer des commandes simples et littérales (`git add`,
`git commit -m "message sans substitution"`), et ne jamais retenter une
commande refusée sous la même forme (changer d'approche, ou le signaler
dans le rapport). Absente du prompt pour l'agent `claude` (clé non
déclarée) : ce dernier n'a pas ce problème.

Non vérifié par un essai réel (consigne explicite de l'issue #873) : à
confirmer que cette clause réduit effectivement les refus lors de la
première bascule réelle d'un projet sur Vibe.

## 9. Garde-fou de longueur de prompt sous Windows (issue #873)

`--prompt` transmet le prompt sur la ligne de commande, pas sur stdin —
Windows plafonne `CreateProcess` à 32767 caractères au total, et
`list2cmdline()` de Python (utilisé par `subprocess.Popen` quand `args` est
une liste) reconstruit tout l'argv, prompt compris, en une seule ligne
avant de la transmettre. Même plafond déjà rencontré pour `gh issue comment
--body` (voir `commenter_issue` dans `watcher.py`, issue #237, qui l'évite
avec `--body-file`). Un prompt réel observé fait environ 12 000 caractères,
mais rien ne borne aujourd'hui sa taille (CONTEXTE + CONSIGNES + corps
d'issue injectés par `watcher.py`).

**Correctif appliqué : garde-fou qui échoue proprement.**
`_construire_cmd_vibe` lève `PromptTropLong` (nouvelle exception, même
esprit que `ModeAgentIndisponible`) si `len(prompt) >
LIMITE_CAR_PROMPT_VIBE_WINDOWS` (30 000 caractères, marge de sécurité sous
32767 pour le reste de l'argv et l'échappement de guillemets) — posé
UNIQUEMENT sous Windows (`os.name == "nt"`) : Linux (ARG_MAX de plusieurs
centaines de Ko) n'a pas cette contrainte, ce garde-fou ne se déclenche
jamais sur CCL. `lancer_claude` capture cette exception et retourne un
échec ordinaire avec un message clair (longueur observée, limite, piste de
correction) plutôt que de laisser passer un échec obscur côté `vibe`.

**Moyen de transmission alternatif : établi par lecture, NON appliqué.**
`vibe --help` (version 2.26.1 installée localement, aucune session lancée)
documente `--prompt-file PATH` : « Run in programmatic mode with the prompt
read from PATH, instead of -p TEXT or stdin. » — un fichier n'a aucune
limite de taille comparable à une ligne de commande, ce qui éliminerait
structurellement ce problème plutôt que de seulement le détecter. **Non
appliqué par cette issue**, pour trois raisons : (1) seule la version
2.26.1 (celle installée sur la machine CCL qui a traité l'issue #873) a été
vérifiée — pas la 3.1.0/3.1.1 réellement visée (§7), (2) basculer `--prompt`
vers `--prompt-file` demanderait de gérer le cycle de vie d'un fichier
temporaire (création, encodage, suppression garantie même en cas de
timeout/crash) dans `lancer_claude`, un changement plus large que le
périmètre strict demandé par cette issue (« construction du prompt et de la
commande Vibe », pas la gestion de fichiers temporaires côté watcher), (3)
aucun essai réel n'a pu confirmer le comportement de `--prompt-file` (encodage
UTF-8 notamment). Piste prête pour une future issue, avec la commande
exacte ci-dessus comme point de départ, à valider par un essai réel sur la
version réellement pinnée avant de remplacer le garde-fou actuel.

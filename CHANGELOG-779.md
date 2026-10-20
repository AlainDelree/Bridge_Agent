## 20 octobre 2026 — issue #779

Incident chesscoach #126 : l'agent Vibe a échoué en 3,4 secondes, pour toute
sortie un message de l'outil annonçant qu'une nouvelle interface (TUI Rust)
en préversion était utilisée par défaut et indiquant comment revenir à
l'ancienne au moyen d'une variable d'environnement — Vibe a été mis à jour
(ou sa bascule distante a changé) entre deux traitements, sans la moindre
intervention locale. Le garde-fou d'arrêt rapide (issue #763) a fonctionné
comme prévu et n'a donc PAS été modifié.

- **Variable d'environnement posée pour le seul subprocess `vibe`.** Lecture
  du code source de Vibe installé (`vibe.cli.launcher`) : le choix entre
  l'implémentation CLI historique (Python, celle que `_construire_cmd_vibe`
  construit) et la nouvelle (Rust, en préversion) suit `VIBE_CLI` si posée,
  sinon une bascule distante (cache GrowthBook `vibe_cli_rust_tui_rollout`),
  relue à CHAQUE lancement — donc susceptible de changer de choix sans
  aucune mise à jour de paquet. `AGENTS_CONNUS["vibe"]["env"] = {"VIBE_CLI":
  "python"}` (nouvelle clé `"env"` de `AGENTS_CONNUS`, absente pour
  `"claude"`) est désormais fusionné sur une COPIE de `os.environ` dans
  `lancer_claude`, juste avant le `Popen` — seul ce subprocess la reçoit,
  jamais l'environnement du watcher lui-même ni celui de l'agent `claude`.
  Centralisé au même endroit que le reste de ce qui est propre à l'agent
  (binaire, construction de la commande) plutôt que posée au niveau du
  service systemd, qui aurait affecté tout ce que ce compte lance.
- **Décision sur une future mise à jour silencieuse** (`provisioning/vibe/
  README.md` §6 et §7) : une sonde de compatibilité avant chaque lancement
  a été examinée puis rejetée (coût systématique sur chaque tentative de
  chaque issue, pour un incident survenu une seule fois en plusieurs mois —
  et une table d'options attendues vieillirait elle-même avec les versions
  de l'outil, comme l'a déjà montré le pré-vol d'authentification). Retenu à
  la place : figer la version installée (`uv tool install --force
  "mistral-vibe==2.26.1"`, à la place de `requirements = [{ name =
  "mistral-vibe" }]` sans version dans `uv-receipt.toml`) — une mise à jour
  ne peut alors plus survenir qu'à travers une action délibérée d'Alain, qui
  revérifie `_construire_cmd_vibe` avant de la republier. §6 documente en
  plus le choix de `VIBE_CLI=python` ci-dessus, qui neutralise à lui seul la
  bascule distante, indépendamment de la version installée.
- **Causes connues nommées dans le message d'arrêt rapide.** Le message de
  `_gerer_tentative_anormalement_rapide` (issue #763) pointait jusqu'ici
  inconditionnellement vers l'authentification, quelle que soit la cause
  réelle. Nouvelle fonction `_detecter_cause_connue_echec_rapide`, appelée
  UNIQUEMENT pour affiner ce message (jamais pour décider d'un arrêt, déjà
  acquis à ce stade) : reconnaît la signature réelle du message de Vibe sur
  sa nouvelle interface (`AGENTS_CONNUS["vibe"]["causes_connues_echec_
  rapide"]`, confirmée en lisant le binaire `vibe-rs` installé — "to switch
  back to the classic tui, set vibe_cli=python") ainsi qu'une signature
  générique « binaire introuvable » (dérivée de `msg_binaire_introuvable`,
  agnostique de l'agent). Best-effort explicite, comme les tables de
  signatures d'erreur bloquante existantes (#760/#761) : le texte générique
  d'authentification reste le repli dès qu'aucune signature ne correspond.
- **Tests** (`tests/test_vibe_cli_et_causes_connues_779.py`, 3 scénarios) :
  `VIBE_CLI=python` transmis au subprocess `vibe` seul (ni à `claude`, ni à
  `os.environ` du watcher) ; reconnaissance des deux signatures et repli sur
  `None` pour une sortie ordinaire ; bout en bout via `traiter_issue`, le
  commentaire de clôture cite la cause reconnue et plus le texte générique
  d'authentification. Suite complète (76 fichiers `tests/test_*.py`, dont
  #760/#761/#763) rejouée sans régression.

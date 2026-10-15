# CHANGELOG-761 — à fusionner dans CHANGELOG.md

## 15 octobre 2026 — issue #761

Correction de trois défauts relevés en relecture du diff de l'issue #760
(Mistral Vibe comme second agent d'exécution) — le troisième était une
régression sur l'agent en production (Claude Code), que #760 devait
pourtant laisser strictement inchangé.

- **Point 1 — périmètre transmis explicitement au nouvel agent.** La
  signature commune `construire_cmd(mode, modele, prompt, cwd)` (portée par
  `AGENTS_CONNUS[agent]["construire_cmd"]`) gagne un 4e paramètre `cwd` ;
  `lancer_claude` lui passe désormais `cwd_effectif` (le répertoire déjà
  calculé par l'appelant — projet ou worktree, issue #337), identique à celui
  du `cwd=` du Popen. `_construire_cmd_vibe` en fait usage via `--workdir
  {cwd}` : sans cette option, vibe se rabattait sur le répertoire courant du
  process, un confinement obtenu par simple effet de bord plutôt que demandé
  explicitement — c'était pourtant l'argument de sécurité principal en
  faveur de cet agent. `_construire_cmd_claude` reçoit `cwd` mais l'IGNORE
  délibérément (Claude Code n'a pas d'option équivalente et n'en a jamais eu
  besoin, son confinement passant déjà par le `cwd=` du Popen) : la commande
  produite pour l'agent en production est donc **strictement identique** à
  avant cette issue, dans les trois modes (vérifié par comparaison directe,
  voir le scénario de test ci-dessous).
- **Point 2 — mode lecture active (scratch) déclaré indisponible pour vibe**,
  plutôt que de le faire semblant de fonctionner. #760 mappait ce mode sur le
  même profil TOML que l'écriture libre, en misant sur le garde-fou
  technique existant (`_verifier_violation_scratch`, empreinte git
  avant/après) pour rattraper après coup une écriture dans le projet — mais
  ce mode a justement besoin d'écrire dans un dossier scratch **hors** du
  périmètre déclaré (`--workdir`), et vibe refuse précisément d'écrire hors
  de ce périmètre (constaté par essai manuel). La seule option qui
  l'étendrait, `--add-dir`, a été vérifiée dans le code source de l'outil
  installé (`vibe.core.workspace.Workspace.authorized_roots`, documenté
  littéralement comme « the whole of the write boundary ») : elle ouvre
  TOUT répertoire ajouté (`--workdir` comme `--add-dir`) à la même écriture
  sans aucune distinction lecture/écriture — l'utiliser pour le scratch
  aurait donc ouvert le projet à l'écriture tout autant, sans qu'aucun
  garde-fou ne rattrape une violation hors du dépôt git. `_construire_cmd_vibe`
  lève désormais `ModeAgentIndisponible` (nouvelle exception, capturée
  proprement dans `lancer_claude` — échec ordinaire de la tentative, jamais
  un crash) quand `MODE_LECTURE_ACTIVE` est demandé pour cet agent, plutôt
  que de contourner avec une fausse confinement. Documenté dans
  `provisioning/vibe/README.md` et le profil `bridge_ecriture.toml`. Aucun
  projet n'étant encore basculé sur vibe, ceci ne change aucun comportement
  observable actuel — seulement ce qui se passerait lors d'une future
  bascule.
- **Point 3 — détection d'erreur bloquante restreinte au flux d'erreur réel
  du process**, plus jamais au rapport rédigé par l'agent (régression sur
  l'agent en production, corrigée). #760 cherchait les signatures
  (`SIGNATURES_ERREUR_BLOQUANTE_*`) dans la `sortie` capturée par
  `_executer_une_tentative`, qui peut être soit le vrai stderr d'un échec de
  process, soit — après reclassification par les garde-fous #581/#757
  (sortie sans marqueur ✅/❌, ou verdict ❌ malgré un code de retour 0) — un
  message embarquant un extrait du RAPPORT de l'agent : un rapport évoquant
  de l'authentification, des quotas disque ou un code retour HTTP
  déclenchait alors un arrêt définitif à tort, label d'échec posé sans
  aucune tentative. `_executer_une_tentative` retourne désormais un 3e
  élément, `stderr_brut` : la `sortie` originale UNIQUEMENT si `succes` était
  déjà `False` au retour de `lancer_claude` (donc un vrai stderr de process,
  jamais rédigé par l'agent), sinon `None`. `_detecter_erreur_bloquante`
  (signature changée : `stderr_brut: str | None`, appelée désormais avec ce
  3e élément plutôt qu'avec `sortie`) retourne toujours `None` sur `None` —
  aucune détection n'est plus jamais tentée sur un texte produit par l'agent.
  Signatures revues au passage pour les deux agents (plus conservatrices,
  "mieux vaut rater une erreur bloquante qu'arrêter à tort une issue
  valide") : retrait des formulations trop ordinaires isolément
  ("not logged in", "please run", "unauthorized" seul, "quota" seul) au
  profit de formulations plus spécifiques ("invalid api key",
  "authentication_error", "please authenticate", "oauth token", "credit
  balance is too low" pour Claude Code ; "invalid api key", "401
  unauthorized", "quota exceeded", "insufficient quota" pour vibe, toujours
  best-effort et non vérifié en conditions réelles).

- **`watcher.py`** : nouvelle exception `ModeAgentIndisponible` ; signature de
  `construire_cmd` (+`cwd`) sur les deux entrées de `AGENTS_CONNUS` ;
  `_detecter_erreur_bloquante` prend `stderr_brut` au lieu de `sortie` ;
  `_executer_une_tentative` retourne `(succes, sortie, stderr_brut)` (seul
  appelant, dans `_traiter_issue_synchrone`, mis à jour) ; constantes
  `SIGNATURES_ERREUR_BLOQUANTE_CLAUDE`/`_VIBE` resserrées.
- **`provisioning/vibe/README.md`** et **`provisioning/vibe/agents/bridge_ecriture.toml`** :
  documentent `--workdir` et l'indisponibilité du mode lecture active.
- **`tests/test_corrections_erreurs_bloquantes_761.py`** (nouveau, 4
  scénarios) : commande produite pour `vibe` (`--workdir`) et pour `claude`
  (strictement inchangée, comparaison directe par mode) ; `MODE_LECTURE_ACTIVE`
  sous vibe échoue proprement via `lancer_claude` (sans lancer de process
  `vibe` réel — aucune session facturée, consigne de #760/#761) ; un rapport
  d'agent (succès réinterprété en échec par #581, mots ordinaires inclus) ne
  déclenche PAS l'arrêt définitif et consomme ses deux tentatives prévues ;
  un vrai stderr de process avec signature déclenche, lui, l'arrêt immédiat
  dès la première tentative. Les 64 tests existants (`tests/lancer_tous_les_tests.py`)
  restent verts sans modification, plus ce nouveau fichier (65/65).
- **Aucune session réelle `claude`/`vibe` lancée** pendant cette tâche
  (consigne explicite, quota facturé pour vibe + deux agents imbriqués) :
  toutes les vérifications ci-dessus passent par de faux exécutables
  (`tests/garde_fou_faux_executables.py`, même technique que les tests
  existants #247/#322/#327) ou par appel direct des fonctions Python. Le CLI
  `vibe` réellement installé sur cette machine a servi UNIQUEMENT à lire son
  aide (`vibe --help`, confirmant `--workdir`/`--add-dir`) et son code source
  installé (`vibe.core.workspace.Workspace`, confirmant l'absence de
  distinction lecture/écriture par répertoire) — jamais à lancer de session.

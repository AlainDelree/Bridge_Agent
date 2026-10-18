# CHANGELOG-768 — à fusionner dans CHANGELOG.md

## 18 octobre 2026 — issue #768

Label indiquant quel **agent d'exécution** a traité l'issue, posé à la
clôture en même temps que `done` — distinct des labels de plateforme déjà
existants (`for-linux`/`for-windows`), qui ne permettaient pas de
distinguer un second agent tournant sur la même machine du premier.

- **Nouveaux labels `agent-claude` / `agent-vibe`** (un par valeur connue de
  `AGENT`, voir `AGENTS_CONNUS` de `watcher.py`) : posés par
  `fermer_issue()` via la nouvelle propriété `Config.label_agent` (dérivée
  de `CFG.agent`, jamais de la plateforme). Ajoutés à `nouveau_projet.LABELS`
  (provisionnés d'office sur tout nouveau projet, même précédent que
  `sans-redacteur`/#648) ; créés manuellement sur le dépôt Bridge_Agent lui-
  même (`gh label create`). **Les autres dépôts déjà existants nécessitent
  le même `gh label create` manuel une fois** — hors périmètre de ce
  worktree.
- **Best-effort, jamais bloquant.** `ajouter_label()` journalise désormais
  aussi un code de retour `gh` non nul (ex. label absent du dépôt), en plus
  de la capture d'exception déjà en place — mais ne lève et ne retourne
  toujours rien : un échec de pose du label d'agent ne peut ni empêcher ni
  changer le résultat de `fermer_issue()`.
- **Correction du commentaire erroné introduit par #767** sur
  `formater_bloc_calibration()` : il affirmait que la ligne `🤖 Agent : ...`
  du commentaire de clôture provenait d'une lecture de la clé `AGENT` du
  projet — ce que le code n'a jamais fait (seule `LIBELLE_AGENT`, ou à
  défaut la plateforme détectée, est lue). La ligne elle-même est renommée
  `🤖 Plateforme : ...` pour ne plus laisser croire qu'elle désigne l'agent
  d'exécution, désormais couvert par le label ci-dessus.
- Test ajouté : `tests/test_label_agent_768.py` (3 scénarios — dérivation de
  `label_agent`, pose conjointe à la clôture, best-effort sur échec).

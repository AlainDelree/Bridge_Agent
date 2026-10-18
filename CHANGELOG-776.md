## 18 octobre 2026 — issue #776

Correction de l'ordre fusion/consolidation du changelog dans `WORKTREES.md`,
qui provoquait un conflit systématique en cas de worktrees parallèles.

- **Cause** : consolider `CHANGELOG-<N>.md` *depuis le worktree*, avant de
  merger, modifie `CHANGELOG.md` sur chaque branche worktree indépendamment —
  deux branches parallèles insérant chacune leur entrée en tête du même
  fichier entrent alors en conflit au second merge, par construction.
- **§3 (workflow normal)** : procédure principale réécrite — fusionner
  chaque branche worktree dans `master` *en premier* (étape 3), puis
  consolider les `CHANGELOG-<N>.md` *depuis `REP_TRAVAIL`*, jamais depuis un
  worktree (étape 4 nouvelle). Raison expliquée en détail. Règle générale
  énoncée : ne jamais consolider le changelog depuis un worktree. Rappel que
  cette règle ne remplace pas la leçon voisine (committer le code avant de
  merger) : l'une concerne le code, l'autre le changelog.
- **Avertissement inversé** : l'ancien ⚠️ présentait le bon ordre (merger
  puis consolider) comme l'erreur à éviter — il disait l'exact inverse de la
  règle correcte. Remplacé par un avertissement sur le cas d'un
  `CHANGELOG-<N>.md` encore non consolidé au moment d'un push.
- **§4 (récupération)** : retrait de l'entrée « `CHANGELOG-N.md` oublié avant
  merge/push », qui décrivait en réalité le déroulement normal (relancer le
  script depuis `REP_TRAVAIL` après le merge) et n'avait plus lieu d'être
  présentée comme une exception.
- **Méthode alternative vérifiée** (copier `CHANGELOG-<N>.md` sur `master`
  avant de merger, puis consolider depuis `master`) : testée par un merge
  git réel. Elle ne provoque pas le conflit sur `CHANGELOG.md` (même raison
  que la méthode recommandée : le `CHANGELOG.md` de la branche worktree
  n'est jamais modifié), mais `CHANGELOG-<N>.md` réapparaît sur `master`
  après le merge suivant et doit être supprimé une seconde fois — documentée
  avec cette réserve plutôt que retirée, puisqu'elle ne provoque pas la
  collision visée.
- **`BRIDGE_AGENT_DOC.md` §10** : levée de l'ambiguïté « au moment de la
  fusion du worktree » (avant ou après ?) — précisé : après la fusion,
  jamais depuis le worktree. Pied de page mis à jour.

Aucun script modifié — uniquement `WORKTREES.md` et `BRIDGE_AGENT_DOC.md`.

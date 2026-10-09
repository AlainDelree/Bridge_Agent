# CHANGELOG-737 — à fusionner dans CHANGELOG.md

## 9 octobre 2026 — issue #737 (finitions)

Nettoyage de finition de `BRIDGE_AGENT_DOC.md` après relecture de la version publiée (743 → 635 lignes) : une contradiction, des restes et des condensations, sans renumérotation de section ni modification de code.

- **§16 vs §3.4 (contradiction)** — §16 restreignait le service CCW central (`REDACTEUR=bridge_agent`) aux projets « sans service dédié » ; §3.4 autorise correctement cette voie pour n'importe quel projet, y compris avec service dédié, à réserver à un besoin exceptionnel. §16 aligné sur §3.4 (restriction supprimée, renvoi conservé).
- **§6 (Champs spéciaux)** — retrait du paragraphe final sur les valeurs `TYPE=spec_*`, retirées du code par l'issue #734.
- **TIMEOUT par défaut (§3.3/§6/§19)** — vérifié dans `watcher.py` (`extraire_timeout`/`Config.timeout_claude`) : le défaut réel est celui du projet (`TIMEOUT_CLAUDE` du `.conf`), lui-même 300 s si absent du `.conf` — pas un flat 300 s comme l'affirmaient §6/§19. Les trois endroits réécrits à l'identique : « défaut du projet (`TIMEOUT_CLAUDE` du `.conf`, 300 s si non précisé) ».
- **§10 (CHANGELOG.md)** — règle périmée (« toute issue ajoute son entrée en tête de CHANGELOG.md ») et historique #237-#268 retirés ; remplacés par la description du mécanisme actuel (`CHANGELOG-<N>.md` par worktree, fusionné par `scripts/fusionner_changelog.py`) et la seule règle à conserver : maintenir la toute dernière ligne « Dernière mise à jour » au format attendu par `regenerer_tableaux_projets.py`.
- **§12 (exception configs/*.conf)** — condensé à 7 lignes : Alain seul modifie `configs/*.conf` ; CCL/CCW ne le font jamais, même si l'issue le demande ; garde-fou technique de `watcher.py` annule automatiquement. Historique (#298, #318), noms de fonctions internes et détail du mécanisme retirés — déjà dans `ARCHITECTURE.md` §2.6.
- **§13 (Commandes utiles)** — section supprimée en totalité : gestion de projet CLI déjà dans `ARCHITECTURE.md` §8, parallélisation `mode_write` déjà dans `WORKTREES.md`. Phrase sur la reprise de worktree par `RELANCE` ajoutée au §11 (absente jusqu'ici).
- **§14 (Chef → Ouvrier)** — réduit de ~86 à ~43 lignes : conservé le principe, le critère de décision + contre-exemple pour ne pas passer par un chef, le format des titres, le TIMEOUT généreux pour un chef, une phrase sur le rallumage des watchers `for-windows`. Retiré : note « injection automatique » et son historique (#209/#243/#241/#242), rappel détaillé de la contrainte d'exécution synchrone (déjà injectée par `consignes/globales.md`, renvoi conservé), exemple avec commande `gh issue create` complète.
- **§1** — note « Rafraîchissement automatique (issue #185) » réduite à une phrase.

Contrôles effectués : aucun renvoi `§N` cassé (vérifié par grep, toutes les sections référencées existent) ; tableaux §2/§7 et pied de page « Dernière mise à jour » non touchés ; suite de tests complète (`pytest tests/` — 227 tests) et scripts `test_*.py` autonomes tous verts ; `regenerer_tableaux_projets.regenerer()` testé sur une copie isolée (jamais sur le vrai dépôt).

Point d'attention signalé mais non traité (hors périmètre « aucune modification de code ») : deux commentaires de code pointent vers `BRIDGE_AGENT_DOC.md §13` (`watcher.py::_compter_watchers_actifs`, `scripts/mesurer_api.py`), section désormais supprimée — ces renvois étaient déjà incohérents avec le contenu de l'ancien §13 avant ce nettoyage (ni PID ni mesure API n'y figuraient), donc pas une régression introduite ici, mais à corriger dans une issue dédiée si jugé utile.

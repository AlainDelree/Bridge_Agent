# CHANGELOG-775 — à fusionner dans CHANGELOG.md

## 18 octobre 2026 — issue #775

Élagage de `BRIDGE_AGENT_DOC.md` : retrait des éléments d'interface/affichage
que les ajouts récents liés au second agent (Vibe) y avaient fait entrer,
sans rapport avec la rédaction d'une issue ou la compréhension du
fonctionnement du système.

- **Retiré** : le paragraphe sur l'onglet web « Agent Vibe » (choix du
  modèle actif, déclaration/retrait, écriture chirurgicale de `config.toml`)
  et le journal `logs/journal_modele_vibe.jsonl` qu'il alimente (§10, issues
  #766/#769) — pure description d'interface, aucune issue ne s'écrit
  différemment selon que ce journal existe.
- **Retiré** : le paragraphe sur la ligne `🤖 Plateforme :` du commentaire
  de clôture et son renommage depuis « Agent » (§19, issue #768), ainsi que
  les deux renvois croisés vers elle (§4, §10) — intitulé d'affichage,
  distinct du mécanisme réellement utile (labels `agent-claude`/`agent-vibe`,
  conservés).
- **Conservé** sans y toucher : la présence des deux agents d'exécution, le
  réglage par projet (clé `AGENT` du `.conf`) et les labels posés à la
  clôture (§4, §10) — ont leur place dans ce document.
- **Ajouté** (§5) : l'indisponibilité du mode lecture active (`mode_scratch`)
  pour l'agent `vibe` (issue #761) — vibe n'a aucun moyen d'ouvrir le
  dossier scratch en écriture sans ouvrir aussi le projet ; une issue en
  lecture active sur un projet réglé sur cet agent échoue. Cette contrainte
  n'était documentée que dans `watcher.py`, jamais dans le document de
  référence pour Claude Chat.
- Ligne de pied de page (« Dernière mise à jour ») mise à jour en
  conséquence, sans toucher à l'exemple de ce même format au §10.

Aucune réécriture globale entreprise : seules les parties dont l'inutilité
était nette ont été retirées, le reste du document (dont le reste du §10,
§16, §18, §19) n'a pas été remis en cause.

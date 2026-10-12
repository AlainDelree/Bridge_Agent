# CHANGELOG-753 — à fusionner dans CHANGELOG.md

## 13 octobre 2026 — issue #753

Nouveau bouton « ↺ Relancer les allumés » dans le panneau latéral Infrastructure — jusqu'ici, pour déployer un changement de `watcher.py`, seul « ↺ Relancer tous les CCL » relançait les watchers déjà actifs, mais il allumait aussi tous les éteints (14 projets), qui scrutent alors GitHub toutes les 11s pendant 20 min sans aucune utilité (~1500 appels, près d'un tiers du quota horaire).

- **`static/js/panneau_lateral.js`** : nouveau bouton entre « ▶ Lancer les éteints » et « ↺ Relancer tous les CCL », visible seulement s'il y a au moins un watcher actif. Relance uniquement les watchers CCL actuellement actifs (même source `/watchers`), un à la fois, la relance en échec d'un projet ne bloquant pas les suivants. Saute (sans le relancer) tout watcher actif dont le décompte « en cours » n'est pas nul (`resumeProjetMonitoring`, déjà en mémoire — aucun fetch réseau supplémentaire), et le signale dans un résumé court « N relancé(s), M ignoré(s) » avec les noms des projets occupés.
- Trois fonctions pures ajoutées et testées sans DOM (`static/js/tests/panneau_lateral.test.js`) : `selectionnerWatchersActifsARelancer` (sélection actifs + sans issue en cours — un éteint n'est jamais relancé ni compté comme ignoré), `resumerRelanceActifs` (texte du résumé + choix du type de toast : succès non comptabilisé si rien d'ignoré, avertissement sinon), `relancerSequentiellement` (boucle séquentielle, échec d'un projet sans effet sur les suivants).
- Les deux boutons existants restent inchangés dans leur fonctionnement ; une info-bulle a été ajoutée sur « ↺ Relancer tous les CCL » rappelant qu'il allume aussi les watchers éteints.
- `ARCHITECTURE.md` : nouvelle section §13 décrivant ce bouton. `BRIDGE_AGENT_DOC.md` non modifié (hors périmètre de la tâche).

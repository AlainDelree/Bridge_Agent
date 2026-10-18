# CHANGELOG-769 — à fusionner dans CHANGELOG.md

## 18 octobre 2026 — issue #769

Journal des changements de modèle de l'agent Vibe faits depuis l'interface
web, et mise à jour de la documentation sur les évolutions récentes non
encore documentées (#768).

- **Journal `logs/journal_modele_vibe.jsonl`** (gitignoré, JSONL — même
  convention que `journal_ecritures_historique.jsonl` de `watcher.py`,
  issue #521) : une ligne par changement de modèle actif, déclaration ou
  retrait fait depuis l'onglet **Agent Vibe** (`app/vibe_modele.py`), avec
  date, modèle quitté et modèle choisi. Best-effort strict : un échec
  d'écriture (`_journaliser_modele`) ne bloque jamais l'opération qu'il
  journalise. Borné aux `NB_ENTREES_JOURNAL_CONSERVEES` (300) entrées les
  plus récentes plutôt qu'un archivage par catégorie — le volume d'une
  action manuelle reste de toute façon faible (même logique que
  `NB_SAUVEGARDES_CONSERVEES` du même fichier).
- **Historique affiché dans l'onglet** : `GET /vibe-modele/etat` expose
  désormais la clé `journal` (les `NB_ENTREES_JOURNAL_AFFICHEES` = 20
  entrées les plus récentes, la plus récente en premier) ; nouvelle section
  « Historique des changements » dans `templates/fragments/onglet_vibe.html`
  / `static/js/vibe_modele.js`, qui précise explicitement que ce journal ne
  couvre que les changements faits par l'interface — ni une édition
  manuelle de `config.toml`, ni la réécriture faite par Vibe lui-même à
  chaque démarrage.
- **Un changement vers le modèle déjà actif (no-op) n'est pas journalisé**
  (aucun changement réel) ; déclaration et retrait sont journalisés chacun
  avec leur propre événement (`declaration`/`retrait`) pour qu'un modèle
  retiré puis redéclaré n'apparaisse pas comme un trou dans l'historique.
- **Documentation (`BRIDGE_AGENT_DOC.md`)** mise à jour : §4 (nouveaux
  labels `agent-claude`/`agent-vibe` posés à la clôture, issue #768, et le
  fait qu'ils doivent exister sur le dépôt cible) ; §10 (mention du journal
  introduit ici, et rappel de la distinction label d'agent vs ligne de
  plateforme) ; §19 (ligne `🤖 Plateforme :` du commentaire de clôture,
  renommée depuis « Agent » par #768). Ligne de pied de page « Dernière
  mise à jour » mise à jour en conséquence.
- Tests ajoutés : `tests/test_journal_modele_vibe_769.py` (6 scénarios —
  journalisation d'un changement actif, no-op non journalisé, déclaration +
  retrait, exposition dans `/vibe-modele/etat`, purge au-delà du plafond,
  best-effort sur échec d'écriture) et extension de
  `static/js/tests/vibe_modele.test.js` (rendu des entrées de journal,
  logique pure). `tests/test_modele_vibe_766.py` corrigé pour isoler le
  journal dans un répertoire temporaire (évite de polluer le vrai
  `logs/journal_modele_vibe.jsonl` à chaque exécution des tests).

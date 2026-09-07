## 7 septembre 2026 — issue #521

Traçabilité minimale sur `logs/historique_durees.json` et
`logs/etat_timeout.json`, pour diagnostiquer une future perte de données
comme celle du 7 septembre 2026 restée inexpliquée faute de preuve (fichiers
gitignorés, aucun historique git natif).
- Approche retenue (parmi les deux esquissées dans l'issue) : un journal
  séparé append-only, plutôt qu'une exception ciblée au `.gitignore` de
  `logs/` — `historique_durees.json` grossit à chaque issue close
  (cf. `scripts/archiver_historique.py`), le suivre en git alourdirait
  chaque commit de sauvegarde CCL sans rapport avec la tâche en cours.
- `watcher.py` : nouveau `logs/journal_ecritures_historique.jsonl` (JSON
  Lines, déjà couvert par le `.gitignore` existant de `logs/`) via
  `_journaliser_ecriture` (nouvelle fonction). Une ligne par écriture
  significative : `nb_avant`/`nb_apres` (nombre d'entrées), taille en octets
  avant/après, `operation`, et `reinitialise_corruption=true` si l'écriture
  repart d'un JSON illisible (la signature exacte d'une perte de données
  silencieuse — jusqu'ici, `enregistrer_duree` réinitialisait déjà
  discrètement l'historique à `[]` dans ce cas, sans laisser aucune trace).
  Appelé depuis `enregistrer_duree` (`operation="cloture_issue"`,
  `historique_durees.json`) et depuis `_maj_etat_json` pour
  `etat_timeout.json` uniquement (`operation="calibration_timeout"`,
  nombre de combinaisons avant/après) — `etat_ambiance.json` non instrumenté
  (deux clés fixes `F_reseau`/`F_local`, jamais perdues de la même façon,
  hors du périmètre demandé par l'issue).
- `scripts/archiver_historique.py` : écrit aussi dans ce même journal
  (`operation="archivage_manuel"`, nouvelle fonction locale
  `_journaliser_archivage`, sans importer `watcher.py` — cohérent avec le
  découplage volontaire du script) lors d'une exécution réelle (jamais en
  `--dry-run`). But : qu'une réduction volontaire et attendue du fichier
  (archivage manuel par Alain) ne soit jamais confondue, à la lecture du
  journal, avec une chute inexpliquée.
- `BRIDGE_AGENT_DOC.md` (§19.3, §19.7) : documentation du nouveau journal et
  de son rôle diagnostique.
- Aucun test dédié ajouté : vérification manuelle (écritures normales,
  simulation d'une corruption suivie d'une réinitialisation, exécution de
  `archiver_historique.py`) dans un dossier temporaire isolé, hors du
  périmètre du projet — cf. rapport de clôture de l'issue.

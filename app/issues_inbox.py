"""État de l'onglet « Résultats inbox » (issue #483).

Lit l'état du watcher_issues_inbox (scripts/watcher_issues_inbox.py) UNIQUEMENT
depuis le disque — aucun appel gh, aucune dépendance au watcher étant en cours
d'exécution ou non. L'alarme visuelle de l'onglet est pilotée exclusivement par
la présence de fichiers dans issues_inbox/rejected/ (pas de parsing de log, cf.
tâche demandée de l'issue #483) ; l'historique des succès/rejets est une simple
lecture informative de logs/issues_inbox.log, sans effet sur l'alarme.
"""

import sys
from pathlib import Path

from flask import jsonify

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT / "scripts"))

from watcher_issues_inbox import charger_config_inbox, DEFAUT_CHEMIN_CONFIG  # noqa: E402

# Nombre de lignes d'historique renvoyées à l'onglet (le fichier lui-même est
# déjà borné à MAX_LOG_LINES par le watcher — cf. ConfigInbox.max_log_lines).
LIGNES_HISTORIQUE_AFFICHEES = 50


def _config():
    """Relit configs/watcher_issues_inbox.conf à chaque appel (comme
    app/projets.py::get_config) — reflète toujours l'état réel du fichier,
    y compris s'il a été créé/modifié à la main par Alain après le démarrage
    du serveur. Absent : défauts sensés (voir ConfigInbox)."""
    return charger_config_inbox(DEFAUT_CHEMIN_CONFIG)


def etat_inbox():
    """Retourne :
      - alarme     : True si issues_inbox/rejected/ contient au moins un fichier
      - rejetes    : [{nom, date}] triés du plus récent au plus ancien
      - historique : dernières lignes de logs/issues_inbox.log (plus récente
                     en premier), purement informatif
    """
    cfg = _config()

    rejetes = []
    if cfg.rejected_dir.is_dir():
        for chemin in cfg.rejected_dir.iterdir():
            if not chemin.is_file():
                continue
            try:
                horodatage = chemin.stat().st_mtime
            except OSError:
                continue
            rejetes.append({"nom": chemin.name, "date": horodatage})
    rejetes.sort(key=lambda r: r["date"], reverse=True)

    historique = []
    if cfg.fichier_log.exists():
        try:
            lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
            historique = list(reversed(lignes[-LIGNES_HISTORIQUE_AFFICHEES:]))
        except OSError:
            historique = []

    return jsonify(
        alarme=len(rejetes) > 0,
        rejetes=rejetes,
        historique=historique,
        inbox_dir=str(cfg.inbox_dir),
        rejected_dir=str(cfg.rejected_dir),
    )

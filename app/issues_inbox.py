"""État de l'onglet « Résultats inbox » + pilotage du watcher spool (issues
#483, #485).

Lit l'état du watcher_issues_inbox (scripts/watcher_issues_inbox.py) UNIQUEMENT
depuis le disque — aucun appel gh. L'alarme visuelle de l'onglet est pilotée
exclusivement par la présence de fichiers dans issues_inbox/rejected/ (pas de
parsing de log, cf. tâche demandée de l'issue #483) ; l'historique des succès/
rejets est une simple lecture informative de logs/issues_inbox.log, sans effet
sur l'alarme.

Gestion du processus (issue #485) : même principe que chemin_pid/
watcher_actif/demarrer_watcher/arreter_watcher de app/watchers.py, mais pour
le watcher spool UNIQUE (pas de paramètre projet, un seul fichier PID). Le
watcher spool n'a par défaut pas d'auto-extinction (contrairement aux watchers
de projet, DELAI_INACTIVITE_MIN) : une durée optionnelle peut être choisie au
démarrage (--duree-min), auto-extinction interne implémentée par le script
lui-même (voir scripts/watcher_issues_inbox.py::boucle).
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from flask import jsonify, request

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT / "scripts"))

from watcher_issues_inbox import charger_config_inbox, DEFAUT_CHEMIN_CONFIG  # noqa: E402

# Nombre de lignes d'historique renvoyées à l'onglet (le fichier lui-même est
# déjà borné à MAX_LOG_LINES par le watcher — cf. ConfigInbox.max_log_lines).
LIGNES_HISTORIQUE_AFFICHEES = 50

# Fichier PID : même convention que les watchers de projet (app/watchers.py::
# chemin_pid), mais chemin fixe puisqu'il n'existe qu'UN watcher spool.
CHEMIN_PID = DOSSIER_SCRIPT / "logs" / "watcher-issues_inbox.pid"
# Échéance d'auto-extinction (epoch, écrite par demarrer_watcher_inbox() si une
# durée a été choisie) — permet à l'interface d'afficher le temps restant sans
# dépendre de l'horloge interne (monotone) du process watcher, qui tourne dans
# un process séparé de Flask. Absente = watcher lancé « indéfiniment ».
CHEMIN_ECHEANCE = DOSSIER_SCRIPT / "logs" / "watcher-issues_inbox.echeance"


# ─── Gestion du processus ──────────────────────────────────────────────────

def watcher_inbox_actif() -> tuple[bool, int | None]:
    """Retourne (actif, pid) — même logique que app/watchers.py::watcher_actif."""
    if not CHEMIN_PID.exists():
        return False, None
    try:
        pid = int(CHEMIN_PID.read_text().strip())
        os.kill(pid, 0)   # lève OSError si le processus est mort
        return True, pid
    except (OSError, ProcessLookupError, ValueError):
        return False, None


def _temps_restant_s():
    """Secondes avant l'auto-extinction, ou None si aucune durée n'a été
    fixée au démarrage (le watcher tourne indéfiniment)."""
    if not CHEMIN_ECHEANCE.exists():
        return None
    try:
        echeance = float(CHEMIN_ECHEANCE.read_text().strip())
    except (OSError, ValueError):
        return None
    return max(0.0, echeance - time.time())


def demarrer_watcher_inbox(duree_min: int = 0) -> tuple[bool, int]:
    """Lance (ou relance) le watcher spool. Redémarre TOUJOURS s'il tourne
    déjà — pas de refus silencieux (issue #485) : la nouvelle durée remplace
    l'ancienne. duree_min=0 → tourne indéfiniment (comportement historique)."""
    actif, pid_ancien = watcher_inbox_actif()
    if actif and pid_ancien:
        try:
            os.kill(pid_ancien, signal.SIGTERM)
            time.sleep(0.8)
        except OSError:
            pass

    CHEMIN_PID.parent.mkdir(parents=True, exist_ok=True)
    watcher_script = DOSSIER_SCRIPT / "scripts" / "watcher_issues_inbox.py"
    cmd = [sys.executable, str(watcher_script)]
    if duree_min > 0:
        cmd += ["--duree-min", str(duree_min)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    CHEMIN_PID.write_text(str(proc.pid))
    if duree_min > 0:
        CHEMIN_ECHEANCE.write_text(str(time.time() + duree_min * 60))
    else:
        CHEMIN_ECHEANCE.unlink(missing_ok=True)
    return True, proc.pid


def arreter_watcher_inbox() -> tuple[bool, str]:
    """Arrête le watcher spool via SIGTERM. Retourne (succès, message)."""
    actif, pid = watcher_inbox_actif()
    if not actif:
        return False, "watcher déjà inactif"
    try:
        os.kill(pid, signal.SIGTERM)
        CHEMIN_PID.unlink(missing_ok=True)
        CHEMIN_ECHEANCE.unlink(missing_ok=True)
        return True, f"watcher arrêté (pid {pid})"
    except OSError as e:
        return False, str(e)


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
      - watcher_actif, watcher_pid, watcher_restant_s : état du processus
        watcher spool (issue #485) — restant_s = None si actif sans durée
        fixée (indéfini) ou si inactif.
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

    actif, pid = watcher_inbox_actif()

    return jsonify(
        alarme=len(rejetes) > 0,
        rejetes=rejetes,
        historique=historique,
        inbox_dir=str(cfg.inbox_dir),
        rejected_dir=str(cfg.rejected_dir),
        watcher_actif=actif,
        watcher_pid=pid,
        watcher_restant_s=_temps_restant_s() if actif else None,
    )


def demarrer_watcher_inbox_route():
    """Démarre (ou relance, si déjà actif) le watcher spool. JSON attendu :
    {duree_min: N} — 0 ou absent = tourne indéfiniment."""
    data = request.json or {}
    try:
        duree_min = int(data.get("duree_min") or 0)
    except (TypeError, ValueError):
        return jsonify(succes=False, erreur="duree_min invalide.")
    if duree_min < 0:
        return jsonify(succes=False, erreur="duree_min doit être positif ou nul.")
    try:
        _, pid = demarrer_watcher_inbox(duree_min)
        return jsonify(succes=True, pid=pid, duree_min=duree_min)
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))


def arreter_watcher_inbox_route():
    """Arrête le watcher spool."""
    ok, msg = arreter_watcher_inbox()
    return jsonify(succes=ok, message=msg)

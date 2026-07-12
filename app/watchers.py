"""Gestion des processus watcher du bridge (un watcher par projet).

Extraite de new_issue.py à l'étape 6 du refactoring modulaire. Regroupe le
cycle de vie des watchers : démarrage, arrêt, détection du PID et les routes
Flask associées à l'onglet « Watchers » de l'interface.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from flask import jsonify, request

# app.projets ajoute la racine du projet au sys.path lors de son import (pour
# « from watcher import ») ; on l'importe donc avant watcher.
from app.projets import lister_projets, projet_par_nom
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)
from watcher import Config

# Racine du projet (dossier parent du package app/) : watcher.py et le dossier
# configs/ y vivent.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent


# ─── Gestion du processus watcher ────────────────────────────────────────────

def chemin_pid(cfg: Config) -> Path:
    return cfg.fichier_log.parent / f"watcher-{cfg.nom}.pid"


def watcher_actif(cfg: Config) -> tuple[bool, int | None]:
    """Retourne (actif, pid). Consulte le fichier PID et vérifie que le
    processus existe encore (os.kill(pid, 0) ne tue pas, il sonde)."""
    pid_file = chemin_pid(cfg)
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)   # lève OSError si le processus est mort
        return True, pid
    except (OSError, ProcessLookupError, ValueError):
        return False, None


def demarrer_watcher(cfg: Config, forcer: bool = True) -> tuple[bool, int]:
    """Lance (ou relance) le watcher du projet.
    Si forcer=False et qu'un watcher tourne déjà, retourne (False, pid_existant).
    Si forcer=True, arrête l'existant avant de redémarrer.
    Retourne (redemarré, pid)."""
    actif, pid_ancien = watcher_actif(cfg)
    if actif and not forcer:
        return False, pid_ancien

    if actif and pid_ancien:
        try:
            os.kill(pid_ancien, signal.SIGTERM)
            time.sleep(0.8)
        except OSError:
            pass

    pid_file = chemin_pid(cfg)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    conf_file      = DOSSIER_SCRIPT / "configs" / f"{cfg.nom}.conf"
    watcher_script = DOSSIER_SCRIPT / "watcher.py"

    proc = subprocess.Popen(
        [sys.executable, str(watcher_script), "--config", str(conf_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid_file.write_text(str(proc.pid))
    return True, proc.pid


def arreter_watcher(cfg: Config) -> tuple[bool, str]:
    """Arrête le watcher du projet via SIGTERM.
    Retourne (succès, message)."""
    actif, pid = watcher_actif(cfg)
    if not actif:
        return False, "watcher déjà inactif"
    try:
        os.kill(pid, signal.SIGTERM)
        chemin_pid(cfg).unlink(missing_ok=True)
        return True, f"watcher arrêté (pid {pid})"
    except OSError as e:
        return False, str(e)


# ─── Routes Flask ──────────────────────────────────────────────────────────────

def watchers():
    """Retourne le statut de tous les projets disponibles."""
    resultat = []
    for cfg in lister_projets():
        actif, pid = watcher_actif(cfg)
        resultat.append({
            "nom":   cfg.nom,
            "depot": cfg.depot,
            "actif": actif,
            "pid":   pid,
        })
    return jsonify(resultat)


def lancer_watcher():
    """Lance ou relance le watcher du projet.
    relancer=true → redémarre même s'il tourne déjà.
    relancer=false → démarre seulement s'il est inactif."""
    data    = request.json or {}
    cfg     = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    forcer  = data.get("relancer", True)
    try:
        redemarré, pid = demarrer_watcher(cfg, forcer=forcer)
        return jsonify(succes=True, pid=pid, redemarré=redemarré)
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))


def arreter_watcher_route():
    """Arrête le watcher du projet."""
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    ok, msg = arreter_watcher(cfg)
    return jsonify(succes=ok, message=msg)


def statut(nom_projet):
    """Indique si le watcher de ce projet est en cours d'exécution."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(actif=False)
    actif, pid = watcher_actif(cfg)
    return jsonify(actif=actif, pid=pid)

"""Gestion des processus watcher du bridge (un watcher par projet).

Extraite de new_issue.py à l'étape 6 du refactoring modulaire. Regroupe le
cycle de vie des watchers : démarrage, arrêt, détection du PID et les routes
Flask associées à l'onglet « Watchers » de l'interface.

Démarrage/arrêt via systemd --user (issue #596) : demarrer_watcher()/
arreter_watcher() appellent `systemctl --user start|restart|stop
watcher@<projet>` (unité définie dans systemd/watcher@.service, installée par
installer_services.sh) plutôt que de gérer le process directement
(subprocess.Popen / SIGTERM), pour survivre à un crash (Restart=on-failure)
et à un redémarrage du ThinkPad. watcher_actif() reste basé sur le fichier PID
(logs/watcher-<nom>.pid) — désormais publié par watcher.py lui-même à son
démarrage, quel que soit son mode de lancement (terminal, systemd, ou cet
appel) — ce qui laisse inchangés les autres consommateurs de ce fichier
(watcher.py::detecter_conflit_watcher/_compter_watchers_actifs,
app.interruption.interrompre_linux).
"""

import os
import subprocess
import time
from pathlib import Path

from flask import jsonify, request

# app.projets ajoute la racine du projet au sys.path lors de son import (pour
# « from watcher import ») ; on l'importe donc avant watcher.
from app.projets import lister_projets, projet_par_nom
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)
from watcher import Config


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


def demarrer_watcher(cfg: Config, forcer: bool = True) -> tuple[bool, int | None]:
    """Lance (ou relance) le watcher du projet via `systemctl --user`
    (issue #596). Si forcer=False et qu'un watcher tourne déjà, retourne
    (False, pid_existant) sans y toucher. Si forcer=True, l'unité est
    redémarrée (démarrée si elle était éteinte) — `systemctl restart`
    fonctionne aussi bien sur une unité déjà active qu'inactive.
    Retourne (redemarré, pid) ; pid peut être None si watcher.py n'a pas
    encore publié son fichier PID au terme du court sondage ci-dessous
    (démarrage anormalement lent), sans que ce soit un échec pour autant."""
    actif, pid_ancien = watcher_actif(cfg)
    if actif and not forcer:
        return False, pid_ancien

    unite  = f"watcher@{cfg.nom}"
    action = "restart" if actif else "start"
    subprocess.run(["systemctl", "--user", action, unite],
                    check=True, capture_output=True, text=True, timeout=15)

    # watcher.py publie son PID dès son démarrage (issue #596) — court
    # sondage pour laisser à systemd + Python le temps de le faire.
    pid_file = chemin_pid(cfg)
    for _ in range(30):
        if pid_file.exists():
            try:
                return True, int(pid_file.read_text().strip())
            except ValueError:
                pass
        time.sleep(0.1)
    return True, None


def arreter_watcher(cfg: Config) -> tuple[bool, str]:
    """Arrête le watcher du projet via `systemctl --user stop` (issue #596) —
    un arrêt délibéré de ce point de vue pour systemd, qui ne déclenche donc
    jamais `Restart=on-failure` de watcher@<projet>.service (à la différence
    d'un SIGKILL externe, cf. app.interruption._neutraliser_relance_systemd).
    Retourne (succès, message)."""
    actif, pid = watcher_actif(cfg)
    if not actif:
        return False, "watcher déjà inactif"
    unite = f"watcher@{cfg.nom}"
    try:
        subprocess.run(["systemctl", "--user", "stop", unite],
                        check=True, capture_output=True, text=True, timeout=15)
    except subprocess.CalledProcessError as e:
        return False, (e.stderr or str(e)).strip()
    except subprocess.TimeoutExpired:
        return False, "délai dépassé (systemctl --user stop)"
    chemin_pid(cfg).unlink(missing_ok=True)
    return True, f"watcher arrêté (pid {pid})"


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

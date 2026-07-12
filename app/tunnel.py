"""Gestion du tunnel cloudflared (mode --externe) du bridge.

Extraite de new_issue.py à l'étape 5 du refactoring modulaire. En mode
--externe, new_issue.py démarre lui-même le tunnel cloudflared
(« cloudflared tunnel run bridge-agent ») au lancement et l'arrête proprement
à la fermeture (Ctrl+C / SIGTERM ou bouton « Quitter »). Plus besoin de le
lancer à la main dans un terminal séparé.
"""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# Racine du projet (dossier parent du package app/).
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent

URL_TUNNEL = "https://bridge.frederiqueferette.be"

# Instance Flask détentrice de app.config['PROC_TUNNEL']. Mémorisée par
# demarrer_tunnel() pour qu'arreter_tunnel() retrouve le processus hors
# contexte de requête (gestionnaire de signal). Reste None en mode local
# (le tunnel n'est jamais démarré) : arreter_tunnel() y est alors sans effet.
_app = None


def demarrer_tunnel(app_instance):
    """Vérifie l'installation de cloudflared et sa config, puis lance le tunnel
    bridge-agent en arrière-plan (stdout/stderr silencieux sauf erreur). Stocke
    le processus dans app.config['PROC_TUNNEL']. Termine le programme (exit 1)
    avec un message clair si un prérequis manque ou si le tunnel meurt
    immédiatement au démarrage."""
    global _app
    _app = app_instance

    # 1) cloudflared doit être installé.
    if shutil.which("cloudflared") is None:
        print("Erreur : cloudflared est introuvable (which cloudflared).")
        print("Installez cloudflared avant d'utiliser --externe.")
        sys.exit(1)

    # 2) La configuration du tunnel (~/.cloudflared/config.yml) doit exister.
    config_tunnel = Path.home() / ".cloudflared" / "config.yml"
    if not config_tunnel.exists():
        print(f"Erreur : configuration cloudflared introuvable : {config_tunnel}")
        print("Configurez le tunnel cloudflared avant d'utiliser --externe.")
        sys.exit(1)

    # 3) Lancement silencieux (sortie capturée, affichée seulement en cas d'échec).
    proc_tunnel = subprocess.Popen(
        ["cloudflared", "tunnel", "run", "bridge-agent"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 4) Laisse 2 s au tunnel pour s'établir, puis vérifie qu'il est vivant.
    time.sleep(2)
    if proc_tunnel.poll() is not None:
        try:
            err = proc_tunnel.stderr.read().decode("utf-8", "replace") if proc_tunnel.stderr else ""
        except Exception:
            err = ""
        print("Erreur : le tunnel cloudflared s'est arrêté immédiatement.")
        if err.strip():
            print(err.strip())
        sys.exit(1)

    app_instance.config["PROC_TUNNEL"] = proc_tunnel
    print(f"Tunnel cloudflared démarré (pid {proc_tunnel.pid})")
    print(f"URL : {URL_TUNNEL}")


def arreter_tunnel():
    """Arrête proprement le tunnel cloudflared s'il a été démarré et tourne
    encore. Sans effet si aucun tunnel n'est actif (mode local ou déjà arrêté).
    Fonctionne hors contexte de requête (gestionnaire de signal) en accédant
    à app.config via l'instance mémorisée par demarrer_tunnel()."""
    if _app is None:
        return
    proc_tunnel = _app.config.get("PROC_TUNNEL")
    if proc_tunnel is not None and proc_tunnel.poll() is None:
        try:
            proc_tunnel.terminate()
            proc_tunnel.wait(timeout=3)
        except Exception:
            pass
        print("Tunnel cloudflared arrêté.")

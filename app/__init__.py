"""Package application du bridge inter-agents.

Fabrique create_app() : instancie Flask et pose l'état partagé dans app.config
(lu à la requête, jamais figé à l'import). Voir app/etat.py pour les accesseurs.
"""

import os
from pathlib import Path

from flask import Flask

# Racine du projet (dossier parent du package app/). Les gabarits et fichiers
# statiques (extraits à l'étape 1 du refactoring) vivent à la racine, pas dans
# app/ : on pointe Flask explicitement vers ces dossiers.
RACINE = Path(__file__).resolve().parent.parent


def create_app() -> Flask:
    """Instancie l'application Flask et initialise l'état partagé.

    N'enregistre encore aucun blueprint : les routes sont ajoutées ailleurs
    (new_issue.py) durant cette étape du refactoring. L'état partagé mutable
    est stocké dans app.config et lu à la requête via app/etat.py — jamais figé
    à l'import sous forme de variable globale de module.
    """
    app = Flask(
        __name__,
        template_folder=str(RACINE / "templates"),
        static_folder=str(RACINE / "static"),
    )

    # Clé de signature des cookies de session régénérée à chaque démarrage : les
    # sessions ne survivent pas à un redémarrage (acceptable) mais la clé n'est
    # jamais figée dans le code source — un cookie session['authentifie'] ne peut
    # donc pas être forgé à partir du dépôt.
    app.config["SECRET_KEY"] = os.urandom(32)

    # État partagé (anciennes variables globales de new_issue.py).
    app.config["MODE_EXTERNE"]   = False   # login exigé uniquement en --externe
    app.config["MOT_DE_PASSE"]   = ""      # hash sha256 chargé au démarrage
    app.config["ARRET_DEMANDE"]  = False   # positionné par un signal / le bouton Quitter
    app.config["LAST_HEARTBEAT"] = 0.0     # horodatage du dernier heartbeat reçu
    app.config["HEARTBEAT_RECU"] = False   # aucune surveillance tant qu'aucun heartbeat
    app.config["PROC_TUNNEL"]    = None    # processus cloudflared (mode --externe)

    return app

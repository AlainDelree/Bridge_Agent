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
    """Instancie l'application Flask, initialise l'état partagé et enregistre
    toutes les routes. Retourne l'application complètement configurée.

    L'état partagé mutable est stocké dans app.config et lu à la requête via
    app/etat.py — jamais figé à l'import sous forme de variable globale de
    module. Les routes sont enregistrées via app.add_url_rule() ci-dessous :
    les décorateurs @login_requis sont appliqués aux routes protégées.
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

    _enregistrer_routes(app)
    return app


def _enregistrer_routes(app: Flask) -> None:
    """Importe les modules de routes et les enregistre sur l'application.

    Les imports sont différés ici (plutôt qu'en tête de module) pour éviter les
    imports circulaires : ces modules font « from app import etat / create_app »,
    ce qui ne fonctionne qu'une fois le package app initialisé.
    """
    from app.auth import login_requis, login, login_post, logout
    from app.projets import get_config, post_config
    from app.watchers import (watchers, lancer_watcher,
                              arreter_watcher_route, statut)
    from app.issues import (apercu, envoyer, issues_liste, issue_detail,
                            issues_en_attente, annuler_issue, fermer_issue)
    from app.journal import journal
    from app.cycle_vie import heartbeat, events, quitter
    from app.vues import index

    app.add_url_rule("/login", "login", login, methods=["GET"])
    app.add_url_rule("/login", "login_post", login_post, methods=["POST"])
    app.add_url_rule("/logout", "logout", logout)
    app.add_url_rule("/", "index", login_requis(index))
    app.add_url_rule("/apercu", "apercu", login_requis(apercu), methods=["POST"])
    app.add_url_rule("/envoyer", "envoyer", login_requis(envoyer), methods=["POST"])
    app.add_url_rule("/journal/<nom_projet>", "journal", login_requis(journal))
    app.add_url_rule("/issues-liste/<nom_projet>", "issues_liste", login_requis(issues_liste))
    app.add_url_rule("/issue/<nom_projet>/<numero>", "issue_detail", login_requis(issue_detail))
    app.add_url_rule("/issues-en-attente/<nom_projet>", "issues_en_attente", login_requis(issues_en_attente))
    app.add_url_rule("/annuler-issue/<nom_projet>/<numero>", "annuler_issue", login_requis(annuler_issue), methods=["POST"])
    app.add_url_rule("/fermer-issue/<nom_projet>/<numero>", "fermer_issue", login_requis(fermer_issue), methods=["POST"])
    app.add_url_rule("/config/<nom_projet>", "get_config", login_requis(get_config), methods=["GET"])
    app.add_url_rule("/config/<nom_projet>", "post_config", login_requis(post_config), methods=["POST"])
    app.add_url_rule("/watchers", "watchers", login_requis(watchers))
    app.add_url_rule("/lancer-watcher", "lancer_watcher", login_requis(lancer_watcher), methods=["POST"])
    app.add_url_rule("/arreter-watcher", "arreter_watcher_route", login_requis(arreter_watcher_route), methods=["POST"])
    app.add_url_rule("/statut/<nom_projet>", "statut", login_requis(statut))
    app.add_url_rule("/heartbeat", "heartbeat", heartbeat, methods=["POST"])
    app.add_url_rule("/events", "events", login_requis(events))
    app.add_url_rule("/quitter", "quitter", login_requis(quitter), methods=["POST"])

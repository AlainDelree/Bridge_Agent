#!/usr/bin/env python3
"""
new_issue.py — Interface web de création d'issues pour le bridge inter-agents.
Lit les configs configs/*.conf, propose un formulaire pour chaque projet.

Usage :
    python3 new_issue.py                  # mode local (127.0.0.1, HTTP, sans SSL)
    python3 new_issue.py --externe        # exposition réseau (0.0.0.0, HTTPS + mdp)
    python3 new_issue.py --port 5100
    python3 new_issue.py --no-browser

Ce fichier ne contient que le point d'entrée CLI : parsing des arguments,
création de l'application via app.create_app() (qui enregistre lui-même toutes
les routes), démarrage du serveur et gestion propre de l'arrêt. Toute la logique
métier vit dans le package app/ (auth, watchers, issues, journal, cycle_vie,
vues, projets, tunnel).
"""

import argparse
import getpass
import hashlib
import os
import signal
import sys
import webbrowser
from pathlib import Path
from threading import Thread, Timer

# Fabrique de l'application (routes incluses) et accesseurs à l'état partagé.
from app import create_app, etat
from app.tunnel import demarrer_tunnel, arreter_tunnel
from app.cycle_vie import surveiller_heartbeat

DOSSIER_SCRIPT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(
        description="Interface web de création d'issues — Bridge Agent"
    )
    parser.add_argument("--port", type=int, default=5100,
                        help="Port du serveur web (défaut : 5100)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Ne pas ouvrir le navigateur automatiquement")
    parser.add_argument("--set-password", action="store_true",
                        help="Génère le hash sha256 d'un mot de passe à copier "
                             "dans le .conf, puis quitte sans démarrer le serveur")
    parser.add_argument("--externe", action="store_true",
                        help="Exposition réseau (accès distant via tunnel) : "
                             "host 0.0.0.0 + HTTPS + mot de passe obligatoire. "
                             "Sans cette option : mode local (127.0.0.1, HTTP, "
                             "sans SSL)")
    args = parser.parse_args()

    # Utilitaire : génération du hash du mot de passe d'accès (ne démarre pas le
    # serveur). Le mot de passe est demandé deux fois pour confirmation et n'est
    # jamais affiché ni stocké en clair — seul le hash sha256 est produit.
    if args.set_password:
        mp1 = getpass.getpass("Nouveau mot de passe : ")
        mp2 = getpass.getpass("Confirmez le mot de passe : ")
        if not mp1:
            print("Mot de passe vide — abandon.")
            sys.exit(1)
        if mp1 != mp2:
            print("Les deux saisies diffèrent — abandon.")
            sys.exit(1)
        hache = hashlib.sha256(mp1.encode("utf-8")).hexdigest()
        print("\nCopiez cette ligne dans configs/bridge_agent.conf :\n")
        print(f"MOT_DE_PASSE = {hache}")
        sys.exit(0)

    # Création de l'application Flask (routes enregistrées par create_app) et
    # chargement de l'état initial.
    app = create_app()
    app.config["MOT_DE_PASSE"] = etat.charger_mot_de_passe()

    # Deux modes de fonctionnement :
    #   • local (défaut)      : host 127.0.0.1, HTTP simple, sans SSL. Destiné à
    #     un usage sur place (devant le ThinkPad) — pas d'exposition réseau. Le
    #     mot de passe n'est PAS requis (mais reste appliqué s'il est configuré,
    #     via le décorateur @login_requis : aucune régression en mode local).
    #   • externe (--externe) : host 0.0.0.0, HTTPS + mot de passe OBLIGATOIRES.
    #     Destiné à l'accès distant (téléphone via tunnel).
    if args.externe:
        app.config["MODE_EXTERNE"] = True
        host   = "0.0.0.0"
        schema = "https"

        # En mode externe, refuser de démarrer si aucun mot de passe n'est
        # configuré : l'interface serait exposée au réseau sans authentification.
        if not app.config["MOT_DE_PASSE"]:
            print("Erreur : MOT_DE_PASSE non configuré.")
            print("Lancez d'abord : python3 new_issue.py --set-password")
            sys.exit(1)

        # Emplacement du certificat auto-signé (HTTPS). Généré une fois via :
        #   openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem \
        #     -out ssl/cert.pem -days 3650 -nodes -subj "/CN=bridge-agent-local"
        cert = DOSSIER_SCRIPT / "ssl" / "cert.pem"
        cle  = DOSSIER_SCRIPT / "ssl" / "key.pem"
        if not (cert.exists() and cle.exists()):
            print("Certificat SSL introuvable dans ssl/. Générez-le avec :")
            print('  openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem \\')
            print('    -out ssl/cert.pem -days 3650 -nodes -subj "/CN=bridge-agent-local"')
            sys.exit(1)
        ssl_context = (str(cert), str(cle))
    else:
        host        = "127.0.0.1"
        schema      = "http"
        ssl_context = None

    # Ctrl+C (SIGINT) ou SIGTERM : on prévient d'abord l'onglet via /events en
    # positionnant ARRET_DEMANDE, puis on laisse ~1,5 s à la connexion SSE pour
    # livrer l'event « shutdown » avant de terminer le processus.
    def gestionnaire_arret(signum, frame):
        app.config["ARRET_DEMANDE"] = True
        arreter_tunnel()
        Timer(1.5, lambda: os._exit(0)).start()

    signal.signal(signal.SIGINT, gestionnaire_arret)
    signal.signal(signal.SIGTERM, gestionnaire_arret)

    # Mode --externe : démarrage automatique du tunnel cloudflared avant
    # d'exposer le serveur. Vérifie les prérequis (cloudflared + config) et
    # quitte proprement (exit 1) en cas de problème. L'arrêt est géré par le
    # gestionnaire de signal ci-dessus et par la route /quitter.
    if args.externe:
        demarrer_tunnel(app)

    # Surveillance des heartbeats du navigateur (daemon → ne bloque jamais
    # l'arrêt du processus si le gestionnaire de signal est lent).
    Thread(target=surveiller_heartbeat, args=(app,), daemon=True).start()

    if not args.no_browser:
        Timer(1.2, lambda: webbrowser.open(f"{schema}://localhost:{args.port}")).start()

    print(f"Bridge Agent — interface web sur {schema}://localhost:{args.port}"
          f" ({'externe' if args.externe else 'local'})")
    print("Ctrl-C pour arrêter.")
    app.run(
        host=host,
        port=args.port,
        ssl_context=ssl_context,
        threaded=True,
        debug=False,
    )


if __name__ == "__main__":
    main()

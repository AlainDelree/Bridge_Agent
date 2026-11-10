#!/usr/bin/env python3
"""
new_issue.py — Interface web de création d'issues pour le bridge inter-agents.
Lit les configs configs/*.conf, propose un formulaire pour chaque projet.

Usage :
    python3 new_issue.py                  # mode local (127.0.0.1, HTTP, sans SSL)
    python3 new_issue.py --lan            # accès réseau local (0.0.0.0, HTTP, mdp obligatoire)
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
import logging
import os
import signal
import sys
import webbrowser
from pathlib import Path
from threading import Thread, Timer

# Fabrique de l'application (routes incluses) et accesseurs à l'état partagé.
from app import create_app, etat
import etat_son_issue
from app.tunnel import demarrer_tunnel, arreter_tunnel
from app.cycle_vie import surveiller_heartbeat
from app.notifications_poller import surveiller_transitions
from app.watchers import surveiller_redemarrages_differes
from app.issues_inbox import (watcher_inbox_actif, demarrer_watcher_inbox,
                              arreter_watcher_inbox)
from etat_cases_cochees import nettoyer_anciennes as nettoyer_cases_cochees
from watcher import nettoyer_verrous_perimes, tenter_maj_auto_demarrage, forcer_utf8
from mesure_charge_interface import demarrer_echantillonnage

DOSSIER_SCRIPT = Path(__file__).resolve().parent

# Requêtes HTTP ignorées du journal d'accès werkzeug quand new_issue.py tourne
# sous le superviseur de session Windows (issue #875, point 3) : le superviseur
# recopie EN CONTINU stdout/stderr vers logs\new_issue-session.log (voir
# surveiller_processus_session.ps1), donc CHAQUE requête — dont /heartbeat,
# sondé par le navigateur toutes les quelques secondes, et les fichiers
# statiques — y ajoutait une ligne sans jamais s'arrêter. Ne change rien sous
# Linux ni pour lancer_new_issue.sh (ni l'un ni l'autre ne posent la variable
# d'environnement ci-dessous) : seul le superviseur Windows l'active.
_MOTIFS_REQUETES_SILENCIEUSES = ('"GET /heartbeat', '"GET /static/')


class _FiltreRequetesBruyantes(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        return not any(motif in message for motif in _MOTIFS_REQUETES_SILENCIEUSES)


def _filtrer_requetes_bruyantes_si_sous_superviseur() -> None:
    if os.environ.get("BRIDGE_SOUS_SUPERVISEUR_SESSION"):
        logging.getLogger("werkzeug").addFilter(_FiltreRequetesBruyantes())


# Niveau de bandeau (classes CSS .bandeau-eval-windows existantes, issue
# #741) associé à chaque statut de tenter_maj_auto_demarrage() (issue #868).
_NIVEAU_MAJ_AUTO_DEPOT = {"maj": "gris", "a_jour": "gris", "ignore": "orange", "echec": "rouge"}


def _formater_message_maj_auto_depot(resultat: dict) -> str | None:
    """Message humain à afficher (console + bandeau de l'interface) pour le
    résultat d'une tentative de mise à jour automatique du dépôt au
    démarrage (issue #868, `watcher.tenter_maj_auto_demarrage`). None si la
    fonctionnalité est désactivée (réglage absent — cas par défaut, aucun
    message, comportement inchangé pour les installations existantes
    d'Alain). Rien n'est jamais silencieux dans les autres cas : chaque
    statut (à jour, mis à jour, ignoré, échec) produit un message explicite,
    avec sa raison pour « ignoré »/« échec » et la liste des fichiers changés
    pour « mis à jour » — accompagné du rappel que les watchers déjà
    démarrés tournent encore sur l'ancien code tant qu'ils ne sont pas
    relancés."""
    statut = resultat.get("statut")
    message = resultat.get("message")
    if statut == "desactive":
        return None
    prefixe = "Mise à jour automatique du dépôt de l'outil (MAJ_AUTO_DEPOT)"
    if statut == "a_jour":
        return f"{prefixe} : déjà à jour."
    if statut == "maj":
        fichiers = resultat.get("fichiers") or []
        detail = f" — {len(fichiers)} fichier(s) modifié(s) : {', '.join(fichiers)}" if fichiers else ""
        return (f"{prefixe} : mis à jour ({message}){detail}. Les watchers déjà démarrés "
                "utilisent encore l'ancien code tant qu'ils ne sont pas relancés.")
    if statut == "ignore":
        return f"{prefixe} : ignorée — {message}."
    return f"{prefixe} : échec — {message}."


def _mode_reseau(args) -> tuple[str, str, bool]:
    """Détermine (host, schema, acces_reseau) à partir des arguments CLI,
    sans aucun effet de bord (testable sans démarrer de serveur). --lan et
    --externe écoutent tous deux au-delà de 127.0.0.1 (issue #831)."""
    if args.lan:
        return "0.0.0.0", "http", True
    if args.externe:
        return "0.0.0.0", "https", True
    return "127.0.0.1", "http", False


def _erreur_mot_de_passe_manquant(acces_reseau: bool, mot_de_passe: str) -> str | None:
    """None si le démarrage peut continuer, sinon le message d'erreur à
    afficher avant sys.exit(1) : --lan et --externe exigent tous deux un mot
    de passe configuré dès que l'écoute dépasse 127.0.0.1 (issue #831)."""
    if acces_reseau and not mot_de_passe:
        return ("Erreur : MOT_DE_PASSE non configuré.\n"
                "Lancez d'abord : python3 new_issue.py --set-password")
    return None


def main():
    # Sous le superviseur de session Windows (provisioning/windows/
    # surveiller_processus_session.ps1), stdout/stderr sont redirigés vers un
    # fichier : sans ce forçage, la console Windows encode par défaut en
    # cp1252, qui ne sait pas écrire les flèches/symboles (ex. « → » du
    # message de mise à jour automatique du dépôt, plus bas) — UnicodeEncode
    # Error qui arrêtait tout new_issue.py en plein `print()` (issue #875). Le
    # superviseur pose lui-même PYTHONUTF8/PYTHONIOENCODING dans
    # l'environnement du process avant de le lancer ; cet appel est une
    # seconde protection, indépendante de l'environnement (utile aussi en
    # lancement manuel depuis une console cp1252). Inoffensif sous Linux
    # (stdout déjà en UTF-8) — voir watcher.forcer_utf8 (issue #698).
    forcer_utf8(sys.stdout)
    forcer_utf8(sys.stderr)

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
    parser.add_argument("--lan", action="store_true",
                        help="Accès réseau local uniquement : host 0.0.0.0, "
                             "HTTP, mot de passe OBLIGATOIRE (circule en "
                             "clair sur le réseau local, HTTP non chiffré), "
                             "sans tunnel Cloudflare. Destiné à un LAN de "
                             "confiance (ex. PC fixe Windows sur le même "
                             "réseau). Incompatible avec --externe.")
    args = parser.parse_args()

    if args.lan and args.externe:
        print("Erreur : --lan et --externe sont incompatibles.")
        sys.exit(1)

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

    # Mise à jour automatique FACULTATIVE du dépôt de l'outil au lancement
    # (issue #868) — équivalent, pour une installation locale sans service
    # CCW, du rafraîchissement que le watcher fait lui-même en début de
    # cycle (watcher.rafraichir_depot, issue #185). Désactivée par défaut
    # (réglage MAJ_AUTO_DEPOT absent de identite_locale.conf, issue #859) :
    # dans ce cas tenter_maj_auto_demarrage() ne lance AUCUNE commande git et
    # renvoie {"statut": "desactive"}, donc aucun message ici — comportement
    # strictement inchangé pour les installations existantes d'Alain
    # (ThinkPad, PC fixe). Jamais bloquant (délai court, --ff-only) ; rien
    # n'est silencieux : le résultat est à la fois affiché ici (capturé dans
    # logs/new_issue-session.log par le superviseur de démarrage Windows,
    # provisioning/windows/installer_demarrage_session.ps1) et exposé dans
    # app.config pour le bandeau d'état de l'interface (app/vues.py,
    # templates/fragments/bandeaux.html).
    _resultat_maj_depot = tenter_maj_auto_demarrage()
    _message_maj_depot = _formater_message_maj_auto_depot(_resultat_maj_depot)
    if _message_maj_depot:
        print(_message_maj_depot)
    app.config["MAJ_AUTO_DEPOT"] = (
        {
            "statut": _resultat_maj_depot.get("statut"),
            "message": _message_maj_depot,
            "niveau": _NIVEAU_MAJ_AUTO_DEPOT.get(_resultat_maj_depot.get("statut"), "gris"),
        }
        if _message_maj_depot else None
    )

    # Nettoyage de l'état des cases cochées « traité/lu » (issue #629) :
    # purement local, AUCUN appel GitHub — retire, pour chaque projet, les
    # coches devenues invisibles (numéro trop ancien pour pouvoir encore
    # apparaître dans la liste Résultats de ce projet).
    _ok_cases, _nb_cases, _erreur_cases = nettoyer_cases_cochees()
    if not _ok_cases:
        print(f"⚠️  Nettoyage des cases cochées (issue #629) impossible : {_erreur_cases}")

    # Nettoyage du choix de son par issue (issue #630) : même règle que les
    # cases cochées — purge, projet par projet, des entrées dont le numéro
    # est ≤ (plus grand numéro connu du projet − 50). Best-effort
    # (etat_son_issue ne lève jamais), ne doit jamais empêcher le démarrage.
    etat_son_issue.nettoyer_entrees_perimees()

    # Nettoyage des verrous de watchers périmés (issue #751) : logs/verrous/
    # accumulait des verrous désignant des process disparus (ou zombies,
    # cf. #748) qu'il fallait jusqu'ici retirer à la main avant un
    # redémarrage. Best-effort strict, rien n'est jamais affiché dans
    # l'interface (seulement journalisé) ; ne touche jamais aux worktrees ni
    # aux dossiers de travail — uniquement aux fichiers de verrou eux-mêmes.
    nettoyer_verrous_perimes()

    # Trois modes de fonctionnement :
    #   • local (défaut)      : host 127.0.0.1, HTTP simple, sans SSL. Destiné à
    #     un usage sur place (devant le ThinkPad) — pas d'exposition réseau. Le
    #     mot de passe n'est PAS requis (mais reste appliqué s'il est configuré,
    #     via le décorateur @login_requis : aucune régression en mode local).
    #   • LAN (--lan)         : host 0.0.0.0, HTTP simple, sans SSL, sans tunnel
    #     Cloudflare, mot de passe OBLIGATOIRE (ACCES_RESEAU=True, donc
    #     @login_requis l'exige — cf. app/auth.py, issue #831). Accès confiné
    #     au réseau local (ex. PC fixe Windows) ; rien n'est exposé vers
    #     l'extérieur. Le mot de passe circule néanmoins EN CLAIR sur ce réseau
    #     local (HTTP non chiffré) — risque connu, non résolu par cette issue.
    #   • externe (--externe) : host 0.0.0.0, HTTPS + mot de passe OBLIGATOIRES.
    #     Destiné à l'accès distant (téléphone via tunnel).
    host, schema, acces_reseau = _mode_reseau(args)
    app.config["ACCES_RESEAU"] = acces_reseau

    erreur_mdp = _erreur_mot_de_passe_manquant(acces_reseau, app.config["MOT_DE_PASSE"])
    if erreur_mdp:
        print(erreur_mdp)
        sys.exit(1)

    if args.externe:
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
        ssl_context = None

    # Ctrl+C (SIGINT) ou SIGTERM : on prévient d'abord l'onglet via /events en
    # positionnant ARRET_DEMANDE, puis on laisse ~1,5 s à la connexion SSE pour
    # livrer l'event « shutdown » avant de terminer le processus.
    def gestionnaire_arret(signum, frame):
        app.config["ARRET_DEMANDE"] = True
        arreter_tunnel()
        # Cycle de vie du watcher spool issues_inbox lié à celui de new_issue.py
        # (issue #496) : à l'arrêt, on coupe systématiquement le watcher spool,
        # que son démarrage courant soit l'auto-démarrage ci-dessous ou une
        # relance manuelle (override) faite entre-temps depuis le panneau
        # Infrastructure — même mécanisme que le bouton ⏹ Arrêter existant.
        arreter_watcher_inbox()
        Timer(1.5, lambda: os._exit(0)).start()

    signal.signal(signal.SIGINT, gestionnaire_arret)
    signal.signal(signal.SIGTERM, gestionnaire_arret)

    # Démarrage automatique du watcher spool issues_inbox (issue #496) : son
    # cycle de vie suit désormais celui de new_issue.py lui-même (tous modes
    # confondus — local/LAN/externe), plutôt qu'une durée choisie
    # manuellement. S'il tourne déjà (ex. laissé actif par une session
    # précédente qui a planté, ou une manip manuelle avant ce démarrage), on
    # ne touche à rien : demarrer_watcher_inbox() redémarre TOUJOURS le
    # processus existant (issue #485), ce qui couperait inutilement un
    # watcher déjà en cours. Les boutons manuels ▶ Démarrer / ↺ Relancer /
    # ⏹ Arrêter du panneau Infrastructure restent utilisables ensuite comme
    # override pendant que new_issue.py tourne.
    if not watcher_inbox_actif()[0]:
        demarrer_watcher_inbox()

    # Mode --externe : démarrage automatique du tunnel cloudflared avant
    # d'exposer le serveur. Vérifie les prérequis (cloudflared + config) et
    # quitte proprement (exit 1) en cas de problème. L'arrêt est géré par le
    # gestionnaire de signal ci-dessus et par la route /quitter.
    if args.externe:
        demarrer_tunnel(app)

    # Surveillance des heartbeats du navigateur (daemon → ne bloque jamais
    # l'arrêt du processus si le gestionnaire de signal est lent).
    Thread(target=surveiller_heartbeat, args=(app,), daemon=True).start()

    # Détection serveur des transitions d'issues (issue #187) : polling GitHub
    # périodique qui déclenche bip/notify-send/ntfy sur le ThinkPad pour toute
    # issue fermée (succès) ou marquée needs-human (échec), y compris celles
    # traitées par le PC Windows (CCW) — sans aucun appel réseau depuis le PC CCW.
    # Daemon → n'empêche jamais l'arrêt du processus. Désactivable via
    # BRIDGE_NOTIF_SCOPE=off.
    Thread(target=surveiller_transitions, daemon=True).start()

    # Exécution des redémarrages de watcher différés (issue #609) : un
    # redémarrage forcé demandé (« Enregistrer et relancer », relances
    # manuelles) pendant qu'une tâche est en cours n'est jamais exécuté tout
    # de suite (cf. app.watchers.demarrer_watcher_ou_differer) — ce thread
    # sonde périodiquement et l'exécute dès la fin de la tâche. Daemon →
    # n'empêche jamais l'arrêt du processus.
    Thread(target=surveiller_redemarrages_differes, daemon=True).start()

    # Échantillonneur continu de charge de l'interface (issue #835 point 3) :
    # une ligne JSON par minute dans logs/charge_interface.log (CPU serveur +
    # fils, requêtes/minute). Daemon → s'arrête avec le serveur ; ne doit
    # jamais retarder le démarrage (démarrage du thread lui-même instantané,
    # la boucle ne fait rien avant sa première minute écoulée).
    demarrer_echantillonnage()

    _filtrer_requetes_bruyantes_si_sous_superviseur()

    if not args.no_browser:
        Timer(1.2, lambda: webbrowser.open(f"{schema}://localhost:{args.port}")).start()

    mode_label = "externe" if args.externe else ("lan" if args.lan else "local")
    print(f"Bridge Agent — interface web sur {schema}://localhost:{args.port}"
          f" ({mode_label})")
    if args.lan:
        print(f"Accessible depuis le réseau local sur {schema}://<IP-de-cette-machine>:{args.port}"
              " — mot de passe obligatoire (circule en clair, HTTP non chiffré).")
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

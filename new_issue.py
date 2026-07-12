#!/usr/bin/env python3
"""
new_issue.py — Interface web de création d'issues pour le bridge inter-agents.
Lit les configs configs/*.conf, propose un formulaire pour chaque projet.

Usage :
    python3 new_issue.py                  # mode local (127.0.0.1, HTTP, sans SSL)
    python3 new_issue.py --externe        # exposition réseau (0.0.0.0, HTTPS + mdp)
    python3 new_issue.py --port 5100
    python3 new_issue.py --no-browser
"""

import argparse
import getpass
import hashlib
import os
import signal
import sys
import time
import webbrowser
from pathlib import Path
from threading import Thread, Timer

from flask import (Response, current_app, jsonify, render_template,
                   request, stream_with_context)

# Partage du lecteur de config avec watcher.py (même dossier).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from watcher import Config, charger_config  # noqa: E402

# Fabrique de l'application et accesseurs à l'état partagé (app.config).
from app import create_app, etat  # noqa: E402

# Fonctions liées aux projets (extraites à l'étape 3 du refactoring).
from app.projets import (lister_projets, projet_par_nom,  # noqa: E402
                         sauvegarder_conf, CLES_EDITABLES)

# Authentification : décorateur + routes login/logout (extraits à l'étape 4).
from app.auth import login_requis, login, login_post, logout  # noqa: E402,F401

# Gestion du tunnel cloudflared (extraite à l'étape 5 du refactoring).
from app.tunnel import URL_TUNNEL, demarrer_tunnel, arreter_tunnel  # noqa: E402,F401

# Gestion des watchers : cycle de vie + routes (extraite à l'étape 6).
from app.watchers import (chemin_pid, watcher_actif,  # noqa: E402,F401
                          demarrer_watcher, arreter_watcher, watchers,
                          lancer_watcher, arreter_watcher_route, statut)

# Gestion des issues : construction body/labels + routes (extraite à l'étape 7).
from app.issues import (construire_body, construire_labels,  # noqa: E402,F401
                        apercu, envoyer, issues_liste, issue_detail,
                        issues_en_attente, annuler_issue)

DOSSIER_SCRIPT = Path(__file__).resolve().parent

# Instance Flask créée au démarrage (main) via create_app(). Déclarée ici pour
# permettre les décorateurs @app.route au niveau module — l'objet est affecté
# avant d'enregistrer les routes.
app = None


# ─── Cycle de vie serveur ↔ onglet navigateur ────────────────────────────────
# Le navigateur émet un heartbeat (POST /heartbeat) toutes les 5 s. Un thread
# daemon coupe le serveur si plus rien n'arrive pendant DELAI_HEARTBEAT_MAX s
# (onglet fermé). Dans l'autre sens, un Ctrl+C (SIGINT/SIGTERM) positionne
# l'état ARRET_DEMANDE : la route SSE /events le détecte et prévient l'onglet.
# L'état partagé (heartbeat, arrêt demandé, tunnel, mode externe, mot de passe)
# vit désormais dans app.config, lu à la requête via app/etat.py.
INTERVALLE_HEARTBEAT = 5        # période de sonde côté serveur (s)
DELAI_HEARTBEAT_MAX  = 15       # au-delà, l'onglet est considéré fermé


# CLES_EDITABLES, lister_projets(), projet_par_nom() et sauvegarder_conf() sont
# désormais dans app/projets.py (importés en tête de fichier).


# ─── Sécurité : authentification + filtrage IP ────────────────────────────────
# MAX_ECHECS_LOGIN, login_requis(), login(), login_post() et logout() sont
# désormais dans app/auth.py (importés en tête de fichier, étape 4). Le hash du
# mot de passe (MOT_DE_PASSE) et le drapeau MODE_EXTERNE vivent dans app.config :
# chargés au démarrage (main), lus à la requête via etat.get().
# charger_mot_de_passe() est dans app/etat.py.


# ─── Gestion du processus watcher ────────────────────────────────────────────
# chemin_pid(), watcher_actif(), demarrer_watcher() et arreter_watcher() sont
# désormais dans app/watchers.py (importés en tête de fichier, étape 6).


# ─── Construction du body et des labels ───────────────────────────────────────
# construire_body() et construire_labels() sont désormais dans app/issues.py
# (importés en tête de fichier, étape 7).


# ─── Routes Flask ──────────────────────────────────────────────────────────────
# login(), login_post(), logout() et le gabarit TEMPLATE_LOGIN sont désormais
# dans app/auth.py (importés en tête de fichier, étape 4). apercu() et envoyer()
# sont désormais dans app/issues.py (importés en tête de fichier, étape 7).

def index():
    return render_template("index.html", projets=lister_projets(),
                           auth_active=bool(etat.get("MOT_DE_PASSE")))


def journal(nom_projet):
    """Server-Sent Events : streame le journal du watcher en temps réel."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return Response("Projet introuvable.", status=404)
    fichier_log = cfg.fichier_log

    def generer():
        # ── 1. Les 80 dernières lignes existantes ──────────────────────────
        if fichier_log.exists():
            with open(fichier_log, "r", encoding="utf-8", errors="replace") as f:
                lignes = f.readlines()
            for l in lignes[-80:]:
                yield f"data: {l.rstrip()}\n\n"
        else:
            yield "data: (journal vide — le watcher n'a pas encore démarré)\n\n"

        # ── 2. Nouvelles lignes au fil de l'eau ────────────────────────────
        while True:
            try:
                taille = fichier_log.stat().st_size if fichier_log.exists() else 0
                with open(fichier_log, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(taille)
                    while True:
                        ligne = f.readline()
                        if ligne:
                            taille += len(ligne.encode("utf-8"))
                            yield f"data: {ligne.rstrip()}\n\n"
                        else:
                            time.sleep(0.5)
                            yield ": ping\n\n"  # keepalive (ignoré par onmessage)
                            # Vérifier si le fichier a été rotaté (taille diminuée)
                            nouvelle_taille = fichier_log.stat().st_size if fichier_log.exists() else 0
                            if nouvelle_taille < taille:
                                break  # rotation détectée → réouvrir
            except FileNotFoundError:
                time.sleep(2)
                yield ": ping\n\n"

    return Response(
        generer(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# issues_liste(), issue_detail(), issues_en_attente() et annuler_issue() sont
# désormais dans app/issues.py (importés en tête de fichier, étape 7).


def get_config(nom_projet):
    """Retourne les valeurs actuelles du .conf, relues depuis le disque à
    chaque appel (via charger_config) plutôt que depuis l'objet Config en
    mémoire. Ainsi l'onglet Configuration reflète toujours l'état réel du
    fichier, même s'il a été modifié à la main après le démarrage."""
    chemin = DOSSIER_SCRIPT / "configs" / f"{nom_projet}.conf"
    if not chemin.exists():
        return jsonify(erreur="Projet introuvable."), 404
    try:
        cfg = charger_config(chemin)
    except SystemExit as e:
        # charger_config quitte (sys.exit) si un champ requis manque ou
        # qu'un entier est mal formé : on le rattrape pour ne pas tuer
        # le serveur et renvoyer une erreur exploitable côté onglet.
        return jsonify(erreur=f"Config invalide : {e}"), 400
    return jsonify(
        nom            = cfg.nom,
        depot          = cfg.depot,
        rep_travail    = str(cfg.rep_travail),
        perimetre      = cfg.perimetre,
        cmd_backup     = cfg.cmd_backup,
        topic_ntfy     = cfg.topic_ntfy,
        label          = cfg.label,
        intervalle     = cfg.intervalle,
        max_essais     = cfg.max_essais,
        timeout_claude = cfg.timeout_claude,
        script_bip     = str(cfg.script_bip),
        fichier_contexte = cfg.fichier_contexte,
        log_taille_max_mo = cfg.log_taille_max_mo,
        log_archives   = cfg.log_archives,
        modele_ccl     = cfg.modele_ccl,
    )


def post_config(nom_projet):
    """Enregistre les clés éditables dans le .conf."""
    data = request.json or {}
    ok, msg = sauvegarder_conf(nom_projet, data)
    return jsonify(succes=ok, message=msg)


# watchers(), lancer_watcher(), arreter_watcher_route() et statut() sont
# désormais dans app/watchers.py (importés en tête de fichier, étape 6).


def heartbeat():
    """Le navigateur signale que l'onglet est toujours ouvert. Met à jour
    l'horodatage surveillé par surveiller_heartbeat()."""
    etat.set("LAST_HEARTBEAT", time.time())
    etat.set("HEARTBEAT_RECU", True)
    return jsonify(ok=True)


def events():
    """SSE dédié au cycle de vie (séparé du journal watcher).
    Envoie un keepalive toutes les 5 s ; dès qu'un signal d'arrêt a été reçu
    (ARRET_DEMANDE), émet un event « shutdown » puis ferme la connexion.
    app.config est capturé ICI (dans le contexte de requête) avant d'entrer
    dans le générateur — current_app n'est plus disponible une fois le
    générateur démarré hors contexte de requête."""
    config = current_app.config   # capturé dans le contexte de requête

    def generer():
        dernier_ping = time.time()
        while True:
            if config.get("ARRET_DEMANDE"):   # lecture directe, pas via etat.get()
                yield "event: shutdown\ndata: stop\n\n"
                return
            time.sleep(0.5)   # sonde fréquente du flag, keepalive espacé
            if time.time() - dernier_ping >= 5:
                yield ": ping\n\n"
                dernier_ping = time.time()

    return Response(
        generer(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def quitter():
    """Arrêt volontaire déclenché par le bouton « Quitter » de l'onglet.
    Positionne ARRET_DEMANDE (l'overlay /events sert de filet de sécurité si
    window.close() est bloqué), répond immédiatement, puis coupe le processus
    après 2 s — le délai laisse le navigateur recevoir la réponse et exécuter
    window.close() avant que le serveur ne disparaisse."""
    etat.set("ARRET_DEMANDE", True)

    def arret_differe():
        time.sleep(2)
        arreter_tunnel()
        os._exit(0)

    Thread(target=arret_differe, daemon=True).start()
    return jsonify(ok=True)


# ─── Point d'entrée ───────────────────────────────────────────────────────────


def surveiller_heartbeat(app_instance):
    """Thread daemon : coupe le serveur (SIGTERM sur son propre PID) si l'onglet
    navigateur a cessé d'émettre des heartbeats depuis plus de DELAI_HEARTBEAT_MAX
    secondes. Tant qu'aucun heartbeat n'a jamais été reçu (serveur qui démarre,
    ou lancé en --no-browser), aucune surveillance : on n'auto-coupe jamais un
    serveur qui n'a pas encore eu de client. L'état est lu via app.config
    (l'instance est passée au thread car on est hors contexte de requête)."""
    while True:
        time.sleep(INTERVALLE_HEARTBEAT)
        heartbeat_recu = app_instance.config.get("HEARTBEAT_RECU", False)
        last_heartbeat = app_instance.config.get("LAST_HEARTBEAT", 0.0)
        if heartbeat_recu and (time.time() - last_heartbeat) > DELAI_HEARTBEAT_MAX:
            os.kill(os.getpid(), signal.SIGTERM)
            return

def enregistrer_routes(app_instance):
    """Enregistre toutes les routes Flask sur l'instance d'application.
    Les décorateurs @login_requis sont appliqués aux routes protégées."""
    app_instance.add_url_rule("/login", "login", login, methods=["GET"])
    app_instance.add_url_rule("/login", "login_post", login_post, methods=["POST"])
    app_instance.add_url_rule("/logout", "logout", logout)
    app_instance.add_url_rule("/", "index", login_requis(index))
    app_instance.add_url_rule("/apercu", "apercu", login_requis(apercu), methods=["POST"])
    app_instance.add_url_rule("/envoyer", "envoyer", login_requis(envoyer), methods=["POST"])
    app_instance.add_url_rule("/journal/<nom_projet>", "journal", login_requis(journal))
    app_instance.add_url_rule("/issues-liste/<nom_projet>", "issues_liste", login_requis(issues_liste))
    app_instance.add_url_rule("/issue/<nom_projet>/<numero>", "issue_detail", login_requis(issue_detail))
    app_instance.add_url_rule("/issues-en-attente/<nom_projet>", "issues_en_attente", login_requis(issues_en_attente))
    app_instance.add_url_rule("/annuler-issue/<nom_projet>/<numero>", "annuler_issue", login_requis(annuler_issue), methods=["POST"])
    app_instance.add_url_rule("/config/<nom_projet>", "get_config", login_requis(get_config), methods=["GET"])
    app_instance.add_url_rule("/config/<nom_projet>", "post_config", login_requis(post_config), methods=["POST"])
    app_instance.add_url_rule("/watchers", "watchers", login_requis(watchers))
    app_instance.add_url_rule("/lancer-watcher", "lancer_watcher", login_requis(lancer_watcher), methods=["POST"])
    app_instance.add_url_rule("/arreter-watcher", "arreter_watcher_route", login_requis(arreter_watcher_route), methods=["POST"])
    app_instance.add_url_rule("/statut/<nom_projet>", "statut", login_requis(statut))
    app_instance.add_url_rule("/heartbeat", "heartbeat", heartbeat, methods=["POST"])
    app_instance.add_url_rule("/events", "events", login_requis(events))
    app_instance.add_url_rule("/quitter", "quitter", login_requis(quitter), methods=["POST"])


def main():
    global app

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

    # Création de l'application Flask et chargement de l'état initial.
    app = create_app()
    app.config["MOT_DE_PASSE"] = etat.charger_mot_de_passe()
    enregistrer_routes(app)

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

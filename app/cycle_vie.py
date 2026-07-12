"""Cycle de vie serveur ↔ onglet navigateur du bridge.

Extraite de new_issue.py à l'étape 8 du refactoring modulaire.

Le navigateur émet un heartbeat (POST /heartbeat) toutes les 5 s. Un thread
daemon coupe le serveur si plus rien n'arrive pendant DELAI_HEARTBEAT_MAX s
(onglet fermé). Dans l'autre sens, un Ctrl+C (SIGINT/SIGTERM) positionne
l'état ARRET_DEMANDE : la route SSE /events le détecte et prévient l'onglet.
L'état partagé (heartbeat, arrêt demandé, tunnel, mode externe, mot de passe)
vit dans app.config, lu à la requête via app/etat.py.
"""

import os
import signal
import time
from threading import Thread

from flask import Response, current_app, jsonify

from app import etat
from app.tunnel import arreter_tunnel

INTERVALLE_HEARTBEAT = 5        # période de sonde côté serveur (s)
DELAI_HEARTBEAT_MAX  = 15       # au-delà, l'onglet est considéré fermé


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

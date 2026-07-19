"""Cycle de vie serveur ↔ onglet navigateur du bridge.

Extraite de new_issue.py à l'étape 8 du refactoring modulaire.

Preuve de vie de l'onglet (issue #157) — deux signaux combinés :

  1. La connexion SSE /events (signal PRINCIPAL, robuste). Une connexion HTTP
     établie reste active même quand l'onglet passe en arrière-plan ; elle
     n'est PAS ralentie par le throttling des timers JS. Tant qu'au moins une
     connexion /events est ouverte, l'onglet est vivant. Sa fermeture réelle
     (onglet/fenêtre fermé) fait tomber la connexion → surveiller_heartbeat()
     coupe le serveur après un court délai.

  2. Le heartbeat POST /heartbeat toutes les 5 s (signal de repli). Historique,
     conservé pour la robustesse (si le SSE hoquette). Comme les navigateurs
     throttlent le setInterval des onglets en arrière-plan, son seuil est
     désormais GÉNÉREUX (DELAI_HEARTBEAT_MAX) pour ne plus couper à tort.

Le serveur ne s'auto-coupe que si LES DEUX signaux sont éteints. Dans l'autre
sens, un Ctrl+C (SIGINT/SIGTERM) positionne l'état ARRET_DEMANDE : la route
SSE /events le détecte et prévient l'onglet. L'état partagé vit dans
app.config, lu à la requête via app/etat.py.
"""

import os
import signal
import time
from threading import Lock, Thread

from flask import Response, current_app, jsonify

from app import diag_heartbeat   # DIAGNOSTIC TEMPORAIRE — issue #157, à retirer
from app import etat
from app.tunnel import arreter_tunnel

INTERVALLE_HEARTBEAT = 5        # période de sonde côté serveur (s)
# Seuil du heartbeat JS : généreux car ce timer est throttlé quand l'onglet est
# en arrière-plan (issue #157). Le SSE reste le garde-fou robuste.
DELAI_HEARTBEAT_MAX  = 90
# Tolérance de reconnexion SSE : une connexion /events tombée puis reprise
# (EventSource se reconnecte seul) laisse une brève fenêtre à 0 connexion.
DELAI_SSE_MAX        = 20

# Compteur de connexions SSE actives, protégé par un verrou (plusieurs threads
# de requête concurrents peuvent l'incrémenter/décrémenter — issue #157).
_lock_sse = Lock()


def _sse_connecte(config) -> int:
    """Enregistre l'ouverture d'une connexion /events. Retourne le nouveau total."""
    with _lock_sse:
        n = config.get("SSE_CONNEXIONS_ACTIVES", 0) + 1
        config["SSE_CONNEXIONS_ACTIVES"] = n
        config["SSE_DEJA_VU"] = True
        config["LAST_SSE_ACTIVITE"] = time.time()
    return n


def _sse_deconnecte(config) -> int:
    """Enregistre la fermeture d'une connexion /events. Retourne le nouveau total."""
    with _lock_sse:
        n = max(0, config.get("SSE_CONNEXIONS_ACTIVES", 0) - 1)
        config["SSE_CONNEXIONS_ACTIVES"] = n
        config["LAST_SSE_ACTIVITE"] = time.time()
    return n


def heartbeat():
    """Le navigateur signale que l'onglet est toujours ouvert. Met à jour
    l'horodatage surveillé par surveiller_heartbeat()."""
    etat.set("LAST_HEARTBEAT", time.time())
    etat.set("HEARTBEAT_RECU", True)
    diag_heartbeat.log_heartbeat()   # DIAGNOSTIC TEMPORAIRE — issue #157, à retirer
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
        # Ouverture comptabilisée comme preuve de vie (issue #157). Chaque
        # keepalive réussi rafraîchit LAST_SSE_ACTIVITE ; l'échec d'un yield
        # (onglet fermé) déclenche le finally qui décrémente le compteur.
        n = _sse_connecte(config)
        diag_heartbeat.log_sse("connexion", n)   # DIAGNOSTIC TEMPORAIRE — issue #157, à retirer
        try:
            dernier_ping = time.time()
            while True:
                if config.get("ARRET_DEMANDE"):   # lecture directe, pas via etat.get()
                    yield "event: shutdown\ndata: stop\n\n"
                    return
                time.sleep(0.5)   # sonde fréquente du flag, keepalive espacé
                if time.time() - dernier_ping >= 5:
                    yield ": ping\n\n"
                    dernier_ping = time.time()
                    config["LAST_SSE_ACTIVITE"] = time.time()   # preuve de vie (issue #157)
        finally:
            n = _sse_deconnecte(config)
            diag_heartbeat.log_sse("déconnexion", n)   # DIAGNOSTIC TEMPORAIRE — issue #157, à retirer

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
    """Thread daemon : coupe le serveur (SIGTERM sur son propre PID) quand
    l'onglet navigateur est réellement fermé (issue #157).

    Preuve de vie combinée, robuste au throttling des timers JS en arrière-plan :
      - SSE : une connexion /events active (SSE_CONNEXIONS_ACTIVES >= 1), ou une
        activité SSE de moins de DELAI_SSE_MAX s. Une connexion HTTP établie
        survit au passage en arrière-plan, contrairement à un setInterval.
      - heartbeat : un POST /heartbeat de moins de DELAI_HEARTBEAT_MAX s (seuil
        généreux car ce timer peut être fortement retardé en arrière-plan).

    Le serveur ne s'auto-coupe que si LES DEUX signaux sont éteints. Tant
    qu'aucun client n'a jamais été vu (ni SSE ni heartbeat — serveur qui
    démarre, ou lancé en --no-browser), aucune surveillance. L'état est lu via
    app.config (l'instance est passée au thread, hors contexte de requête)."""
    while True:
        time.sleep(INTERVALLE_HEARTBEAT)
        cfg = app_instance.config
        maintenant = time.time()

        connexions     = cfg.get("SSE_CONNEXIONS_ACTIVES", 0)
        derniere_sse   = cfg.get("LAST_SSE_ACTIVITE", 0.0)
        heartbeat_recu = cfg.get("HEARTBEAT_RECU", False)
        last_heartbeat = cfg.get("LAST_HEARTBEAT", 0.0)

        # Aucun client n'a jamais été vu (SSE ou heartbeat) → ne jamais couper.
        if not heartbeat_recu and not cfg.get("SSE_DEJA_VU", False):
            continue

        delta_hb  = maintenant - last_heartbeat
        delta_sse = maintenant - derniere_sse

        sse_vivant       = connexions >= 1 or delta_sse <= DELAI_SSE_MAX
        heartbeat_vivant = heartbeat_recu and delta_hb <= DELAI_HEARTBEAT_MAX

        if not sse_vivant and not heartbeat_vivant:
            diag_heartbeat.log_arret(delta_hb, delta_sse, connexions,   # DIAGNOSTIC TEMPORAIRE — issue #157
                                     DELAI_HEARTBEAT_MAX, DELAI_SSE_MAX)  # à retirer
            os.kill(os.getpid(), signal.SIGTERM)
            return

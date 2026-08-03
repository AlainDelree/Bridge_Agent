"""
app/fin_issue.py — SSE de fin d'issue pour l'onglet Résultats (issue #350).

Objectif : rafraîchir la ligne d'une issue dans l'onglet Résultats en moins
d'une seconde après sa clôture, sans polling. Le déclencheur est le script
partagé `scripts/traitement_fin.py` (anciennement bip.py, invoqué par
watcher.py/notifications.py à chaque transition terminale d'issue) : il POSTe
ici, en best-effort, juste après avoir émis le bip.

Mécanisme de diffusion : new_issue.py est mono-utilisateur mais plusieurs
onglets du navigateur peuvent être ouverts en même temps sur la même machine —
une simple variable globale ne suffirait donc pas à notifier chacun. Chaque
connexion GET /stream pose sa propre `queue.Queue`, ajoutée à la liste partagée
`FIN_ISSUE_ABONNES` (app.config) à la connexion et retirée à la déconnexion ;
POST /notifier-fin-issue pousse l'événement dans TOUTES les files actives (pas
de broadcast au sens réseau, juste une boucle Python).
"""

import json
import queue
from threading import Lock

from flask import Response, current_app, jsonify, request

from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)

DELAI_PING = 30   # s — garde la connexion /stream ouverte (proxys, navigateur)

_verrou_abonnes = Lock()


def notifier_fin_issue():
    """POST /notifier-fin-issue — appelé par scripts/traitement_fin.py. Corps
    JSON {"projet": ..., "numero": ...}. Pousse un événement SSE `fin_issue` à
    tous les onglets Résultats actuellement ouverts. Pas d'authentification
    (appelé par un script local, pas par un navigateur) — cohérent avec
    /heartbeat, déjà sans login_requis."""
    corps = request.get_json(silent=True) or {}
    projet = corps.get("projet")
    numero = corps.get("numero")
    if not projet or numero is None:
        return jsonify(ok=False, erreur="projet et numero requis"), 400

    evenement = "event: fin_issue\ndata: " + json.dumps({"projet": projet, "numero": numero}) + "\n\n"
    abonnes = current_app.config.setdefault("FIN_ISSUE_ABONNES", [])
    with _verrou_abonnes:
        cibles = list(abonnes)
    for file_attente in cibles:
        file_attente.put(evenement)
    return jsonify(ok=True)


def stream_fin_issue():
    """GET /stream — SSE dédié à l'onglet Résultats (issue #350) : un événement
    `fin_issue` par transition détectée côté script. Une file dédiée par
    connexion (plusieurs onglets possibles), ping toutes les DELAI_PING s pour
    maintenir la connexion. Le try/finally couvre la déconnexion du navigateur
    (GeneratorExit levée dans le générateur quand Flask cesse de le consommer),
    pour toujours retirer la file de la liste des abonnés."""
    config = current_app.config   # capturé dans le contexte de requête
    file_attente = queue.Queue()
    abonnes = config.setdefault("FIN_ISSUE_ABONNES", [])
    with _verrou_abonnes:
        abonnes.append(file_attente)

    def generer():
        try:
            while True:
                try:
                    yield file_attente.get(timeout=DELAI_PING)
                except queue.Empty:
                    yield ": ping\n\n"
        finally:
            with _verrou_abonnes:
                if file_attente in abonnes:
                    abonnes.remove(file_attente)

    return Response(
        generer(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

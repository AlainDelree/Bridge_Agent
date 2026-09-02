"""
app/fin_issue.py — SSE de fin/début d'issue pour l'onglet Résultats (issues
#350, #515).

Objectif : rafraîchir la liste de l'onglet Résultats en moins d'une seconde
après une transition d'issue (démarrage OU clôture), sans polling GitHub.
Deux déclencheurs :
  - `scripts/traitement_fin.py` (anciennement bip.py, invoqué par
    watcher.py/notifications.py à chaque transition terminale d'issue) POSTe
    sur /notifier-fin-issue, en best-effort, juste après avoir émis le bip ;
  - `watcher.py::notifier_debut_sse` POSTe sur /notifier-debut-issue juste
    après l'ACK d'une issue (début réel du traitement), pour couvrir le cas
    d'une issue créée (via issues_inbox par ex.) pendant qu'aucun onglet
    Résultats ne l'a encore vue apparaître (issue #515) : sans cet événement,
    seule sa CLÔTURE aurait déclenché un rafraîchissement, mais `fin_issue` ne
    fait que mettre à jour une ligne déjà connue — jamais en ajouter une
    nouvelle (voir app.js::gererEvenementIssue).

Mécanisme de diffusion : new_issue.py est mono-utilisateur mais plusieurs
onglets du navigateur peuvent être ouverts en même temps sur la même machine —
une simple variable globale ne suffirait donc pas à notifier chacun. Chaque
connexion GET /stream pose sa propre `queue.Queue`, ajoutée à la liste partagée
`FIN_ISSUE_ABONNES` (app.config) à la connexion et retirée à la déconnexion ;
POST /notifier-fin-issue et /notifier-debut-issue poussent chacun leur
événement dans TOUTES les files actives (pas de broadcast au sens réseau,
juste une boucle Python). Depuis #515, le canal est ouvert en PERMANENCE côté
navigateur (dès le chargement de la page, comme le polling du badge « Résultats
inbox », §3.8) et non plus seulement pendant que l'onglet Résultats est actif.
"""

import json
import queue
from threading import Lock

from flask import Response, current_app, jsonify, request

from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)

DELAI_PING = 30   # s — garde la connexion /stream ouverte (proxys, navigateur)

_verrou_abonnes = Lock()


def _pousser_evenement(nom_evenement: str):
    """Factorise le POST JSON {"projet":..., "numero":...} → diffusion de
    `event: <nom_evenement>` à toutes les files abonnées. Partagé par
    notifier_fin_issue et notifier_debut_issue (issue #515)."""
    corps = request.get_json(silent=True) or {}
    projet = corps.get("projet")
    numero = corps.get("numero")
    if not projet or numero is None:
        return jsonify(ok=False, erreur="projet et numero requis"), 400

    evenement = f"event: {nom_evenement}\ndata: " + json.dumps({"projet": projet, "numero": numero}) + "\n\n"
    abonnes = current_app.config.setdefault("FIN_ISSUE_ABONNES", [])
    with _verrou_abonnes:
        cibles = list(abonnes)
    for file_attente in cibles:
        file_attente.put(evenement)
    return jsonify(ok=True)


def notifier_fin_issue():
    """POST /notifier-fin-issue — appelé par scripts/traitement_fin.py. Corps
    JSON {"projet": ..., "numero": ...}. Pousse un événement SSE `fin_issue` à
    tous les onglets actuellement ouverts. Pas d'authentification (appelé par
    un script local, pas par un navigateur) — cohérent avec /heartbeat, déjà
    sans login_requis."""
    return _pousser_evenement("fin_issue")


def notifier_debut_issue():
    """POST /notifier-debut-issue (issue #515) — appelé par
    watcher.py::notifier_debut_sse juste après l'ACK d'une issue. Corps JSON
    {"projet": ..., "numero": ...}. Pousse un événement SSE `debut_issue` à
    tous les onglets actuellement ouverts, pour signaler l'apparition possible
    d'une issue encore inconnue du navigateur. Pas d'authentification, même
    raison que notifier_fin_issue."""
    return _pousser_evenement("debut_issue")


def stream_fin_issue():
    """GET /stream — SSE dédié à l'onglet Résultats (issues #350, #515) :
    un événement `fin_issue` ou `debut_issue` par transition détectée côté
    watcher. Une file dédiée par connexion (plusieurs onglets possibles),
    ping toutes les DELAI_PING s pour maintenir la connexion. Le try/finally
    couvre la déconnexion du navigateur (GeneratorExit levée dans le
    générateur quand Flask cesse de le consommer), pour toujours retirer la
    file de la liste des abonnés."""
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

"""
app/fin_issue.py — SSE de fin/début d'issue pour l'onglet Résultats (issues
#350, #515) + événements du dépôt issues_inbox/ (issue #631, backend seul :
`fichier_recu`, `creation_issue`, `fichier_refuse` — préparent la fusion de
l'onglet « Résultats inbox » dans Résultats à l'étape 9b ; ignorés sans effet
par le code actuel, qui ne connaît que `fin_issue`/`debut_issue`).

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


def _diffuser(nom_evenement: str, payload: dict) -> None:
    """Pousse `event: <nom_evenement>\\ndata: <payload JSON>\\n\\n` à toutes
    les files SSE actuellement abonnées (app.config["FIN_ISSUE_ABONNES"]).
    Cœur commun à `_pousser_evenement` (fin/début d'issue) et aux émetteurs
    des événements issues_inbox (issue #631) — factorise la construction du
    message SSE et la copie sous verrou de la liste d'abonnés, seule partie
    qui différait déjà entre les deux avant #631."""
    evenement = f"event: {nom_evenement}\ndata: " + json.dumps(payload) + "\n\n"
    abonnes = current_app.config.setdefault("FIN_ISSUE_ABONNES", [])
    with _verrou_abonnes:
        cibles = list(abonnes)
    for file_attente in cibles:
        file_attente.put(evenement)


def _pousser_evenement(nom_evenement: str):
    """Factorise le POST JSON {"projet":..., "numero":...} → diffusion de
    `event: <nom_evenement>` à toutes les files abonnées. Partagé par
    notifier_fin_issue et notifier_debut_issue (issue #515)."""
    corps = request.get_json(silent=True) or {}
    projet = corps.get("projet")
    numero = corps.get("numero")
    if not projet or numero is None:
        return jsonify(ok=False, erreur="projet et numero requis"), 400

    _diffuser(nom_evenement, {"projet": projet, "numero": numero})
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


# ─── Événements issues_inbox/ (issue #631, backend seul — §3, §17.3 du DOC) ──
# Même famille que /notifier-fin-issue et /notifier-debut-issue ci-dessus :
# appel best-effort par un script local (timeout court côté appelant, aucune
# authentification requise ici), échec silencieux si new_issue.py n'est pas
# lancé. Trois émetteurs :
#   - fichier_recu     : scripts/watcher_issues_inbox.py, dès qu'il prend en
#     charge un fichier déposé dans issues_inbox/ (avant même son parsing) ;
#   - creation_issue   : après CHAQUE création RÉUSSIE d'une issue (jamais
#     pour un bloc RELANCE, qui n'en crée aucune) — soit par
#     watcher_issues_inbox.py (process séparé, via la route POST ci-dessous),
#     soit par app.issues.envoyer() (formulaire web, MÊME process que
#     new_issue.py → appel direct à emettre_creation_issue(), sans HTTP) ;
#   - fichier_refuse   : pour chaque bloc refusé (fichier mono-issue entier,
#     ou un bloc d'un lot multi-issues, §3.13) — un événement par bloc, dans
#     l'ordre de traitement.
# Pour un fichier multi-blocs, watcher_issues_inbox.py émet donc : un
# fichier_recu, puis une suite de creation_issue/fichier_refuse (un par
# bloc, dans l'ordre) — jamais groupés.

def emettre_creation_issue(projet: str, numero: int, titre: str, fichier: str | None = None) -> None:
    """Diffuse l'événement SSE `creation_issue`. Appelée EN DIRECT (même
    process, pas de HTTP) par `app.issues.envoyer()` juste après une création
    réussie via le formulaire web ; `notifier_creation_issue()` ci-dessous
    l'appelle aussi, depuis la route POST utilisée par
    `scripts/watcher_issues_inbox.py` (process séparé). `fichier` est le nom
    du fichier d'origine dans issues_inbox/, absent (None) pour une création
    par formulaire."""
    _diffuser("creation_issue", {
        "projet": projet, "numero": numero, "titre": titre, "fichier": fichier,
    })


def notifier_fichier_recu():
    """POST /notifier-fichier-recu (issue #631) — appelé par
    scripts/watcher_issues_inbox.py dès qu'il prend en charge un fichier
    déposé dans issues_inbox/ (avant tout parsing/validation). Corps JSON
    {"fichier": <nom>}. Pousse un événement SSE `fichier_recu`. Pas
    d'authentification, même raison que notifier_fin_issue."""
    corps = request.get_json(silent=True) or {}
    fichier = corps.get("fichier")
    if not fichier:
        return jsonify(ok=False, erreur="fichier requis"), 400
    _diffuser("fichier_recu", {"fichier": fichier})
    return jsonify(ok=True)


def notifier_creation_issue():
    """POST /notifier-creation-issue (issue #631) — appelé par
    scripts/watcher_issues_inbox.py après chaque création réussie d'une issue
    depuis un fichier d'issues_inbox/ (jamais pour un bloc RELANCE). Corps
    JSON {"projet", "numero", "titre", "fichier"} (fichier = nom du fichier
    d'origine). Pas d'authentification, même raison que notifier_fin_issue."""
    corps = request.get_json(silent=True) or {}
    projet = corps.get("projet")
    numero = corps.get("numero")
    titre = corps.get("titre")
    if not projet or numero is None or not titre:
        return jsonify(ok=False, erreur="projet, numero et titre requis"), 400
    emettre_creation_issue(projet, numero, titre, fichier=corps.get("fichier"))
    return jsonify(ok=True)


def notifier_fichier_refuse():
    """POST /notifier-fichier-refuse (issue #631) — appelé par
    scripts/watcher_issues_inbox.py pour chaque bloc refusé (fichier
    mono-issue entier, ou un bloc d'un lot multi-issues). Corps JSON
    {"fichier", "titre", "motif"} (titre absent/null si le bloc n'a même pas
    livré de #Titre: exploitable). Pas d'authentification, même raison que
    notifier_fin_issue."""
    corps = request.get_json(silent=True) or {}
    fichier = corps.get("fichier")
    motif = corps.get("motif")
    if not fichier or not motif:
        return jsonify(ok=False, erreur="fichier et motif requis"), 400
    _diffuser("fichier_refuse", {
        "fichier": fichier, "titre": corps.get("titre") or None, "motif": motif,
    })
    return jsonify(ok=True)


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

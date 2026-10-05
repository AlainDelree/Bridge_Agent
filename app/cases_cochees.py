"""Routes Flask de l'état serveur des cases « traité/lu » de l'onglet
Résultats (issue #629, étape 5a de la refonte web — ARCHITECTURE.md §6).

Backend posé à l'étape 5a (#629) ; consommé côté navigateur par
`static/js/resultats_coches.js` (dont l'import idempotent de l'existant via
`importer_cases`) depuis l'étape 5b (#636). Toute la logique de stockage
(fichier JSON sous `logs/`, écriture atomique + verrou) vit dans
`etat_cases_cochees.py` à la racine — même relation que
`app/rate_limit.py` / `etat_rate_limit.py` (issue #615). Mêmes protections
d'authentification (`login_requis`) que le reste de l'interface."""

import sys
from pathlib import Path

from flask import jsonify, request

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

import etat_cases_cochees as ecc  # noqa: E402
from app.fin_issue import _diffuser  # noqa: E402 (issue #720, diffusion SSE ci-dessous)


def lire_cases(nom_projet):
    """GET /cases-cochees/<nom_projet> — numéros cochés pour ce projet."""
    return jsonify(numeros=ecc.lire_cases_cochees(nom_projet))


def cocher_case(nom_projet, numero):
    """POST /cases-cochees/<nom_projet>/<numero> — coche cette issue."""
    ok, erreur = ecc.cocher_issue(nom_projet, numero)
    if not ok:
        return jsonify(succes=False, erreur=erreur), 500
    return jsonify(succes=True, numeros=ecc.lire_cases_cochees(nom_projet))


def decocher_case(nom_projet, numero):
    """DELETE /cases-cochees/<nom_projet>/<numero> — décoche cette issue."""
    ok, erreur = ecc.decocher_issue(nom_projet, numero)
    if not ok:
        return jsonify(succes=False, erreur=erreur), 500
    return jsonify(succes=True, numeros=ecc.lire_cases_cochees(nom_projet))


def notifier_case_decochee():
    """POST /notifier-case-decochee (issue #720) — appelé par
    `scripts/watcher_issues_inbox.py` (process séparé) juste après une
    RELANCE RÉUSSIE sur une issue déposée dans `issues_inbox/` (champ
    RELANCE, §3.14 du DOC) : cette issue va produire un nouveau résultat,
    sa case « traité/lu » ne doit donc plus la montrer comme déjà lue.

    Décoche réellement l'état serveur (`ecc.decocher_issue`, idempotente —
    aucun effet/erreur si elle était déjà décochée) PUIS diffuse
    l'événement SSE `case_decochee` à tous les onglets Résultats déjà
    ouverts (`app.fin_issue._diffuser`) : sans ce second temps, la case
    resterait cochée à l'écran jusqu'au prochain chargement par projet
    (l'interface ne relit l'état serveur qu'à ce moment-là, voir
    `static/js/resultats_coches.js::rechargerCases`).

    Corps JSON {"projet", "numero"}. Pas d'authentification — appelé par un
    script local, jamais par un navigateur, même raison que
    `/notifier-fichier-recu` (`app/fin_issue.py`)."""
    corps = request.get_json(silent=True) or {}
    projet = corps.get("projet")
    numero = corps.get("numero")
    if not projet or numero is None:
        return jsonify(ok=False, erreur="projet et numero requis"), 400
    ok, erreur = ecc.decocher_issue(projet, int(numero))
    if not ok:
        return jsonify(ok=False, erreur=erreur), 500
    _diffuser("case_decochee", {"projet": projet, "numero": int(numero)})
    return jsonify(ok=True)


def importer_cases_route():
    """POST /cases-cochees/importer — import en masse, idempotent (issue
    #629, servira à la reprise du localStorage en 5b). Corps JSON attendu :
    `{"cases": [{"projet": ..., "numero": ...}, ...]}`, potentiellement
    plusieurs projets à la fois."""
    data = request.json or {}
    cases = data.get("cases")
    if not isinstance(cases, list):
        return jsonify(succes=False, erreur="Champ 'cases' (liste) requis."), 400
    ok, nb_ajoutees, erreur = ecc.importer_cases(cases)
    if not ok:
        return jsonify(succes=False, erreur=erreur), 500
    return jsonify(succes=True, nb_ajoutees=nb_ajoutees)

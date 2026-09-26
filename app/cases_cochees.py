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

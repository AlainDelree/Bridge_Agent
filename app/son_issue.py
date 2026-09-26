"""Choix du son (plat/cloche) PAR ISSUE (issue #630), en plus de l'interrupteur
GLOBAL (`app/son.py`, issue #527). Une issue sans choix propre suit
l'interrupteur global — voir `etat_son_issue.py` (logique de stockage,
partagée avec `scripts/traitement_fin.py`, qui résout le son effectivement
joué à la clôture) et `scripts/traitement_fin.py::main()` pour l'ordre de
résolution (choix de l'issue, puis interrupteur global).

Backend posé à l'étape #630 ; contrôle à 3 états (Global/Plat/Cloche) déplacé du
panneau latéral vers la ligne de la liste à l'étape 6 de la refonte web
(#641) — voir `static/js/actions_ligne.js::rendreControleSonLigne`/
`choisirSonIssueLigne` et `BRIDGE_AGENT_DOC.md`."""

from flask import jsonify, request

import etat_son_issue


def get_son_issue(nom_projet, numero):
    """GET /son-issue/<nom_projet>/<numero> — choix propre à cette issue, ou
    `son: null` si aucun (l'interrupteur global `/son-actif` s'applique
    alors)."""
    try:
        numero_int = int(numero)
    except (TypeError, ValueError):
        return jsonify(erreur=f"Numéro d'issue invalide : {numero!r}"), 400
    return jsonify(son=etat_son_issue.son_choisi(nom_projet, numero_int))


def get_sons_projet(nom_projet):
    """GET /son-issue/<nom_projet> — tous les choix propres du projet en une
    requête, `{"sons": {"630": "cloche", ...}}` (issue #641, refonte web étape
    6) : peuple le contrôle de son de CHAQUE ligne ouverte sans une requête par
    ligne, même stratégie que `/cases-cochees/<nom_projet>` (issue #636)."""
    return jsonify(sons=etat_son_issue.sons_projet(nom_projet))


def post_son_issue(nom_projet, numero):
    """POST /son-issue/<nom_projet>/<numero> — enregistre le choix ({"son":
    "plat"|"cloche"}) pour CETTE issue seule. `{"son": null}` (ou absent)
    retire le choix propre à l'issue — elle retombe alors sur l'interrupteur
    global."""
    try:
        numero_int = int(numero)
    except (TypeError, ValueError):
        return jsonify(erreur=f"Numéro d'issue invalide : {numero!r}"), 400

    data = request.json or {}
    son  = data.get("son")
    son  = str(son).strip().lower() if son else None

    ok, erreur = etat_son_issue.definir_son(nom_projet, numero_int, son)
    if not ok:
        return jsonify(erreur=erreur or "Écriture impossible."), (400 if erreur else 500)
    return jsonify(succes=True, son=son)

"""Couche Flask de la mesure continue de charge de l'interface web (issue
#835, points 3 et 4) — la logique indépendante de Flask (compteurs, calcul
CPU, écriture/rotation du journal) vit dans mesure_charge_interface.py à la
racine (même répartition que etat_cases_cochees.py / app/cases_cochees.py).

enregistrer_hooks(app) installe les crochets before_request/after_request
(point 3) : volontairement légers (une lecture d'horloge, une addition sous
verrou dans mesure_charge_interface.enregistrer_requete), jamais d'E/S disque
par requête. route_resume_precharge (point 4) reçoit le résumé court envoyé
par la page à la fin de chaque série de préparations — mêmes règles de
connexion que le reste de l'interface (login_requis, posé par
app/__init__.py comme pour toute route utilisateur)."""

import sys
import time
from pathlib import Path

from flask import g, jsonify, request

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

import mesure_charge_interface as mci  # noqa: E402

# Corps JSON volontairement minuscule (issue #835 point 4) : un résumé ne
# contient que 5 champs numériques/chaîne courte — toute taille au-delà est
# déjà anormale.
TAILLE_MAX_CORPS_RESUME = 1024

CHAMPS_NUMERIQUES_RESUME = ("nb_issues_preparees", "nb_requetes", "duree_totale_ms", "duree_max_ms")
MODES_CONNUS = ("moderne", "repli")
CHAMPS_ATTENDUS_RESUME = frozenset(CHAMPS_NUMERIQUES_RESUME) | {"mode"}


def avant_requete():
    """Crochet before_request — rien d'autre qu'une lecture d'horloge posée
    dans flask.g (pas de verrou ici : la minute où la requête ARRIVE n'a pas
    besoin d'être exacte à la milliseconde)."""
    g._debut_mesure_charge = time.monotonic()


def apres_requete(reponse):
    """Crochet after_request — une soustraction et un appel à
    mesure_charge_interface.enregistrer_requete (lui-même sous verrou) :
    jamais de calcul coûteux ni d'E/S ici, le disque n'est touché que par la
    boucle d'échantillonnage (une fois par minute)."""
    debut = getattr(g, "_debut_mesure_charge", None)
    if debut is not None:
        route = request.url_rule.rule if request.url_rule else "(route inconnue)"
        mci.enregistrer_requete(route, time.monotonic() - debut)
    return reponse


def enregistrer_hooks(app):
    """Installe les deux crochets ci-dessus sur `app` — appelée depuis
    app.create_app(). Ne démarre PAS le thread d'échantillonnage lui-même
    (mesure_charge_interface.demarrer_echantillonnage()) : celui-ci est démarré
    explicitement par new_issue.py, comme les autres threads daemon de
    l'application — sans quoi chaque create_app() de test en démarrerait un
    nouveau."""
    app.before_request(avant_requete)
    app.after_request(apres_requete)


def _erreur_resume(message):
    return jsonify(succes=False, erreur=message), 400


def route_resume_precharge():
    """POST /mesure-precharge (issue #835 point 4) — accepte UNIQUEMENT le
    résumé court d'une série de préparations terminée : nb_issues_preparees,
    nb_requetes, duree_totale_ms, duree_max_ms (nombres >= 0) et mode
    ('moderne'|'repli'). Rejette un corps trop gros, des champs inconnus ou
    manquants, des valeurs non numériques — rien d'autre n'est jamais
    journalisé."""
    brut = request.get_data()   # cache=True (défaut) : get_json ci-dessous relit le même corps
    if len(brut) > TAILLE_MAX_CORPS_RESUME:
        return _erreur_resume("Corps trop volumineux.")
    corps = request.get_json(silent=True)
    if not isinstance(corps, dict):
        return _erreur_resume("Corps JSON requis.")
    if set(corps.keys()) != CHAMPS_ATTENDUS_RESUME:
        return _erreur_resume("Champs inattendus ou manquants.")
    valeurs = {}
    for champ in CHAMPS_NUMERIQUES_RESUME:
        v = corps[champ]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            return _erreur_resume(f"Champ '{champ}' numérique >= 0 requis.")
        valeurs[champ] = v
    mode = corps["mode"]
    if not isinstance(mode, str) or mode not in MODES_CONNUS:
        return _erreur_resume("Champ 'mode' invalide.")
    mci.ecrire_ligne(mci.ligne_resume_precharge(
        mci.horodatage(), valeurs["nb_issues_preparees"], valeurs["nb_requetes"],
        valeurs["duree_totale_ms"], valeurs["duree_max_ms"], mode))
    return jsonify(succes=True)

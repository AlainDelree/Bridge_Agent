"""Routes Flask de création de projet (issue #99).

Réutilise SANS DUPLICATION la logique du script CLI nouveau_projet.py (issue
#98) en l'important comme module : validation du nom, gh repo view/create,
génération du .conf depuis le gabarit, création idempotente des labels,
fichiers contexte, mise à jour de BRIDGE_AGENT_DOC.md. Les mêmes fonctions
servent au script interactif (comportement inchangé) et à ces routes.

Deux points d'entrée :
  GET  /nouveau-projet/verifier — vérifie nom + dépôt AVANT création (pré-remplit
       les défauts et signale si le dépôt existe déjà ou si le nom est pris).
  POST /nouveau-projet          — exécute la création et renvoie un compte-rendu
       structuré (succès/échec par étape), cohérent avec le comportement
       idempotent du script CLI.
"""

import sys
from pathlib import Path

from flask import jsonify, request

# Racine du projet (dossier parent du package app/) : le script CLI
# nouveau_projet.py y vit, à côté de watcher.py. On l'ajoute au sys.path pour
# que « import nouveau_projet » fonctionne même en import isolé du module.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

import nouveau_projet as np_cli  # noqa: E402


def verifier_nouveau_projet():
    """Vérifie un nom (et éventuellement un dépôt) avant la création.

    Query params : nom (requis), depot (optionnel). Renvoie les défauts proposés
    et l'état d'existence, pour que le formulaire pré-remplisse les champs et
    prévienne l'utilisateur avant qu'il ne clique « Créer » :
      - nom_valide   : le nom respecte le format (minuscules/chiffres/underscore)
      - conf_existe  : configs/<nom>.conf existe déjà (nom pris)
      - depot        : dépôt effectivement vérifié (celui fourni ou le défaut)
      - depot_existe : ce dépôt existe déjà sur GitHub → installation, pas création
      - depot_defaut / rep_defaut : propositions pré-remplies (modifiables)."""
    nom = (request.args.get("nom") or "").strip().lower()
    depot = (request.args.get("depot") or "").strip()

    valide = np_cli.valider_nom(nom)
    depot_defaut = np_cli.depot_defaut(nom) if valide else ""
    depot_a_verifier = depot or depot_defaut

    return jsonify(
        nom          = nom,
        nom_valide   = valide,
        conf_existe  = np_cli.conf_existe(nom) if valide else False,
        depot_defaut = depot_defaut,
        rep_defaut   = np_cli.rep_defaut(nom) if valide else "",
        depot        = depot_a_verifier,
        depot_existe = bool(depot_a_verifier) and np_cli.depot_existe(depot_a_verifier),
    )


def creer_nouveau_projet():
    """Exécute la création complète du projet et renvoie le compte-rendu.

    Délègue entièrement à nouveau_projet.creer_projet() (même orchestration que
    le script CLI). Le résultat est déjà sérialisable en JSON (les étapes ne
    contiennent que des chaînes). Code HTTP 200 au succès, 400 en cas d'échec
    (nom invalide, .conf déjà présent, dépôt absent non créé, etc.)."""
    data = request.json or {}
    resultat = np_cli.creer_projet(
        nom                   = data.get("nom", ""),
        depot                 = data.get("depot", ""),
        rep                   = data.get("rep", ""),
        perimetre             = data.get("perimetre", ""),
        topic                 = data.get("topic", ""),
        avec_specs            = bool(data.get("avec_specs")),
        creer_depot_si_absent = bool(data.get("creer_depot_si_absent", True)),
    )
    return jsonify(resultat), (200 if resultat.get("succes") else 400)

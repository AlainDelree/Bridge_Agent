"""Routes Flask de suppression de projet (issue #587).

Symétrique à app/nouveau_projet.py : réutilise SANS DUPLICATION la logique de
supprimer_projet.py (dry-run + orchestrateur). Deux points d'entrée :
  GET  /supprimer-projet/verifier/<nom_projet> — mode à blanc : liste ce qui
       serait supprimé, sans rien toucher (consultable avant confirmation
       côté interface, checklist de l'issue #587).
  POST /supprimer-projet                       — exécute la suppression
       réelle, après revérification côté serveur de la confirmation.
"""

import sys
from pathlib import Path

from flask import jsonify, request

# Racine du projet (dossier parent du package app/) : supprimer_projet.py y
# vit, à côté de nouveau_projet.py et watcher.py.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

import supprimer_projet as sp_cli  # noqa: E402


def verifier_supprimer_projet(nom_projet):
    """GET /supprimer-projet/verifier/<nom_projet> — dry-run, aucune écriture
    disque ni sur BRIDGE_AGENT_DOC.md. Alimente l'aperçu affiché côté modal
    avant que la checklist de confirmation ne soit proposée."""
    apercu = sp_cli.previsualiser_suppression(nom_projet)
    if not apercu["existe"]:
        return jsonify(existe=False, nom=nom_projet), 404
    return jsonify(**apercu)


def executer_supprimer_projet():
    """POST /supprimer-projet — exécute réellement la suppression.

    Corps JSON attendu : {"nom": "...", "confirmation": "<nom>"}. Le champ
    `confirmation` doit reproduire EXACTEMENT le nom du projet — second
    garde-fou, indépendant des cases cochées côté navigateur (la checklist
    d'interface demandée par l'issue #587 peut être contournée par un appel
    direct à cette route ; cette vérification serveur, elle, ne peut pas
    l'être)."""
    data = request.json or {}
    nom = (data.get("nom") or "").strip().lower()
    confirmation = (data.get("confirmation") or "").strip().lower()
    if not nom or confirmation != nom:
        return jsonify(succes=False, nom=nom, etapes=[],
                       erreur="Confirmation manquante ou ne correspondant pas "
                              "au nom du projet."), 400
    resultat = sp_cli.supprimer_projet(nom, dry_run=False)
    return jsonify(resultat), (200 if resultat.get("succes") else 400)

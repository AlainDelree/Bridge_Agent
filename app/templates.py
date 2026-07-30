"""Bibliothèque de templates d'issues récurrentes (issue #284).

Certaines issues reviennent régulièrement à l'identique (ex. build Scrabble) :
plutôt que de redemander à Claude Chat ou de fouiller les conversations
passées, un template capture l'état complet du formulaire « Nouvelle issue »
(titre, corps, priorité, timeout, mode, notifications, modèle) et se recharge
en un clic. Stockage : un fichier JSON gitignoré par projet
(configs/templates_<projet>.json) — état de formulaire local, pas du code.
"""

import json
import uuid
from pathlib import Path

from flask import jsonify, request

from app.projets import projet_par_nom

# Racine du projet (dossier parent du package app/) : configs/ y vit.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
DOSSIER_TEMPLATES = DOSSIER_SCRIPT / "configs"

# Champs stockés par template, avec leur défaut — mêmes clés que
# collecterFormulaire() côté navigateur pour que sauvegarde et rechargement du
# formulaire n'aient aucune conversion à faire.
CHAMPS_TEMPLATE_DEFAUTS = {
    "titre":           "",
    "corps":           "",
    "priorite":        "normale",
    "timeout":         "300",
    "mode":            "lecture",
    "notifs":          [],
    "modele_ponctuel": "",
}


def _chemin_templates(nom_projet: str) -> Path:
    return DOSSIER_TEMPLATES / f"templates_{nom_projet}.json"


def _charger_templates(nom_projet: str) -> list:
    """Liste des templates du projet, ou liste vide si le fichier n'existe pas
    encore ou est illisible/corrompu."""
    chemin = _chemin_templates(nom_projet)
    try:
        if chemin.exists():
            return json.loads(chemin.read_text(encoding="utf-8")) or []
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _sauvegarder_templates(nom_projet: str, templates: list) -> None:
    chemin = _chemin_templates(nom_projet)
    chemin.write_text(
        json.dumps(templates, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ─── Routes Flask ──────────────────────────────────────────────────────────────

def templates_liste(nom_projet):
    """Retourne la bibliothèque de templates du projet (GET)."""
    if not projet_par_nom(nom_projet):
        return jsonify(erreur="Projet introuvable."), 404
    return jsonify(_charger_templates(nom_projet))


def templates_sauvegarder():
    """Crée ou met à jour un template (POST).

    Un `id` présent dans le corps de la requête et correspondant à un template
    existant du projet met à jour cette entrée ; sinon (absent ou inconnu) une
    nouvelle entrée est créée avec un id généré."""
    data = request.json or {}
    nom_projet = (data.get("projet") or "").strip()
    if not projet_par_nom(nom_projet):
        return jsonify(succes=False, erreur="Projet introuvable."), 404
    nom = (data.get("nom") or "").strip()
    if not nom:
        return jsonify(succes=False, erreur="Le nom du template est obligatoire."), 400

    templates = _charger_templates(nom_projet)
    id_existant = data.get("id")
    id_final = id_existant if any(t.get("id") == id_existant for t in templates) else uuid.uuid4().hex[:8]

    template = {"id": id_final, "nom": nom, "projet": nom_projet}
    for champ, defaut in CHAMPS_TEMPLATE_DEFAUTS.items():
        template[champ] = data.get(champ, defaut)

    for i, t in enumerate(templates):
        if t.get("id") == id_final:
            templates[i] = template
            break
    else:
        templates.append(template)

    _sauvegarder_templates(nom_projet, templates)
    return jsonify(succes=True, template=template)


def templates_supprimer(nom_projet, template_id):
    """Supprime un template du projet (DELETE)."""
    if not projet_par_nom(nom_projet):
        return jsonify(succes=False, erreur="Projet introuvable."), 404
    templates = _charger_templates(nom_projet)
    restants = [t for t in templates if t.get("id") != template_id]
    if len(restants) == len(templates):
        return jsonify(succes=False, erreur="Template introuvable."), 404
    _sauvegarder_templates(nom_projet, restants)
    return jsonify(succes=True)

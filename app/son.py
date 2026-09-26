"""Interrupteur global plat/cloche du bip (issue #527).

`scripts/traitement_fin.py` lit `scripts/son_actif.txt` (une seule ligne,
`plat` ou `cloche`) pour choisir entre `bip_plat()` et `bip()`. Avant cette
issue, seule une édition manuelle du fichier permettait de changer de
timbre ; ces routes l'exposent dans l'interface.

Ce réglage n'est pas dans un `.conf` de projet : `son_actif.txt` pilote TOUS
les projets utilisant le script partagé, donc ces routes ne prennent pas de
`<nom_projet>` en paramètre. Le réglage de tonalité PAR PROJET (`TONALITE_BIP`)
envisagé à l'issue #526 a été abandonné au profit du choix par issue
(#630/#637/#641/#642) et retiré de l'interface à l'issue #643 — le modèle
son ne comporte plus que deux niveaux : l'interrupteur global ci-dessous et
le choix par issue.
"""

import sys
from pathlib import Path

from flask import jsonify, request

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

import notifications  # noqa: E402

CHEMIN_SON_ACTIF   = DOSSIER_SCRIPT / "scripts" / "son_actif.txt"
SCRIPT_BIP_PARTAGE = DOSSIER_SCRIPT / "scripts" / "traitement_fin.py"

SONS_VALIDES = ("plat", "cloche")


def _lire_son_actif() -> str:
    """Même logique que `son_actif()` dans scripts/traitement_fin.py : fichier
    absent, illisible, ou valeur non reconnue → 'plat' (défaut inchangé)."""
    try:
        valeur = CHEMIN_SON_ACTIF.read_text(encoding="utf-8").strip().lower()
        if valeur in SONS_VALIDES:
            return valeur
    except OSError:
        pass
    return "plat"


def get_son_actif():
    """GET /son-actif — état courant, pour peupler l'interrupteur au chargement."""
    return jsonify(son=_lire_son_actif())


def post_son_actif():
    """POST /son-actif — écrit le timbre choisi ({"son": "plat"|"cloche"}) dans
    `son_actif.txt`, effectif au bip suivant sans redémarrage d'aucun processus
    (le fichier est relu à chaque bip par traitement_fin.py::son_actif())."""
    data = request.json or {}
    son = str(data.get("son", "")).strip().lower()
    if son not in SONS_VALIDES:
        return jsonify(erreur=f"Valeur invalide (attendu 'plat' ou 'cloche') : {son!r}"), 400
    CHEMIN_SON_ACTIF.write_text(son + "\n", encoding="utf-8")
    return jsonify(succes=True, son=son)


def tester_son():
    """POST /tester-son — joue le bip avec le timbre ACTUELLEMENT enregistré
    dans son_actif.txt (le front écrit d'abord via POST /son-actif au clic sur
    l'interrupteur, donc ce test entend toujours le dernier choix). Tonalité
    neutre (0) — comme le chemin réel du bip depuis #630, ce réglage n'est
    plus rattaché à un projet (issue #643)."""
    notifications.bip(SCRIPT_BIP_PARTAGE, 1, tonalite=0)
    return jsonify(succes=True)

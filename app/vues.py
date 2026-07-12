"""Vues générales du bridge (page principale).

Extraite de new_issue.py à l'étape 8 du refactoring modulaire. Regroupe la
route index() qui rend le gabarit principal de l'interface.
"""

from flask import render_template

from app.projets import lister_projets
from app import etat


def index():
    return render_template("index.html", projets=lister_projets(),
                           auth_active=bool(etat.get("MOT_DE_PASSE")))

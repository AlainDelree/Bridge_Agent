"""Vues générales du bridge (page principale).

Extraite de new_issue.py à l'étape 8 du refactoring modulaire. Regroupe la
route index() qui rend le gabarit principal de l'interface.
"""

from flask import render_template

import identite
from app.projets import lister_projets
from app.issues import formats_image_acceptes
from app.jetons_annuaire import etat_jetons_annuaire
from app import etat
from watcher import AGENT_PAR_DEFAUT


def index():
    return render_template("index.html", projets=lister_projets(),
                           auth_active=bool(etat.get("MOT_DE_PASSE")),
                           formats_image=formats_image_acceptes(),
                           jetons_annuaire=etat_jetons_annuaire(),
                           maj_auto_depot=etat.get("MAJ_AUTO_DEPOT"),
                           agent_par_defaut=AGENT_PAR_DEFAUT,
                           machine_seule=identite.machine_seule(),
                           diagnostic_copie=identite.diagnostic_copie())

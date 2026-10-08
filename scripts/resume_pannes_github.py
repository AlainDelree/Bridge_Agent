#!/usr/bin/env python3
"""scripts/resume_pannes_github.py — résumé en LECTURE SEULE de
logs/pannes_github.log (issue #732) : nombre d'épisodes de panne et durée
cumulée, par mois et par cause.

N'écrit jamais rien, ne touche à aucun autre fichier du projet — seul outil
de diagnostic pour savoir, avec ses propres chiffres, si les coupures
viennent de GitHub ou de la connexion locale, avant de décider d'un éventuel
système de secours (issue #732).

Limite documentée : ce résumé ne voit que les pannes survenues pendant que
new_issue.py tournait et qu'un appel gh a échoué (voir app/github_status.py)
— une coupure internet totale qui empêcherait aussi new_issue.py de tourner
n'y apparaît pas.

Usage :
    python3 scripts/resume_pannes_github.py
    python3 scripts/resume_pannes_github.py --fichier logs/pannes_github.log
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

from app.github_status import parser_ligne_journal  # noqa: E402 (réutilise le même format de ligne)

CHEMIN_DEFAUT = DOSSIER_SCRIPT / "logs" / "pannes_github.log"


def resumer(lignes: list) -> dict:
    """{ (mois, cause): {"episodes": n, "duree_s": total} } — pure, testable
    sans fichier (voir tests/test_alerte_panne_github_732.py)."""
    resume = defaultdict(lambda: {"episodes": 0, "duree_s": 0.0})
    for ligne in lignes:
        champs = parser_ligne_journal(ligne)
        if champs is None:
            continue
        try:
            debut = datetime.fromisoformat(champs["debut"])
            duree_s = float(champs["duree_s"])
        except ValueError:
            continue
        cle = (debut.strftime("%Y-%m"), champs["cause"])
        resume[cle]["episodes"] += 1
        resume[cle]["duree_s"] += duree_s
    return dict(resume)


def formater_duree(duree_s: float) -> str:
    total = int(duree_s)
    heures, reste = divmod(total, 3600)
    minutes, secondes = divmod(reste, 60)
    if heures:
        return f"{heures}h{minutes:02d}"
    if minutes:
        return f"{minutes}m{secondes:02d}"
    return f"{secondes}s"


def afficher(resume: dict) -> None:
    if not resume:
        print("Aucune panne enregistrée.")
        return
    print(f"{'Mois':<9} {'Cause':<40} {'Épisodes':>9}  {'Durée cumulée':>14}")
    for mois, cause in sorted(resume.keys()):
        donnees = resume[(mois, cause)]
        print(f"{mois:<9} {cause:<40} {donnees['episodes']:>9}  "
              f"{formater_duree(donnees['duree_s']):>14}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fichier", default=str(CHEMIN_DEFAUT),
                         help="Chemin de logs/pannes_github.log (défaut : celui du projet).")
    args = parser.parse_args()

    chemin = Path(args.fichier)
    if not chemin.exists():
        print("Aucune panne enregistrée.")
        return 0

    lignes = chemin.read_text(encoding="utf-8").splitlines()
    afficher(resumer(lignes))
    return 0


if __name__ == "__main__":
    sys.exit(main())

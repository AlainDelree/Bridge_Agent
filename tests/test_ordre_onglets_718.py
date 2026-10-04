#!/usr/bin/env python3
"""Test de non-régression — issue #718 : l'onglet « En attente » (issues
#713/#714) doit apparaître AVANT l'onglet « Résultats » dans la barre
d'onglets, mais ce changement d'ordre ne doit PAS faire de « En attente »
l'onglet actif au lancement — Résultats doit le rester, par nom (pas par
position dans la liste).

Couvre, en lisant directement les fichiers (aucune dépendance au DOM ni à un
navigateur, comme les autres tests de cette famille, ex. #713) :
- `templates/fragments/onglets.html` : le bloc `data-onglet="attente"`
  apparaît avant le bloc `data-onglet="resultats"` ; c'est ce dernier (et lui
  seul) qui porte la classe `actif` au chargement ;
- `static/js/onglets.js` : la constante `ONGLET_PAR_DEFAUT` désigne
  `'resultats'` explicitement — l'activation par défaut ne dépend donc pas de
  la position de l'onglet dans le gabarit.

Exécution :  python3 tests/test_ordre_onglets_718.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def _onglets_html() -> str:
    return (RACINE / "templates" / "fragments" / "onglets.html").read_text(encoding="utf-8")


def _onglets_js() -> str:
    return (RACINE / "static" / "js" / "onglets.js").read_text(encoding="utf-8")


def test_onglet_attente_avant_resultats_dans_le_gabarit():
    html = _onglets_html()
    pos_attente = html.find('data-onglet="attente"')
    pos_resultats = html.find('data-onglet="resultats"')
    assert pos_attente != -1, "onglet « En attente » introuvable dans le gabarit"
    assert pos_resultats != -1, "onglet « Résultats » introuvable dans le gabarit"
    assert pos_attente < pos_resultats, (
        "l'onglet « En attente » doit apparaître avant « Résultats » dans la barre d'onglets")
    return {"pos_attente": pos_attente, "pos_resultats": pos_resultats}


def test_resultats_seul_onglet_actif_au_chargement():
    html = _onglets_html()
    blocs = re.findall(r'<div class="([^"]*)" data-onglet="([^"]+)">', html)
    actifs = [nom for classes, nom in blocs if "actif" in classes.split()]
    assert actifs == ["resultats"], (
        f"un seul onglet doit porter la classe 'actif' au chargement, et c'est Résultats : {actifs}")
    return {"actifs": actifs}


def test_onglet_par_defaut_vaut_resultats_explicitement():
    js = _onglets_js()
    assert re.search(r"""ONGLET_PAR_DEFAUT\s*=\s*['"]resultats['"]""", js), (
        "ONGLET_PAR_DEFAUT doit désigner 'resultats' par son nom dans static/js/onglets.js")
    return {}


def main() -> int:
    tests = [
        ("gabarit : « En attente » avant « Résultats »", test_onglet_attente_avant_resultats_dans_le_gabarit),
        ("gabarit : Résultats seul actif au chargement", test_resultats_seul_onglet_actif_au_chargement),
        ("onglets.js : ONGLET_PAR_DEFAUT = 'resultats'", test_onglet_par_defaut_vaut_resultats_explicitement),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

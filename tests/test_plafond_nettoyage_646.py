#!/usr/bin/env python3
"""Test de `plafond_nettoyage.py` — issue #646 (balayage final de la refonte
web), règle de purge commune factorisée à partir de
`etat_cases_cochees.nettoyer_anciennes()` (#629) et
`etat_son_issue.nettoyer_entrees_perimees()` (#630).

Couvre le calcul du seuil et la sélection des numéros à retirer,
indépendamment du format de stockage (liste ou clés de dict) qui reste
propre à chaque appelant.

Exécution :  python3 tests/test_plafond_nettoyage_646.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import plafond_nettoyage as pn  # noqa: E402


def test_seuil_nettoyage_plus_grand_moins_marge():
    assert pn.seuil_nettoyage([100, 150, 151, 200], 50) == 150


def test_seuil_nettoyage_numeros_vides():
    assert pn.seuil_nettoyage([], 50) is None


def test_numeros_perimes_retire_ceux_sous_le_seuil():
    assert pn.numeros_perimes([100, 150, 151, 200], 50) == {100, 150}


def test_numeros_perimes_rien_a_retirer():
    # Plus grand numéro 3 - marge 50 → seuil négatif : aucun numéro ne peut
    # être ≤ un seuil négatif.
    assert pn.numeros_perimes([3], 50) == set()


def test_numeros_perimes_numeros_vides():
    assert pn.numeros_perimes([], 50) == set()


def test_numeros_perimes_fonctionne_sur_des_cles_de_dict():
    entree = {949: "cloche", 950: "cloche", 951: "plat", 1000: "cloche"}
    assert pn.numeros_perimes(entree.keys(), 50) == {949, 950}


def main() -> int:
    tests = [
        ("seuil_nettoyage — plus grand numéro moins la marge", test_seuil_nettoyage_plus_grand_moins_marge),
        ("seuil_nettoyage — numéros vides → None", test_seuil_nettoyage_numeros_vides),
        ("numeros_perimes — retire ceux ≤ seuil", test_numeros_perimes_retire_ceux_sous_le_seuil),
        ("numeros_perimes — rien à retirer", test_numeros_perimes_rien_a_retirer),
        ("numeros_perimes — numéros vides → ensemble vide", test_numeros_perimes_numeros_vides),
        ("numeros_perimes — fonctionne sur des clés de dict (format #630)", test_numeros_perimes_fonctionne_sur_des_cles_de_dict),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
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

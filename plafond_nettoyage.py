#!/usr/bin/env python3
"""plafond_nettoyage.py — règle de purge commune « plus grand numéro connu
moins une marge » (issue #646, balayage final de la refonte web).

Contexte : `etat_cases_cochees.nettoyer_anciennes()` (#629) et
`etat_son_issue.nettoyer_entrees_perimees()` (#630) appliquaient chacune,
séparément, la même règle PAR PROJET : retirer les entrées dont le numéro
est ≤ (plus grand numéro connu de ce fichier pour ce projet − une marge).
Ce module factorise le calcul du seuil et la décision de ce qui doit
partir ; chaque appelant garde la responsabilité de son propre format de
stockage (liste de numéros pour l'un, dict numéro→valeur pour l'autre).
"""


def seuil_nettoyage(numeros, marge: int) -> int | None:
    """Seuil de purge pour un ensemble de numéros connus (ceux d'UN projet) :
    plus grand numéro − `marge`. `None` si `numeros` est vide (rien à
    purger)."""
    if not numeros:
        return None
    return max(numeros) - marge


def numeros_perimes(numeros, marge: int) -> set:
    """Sous-ensemble de `numeros` (entiers) à purger : ceux ≤ `seuil_nettoyage`.
    Ensemble vide si `numeros` est vide ou si aucun n'est ≤ seuil."""
    seuil = seuil_nettoyage(numeros, marge)
    if seuil is None:
        return set()
    return {n for n in numeros if n <= seuil}

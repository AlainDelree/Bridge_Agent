#!/usr/bin/env python3
"""Test de non-régression — issue #734.

Trou comblé : `watcher.py` reconnaissait encore trois valeurs de TYPE
(spec_vue, spec_metier, spec_persistance) héritées du pattern « Chef + Specs
MVC » abandonné (doc retirée par #207). Un audit de la doc (#731) les a
relevées comme code mort : plus aucune consigne `type_spec_*.md`, plus aucune
mention dans BRIDGE_AGENT_DOC.md, aucun test ne les citait.

Retiré : les trois valeurs de `TYPES_ISSUE`, les branches correspondantes de
`_classer_valeur_type` (persistance/métier/vue) et les mentions dans les
docstrings de `_classer_valeur_type`/`deduire_type_issue`. Les types restants
sont chef, ouvrier et normal — un TYPE spec_* (ou « vue »/« métier »/
« persistance ») retombe désormais sur « normal », comme toute valeur
inconnue.

Ces scénarios vérifient :
- un champ TYPE spec_vue/spec_metier/spec_persistance (ou vue/métier/
  persistance) donne bien « normal » ;
- chef et ouvrier restent reconnus, via le champ TYPE ET via le préfixe du
  titre ;
- un historique (liste passée à `app.issues.estimer_duree`) contenant
  d'anciennes entrées de type spec_* se filtre sans erreur (elles ne
  correspondent plus à aucun type_issue demandé, donc ignorées).

Exécution :  python3 tests/test_retrait_types_spec_mvc_734.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def scenario_types_spec_abandonnes_retombent_sur_normal():
    for valeur in ("spec_vue", "spec_metier", "spec_persistance",
                   "vue", "métier", "metier", "persistance"):
        body = f"| TYPE | {valeur} |"
        obtenu = watcher.deduire_type_issue("Titre quelconque", body)
        assert obtenu == "normal", (
            f"TYPE={valeur!r} aurait dû retomber sur 'normal', obtenu {obtenu!r}"
        )
    return "spec_vue/spec_metier/spec_persistance (et vue/métier/persistance) → normal"


def scenario_types_spec_retires_de_types_issue():
    for valeur in ("spec_vue", "spec_metier", "spec_persistance"):
        assert valeur not in watcher.TYPES_ISSUE, (
            f"{valeur!r} ne devrait plus figurer dans TYPES_ISSUE={watcher.TYPES_ISSUE}"
        )
    assert watcher.TYPES_ISSUE == ("chef", "ouvrier", "normal")
    return f"TYPES_ISSUE={watcher.TYPES_ISSUE}"


def scenario_chef_ouvrier_toujours_reconnus_par_champ_type():
    assert watcher.deduire_type_issue("Titre quelconque", "| TYPE | chef |") == "chef"
    assert watcher.deduire_type_issue("Titre quelconque", "| TYPE | ouvrier |") == "ouvrier"
    return "champ TYPE chef/ouvrier toujours reconnu"


def scenario_chef_ouvrier_toujours_reconnus_par_prefixe_titre():
    assert watcher.deduire_type_issue("Chef : orchestrer la migration", "") == "chef"
    assert watcher.deduire_type_issue("Ouvrier : appliquer le correctif", "") == "ouvrier"
    # Un titre ne mentionnant ni chef ni ouvrier retombe sur normal (et pas sur
    # un spec_* par accident, cf. ancien commentaire sur « Ajouter la vue X »).
    assert watcher.deduire_type_issue("Ajouter la vue de synthèse", "") == "normal"
    return "préfixe de titre chef/ouvrier toujours reconnu, reste → normal"


def scenario_historique_avec_anciennes_entrees_spec_se_filtre_sans_erreur():
    sys.path.insert(0, str(RACINE))
    from app.issues import estimer_duree  # import tardif : dépend de Flask

    historique = [
        {"projet": "demo", "type": "spec_vue", "mode": "write", "duree": 120, "expiree": False},
        {"projet": "demo", "type": "spec_metier", "mode": "write", "duree": 130, "expiree": False},
        {"projet": "demo", "type": "spec_persistance", "mode": "write", "duree": 140, "expiree": False},
        {"projet": "demo", "type": "normal", "mode": "write", "duree": 100, "expiree": False},
    ]
    # deduire_type_issue ne produit plus jamais spec_vue/spec_metier/
    # spec_persistance : le seul type_issue demandé en pratique est désormais
    # "normal", qui ne doit matcher QUE l'entrée "normal" — les anciennes
    # entrées spec_* restent présentes dans l'historique mais deviennent
    # orphelines, sans jamais provoquer d'erreur.
    resultat = estimer_duree(historique, "demo", "normal", "write")
    assert resultat["n"] == 1, (
        f"seule l'entrée 'normal' doit matcher, obtenu n={resultat['n']}"
    )
    assert resultat["mediane"] == 100

    # Interroger directement une ancienne valeur spec_* (cas qui ne se
    # produit plus en pratique) ne doit pas non plus planter.
    resultat_spec = estimer_duree(historique, "demo", "spec_vue", "write")
    assert isinstance(resultat_spec, dict) and "mediane" in resultat_spec
    return "entrées spec_* orphelines : filtrage par 'normal' correct, aucune erreur"


def main():
    tests = [
        ("TYPE spec_vue/spec_metier/spec_persistance (et variantes) → normal",
         scenario_types_spec_abandonnes_retombent_sur_normal),
        ("spec_vue/spec_metier/spec_persistance retirés de TYPES_ISSUE",
         scenario_types_spec_retires_de_types_issue),
        ("chef/ouvrier reconnus via le champ TYPE",
         scenario_chef_ouvrier_toujours_reconnus_par_champ_type),
        ("chef/ouvrier reconnus via le préfixe du titre",
         scenario_chef_ouvrier_toujours_reconnus_par_prefixe_titre),
        ("historique avec anciennes entrées spec_* : pas d'erreur au chargement",
         scenario_historique_avec_anciennes_entrees_spec_se_filtre_sans_erreur),
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

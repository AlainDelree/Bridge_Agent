#!/usr/bin/env python3
"""Test de non-régression — issue #590.

Trou comblé : la condition de « succès rapide » de `_maj_combinaison_timeout`
comparait la durée réelle à `SEUIL_SUCCES_RAPIDE × timeout_courant`. Or
`timeout_courant` est le TIMEOUT SUGGÉRÉ de l'exécution en cours, qui inclut
déjà le `multiplicateur_backoff` courant : si celui-ci est emballé (plusieurs
timeouts en cascade), la barre devient inatteignable et
`succes_rapides_consecutifs` ne peut plus jamais s'incrémenter — le backoff
reste bloqué indéfiniment, même après un retour à la normale. Corrigé en
ancrant la comparaison sur `duree_typique + K_VARIABILITE × variabilite` (le
repère historique propre à la combinaison), indépendant du backoff courant.
En filet de sécurité, `TIMEOUT_suggéré` est désormais aussi borné par
`TIMEOUT_SUGGERE_PLAFOND`.

Ces scénarios vérifient :
- avec un backoff emballé (7481.83, cas réel constaté sur
  relecture_bridge|normal|write|normal), un succès dans la durée typique
  incrémente bien `succes_rapides_consecutifs` (échouait avant #590 : la
  vieille condition, réintroduite localement pour comparaison, ne s'incrémente
  jamais dans ce cas) ;
- 3 succès rapides consécutifs ramènent bien le backoff à 1.0 même dans ce
  contexte ;
- un succès proche de duree_typique (pas notablement plus rapide) NE compte
  PAS comme rapide et remet le compteur à zéro ;
- `_timeout_suggere_borne` plafonne bien un calcul qui déborderait sans lui.

Exécution :  python3 tests/test_backoff_ancrage_duree_typique_590.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def scenario_succes_rapide_incremente_malgre_backoff_emballe():
    donnees = {
        "combinaisons": {
            "relecture_bridge|normal|write|normal": {
                "duree_typique": 200.0,
                "variabilite": 10.0,
                "multiplicateur_backoff": 7481.83,
                "succes_rapides_consecutifs": 0,
                "n_observations": 50,
            }
        }
    }
    cle = "relecture_bridge|normal|write|normal"

    # Avec l'ANCIENNE condition (comparaison à timeout_courant, l'en-tête TIMEOUT
    # de CETTE exécution — ex. 300s, cf. « TIMEOUT plancher, trop court » constaté
    # sur l'issue #65 réelle), la barre est DÉCOUPLÉE de duree_typique : un succès
    # de 100s (2x plus rapide que duree_typique=200s, donc bien "rapide") ne serait
    # PAS détecté si timeout_courant est resté bas (ex. 120s, 0.7×120=84 > 100) :
    ancien_timeout_courant = 120
    assert not (100.0 < watcher.SEUIL_SUCCES_RAPIDE * ancien_timeout_courant), (
        "pré-condition du test invalide : l'ancienne barre devrait rater ce succès pourtant rapide"
    )

    # Avec le CORRECTIF (#590), ce même succès de 100s (ancré sur duree_typique,
    # PAS sur timeout_courant) doit incrémenter le compteur, backoff emballé ou non :
    duree_typique_avant, etat = watcher._maj_combinaison_timeout(
        donnees, cle, duree_s=100.0, expiree=False)
    assert etat["succes_rapides_consecutifs"] == 1, (
        f"succes_rapides_consecutifs aurait dû passer à 1, obtenu {etat['succes_rapides_consecutifs']}"
    )
    assert etat["multiplicateur_backoff"] == 7481.83, (
        "le backoff ne doit pas bouger avant SUCCES_RAPIDES_POUR_RESET succès rapides"
    )
    return "succes_rapides_consecutifs=1 malgré backoff=7481.83"


def scenario_trois_succes_rapides_reinitialisent_le_backoff():
    donnees = {
        "combinaisons": {
            "relecture_bridge|normal|write|normal": {
                "duree_typique": 200.0,
                "variabilite": 10.0,
                "multiplicateur_backoff": 7481.83,
                "succes_rapides_consecutifs": 0,
                "n_observations": 50,
            }
        }
    }
    cle = "relecture_bridge|normal|write|normal"

    for _ in range(watcher.SUCCES_RAPIDES_POUR_RESET):
        _, etat = watcher._maj_combinaison_timeout(
            donnees, cle, duree_s=100.0, expiree=False)

    assert etat["multiplicateur_backoff"] == 1.0, (
        f"le backoff aurait dû être réinitialisé à 1.0, obtenu {etat['multiplicateur_backoff']}"
    )
    assert etat["succes_rapides_consecutifs"] == 0
    return f"backoff réinitialisé à 1.0 après {watcher.SUCCES_RAPIDES_POUR_RESET} succès rapides"


def scenario_succes_non_rapide_remet_compteur_a_zero():
    donnees = {
        "combinaisons": {
            "relecture_bridge|normal|write|normal": {
                "duree_typique": 200.0,
                "variabilite": 0.0,
                "multiplicateur_backoff": 5.0,
                "succes_rapides_consecutifs": 2,
                "n_observations": 50,
            }
        }
    }
    cle = "relecture_bridge|normal|write|normal"

    # duree_s proche de duree_typique (pas notablement plus rapide) : ne doit
    # PAS compter comme "rapide".
    _, etat = watcher._maj_combinaison_timeout(
        donnees, cle, duree_s=195.0, expiree=False)
    assert etat["succes_rapides_consecutifs"] == 0, (
        f"un succès non rapide doit remettre le compteur à zéro, obtenu {etat['succes_rapides_consecutifs']}"
    )
    assert etat["multiplicateur_backoff"] == 5.0, "le backoff ne doit pas bouger sur un succès non rapide"
    return "compteur remis à zéro sur succès non rapide"


def scenario_plafond_timeout_suggere():
    # Backoff emballé comme dans le cas réel constaté (#590) : sans plafond,
    # le calcul brut dépasserait très largement TIMEOUT_SUGGERE_PLAFOND.
    suggere = watcher._timeout_suggere_borne(
        duree_typique=200.0, variabilite=10.0, f_pertinent=1.0, backoff=7481.83)
    assert suggere == watcher.TIMEOUT_SUGGERE_PLAFOND, (
        f"TIMEOUT_suggéré aurait dû être plafonné à {watcher.TIMEOUT_SUGGERE_PLAFOND}, obtenu {suggere}"
    )

    # Cas normal (backoff=1.0) : bien en dessous du plafond, valeur inchangée.
    suggere_normal = watcher._timeout_suggere_borne(
        duree_typique=200.0, variabilite=10.0, f_pertinent=1.0, backoff=1.0)
    attendu = (200.0 + watcher.K_VARIABILITE * 10.0) * 1.0 * 1.0
    assert suggere_normal == max(attendu, watcher.TIMEOUT_SUGGERE_PLANCHER)
    assert suggere_normal < watcher.TIMEOUT_SUGGERE_PLAFOND

    # Plancher toujours respecté sur un cas dérisoirement bas.
    suggere_plancher = watcher._timeout_suggere_borne(
        duree_typique=1.0, variabilite=0.0, f_pertinent=1.0, backoff=1.0)
    assert suggere_plancher == watcher.TIMEOUT_SUGGERE_PLANCHER
    return f"plafond={watcher.TIMEOUT_SUGGERE_PLAFOND}s respecté, plancher={watcher.TIMEOUT_SUGGERE_PLANCHER}s respecté"


def main():
    tests = [
        ("succès rapide s'incrémente malgré un backoff emballé (cas réel #65)",
         scenario_succes_rapide_incremente_malgre_backoff_emballe),
        ("3 succès rapides consécutifs réinitialisent le backoff",
         scenario_trois_succes_rapides_reinitialisent_le_backoff),
        ("succès non notablement rapide remet le compteur à zéro",
         scenario_succes_non_rapide_remet_compteur_a_zero),
        ("TIMEOUT_suggéré plafonné (filet de sécurité)",
         scenario_plafond_timeout_suggere),
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

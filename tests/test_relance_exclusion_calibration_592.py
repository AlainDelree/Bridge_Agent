#!/usr/bin/env python3
"""Test de non-régression — issue #592.

Trou comblé : quand une issue est relancée via le champ RELANCE (#516) après
un échec needs-human ou un timeout, watcher.py peut retrouver dans le
worktree du travail déjà effectué par la tentative précédente. La durée
mesurée (nouvelle ACK → clôture) est alors artificiellement courte et tirait
`duree_typique` vers le bas.

Corrigé en détectant, AVANT l'ACK courante, un commentaire d'échec définitif
(préfixe `MARQUEUR_ECHEC_TENTATIVES`, posté par watcher.py avant needs-human)
déjà présent dans l'historique de l'issue — signe d'une RELANCE
(`_issue_est_relance`). Si détecté, la durée est traitée comme CENSURÉE
(même principe que les timeouts) dans `_maj_combinaison_timeout` : aucune
mise à jour de `duree_typique`/`variabilite`/succès rapides/backoff, seul
`n_relances_exclues` est incrémenté (traçabilité). `maj_calibration_timeout`
exclut de même cette durée de la mise à jour de F_reseau/F_local.

Ces scénarios vérifient :
- `_issue_est_relance` détecte bien le marqueur d'échec dans l'historique,
  et ne détecte rien sur une issue normale (aucun échec préalable) ;
- un succès de RELANCE (`relance=True`) laisse `duree_typique`/`variabilite`
  inchangés et incrémente `n_relances_exclues` ;
- un succès normal (`relance=False`, non-régression) met à jour
  `duree_typique`/`variabilite` comme avant #592 ;
- `maj_calibration_timeout` bout en bout : une RELANCE ne modifie pas
  `duree_typique` dans `etat_timeout.json`, une issue normale si.

Exécution :  python3 tests/test_relance_exclusion_calibration_592.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def scenario_detection_relance_sur_historique():
    commentaires_relance = [
        "✅ ACK — Issue #123 reçue par watcher.py...",
        "❌ Échec après 3 tentatives.\n\nDernière erreur : `timeout`.",
        "✅ ACK — Issue #123 reçue par watcher.py (relance)...",
    ]
    assert watcher._issue_est_relance(commentaires_relance) is True, (
        "un commentaire d'échec préalable doit être détecté comme RELANCE"
    )

    commentaires_normaux = [
        "✅ ACK — Issue #124 reçue par watcher.py...",
    ]
    assert watcher._issue_est_relance(commentaires_normaux) is False, (
        "aucun échec préalable : ne doit PAS être détecté comme RELANCE"
    )

    assert watcher._issue_est_relance([]) is False, (
        "historique vide (ex. lecture réseau ratée) : pas de faux positif"
    )
    return "détection RELANCE correcte (positif, négatif, historique vide)"


def scenario_relance_exclut_duree_typique_et_variabilite():
    donnees = {
        "combinaisons": {
            "bridge_agent|normal|write|normal": {
                "duree_typique": 200.0,
                "variabilite": 10.0,
                "multiplicateur_backoff": 1.0,
                "succes_rapides_consecutifs": 0,
                "n_observations": 20,
            }
        }
    }
    cle = "bridge_agent|normal|write|normal"

    # Durée artificiellement courte (travail déjà fait par la tentative
    # précédente) : si elle n'était PAS exclue, elle tirerait duree_typique
    # (200s) fortement vers le bas.
    duree_typique_avant, etat = watcher._maj_combinaison_timeout(
        donnees, cle, duree_s=5.0, expiree=False, relance=True)

    assert duree_typique_avant == 200.0
    assert etat["duree_typique"] == 200.0, (
        f"duree_typique n'aurait pas dû bouger sur une RELANCE, obtenu {etat['duree_typique']}"
    )
    assert etat["variabilite"] == 10.0, (
        f"variabilite n'aurait pas dû bouger sur une RELANCE, obtenu {etat['variabilite']}"
    )
    assert etat["n_observations"] == 20, "n_observations ne doit pas compter une RELANCE"
    assert etat["multiplicateur_backoff"] == 1.0
    assert etat["succes_rapides_consecutifs"] == 0
    assert etat.get("n_relances_exclues") == 1, (
        f"n_relances_exclues aurait dû passer à 1, obtenu {etat.get('n_relances_exclues')}"
    )
    return "duree_typique/variabilite inchangés, n_relances_exclues=1"


def scenario_non_regression_succes_normal():
    donnees = {
        "combinaisons": {
            "bridge_agent|normal|write|normal": {
                "duree_typique": 200.0,
                "variabilite": 10.0,
                "multiplicateur_backoff": 1.0,
                "succes_rapides_consecutifs": 0,
                "n_observations": 20,
            }
        }
    }
    cle = "bridge_agent|normal|write|normal"

    duree_typique_avant, etat = watcher._maj_combinaison_timeout(
        donnees, cle, duree_s=210.0, expiree=False, relance=False)

    assert duree_typique_avant == 200.0
    attendu = watcher._ewma_maj(200.0, 210.0, watcher.ALPHA_EWMA_ISSUES)
    assert etat["duree_typique"] == attendu, (
        f"duree_typique aurait dû être mise à jour comme avant #592, obtenu {etat['duree_typique']}"
    )
    assert etat["n_observations"] == 21
    assert "n_relances_exclues" not in etat, (
        "une issue normale ne doit jamais introduire n_relances_exclues"
    )
    return f"duree_typique mise à jour normalement ({attendu:.2f}s), non-régression OK"


def scenario_maj_calibration_timeout_bout_en_bout():
    with tempfile.TemporaryDirectory() as tmp:
        fichier_etat = Path(tmp) / "etat_timeout.json"
        ancien_fichier = watcher.FICHIER_ETAT_TIMEOUT
        ancien_ambiance = watcher.FICHIER_ETAT_AMBIANCE
        watcher.FICHIER_ETAT_TIMEOUT = fichier_etat
        watcher.FICHIER_ETAT_AMBIANCE = Path(tmp) / "etat_ambiance.json"
        try:
            # Amorce : un premier succès normal établit duree_typique.
            watcher.maj_calibration_timeout(
                projet="bridge_agent", type_issue="normal", mode="write",
                duree_s=200.0, expiree=False, body="", date_iso="2026-09-23T10:00:00",
                complexite="normal",
            )
            etat = watcher._lire_json_best_effort(fichier_etat)
            cle = watcher._cle_combinaison("bridge_agent", "normal", "write", "normal")
            duree_apres_amorce = etat["combinaisons"][cle]["duree_typique"]
            assert duree_apres_amorce == 200.0

            # RELANCE : durée artificiellement courte (5s) — ne doit RIEN changer.
            watcher.maj_calibration_timeout(
                projet="bridge_agent", type_issue="normal", mode="write",
                duree_s=5.0, expiree=False, body="", date_iso="2026-09-23T10:05:00",
                complexite="normal", relance=True,
            )
            etat = watcher._lire_json_best_effort(fichier_etat)
            duree_apres_relance = etat["combinaisons"][cle]["duree_typique"]
            assert duree_apres_relance == duree_apres_amorce, (
                f"duree_typique n'aurait pas dû bouger après une RELANCE, "
                f"obtenu {duree_apres_relance} (attendu {duree_apres_amorce})"
            )

            # Issue normale ensuite : doit à nouveau mettre à jour duree_typique.
            watcher.maj_calibration_timeout(
                projet="bridge_agent", type_issue="normal", mode="write",
                duree_s=220.0, expiree=False, body="", date_iso="2026-09-23T10:10:00",
                complexite="normal", relance=False,
            )
            etat = watcher._lire_json_best_effort(fichier_etat)
            duree_apres_normale = etat["combinaisons"][cle]["duree_typique"]
            assert duree_apres_normale != duree_apres_amorce, (
                "une issue normale après la RELANCE doit remettre à jour duree_typique"
            )
            return (
                f"amorce={duree_apres_amorce:.1f}s → relance inchangée="
                f"{duree_apres_relance:.1f}s → normale mise à jour={duree_apres_normale:.1f}s"
            )
        finally:
            watcher.FICHIER_ETAT_TIMEOUT = ancien_fichier
            watcher.FICHIER_ETAT_AMBIANCE = ancien_ambiance


def main():
    tests = [
        ("détection RELANCE sur l'historique des commentaires",
         scenario_detection_relance_sur_historique),
        ("RELANCE : duree_typique/variabilite exclus, n_relances_exclues tracé",
         scenario_relance_exclut_duree_typique_et_variabilite),
        ("non-régression : succès normal met à jour duree_typique comme avant",
         scenario_non_regression_succes_normal),
        ("maj_calibration_timeout bout en bout (amorce → relance → normale)",
         scenario_maj_calibration_timeout_bout_en_bout),
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

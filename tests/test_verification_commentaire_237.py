#!/usr/bin/env python3
"""Test de non-régression — issue #237.

Reproduit l'incident de l'issue #236 : `gh issue comment` rend le code de
retour 0 alors qu'AUCUN commentaire n'a réellement été créé (troncature
silencieuse côté `gh`, notamment via le plafond argv Windows). Avant #237,
`commenter_resultat_avec_retry` faisait confiance au seul code de retour et
`fermer_issue` était appelée juste après — effaçant silencieusement le
travail. Ce test vérifie que la VÉRIFICATION post-publication (relecture de
l'issue, présence du marqueur `MARQUEUR_RESULTAT`) empêche ce scénario : si
`gh` rend 0 mais que la relecture ne trouve aucun commentaire correspondant,
la tentative est traitée comme un échec, toutes les tentatives échouent (le
mock ne pose jamais le commentaire) et l'issue N'EST PAS fermée.

Exécution :  python3 tests/test_verification_commentaire_237.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def scenario_1_gh_rend_0_sans_commentaire_reel():
    """`gh issue comment` rend 0 à chaque tentative, mais la relecture de
    l'issue ne trouve jamais le marqueur (comme si le commentaire n'avait
    jamais été créé, cf. #236). commenter_resultat_avec_retry doit épuiser
    toutes ses tentatives et retourner False — jamais True sur la seule foi
    du code de retour."""
    appels_comment = {"n": 0}

    def fake_run(cmd, **kwargs):
        res = mock.Mock()
        if "comment" in cmd:
            appels_comment["n"] += 1
            res.returncode = 0  # gh ment : rend 0 sans rien poster
            res.stdout = ""
            res.stderr = ""
        elif "view" in cmd:
            res.returncode = 0
            res.stdout = '{"comments": []}'  # jamais retrouvé à la relecture
            res.stderr = ""
        else:
            raise AssertionError(f"commande inattendue : {cmd}")
        return res

    with mock.patch.object(watcher, "CFG", mock.Mock(depot="exemple/depot-test")), \
         mock.patch.object(watcher.subprocess, "run", fake_run), \
         mock.patch.object(watcher.time, "sleep", lambda _: None):
        resultat = watcher.commenter_resultat_avec_retry(
            999, f"{watcher.MARQUEUR_RESULTAT}\n## Résultat\n\nOK"
        )

    assert resultat is False, (
        "commenter_resultat_avec_retry a retourné True alors qu'aucun "
        "commentaire n'a jamais été confirmé présent — régression #236."
    )
    # 1 tentative initiale + 3 retries (DELAIS_RETRY_RESULTAT) = 4.
    assert appels_comment["n"] == 1 + len(watcher.DELAIS_RETRY_RESULTAT), (
        f"Nombre de tentatives inattendu : {appels_comment['n']}"
    )
    return {"appels_comment": appels_comment["n"]}


def scenario_2_traiter_issue_ne_ferme_pas_si_verification_echoue():
    """Bout-en-bout via traiter_issue (comme #236 l'a vécu) : lancer_claude
    réussit, mais le commentaire de résultat n'est jamais confirmé présent à
    la relecture. L'issue ne doit PAS être fermée (ni `gh issue close`, ni
    label `done`) : elle reste ouverte pour reprise au prochain cycle."""
    appels = {"close": 0, "edit_done": 0}

    def fake_run(cmd, **kwargs):
        res = mock.Mock()
        if "comment" in cmd:
            res.returncode = 0
            res.stdout = ""
            res.stderr = ""
        elif "view" in cmd:
            res.returncode = 0
            res.stdout = '{"comments": []}'
            res.stderr = ""
        elif "close" in cmd:
            appels["close"] += 1
            res.returncode = 0
            res.stdout = ""
            res.stderr = ""
        elif "edit" in cmd:
            if watcher.LABEL_FAIT in cmd:
                appels["edit_done"] += 1
            res.returncode = 0
            res.stdout = ""
            res.stderr = ""
        else:
            raise AssertionError(f"commande inattendue : {cmd}")
        return res

    issue = {"number": 236, "title": "issue de test", "body": "", "labels": []}

    with mock.patch.object(watcher, "CFG", mock.Mock(
                depot="exemple/depot-test", nom="test_237",
                max_essais=1, perimetre="/tmp", rep_travail=Path("/tmp"),
                perimetre_dynamique=False)), \
         mock.patch.object(watcher.subprocess, "run", fake_run), \
         mock.patch.object(watcher.time, "sleep", lambda _: None), \
         mock.patch.object(watcher, "lancer_claude",
                            lambda *a, **k: (True, "sortie de build")), \
         mock.patch.object(watcher, "acquerir_verrou", lambda *a, **k: Path("/tmp/verrou-test-237")), \
         mock.patch.object(watcher, "liberer_verrou", lambda *a, **k: None), \
         mock.patch.object(watcher, "notifier", lambda *a, **k: None), \
         mock.patch.object(watcher, "enregistrer_duree", lambda *a, **k: None), \
         mock.patch.object(watcher, "maj_calibration_timeout", lambda *a, **k: None):
        watcher.traiter_issue(issue, dry_run=False)

    assert appels["close"] == 0, (
        "L'issue a été fermée (`gh issue close`) alors que le commentaire de "
        "résultat n'a jamais été confirmé présent — régression #236."
    )
    assert appels["edit_done"] == 0, (
        "Le label 'done' a été posé alors que le commentaire de résultat n'a "
        "jamais été confirmé présent — régression #236."
    )
    return appels


def main():
    tests = [
        ("gh rend 0 sans commentaire réel → échec après épuisement des tentatives",
         scenario_1_gh_rend_0_sans_commentaire_reel),
        ("traiter_issue ne ferme pas l'issue si la vérification échoue",
         scenario_2_traiter_issue_ne_ferme_pas_si_verification_echoue),
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

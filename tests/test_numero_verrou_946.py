#!/usr/bin/env python3
"""Test de non-régression — issue #946.

Chaque verrou de traitement (`logs/verrous/*.lock`) indique déjà le watcher
propriétaire (`pid=`), le projet, le mode et le dossier de travail — mais pas
le numéro de l'issue qu'il protège. Cette issue ajoute un champ `numero=<N>`
au contenu du verrou, écrit par `acquerir_verrou` (donc dans les trois modes :
écriture, lecture active, lecture simple — un seul point d'écriture, voir
`watcher._acquerir_verrou_pour_issue`) et relu par `taches_en_cours`, SANS
changer la façon dont une tâche est jugée « en cours » (toujours fondée
uniquement sur `pid=`).

Compatibilité impérative : un verrou déjà présent sur disque, posé avant
cette issue (donc sans `numero=`), doit continuer à être lu exactement comme
avant — `numero` simplement inconnu (None), jamais une erreur. Même chose
pour une valeur `numero=` corrompue ou vide. `numero=` est placé AVANT `rep=`
(comme `mode=`/`projet=`/`pid=`) : sa lecture ne doit donc jamais dépendre de
ce que vaut `rep=`, y compris quand ce chemin contient des espaces.

Exécution :  python3 tests/test_numero_verrou_946.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def _isoler_etat(tmp_path: Path, nom: str, rep_travail: Path):
    """Isole DOSSIER_VERROUS et CFG dans un dossier temporaire — jamais dans
    le vrai logs/verrous/ du dépôt (même technique que les autres tests de
    verrous, ex. tests/test_orphelin_verrou_perime_322.py)."""
    anciens = {"DOSSIER_VERROUS": watcher.DOSSIER_VERROUS, "CFG": watcher.CFG}
    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    watcher.CFG = watcher.Config(
        nom=nom, depot="AlainDelree/depot-inexistant-test946",
        rep_travail=rep_travail, topic_ntfy=nom,
    )
    return anciens


def _restaurer_etat(anciens: dict) -> None:
    watcher.DOSSIER_VERROUS = anciens["DOSSIER_VERROUS"]
    watcher.CFG = anciens["CFG"]


def scenario_numero_consigne_dans_les_trois_modes():
    """`acquerir_verrou` écrit `numero=<N>` quel que soit le mode : écriture
    (verrou du worktree), lecture active (verrou partagé du dossier projet)
    et lecture simple."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        resultats = {}
        for mode in (watcher.MODE_ECRITURE, watcher.MODE_LECTURE_ACTIVE, watcher.MODE_LECTURE):
            rep = tmp_path / mode
            rep.mkdir()
            anciens = _isoler_etat(tmp_path, f"test946-{mode}", rep)
            try:
                verrou = watcher.acquerir_verrou(rep, 1800, mode, numero=100 + hash(mode) % 100)
                assert verrou is not None, f"verrou non acquis en mode {mode}"
                contenu = verrou.read_text(encoding="utf-8")
                assert "numero=" in contenu, (
                    f"champ numero= absent du verrou en mode {mode} : {contenu!r}")
                resultats[mode] = contenu
            finally:
                watcher.liberer_verrou(watcher._chemin_verrou(rep))
                _restaurer_etat(anciens)
        return {"modes_verifies": list(resultats)}


def scenario_lecture_verrou_ancien_sans_numero():
    """Un verrou posé AVANT cette issue (sans champ `numero=`) doit continuer
    à être lu exactement comme avant : `taches_en_cours` le compte toujours
    comme « en cours » (le pid propriétaire est ce process, donc vivant),
    avec rep/mode corrects et numero=None (inconnu), jamais une exception."""
    import os
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep = tmp_path / "projet"
        rep.mkdir()
        anciens = _isoler_etat(tmp_path, "test946-ancien", rep)
        try:
            verrou = watcher._chemin_verrou(rep)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(f"pid={os.getpid()} projet=test946-ancien mode=ecriture rep={rep}\n",
                               encoding="utf-8")

            taches = watcher.taches_en_cours("test946-ancien")

            assert len(taches) == 1, f"une seule tâche attendue : {taches}"
            assert taches[0]["rep"] == str(rep), taches[0]
            assert taches[0]["mode"] == "ecriture", taches[0]
            assert taches[0]["numero"] is None, (
                f"numéro attendu inconnu (None) pour un verrou ancien sans champ : {taches[0]}")
            return {"numero": taches[0]["numero"]}
        finally:
            _restaurer_etat(anciens)


def scenario_lecture_numero_avec_rep_contenant_des_espaces():
    """`numero=` est placé avant `rep=` dans le contenu du verrou : sa lecture
    (et celle de mode=/projet=/pid=, qui le précèdent déjà) ne doit pas être
    perturbée par un `rep=` dont la valeur contient des espaces."""
    import os
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_avec_espaces = tmp_path / "mon projet avec espaces"
        rep_avec_espaces.mkdir()
        anciens = _isoler_etat(tmp_path, "test946-espaces", rep_avec_espaces)
        try:
            verrou = watcher._chemin_verrou(rep_avec_espaces)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(
                f"pid={os.getpid()} projet=test946-espaces mode=lecture_active "
                f"numero=42 rep={rep_avec_espaces}\n",
                encoding="utf-8")

            taches = watcher.taches_en_cours("test946-espaces")

            assert len(taches) == 1, f"une seule tâche attendue : {taches}"
            assert taches[0]["mode"] == "lecture_active", (
                f"mode= mal lu malgré l'espace dans rep= : {taches[0]}")
            assert taches[0]["numero"] == 42, (
                f"numero= mal lu malgré l'espace dans rep= : {taches[0]}")
            return {"numero": taches[0]["numero"], "mode": taches[0]["mode"]}
        finally:
            _restaurer_etat(anciens)


def scenario_numero_invalide_ignore_sans_erreur():
    """Une valeur `numero=` invalide (non numérique) ou vide est ignorée
    silencieusement — le numéro redevient simplement inconnu (None), sans
    jamais faire échouer `taches_en_cours`."""
    import os
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep = tmp_path / "projet"
        rep.mkdir()
        anciens = _isoler_etat(tmp_path, "test946-invalide", rep)
        try:
            verrou = watcher._chemin_verrou(rep)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(
                f"pid={os.getpid()} projet=test946-invalide mode=ecriture numero=abc rep={rep}\n",
                encoding="utf-8")

            taches = watcher.taches_en_cours("test946-invalide")

            assert len(taches) == 1, f"une seule tâche attendue : {taches}"
            assert taches[0]["numero"] is None, (
                f"numéro invalide aurait dû être ignoré (None) : {taches[0]}")
            return {"numero": taches[0]["numero"]}
        finally:
            _restaurer_etat(anciens)


def scenario_taches_en_cours_avec_et_sans_numero():
    """`taches_en_cours` expose le numéro de chaque tâche sans changer la
    façon dont une tâche est jugée « en cours » : une liste avec un verrou
    muni de `numero=` et un autre sans doit renvoyer les deux tâches, chacune
    avec son propre numéro (ou None)."""
    import os
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_a = tmp_path / "a"
        rep_a.mkdir()
        rep_b = tmp_path / "b"
        rep_b.mkdir()
        anciens = _isoler_etat(tmp_path, "test946-mixte", rep_a)
        try:
            verrou_a = watcher._chemin_verrou(rep_a)
            verrou_b = watcher._chemin_verrou(rep_b)
            verrou_a.parent.mkdir(parents=True, exist_ok=True)
            verrou_a.write_text(
                f"pid={os.getpid()} projet=test946-mixte mode=ecriture numero=777 rep={rep_a}\n",
                encoding="utf-8")
            verrou_b.write_text(
                f"pid={os.getpid()} projet=test946-mixte mode=lecture rep={rep_b}\n",
                encoding="utf-8")

            taches = watcher.taches_en_cours("test946-mixte")

            assert len(taches) == 2, f"deux tâches attendues : {taches}"
            numeros = {t["rep"]: t["numero"] for t in taches}
            assert numeros[str(rep_a)] == 777, numeros
            assert numeros[str(rep_b)] is None, numeros
            return {"numeros": numeros}
        finally:
            _restaurer_etat(anciens)


def main():
    tests = [
        ("acquerir_verrou consigne numero= dans les trois modes",
         scenario_numero_consigne_dans_les_trois_modes),
        ("verrou ancien sans numero= → lu comme avant, numéro inconnu",
         scenario_lecture_verrou_ancien_sans_numero),
        ("numero= lu correctement malgré un rep= contenant des espaces",
         scenario_lecture_numero_avec_rep_contenant_des_espaces),
        ("numero= invalide → ignoré sans erreur",
         scenario_numero_invalide_ignore_sans_erreur),
        ("taches_en_cours : liste mixte avec et sans numéro",
         scenario_taches_en_cours_avec_et_sans_numero),
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

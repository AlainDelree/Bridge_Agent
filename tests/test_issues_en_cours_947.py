#!/usr/bin/env python3
"""Test de non-régression — issue #947.

L'étude #939 prévoit qu'avant de fermer proprement une issue, l'interface
prévienne l'utilisateur si d'autres issues du même projet tournent encore,
en les listant. Cette issue ajoute la route `GET /issues-en-cours/<nom_projet>`
(`app/watchers.py::issues_en_cours`, même famille que `/watchers` et
`/statut/<nom_projet>`) qui expose cette liste pour UN projet, à l'instant
précis de l'appel.

Source UNIQUE : les verrous de traitement, via `tache_en_cours()`
(app/watchers.py, donc `watcher.taches_en_cours`, issue #946) — jamais
d'appel GitHub, jamais de lecture de la liste d'issues de l'interface.
Une tâche dont le watcher propriétaire est mort n'est pas comptée : c'est
déjà le comportement de `taches_en_cours` elle-même, pas dupliqué par la
route — un scénario ci-dessous le vérifie avec la vraie fonction (verrou
réel, pid réellement mort), sans mock.

La plupart des autres scénarios substituent `projet_par_nom`, `watcher_actif`
et `tache_en_cours` de `app.watchers` (même technique que
tests/test_relancer_watcher_574.py) pour isoler la logique de la route de
tout accès disque réel (fichier PID, configs/*.conf).

Exécution :  python3 tests/test_issues_en_cours_947.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import watcher  # noqa: E402
import app.watchers as watchers_mod  # noqa: E402

APP_FLASK = flask.Flask(__name__)


def _appeler(nom_projet: str, exclure: int | None = None):
    chemin = f"/issues-en-cours/{nom_projet}"
    if exclure is not None:
        chemin += f"?exclure={exclure}"
    with APP_FLASK.test_request_context(chemin):
        resultat = watchers_mod.issues_en_cours(nom_projet)
    if isinstance(resultat, tuple):
        reponse, code = resultat
        return reponse.get_json(), code
    return resultat.get_json(), 200


def _attendre_mort(pid: int, delai: float) -> bool:
    import os
    fin = time.monotonic() + delai
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def _pid_mort() -> int:
    """Même technique que tests/test_nettoyage_verrous_perimes_751.py :
    un vrai PID, garanti mort (pas de risque de réutilisation flaky par
    l'OS juste après coup)."""
    proc = subprocess.Popen(["sleep", "30"])
    pid = proc.pid
    proc.kill()
    proc.wait(timeout=5)
    assert _attendre_mort(pid, 5.0), f"précondition non remplie : le PID {pid} est toujours vivant"
    return pid


def scenario_projet_inconnu():
    watchers_mod.projet_par_nom = lambda nom: None
    corps, code = _appeler("projet-inexistant-947")
    assert code == 404, (corps, code)
    assert "erreur" in corps, corps
    return {"code": code, "corps": corps}


def scenario_projet_sans_tache():
    cfg = SimpleNamespace(nom="test947-vide")
    watchers_mod.projet_par_nom = lambda nom: cfg
    watchers_mod.watcher_actif = lambda c: (True, 123)
    watchers_mod.tache_en_cours = lambda c: []
    corps, code = _appeler("test947-vide")
    assert code == 200, (corps, code)
    assert corps["issues"] == [], corps
    assert corps["watcher_actif"] is True, corps
    return corps


def scenario_une_tache_avec_numero():
    cfg = SimpleNamespace(nom="test947-numero")
    watchers_mod.projet_par_nom = lambda nom: cfg
    watchers_mod.watcher_actif = lambda c: (True, 1)
    watchers_mod.tache_en_cours = lambda c: [
        {"rep": "/tmp/x", "mode": "ecriture", "numero": 123},
    ]
    corps, code = _appeler("test947-numero")
    assert code == 200, (corps, code)
    assert corps["issues"] == [{"numero": 123, "mode": "ecriture"}], corps
    return corps


def scenario_une_tache_sans_numero():
    """Verrou ancien sans `numero=` (posé avant #946) : entrée avec numéro
    inconnu (null), comptée quand même comme tâche en cours."""
    cfg = SimpleNamespace(nom="test947-sansnum")
    watchers_mod.projet_par_nom = lambda nom: cfg
    watchers_mod.watcher_actif = lambda c: (True, 1)
    watchers_mod.tache_en_cours = lambda c: [
        {"rep": "/tmp/y", "mode": "lecture_active", "numero": None},
    ]
    corps, code = _appeler("test947-sansnum")
    assert code == 200, (corps, code)
    assert corps["issues"] == [{"numero": None, "mode": "lecture_active"}], corps
    return corps


def scenario_plusieurs_taches_en_parallele():
    """Plusieurs issues en écriture en parallèle (MAX_WRITE_PARALLELE > 1) :
    une entrée par issue."""
    cfg = SimpleNamespace(nom="test947-parallele")
    watchers_mod.projet_par_nom = lambda nom: cfg
    watchers_mod.watcher_actif = lambda c: (True, 1)
    watchers_mod.tache_en_cours = lambda c: [
        {"rep": "/tmp/a", "mode": "ecriture", "numero": 10},
        {"rep": "/tmp/b", "mode": "ecriture", "numero": 20},
    ]
    corps, code = _appeler("test947-parallele")
    assert code == 200, (corps, code)
    assert corps["issues"] == [
        {"numero": 10, "mode": "ecriture"},
        {"numero": 20, "mode": "ecriture"},
    ], corps
    return corps


def scenario_exclusion_numero_connu():
    """Paramètre `exclure` sur un numéro connu : cette entrée disparaît,
    les autres restent — « les AUTRES issues en cours »."""
    cfg = SimpleNamespace(nom="test947-exclusion")
    watchers_mod.projet_par_nom = lambda nom: cfg
    watchers_mod.watcher_actif = lambda c: (True, 1)
    watchers_mod.tache_en_cours = lambda c: [
        {"rep": "/tmp/a", "mode": "ecriture", "numero": 10},
        {"rep": "/tmp/b", "mode": "ecriture", "numero": 20},
    ]
    corps, code = _appeler("test947-exclusion", exclure=10)
    assert code == 200, (corps, code)
    assert corps["issues"] == [{"numero": 20, "mode": "ecriture"}], corps
    return corps


def scenario_non_exclusion_numero_inconnu():
    """Le numéro visé par l'exclusion est inconnu pour ce verrou (numero
    None) : dans le doute, l'entrée reste dans la liste — jamais exclue par
    erreur."""
    cfg = SimpleNamespace(nom="test947-exclusion-inconnu")
    watchers_mod.projet_par_nom = lambda nom: cfg
    watchers_mod.watcher_actif = lambda c: (True, 1)
    watchers_mod.tache_en_cours = lambda c: [
        {"rep": "/tmp/a", "mode": "ecriture", "numero": None},
    ]
    corps, code = _appeler("test947-exclusion-inconnu", exclure=10)
    assert code == 200, (corps, code)
    assert corps["issues"] == [{"numero": None, "mode": "ecriture"}], corps
    return corps


def scenario_tache_watcher_mort_ignoree():
    """Intégration réelle avec `watcher.taches_en_cours` (AUCUN mock sur
    `tache_en_cours` ici) : un verrou dont le pid propriétaire est
    réellement mort n'est jamais compté — la route ne fait que reprendre ce
    que `taches_en_cours` renvoie déjà, sans dupliquer ce filtre."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep = tmp_path / "projet"
        rep.mkdir()
        ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"
        cfg = watcher.Config(nom="test947-mort", depot="AlainDelree/depot-inexistant-947",
                              rep_travail=rep, topic_ntfy="test947-mort")
        try:
            verrou = watcher._chemin_verrou(rep)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            pid_mort = _pid_mort()
            verrou.write_text(
                f"pid={pid_mort} projet=test947-mort mode=ecriture numero=55 rep={rep}\n",
                encoding="utf-8")

            watchers_mod.projet_par_nom = lambda nom: cfg
            watchers_mod.watcher_actif = lambda c: (False, None)
            corps, code = _appeler("test947-mort")

            assert code == 200, (corps, code)
            assert corps["issues"] == [], corps
            return corps
        finally:
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous


def main():
    ancien_projet_par_nom = watchers_mod.projet_par_nom
    ancien_watcher_actif = watchers_mod.watcher_actif
    ancien_tache_en_cours = watchers_mod.tache_en_cours

    tests = [
        ("projet inconnu → erreur claire, 404 (#947)", scenario_projet_inconnu),
        ("projet sans verrou → liste vide (#947)", scenario_projet_sans_tache),
        ("une tâche avec numéro connu (#947)", scenario_une_tache_avec_numero),
        ("une tâche sans numéro (verrou ancien) → comptée, numéro inconnu (#947)", scenario_une_tache_sans_numero),
        ("plusieurs tâches en parallèle → une entrée chacune (#947)", scenario_plusieurs_taches_en_parallele),
        ("exclusion d'un numéro connu (#947)", scenario_exclusion_numero_connu),
        ("non-exclusion quand le numéro du verrou est inconnu (#947)", scenario_non_exclusion_numero_inconnu),
        ("tâche dont le watcher est mort → ignorée, sans duplication du filtre (#947)", scenario_tache_watcher_mort_ignoree),
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
        finally:
            watchers_mod.projet_par_nom = ancien_projet_par_nom
            watchers_mod.watcher_actif = ancien_watcher_actif
            watchers_mod.tache_en_cours = ancien_tache_en_cours

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

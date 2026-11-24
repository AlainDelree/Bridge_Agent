#!/usr/bin/env python3
"""Tests — issue #950 (actions par issue sur la ligne de résultat).

Couvre les deux routes TOUCHÉES côté serveur par cette issue :

1. `app.issues.annuler_issue` (bouton « Annuler l'issue », en file) : refuse
   de fermer une issue qui a démarré entre-temps (route #947,
   `app.watchers.tache_en_cours` — même source que `/issues-en-cours`), et
   l'invite à utiliser « Interrompre » à la place ; ferme normalement sinon.
2. `app.issues.fermer_issue` (bouton « Fermer », needs-human/interrompue) :
   commentaire GitHub corrigé (plus de « intervention humaine effectuée »,
   trompeur — #938 point 2.1), et ne touche JAMAIS le watcher ni les autres
   issues (un seul appel `gh issue close`, rien d'autre).

La décision « quels boutons pour quel état » (en file/en cours/interrompue/
needs-human/terminée/interactive) est en logique PURE côté JS
(static/js/actions_ligne.js::boutonsActionLigne/mecanismeInterruptionLigne) —
testée sous Node, voir static/js/tests/actions_ligne.test.js (hors périmètre
de ce fichier Python).

`gh` est remplacé par un mock de `subprocess.run` (aucun appel réseau réel).

Exécution :  python3 tests/test_actions_ligne_950.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.issues as issues  # noqa: E402
import app.watchers as watchers_mod  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CFG = SimpleNamespace(nom="projetActions950", depot="AlainDelree/depot-actions950")


class FauxCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _appels_gh_issue_close(run_mock):
    """Filtre les appels subprocess.run qui sont RÉELLEMENT un `gh issue
    close` — annuler_issue/fermer_issue appellent aussi, en best-effort après
    coup, `maj_rate_limit` (etat_rate_limit._interroger_gh, lui-même un appel
    `gh api rate_limit` séparé) : sans ce filtre, le compte brut des appels
    subprocess ne reflète pas « combien de fermetures/actions gh ont eu
    lieu »."""
    return [c for c in run_mock.call_args_list
            if list(c.args[0][:3]) == ["gh", "issue", "close"]]


def _appeler_annuler(numero, taches_en_cours):
    with APP_FLASK.test_request_context("/annuler-issue"), \
         mock.patch.object(issues, "projet_par_nom", lambda n: CFG), \
         mock.patch.object(watchers_mod, "tache_en_cours", lambda c: taches_en_cours), \
         mock.patch("subprocess.run") as run_mock:
        run_mock.return_value = FauxCompletedProcess(returncode=0)
        resp = issues.annuler_issue(CFG.nom, numero)
    body = resp[0] if isinstance(resp, tuple) else resp
    return body.get_json(), _appels_gh_issue_close(run_mock)


def _appeler_fermer(numero):
    with APP_FLASK.test_request_context("/fermer-issue"), \
         mock.patch.object(issues, "projet_par_nom", lambda n: CFG), \
         mock.patch("subprocess.run") as run_mock:
        run_mock.return_value = FauxCompletedProcess(returncode=0)
        resp = issues.fermer_issue(CFG.nom, numero)
    body = resp[0] if isinstance(resp, tuple) else resp
    return body.get_json(), _appels_gh_issue_close(run_mock)


# ─── annuler_issue : course avec un démarrage entre-temps (issue #950, point 4) ─

def scenario_annuler_issue_en_file_est_fermee():
    corps, appels = _appeler_annuler(42, taches_en_cours=[])
    assert corps["succes"] is True, corps
    assert len(appels) == 1, "un seul `gh issue close` attendu"
    args = appels[0].args[0]
    assert "42" in args
    idx_comment = args.index("--comment")
    commentaire = args[idx_comment + 1]
    assert "avant traitement par le watcher" in commentaire, commentaire
    return {}


def scenario_annuler_issue_deja_en_cours_est_refusee():
    corps, appels = _appeler_annuler(
        43, taches_en_cours=[{"numero": 43, "mode": "ecriture", "rep": "x"}])
    assert corps["succes"] is False, corps
    assert "Interrompre" in corps["message"], corps
    assert not appels, "gh ne doit PAS être appelé si l'issue tourne déjà"
    return {}


def scenario_annuler_issue_autre_numero_en_cours_nest_pas_bloquee():
    # Une AUTRE issue du même projet tourne : ne doit jamais bloquer celle-ci
    # (portée stricte par numéro, même principe que #949).
    corps, appels = _appeler_annuler(
        44, taches_en_cours=[{"numero": 999, "mode": "ecriture", "rep": "x"}])
    assert corps["succes"] is True, corps
    assert len(appels) == 1
    return {}


def scenario_annuler_issue_numero_inconnu_en_verrou_nest_pas_bloquee():
    # Verrou ancien (posé avant #946) sans numéro=, donc numero=None côté
    # tache_en_cours — ne doit JAMAIS, par excès de prudence, bloquer une
    # fermeture légitime (seule une égalité STRICTE avec un numéro connu bloque,
    # même garde que app.watchers.issues_en_cours, voir sa docstring).
    corps, appels = _appeler_annuler(
        45, taches_en_cours=[{"numero": None, "mode": "ecriture", "rep": "x"}])
    assert corps["succes"] is True, corps
    assert len(appels) == 1
    return {}


def scenario_annuler_issue_projet_introuvable_404():
    with APP_FLASK.test_request_context("/annuler-issue"), \
         mock.patch.object(issues, "projet_par_nom", lambda n: None):
        resp = issues.annuler_issue("projet-inconnu-950", 1)
    body, code = resp
    assert code == 404, code
    assert body.get_json()["succes"] is False
    return {}


# ─── fermer_issue : commentaire corrigé, watcher jamais touché (point 5) ───

def scenario_fermer_issue_commentaire_corrige_sans_watcher():
    corps, appels = _appeler_fermer(46)
    assert corps["succes"] is True, corps
    assert len(appels) == 1, (
        "fermer_issue ne doit faire qu'UN seul `gh issue close` "
        "— jamais d'appel séparé touchant le watcher ou une autre issue")
    args = appels[0].args[0]
    idx_comment = args.index("--comment")
    commentaire = args[idx_comment + 1]
    assert commentaire == "Issue fermée manuellement depuis l'interface (new_issue.py).", commentaire
    # Texte trompeur de l'issue #938 point 2.1, explicitement absent désormais.
    assert "intervention humaine" not in commentaire.lower(), commentaire
    return {}


def scenario_fermer_issue_projet_introuvable_404():
    with APP_FLASK.test_request_context("/fermer-issue"), \
         mock.patch.object(issues, "projet_par_nom", lambda n: None):
        resp = issues.fermer_issue("projet-inconnu-950", 1)
    body, code = resp
    assert code == 404, code
    assert body.get_json()["succes"] is False
    return {}


def main():
    tests = [
        ("annuler_issue : en file (aucune tâche en cours) → fermée normalement",
         scenario_annuler_issue_en_file_est_fermee),
        ("annuler_issue : déjà en cours (même numéro) → refusée, invite à Interrompre",
         scenario_annuler_issue_deja_en_cours_est_refusee),
        ("annuler_issue : une AUTRE issue en cours → n'empêche pas celle-ci",
         scenario_annuler_issue_autre_numero_en_cours_nest_pas_bloquee),
        ("annuler_issue : verrou sans numéro connu → n'empêche pas (prudence, pas excès)",
         scenario_annuler_issue_numero_inconnu_en_verrou_nest_pas_bloquee),
        ("annuler_issue : projet introuvable → 404",
         scenario_annuler_issue_projet_introuvable_404),
        ("fermer_issue : commentaire corrigé, un seul appel gh (watcher jamais touché)",
         scenario_fermer_issue_commentaire_corrige_sans_watcher),
        ("fermer_issue : projet introuvable → 404",
         scenario_fermer_issue_projet_introuvable_404),
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

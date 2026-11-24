#!/usr/bin/env python3
"""Tests — issue #951 (fermeture propre d'une issue EN COURS depuis sa
ligne, avec avertissement quand l'issue est interactive).

La séquence « déposer la demande d'interruption ciblée (#949) → attendre
que l'issue ne figure plus parmi les issues en cours (#947) → fermer
seulement alors (#950) », ainsi que la fenêtre du cas interactif, sont
orchestrées CÔTÉ CLIENT (static/js/app.js — fermerIssueEnCoursDepuisLigne et
son arborescence), comme toute l'interaction par bouton de ligne depuis
#949/#950 : rien de nouveau n'est ajouté côté serveur pour cette
orchestration elle-même (aucune nouvelle route, les trois routes existantes
/demander-interruption-issue, /issues-en-cours et /fermer-issue suffisent),
non testable par ce fichier Python — voir static/js/tests/actions_ligne.test.js
pour la décision des boutons par état (boutonsActionLigne étendue par cette
issue) et VERIFICATIONS_MANUELLES.md pour la séquence réseau elle-même.

Ce fichier couvre le seul changement RÉEL côté serveur (issue #951, point 4) :
`app.issues.fermer_issue` retire désormais le label `needs-human` APRÈS
avoir fermé l'issue — sans quoi une issue fermée manuellement (y compris,
depuis cette issue, par la séquence normale ci-dessus, qui pose needs-human
comme étape intermédiaire avant de fermer) continuait à s'afficher comme un
« échec » (badge ⚠️ needs-human, `badgeLabel()` côté détail/recherche).

Vérifie :
1. Fermeture réussie → `gh issue close` PUIS `gh issue edit --remove-label
   needs-human`, dans cet ordre (jamais l'inverse — une issue encore
   ouverte sans needs-human redeviendrait éligible au prochain cycle du
   watcher).
2. Fermeture en échec (gh issue close en échec) → AUCUN retrait de label
   tenté (rien à retirer, l'issue n'est pas fermée).
3. Le retrait de label est best-effort STRICT : s'il échoue (ou lève), la
   réponse de la route reste `succes=True` — la fermeture elle-même a déjà
   réussi, ce second appel ne doit jamais la faire passer pour un échec.
4. Non-régression #950 : commentaire de fermeture inchangé, projet
   introuvable → 404.

`gh` est remplacé par un mock de `subprocess.run` (aucun appel réseau réel),
même technique que tests/test_actions_ligne_950.py.

Exécution :  python3 tests/test_fermeture_issue_en_cours_951.py
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

APP_FLASK = flask.Flask(__name__)

CFG = SimpleNamespace(nom="projetFermeture951", depot="AlainDelree/depot-fermeture951")


class FauxCompletedProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _appels(run_mock, *prefixe):
    prefixe = list(prefixe)
    n = len(prefixe)
    return [c for c in run_mock.call_args_list if list(c.args[0][:n]) == prefixe]


def _appeler_fermer(numero, resultats_par_sous_commande=None):
    """`resultats_par_sous_commande` : dict optionnel {("gh","issue","close"): FauxCompletedProcess(...), ...}
    — sinon succès (returncode=0) pour tout appel gh."""
    resultats_par_sous_commande = resultats_par_sous_commande or {}

    def _side_effect(args, **kwargs):
        for prefixe, resultat in resultats_par_sous_commande.items():
            if tuple(args[:len(prefixe)]) == prefixe:
                if isinstance(resultat, Exception):
                    raise resultat
                return resultat
        return FauxCompletedProcess(returncode=0)

    with APP_FLASK.test_request_context("/fermer-issue"), \
         mock.patch.object(issues, "projet_par_nom", lambda n: CFG), \
         mock.patch("subprocess.run", side_effect=_side_effect) as run_mock:
        resp = issues.fermer_issue(CFG.nom, numero)
    body = resp[0] if isinstance(resp, tuple) else resp
    return body.get_json(), run_mock


# ─── Scénario 1 : fermeture réussie → close PUIS remove-label needs-human ──

def scenario_fermeture_reussie_retire_needs_human_apres_coup():
    corps, run_mock = _appeler_fermer(951001)
    assert corps["succes"] is True, corps

    appels_close = _appels(run_mock, "gh", "issue", "close")
    appels_retrait = _appels(run_mock, "gh", "issue", "edit")
    assert len(appels_close) == 1, f"un seul `gh issue close` attendu : {appels_close}"
    assert len(appels_retrait) == 1, (
        f"un seul retrait de label needs-human attendu après une fermeture réussie : {appels_retrait}")

    args_retrait = appels_retrait[0].args[0]
    assert "--remove-label" in args_retrait, args_retrait
    idx = args_retrait.index("--remove-label")
    assert args_retrait[idx + 1] == "needs-human", args_retrait

    # Ordre : le retrait de label doit survenir APRÈS le close (jamais avant —
    # une issue encore ouverte sans needs-human redeviendrait éligible au
    # prochain cycle du watcher).
    tous = run_mock.call_args_list
    idx_close = next(i for i, c in enumerate(tous) if list(c.args[0][:3]) == ["gh", "issue", "close"])
    idx_edit = next(i for i, c in enumerate(tous) if list(c.args[0][:3]) == ["gh", "issue", "edit"])
    assert idx_close < idx_edit, "le retrait de needs-human doit survenir APRÈS la fermeture"
    return {}


# ─── Scénario 2 : fermeture en échec → aucun retrait de label tenté ────────

def scenario_fermeture_en_echec_ne_retire_rien():
    corps, run_mock = _appeler_fermer(951002, resultats_par_sous_commande={
        ("gh", "issue", "close"): FauxCompletedProcess(returncode=1, stderr="erreur gh simulée"),
    })
    assert corps["succes"] is False, corps
    appels_retrait = _appels(run_mock, "gh", "issue", "edit")
    assert not appels_retrait, "aucun retrait de label ne doit être tenté si la fermeture a échoué"
    return {}


# ─── Scénario 3 : retrait de label en échec → la fermeture reste un succès ─

def scenario_retrait_label_echoue_sans_faire_echouer_la_fermeture():
    corps, run_mock = _appeler_fermer(951003, resultats_par_sous_commande={
        ("gh", "issue", "edit"): FauxCompletedProcess(returncode=1, stderr="label absent, peu importe"),
    })
    assert corps["succes"] is True, (
        "un échec best-effort du retrait de label ne doit JAMAIS faire passer la fermeture pour un échec : "
        f"{corps}")
    return {}


def scenario_retrait_label_leve_une_exception_sans_faire_echouer_la_fermeture():
    corps, run_mock = _appeler_fermer(951004, resultats_par_sous_commande={
        ("gh", "issue", "edit"): RuntimeError("boom"),
    })
    assert corps["succes"] is True, (
        f"une exception sur le retrait de label (best-effort strict) ne doit pas remonter : {corps}")
    return {}


# ─── Scénario 4 : non-régression #950 ──────────────────────────────────────

def scenario_commentaire_fermeture_inchange():
    corps, run_mock = _appeler_fermer(951005)
    assert corps["succes"] is True, corps
    appels_close = _appels(run_mock, "gh", "issue", "close")
    args = appels_close[0].args[0]
    idx_comment = args.index("--comment")
    commentaire = args[idx_comment + 1]
    assert commentaire == "Issue fermée manuellement depuis l'interface (new_issue.py).", commentaire
    return {}


def scenario_projet_introuvable_404():
    with APP_FLASK.test_request_context("/fermer-issue"), \
         mock.patch.object(issues, "projet_par_nom", lambda n: None):
        resp = issues.fermer_issue("projet-inconnu-951", 1)
    body, code = resp
    assert code == 404, code
    assert body.get_json()["succes"] is False
    return {}


def main():
    tests = [
        ("fermer_issue : fermeture réussie → close PUIS retrait de needs-human",
         scenario_fermeture_reussie_retire_needs_human_apres_coup),
        ("fermer_issue : fermeture en échec → aucun retrait de label tenté",
         scenario_fermeture_en_echec_ne_retire_rien),
        ("fermer_issue : retrait de label en échec (returncode≠0) → succès conservé",
         scenario_retrait_label_echoue_sans_faire_echouer_la_fermeture),
        ("fermer_issue : retrait de label lève une exception → succès conservé",
         scenario_retrait_label_leve_une_exception_sans_faire_echouer_la_fermeture),
        ("fermer_issue : commentaire de fermeture inchangé (non-régression #950)",
         scenario_commentaire_fermeture_inchange),
        ("fermer_issue : projet introuvable → 404",
         scenario_projet_introuvable_404),
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

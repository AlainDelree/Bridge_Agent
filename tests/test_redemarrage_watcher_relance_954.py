#!/usr/bin/env python3
"""Test de non-régression — issue #954, point 3 (« Relancer »/« Interrompre et
relancer le watcher » du panneau Infrastructure, renommés « Redémarrer le
watcher ») : la confirmation/l'interruption ciblée (#949) de chaque issue en
cours/l'attente de leur arrêt (#947) et la relance individuelle (même route
que le bouton « Relancer » de la ligne) sont orchestrées CÔTÉ CLIENT
(static/js/interruption_projet.js) — ce test couvre uniquement la PARTIE
SERVEUR ajoutée par cette issue : la mémorisation/purge de la liste des
issues que la séquence va relancer, dans un fichier sous DOSSIER_LOGS (jamais
REP_TRAVAIL), et son branchement dans la route existante POST
/lancer-watcher + la nouvelle route POST /purger-issues-a-relancer.

Couvre :
1. `memoriser_issues_a_relancer` écrit un JSON trié/dédupliqué, sous
   DOSSIER_LOGS (pas REP_TRAVAIL) — scenario_memoriser_ecrit_sous_logs.
2. `purger_issues_a_relancer` supprime le fichier ; no-op si déjà absent —
   scenario_purger_supprime_et_noop_si_absent.
3. POST /lancer-watcher avec `issues_a_relancer` non vide : mémorise AVANT
   d'appeler demarrer_watcher_ou_differer — scenario_route_lancer_memorise.
4. POST /lancer-watcher SANS `issues_a_relancer` (ou vide) : comportement
   STRICTEMENT inchangé, rien n'est écrit —
   scenario_route_lancer_sans_issues_rien_ecrit.
5. POST /purger-issues-a-relancer : purge effective, `succes=True` même sans
   fichier, `succes=False` si projet inconnu —
   scenario_route_purger_*.

Exécution :  python3 tests/test_redemarrage_watcher_relance_954.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.watchers as watchers_mod  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CFG_TEST954 = SimpleNamespace(depot="AlainDelree/depot-test954", nom="projet954")


def _appeler_lancer_watcher(payload: dict):
    with APP_FLASK.test_request_context("/lancer-watcher", json=payload):
        return watchers_mod.lancer_watcher().get_json()


def _appeler_purger(payload: dict):
    with APP_FLASK.test_request_context("/purger-issues-a-relancer", json=payload):
        return watchers_mod.purger_issues_a_relancer_route().get_json()


def scenario_memoriser_ecrit_sous_logs():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_logs = watchers_mod.DOSSIER_LOGS
        watchers_mod.DOSSIER_LOGS = tmp_path / "logs"
        try:
            watchers_mod.memoriser_issues_a_relancer("projetA954", [12, 7, 7, 3])
            chemin = watchers_mod._chemin_issues_a_relancer("projetA954")
            assert str(chemin).startswith(str(watchers_mod.DOSSIER_LOGS)), (
                f"le fichier doit être sous DOSSIER_LOGS (jamais REP_TRAVAIL) : {chemin}")
            import json
            contenu = json.loads(chemin.read_text(encoding="utf-8"))
            assert contenu == [3, 7, 12], f"liste triée/dédupliquée attendue : {contenu}"
        finally:
            watchers_mod.DOSSIER_LOGS = ancien_dossier_logs
    return {}


def scenario_purger_supprime_et_noop_si_absent():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_logs = watchers_mod.DOSSIER_LOGS
        watchers_mod.DOSSIER_LOGS = tmp_path / "logs"
        try:
            watchers_mod.memoriser_issues_a_relancer("projetB954", [1, 2])
            chemin = watchers_mod._chemin_issues_a_relancer("projetB954")
            assert chemin.exists()
            watchers_mod.purger_issues_a_relancer("projetB954")
            assert not chemin.exists(), "le fichier aurait dû être supprimé"
            # Un second appel (fichier déjà absent) ne doit jamais lever.
            watchers_mod.purger_issues_a_relancer("projetB954")
        finally:
            watchers_mod.DOSSIER_LOGS = ancien_dossier_logs
    return {}


def scenario_route_lancer_memorise():
    """issues_a_relancer non vide : mémorisé AVANT l'appel à
    demarrer_watcher_ou_differer (même si celui-ci échoue, le fichier existe
    déjà — la séquence côté client décide alors de purger immédiatement,
    hors périmètre de ce test serveur)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_logs = watchers_mod.DOSSIER_LOGS
        watchers_mod.DOSSIER_LOGS = tmp_path / "logs"
        ancien_projet_par_nom = watchers_mod.projet_par_nom
        ancien_demarrer = watchers_mod.demarrer_watcher_ou_differer
        try:
            watchers_mod.projet_par_nom = lambda nom: CFG_TEST954
            watchers_mod.demarrer_watcher_ou_differer = lambda cfg, forcer: ("demarre", 1234)

            r = _appeler_lancer_watcher({"projet": "projet954", "relancer": True,
                                         "issues_a_relancer": [55, 56]})

            assert r["succes"] is True, r
            assert r["redemarré"] is True, r
            chemin = watchers_mod._chemin_issues_a_relancer("projet954")
            assert chemin.exists(), "la liste aurait dû être mémorisée avant le redémarrage"
            import json
            assert json.loads(chemin.read_text(encoding="utf-8")) == [55, 56]
        finally:
            watchers_mod.DOSSIER_LOGS = ancien_dossier_logs
            watchers_mod.projet_par_nom = ancien_projet_par_nom
            watchers_mod.demarrer_watcher_ou_differer = ancien_demarrer
    return {}


def scenario_route_lancer_sans_issues_rien_ecrit():
    """Comportement STRICTEMENT inchangé (issues_a_relancer absent ou vide) :
    aucun fichier écrit — non-régression pour tout appel existant
    (« Lancer » d'un watcher éteint, relances groupées du panneau...)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_logs = watchers_mod.DOSSIER_LOGS
        watchers_mod.DOSSIER_LOGS = tmp_path / "logs"
        ancien_projet_par_nom = watchers_mod.projet_par_nom
        ancien_demarrer = watchers_mod.demarrer_watcher_ou_differer
        try:
            watchers_mod.projet_par_nom = lambda nom: CFG_TEST954
            watchers_mod.demarrer_watcher_ou_differer = lambda cfg, forcer: ("demarre", 1)

            r = _appeler_lancer_watcher({"projet": "projet954", "relancer": True})
            assert r["succes"] is True, r
            assert not (watchers_mod.DOSSIER_LOGS / "redemarrages_watcher").exists(), (
                "aucun dossier de mémorisation n'aurait dû être créé")

            r2 = _appeler_lancer_watcher({"projet": "projet954", "relancer": True,
                                          "issues_a_relancer": []})
            assert r2["succes"] is True, r2
            assert not (watchers_mod.DOSSIER_LOGS / "redemarrages_watcher").exists()
        finally:
            watchers_mod.DOSSIER_LOGS = ancien_dossier_logs
            watchers_mod.projet_par_nom = ancien_projet_par_nom
            watchers_mod.demarrer_watcher_ou_differer = ancien_demarrer
    return {}


def scenario_route_purger_efficace_et_best_effort():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_logs = watchers_mod.DOSSIER_LOGS
        watchers_mod.DOSSIER_LOGS = tmp_path / "logs"
        ancien_projet_par_nom = watchers_mod.projet_par_nom
        try:
            watchers_mod.projet_par_nom = lambda nom: CFG_TEST954
            watchers_mod.memoriser_issues_a_relancer("projet954", [1])
            chemin = watchers_mod._chemin_issues_a_relancer("projet954")
            assert chemin.exists()

            r = _appeler_purger({"projet": "projet954"})
            assert r["succes"] is True, r
            assert not chemin.exists()

            # Déjà purgé : un second appel reste un succès (best-effort strict).
            r2 = _appeler_purger({"projet": "projet954"})
            assert r2["succes"] is True, r2
        finally:
            watchers_mod.DOSSIER_LOGS = ancien_dossier_logs
            watchers_mod.projet_par_nom = ancien_projet_par_nom
    return {}


def scenario_route_purger_projet_inconnu():
    ancien_projet_par_nom = watchers_mod.projet_par_nom
    try:
        watchers_mod.projet_par_nom = lambda nom: None
        r = _appeler_purger({"projet": "inconnu954"})
        assert r["succes"] is False, r
    finally:
        watchers_mod.projet_par_nom = ancien_projet_par_nom
    return {}


def main():
    tests = [
        ("memoriser_issues_a_relancer écrit sous DOSSIER_LOGS, trié/dédupliqué",
         scenario_memoriser_ecrit_sous_logs),
        ("purger_issues_a_relancer supprime, no-op si déjà absent",
         scenario_purger_supprime_et_noop_si_absent),
        ("POST /lancer-watcher avec issues_a_relancer : mémorise avant le redémarrage",
         scenario_route_lancer_memorise),
        ("POST /lancer-watcher sans issues_a_relancer : rien n'est écrit (inchangé)",
         scenario_route_lancer_sans_issues_rien_ecrit),
        ("POST /purger-issues-a-relancer : purge effective, best-effort",
         scenario_route_purger_efficace_et_best_effort),
        ("POST /purger-issues-a-relancer : projet inconnu → succes=False",
         scenario_route_purger_projet_inconnu),
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

#!/usr/bin/env python3
"""Test de non-régression — issue #721 : le bouton « 🔄 Relancer » d'une
ligne de l'onglet Résultats (`app/interruption.py::route_relancer`, issue
#460, §13) doit décocher la case « traité/lu » de l'issue relancée — même
intention que la relance par fichier RELANCE d'`issues_inbox/` (issue #720),
mais `route_relancer()` s'exécute dans le MÊME process (`new_issue.py`) que
l'état des cases : pas de notification réseau, appel direct à
`app/cases_cochees.py::decocher_et_diffuser` (facteur commun aux deux
chemins, qui décoche l'état serveur PUIS diffuse l'événement SSE
`case_decochee`, exactement comme #720).

État isolé par monkeypatch (même garde-fou que
tests/test_decoche_relance_720.py et tests/test_relancer_watcher_574.py) —
aucun appel `gh` réel :
- relance réussie, issue cochée → case décochée + événement SSE
  `case_decochee` diffusé à l'onglet déjà ouvert ;
- relance réussie, issue non cochée → aucun effet, aucune erreur ;
- relance refusée/en erreur (retrait du label needs-human en échec) → la
  case ne change pas, aucun événement diffusé ;
- dépôt sans projet configuré (`cfg` = None) → aucun crash, aucune décoche
  tentée (pas de case possible pour un projet non configuré localement) ;
- le comportement de `relancer_issue()` lui-même (labels, commentaire,
  `statut_global`) reste inchangé — simple ajout après coup, cf.
  tests/test_relancer_watcher_574.py qui continue de couvrir ce périmètre.

Exécution :  python3 -m pytest tests/test_decoche_bouton_relancer_721.py
"""

import json
import queue
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402
import pytest  # noqa: E402

import etat_cases_cochees as ecc  # noqa: E402
from app import interruption  # noqa: E402
import app.watchers as watchers_mod  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CFG_BRIDGE_AGENT = SimpleNamespace(depot="AlainDelree/Bridge_Agent", nom="bridge_agent")


# ─── Isolation de l'état serveur des cases (même garde-fou que #629/#720) ──
class _EtatIsole:
    def __enter__(self):
        self._ancien_chemin = ecc.CHEMIN_ETAT
        self._ancien_verrou = ecc.CHEMIN_VERROU
        self._tmp = tempfile.TemporaryDirectory()
        ecc.CHEMIN_ETAT = Path(self._tmp.name) / "etat_cases_cochees.json"
        ecc.CHEMIN_VERROU = ecc.CHEMIN_ETAT.with_suffix(".lock")
        return self

    def __exit__(self, *exc):
        ecc.CHEMIN_ETAT = self._ancien_chemin
        ecc.CHEMIN_VERROU = self._ancien_verrou
        self._tmp.cleanup()


def _reabonner() -> "queue.Queue":
    q = queue.Queue()
    APP_FLASK.config["FIN_ISSUE_ABONNES"] = [q]
    return q


def _payload(message: str) -> dict:
    ligne_data = message.split("data: ", 1)[1].strip()
    return json.loads(ligne_data)


def _neutraliser_gh(appels: dict):
    """Substitue les deux appels `gh` de relancer_issue() (retrait de label +
    commentaire), comme tests/test_relancer_watcher_574.py — aucun accès
    réseau."""
    def _faux_retrait(depot, numero, label):
        return "succes", f"Label « {label} » retiré."

    def _faux_commentaire(depot, numero, message):
        appels["commentaire"] = message
        return "succes", "Commentaire posté."

    interruption._retirer_label_gh = _faux_retrait
    interruption._commenter_gh = _faux_commentaire


def _appeler_relancer(payload: dict) -> dict:
    with APP_FLASK.test_request_context("/relancer-issue", json=payload):
        return interruption.route_relancer().get_json()


@pytest.fixture(autouse=True)
def _isoler_interruption():
    """Même garde-fou que tests/test_relancer_watcher_574.py — module
    singleton partagé par toute la session pytest."""
    noms = ("projet_par_depot", "_retirer_label_gh", "_commenter_gh",
            "demarrer_service_ccw_arriere_plan")
    originaux = {nom: getattr(interruption, nom) for nom in noms}
    watchers_original = watchers_mod.demarrer_watcher
    yield
    for nom, valeur in originaux.items():
        setattr(interruption, nom, valeur)
    watchers_mod.demarrer_watcher = watchers_original


def test_relance_reussie_decoche_issue_cochee_et_diffuse_evenement():
    with _EtatIsole():
        ecc.cocher_issue("bridge_agent", 77)
        q = _reabonner()
        appels = {}
        _neutraliser_gh(appels)
        interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT

        r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77,
                                "labels": ["bridge"]})

        assert r["succes"] and r["statut_global"] == "ok", r
        assert ecc.lire_cases_cochees("bridge_agent") == []
        message = q.get_nowait()
        assert message.startswith("event: case_decochee\n"), message
        assert _payload(message) == {"projet": "bridge_agent", "numero": 77}


def test_relance_reussie_issue_non_cochee_aucun_effet_aucune_erreur():
    with _EtatIsole():
        ecc.cocher_issue("bridge_agent", 1)   # une AUTRE issue, cochée
        q = _reabonner()
        appels = {}
        _neutraliser_gh(appels)
        interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT

        r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77,
                                "labels": ["bridge"]})

        assert r["succes"] and r["statut_global"] == "ok", r
        # idempotent : rien à retirer, l'état des AUTRES cases reste intact.
        assert ecc.lire_cases_cochees("bridge_agent") == [1]
        q.get_nowait()   # l'événement est quand même diffusé (idempotent côté front aussi, comme #720)


def test_relance_refusee_la_case_ne_change_pas():
    with _EtatIsole():
        ecc.cocher_issue("bridge_agent", 77)
        q = _reabonner()
        interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT
        interruption._retirer_label_gh = lambda depot, numero, label: ("echec", "gh: issue non trouvée")
        interruption._commenter_gh = lambda depot, numero, message: ("succes", "Commentaire posté.")

        r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77,
                                "labels": ["bridge"]})

        assert r["succes"], r
        assert r["statut_global"] == "echec", r
        assert ecc.lire_cases_cochees("bridge_agent") == [77], \
            "une relance en échec ne doit décocher personne"
        assert q.empty(), "aucun événement ne doit être diffusé si la relance échoue"


def test_depot_sans_projet_configure_aucune_decoche_aucun_crash():
    with _EtatIsole():
        ecc.cocher_issue("bridge_agent", 77)
        appels = {}
        _neutraliser_gh(appels)
        interruption.projet_par_depot = lambda depot: None

        r = _appeler_relancer({"depot": "AlainDelree/Depot-Inconnu", "numero": 5,
                                "labels": ["bridge"]})

        assert r["succes"] and r["statut_global"] == "ok", r
        # cfg=None : aucune case possible pour un dépôt non configuré
        # localement — l'état des AUTRES projets reste intact.
        assert ecc.lire_cases_cochees("bridge_agent") == [77]

#!/usr/bin/env python3
"""Test de non-régression — issue #720 : une RELANCE réussie (champ RELANCE
d'`issues_inbox/`, §3.14 du DOC, issue #516) doit décocher automatiquement la
case « traité/lu » de l'issue relancée dans l'onglet Résultats (état serveur
#629/#636, `logs/etat_cases_cochees.json`) — sinon elle apparaît comme déjà
lue alors qu'elle va produire un NOUVEAU résultat.

Deux couches couvertes séparément, comme l'exige la contrainte « le watcher
spool ne doit jamais écrire lui-même dans `logs/etat_cases_cochees.json` » :

1. `app/cases_cochees.py::notifier_case_decochee` (route POST, exécutée dans
   le process `new_issue.py`) — décoche réellement l'état serveur
   (`etat_cases_cochees.decocher_issue`, idempotente, isolée par
   `_EtatIsole` comme tests/test_cases_cochees_629.py) PUIS diffuse
   l'événement SSE `case_decochee` à tous les onglets déjà ouverts (même
   mécanisme que tests/test_evenements_issues_inbox_631.py) :
   - issue cochée → décochée + événement diffusé ;
   - issue non cochée → aucun effet, aucune erreur (idempotent) ;
   - requête incomplète → 400, rien n'est modifié ni diffusé.

2. `scripts/watcher_issues_inbox.py::_traiter_relance` (process séparé) —
   POSTe best-effort vers cette route via `_notifier_case_decochee`
   (interception de `_poster_best_effort`, comme
   tests/test_pas_de_ligne_fichier_recu_si_relance_719.py) :
   - relance réussie → POST avec (projet, numéro) corrects ;
   - relance refusée (issue introuvable/fermée) → AUCUN POST, la case ne
     doit pas changer ;
   - lot avec plusieurs RELANCE → un POST par issue relancée ;
   - lot mixte (RELANCE + création) → la création n'est pas affectée (même
     scénario que tests/test_champ_relance_516.py::scenario_5, enrichi) ;
   - `new_issue.py` non lancé : `_poster_best_effort` n'élève jamais
     d'exception (urllib intercepté), donc la relance elle-même reste
     réussie — seule la décoche est perdue, silencieusement.

Aucun appel réseau ni `gh` réel.

Exécution :  python3 -m pytest tests/test_decoche_relance_720.py
"""

import json
import os
import queue
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402
import pytest  # noqa: E402

import etat_cases_cochees as ecc  # noqa: E402
from app import cases_cochees as route_cc  # noqa: E402
import app.watchers as watchers_mod  # noqa: E402
import utils  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402

APP_FLASK = flask.Flask(__name__)


# ─── Isolation de l'état serveur des cases (même garde-fou que #629) ────────
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


# ─────────────────────────────────────────────────────────────────────────
# 1. Route Flask app/cases_cochees.py::notifier_case_decochee
# ─────────────────────────────────────────────────────────────────────────

def test_route_decoche_issue_cochee_et_diffuse_evenement():
    with _EtatIsole():
        ecc.cocher_issue("bridge_agent", 629)
        q = _reabonner()
        with APP_FLASK.test_request_context(
                "/notifier-case-decochee", method="POST",
                json={"projet": "bridge_agent", "numero": 629}):
            rep = route_cc.notifier_case_decochee()
        assert rep.get_json()["ok"] is True
        assert ecc.lire_cases_cochees("bridge_agent") == []
        message = q.get_nowait()
        assert message.startswith("event: case_decochee\n"), message
        assert _payload(message) == {"projet": "bridge_agent", "numero": 629}


def test_route_decoche_issue_non_cochee_aucun_effet_aucune_erreur():
    with _EtatIsole():
        ecc.cocher_issue("bridge_agent", 1)   # une AUTRE issue, cochée
        q = _reabonner()
        with APP_FLASK.test_request_context(
                "/notifier-case-decochee", method="POST",
                json={"projet": "bridge_agent", "numero": 629}):
            rep = route_cc.notifier_case_decochee()
        assert rep.get_json()["ok"] is True
        # idempotent : rien à retirer, l'état des AUTRES cases reste intact.
        assert ecc.lire_cases_cochees("bridge_agent") == [1]
        q.get_nowait()   # l'événement est quand même diffusé (idempotent côté front aussi)


def test_route_champs_manquants_400_rien_modifie():
    with _EtatIsole():
        ecc.cocher_issue("bridge_agent", 629)
        with APP_FLASK.test_request_context(
                "/notifier-case-decochee", method="POST", json={"projet": "bridge_agent"}):
            rep, code = route_cc.notifier_case_decochee()
        assert code == 400
        assert rep.get_json()["ok"] is False
        assert ecc.lire_cases_cochees("bridge_agent") == [629], \
            "une requête incomplète ne doit décocher personne"


# ─────────────────────────────────────────────────────────────────────────
# 2. scripts/watcher_issues_inbox.py — appel best-effort depuis _traiter_relance
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isoler_watcher_issues_inbox():
    """Même garde-fou que tests/test_champ_relance_516.py et tests/
    test_pas_de_ligne_fichier_recu_si_relance_719.py — module singleton
    partagé par toute la session pytest."""
    noms = ("_creer_issue", "_issue_ouverte_meme_titre", "_poster_best_effort",
            "_recuperer_issue", "_modifier_corps_gh", "relancer_issue",
            "demarrer_service_ccw_arriere_plan", "DOSSIER_SCRIPT", "charger_config")
    originaux = {nom: getattr(w, nom) for nom in noms}
    watchers_original = watchers_mod.demarrer_watcher
    yield
    for nom, valeur in originaux.items():
        setattr(w, nom, valeur)
    watchers_mod.demarrer_watcher = watchers_original


def _cfg_projet(depot="AlainDelree/Bridge_Agent", nom="bridge_agent", rep_travail=None,
                 perimetre_dynamique=False):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            max_essais=3, rep_travail=rep_travail or Path(tempfile.gettempdir()),
                            perimetre_dynamique=perimetre_dynamique)


def _preparer_cfg(tmp_dir: Path, projets=("bridge_agent",)) -> "w.ConfigInbox":
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    for projet in projets:
        (tmp_dir / "configs" / f"{projet}.conf").write_text(
            "DEPOT=AlainDelree/Bridge_Agent\n", encoding="utf-8")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet(rep_travail=tmp_dir, nom=chemin.stem)
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _deposer(chemin: Path, contenu: str) -> None:
    chemin.write_text(contenu, encoding="utf-8")
    os.utime(chemin, (time.time() - 5, time.time() - 5))  # passe le seuil _fichier_pret (1s)


def _appel_ccw_interdit(*_a, **_k):
    raise AssertionError("demarrer_service_ccw_arriere_plan n'aurait pas dû être appelé.")


def _neutraliser_relance_succes(numeros=(126,), depot="AlainDelree/Bridge_Agent",
                                 labels=("bridge", "for-linux")):
    def _fausse_recuperation(depot_appel, numero):
        assert numero in numeros, f"numéro inattendu : {numero}"
        return True, "", {
            "number": numero, "state": "OPEN", "title": f"Issue #{numero}",
            "body": "| PROJET | bridge_agent |\n",
            "labels": [{"name": l} for l in labels],
        }

    w._recuperer_issue = _fausse_recuperation
    w._modifier_corps_gh = lambda depot_appel, numero, corps: (True, "")
    w.relancer_issue = lambda depot_appel, numero, commentaire="": (
        "ok", [{"etape": "retrait_label_needs_human", "statut": "succes", "message": ""}])
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)
    w.demarrer_service_ccw_arriere_plan = _appel_ccw_interdit


def _neutraliser_relance_echec(numero: int, motif: str = "introuvable"):
    w._recuperer_issue = lambda depot_appel, numero_appel: (False, motif, None)
    w.demarrer_service_ccw_arriere_plan = _appel_ccw_interdit


def _neutraliser_creation(numero_depart: int = 1):
    compteur = {"n": numero_depart}

    def _creer(cfg_i, cfg_p, titre, labels, body):
        url = f"https://github.com/AlainDelree/Bridge_Agent/issues/{compteur['n']}"
        compteur["n"] += 1
        return True, url

    w._creer_issue = _creer
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)


def _decoches(appels: list) -> list:
    return [p for u, p in appels if u == w.URL_NOTIFIER_CASE_DECOCHEE]


def test_relance_reussie_poste_decoche_bon_projet_numero(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("decoche1")
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126,))

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    contenu = "| PROJET | bridge_agent |\n| RELANCE | #126 |\n\nRelance.\n"
    champs = w.extraire_champs(contenu)
    succes, *_ = w._traiter_relance(cfg, champs)

    assert succes
    assert _decoches(appels) == [{"projet": "bridge_agent", "numero": 126}], appels


def test_relance_refusee_aucune_decoche(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("decoche2")
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_echec(126, motif="issue #126 introuvable")

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    contenu = "| PROJET | bridge_agent |\n| RELANCE | #126 |\n\nRelance.\n"
    champs = w.extraire_champs(contenu)
    succes, *_ = w._traiter_relance(cfg, champs)

    assert not succes
    assert _decoches(appels) == [], appels


def test_relance_issue_fermee_aucune_decoche(tmp_path_factory):
    """Dépôt correct mais issue fermée : rejetée AVANT relancer_issue, donc
    aucune décoche — la case ne doit pas changer pour une relance refusée."""
    tmp = tmp_path_factory.mktemp("decoche3")
    cfg = _preparer_cfg(tmp)

    def _fausse_recuperation(depot, numero):
        return True, "", {"number": numero, "state": "CLOSED", "title": "Ancienne tâche", "body": ""}
    w._recuperer_issue = _fausse_recuperation

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    contenu = "| PROJET | bridge_agent |\n| RELANCE | #99 |\n"
    champs = w.extraire_champs(contenu)
    succes, *_ = w._traiter_relance(cfg, champs)

    assert not succes
    assert _decoches(appels) == [], appels


def test_lot_plusieurs_relance_chaque_issue_decochee(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("decoche4")
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126, 127))

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé : lot entièrement RELANCE")
    w._creer_issue = _jamais_appele

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot_relance.txt"
    _deposer(chemin,
             "#Titre: Relance un\n| PROJET | bridge_agent |\n| RELANCE | #126 |\nCorps1.\n"
             "#Titre: Relance deux\n| PROJET | bridge_agent |\n| RELANCE | #127 |\nCorps2.\n")

    w.traiter_fichier(cfg, chemin)

    assert _decoches(appels) == [{"projet": "bridge_agent", "numero": 126},
                                  {"projet": "bridge_agent", "numero": 127}], appels


def test_lot_mixte_relance_et_creation_creation_inchangee(tmp_path_factory):
    """Lot mixte (RELANCE + création normale) : la création garde son
    comportement normal (même issue ouverte, même URL gh) ET l'issue
    relancée est décochée — les deux chemins ne se gênent pas."""
    tmp = tmp_path_factory.mktemp("decoche5")
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126,))
    _neutraliser_creation()

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot.txt"
    _deposer(chemin,
             "#Titre: Bloc création\n| PROJET | bridge_agent |\nCorps1.\n"
             "#Titre: Bloc relance\n| PROJET | bridge_agent |\n| RELANCE | #126 |\nCorps2.\n")

    w.traiter_fichier(cfg, chemin)

    assert _decoches(appels) == [{"projet": "bridge_agent", "numero": 126}], appels
    creations = [p for u, p in appels if u == w.URL_NOTIFIER_CREATION_ISSUE]
    assert len(creations) == 1 and creations[0]["titre"] == "Bloc création", appels


def test_new_issue_non_lance_relance_reussit_decoche_perdue_sans_erreur(
        monkeypatch, tmp_path_factory):
    """`new_issue.py` éteint (urllib échoue) : _poster_best_effort n'élève
    JAMAIS d'exception — la relance elle-même doit donc rester réussie,
    seule la décoche best-effort est perdue, silencieusement. Force la
    neutralisation de test à off (échappatoire #635) pour exercer le VRAI
    chemin urllib de _poster_best_effort."""
    monkeypatch.setenv("BRIDGE_AGENT_NOTIFS_RESEAU_FORCEES", "1")
    assert utils.notifications_reseau_neutralisees() is False

    def _urlopen_en_panne(*_a, **_k):
        raise ConnectionRefusedError("new_issue.py n'est pas lancé")
    monkeypatch.setattr(urllib.request, "urlopen", _urlopen_en_panne)

    tmp = tmp_path_factory.mktemp("decoche6")
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126,))

    contenu = "| PROJET | bridge_agent |\n| RELANCE | #126 |\n\nRelance.\n"
    champs = w.extraire_champs(contenu)
    succes, titre, projet, texte, *_ = w._traiter_relance(cfg, champs)

    assert succes, texte   # la relance réussit malgré l'échec silencieux de la décoche

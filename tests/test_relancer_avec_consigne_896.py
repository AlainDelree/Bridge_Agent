#!/usr/bin/env python3
"""Test de non-régression — issue #896 : route POST
`/issues-inbox/relancer-avec-consigne` (app/issues_inbox.py), qui relie le
bouton ⛔ « Interrompre » (app/interruption.py, pose needs-human SANS fermer
l'issue ni toucher au worktree) au champ `RELANCE` d'`issues_inbox/`
(§3.14 BRIDGE_AGENT_DOC.md) : dépose un fichier RELANCE avec la consigne
corrigée et/ou le nouveau TIMEOUT, sans recréer de nouvelle issue et sans
dupliquer la validation de `watcher_issues_inbox.py::_traiter_relance`
(exécutée à part, en asynchrone, par le watcher spool — hors périmètre de
cette route).

Couvre : format du fichier déposé (en-tête PROJET/RELANCE/TIMEOUT + texte
libre), rejet si projet/numéro invalide ou si consigne ET TIMEOUT sont vides
tous les deux, et démarrage à la demande du watcher spool SEULEMENT s'il est
éteint (jamais de redémarrage d'un watcher déjà actif — couperait le
traitement d'un autre fichier en cours, voir docstring de
`demarrer_watcher_inbox`).

Exécution :  python3 -m pytest tests/test_relancer_avec_consigne_896.py
"""

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402
import pytest  # noqa: E402

from app import issues_inbox  # noqa: E402
from watcher_issues_inbox import ConfigInbox  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CFG_PROJET = SimpleNamespace(nom="bridge_agent", depot="AlainDelree/Bridge_Agent")


@pytest.fixture()
def tmp_inbox():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = ConfigInbox(inbox_dir=Path(tmp) / "issues_inbox",
                           rejected_dir=Path(tmp) / "issues_inbox" / "rejected")
        yield cfg


@pytest.fixture(autouse=True)
def _isoler(tmp_inbox):
    originaux = {
        "_config": issues_inbox._config,
        "projet_par_nom": issues_inbox.projet_par_nom,
        "watcher_inbox_actif": issues_inbox.watcher_inbox_actif,
        "demarrer_watcher_inbox": issues_inbox.demarrer_watcher_inbox,
    }
    issues_inbox._config = lambda: tmp_inbox
    issues_inbox.projet_par_nom = lambda nom: CFG_PROJET if nom == "bridge_agent" else None
    yield tmp_inbox
    for nom, valeur in originaux.items():
        setattr(issues_inbox, nom, valeur)


def _appeler(payload: dict) -> dict:
    with APP_FLASK.test_request_context("/issues-inbox/relancer-avec-consigne", json=payload):
        reponse = issues_inbox.relancer_avec_consigne()
    if isinstance(reponse, tuple):
        corps, _code = reponse
        return corps.get_json()
    return reponse.get_json()


def test_fichier_depose_contient_entete_relance_et_texte_libre(tmp_inbox):
    issues_inbox.watcher_inbox_actif = lambda: (True, 4242)  # déjà actif : pas de démarrage

    r = _appeler({"projet": "bridge_agent", "numero": 612,
                  "texte": "Le TIMEOUT était trop court.", "timeout_s": 1800})

    assert r["succes"], r
    assert r["watcher_actif"] is True
    assert r["watcher_demarre"] is False

    fichier = tmp_inbox.inbox_dir / r["fichier"]
    assert fichier.is_file()
    contenu = fichier.read_text(encoding="utf-8")
    assert "| PROJET  | bridge_agent |" in contenu
    assert "| RELANCE | #612 |" in contenu
    assert "| TIMEOUT | 1800s |" in contenu
    assert "Le TIMEOUT était trop court." in contenu


def test_timeout_seul_sans_texte_autorise(tmp_inbox):
    issues_inbox.watcher_inbox_actif = lambda: (True, 1)

    r = _appeler({"projet": "bridge_agent", "numero": 7, "texte": "", "timeout_s": 2400})

    assert r["succes"], r
    contenu = (tmp_inbox.inbox_dir / r["fichier"]).read_text(encoding="utf-8")
    assert "| TIMEOUT | 2400s |" in contenu
    assert "| RELANCE | #7 |" in contenu


def test_texte_seul_sans_timeout_autorise(tmp_inbox):
    issues_inbox.watcher_inbox_actif = lambda: (True, 1)

    r = _appeler({"projet": "bridge_agent", "numero": 7, "texte": "Nouvelle consigne."})

    assert r["succes"], r
    contenu = (tmp_inbox.inbox_dir / r["fichier"]).read_text(encoding="utf-8")
    assert "TIMEOUT" not in contenu
    assert "Nouvelle consigne." in contenu


def test_rejet_si_texte_et_timeout_tous_deux_vides():
    issues_inbox.watcher_inbox_actif = lambda: (True, 1)

    r = _appeler({"projet": "bridge_agent", "numero": 7, "texte": "  ", "timeout_s": ""})

    assert not r["succes"]
    assert "Rien à corriger" in r["erreur"]


def test_rejet_si_projet_inconnu():
    r = _appeler({"projet": "projet_fantome", "numero": 7, "texte": "x"})
    assert not r["succes"]
    assert "introuvable" in r["erreur"]


def test_rejet_si_numero_invalide():
    r = _appeler({"projet": "bridge_agent", "numero": "abc", "texte": "x"})
    assert not r["succes"]
    assert "invalide" in r["erreur"]


def test_rejet_si_timeout_non_numerique():
    r = _appeler({"projet": "bridge_agent", "numero": 7, "texte": "x", "timeout_s": "pas-un-nombre"})
    assert not r["succes"]
    assert "TIMEOUT" in r["erreur"]


def test_rejet_si_timeout_negatif_ou_nul():
    r = _appeler({"projet": "bridge_agent", "numero": 7, "texte": "x", "timeout_s": 0})
    assert not r["succes"]
    assert "positif" in r["erreur"]


def test_demarre_watcher_spool_si_eteint(tmp_inbox):
    appels = {"demarre": 0}
    issues_inbox.watcher_inbox_actif = lambda: (False, None)

    def _faux_demarrage(duree_min=0):
        appels["demarre"] += 1
        return True, 9999

    issues_inbox.demarrer_watcher_inbox = _faux_demarrage

    r = _appeler({"projet": "bridge_agent", "numero": 7, "texte": "x"})

    assert r["succes"], r
    assert r["watcher_demarre"] is True
    assert r["watcher_pid"] == 9999
    assert appels["demarre"] == 1


def test_ne_redemarre_jamais_un_watcher_spool_deja_actif():
    """Un redémarrage couperait le traitement d'un AUTRE fichier en cours
    (voir docstring de demarrer_watcher_inbox, issue #485) — jamais appelé
    ici si le watcher tourne déjà."""
    issues_inbox.watcher_inbox_actif = lambda: (True, 123)

    def _demarrage_interdit(duree_min=0):
        raise AssertionError("demarrer_watcher_inbox n'aurait pas dû être appelé "
                              "pour un watcher déjà actif (issue #896)")

    issues_inbox.demarrer_watcher_inbox = _demarrage_interdit

    r = _appeler({"projet": "bridge_agent", "numero": 7, "texte": "x"})

    assert r["succes"], r
    assert r["watcher_demarre"] is False
    assert r["watcher_pid"] == 123


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))

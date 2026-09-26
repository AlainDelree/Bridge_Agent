#!/usr/bin/env python3
"""Test de non-régression — issue #635 : plus jamais de POST best-effort réel
depuis les tests vers un `new_issue.py` lancé sur le poste (toasts « mise à
jour impossible » pour des projets fictifs pendant la suite de tests, voir
tests/test_worktree_parallelisation_337.py, qui exerce le vrai code de
watcher.py de bout en bout).

Couvre :
- `utils.notifications_reseau_neutralisees()` : True pendant un run pytest
  (toujours le cas ici) et pour un script exécuté directement depuis
  `tests/` (simulé en monkeypatchant `sys.modules['__main__']`) ; False hors
  contexte de test, et pour l'échappatoire explicite
  `BRIDGE_AGENT_NOTIFS_RESEAU_FORCEES=1` ;
- `traitement_fin._notifier` (donc `notifier_fin_issue`/`notifier_debut_issue`)
  et `watcher_issues_inbox._poster_best_effort` : n'appellent JAMAIS
  `urllib.request.urlopen` pendant la suite — un envoi réel échouerait ce
  test (assertion sur une liste d'appels interceptés, vide).

Exécution :  python3 -m pytest tests/test_neutralisation_notifs_reseau_635.py
"""

import sys
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import utils  # noqa: E402
import traitement_fin  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402


def test_neutralisation_active_pendant_pytest():
    assert utils.notifications_reseau_neutralisees() is True


def test_echappatoire_explicite_reactive_les_envois(monkeypatch):
    monkeypatch.setenv("BRIDGE_AGENT_NOTIFS_RESEAU_FORCEES", "1")
    assert utils.notifications_reseau_neutralisees() is False


def test_detection_script_tests_direct_hors_pytest(monkeypatch):
    """Simule l'exécution directe d'un script `tests/test_xxx.py` (sans
    passer par pytest) : `sys.modules['__main__']` pointe alors vers ce
    fichier — c'est le cas réel de tests/test_worktree_parallelisation_337.py.
    Teste `_script_tests_direct()` isolément (sans toucher à `sys.modules
    ['pytest']`, dont dépend le process de test lui-même)."""
    faux_principal = types.SimpleNamespace(__file__=str(RACINE / "tests" / "un_script.py"))
    monkeypatch.setitem(sys.modules, "__main__", faux_principal)
    assert utils._script_tests_direct() is True


def test_detection_absente_hors_tests(monkeypatch):
    faux_principal = types.SimpleNamespace(__file__=str(RACINE / "watcher.py"))
    monkeypatch.setitem(sys.modules, "__main__", faux_principal)
    assert utils._script_tests_direct() is False


def test_notifier_fin_issue_naccede_jamais_au_reseau(monkeypatch):
    appels = []
    monkeypatch.setattr(
        traitement_fin.urllib.request, "urlopen",
        lambda *a, **k: appels.append((a, k)),
    )
    traitement_fin.notifier_fin_issue("test611par", 93375)
    traitement_fin.notifier_debut_issue("test576max1", 93761)
    assert appels == []


def test_poster_best_effort_naccede_jamais_au_reseau(monkeypatch):
    appels = []
    monkeypatch.setattr(
        w.urllib.request, "urlopen",
        lambda *a, **k: appels.append((a, k)),
    )
    w._notifier_fichier_recu("faux_fichier.txt")
    w._notifier_creation_issue("test576max2", 93764, "titre fictif")
    assert appels == []

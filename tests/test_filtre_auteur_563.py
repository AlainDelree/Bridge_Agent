#!/usr/bin/env python3
"""Test de non-régression — issue #563 : garde-fou explicite sur l'AUTEUR
d'une issue dans `lister_issues()`, en complément du filtre par labels (#477).

Jusqu'ici, la seule protection contre une issue créée par un tiers était
INDIRECTE (poser un label exige les droits d'écriture sur le dépôt). Ce test
vérifie que `lister_issues()` :
- laisse passer une issue correctement labellisée ET dont l'auteur figure
  dans `AUTEURS_AUTORISES` (ex. AlainDelree) ;
- ignore une issue correctement labellisée mais dont l'auteur N'EST PAS dans
  `AUTEURS_AUTORISES`, avec un `log.warning` explicite (pas un filtrage
  silencieux, à la différence du filtre #477 sur les labels).

`gh issue list` est simulé via un mock de `subprocess.run` (aucun accès
réseau). Le champ `author` du JSON simulé suit le format réel de
`gh --json author` : `{"login": "...", ...}`.

Exécution :  python3 tests/test_filtre_auteur_563.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import logging
import sys
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def _issue_gh(numero, auteur, labels=("for-linux",)):
    """Fabrique une entrée JSON telle que renvoyée par `gh issue list --json
    number,title,body,labels,createdAt,author`."""
    return {
        "number": numero,
        "title": f"issue #{numero}",
        "body": "",
        "labels": [{"name": l} for l in labels],
        "createdAt": "2026-09-17T10:00:00Z",
        "author": {"login": auteur},
    }


class _CaptureLog(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _executer_lister_issues(issues_brutes):
    """Appelle watcher.lister_issues() avec `gh issue list` simulé, CFG minimal,
    et capture les logs émis. Renvoie (issues_retenues, records_warning)."""
    fake_res = mock.Mock(
        returncode=0,
        stdout=json.dumps(issues_brutes),
        stderr="",
    )

    watcher.CFG = watcher.Config(
        nom="test_auteur_563",
        depot="exemple/depot-test",
        rep_travail=Path("/tmp/rep_test_auteur_563"),
        topic_ntfy="test-topic",
        label="for-linux",
    )

    capture = _CaptureLog()
    capture.setLevel(logging.WARNING)
    watcher.log.addHandler(capture)
    try:
        with mock.patch.object(watcher.subprocess, "run", return_value=fake_res):
            issues = watcher.lister_issues()
    finally:
        watcher.log.removeHandler(capture)

    return issues, capture.records


def scenario_auteur_autorise_passe():
    """Une issue bien labellisée, auteur AlainDelree (autorisé) : retenue,
    aucun warning émis."""
    brutes = [_issue_gh(100, "AlainDelree")]
    issues, warnings = _executer_lister_issues(brutes)
    assert [i["number"] for i in issues] == [100], (
        f"L'issue d'un auteur autorisé aurait dû être retenue : {issues}"
    )
    assert not warnings, f"Aucun warning attendu pour un auteur autorisé : {warnings}"


def scenario_auteur_non_autorise_ignoree_avec_log():
    """Une issue bien labellisée, mais dont l'auteur N'EST PAS dans
    AUTEURS_AUTORISES : ignorée, ET un log.warning explicite est émis (pas un
    simple non-match silencieux comme pour le filtre #477 sur les labels)."""
    brutes = [_issue_gh(101, "un_collaborateur_quelconque")]
    issues, warnings = _executer_lister_issues(brutes)
    assert issues == [], (
        f"L'issue d'un auteur non autorisé n'aurait pas dû être retenue : {issues}"
    )
    assert len(warnings) == 1, (
        f"Un log.warning explicite était attendu (issue labellisée mais auteur "
        f"non autorisé) : {warnings}"
    )
    message = warnings[0].getMessage()
    assert "101" in message and "un_collaborateur_quelconque" in message, (
        f"Le log doit identifier le numéro d'issue et l'auteur rejeté : {message}"
    )


def scenario_mixte_seul_l_autorise_survit():
    """Deux issues éligibles par labels, un seul auteur autorisé : seule
    l'issue de l'auteur autorisé survit, avec un unique warning pour l'autre."""
    brutes = [_issue_gh(102, "AlainDelree"), _issue_gh(103, "quelquun_dautre")]
    issues, warnings = _executer_lister_issues(brutes)
    assert [i["number"] for i in issues] == [102], (
        f"Seule l'issue #102 (auteur autorisé) aurait dû survivre : {issues}"
    )
    assert len(warnings) == 1 and "103" in warnings[0].getMessage()


def scenario_filtre_477_toujours_actif():
    """Contrôle de non-régression : le filtre existant sur les labels (#477)
    continue d'ignorer SILENCIEUSEMENT (pas de warning) une issue sans label
    for-linux/for-windows, même si l'auteur est autorisé."""
    brutes = [_issue_gh(104, "AlainDelree", labels=("autre-label",))]
    issues, warnings = _executer_lister_issues(brutes)
    assert issues == [], "Le filtre #477 sur les labels doit rester actif."
    assert not warnings, (
        "Le filtre #477 (labels) doit rester silencieux, à la différence du "
        "filtre #563 (auteur)."
    )


def main():
    tests = [
        ("auteur autorisé → retenue, pas de warning", scenario_auteur_autorise_passe),
        ("auteur non autorisé → ignorée + log.warning explicite",
         scenario_auteur_non_autorise_ignoree_avec_log),
        ("mélange autorisé/non-autorisé → seul l'autorisé survit",
         scenario_mixte_seul_l_autorise_survit),
        ("filtre #477 (labels) toujours silencieux", scenario_filtre_477_toujours_actif),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
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

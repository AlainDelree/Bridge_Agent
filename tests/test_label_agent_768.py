#!/usr/bin/env python3
"""Test de non-régression — issue #768.

Couvre :
- `Config.label_agent` dérive le label GitHub ("agent-claude", "agent-vibe")
  de CFG.agent, et non de la plateforme (contrairement à
  libelle_agent_effectif, issue #239/#767).
- `fermer_issue()` pose ce label en même temps que LABEL_FAIT, à la clôture.
- Best-effort strict (issue #768) : un échec de pose du label d'agent (ex.
  label absent du dépôt) ne doit JAMAIS faire échouer `fermer_issue()` ni
  changer sa valeur de retour — seul `close` + `--add-label done` comptent.

Aucun appel réseau réel : `subprocess.run` est monkeypatché dans `watcher`.

Exécution :  python3 tests/test_label_agent_768.py
"""

import sys
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def scenario_1_label_agent_derive_de_cfg_agent():
    """Config.label_agent reflète CFG.agent ('claude'/'vibe'), jamais la
    plateforme — à la différence de libelle_agent_effectif."""
    cfg_claude = watcher.Config(nom="x", depot="x/x", rep_travail=Path("/tmp"), agent="claude")
    cfg_vibe = watcher.Config(nom="x", depot="x/x", rep_travail=Path("/tmp"), agent="vibe")

    assert cfg_claude.label_agent == "agent-claude", cfg_claude.label_agent
    assert cfg_vibe.label_agent == "agent-vibe", cfg_vibe.label_agent
    return {"agent-claude": cfg_claude.label_agent, "agent-vibe": cfg_vibe.label_agent}


def scenario_2_fermer_issue_pose_label_fait_et_label_agent():
    """fermer_issue() doit tenter les TROIS sous-commandes (close, add-label
    done, add-label agent-claude) quand tout réussit."""
    appels = {"close": 0, "edit_done": 0, "edit_agent": 0}

    def fake_run(cmd, **kwargs):
        res = mock.Mock()
        res.returncode = 0
        res.stdout = ""
        res.stderr = ""
        if "close" in cmd:
            appels["close"] += 1
        elif "--add-label" in cmd and watcher.LABEL_FAIT in cmd:
            appels["edit_done"] += 1
        elif "--add-label" in cmd and "agent-claude" in cmd:
            appels["edit_agent"] += 1
        else:
            raise AssertionError(f"commande inattendue : {cmd}")
        return res

    with mock.patch.object(watcher, "CFG", mock.Mock(
                depot="exemple/depot-test", agent="claude",
                label_agent="agent-claude")), \
         mock.patch.object(watcher.subprocess, "run", fake_run), \
         mock.patch.object(watcher, "etat_rate_limit", mock.Mock()):
        resultat = watcher.fermer_issue(123)

    assert resultat is True, "fermer_issue doit réussir quand close + label done réussissent"
    assert appels == {"close": 1, "edit_done": 1, "edit_agent": 1}, appels
    return appels


def scenario_3_echec_label_agent_best_effort_sans_impact():
    """Le label d'agent n'existe pas encore sur ce dépôt (gh retourne un code
    non nul, comme pour un label manquant) : fermer_issue() doit malgré tout
    réussir (close + label 'done' OK), SANS lever ni changer son résultat."""
    appels = {"edit_agent": 0}

    def fake_run(cmd, **kwargs):
        res = mock.Mock()
        res.stdout = ""
        if "close" in cmd:
            res.returncode = 0
            res.stderr = ""
        elif "--add-label" in cmd and watcher.LABEL_FAIT in cmd:
            res.returncode = 0
            res.stderr = ""
        elif "--add-label" in cmd and "agent-claude" in cmd:
            appels["edit_agent"] += 1
            res.returncode = 1  # label absent du dépôt (comme #648)
            res.stderr = "could not add label: 'agent-claude' not found"
        else:
            raise AssertionError(f"commande inattendue : {cmd}")
        return res

    with mock.patch.object(watcher, "CFG", mock.Mock(
                depot="exemple/depot-test", agent="claude",
                label_agent="agent-claude")), \
         mock.patch.object(watcher.subprocess, "run", fake_run), \
         mock.patch.object(watcher, "etat_rate_limit", mock.Mock()):
        resultat = watcher.fermer_issue(124)

    assert resultat is True, (
        "fermer_issue doit réussir même si le label d'agent échoue (best-effort, issue #768)"
    )
    assert appels["edit_agent"] == 1, "la pose du label d'agent doit être tentée"
    return appels


def main() -> int:
    tests = [
        ("Config.label_agent dérive de CFG.agent (pas de la plateforme)",
         scenario_1_label_agent_derive_de_cfg_agent),
        ("fermer_issue pose 'done' ET le label d'agent au succès",
         scenario_2_fermer_issue_pose_label_fait_et_label_agent),
        ("échec de pose du label d'agent : best-effort, sans impact sur fermer_issue",
         scenario_3_echec_label_agent_best_effort_sans_impact),
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

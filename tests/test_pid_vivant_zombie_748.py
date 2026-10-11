#!/usr/bin/env python3
"""Test de non-régression — issue #748.

Contexte : incident Scrabble #452 (11/10/2026, mode écriture). Après un clic
sur « Interrompre », un verrou de worktree (logs/verrous/*.lock) est resté en
place avec le PID du watcher — ce PID correspondait à un process ZOMBIE (état
Z, « defunct »), dont le parent ne l'avait pas récupéré. `_pid_vivant` (watcher.py)
s'appuie sur `os.kill(pid, 0)`, qui RÉUSSIT pour un zombie (entrée encore
présente dans la table des process tant que le parent ne l'a pas réapé) : un
watcher tué devenu zombie était donc encore considéré « vivant », bloquant la
suppression du verrou (voir tests/test_interruption_zombie_748.py pour la
conséquence côté interrompre_linux) et faussant le panneau Infrastructure
(`taches_en_cours`/`watcher_actif`).

Correction : `_pid_vivant` lit désormais l'état (3e champ) de
/proc/<pid>/stat sous Linux — 'Z' ⇒ False, un fait certain au même titre
qu'un PID introuvable (ni l'un ni l'autre n'exécute plus rien). Repli sur le
comportement antérieur si /proc est absent ou la lecture échoue (ne change
rien sous Windows, ni sur un OS POSIX sans /proc).

Exécution :  python3 tests/test_pid_vivant_zombie_748.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def _attendre_etat(pid: int, etat_attendu: str, delai_max: float = 5.0) -> bool:
    fin = time.monotonic() + delai_max
    while time.monotonic() < fin:
        if watcher._etat_processus_linux(pid) == etat_attendu:
            return True
        time.sleep(0.05)
    return False


def scenario_pid_zombie_non_reape_renvoie_faux():
    """Un enfant tué puis jamais réapé (os.waitpid) devient zombie : _pid_vivant
    doit renvoyer False — reproduit l'incident Scrabble #452."""
    pid = os.fork()
    if pid == 0:
        os._exit(0)   # l'enfant se termine immédiatement
    try:
        assert _attendre_etat(pid, "Z", delai_max=5.0), (
            f"le process {pid} n'est jamais passé à l'état zombie (Z) — "
            f"précondition du test non remplie."
        )
        assert watcher._pid_vivant(pid) is False, (
            f"_pid_vivant({pid}) aurait dû renvoyer False pour un zombie confirmé "
            f"(état Z), pas True (incident #452 reproduit)."
        )
    finally:
        os.waitpid(pid, 0)   # réap propre, évite de laisser un zombie du test
    return {"pid": pid}


def scenario_pid_vivant_reel_renvoie_vrai():
    """Non-régression : un vrai process vivant (celui-ci-même) reste détecté
    comme vivant — la correction ne doit jamais introduire de faux négatif."""
    assert watcher._pid_vivant(os.getpid()) is True
    return {}


def scenario_pid_inexistant_renvoie_faux():
    """Non-régression du comportement existant (issue #584) : un PID qui
    n'existe plus reste détecté comme mort, fait certain inchangé par #748."""
    import subprocess
    proc = subprocess.Popen(["sleep", "30"])
    pid_mort = proc.pid
    proc.kill()
    proc.wait(timeout=5)
    fin = time.monotonic() + 5
    while time.monotonic() < fin:
        try:
            os.kill(pid_mort, 0)
        except ProcessLookupError:
            break
        time.sleep(0.05)
    assert watcher._pid_vivant(pid_mort) is False
    return {"pid": pid_mort}


def scenario_etat_processus_linux_repli_si_illisible():
    """_etat_processus_linux renvoie None (jamais une exception) pour un PID
    dont /proc/<pid>/stat est illisible — _pid_vivant doit alors retomber sur
    son comportement antérieur (True, prudence), pas planter."""
    assert watcher._etat_processus_linux(-1) is None
    # PID improbable, très probablement inexistant — la lecture échoue
    # (FileNotFoundError), pas d'exception propagée.
    assert watcher._etat_processus_linux(2**30) is None
    return {}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur os.fork()/```/proc```, non applicable sous Windows)")
        return 0

    tests = [
        ("zombie confirmé (état Z) → _pid_vivant renvoie False (incident #452)",
         scenario_pid_zombie_non_reape_renvoie_faux),
        ("process vivant réel → _pid_vivant renvoie True (non-régression)",
         scenario_pid_vivant_reel_renvoie_vrai),
        ("PID inexistant → _pid_vivant renvoie False (non-régression #584)",
         scenario_pid_inexistant_renvoie_faux),
        ("_etat_processus_linux : repli silencieux (None) si /proc illisible",
         scenario_etat_processus_linux_repli_si_illisible),
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

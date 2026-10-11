#!/usr/bin/env python3
"""Test de non-régression — issue #748 (incident Scrabble #452).

Reproduit par le code le scénario réel : le watcher visé par un
« Interrompre » meurt mais devient ZOMBIE plutôt que de disparaître — son
parent réel (PAS le process Flask qui exécute interrompre_linux) ne le
récupère jamais (`waitpid`). `_reaper_best_effort` (app/interruption.py) ne
peut rien ici : il ne tente un `waitpid` QUE sur un enfant DIRECT du process
Flask courant (cf. sa docstring) — un watcher zombie dont le vrai parent est
un AUTRE process reproduit exactement la limite documentée. Seule la
correction de `_pid_vivant` (watcher.py, issue #748 — détection de l'état Z
via /proc/<pid>/stat) permet alors de conclure correctement « arbre mort »
dans la boucle d'attente de 5s (au lieu d'épuiser les 5s puis de renoncer,
laissant le verrou en place, comme vécu sur Scrabble #452).

Technique de double fork + pipe (même esprit que
tests/test_orphelin_verrou_perime_322.py, qui lance de vrais process) : un
process INTERMÉDIAIRE (encore vivant, jamais de waitpid) est le vrai parent
du PID cible — ce PID n'est PAS un enfant direct de ce script de test.

Couvre aussi le volet « panneau Infrastructure » (point 6 de l'issue) :
`watcher.taches_en_cours` ne compte plus un verrou orphelin (process mort ou
zombie ET dossier de travail absent) comme une tâche en cours — sans jamais
SUPPRIMER le fichier de verrou lui-même (ce n'est pas son rôle).

Exécution :  python3 tests/test_interruption_zombie_748.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
import app.interruption as interruption  # noqa: E402


def _attendre_etat(pid: int, etat_attendu: str, delai_max: float = 5.0) -> bool:
    fin = time.monotonic() + delai_max
    while time.monotonic() < fin:
        if watcher._etat_processus_linux(pid) == etat_attendu:
            return True
        time.sleep(0.05)
    return False


class _ZombieViaIntermediaire:
    """Crée un PID vivant dont le VRAI parent (un process intermédiaire,
    créé par ce même contexte) ne l'attend jamais — reproduit un watcher
    zombie dont le process Flask courant n'est PAS le parent direct (limite
    documentée de _reaper_best_effort). Nettoyage : tue l'intermédiaire à la
    sortie du contexte (libère alors le zombie, réapé par init)."""

    def __enter__(self):
        r, w = os.pipe()
        self.pid_intermediaire = os.fork()
        if self.pid_intermediaire == 0:
            os.close(r)
            pid_cible = os.fork()
            if pid_cible == 0:
                os.close(w)
                time.sleep(30)   # vivant jusqu'au SIGKILL envoyé par le test
                os._exit(0)
            os.write(w, str(pid_cible).encode("ascii"))
            os.close(w)
            # Reste vivant SANS JAMAIS faire waitpid(pid_cible, ...) : une
            # fois tué, pid_cible devient zombie jusqu'à ce que CE process
            # (son vrai parent, pas le test) se termine lui-même.
            time.sleep(30)
            os._exit(0)
        os.close(w)
        self.pid_cible = int(os.read(r, 32).decode("ascii"))
        os.close(r)
        return self.pid_cible

    def __exit__(self, *exc):
        try:
            os.kill(self.pid_intermediaire, 9)
        except OSError:
            pass
        try:
            os.waitpid(self.pid_intermediaire, 0)
        except ChildProcessError:
            pass


def _isoler_etat(tmp_path: Path, nom: str) -> dict:
    anciens = {
        "DOSSIER_VERROUS": watcher.DOSSIER_VERROUS,
        "interruption.DOSSIER_LOGS": interruption.DOSSIER_LOGS,
    }
    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    interruption.DOSSIER_LOGS = tmp_path / "logs"
    interruption.DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
    return anciens


def _restaurer_etat(anciens: dict) -> None:
    watcher.DOSSIER_VERROUS = anciens["DOSSIER_VERROUS"]
    interruption.DOSSIER_LOGS = anciens["interruption.DOSSIER_LOGS"]


def scenario_interrompre_linux_watcher_zombie_nettoie_les_verrous():
    """Le PID du watcher (fichier logs/watcher-<nom>.pid) est tué par
    interrompre_linux puis devient zombie, SANS que _reaper_best_effort ne
    puisse le récupérer (parent réel = process intermédiaire, pas ce test).
    La boucle d'attente de 5s doit conclure « arbre mort » (grâce à
    _pid_vivant corrigé) BIEN avant l'écoulement des 5s, et les verrous
    (principal + worktree actif) doivent être supprimés."""
    with tempfile.TemporaryDirectory() as tmp, _ZombieViaIntermediaire() as pid_cible:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "rep_travail"
        rep_travail.mkdir()
        anciens = _isoler_etat(tmp_path, "test748")
        try:
            (interruption.DOSSIER_LOGS / "watcher-test748.pid").write_text(str(pid_cible))

            # Verrou principal + verrou d'un worktree actif fictif (issue
            # #337/#340) : les deux doivent être supprimés une fois l'arbre
            # confirmé mort — `_lister_worktrees_actifs` dépend de `git
            # worktree list`, hors sujet ici : patché pour simuler UN
            # worktree actif sans dépendance git réelle.
            verrou_principal = watcher._chemin_verrou(rep_travail)
            verrou_principal.parent.mkdir(parents=True, exist_ok=True)
            verrou_principal.write_text(f"pid={pid_cible} projet=test748 rep={rep_travail}\n")

            chemin_worktree = tmp_path / "test748-issue999"
            chemin_worktree.mkdir()
            verrou_worktree = watcher._chemin_verrou(chemin_worktree)
            verrou_worktree.write_text(f"pid={pid_cible} projet=test748 mode=ecriture rep={chemin_worktree}\n")

            cfg = type("Cfg", (), {"nom": "test748", "rep_travail": rep_travail})()

            debut = time.monotonic()
            with mock.patch.object(interruption, "_lister_worktrees_actifs", lambda c: [chemin_worktree]):
                etapes = interruption.interrompre_linux(cfg)
            duree = time.monotonic() - debut

            par_etape = {e["etape"]: e for e in etapes}
            assert par_etape["attente_fin_process"]["statut"] == "succes", (
                f"l'attente aurait dû conclure « arbre mort » pour un zombie confirmé : {par_etape['attente_fin_process']}"
            )
            assert duree < 4.5, (
                f"la conclusion « arbre mort » a pris {duree:.1f}s — devrait être quasi immédiate "
                f"grâce à _pid_vivant corrigé, pas attendre l'épuisement des 5s."
            )
            assert not verrou_principal.exists(), "le verrou principal aurait dû être supprimé"
            assert not verrou_worktree.exists(), "le verrou du worktree actif aurait dû être supprimé"

            # Conséquence attendue côté panneau Infrastructure (point 5/6) :
            # plus aucune tâche en cours pour ce projet.
            assert watcher.taches_en_cours("test748") == [], (
                "le panneau afficherait encore une tâche en cours pour ce projet"
            )
        finally:
            _restaurer_etat(anciens)
        return {"pid_cible": pid_cible, "duree_attente": round(duree, 2)}


def scenario_taches_en_cours_ignore_verrou_orphelin_sans_le_supprimer():
    """Un verrou dont le PID propriétaire est zombie ET dont le dossier de
    travail (`rep`) a été supprimé (ex. worktree nettoyé entre-temps) n'est
    pas compté comme une tâche en cours — mais le fichier de verrou lui-même
    n'est PAS supprimé par taches_en_cours (pas son rôle, cf. intention #748
    point 6 : « ne pas supprimer silencieusement »)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        anciens = {"DOSSIER_VERROUS": watcher.DOSSIER_VERROUS}
        watcher.DOSSIER_VERROUS = tmp_path / "verrous"

        try:
            # PID mort garanti (plus simple à obtenir qu'un zombie ici : la
            # condition testée par taches_en_cours est seulement "pas vivant",
            # déjà vraie pour mort ET pour zombie depuis la correction #748).
            import subprocess
            proc = subprocess.Popen(["sleep", "30"])
            pid_mort = proc.pid
            proc.kill()
            proc.wait(timeout=5)
            fin = time.monotonic() + 5
            while time.monotonic() < fin and watcher._pid_vivant(pid_mort):
                time.sleep(0.05)
            assert not watcher._pid_vivant(pid_mort)

            rep_disparu = tmp_path / "worktree-disparu"   # jamais créé

            verrou = watcher._chemin_verrou(rep_disparu)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(f"pid={pid_mort} projet=test748b mode=ecriture rep={rep_disparu}\n")

            assert watcher.taches_en_cours("test748b") == [], (
                "un verrou orphelin (process mort, dossier de travail absent) "
                "ne devrait pas être compté comme une tâche en cours"
            )
            assert verrou.exists(), (
                "taches_en_cours ne doit JAMAIS supprimer le fichier de verrou "
                "lui-même — seulement l'exclure du décompte"
            )
        finally:
            watcher.DOSSIER_VERROUS = anciens["DOSSIER_VERROUS"]
        return {"pid_mort": pid_mort}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur os.fork(), non applicable sous Windows)")
        return 0

    tests = [
        ("watcher zombie (parent réel ≠ ce process) → arbre mort, verrous supprimés",
         scenario_interrompre_linux_watcher_zombie_nettoie_les_verrous),
        ("verrou orphelin (mort/zombie + rep absent) → ignoré par taches_en_cours, jamais supprimé",
         scenario_taches_en_cours_ignore_verrou_orphelin_sans_le_supprimer),
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

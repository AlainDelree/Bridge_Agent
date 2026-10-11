#!/usr/bin/env python3
"""Test de non-régression — issue #751.

Contexte : des verrous d'issues terminées ou interrompues restaient dans
logs/verrous/ — le 11/10/2026, trois verrous (Bridge_Agent #573,
Relecture_Bridge #73 et #100) désignaient des process disparus et des
dossiers de worktrees supprimés depuis longtemps, retirés à la main faute de
nettoyage automatique au démarrage de new_issue.py.

`watcher.nettoyer_verrous_perimes()` (appelée une fois au démarrage de
new_issue.py) purge désormais ces verrous, mais UNIQUEMENT sur la foi du
PROCESSUS (PID absent ou zombie, même sonde `_pid_vivant` que
`acquerir_verrou`, issue #748) — jamais sur l'existence du dossier de
travail. Un verrou dont le process est vivant n'est donc jamais supprimé,
même si son `rep` a disparu (cas suspect, seulement journalisé en warning).

Ces scénarios vérifient :
- un verrou au PID absent est supprimé ;
- un verrou au PID d'un zombie est supprimé ;
- un verrou au PID vivant est conservé, y compris quand son rep n'existe
  plus (avertissement journalisé, nom du verrou + PID) ;
- un verrou au PID vivant avec un rep existant est conservé sans aucune
  alerte, et le dossier de travail n'est jamais touché ;
- un verrou illisible, ou sans champ pid= exploitable, est conservé ;
- un verrou posé depuis moins de deux minutes est conservé ;
- une erreur de lecture du dossier de verrous ne lève aucune exception
  (best-effort) ;
- deux passages successifs donnent le même résultat (idempotent).

Exécution :  python3 tests/test_nettoyage_verrous_perimes_751.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402

AGE_VIEUX = watcher.AGE_MIN_NETTOYAGE_VERROUS + 60
AGE_JEUNE = watcher.AGE_MIN_NETTOYAGE_VERROUS - 30


def _capturer_logs():
    messages: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    handler = CaptureHandler()
    watcher.log.addHandler(handler)
    watcher.log.setLevel(logging.DEBUG)
    return messages, handler


def _ecrire_verrou(dossier: Path, nom: str, pid, rep: Path | None, age_s: float) -> Path:
    dossier.mkdir(parents=True, exist_ok=True)
    verrou = dossier / nom
    contenu = "projet=test751 mode="
    if pid is not None:
        contenu = f"pid={pid} " + contenu
    if rep is not None:
        contenu += f" rep={rep}"
    verrou.write_text(contenu + "\n", encoding="utf-8")
    t = time.time() - age_s
    os.utime(verrou, (t, t))
    return verrou


def _attendre_mort(pid: int, delai_max: float = 5.0) -> bool:
    fin = time.monotonic() + delai_max
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def _pid_mort() -> int:
    proc = subprocess.Popen(["sleep", "30"])
    pid = proc.pid
    proc.kill()
    proc.wait(timeout=5)
    assert _attendre_mort(pid, 5.0), f"précondition non remplie : le PID {pid} est toujours vivant"
    return pid


def scenario_pid_absent_supprime():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "verrous"
        ancien = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = dossier
        rep = Path(tmp) / "rep_existant"
        rep.mkdir()
        try:
            verrou = _ecrire_verrou(dossier, "a.lock", _pid_mort(), rep, AGE_VIEUX)
            watcher.nettoyer_verrous_perimes()
            assert not verrou.exists(), "le verrou au PID absent aurait dû être supprimé"
            assert rep.is_dir(), "le dossier de travail ne doit JAMAIS être supprimé, même quand son verrou l'est"
        finally:
            watcher.DOSSIER_VERROUS = ancien
    return {}


def scenario_pid_zombie_supprime():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "verrous"
        ancien = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = dossier
        pid = os.fork()
        if pid == 0:
            os._exit(0)
        try:
            fin = time.monotonic() + 5
            while time.monotonic() < fin and watcher._etat_processus_linux(pid) != "Z":
                time.sleep(0.05)
            assert watcher._etat_processus_linux(pid) == "Z", (
                f"précondition : le process {pid} n'est jamais passé à l'état zombie."
            )

            verrou = _ecrire_verrou(dossier, "b.lock", pid, None, AGE_VIEUX)
            watcher.nettoyer_verrous_perimes()
            assert not verrou.exists(), "le verrou au PID d'un zombie aurait dû être supprimé (issue #748)"
        finally:
            os.waitpid(pid, 0)
            watcher.DOSSIER_VERROUS = ancien
    return {"pid_zombie": pid}


def scenario_pid_vivant_rep_absent_conserve_et_signale():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "verrous"
        ancien = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = dossier
        rep = Path(tmp) / "rep_jamais_cree"
        messages, handler = _capturer_logs()
        try:
            verrou = _ecrire_verrou(dossier, "c.lock", os.getpid(), rep, AGE_VIEUX)
            watcher.nettoyer_verrous_perimes()
            assert verrou.exists(), "un verrou au PID vivant ne doit JAMAIS être supprimé, même si rep a disparu"
            assert any(verrou.name in m and str(os.getpid()) in m for m in messages), (
                f"aucun avertissement journalisé pour ce cas suspect (verrou vivant, rep absent) : {messages}"
            )
        finally:
            watcher.log.removeHandler(handler)
            watcher.DOSSIER_VERROUS = ancien
    return {}


def scenario_pid_vivant_rep_existant_conserve_sans_alerte():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "verrous"
        ancien = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = dossier
        rep = Path(tmp) / "rep_existant"
        rep.mkdir()
        messages, handler = _capturer_logs()
        try:
            verrou = _ecrire_verrou(dossier, "d.lock", os.getpid(), rep, AGE_VIEUX)
            watcher.nettoyer_verrous_perimes()
            assert verrou.exists(), "un verrou vivant avec un rep existant doit être conservé"
            assert not any(verrou.name in m for m in messages), (
                f"aucun avertissement ne devrait être journalisé pour ce cas normal : {messages}"
            )
            assert rep.is_dir(), "le dossier de travail ne doit jamais être touché"
        finally:
            watcher.log.removeHandler(handler)
            watcher.DOSSIER_VERROUS = ancien
    return {}


def scenario_verrou_illisible_ou_sans_pid_conserve():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "verrous"
        ancien = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = dossier
        try:
            verrou_sans_pid = _ecrire_verrou(dossier, "e.lock", None, None, AGE_VIEUX)

            # « Illisible » : un dossier portant l'extension .lock — .stat()
            # réussit (âge calculable) mais .read_text() lève OSError.
            verrou_illisible = dossier / "f.lock"
            verrou_illisible.mkdir(parents=True)
            t = time.time() - AGE_VIEUX
            os.utime(verrou_illisible, (t, t))

            watcher.nettoyer_verrous_perimes()

            assert verrou_sans_pid.exists(), "un verrou sans champ pid= exploitable doit être conservé"
            assert verrou_illisible.exists(), "un verrou illisible doit être conservé"
        finally:
            watcher.DOSSIER_VERROUS = ancien
    return {}


def scenario_verrou_jeune_conserve():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "verrous"
        ancien = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = dossier
        try:
            verrou = _ecrire_verrou(dossier, "g.lock", _pid_mort(), None, AGE_JEUNE)
            watcher.nettoyer_verrous_perimes()
            assert verrou.exists(), (
                "un verrou posé depuis moins de deux minutes ne doit jamais être "
                "supprimé (course possible avec un watcher en train de le poser)"
            )
        finally:
            watcher.DOSSIER_VERROUS = ancien
    return {}


def scenario_erreur_lecture_dossier_sans_exception():
    """Best-effort : une erreur en lisant DOSSIER_VERROUS lui-même (dossier
    illisible, permissions...) ne doit jamais empêcher le démarrage de
    new_issue.py — journalisée, puis la fonction revient normalement."""

    class _DossierCasse:
        def is_dir(self):
            return True

        def glob(self, motif):
            raise OSError("dossier illisible (simulation issue #751)")

    ancien = watcher.DOSSIER_VERROUS
    watcher.DOSSIER_VERROUS = _DossierCasse()
    messages, handler = _capturer_logs()
    try:
        watcher.nettoyer_verrous_perimes()   # ne doit lever AUCUNE exception
        assert any("interrompu" in m for m in messages), (
            f"l'erreur de lecture du dossier aurait dû être journalisée : {messages}"
        )
    finally:
        watcher.log.removeHandler(handler)
        watcher.DOSSIER_VERROUS = ancien
    return {}


def scenario_idempotent_deux_passages():
    with tempfile.TemporaryDirectory() as tmp:
        dossier = Path(tmp) / "verrous"
        ancien = watcher.DOSSIER_VERROUS
        watcher.DOSSIER_VERROUS = dossier
        try:
            verrou_mort = _ecrire_verrou(dossier, "h.lock", _pid_mort(), None, AGE_VIEUX)
            verrou_vivant = _ecrire_verrou(
                dossier, "i.lock", os.getpid(), Path(tmp) / "rep_absent2", AGE_VIEUX
            )

            watcher.nettoyer_verrous_perimes()
            etat_1 = (verrou_mort.exists(), verrou_vivant.exists())
            watcher.nettoyer_verrous_perimes()
            etat_2 = (verrou_mort.exists(), verrou_vivant.exists())

            assert etat_1 == (False, True), f"résultat inattendu après le 1er passage : {etat_1}"
            assert etat_2 == (False, True), f"résultat inattendu après le 2e passage (non idempotent) : {etat_2}"
        finally:
            watcher.DOSSIER_VERROUS = ancien
    return {}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur os.fork()/signaux POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("verrou au PID absent → supprimé (rep jamais touché)", scenario_pid_absent_supprime),
        ("verrou au PID d'un zombie → supprimé (issue #748)", scenario_pid_zombie_supprime),
        ("verrou au PID vivant, rep absent → conservé + avertissement", scenario_pid_vivant_rep_absent_conserve_et_signale),
        ("verrou au PID vivant, rep existant → conservé sans alerte", scenario_pid_vivant_rep_existant_conserve_sans_alerte),
        ("verrou illisible ou sans PID → conservé", scenario_verrou_illisible_ou_sans_pid_conserve),
        ("verrou de moins de deux minutes → conservé", scenario_verrou_jeune_conserve),
        ("erreur de lecture du dossier → journalisée, aucune exception", scenario_erreur_lecture_dossier_sans_exception),
        ("deux passages successifs → résultat identique (idempotent)", scenario_idempotent_deux_passages),
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

#!/usr/bin/env python3
"""Test de non-régression — issue #247.

Vérifie qu'aucun descendant du process `claude` ne survit au retour de
`lancer_claude` — cas réel à l'origine de l'issue : un `cmd.exe` de build
Windows resté vivant après la fermeture de l'issue, verrouillant le livrable
produit sans le moindre signal dans le journal.

Le test remplace `claude` par un faux exécutable (`fake_claude.sh`, placé en
tête de PATH) qui lance en arrière-plan un vrai process enfant bloqué sur une
lecture (`open()` sur un FIFO jamais écrit — équivalent d'une lecture stdin
qui n'aboutit jamais), écrit le PID de cet enfant dans un fichier, puis
termine immédiatement lui-même avec succès — reproduisant exactement le
schéma « le parent (claude) revient, l'enfant reste ». Après le retour de
`lancer_claude`, l'enfant doit être mort.

Couvre aussi le point 4 de l'issue (critique) : le nettoyage ne doit jamais
pouvoir atteindre le process de test lui-même (qui joue le rôle du watcher) —
vérifié en confirmant que le process de test est toujours vivant après
l'appel.

Exécution :  python3 tests/test_nettoyage_arbre_247.py
Sortie      :  code 0 si le scénario passe, 1 sinon.
"""

import logging
import os
import stat
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402

FAKE_CLAUDE = """#!/bin/bash
# Faux `claude` : lance un enfant bloqué (lecture sur un FIFO jamais écrit,
# équivalent d'une lecture stdin qui n'aboutit jamais), note son PID, puis
# termine immédiatement — le parent revient, l'enfant doit rester vivant tant
# que rien ne le nettoie explicitement.
python3 -c "open(\\"$TEST_FIFO_247\\", \\"r\\").read()" >/dev/null 2>&1 &
echo $! > "$TEST_PIDFILE_247"
echo "fake claude output"
exit 0
"""


def attendre_mort(pid: int, delai_max: float = 5.0) -> bool:
    """Poll jusqu'à ce que le process pid ne soit plus vivant, ou délai_max
    écoulé. Retourne True si mort constatée."""
    fin = time.monotonic() + delai_max
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        time.sleep(0.1)
    return False


def scenario_enfant_bloque_tue_apres_retour():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake_claude_path = bin_dir / "claude"
        fake_claude_path.write_text(FAKE_CLAUDE, encoding="utf-8")
        fake_claude_path.chmod(fake_claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        fifo_path = tmp_path / "blocage.fifo"
        os.mkfifo(fifo_path)
        pidfile_path = tmp_path / "enfant.pid"

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_FIFO_247"] = str(fifo_path)
        os.environ["TEST_PIDFILE_247"] = str(pidfile_path)

        # Capture des log.warning émis par le nettoyage (issue #247 point 2 :
        # chaque orphelin tué doit être journalisé, PID + ligne de commande).
        messages: list[str] = []

        class CaptureHandler(logging.Handler):
            def emit(self, record):
                messages.append(record.getMessage())

        handler = CaptureHandler()
        watcher.log.addHandler(handler)
        watcher.log.setLevel(logging.DEBUG)

        watcher.CFG = watcher.Config(
            nom="test247", depot="AlainDelree/Bridge_Agent",
            rep_travail=tmp_path, topic_ntfy="test247",
        )

        pid_watcher_test = os.getpid()

        try:
            succes, sortie = watcher.lancer_claude(
                numero=9999, titre="Test #247", body="Corps de test",
                dry_run=False, mode=watcher.MODE_LECTURE,
                timeout=15, cwd=tmp_path,
            )
        finally:
            watcher.log.removeHandler(handler)
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_FIFO_247", None)
            os.environ.pop("TEST_PIDFILE_247", None)

        assert succes, f"lancer_claude aurait dû réussir (faux claude, exit 0) : {sortie}"

        assert pidfile_path.exists(), "le faux claude n'a pas écrit le PID de son enfant"
        pid_enfant = int(pidfile_path.read_text().strip())

        # Point 4 (critique) : le nettoyage ne doit jamais toucher le process
        # de test lui-même (qui joue ici le rôle du watcher).
        try:
            os.kill(pid_watcher_test, 0)
        except ProcessLookupError:
            raise AssertionError("le process de test (rôle du watcher) a été tué — régression critique du point 4 !")

        assert attendre_mort(pid_enfant, delai_max=5.0), (
            f"l'enfant bloqué (PID {pid_enfant}) est toujours vivant après le retour "
            f"de lancer_claude — le nettoyage de l'arbre de process a échoué."
        )

        assert any(str(pid_enfant) in m for m in messages), (
            f"aucun log.warning ne mentionne le PID de l'enfant tué ({pid_enfant}) — "
            f"le nettoyage doit être journalisé (issue #247 point 2). Messages capturés : {messages}"
        )

    return {"pid_enfant": pid_enfant, "warnings": len(messages)}


def main():
    if os.name == "nt":
        print("  (ignoré : test spécifique POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("enfant bloqué sur lecture → tué après retour de lancer_claude",
         scenario_enfant_bloque_tue_apres_retour),
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

#!/usr/bin/env python3
"""Test de non-régression — issue #322.

Trou comblé : si le watcher meurt BRUTALEMENT (kill -9, coupure, plantage
Python non capturé) PENDANT qu'un claude tourne, aucun `finally` ne s'exécute
→ le claude devient orphelin ET le verrou reste posé. Au démarrage suivant, le
watcher voit ce verrou, le déclare périmé et le REPREND. Avant cette issue, il
le reprenait sans vérifier qu'un claude orphelin de l'ancien contexte tourne
encore, risquant de lancer un second claude dans le même rep_travail pendant
que l'orphelin y écrit toujours.

Ces scénarios vérifient, au moment précis où `acquerir_verrou` reprend un
verrou PÉRIMÉ :
- l'orphelin (pgid stocké dans le verrou, process vivant, ligne de commande
  contenant "claude") est bien tué avant la reprise, et journalisé ;
- le garde-fou anti-reboot empêche tout kill si l'une des trois conditions
  (verrou périmé + process vivant + process est un claude) manque :
  process disparu, ou process vivant mais pas un claude ;
- un verrou d'ancien format (sans champ claude_pgid) est repris sans erreur
  et sans tentative de kill ;
- `lancer_claude` consigne bien le pgid de claude dans le verrou fourni, une
  fois le Popen réussi.

Exécution :  python3 tests/test_orphelin_verrou_perime_322.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402

FAKE_CLAUDE_BLOQUE = """#!/bin/bash
sleep 30
"""


def attendre_mort(pid: int, delai_max: float = 5.0) -> bool:
    fin = time.monotonic() + delai_max
    while time.monotonic() < fin:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.1)
    return False


def _capturer_logs():
    messages: list[str] = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    handler = CaptureHandler()
    watcher.log.addHandler(handler)
    watcher.log.setLevel(logging.DEBUG)
    return messages, handler


def _preparer_contexte(tmp_path: Path, nom: str):
    """Isole DOSSIER_VERROUS et CFG dans un dossier temporaire — jamais dans le
    vrai logs/verrous/ du dépôt. Retourne (ancien_dossier_verrous, dossier_verrous_tmp)."""
    dossier_verrous_tmp = tmp_path / "verrous"
    ancien_dossier_verrous = watcher.DOSSIER_VERROUS
    watcher.DOSSIER_VERROUS = dossier_verrous_tmp
    watcher.CFG = watcher.Config(
        nom=nom, depot="AlainDelree/Bridge_Agent",
        rep_travail=tmp_path, topic_ntfy=nom,
    )
    return ancien_dossier_verrous, dossier_verrous_tmp


def _lancer_fake_claude_bloque(tmp_path: Path) -> subprocess.Popen:
    """Lance un faux `claude` (nom du fichier exécuté = « claude ») bloqué sur
    un sleep long, dans sa propre session (pgid == pid, comme lancer_claude le
    fait pour le vrai claude). Sert à simuler l'orphelin d'un watcher mort
    brutalement pendant que claude tournait.

    Le script bash exécute `sleep` comme dernier appel, qui devient un
    process ENFANT du bash (pid différent, même pgid) — c'est donc le groupe
    de process (killpg) qui doit être tué, pas un seul pid. Un thread démon
    fait le `wait()` en continu pour réaper immédiatement le process dès sa
    mort effective (sans ça, il resterait zombie — donc détecté « vivant »
    par os.kill(pid, 0) — jusqu'à ce que le test appelle wait() lui-même)."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_claude_path = bin_dir / "claude"
    fake_claude_path.write_text(FAKE_CLAUDE_BLOQUE, encoding="utf-8")
    fake_claude_path.chmod(fake_claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    proc = subprocess.Popen([str(fake_claude_path)], start_new_session=True)
    threading.Thread(target=proc.wait, daemon=True).start()
    return proc


def _peremption_pour(timeout_projet: int) -> float:
    return watcher.CFG.max_essais * (timeout_projet + watcher.PAUSE_ENTRE_TENTATIVES) + watcher.PEREMPTION_MARGE_VERROU


def scenario_orphelin_claude_tue_a_reprise_verrou():
    """Cas nominal : verrou périmé + pgid stocké + process vivant + c'est bien
    un claude → tué avant la reprise, journalisé, verrou repris normalement."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_verrous, _ = _preparer_contexte(tmp_path, "test322a")
        messages, handler = _capturer_logs()
        proc_orphelin = _lancer_fake_claude_bloque(tmp_path)
        try:
            timeout_projet = 1
            verrou = watcher._chemin_verrou(tmp_path)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(
                f"pid=999999 projet=test322a rep={tmp_path} claude_pgid={proc_orphelin.pid}\n",
                encoding="utf-8",
            )
            age_perime = _peremption_pour(timeout_projet) + 10
            t = time.time() - age_perime
            os.utime(verrou, (t, t))

            resultat = watcher.acquerir_verrou(tmp_path, timeout_projet)

            assert resultat == verrou, f"le verrou périmé aurait dû être repris (même chemin) : {resultat} != {verrou}"
            assert attendre_mort(proc_orphelin.pid, delai_max=5.0), (
                f"l'orphelin claude (PID {proc_orphelin.pid}) est toujours vivant après "
                f"la reprise du verrou périmé — le nettoyage a échoué."
            )
            assert any(str(proc_orphelin.pid) in m and "claude" in m.lower() for m in messages), (
                f"aucun log.warning ne mentionne l'orphelin tué (PID {proc_orphelin.pid}). "
                f"Messages : {messages}"
            )
        finally:
            watcher.log.removeHandler(handler)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.liberer_verrou(watcher._chemin_verrou(tmp_path))
            try:
                proc_orphelin.kill()
                proc_orphelin.wait(timeout=2)
            except Exception:
                pass

    return {"pid_orphelin": proc_orphelin.pid}


def scenario_pgid_vivant_mais_pas_un_claude_non_tue():
    """Garde-fou (condition 3) : le pgid stocké désigne un process bien vivant,
    mais dont la ligne de commande ne contient pas « claude » (ex. pgid recyclé
    après reboot pour un tout autre programme) → ne doit JAMAIS être tué."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_verrous, _ = _preparer_contexte(tmp_path, "test322b")
        messages, handler = _capturer_logs()
        proc_innocent = subprocess.Popen(["sleep", "30"], start_new_session=True)
        try:
            timeout_projet = 1
            verrou = watcher._chemin_verrou(tmp_path)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(
                f"pid=999999 projet=test322b rep={tmp_path} claude_pgid={proc_innocent.pid}\n",
                encoding="utf-8",
            )
            age_perime = _peremption_pour(timeout_projet) + 10
            t = time.time() - age_perime
            os.utime(verrou, (t, t))

            resultat = watcher.acquerir_verrou(tmp_path, timeout_projet)

            assert resultat == verrou, "le verrou périmé aurait dû être repris malgré tout"
            time.sleep(0.3)
            assert proc_innocent.poll() is None, (
                "un process innocent (pas un claude) a été tué par erreur — "
                "régression critique du garde-fou anti-reboot."
            )
            assert not any(str(proc_innocent.pid) in m for m in messages), (
                f"un log de kill mentionne le process innocent alors qu'il n'a pas dû être touché : {messages}"
            )
        finally:
            watcher.log.removeHandler(handler)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.liberer_verrou(watcher._chemin_verrou(tmp_path))
            try:
                proc_innocent.kill()
                proc_innocent.wait(timeout=2)
            except Exception:
                pass

    return {"pid_innocent": proc_innocent.pid}


def scenario_pgid_disparu_non_tue():
    """Garde-fou (condition 2) : le pgid stocké ne correspond plus à aucun
    process vivant (déjà mort, ou recyclé après reboot pour un pid qui n'existe
    plus au moment du test) → aucun kill tenté, verrou repris normalement."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_verrous, _ = _preparer_contexte(tmp_path, "test322c")
        messages, handler = _capturer_logs()

        # Un pgid garanti mort : on lance puis on tue un vrai process, on
        # attend sa disparition effective avant de l'utiliser.
        proc_ephemere = subprocess.Popen(["sleep", "30"], start_new_session=True)
        pgid_mort = proc_ephemere.pid
        proc_ephemere.kill()
        proc_ephemere.wait(timeout=5)
        assert attendre_mort(pgid_mort, delai_max=5.0)

        try:
            timeout_projet = 1
            verrou = watcher._chemin_verrou(tmp_path)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(
                f"pid=999999 projet=test322c rep={tmp_path} claude_pgid={pgid_mort}\n",
                encoding="utf-8",
            )
            age_perime = _peremption_pour(timeout_projet) + 10
            t = time.time() - age_perime
            os.utime(verrou, (t, t))

            resultat = watcher.acquerir_verrou(tmp_path, timeout_projet)

            assert resultat == verrou, "le verrou périmé aurait dû être repris malgré le pgid mort"
            # Le log "Verrou périmé... repris" est normal et attendu (comportement
            # inchangé) ; seul un log de nettoyage d'orphelin serait anormal ici.
            assert not any("Orphelin" in m for m in messages), (
                f"aucun kill n'aurait dû être tenté ni journalisé sur un pgid déjà mort : {messages}"
            )
        finally:
            watcher.log.removeHandler(handler)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.liberer_verrou(watcher._chemin_verrou(tmp_path))

    return {"pgid_mort": pgid_mort}


def scenario_verrou_ancien_format_sans_pgid():
    """Rétrocompatibilité : un verrou périmé sans champ claude_pgid (ancien
    format, ou watcher mort avant même le lancement de claude) doit être repris
    sans erreur et sans tentative de kill."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_verrous, _ = _preparer_contexte(tmp_path, "test322d")
        messages, handler = _capturer_logs()
        try:
            timeout_projet = 1
            verrou = watcher._chemin_verrou(tmp_path)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(f"pid=999999 projet=test322d rep={tmp_path}\n", encoding="utf-8")
            age_perime = _peremption_pour(timeout_projet) + 10
            t = time.time() - age_perime
            os.utime(verrou, (t, t))

            resultat = watcher.acquerir_verrou(tmp_path, timeout_projet)

            assert resultat == verrou, "un verrou périmé d'ancien format doit être repris normalement"
            # Le log "Verrou périmé... repris" est normal et attendu (comportement
            # inchangé) ; seul un log de nettoyage d'orphelin serait anormal ici.
            assert not any("Orphelin" in m for m in messages), (
                f"aucun kill ne devrait être tenté sans champ claude_pgid : {messages}"
            )
        finally:
            watcher.log.removeHandler(handler)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.liberer_verrou(watcher._chemin_verrou(tmp_path))

    return {}


def scenario_lancer_claude_ecrit_pgid_dans_verrou():
    """lancer_claude, appelé avec verrou=<chemin>, doit consigner le pgid du
    claude tout juste lancé (pid == pgid, start_new_session=True) dans ce
    fichier, en préservant les champs déjà présents."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier_verrous, _ = _preparer_contexte(tmp_path, "test322e")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        fake_claude_path = bin_dir / "claude"
        fake_claude_path.write_text("#!/bin/bash\necho ok\nexit 0\n", encoding="utf-8")
        fake_claude_path.chmod(fake_claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        try:
            verrou = watcher._chemin_verrou(tmp_path)
            verrou.parent.mkdir(parents=True, exist_ok=True)
            verrou.write_text(f"pid={os.getpid()} projet=test322e rep={tmp_path}\n", encoding="utf-8")

            succes, sortie = watcher.lancer_claude(
                numero=9999, titre="Test #322", body="Corps de test",
                dry_run=False, autoriser_ecriture=False,
                timeout=15, cwd=tmp_path, verrou=verrou,
            )
            assert succes, f"lancer_claude aurait dû réussir : {sortie}"

            contenu = verrou.read_text(encoding="utf-8")
            assert f"pid={os.getpid()}" in contenu, f"le champ pid= d'origine a été perdu : {contenu!r}"
            pgid_lu = watcher._lire_pgid_verrou(verrou)
            assert pgid_lu is not None, f"aucun claude_pgid consigné dans le verrou : {contenu!r}"
        finally:
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            watcher.DOSSIER_VERROUS = ancien_dossier_verrous
            watcher.liberer_verrou(watcher._chemin_verrou(tmp_path))

    return {}


def main():
    if os.name == "nt":
        print("  (ignoré : test spécifique POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("verrou périmé + orphelin claude vivant → tué avant reprise",
         scenario_orphelin_claude_tue_a_reprise_verrou),
        ("garde-fou anti-reboot : pgid vivant mais pas un claude → non tué",
         scenario_pgid_vivant_mais_pas_un_claude_non_tue),
        ("garde-fou anti-reboot : pgid mort/recyclé → non tué",
         scenario_pgid_disparu_non_tue),
        ("verrou ancien format (sans claude_pgid) → repris sans erreur",
         scenario_verrou_ancien_format_sans_pgid),
        ("lancer_claude consigne le pgid dans le verrou fourni",
         scenario_lancer_claude_ecrit_pgid_dans_verrou),
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

#!/usr/bin/env python3
"""Test de non-régression — issue #908.

Contexte : le 18/11/2026, deux process `watcher.py` ont tourné en même temps
sur bridge_agent — l'interface web (`app/watchers.py::demarrer_watcher`,
lancement direct) et l'unité systemd `watcher@bridge_agent` démarrée à la
main par Alain pour un test — chacun avec son propre compteur de
parallélisme, chacun ayant pris la même issue (#903, deux fois, dans des
worktrees `issue903`/`issue903-bis`). Rien n'empêchait alors ce doublon,
quelle que soit la manière dont le second process était lancé : le fichier
PID partagé (`logs/watcher-<nom>.pid`) n'est qu'une donnée informative,
réécrite sans concertation par n'importe quel lancement.

`watcher.acquerir_verrou_processus(nom_projet)` pose désormais, tout au
début de `main()`, un verrou SYSTÈME (flock POSIX non bloquant /
verrouillage de plage Windows via `msvcrt`) sur
`logs/verrous/watcher-processus-<nom>.lock` — gardé ouvert toute la vie du
process, libéré automatiquement par le noyau à sa fermeture (fin propre OU
brutale). Nom délibérément distinct des verrous par issue
(`_chemin_verrou`, `<rep>-<empreinte>.lock`, même dossier) pour ne jamais
les confondre.

Ces scénarios vérifient :
- une deuxième tentative d'acquisition pour le même projet est refusée ;
- le verrou est de nouveau acquérable après un `kill -9` du process qui le
  tenait (vrai sous-process, vraie coupure brutale — pas juste fermeture du
  descripteur) ;
- deux projets différents n'interfèrent jamais entre eux ;
- le verrou n'est PAS hérité par un process enfant (vérifié via
  `/proc/self/fd` dans un sous-process dédié — condition explicite de
  l'issue : une session tmux du mode interactif, ou son serveur, ne doit
  jamais se retrouver à bloquer le redémarrage du watcher) ;
- le code de sortie dédié au refus (`EXIT_VERROU_DEJA_PRIS`) est bien
  distinct des autres codes connus et déclaré dans `SuccessExitStatus` de
  `systemd/watcher@.service`, pour qu'un watcher refusé ne déclenche pas la
  boucle de redémarrage de `Restart=on-failure`.

Comportement Windows (`msvcrt`) : NON exécuté ici (environnement de test
Linux) — voir le rapport de clôture de l'issue #908 pour le détail de ce qui
a été vérifié par relecture de code plutôt que par exécution.

Exécution :  python3 tests/test_verrou_processus_unique_908.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def _preparer_dossier_verrous_tmp(tmp_path: Path) -> Path:
    """Isole watcher.DOSSIER_VERROUS dans un dossier temporaire — jamais le
    vrai logs/verrous/ du dépôt. Retourne l'ANCIEN dossier, à restaurer."""
    ancien = watcher.DOSSIER_VERROUS
    watcher.DOSSIER_VERROUS = tmp_path / "verrous"
    return ancien


def scenario_deuxieme_instance_refusee():
    """Une deuxième tentative d'acquisition pour le MÊME projet, pendant que
    la première tient toujours son descripteur ouvert, est refusée."""
    with tempfile.TemporaryDirectory() as tmp:
        ancien_dossier = _preparer_dossier_verrous_tmp(Path(tmp))
        ancien_fd = watcher._verrou_processus_fd
        try:
            premiere = watcher.acquerir_verrou_processus("test908_a")
            assert premiere is True, "la première acquisition aurait dû réussir"
            fd_premiere = watcher._verrou_processus_fd
            assert fd_premiere is not None

            seconde = watcher.acquerir_verrou_processus("test908_a")
            assert seconde is False, (
                "une deuxième instance pour le même projet aurait dû être refusée "
                "alors que la première tient toujours le verrou."
            )
            # La globale ne doit pas avoir été écrasée par la tentative refusée.
            assert watcher._verrou_processus_fd == fd_premiere
        finally:
            if watcher._verrou_processus_fd is not None:
                os.close(watcher._verrou_processus_fd)
            watcher._verrou_processus_fd = ancien_fd
            watcher.DOSSIER_VERROUS = ancien_dossier
    return {}


def scenario_deux_projets_simultanes():
    """Le verrou est PAR PROJET : deux projets différents s'acquièrent
    chacun sans interférer avec l'autre."""
    with tempfile.TemporaryDirectory() as tmp:
        ancien_dossier = _preparer_dossier_verrous_tmp(Path(tmp))
        ancien_fd = watcher._verrou_processus_fd
        fd_a = fd_b = None
        try:
            ok_a = watcher.acquerir_verrou_processus("test908_proj_a")
            fd_a = watcher._verrou_processus_fd
            ok_b = watcher.acquerir_verrou_processus("test908_proj_b")
            fd_b = watcher._verrou_processus_fd

            assert ok_a is True, "projet A aurait dû acquérir son propre verrou"
            assert ok_b is True, "projet B aurait dû acquérir son propre verrou, indépendant de A"
            assert fd_a != fd_b, "les deux projets ne devraient jamais partager le même descripteur"

            chemin_a = watcher._chemin_verrou_processus("test908_proj_a")
            chemin_b = watcher._chemin_verrou_processus("test908_proj_b")
            assert chemin_a != chemin_b
            assert chemin_a.name != chemin_b.name
        finally:
            for fd in (fd_a, fd_b):
                if fd is not None:
                    try:
                        os.close(fd)
                    except OSError:
                        pass
            watcher._verrou_processus_fd = ancien_fd
            watcher.DOSSIER_VERROUS = ancien_dossier
    return {}


def scenario_verrou_libere_apres_arret_brutal():
    """Le verrou tenu par un process tué au signal 9 (coupure brutale, pas
    de `finally` possible côté enfant) est bien libéré par l'OS — une
    nouvelle instance peut alors démarrer."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier = _preparer_dossier_verrous_tmp(tmp_path)
        ancien_fd = watcher._verrou_processus_fd
        proc = None
        try:
            script = (
                "import sys, time; from pathlib import Path; "
                "sys.path.insert(0, %r); import watcher; "
                "watcher.DOSSIER_VERROUS = Path(%r); "
                "print(watcher.acquerir_verrou_processus('test908_brutal'), flush=True); "
                "time.sleep(60)"
            ) % (str(RACINE), str(watcher.DOSSIER_VERROUS))
            proc = subprocess.Popen(
                [sys.executable, "-c", script],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            premiere_ligne = proc.stdout.readline().strip()
            assert premiere_ligne == "True", (
                f"le sous-process enfant aurait dû acquérir le verrou en premier : {premiere_ligne!r}"
            )

            # Pendant que l'enfant tient le verrou, CE process ne doit pas pouvoir l'acquérir.
            refus_pendant = watcher.acquerir_verrou_processus("test908_brutal")
            assert refus_pendant is False, "le verrou aurait dû être refusé tant que l'enfant est vivant"

            os.kill(proc.pid, signal.SIGKILL)
            proc.wait(timeout=5)

            # Après la mort brutale, le noyau a dû libérer le verrou.
            reussite_apres = None
            fin = time.monotonic() + 5.0
            while time.monotonic() < fin:
                reussite_apres = watcher.acquerir_verrou_processus("test908_brutal")
                if reussite_apres:
                    break
                time.sleep(0.1)
            assert reussite_apres is True, (
                "le verrou aurait dû être libéré par l'OS après le kill -9 de l'enfant, "
                "et donc ré-acquérable sans délai significatif."
            )
        finally:
            if proc is not None and proc.poll() is None:
                proc.kill()
                proc.wait(timeout=5)
            if watcher._verrou_processus_fd is not None:
                os.close(watcher._verrou_processus_fd)
            watcher._verrou_processus_fd = ancien_fd
            watcher.DOSSIER_VERROUS = ancien_dossier
    return {"pid_enfant": proc.pid if proc else None}


def scenario_verrou_non_herite_par_enfant():
    """Le descripteur du verrou ne doit JAMAIS apparaître dans les
    descripteurs ouverts d'un process enfant (issue #908, point 3 — la
    préoccupation réelle étant le serveur tmux d'une session interactive,
    qui survit volontairement au redémarrage du watcher)."""
    if os.name == "nt" or not Path("/proc").is_dir():
        print("  (ignoré : vérification via /proc, spécifique Linux)")
        return {}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        ancien_dossier = _preparer_dossier_verrous_tmp(tmp_path)
        ancien_fd = watcher._verrou_processus_fd
        try:
            ok = watcher.acquerir_verrou_processus("test908_heritage")
            assert ok is True
            chemin_verrou = str(watcher._chemin_verrou_processus("test908_heritage").resolve())

            script = (
                "import os\n"
                "cible = %r\n"
                "trouve = False\n"
                "for entree in os.listdir('/proc/self/fd'):\n"
                "    try:\n"
                "        lien = os.readlink('/proc/self/fd/' + entree)\n"
                "    except OSError:\n"
                "        continue\n"
                "    if lien == cible:\n"
                "        trouve = True\n"
                "        break\n"
                "print('HERITE' if trouve else 'NON_HERITE')\n"
            ) % chemin_verrou
            resultat = subprocess.run(
                [sys.executable, "-c", script],
                capture_output=True, text=True, timeout=10,
            )
            assert "NON_HERITE" in resultat.stdout, (
                f"le descripteur du verrou a été retrouvé chez l'enfant — il serait hérité "
                f"par une session tmux et bloquerait tout redémarrage du watcher. "
                f"stdout={resultat.stdout!r} stderr={resultat.stderr!r}"
            )
        finally:
            if watcher._verrou_processus_fd is not None:
                os.close(watcher._verrou_processus_fd)
            watcher._verrou_processus_fd = ancien_fd
            watcher.DOSSIER_VERROUS = ancien_dossier
    return {}


def scenario_code_sortie_sans_boucle_systemd():
    """`EXIT_VERROU_DEJA_PRIS` est distinct de 0 et de `EXIT_INACTIVITE`, et
    déclaré dans `SuccessExitStatus` de `systemd/watcher@.service` — sans
    quoi `Restart=on-failure` relancerait en boucle un watcher qui se refuse
    pourtant normalement."""
    assert watcher.EXIT_VERROU_DEJA_PRIS != 0
    assert watcher.EXIT_VERROU_DEJA_PRIS != watcher.EXIT_INACTIVITE

    chemin_unite = RACINE / "systemd" / "watcher@.service"
    contenu = chemin_unite.read_text(encoding="utf-8")
    lignes_directive = [
        ligne for ligne in contenu.splitlines()
        if ligne.strip().startswith("SuccessExitStatus=")
    ]
    assert lignes_directive, f"aucune directive SuccessExitStatus= trouvée dans {chemin_unite}"
    codes = lignes_directive[0].split("=", 1)[1].split()
    assert str(watcher.EXIT_VERROU_DEJA_PRIS) in codes, (
        f"EXIT_VERROU_DEJA_PRIS ({watcher.EXIT_VERROU_DEJA_PRIS}) absent de "
        f"SuccessExitStatus ({codes!r}) — systemd relancerait un watcher pourtant "
        f"refusé normalement."
    )
    assert str(watcher.EXIT_INACTIVITE) in codes
    return {"codes_success_exit_status": codes}


def main():
    tests = [
        ("deuxième instance refusée pour le même projet",
         scenario_deuxieme_instance_refusee),
        ("deux projets différents n'interfèrent jamais",
         scenario_deux_projets_simultanes),
        ("verrou libéré après arrêt brutal (kill -9) du process qui le tenait",
         scenario_verrou_libere_apres_arret_brutal),
        ("verrou jamais hérité par un process enfant",
         scenario_verrou_non_herite_par_enfant),
        ("code de sortie dédié, déclaré dans SuccessExitStatus (pas de boucle systemd)",
         scenario_code_sortie_sans_boucle_systemd),
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

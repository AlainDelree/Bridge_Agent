#!/usr/bin/env python3
"""Test de non-régression — issue #749 : dossier dédié aux worktrees
mode_write sous CCW (Windows), symétrique du dossier dédié CCL (issue #740).

Sans machine Windows disponible : les scénarios ci-dessous simulent le
système d'exploitation en monkeypatchant `os.name = "nt"` *après* avoir déjà
construit les `Path` nécessaires (CFG.rep_travail, etc. — construits sous
l'OS réel, donc de vrais `PosixPath`). `os.name` ne pilote la classe choisie
par `pathlib.Path(...)` qu'AU MOMENT de la construction (`Path.__new__`) ;
une fois un `PosixPath` construit, toutes ses opérations ultérieures
(`.parent`, `/`, `.mkdir()`, `os.access()`) restent de vraies opérations
POSIX, quelle que soit la valeur de `os.name` au moment où elles sont
appelées. Seule `_chemin_worktree` (qui lit `os.name` à CHAQUE appel pour
choisir la branche Windows ou Linux) voit donc son AIGUILLAGE changer, sans
qu'aucune opération fichier ne devienne invalide — c'est ce qui permet de
tester la logique Windows sur une machine Linux, avec de vraies créations de
dossiers et de vrais replis sur permission refusée.

(`pathlib.WindowsPath` elle-même reste inutilisable sur Linux — tenter de la
construire directement via `Path(...)` avec `os.name="nt"` lève
`NotImplementedError` dès la première opération dérivée — raison pour
laquelle on construit toujours les chemins AVANT de monkeypatcher `os.name`.)

Vérifie :
- `_chemin_worktree` sous CCW (os.name == "nt") : le dossier dédié est
  `<parent de REP_TRAVAIL>/worktrees` (ex. REP_TRAVAIL `.../CCW/Scrabble` →
  dossier dédié `.../CCW/worktrees`), jamais dérivé de `Path.home()` — même
  si `Path.home()` est monkeypatché vers un piège, le résultat ne s'en
  approche pas.
- Le dossier dédié Windows est créé au besoin (`mkdir`).
- Repli sur l'ancien emplacement (frère de REP_TRAVAIL) + `log.warning`
  explicite si le dossier dédié Windows ne peut pas être créé (parent de
  REP_TRAVAIL en lecture seule).
- Noms et suffixes (`-bis`/`-ter`, issue #611) inchangés sous CCW.
- Comportement CCL (Linux, `os.name != "nt"`) strictement inchangé par ce
  correctif, avec la MÊME config.
- Un worktree hérité à l'ancien emplacement (frère de REP_TRAVAIL) reste
  trouvé et réutilisable par une RELANCE (issue #725), car
  `_trouver_worktree_reutilisable` interroge `git worktree list` et compare
  le NOM du dossier, jamais un chemin calculé — ce mécanisme ne contient
  aucune branche `os.name`, donc aucune dépendance à l'emplacement réel. Ce
  scénario NE force PAS os.name="nt" (voir son docstring : la fonction
  construit des `Path(...)` nus à partir de `git worktree list`, ce qui fait
  réellement lever `NotImplementedError` sous `os.name="nt"` simulé sur
  Linux — limite de `pathlib`, pas du code testé ; vérification Windows
  réelle laissée à Alain, cf. rapport de clôture).
- Comparaison de chemins insensible aux séparateurs : `PureWindowsPath`
  normalise `/` et `\\` de façon identique, ce qui est la même logique de
  normalisation que `pathlib.WindowsPath.resolve()` utilise réellement sous
  Windows — c'est pourquoi `_lister_worktrees_secondaires`/
  `_trouver_worktree_reutilisable` (qui comparent via `Path(...).resolve()`)
  n'ont besoin d'AUCUNE modification pour fonctionner avec le nouvel
  emplacement CCW : le chemin renvoyé par `git worktree list` (toujours en
  `/`, y compris sous Windows) et le chemin calculé par `_chemin_worktree`
  (natif, en `\\`) se résolvent au même `WindowsPath`.

Exécution :  python3 tests/test_worktree_windows_749.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import contextlib
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path, PureWindowsPath

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


@contextlib.contextmanager
def _capturer_logs_watcher():
    """Capture les messages log.warning/log.info de `watcher.log` pendant le
    bloc. Restaure le niveau précédent en sortie (même technique que
    tests/test_worktree_parallelisation_337.py)."""
    messages = []

    class _Handler(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    handler = _Handler()
    ancien_niveau = watcher.log.level
    watcher.log.setLevel(logging.INFO)
    watcher.log.addHandler(handler)
    try:
        yield messages
    finally:
        watcher.log.removeHandler(handler)
        watcher.log.setLevel(ancien_niveau)


@contextlib.contextmanager
def _os_name_force(valeur: str):
    """Monkeypatch temporaire de `os.name` — restauré même en cas d'échec de
    l'assertion. Voir le docstring du module : ne jamais construire de NOUVEAU
    `Path(...)` nu sous ce contexte, seulement réutiliser des `Path` déjà
    construits (via `.parent`, `/`, etc.)."""
    ancien = os.name
    os.name = valeur
    try:
        yield
    finally:
        os.name = ancien


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def scenario_windows_dossier_dedie_derive_de_rep_travail():
    """Issue #749 : sous CCW, le dossier dédié est `<parent de
    REP_TRAVAIL>/worktrees`, exemple de l'issue (`C:\\CCW\\Scrabble` →
    `C:\\CCW\\worktrees`), JAMAIS dérivé de `Path.home()` — vérifié en
    monkeypatchant `Path.home` vers un piège et en s'assurant que le chemin
    obtenu ne s'en approche pas."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_ccw = tmp_path / "CCW"
        rep_travail = rep_ccw / "Scrabble"
        rep_travail.mkdir(parents=True)

        piege_home = tmp_path / "PIEGE_profil_utilisateur"
        piege_home.mkdir()

        ancien_cfg = watcher.CFG
        ancien_home = Path.home
        watcher.CFG = watcher.Config(
            nom="scrabble", depot="AlainDelree/x",
            rep_travail=rep_travail, topic_ntfy="x",
        )
        Path.home = classmethod(lambda cls: piege_home)
        try:
            with _os_name_force("nt"):
                chemin = watcher._chemin_worktree(444)
            attendu = rep_ccw / "worktrees" / "scrabble-issue444"
            assert chemin == attendu, chemin
            assert (rep_ccw / "worktrees").is_dir(), "le dossier dédié aurait dû être créé au besoin"
            assert piege_home not in chemin.parents, \
                f"le chemin ne doit JAMAIS dériver de Path.home() (issue #749) : {chemin}"
        finally:
            watcher.CFG = ancien_cfg
            Path.home = ancien_home
    return {"windows_derive_de_rep_travail_ok": True}


def scenario_windows_repli_si_dossier_dedie_inaccessible():
    """Issue #749 : si le dossier dédié `<parent de REP_TRAVAIL>/worktrees`
    ne peut pas être créé (ici : le parent de REP_TRAVAIL lui-même en lecture
    seule), repli sur l'ancien emplacement — répertoire frère de REP_TRAVAIL
    — signalé par un log.warning explicite, comme sous CCL (issue #740)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_ccw = tmp_path / "CCW_readonly"
        rep_travail = rep_ccw / "Scrabble"
        rep_travail.mkdir(parents=True)
        os.chmod(rep_ccw, 0o555)

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="scrabble749b", depot="AlainDelree/x",
            rep_travail=rep_travail, topic_ntfy="x",
        )
        try:
            with _os_name_force("nt"):
                with _capturer_logs_watcher() as logs:
                    chemin = watcher._chemin_worktree(7491)
            assert chemin == rep_travail.parent / "scrabble749b-issue7491", \
                f"repli sur l'ancien emplacement (frère de REP_TRAVAIL) attendu : {chemin}"
            logs_repli = [m for m in logs if "dossier dédié" in m and "indisponible" in m]
            assert logs_repli, f"aucun log.warning explicite du repli (issue #749) : {logs}"
        finally:
            watcher.CFG = ancien_cfg
            os.chmod(rep_ccw, 0o755)
    return {"windows_repli_ok": True}


def scenario_windows_suffixes_inchanges():
    """Issue #749 : les suffixes historiques `-bis`/`-ter` (issue #611)
    restent appliqués au nom, sous CCW comme sous CCL."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_ccw = tmp_path / "CCW"
        rep_travail = rep_ccw / "Scrabble"
        rep_travail.mkdir(parents=True)

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="scrabble749c", depot="AlainDelree/x",
            rep_travail=rep_travail, topic_ntfy="x",
        )
        try:
            with _os_name_force("nt"):
                standard = watcher._chemin_worktree(7492)
                bis = watcher._chemin_worktree(7492, "-bis")
                ter = watcher._chemin_worktree(7492, "-ter")
            assert standard.name == "scrabble749c-issue7492", standard
            assert bis.name == "scrabble749c-issue7492-bis", bis
            assert ter.name == "scrabble749c-issue7492-ter", ter
            assert standard.parent == bis.parent == ter.parent == rep_ccw / "worktrees"
        finally:
            watcher.CFG = ancien_cfg
    return {"windows_suffixes_ok": True}


def scenario_linux_inchange_avec_meme_config():
    """Issue #749 : la MÊME config (REP_TRAVAIL `.../CCW/Scrabble`), mais
    SANS forcer os.name="nt" (comportement normal de la machine qui exécute
    ce test), continue d'utiliser le dossier dédié CCL (`DOSSIER_WORKTREES_DEDIE`,
    inchangé depuis #740) — ce correctif ne touche QUE la branche Windows."""
    if os.name == "nt":
        print("    (sous-scénario ignoré : exécuté sur une vraie machine Windows)")
        return {"linux_inchange_ignore_sous_nt": True}
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_ccw = tmp_path / "CCW"
        rep_travail = rep_ccw / "Scrabble"
        rep_travail.mkdir(parents=True)

        ancien_cfg = watcher.CFG
        ancien_dossier_dedie = watcher.DOSSIER_WORKTREES_DEDIE
        dossier_dedie_linux = tmp_path / "home_simule" / "worktrees"
        watcher.DOSSIER_WORKTREES_DEDIE = dossier_dedie_linux
        watcher.CFG = watcher.Config(
            nom="scrabble749d", depot="AlainDelree/x",
            rep_travail=rep_travail, topic_ntfy="x",
        )
        try:
            chemin = watcher._chemin_worktree(7493)
            assert chemin == dossier_dedie_linux / "scrabble749d-issue7493", chemin
            assert chemin.parent != rep_ccw / "worktrees", \
                "sous Linux, le dossier dédié CCW ne doit pas être utilisé"
        finally:
            watcher.CFG = ancien_cfg
            watcher.DOSSIER_WORKTREES_DEDIE = ancien_dossier_dedie
    return {"linux_inchange_ok": True}


def scenario_worktree_herite_toujours_trouve_par_relance_sous_ccw():
    """Issue #749 : un worktree créé à l'ANCIEN emplacement (frère de
    REP_TRAVAIL) reste trouvé et repris par une RELANCE (issue #725) —
    `_trouver_worktree_reutilisable` interroge `git worktree list` et
    compare le NOM du dossier, jamais un chemin calculé, et NE LIT
    `os.name` NULLE PART dans son propre code : le mécanisme est par
    construction indépendant de la plateforme et de l'emplacement.

    NE force PAS `os.name = "nt"` ici, contrairement aux autres scénarios de
    ce fichier : `_trouver_worktree_reutilisable`/`_lister_worktrees_secondaires`
    construisent des `Path(...)` NUS à partir des chaînes renvoyées par `git
    worktree list` (pas des `Path` déjà construits comme dans
    `_chemin_worktree`) — sous `os.name="nt"` simulé, ces constructions
    deviennent de vraies `WindowsPath`, et `.resolve()`/`.is_dir()` lèvent
    `NotImplementedError: cannot instantiate 'WindowsPath' on your system`
    (limite de `pathlib`, pas du code testé). Exercer VRAIMENT cette
    fonction avec des chemins Windows réels n'est donc possible que sur une
    vraie machine CCW — à vérifier manuellement par Alain (voir rapport de
    clôture) ; ce scénario couvre la partie démontrable depuis Linux : le
    mécanisme lui-même ne contient aucune branche `os.name`."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="scrabble749e", depot="AlainDelree/x",
            rep_travail=rep_travail, topic_ntfy="x",
        )
        try:
            numero = 7494
            chemin_ancien = rep_travail.parent / f"scrabble749e-issue{numero}"
            branche = watcher._branche_worktree(numero)
            res = subprocess.run(
                ["git", "-C", str(rep_travail), "worktree", "add", str(chemin_ancien), "-b", branche],
                capture_output=True, text=True,
            )
            assert res.returncode == 0, res.stderr

            resultat = watcher._trouver_worktree_reutilisable(numero)
            assert resultat is not None, "le worktree hérité à l'ancien emplacement aurait dû être trouvé"
            assert resultat[0] == chemin_ancien, resultat
        finally:
            watcher.CFG = ancien_cfg
    return {"worktree_herite_retrouve_sous_ccw_ok": True}


def scenario_comparaison_chemins_insensible_separateurs():
    """Issue #749 : `git worktree list` renvoie toujours des chemins en `/`,
    même sous Windows, alors que `_chemin_worktree` calcule un chemin natif
    (`\\`). `PureWindowsPath` (seule classe pathlib Windows réellement
    utilisable depuis Linux — contrairement à `WindowsPath`, elle ne fait
    AUCUN appel système) normalise les deux représentations de façon
    identique : c'est exactement la même logique de normalisation que
    `pathlib.WindowsPath.resolve()` applique réellement sous Windows, ce qui
    confirme que les comparaisons existantes dans
    `_lister_worktrees_secondaires`/`_trouver_worktree_reutilisable`
    (toutes deux basées sur `Path(...).resolve()`) fonctionnent déjà
    correctement avec le nouvel emplacement CCW, sans aucune modification."""
    chemin_git = PureWindowsPath("C:/CCW/worktrees/scrabble-issue444")
    chemin_natif = PureWindowsPath("C:\\CCW\\worktrees\\scrabble-issue444")
    assert chemin_git == chemin_natif, (chemin_git, chemin_natif)
    assert str(chemin_git) == str(chemin_natif) == "C:\\CCW\\worktrees\\scrabble-issue444"
    return {"comparaison_separateurs_ok": True}


def main():
    tests = [
        ("issue #749 — dossier dédié CCW dérivé de REP_TRAVAIL, jamais de Path.home()",
         scenario_windows_dossier_dedie_derive_de_rep_travail),
        ("issue #749 — repli sur l'ancien emplacement si le dossier dédié CCW est inaccessible",
         scenario_windows_repli_si_dossier_dedie_inaccessible),
        ("issue #749 — suffixes -bis/-ter inchangés sous CCW",
         scenario_windows_suffixes_inchanges),
        ("issue #749 — comportement CCL inchangé avec la même config",
         scenario_linux_inchange_avec_meme_config),
        ("issue #749 — worktree hérité à l'ancien emplacement toujours trouvé par une relance sous CCW",
         scenario_worktree_herite_toujours_trouve_par_relance_sous_ccw),
        ("issue #749 — comparaison de chemins insensible aux séparateurs (/ vs \\)",
         scenario_comparaison_chemins_insensible_separateurs),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)  # silencieux sauf échec de test lui-même

    ancien_cfg = watcher.CFG
    ancien_os_name = os.name
    echecs = 0
    try:
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
    finally:
        watcher.CFG = ancien_cfg
        os.name = ancien_os_name

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

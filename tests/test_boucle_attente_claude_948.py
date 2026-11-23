#!/usr/bin/env python3
"""Test de non-régression — issue #948.

Contexte : `lancer_claude` attendait jusqu'ici la fin du `claude` qu'il
lance via un unique `proc.communicate(timeout=timeout)` bloquant — pendant
cette attente, le watcher ne peut rien regarder d'autre. L'étude #939
(interruption d'UNE SEULE issue, sans toucher aux autres) a besoin que le
watcher puisse regarder régulièrement une demande d'interruption pendant
cette attente, d'où le remplacement, par cette issue, de l'attente unique
par une boucle de sondage courte (`_attendre_fin_claude`,
`INTERVALLE_SONDAGE_CLAUDE_S` ~3s) qui reproduit EXACTEMENT le comportement
observable d'avant : mêmes stdout/stderr/code retour, même gestion du
dépassement de délai (message, nettoyage de l'arbre via
`_nettoyer_arbre_claude`), rien d'autre de changé.

Ces scénarios remplacent `claude` par un faux exécutable bash paramétrable
par variables d'environnement (sommeil, sortie, code de retour, enfant
bloqué à nettoyer) — même schéma que `tests/test_nettoyage_arbre_247.py`.
`INTERVALLE_SONDAGE_CLAUDE_S` est réduit pour la durée de chaque scénario
qui en a besoin, afin de garder le test rapide sans changer son
comportement observable (seule la granularité des tours est resserrée).

Exécution :  python3 tests/test_boucle_attente_claude_948.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import stat
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
from garde_fou_faux_executables import verifier_faux_executables_actifs  # noqa: E402

FAKE_CLAUDE = r"""#!/bin/bash
# Faux `claude` paramétrable (issue #948) : sommeil, sortie (petite ou très
# volumineuse), code de retour, et option de lancer un enfant bloqué (même
# schéma que #247) pour le scénario de dépassement de délai.
if [ -n "$TEST_SPAWN_CHILD_948" ]; then
    python3 -c "open(\"$TEST_FIFO_948\", \"r\").read()" >/dev/null 2>&1 &
    echo $! > "$TEST_PIDFILE_948"
fi
if [ -n "$TEST_SLEEP_948" ]; then
    sleep "$TEST_SLEEP_948"
fi
if [ -n "$TEST_BIG_BYTES_948" ]; then
    python3 -c "
import sys
n = $TEST_BIG_BYTES_948
sys.stdout.write('A' * n)
sys.stdout.flush()
sys.stderr.write('B' * n)
sys.stderr.flush()
"
else
    if [ -n "$TEST_STDOUT_948" ]; then
        printf '%s' "$TEST_STDOUT_948"
    fi
    if [ -n "$TEST_STDERR_948" ]; then
        printf '%s' "$TEST_STDERR_948" >&2
    fi
fi
exit "${TEST_EXIT_948:-0}"
"""

VARS_948 = (
    "TEST_SPAWN_CHILD_948", "TEST_FIFO_948", "TEST_PIDFILE_948",
    "TEST_SLEEP_948", "TEST_BIG_BYTES_948", "TEST_STDOUT_948",
    "TEST_STDERR_948", "TEST_EXIT_948",
)


@contextmanager
def _environnement_faux_claude(tmp_path: Path, variables: dict):
    """Place le faux `claude` en tête du PATH et pose les variables
    d'environnement données (converties en str), pour la durée du bloc
    `with` — restaure PATH et retire toutes les variables à la sortie,
    scénario par scénario, sans effet de bord entre deux scénarios."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake_claude_path = bin_dir / "claude"
    fake_claude_path.write_text(FAKE_CLAUDE, encoding="utf-8")
    fake_claude_path.chmod(fake_claude_path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    ancien_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
    try:
        verifier_faux_executables_actifs(bin_dir, ["claude"])
        for cle, valeur in variables.items():
            os.environ[cle] = str(valeur)
        yield bin_dir
    finally:
        if ancien_path:
            os.environ["PATH"] = ancien_path
        else:
            os.environ.pop("PATH", None)
        for cle in VARS_948:
            os.environ.pop(cle, None)


@contextmanager
def _intervalle_sondage_reduit(valeur: float):
    """Réduit `INTERVALLE_SONDAGE_CLAUDE_S` pour la durée du bloc — garde les
    scénarios rapides sans changer le comportement observable (seule la
    granularité des tours change)."""
    ancien = watcher.INTERVALLE_SONDAGE_CLAUDE_S
    watcher.INTERVALLE_SONDAGE_CLAUDE_S = valeur
    try:
        yield
    finally:
        watcher.INTERVALLE_SONDAGE_CLAUDE_S = ancien


def _config_test(tmp_path: Path, nom: str) -> watcher.Config:
    return watcher.Config(
        nom=nom, depot="AlainDelree/Bridge_Agent",
        rep_travail=tmp_path, topic_ntfy=nom,
    )


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
        time.sleep(0.05)
    return False


def scenario_fin_normale_rapide():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948a")
        with _environnement_faux_claude(tmp_path, {"TEST_STDOUT_948": "sortie ok"}):
            succes, sortie = watcher.lancer_claude(
                numero=9001, titre="Test #948a", body="Corps",
                dry_run=False, mode=watcher.MODE_LECTURE,
                timeout=15, cwd=tmp_path,
            )
    assert succes, f"devait réussir : {sortie}"
    assert sortie == "sortie ok", f"stdout inattendu : {sortie!r}"
    return {"sortie": sortie}


def scenario_fin_normale_apres_plusieurs_tours():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948b")
        with _intervalle_sondage_reduit(0.2):
            with _environnement_faux_claude(tmp_path, {
                "TEST_SLEEP_948": "0.9", "TEST_STDOUT_948": "fini apres plusieurs tours",
            }):
                debut = time.monotonic()
                succes, sortie = watcher.lancer_claude(
                    numero=9002, titre="Test #948b", body="Corps",
                    dry_run=False, mode=watcher.MODE_LECTURE,
                    timeout=15, cwd=tmp_path,
                )
                duree = time.monotonic() - debut
    assert succes, f"devait réussir : {sortie}"
    assert sortie == "fini apres plusieurs tours", f"stdout inattendu : {sortie!r}"
    assert duree >= 0.8, f"le process a dû dormir ~0.9s, mesuré {duree:.2f}s — tours trop courts ?"
    return {"duree": round(duree, 2)}


def scenario_code_retour_non_nul():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948c")
        with _environnement_faux_claude(tmp_path, {
            "TEST_EXIT_948": "7", "TEST_STDERR_948": "boum",
        }):
            succes, sortie = watcher.lancer_claude(
                numero=9003, titre="Test #948c", body="Corps",
                dry_run=False, mode=watcher.MODE_LECTURE,
                timeout=15, cwd=tmp_path,
            )
    assert not succes, f"devait échouer (code 7) : {sortie}"
    assert sortie == "boum", f"stderr inattendu : {sortie!r}"
    return {"sortie": sortie}


def scenario_depassement_delai_arrete_arbre():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948d")
        fifo_path = tmp_path / "blocage.fifo"
        os.mkfifo(fifo_path)
        pidfile_path = tmp_path / "enfant.pid"
        with _intervalle_sondage_reduit(0.2):
            with _environnement_faux_claude(tmp_path, {
                "TEST_SPAWN_CHILD_948": "1",
                "TEST_FIFO_948": str(fifo_path),
                "TEST_PIDFILE_948": str(pidfile_path),
                "TEST_SLEEP_948": "10",
            }):
                succes, sortie = watcher.lancer_claude(
                    numero=9004, titre="Test #948d", body="Corps",
                    dry_run=False, mode=watcher.MODE_LECTURE,
                    timeout=1, cwd=tmp_path,
                )
        assert not succes, f"devait échouer (timeout) : {sortie}"
        assert sortie == "Timeout après 1s", f"message de timeout inattendu : {sortie!r}"
        assert pidfile_path.exists(), "le faux claude n'a pas écrit le PID de son enfant"
        pid_enfant = int(pidfile_path.read_text().strip())
        assert attendre_mort(pid_enfant, delai_max=5.0), (
            f"l'enfant bloqué (PID {pid_enfant}) est toujours vivant après le dépassement "
            f"de délai — l'arrêt de l'arbre de process n'a pas eu lieu comme avant."
        )
    return {"pid_enfant": pid_enfant}


def scenario_sortie_tres_volumineuse_sans_blocage():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948e")
        n = 2_000_000
        with _intervalle_sondage_reduit(0.2):
            with _environnement_faux_claude(tmp_path, {"TEST_BIG_BYTES_948": str(n)}):
                debut = time.monotonic()
                succes, sortie = watcher.lancer_claude(
                    numero=9005, titre="Test #948e", body="Corps",
                    dry_run=False, mode=watcher.MODE_LECTURE,
                    timeout=30, cwd=tmp_path,
                )
                duree = time.monotonic() - debut
    assert succes, (
        f"devait réussir — un échec ici (souvent un timeout) signale que claude s'est "
        f"bloqué en écriture faute de lecteur côté watcher : {sortie[:200]!r}"
    )
    assert len(sortie) == n, f"stdout tronqué ou incomplet : {len(sortie)} caractères, attendu {n}"
    assert duree < 15, f"bien trop lent pour {n} caractères sur deux tubes : {duree:.1f}s"
    return {"octets_stdout": len(sortie), "duree": round(duree, 2)}


def scenario_sortie_vide():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948f")
        with _environnement_faux_claude(tmp_path, {}):
            succes, sortie = watcher.lancer_claude(
                numero=9006, titre="Test #948f", body="Corps",
                dry_run=False, mode=watcher.MODE_LECTURE,
                timeout=15, cwd=tmp_path,
            )
    assert succes, f"devait réussir (sortie vide, exit 0) : {sortie}"
    assert sortie == "", f"stdout attendu vide, obtenu : {sortie!r}"
    return {}


def scenario_delai_maximal_respecte_a_un_tour_pres():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948g")
        tour = 0.3
        timeout = 1
        with _intervalle_sondage_reduit(tour):
            with _environnement_faux_claude(tmp_path, {"TEST_SLEEP_948": "10"}):
                debut = time.monotonic()
                succes, sortie = watcher.lancer_claude(
                    numero=9007, titre="Test #948g", body="Corps",
                    dry_run=False, mode=watcher.MODE_LECTURE,
                    timeout=timeout, cwd=tmp_path,
                )
                duree = time.monotonic() - debut
    assert not succes, f"devait échouer (timeout) : {sortie}"
    assert sortie == f"Timeout après {timeout}s", f"message inattendu : {sortie!r}"
    assert duree >= timeout, f"a rendu la main AVANT le délai maximal : {duree:.2f}s < {timeout}s"
    marge = tour + 1.0  # un tour de marge + marge de jitter pour un test fiable en CI
    assert duree <= timeout + marge, (
        f"dépassement du délai maximal de plus d'un tour : {duree:.2f}s pour "
        f"timeout={timeout}s et tour={tour}s"
    )
    return {"duree": round(duree, 2)}


def scenario_point_extension_appele_a_chaque_tour_sans_effet():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        watcher.CFG = _config_test(tmp_path, "test948h")
        appels = []
        originale = watcher._verifier_demande_interruption

        def compteur(numero):
            appels.append(numero)
            return originale(numero)

        watcher._verifier_demande_interruption = compteur
        try:
            with _intervalle_sondage_reduit(0.1):
                with _environnement_faux_claude(tmp_path, {
                    "TEST_SLEEP_948": "0.6", "TEST_STDOUT_948": "ok",
                }):
                    succes, sortie = watcher.lancer_claude(
                        numero=9008, titre="Test #948h", body="Corps",
                        dry_run=False, mode=watcher.MODE_LECTURE,
                        timeout=15, cwd=tmp_path,
                    )
        finally:
            watcher._verifier_demande_interruption = originale
    assert succes, f"devait réussir : {sortie}"
    assert sortie == "ok", f"stdout inattendu : {sortie!r}"
    assert len(appels) >= 2, f"le point d'extension aurait dû être appelé à plusieurs tours, appels={appels}"
    assert all(n == 9008 for n in appels), f"le point d'extension n'a pas reçu le bon numéro d'issue : {appels}"
    return {"appels": len(appels)}


def main():
    if os.name == "nt":
        print("  (ignoré : test spécifique POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("fin normale rapide", scenario_fin_normale_rapide),
        ("fin normale après plusieurs tours", scenario_fin_normale_apres_plusieurs_tours),
        ("code retour non nul", scenario_code_retour_non_nul),
        ("dépassement de délai → arrêt de l'arbre de process", scenario_depassement_delai_arrete_arbre),
        ("sortie très volumineuse sur les deux tubes, sans blocage", scenario_sortie_tres_volumineuse_sans_blocage),
        ("sortie vide", scenario_sortie_vide),
        ("délai maximal respecté à un tour près", scenario_delai_maximal_respecte_a_un_tour_pres),
        ("point d'extension appelé à chaque tour, sans effet sur le résultat", scenario_point_extension_appele_a_chaque_tour_sans_effet),
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

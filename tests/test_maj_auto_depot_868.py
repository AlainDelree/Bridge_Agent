#!/usr/bin/env python3
"""Test de non-régression — issue #868 : mise à jour automatique FACULTATIVE
du dépôt de l'outil au lancement de new_issue.py.

Vérifie l'extension de `watcher.rafraichir_depot` (réutilisée sans être
dupliquée) et `watcher.tenter_maj_auto_demarrage` :
- dépôt déjà à jour → "a_jour", aucune modification du clone ;
- mise à jour possible (fast-forward réel) → "maj", avec la liste des
  fichiers changés (`avec_liste_fichiers=True`) ;
- modifications locales non enregistrées → "ignore" AVANT toute tentative de
  pull (git jamais invoqué pour le pull lui-même), le fichier modifié reste
  intact ;
- historique divergé (commit local non poussé) → "ignore", fast-forward
  impossible, rien n'est écrasé ;
- délai dépassé sur le pull → "echec", message explicite, jamais d'exception ;
- réglage MAJ_AUTO_DEPOT absent de identite_locale.conf → `tenter_maj_auto_
  demarrage()` renvoie {"statut": "desactive", ...} SANS appeler
  rafraichir_depot (donc sans la moindre commande git) ;
- bonus : réglage actif avec MAJ_AUTO_DEPOT_REMOTE/MAJ_AUTO_DEPOT_BRANCHE
  personnalisés → la commande git pull suit bien ce remote/cette branche.

Exécution :  python3 tests/test_maj_auto_depot_868.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
import identite  # noqa: E402
import new_issue  # noqa: E402 — import seul (main() gardé par __main__, aucun effet de bord)


def _git(rep: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=rep, check=check,
        capture_output=True, text=True, encoding="utf-8",
    )


def _init_origine_et_clone(tmp: Path) -> tuple[Path, Path]:
    """Dépôt distant minimal + un clone — mêmes commandes que les autres
    tests git du dépôt (ex. test_worktree_parallelisation_337.py)."""
    origine = tmp / "origine"
    clone = tmp / "clone"
    origine.mkdir()
    _git(origine, "init", "-q", "-b", "master")
    (origine / "f.txt").write_text("v1\n", encoding="utf-8")
    _git(origine, "add", "-A")
    _git(origine, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "v1")
    _git(tmp, "clone", "-q", str(origine), str(clone))
    _git(clone, "-c", "user.email=t@t", "-c", "user.name=t", "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    return origine, clone


def scenario_depot_a_jour():
    with tempfile.TemporaryDirectory() as tmp:
        _origine, clone = _init_origine_et_clone(Path(tmp))
        resultat = watcher.rafraichir_depot(clone, exiger_propre=True)
    assert resultat["statut"] == "a_jour", resultat
    assert "jour" in resultat["message"]


def scenario_mise_a_jour_possible():
    with tempfile.TemporaryDirectory() as tmp:
        origine, clone = _init_origine_et_clone(Path(tmp))
        (origine / "nouveau.txt").write_text("v2\n", encoding="utf-8")
        _git(origine, "add", "-A")
        _git(origine, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "v2")

        resultat = watcher.rafraichir_depot(clone, exiger_propre=True, avec_liste_fichiers=True)

        assert resultat["statut"] == "maj", resultat
        assert resultat["fichiers"] == ["nouveau.txt"], resultat
        assert (clone / "nouveau.txt").read_text(encoding="utf-8") == "v2\n"


def scenario_modifications_locales():
    with tempfile.TemporaryDirectory() as tmp:
        origine, clone = _init_origine_et_clone(Path(tmp))
        (origine / "nouveau.txt").write_text("v2\n", encoding="utf-8")
        _git(origine, "add", "-A")
        _git(origine, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "v2")

        # Modification locale NON enregistrée, sans rapport avec le fichier
        # qui changerait côté distant — un pull réel resterait sans danger,
        # mais le réglage #868 doit renoncer avant même de tenter.
        (clone / "f.txt").write_text("modifié localement\n", encoding="utf-8")

        appel_pull = mock.Mock(wraps=subprocess.run)
        with mock.patch.object(watcher.subprocess, "run", side_effect=lambda cmd, **kw: (
            appel_pull(cmd, **kw) if cmd[:2] != ["git", "pull"]
            else (_ for _ in ()).throw(AssertionError("git pull n'aurait pas dû être tenté"))
        )):
            resultat = watcher.rafraichir_depot(clone, exiger_propre=True)

        assert resultat["statut"] == "ignore", resultat
        assert "non enregistrées" in resultat["message"], resultat
        assert (clone / "f.txt").read_text(encoding="utf-8") == "modifié localement\n"


def scenario_divergence():
    with tempfile.TemporaryDirectory() as tmp:
        origine, clone = _init_origine_et_clone(Path(tmp))

        # Commit local non poussé (ex. backup/fix d'un CCL/CCW en attente de
        # revue) ET un commit distant différent : historiques divergés.
        (clone / "f.txt").write_text("v1\nlocal\n", encoding="utf-8")
        _git(clone, "add", "-A")
        _git(clone, "commit", "-q", "-m", "local")

        (origine / "f.txt").write_text("v1\ndistant\n", encoding="utf-8")
        _git(origine, "add", "-A")
        _git(origine, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "distant")

        resultat = watcher.rafraichir_depot(clone, exiger_propre=True)

        assert resultat["statut"] == "ignore", resultat
        assert "fast-forward" in resultat["message"], resultat
        # Rien n'a été écrasé : le commit local est toujours HEAD.
        tete = _git(clone, "log", "-1", "--format=%s").stdout.strip()
        assert tete == "local", tete


def scenario_delai_depasse():
    """Depuis l'issue #872, un délai dépassé SANS avancée et sans verrou
    résiduel n'est plus un "echec" (trop alarmant pour un cas en fait sans
    risque) mais un "ignore" de cause "reseau" — voir
    tests/test_maj_auto_depot_872.py pour le reste du nouveau comportement
    (avancée malgré le délai, verrou résiduel, nouvelle tentative)."""
    with tempfile.TemporaryDirectory() as tmp:
        _origine, clone = _init_origine_et_clone(Path(tmp))

        class _PopenDelaiDepasse:
            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.pid = 999999999
                self.returncode = None

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(self.cmd, timeout)

            def wait(self, timeout=None):
                self.returncode = -9

            def kill(self):
                pass

        vrai_popen = subprocess.Popen

        def _popen_mock(cmd, **kwargs):
            # Seul le git pull lui-même est simulé en délai dépassé — tout
            # autre appel Popen (y compris ceux internes à subprocess.run,
            # utilisés par _est_depot_git/_tete_git/etc.) doit continuer à
            # fonctionner normalement.
            if cmd[:2] == ["git", "pull"]:
                return _PopenDelaiDepasse(cmd, **kwargs)
            return vrai_popen(cmd, **kwargs)

        with mock.patch.object(watcher.subprocess, "Popen", side_effect=_popen_mock), \
             mock.patch.object(watcher.os, "killpg", side_effect=ProcessLookupError):
            resultat = watcher.rafraichir_depot(clone, exiger_propre=True, timeout=3)

    assert resultat["statut"] == "ignore", resultat
    assert resultat["cause"] == "reseau", resultat
    assert "délai dépassé" in resultat["message"], resultat
    assert "3" in resultat["message"], resultat


def scenario_reglage_absent():
    identite.compte_github.cache_clear()
    with tempfile.TemporaryDirectory() as tmp:
        chemin_identite = Path(tmp) / "identite_locale.conf"  # n'existe pas

        def _rafraichir_jamais_appele(*a, **k):
            raise AssertionError("rafraichir_depot n'aurait pas dû être appelé : réglage absent")

        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin_identite), \
             mock.patch.object(watcher, "rafraichir_depot", side_effect=_rafraichir_jamais_appele):
            resultat = watcher.tenter_maj_auto_demarrage(Path(tmp))

    assert resultat == {"statut": "desactive", "message": None}, resultat


def scenario_reglage_actif_remote_branche_personnalises():
    """MAJ_AUTO_DEPOT=oui + MAJ_AUTO_DEPOT_REMOTE/MAJ_AUTO_DEPOT_BRANCHE dans
    identite_locale.conf : la commande git pull suit bien ce remote/cette
    branche plutôt que le défaut du dépôt (issue #868, point 4)."""
    identite.compte_github.cache_clear()
    with tempfile.TemporaryDirectory() as tmp:
        _origine, clone = _init_origine_et_clone(Path(tmp))
        chemin_identite = Path(tmp) / "identite_locale.conf"
        chemin_identite.write_text(
            "MAJ_AUTO_DEPOT = oui\n"
            "MAJ_AUTO_DEPOT_REMOTE = upstream\n"
            "MAJ_AUTO_DEPOT_BRANCHE = main\n",
            encoding="utf-8",
        )

        commandes = []
        vrai_popen = subprocess.Popen

        def _popen_espion(cmd, **kwargs):
            commandes.append(cmd)
            # Le remote "upstream"/branche "main" n'existent pas dans ce
            # clone minimal : le pull réel échoue (cause "autre", pas
            # "reseau" — pas de nouvelle tentative), seule la commande
            # construite nous intéresse ici.
            return vrai_popen(cmd, **kwargs)

        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin_identite), \
             mock.patch.object(watcher.subprocess, "Popen", side_effect=_popen_espion):
            watcher.tenter_maj_auto_demarrage(clone)

    appels_pull = [c for c in commandes if c[:2] == ["git", "pull"]]
    assert len(appels_pull) == 1, appels_pull
    assert appels_pull[0] == ["git", "pull", "--ff-only", "upstream", "main"], appels_pull[0]


def scenario_messages_affiches_a_utilisateur():
    """`new_issue._formater_message_maj_auto_depot` : rien n'est silencieux —
    chaque statut produit un message explicite (sauf "desactive", qui ne
    doit rien afficher du tout, cf. scenario_reglage_absent), avec la liste
    des fichiers et le rappel « watchers déjà démarrés » pour "maj"."""
    assert new_issue._formater_message_maj_auto_depot(
        {"statut": "desactive", "message": None}) is None

    msg = new_issue._formater_message_maj_auto_depot({"statut": "a_jour", "message": "déjà à jour."})
    assert "déjà à jour" in msg, msg

    msg = new_issue._formater_message_maj_auto_depot(
        {"statut": "maj", "message": "abc123 → def456", "fichiers": ["watcher.py", "identite.py"]})
    assert "watcher.py, identite.py" in msg, msg
    assert "watchers déjà démarrés" in msg and "relancés" in msg, msg

    msg = new_issue._formater_message_maj_auto_depot(
        {"statut": "ignore", "message": "modifications locales non enregistrées"})
    assert "ignorée" in msg and "modifications locales non enregistrées" in msg, msg

    msg = new_issue._formater_message_maj_auto_depot({"statut": "echec", "message": "réseau indisponible (...)"})
    assert "échec" in msg and "réseau indisponible" in msg, msg


def main() -> int:
    tests = [
        ("dépôt déjà à jour", scenario_depot_a_jour),
        ("mise à jour possible (fast-forward réel)", scenario_mise_a_jour_possible),
        ("modifications locales non enregistrées → ignoré sans tenter", scenario_modifications_locales),
        ("historique divergé → ignoré, rien d'écrasé", scenario_divergence),
        ("délai dépassé sur le pull → échec explicite", scenario_delai_depasse),
        ("réglage MAJ_AUTO_DEPOT absent → désactivé, aucun appel git", scenario_reglage_absent),
        ("réglage actif, remote/branche personnalisés", scenario_reglage_actif_remote_branche_personnalises),
        ("messages affichés à l'utilisateur, pour chaque statut", scenario_messages_affiches_a_utilisateur),
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

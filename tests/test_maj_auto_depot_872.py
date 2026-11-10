#!/usr/bin/env python3
"""Test de non-régression — issue #872 : délai de la mise à jour automatique
du dépôt (#868) adapté au démarrage de session, fin du faux « échec ».

Vérifie le nouveau comportement de `watcher.rafraichir_depot` et
`watcher.tenter_maj_auto_demarrage` :
- délai dépassé mais le dépôt a malgré tout avancé (sous-process orphelin
  supposé avoir terminé le travail) → "maj", PAS "echec" ;
- délai dépassé SANS avancée, sans verrou résiduel → "ignore" (cause
  "reseau"), plus jamais "echec" pour ce cas sans risque ;
- verrou `index.lock` résiduel après délai dépassé, arrêt du process
  CONFIRMÉ → considéré périmé avec certitude, supprimé, "ignore" ;
- verrou résiduel après délai dépassé, arrêt du process NON confirmé →
  jamais supprimé, "echec" explicite (cause "verrou_incertain") ;
- verrou déjà présent AVANT toute tentative → "ignore" (cause "verrou"),
  aucune tentative de pull, verrou jamais touché ;
- réseau absent puis présent : `tenter_maj_auto_demarrage` retente
  automatiquement après une pause et réussit au second essai ;
- `MAJ_AUTO_DEPOT_DELAI` dans identite_locale.conf : délai personnalisé lu et
  appliqué (repli sur le défaut si absent/invalide).

Exécution :  python3 tests/test_maj_auto_depot_872.py
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


def _git(rep: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=rep, check=check,
        capture_output=True, text=True, encoding="utf-8",
    )


def _init_origine_et_clone(tmp: Path) -> tuple[Path, Path]:
    origine = tmp / "origine"
    clone = tmp / "clone"
    origine.mkdir()
    _git(origine, "init", "-q", "-b", "master")
    (origine / "f.txt").write_text("v1\n", encoding="utf-8")
    _git(origine, "add", "-A")
    _git(origine, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "v1")
    _git(tmp, "clone", "-q", str(origine), str(clone))
    _git(clone, "config", "user.email", "t@t")
    _git(clone, "config", "user.name", "t")
    return origine, clone


def _patch_popen(side_effect_pull):
    """Remplace watcher.subprocess.Popen, mais délègue au vrai Popen pour
    tout appel qui n'est PAS le git pull testé — nécessaire car
    `subprocess.run` (utilisé par _est_depot_git/_tete_git/_depot_est_propre/
    _chemin_verrou_index_git/_fichiers_modifies_par_pull) appelle lui-même
    Popen en interne."""
    vrai_popen = subprocess.Popen

    def _mock(cmd, **kwargs):
        if cmd[:2] == ["git", "pull"]:
            return side_effect_pull(cmd, **kwargs)
        return vrai_popen(cmd, **kwargs)

    return mock.patch.object(watcher.subprocess, "Popen", side_effect=_mock)


def scenario_delai_depasse_mais_avance():
    """Le délai est dépassé, mais le dépôt a malgré tout avancé — simule
    l'hypothèse retenue pour le faux échec constaté (sous-process orphelin
    ayant terminé le fetch/fast-forward après l'arrêt du process de tête,
    jamais confirmé faute de pouvoir reproduire depuis Linux) en effectuant
    le VRAI pull à l'intérieur du communicate() simulé, puis en levant
    TimeoutExpired comme si notre code avait cessé de l'attendre pile à ce
    moment-là."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        origine, clone = _init_origine_et_clone(tmp)
        (origine / "nouveau.txt").write_text("v2\n", encoding="utf-8")
        _git(origine, "add", "-A")
        _git(origine, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "v2")

        class _PopenAvanceMalgreDelai:
            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.cwd = kwargs.get("cwd")
                self.pid = 999101
                self.returncode = None

            def communicate(self, timeout=None):
                # "git fetch" + "git merge" plutôt que "git pull" : simule le
                # travail réel qu'aurait fini un sous-process orphelin, SANS
                # ré-entrer dans ce même mock (qui n'intercepte que le cmd
                # "git pull" exact).
                subprocess.run(["git", "fetch"], cwd=self.cwd,
                                capture_output=True, text=True, encoding="utf-8")
                subprocess.run(["git", "merge", "--ff-only", "FETCH_HEAD"], cwd=self.cwd,
                                capture_output=True, text=True, encoding="utf-8")
                raise subprocess.TimeoutExpired(self.cmd, timeout)

            def wait(self, timeout=None):
                self.returncode = -9

            def kill(self):
                pass

        with _patch_popen(_PopenAvanceMalgreDelai), \
             mock.patch.object(watcher.os, "killpg", side_effect=ProcessLookupError):
            resultat = watcher.rafraichir_depot(clone, exiger_propre=True, timeout=2,
                                                 avec_liste_fichiers=True)

        assert resultat["statut"] == "maj", resultat
        assert resultat["cause"] is None, resultat
        assert "délai" in resultat["message"] and "dépassé" in resultat["message"], resultat
        assert resultat["fichiers"] == ["nouveau.txt"], resultat
        assert (clone / "nouveau.txt").read_text(encoding="utf-8") == "v2\n"


def scenario_delai_depasse_sans_avance():
    """Délai dépassé, rien n'a bougé, aucun verrou résiduel : état parfaitement
    sûr — ne doit JAMAIS être annoncé comme un "echec" alarmant."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _origine, clone = _init_origine_et_clone(tmp)

        class _PopenTimeoutSansAvance:
            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.pid = 999102
                self.returncode = None

            def communicate(self, timeout=None):
                raise subprocess.TimeoutExpired(self.cmd, timeout)

            def wait(self, timeout=None):
                self.returncode = -9

            def kill(self):
                pass

        with _patch_popen(_PopenTimeoutSansAvance), \
             mock.patch.object(watcher.os, "killpg", side_effect=ProcessLookupError):
            resultat = watcher.rafraichir_depot(clone, exiger_propre=True, timeout=2)

        assert resultat["statut"] == "ignore", resultat
        assert resultat["cause"] == "reseau", resultat
        assert not (clone / ".git" / "index.lock").exists()


def scenario_verrou_residuel_nettoye_apres_arret_confirme():
    """Le process est arrêté avec certitude (killpg réussit), mais un
    index.lock créé par CETTE tentative (aucun ne préexistait) subsiste : il
    est alors — et seulement alors — considéré périmé et supprimé."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _origine, clone = _init_origine_et_clone(tmp)

        class _PopenTimeoutAvecVerrou:
            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.cwd = kwargs.get("cwd")
                self.pid = 999103
                self.returncode = None

            def communicate(self, timeout=None):
                (Path(self.cwd) / ".git" / "index.lock").write_text("", encoding="utf-8")
                raise subprocess.TimeoutExpired(self.cmd, timeout)

            def wait(self, timeout=None):
                self.returncode = -9

            def kill(self):
                pass

        with _patch_popen(_PopenTimeoutAvecVerrou), \
             mock.patch.object(watcher.os, "killpg", return_value=None):
            resultat = watcher.rafraichir_depot(clone, exiger_propre=True, timeout=2)

        assert resultat["statut"] == "ignore", resultat
        assert resultat["cause"] == "reseau", resultat
        assert not (clone / ".git" / "index.lock").exists(), "verrou périmé confirmé : doit être nettoyé"


def scenario_verrou_residuel_sans_confirmation_jamais_supprime():
    """Même scénario, mais l'arrêt du process N'EST PAS confirmé (droits
    refusés) : le verrou résiduel ne doit JAMAIS être supprimé, et le statut
    redevient "echec" — seul cas légitime, l'état n'étant alors plus sûr."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _origine, clone = _init_origine_et_clone(tmp)

        class _PopenTimeoutVerrouIncertain:
            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.cwd = kwargs.get("cwd")
                self.pid = 999104
                self.returncode = None

            def communicate(self, timeout=None):
                (Path(self.cwd) / ".git" / "index.lock").write_text("", encoding="utf-8")
                raise subprocess.TimeoutExpired(self.cmd, timeout)

            def wait(self, timeout=None):
                self.returncode = -9

            def kill(self):
                pass

        with _patch_popen(_PopenTimeoutVerrouIncertain), \
             mock.patch.object(watcher.os, "killpg", side_effect=PermissionError("refusé")):
            resultat = watcher.rafraichir_depot(clone, exiger_propre=True, timeout=2)

        assert resultat["statut"] == "echec", resultat
        assert resultat["cause"] == "verrou_incertain", resultat
        assert (clone / ".git" / "index.lock").exists(), "verrou NON confirmé périmé : ne jamais le supprimer"


def scenario_verrou_deja_present_avant_tentative():
    """Un index.lock déjà présent AVANT même de lancer le pull (opération git
    concurrente, ou résidu d'un lancement précédent) fait renoncer sans
    jamais tenter le pull — et sans jamais y toucher."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _origine, clone = _init_origine_et_clone(tmp)
        verrou = clone / ".git" / "index.lock"
        verrou.write_text("", encoding="utf-8")

        appel_pull = mock.Mock()

        def _jamais_appele(cmd, **kwargs):
            appel_pull(cmd, **kwargs)
            raise AssertionError("git pull n'aurait pas dû être tenté : verrou déjà présent")

        with _patch_popen(_jamais_appele):
            resultat = watcher.rafraichir_depot(clone, exiger_propre=True)

        assert resultat["statut"] == "ignore", resultat
        assert resultat["cause"] == "verrou", resultat
        assert not appel_pull.called
        assert verrou.exists(), "un verrou préexistant ne doit jamais être supprimé automatiquement"


def scenario_reseau_absent_puis_present():
    """`tenter_maj_auto_demarrage` retente automatiquement après un premier
    échec réseau (cause "reseau") et réussit au second essai, une fois le
    réseau "revenu" — issue #872, point 2."""
    identite.compte_github.cache_clear()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        origine, clone = _init_origine_et_clone(tmp)
        (origine / "nouveau.txt").write_text("v2\n", encoding="utf-8")
        _git(origine, "add", "-A")
        _git(origine, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "v2")

        chemin_identite = tmp / "identite_locale.conf"
        chemin_identite.write_text("MAJ_AUTO_DEPOT = oui\n", encoding="utf-8")

        compteur = {"appels": 0}

        class _PopenReseauPuisOk:
            def __init__(self, cmd, **kwargs):
                self.cmd = cmd
                self.cwd = kwargs.get("cwd")
                self.pid = 999105
                self.returncode = None

            def communicate(self, timeout=None):
                compteur["appels"] += 1
                if compteur["appels"] == 1:
                    self.returncode = 1
                    return "", ("fatal: unable to access 'https://example/depot.git/': "
                                "Could not resolve host: example")
                # Réseau "revenu" : fetch + merge --ff-only plutôt que "git
                # pull" (qui ré-entrerait dans ce même mock).
                subprocess.run(["git", "fetch"], cwd=self.cwd,
                                capture_output=True, text=True, encoding="utf-8")
                res = subprocess.run(["git", "merge", "--ff-only", "FETCH_HEAD"], cwd=self.cwd,
                                      capture_output=True, text=True, encoding="utf-8")
                self.returncode = res.returncode
                return res.stdout, res.stderr

            def wait(self, timeout=None):
                pass

            def kill(self):
                pass

        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin_identite), \
             _patch_popen(_PopenReseauPuisOk), \
             mock.patch.object(watcher.time, "sleep"):
            resultat = watcher.tenter_maj_auto_demarrage(clone)

        assert compteur["appels"] == 2, compteur
        assert resultat["statut"] == "maj", resultat
        assert resultat["fichiers"] == ["nouveau.txt"], resultat


def scenario_delai_personnalise_dans_identite_locale():
    """MAJ_AUTO_DEPOT_DELAI dans identite_locale.conf remplace le délai par
    défaut (30s) de tenter_maj_auto_demarrage — issue #872, point 2."""
    identite.compte_github.cache_clear()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _origine, clone = _init_origine_et_clone(tmp)
        chemin_identite = tmp / "identite_locale.conf"
        chemin_identite.write_text(
            "MAJ_AUTO_DEPOT = oui\nMAJ_AUTO_DEPOT_DELAI = 5\n", encoding="utf-8")

        delais_vus = []

        def _rafraichir_espion(rep, **kwargs):
            delais_vus.append(kwargs.get("timeout"))
            return {"statut": "a_jour", "message": "déjà à jour.", "cause": None}

        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin_identite), \
             mock.patch.object(watcher, "rafraichir_depot", side_effect=_rafraichir_espion):
            watcher.tenter_maj_auto_demarrage(clone)

        assert delais_vus == [5], delais_vus


def scenario_delai_invalide_repli_sur_defaut():
    """Une valeur non entière de MAJ_AUTO_DEPOT_DELAI retombe sur le défaut
    (TIMEOUT_MAJ_AUTO_DEMARRAGE) plutôt que de lever une exception."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        chemin_identite = tmp / "identite_locale.conf"
        chemin_identite.write_text("MAJ_AUTO_DEPOT_DELAI = pas-un-nombre\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin_identite):
            assert watcher._delai_maj_auto_demarrage() == watcher.TIMEOUT_MAJ_AUTO_DEMARRAGE


def main() -> int:
    tests = [
        ("délai dépassé mais dépôt avancé → maj (pas d'échec)", scenario_delai_depasse_mais_avance),
        ("délai dépassé sans avancée, aucun verrou → ignoré sans alarme", scenario_delai_depasse_sans_avance),
        ("verrou résiduel + arrêt confirmé → nettoyé, ignoré", scenario_verrou_residuel_nettoye_apres_arret_confirme),
        ("verrou résiduel + arrêt NON confirmé → jamais supprimé, echec", scenario_verrou_residuel_sans_confirmation_jamais_supprime),
        ("verrou déjà présent avant tentative → ignoré sans y toucher", scenario_verrou_deja_present_avant_tentative),
        ("réseau absent puis présent → nouvelle tentative automatique réussie", scenario_reseau_absent_puis_present),
        ("MAJ_AUTO_DEPOT_DELAI personnalisé appliqué", scenario_delai_personnalise_dans_identite_locale),
        ("MAJ_AUTO_DEPOT_DELAI invalide → repli sur le défaut", scenario_delai_invalide_repli_sur_defaut),
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

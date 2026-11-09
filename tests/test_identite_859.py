#!/usr/bin/env python3
"""Test de non-régression — issue #859 : `identite.py`, seule source de
vérité pour le compte GitHub et l'utilisateur SSH par défaut (plus aucune
valeur propre à Alain codée en dur ailleurs dans le dépôt).

Vérifie :
- `compte_github()` préfère `identite_locale.conf` (COMPTE_GITHUB=...) à
  `gh` quand les deux sont disponibles ;
- à défaut de fichier local, `compte_github()` retombe sur `gh api user`
  (mocké ici, aucun accès réseau) ;
- si ni le fichier local ni `gh` ne fournissent de valeur, `compte_github()`
  renvoie `None` plutôt que de lever une exception ou de retomber sur une
  valeur par défaut — c'est ce `None` qui fait que `watcher.auteurs_
  autorises()` renvoie un ensemble VIDE (garde-fou §8 : refuser de traiter
  les issues plutôt qu'ouvrir l'accès à tout le monde, voir
  `tests/test_filtre_auteur_563.py`) et que `verifier_identite_demarrage()`
  arrête le watcher au lancement (`sys.exit`) ;
- `utilisateur_ssh_defaut()` lit UTILISATEUR_SSH dans le fichier local, et
  retombe sur le repli historique "AlainW" à défaut (comportement inchangé
  pour l'installation d'Alain, sans rien configurer de plus).

`compte_github()` est mis en cache (`functools.lru_cache`) : chaque scénario
vide ce cache avant de s'exécuter pour rester indépendant des autres.

Exécution :  python3 tests/test_identite_859.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import identite  # noqa: E402


def _executer(fichier_local_contenu, gh_resultat, fn):
    """Exécute `fn()` avec FICHIER_IDENTITE_LOCALE pointé vers un fichier
    temporaire (contenu `fichier_local_contenu`, ou aucun fichier si None) et
    `subprocess.run` mocké pour renvoyer `gh_resultat` (ou lever OSError si
    None, simulant `gh` absent). Vide le cache de compte_github() avant et
    après pour isoler le scénario."""
    identite.compte_github.cache_clear()
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        if fichier_local_contenu is not None:
            chemin.write_text(fichier_local_contenu, encoding="utf-8")

        def _run_mock(*args, **kwargs):
            if gh_resultat is None:
                raise OSError("gh introuvable (simulé)")
            return gh_resultat

        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin), \
             mock.patch.object(identite.subprocess, "run", side_effect=_run_mock):
            try:
                return fn()
            finally:
                identite.compte_github.cache_clear()


def scenario_fichier_local_prioritaire_sur_gh():
    """COMPTE_GITHUB dans identite_locale.conf : utilisé directement, `gh`
    n'est même pas appelé (vérifié en le faisant lever si invoqué)."""
    def _gh_jamais_appele(*a, **k):
        raise AssertionError("gh n'aurait pas dû être appelé : fichier local prioritaire")

    identite.compte_github.cache_clear()
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("COMPTE_GITHUB = unAmi\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin), \
             mock.patch.object(identite.subprocess, "run", side_effect=_gh_jamais_appele):
            compte = identite.compte_github()
            identite.compte_github.cache_clear()
    assert compte == "unAmi", f"Attendu 'unAmi' depuis le fichier local, obtenu {compte!r}"


def scenario_repli_sur_gh_sans_fichier_local():
    """Sans identite_locale.conf : repli sur `gh api user --jq .login`
    (mocké, aucun accès réseau) — comportement inchangé pour Alain."""
    gh_ok = mock.Mock(returncode=0, stdout="AlainDelree\n", stderr="")
    compte = _executer(None, gh_ok, identite.compte_github)
    assert compte == "AlainDelree", f"Attendu 'AlainDelree' depuis gh, obtenu {compte!r}"


def scenario_aucune_source_renvoie_none():
    """Ni fichier local ni `gh` disponible (gh absent/non authentifié) :
    compte_github() renvoie None plutôt qu'une exception ou une valeur par
    défaut — c'est ce None qui déclenche le refus de traiter (§8)."""
    compte = _executer(None, None, identite.compte_github)
    assert compte is None, f"Attendu None quand aucune source n'est disponible, obtenu {compte!r}"


def scenario_gh_authentification_echouee_renvoie_none():
    """`gh` présent mais non authentifié (returncode != 0) : None, pas
    d'exception."""
    gh_echec = mock.Mock(returncode=1, stdout="", stderr="gh: not logged in")
    compte = _executer(None, gh_echec, identite.compte_github)
    assert compte is None, f"Attendu None si gh échoue, obtenu {compte!r}"


def scenario_utilisateur_ssh_depuis_fichier_local():
    """UTILISATEUR_SSH dans identite_locale.conf : repris tel quel."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("UTILISATEUR_SSH = UnAmiW\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            utilisateur = identite.utilisateur_ssh_defaut()
    assert utilisateur == "UnAmiW", f"Attendu 'UnAmiW', obtenu {utilisateur!r}"


def scenario_utilisateur_ssh_repli_historique():
    """Sans fichier local (ou sans clé UTILISATEUR_SSH dedans) : repli sur
    le repli historique 'AlainW' — comportement inchangé pour Alain."""
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            utilisateur = identite.utilisateur_ssh_defaut()
    assert utilisateur == identite.UTILISATEUR_SSH_HISTORIQUE == "AlainW", (
        f"Attendu le repli historique 'AlainW', obtenu {utilisateur!r}"
    )


def main() -> int:
    tests = [
        ("fichier local prioritaire sur gh", scenario_fichier_local_prioritaire_sur_gh),
        ("repli sur gh sans fichier local", scenario_repli_sur_gh_sans_fichier_local),
        ("aucune source → None (pas d'exception)", scenario_aucune_source_renvoie_none),
        ("gh non authentifié → None", scenario_gh_authentification_echouee_renvoie_none),
        ("utilisateur SSH depuis le fichier local", scenario_utilisateur_ssh_depuis_fichier_local),
        ("utilisateur SSH : repli historique AlainW", scenario_utilisateur_ssh_repli_historique),
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

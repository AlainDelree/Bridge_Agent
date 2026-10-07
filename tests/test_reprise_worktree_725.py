#!/usr/bin/env python3
"""Test de non-régression — issue #725 : réutilisation du worktree existant
d'une issue mode_write lors d'une RELANCE (nouveau traitement après un échec/
timeout/needs-human de la tentative précédente), au lieu de créer
systématiquement un `-bis` vierge basé sur master qui abandonne le travail
déjà fait (constaté sur Rummikub #146).

Vérifie, à l'échelle logique (`_preparer_worktree_ecriture` /
`_trouver_worktree_reutilisable`), sur des dépôts git jetables :
1. Relance avec un worktree valide déjà existant pour cette issue : il est
   REPRIS tel quel, aucun `-bis` créé.
2. Première exécution (aucun worktree existant pour cette issue) : création
   normale via le chemin historique (nom standard).
3. Dossier présent au chemin standard mais PAS enregistré comme worktree de
   ce dépôt (simple dossier) : repli `-bis` comme avant ce correctif.
4. Une modification non commitée du worktree repris est conservée (pas de
   `git reset`/`clean` au moment de la reprise).
5. Deuxième relance : le même worktree est de nouveau repris (pas de
   `-bis`/`-ter` qui s'accumule au fil des relances successives).
6. Plusieurs worktrees hérités pour la même issue (cas antérieur à ce
   correctif, standard + `-bis`) : le plus récemment modifié (dernier
   commit) est choisi.
7. Le bloc de prompt « worktree repris » (`lancer_claude`) n'apparaît QUE
   quand `worktree_repris=True` — absent par défaut (première exécution).

Un worktree verrouillé par un traitement en cours (`_worktree_en_cours_de_
traitement`) n'est jamais repris — testé directement en posant un faux
verrou avec un PID vivant (celui du process de test lui-même).

Exécution :  python3 tests/test_reprise_worktree_725.py
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


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _ajouter_commit(rep: Path, nom_fichier: str, message: str) -> None:
    (rep / nom_fichier).write_text("contenu\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", message], cwd=rep, check=True, capture_output=True)


def _config_isolee(rep_travail: Path, nom: str) -> watcher.Config:
    return watcher.Config(
        nom=nom, depot="AlainDelree/x",
        rep_travail=rep_travail, topic_ntfy=nom,
    )


class _ContexteCfgEtVerrous:
    """Isole watcher.CFG et watcher.DOSSIER_VERROUS pour la durée d'un
    scénario — même esprit que `_contexte_watcher_isole` de
    test_worktree_parallelisation_337.py, réduit ici au strict nécessaire
    (ces scénarios ne lancent aucun thread/claude réel)."""

    def __init__(self, cfg: watcher.Config, dossier_verrous: Path):
        self.cfg = cfg
        self.dossier_verrous = dossier_verrous

    def __enter__(self):
        self._ancien_cfg = watcher.CFG
        self._ancien_dossier_verrous = watcher.DOSSIER_VERROUS
        watcher.CFG = self.cfg
        watcher.DOSSIER_VERROUS = self.dossier_verrous
        return self

    def __exit__(self, *exc):
        watcher.CFG = self._ancien_cfg
        watcher.DOSSIER_VERROUS = self._ancien_dossier_verrous
        return False


def scenario_relance_worktree_existant_repris():
    """(1) Un worktree valide déjà créé pour l'issue (simulant le travail
    d'une tentative précédente, timeout/needs-human) est REPRIS tel quel par
    `_preparer_worktree_ecriture` — aucun `-bis` créé."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        with _ContexteCfgEtVerrous(_config_isolee(rep_travail, "test725a"), tmp_path / "verrous"):
            numero = 7251
            # Simule le travail de la tentative précédente : worktree créé
            # normalement, puis un commit de travail dessus.
            chemin_initial, _ = watcher._creer_worktree(numero)
            assert chemin_initial is not None
            _ajouter_commit(chemin_initial, "travail.txt", "travail de la tentative précédente")

            resultat = watcher._preparer_worktree_ecriture(numero)
            assert resultat.chemin == chemin_initial, \
                f"le worktree existant aurait dû être repris, pas {resultat.chemin}"
            assert resultat.worktree_repris is True
            assert not watcher._chemin_worktree(numero, "-bis").exists(), \
                "aucun -bis n'aurait dû être créé : le worktree existant devait être repris"
            assert (resultat.chemin / "travail.txt").exists(), \
                "le travail déjà fait (commit de la tentative précédente) aurait dû être conservé"
        return {"reprise_ok": True}


def scenario_premiere_execution_creation_normale():
    """(2) Aucun worktree existant pour cette issue : création normale via le
    chemin historique (nom standard), comme avant ce correctif."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        with _ContexteCfgEtVerrous(_config_isolee(rep_travail, "test725b"), tmp_path / "verrous"):
            numero = 7252
            resultat = watcher._preparer_worktree_ecriture(numero)
            assert resultat.chemin == watcher._chemin_worktree(numero), \
                f"première exécution : nom standard attendu, obtenu {resultat.chemin}"
            assert resultat.worktree_repris is False
            assert resultat.commits_ecart == 0
            assert resultat.avertissement_worktree_repris == ""
        return {"premiere_execution_ok": True}


def scenario_dossier_non_enregistre_repli_bis():
    """(3) Le chemin standard existe comme simple DOSSIER (pas un worktree
    enregistré par `git worktree list` — ex. reliquat d'une autre nature) :
    `_trouver_worktree_reutilisable` ne le considère pas comme candidat, et
    le repli historique `-bis` s'applique, comme avant ce correctif."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        with _ContexteCfgEtVerrous(_config_isolee(rep_travail, "test725c"), tmp_path / "verrous"):
            numero = 7253
            # Dossier quelconque au chemin standard, PAS un worktree git.
            watcher._chemin_worktree(numero).mkdir(parents=True)

            assert watcher._trouver_worktree_reutilisable(numero) is None, \
                "un simple dossier non enregistré comme worktree ne doit jamais être choisi"

            resultat = watcher._preparer_worktree_ecriture(numero)
            assert resultat.chemin == watcher._chemin_worktree(numero, "-bis"), \
                f"repli -bis attendu (chemin standard occupé par un non-worktree) : {resultat.chemin}"
            assert resultat.worktree_repris is False
        return {"repli_bis_ok": True}


def scenario_modification_non_commitee_conservee():
    """(4) Une modification non commitée dans le worktree repris (fichier
    modifié, pas encore `git add`/`commit`) est conservée — la reprise ne
    doit jamais faire de `git reset --hard`/`git clean` sur le worktree."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        with _ContexteCfgEtVerrous(_config_isolee(rep_travail, "test725d"), tmp_path / "verrous"):
            numero = 7254
            chemin_initial, _ = watcher._creer_worktree(numero)
            assert chemin_initial is not None
            (chemin_initial / "non_commite.txt").write_text("brouillon en cours\n", encoding="utf-8")

            resultat = watcher._preparer_worktree_ecriture(numero)
            assert resultat.worktree_repris is True
            contenu = (resultat.chemin / "non_commite.txt").read_text(encoding="utf-8")
            assert contenu == "brouillon en cours\n", \
                "la modification non commitée aurait dû survivre à la reprise du worktree"
        return {"non_commite_conserve_ok": True}


def scenario_deuxieme_relance_meme_worktree_repris():
    """(5) Après une première reprise réussie (scénario 1), une DEUXIÈME
    relance reprend ENCORE le même worktree — pas d'accumulation de -bis/-ter
    au fil des relances successives sur une même issue."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        with _ContexteCfgEtVerrous(_config_isolee(rep_travail, "test725e"), tmp_path / "verrous"):
            numero = 7255
            chemin_initial, _ = watcher._creer_worktree(numero)
            assert chemin_initial is not None
            _ajouter_commit(chemin_initial, "v1.txt", "tentative 1")

            resultat_1 = watcher._preparer_worktree_ecriture(numero)
            assert resultat_1.chemin == chemin_initial
            assert resultat_1.worktree_repris is True
            _ajouter_commit(resultat_1.chemin, "v2.txt", "tentative 2 (relance 1)")

            resultat_2 = watcher._preparer_worktree_ecriture(numero)
            assert resultat_2.chemin == chemin_initial, \
                "la deuxième relance aurait dû reprendre le MÊME worktree, pas en créer un nouveau"
            assert resultat_2.worktree_repris is True
            assert not watcher._chemin_worktree(numero, "-bis").exists()
            assert not watcher._chemin_worktree(numero, "-ter").exists()
            assert (resultat_2.chemin / "v1.txt").exists() and (resultat_2.chemin / "v2.txt").exists()
        return {"deuxieme_relance_ok": True}


def scenario_plusieurs_worktrees_herites_le_plus_recent_choisi():
    """(6) Cas hérité d'avant ce correctif : standard ET `-bis` existent déjà
    tous les deux pour la même issue (deux relances successives, chacune
    ayant créé son propre worktree avant ce correctif) — le plus récemment
    modifié (dernier commit) doit être choisi."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)

        with _ContexteCfgEtVerrous(_config_isolee(rep_travail, "test725f"), tmp_path / "verrous"):
            numero = 7256
            chemin_standard, _ = watcher._creer_worktree(numero)
            assert chemin_standard is not None
            _ajouter_commit(chemin_standard, "ancien.txt", "ancien travail (standard)")

            chemin_bis, _ = watcher._creer_worktree(numero, "-bis")
            assert chemin_bis is not None
            # Assure un horodatage de commit strictement postérieur (résolution
            # à la seconde côté git log %ct) avant le commit sur -bis, pour
            # lever toute ambiguïté sur « le plus récent ».
            time.sleep(1.1)
            _ajouter_commit(chemin_bis, "recent.txt", "travail plus récent (-bis)")

            resultat = watcher._preparer_worktree_ecriture(numero)
            assert resultat.chemin == chemin_bis, \
                f"le worktree -bis (plus récent) aurait dû être choisi, pas {resultat.chemin}"
            assert resultat.worktree_repris is True
        return {"plus_recent_choisi_ok": True}


def scenario_worktree_verrouille_non_repris():
    """Un worktree par ailleurs valide mais actuellement VERROUILLÉ par un
    traitement en cours (fichier de verrou avec un PID vivant) ne doit jamais
    être repris — `_preparer_worktree_ecriture` retombe alors sur le chemin
    historique (`-bis`)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rep_travail = tmp_path / "projet"
        rep_travail.mkdir()
        _init_depot_git(rep_travail)
        dossier_verrous = tmp_path / "verrous"

        with _ContexteCfgEtVerrous(_config_isolee(rep_travail, "test725g"), dossier_verrous):
            numero = 7257
            chemin_initial, _ = watcher._creer_worktree(numero)
            assert chemin_initial is not None

            dossier_verrous.mkdir(parents=True, exist_ok=True)
            verrou = watcher._chemin_verrou(chemin_initial)
            # PID du process de test lui-même : toujours vivant, pour l'essai.
            verrou.write_text(f"pid={os.getpid()}\n", encoding="utf-8")

            assert watcher._worktree_en_cours_de_traitement(chemin_initial) is True
            resultat = watcher._preparer_worktree_ecriture(numero)
            assert resultat.chemin != chemin_initial, \
                "un worktree verrouillé par un traitement en cours n'aurait jamais dû être repris"
            assert resultat.worktree_repris is False
            assert resultat.chemin == watcher._chemin_worktree(numero, "-bis")
        return {"worktree_verrouille_ignore_ok": True}


FAUX_CLAUDE_725 = """#!/bin/bash
# Faux `claude` — issue #725. Consigne dans un fichier si le prompt reçu (le
# dernier argument) contient le bloc dédié « worktree REPRIS », pour
# distinguer sans ambiguïté un prompt de reprise d'un prompt normal, sans
# dépendre du contenu réel produit par un agent.
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    if echo "$prompt" | grep -q 'CE WORKTREE EST REPRIS'; then
        touch "$TEST_725_DIR/bloc_reprise_present"
    fi
    if echo "$prompt" | grep -q '3 commit(s)'; then
        touch "$TEST_725_DIR/ecart_commits_present"
    fi
    echo "✅ Tâche terminée — test #725"
fi
exit 0
"""


def scenario_bloc_prompt_reprise_conditionnel():
    """(7) Le bloc de prompt « worktree REPRIS » n'apparaît dans le prompt
    construit par `lancer_claude` QUE lorsque `worktree_repris=True` — absent
    par défaut (première exécution / tentative normale). Même technique que
    test_worktree_parallelisation_337.py : un faux `claude` sur PATH, pour
    inspecter le prompt final sans dépendre d'un vrai agent."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        test_dir = tmp_path / "etat_test"
        test_dir.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        faux_claude = bin_dir / "claude"
        faux_claude.write_text(FAUX_CLAUDE_725, encoding="utf-8")
        faux_claude.chmod(0o755)

        ancien_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{ancien_path}"
        os.environ["TEST_725_DIR"] = str(test_dir)
        ancien_cfg = watcher.CFG
        watcher.CFG = watcher.Config(
            nom="test725prompt", depot="AlainDelree/x",
            rep_travail=tmp_path, topic_ntfy="x",
        )
        try:
            watcher.lancer_claude(
                7258, "Test #725 — bloc de prompt", "corps de test", dry_run=False,
                mode=watcher.MODE_ECRITURE, timeout=30,
                cwd=tmp_path, worktree_repris=False,
            )
            assert not (test_dir / "bloc_reprise_present").exists(), \
                "le bloc de reprise n'aurait pas dû apparaître sans worktree_repris=True"

            watcher.lancer_claude(
                7258, "Test #725 — bloc de prompt", "corps de test", dry_run=False,
                mode=watcher.MODE_ECRITURE, timeout=30,
                cwd=tmp_path, chemin_worktree=tmp_path,
                worktree_repris=True, commits_ecart_worktree=3,
            )
            assert (test_dir / "bloc_reprise_present").exists(), \
                "le bloc de reprise aurait dû apparaître avec worktree_repris=True"
            assert (test_dir / "ecart_commits_present").exists(), \
                "l'écart de commits avec master aurait dû être mentionné dans le bloc de reprise"
        finally:
            watcher.CFG = ancien_cfg
            if ancien_path:
                os.environ["PATH"] = ancien_path
            else:
                os.environ.pop("PATH", None)
            os.environ.pop("TEST_725_DIR", None)
    return {"bloc_prompt_conditionnel_ok": True}


def main():
    if os.name == "nt":
        print("  (ignoré : ce test s'appuie sur bash/git POSIX, non applicable sous Windows)")
        return 0

    tests = [
        ("(1) relance avec worktree existant valide : repris, aucun -bis créé",
         scenario_relance_worktree_existant_repris),
        ("(2) première exécution : création normale (nom standard)",
         scenario_premiere_execution_creation_normale),
        ("(3) dossier présent mais non enregistré comme worktree : repli -bis",
         scenario_dossier_non_enregistre_repli_bis),
        ("(4) modification non commitée conservée lors de la reprise",
         scenario_modification_non_commitee_conservee),
        ("(5) deuxième relance : le même worktree est encore repris",
         scenario_deuxieme_relance_meme_worktree_repris),
        ("(6) plusieurs worktrees hérités : le plus récent est choisi",
         scenario_plusieurs_worktrees_herites_le_plus_recent_choisi),
        ("worktree verrouillé par un traitement en cours : jamais repris",
         scenario_worktree_verrouille_non_repris),
        ("(7) bloc de prompt de reprise : apparaît seulement si repris",
         scenario_bloc_prompt_reprise_conditionnel),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.CRITICAL)

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

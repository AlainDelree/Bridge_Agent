#!/usr/bin/env python3
"""Test de non-régression — issue #856 : l'avertissement « Succès sans
commit au-delà de la sauvegarde » (#764) et le garde-fou voisin « verdict
illisible avec commits » (#777) supposaient tous deux que le PREMIER commit
trouvé après `tete_avant_traitement` est forcément celui de sauvegarde,
repéré par POSITION. Exact pour un projet à sauvegarde standard (le watcher
fait lui-même ce commit, issue #846/#847), FAUX pour un projet à `CMD_BACKUP`
personnalisée (ex. alchess, gestionnaire de sauvegarde hors git) : le
watcher ne committe rien, et l'hypothèse prenait alors l'unique commit de
correctif de la tâche pour une sauvegarde — faux positif constaté sur 6
rapports sur 8 côté alchess (issues #255-#262).

Correction : les deux fonctions reçoivent maintenant explicitement le hash
du commit de sauvegarde watcher (`commit_sauvegarde_watcher`, déjà calculé
par `_demarrer_traitement` pour #846/#847) et excluent CE commit par son
hash EXACT — jamais plus par position. `None` (watcher n'a rien committé —
sauvegarde personnalisée ou tentative en échec) signifie qu'aucun commit
n'est à exclure : tous les commits trouvés comptent pour la tâche.

Couvre, sur des dépôts git jetables :
1. `_avertissement_succes_sans_commit` : matrice 1 commit / plusieurs
   commits / aucun commit, avec ET sans commit de sauvegarde watcher connu.
2. `_commits_au_dela_sauvegarde` : même matrice, côté #777.
3. `lancer_claude` : la ligne « Commits » du gabarit de prompt, pour un
   projet à `CMD_BACKUP` personnalisée, ne demande plus un « [hash backup] »
   qui n'existe pas (cause de l'anomalie `.audit.json` listé à tort dans
   « Fichiers modifiés » sur les rapports alchess #256/#257) — inchangée
   pour un projet à sauvegarde standard.

Exécution :  python3 -m pytest tests/test_sauvegarde_personnalisee_sans_commit_856.py
        ou : python3 tests/test_sauvegarde_personnalisee_sans_commit_856.py
"""

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

import watcher  # noqa: E402


def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _commit(rep: Path, message: str, allow_empty: bool = False) -> str:
    """Crée un commit et retourne son hash complet."""
    cmd = ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", message]
    if allow_empty:
        cmd.append("--allow-empty")
    else:
        subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(cmd, cwd=rep, check=True, capture_output=True)
    return watcher._tete_git(rep)


@pytest.fixture
def depot(tmp_path):
    rep = tmp_path / "projet"
    rep.mkdir()
    _init_depot_git(rep)
    return rep


# ─── 1. _avertissement_succes_sans_commit ──────────────────────────────────

def test_standard_un_seul_commit_backup_connu_signale(depot):
    """Sauvegarde standard (hash connu) : un seul commit, c'est la
    sauvegarde elle-même → rien d'autre pour la tâche → signalé."""
    tete = watcher._tete_git(depot)
    backup = _commit(depot, "avant-tache", allow_empty=True)

    avertissement = watcher._avertissement_succes_sans_commit(
        8560, watcher.MODE_ECRITURE, False, depot, tete, backup)
    assert avertissement != ""
    assert "aucun commit" in avertissement.lower()


def test_standard_backup_plus_fix_pas_signale(depot):
    """Sauvegarde standard : backup + un commit de fix → pas de signalement."""
    tete = watcher._tete_git(depot)
    backup = _commit(depot, "avant-tache", allow_empty=True)
    (depot / "fichier.txt").write_text("modifie\n", encoding="utf-8")
    _commit(depot, "fix-tache")

    avertissement = watcher._avertissement_succes_sans_commit(
        8561, watcher.MODE_ECRITURE, False, depot, tete, backup)
    assert avertissement == ""


def test_personnalisee_aucun_commit_signale(depot):
    """Sauvegarde personnalisée (pas de hash watcher, commit_sauvegarde_
    watcher=None) : la tâche n'a RIEN committé → signalement légitime
    (équivalent de l'issue #257 côté alchess : agent ayant conclu qu'il n'y
    avait rien à modifier)."""
    tete = watcher._tete_git(depot)

    avertissement = watcher._avertissement_succes_sans_commit(
        8562, watcher.MODE_ECRITURE, False, depot, tete, None)
    assert avertissement != ""
    assert "aucun commit" in avertissement.lower()


def test_personnalisee_un_seul_commit_fix_pas_signale(depot):
    """LE FAUX POSITIF DE L'ISSUE #856 : sauvegarde personnalisée, un seul
    commit — mais c'est le correctif de la tâche, pas une sauvegarde
    (puisqu'il n'y en a pas) → NE DOIT PLUS être signalé (avant #856,
    l'ancien code par position le prenait pour la sauvegarde et signalait
    à tort — 6 rapports sur 8 côté alchess, issues #255-#262)."""
    tete = watcher._tete_git(depot)
    (depot / "fichier.txt").write_text("modifie\n", encoding="utf-8")
    _commit(depot, "fix-tache-alchess")

    avertissement = watcher._avertissement_succes_sans_commit(
        8563, watcher.MODE_ECRITURE, False, depot, tete, None)
    assert avertissement == "", (
        "un unique commit de correctif sur un projet à sauvegarde "
        "personnalisée ne doit plus être pris pour une sauvegarde absente "
        "de travail (issue #856)")


def test_personnalisee_fix_et_changelog_pas_signale(depot):
    """Sauvegarde personnalisée, deux commits de tâche (fix + changelog,
    comme l'issue #256 côté alchess, seul rapport sans avertissement avant
    #856 — mais pour la mauvaise raison) → toujours pas de signalement."""
    tete = watcher._tete_git(depot)
    (depot / "fichier.txt").write_text("modifie\n", encoding="utf-8")
    _commit(depot, "fix-tache")
    (depot / "CHANGELOG.md").write_text("entree\n", encoding="utf-8")
    _commit(depot, "changelog")

    avertissement = watcher._avertissement_succes_sans_commit(
        8564, watcher.MODE_ECRITURE, False, depot, tete, None)
    assert avertissement == ""


# ─── 2. _commits_au_dela_sauvegarde (#777, même défaut) ────────────────────

def test_commits_au_dela_standard_exclut_le_backup_par_hash(depot):
    tete = watcher._tete_git(depot)
    backup = _commit(depot, "avant-tache", allow_empty=True)
    (depot / "fichier.txt").write_text("modifie\n", encoding="utf-8")
    _commit(depot, "fix-tache")

    commits = watcher._commits_au_dela_sauvegarde(depot, tete, backup)
    assert len(commits) == 1
    assert "fix-tache" in commits[0]


def test_commits_au_dela_personnalisee_pas_d_exclusion_par_position(depot):
    """Même défaut que #764 dans cette fonction voisine : sauvegarde
    personnalisée, un seul commit de correctif → ne doit plus être écarté
    comme s'il était la sauvegarde (issue #856)."""
    tete = watcher._tete_git(depot)
    (depot / "fichier.txt").write_text("modifie\n", encoding="utf-8")
    _commit(depot, "fix-tache-alchess")

    commits = watcher._commits_au_dela_sauvegarde(depot, tete, None)
    assert len(commits) == 1, (
        f"le commit de correctif unique d'un projet à sauvegarde "
        f"personnalisée ne doit plus être écarté par position : {commits}")
    assert "fix-tache-alchess" in commits[0]


def test_commits_au_dela_personnalisee_aucun_commit(depot):
    tete = watcher._tete_git(depot)
    assert watcher._commits_au_dela_sauvegarde(depot, tete, None) == []


# ─── 3. Gabarit de prompt (ligne « Commits ») ──────────────────────────────

FAUX_CLAUDE_CAPTURE = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    echo "$prompt" > "$TEST_856_PROMPT_FILE"
fi
echo "<!-- bridge:verdict:succes -->"
echo "Tache terminee (test #856)."
exit 0
"""


def _config_isolee(rep_travail: Path, nom: str, cmd_backup: str = "") -> watcher.Config:
    return watcher.Config(
        nom=nom, depot="AlainDelree/x",
        rep_travail=rep_travail, topic_ntfy=nom, cmd_backup=cmd_backup,
    )


def test_gabarit_commits_personnalise_sans_placeholder_backup(depot, tmp_path, monkeypatch):
    """Projet à `CMD_BACKUP` personnalisée (ex. alchess) : la ligne
    « Commits » du prompt ne doit plus demander un « [hash backup] » qui
    n'existe pas — seulement « [hash fix] », et une mention explicite de ne
    citer que les commits réels de la tâche."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_CAPTURE, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{__import__('os').pathsep}{__import__('os').environ.get('PATH', '')}")
    fichier_prompt = tmp_path / "prompt.txt"
    monkeypatch.setenv("TEST_856_PROMPT_FILE", str(fichier_prompt))

    ancien_cfg = watcher.CFG
    watcher.CFG = _config_isolee(depot, "test856a", cmd_backup="python3 outils/sauvegarder.py")
    try:
        watcher.lancer_claude(8565, "Titre", "corps", dry_run=False, mode=watcher.MODE_ECRITURE,
                               timeout=30, cwd=depot, commit_sauvegarde_watcher=None)
    finally:
        watcher.CFG = ancien_cfg

    prompt = fichier_prompt.read_text(encoding="utf-8")
    # Isole la ligne « Commits » du GABARIT de rapport final (section « Réponds
    # avec ce format exact » en fin de prompt) — distincte de la consigne de
    # sauvegarde plus haut, qui explique elle-même le cas standard en citant
    # "[hash backup]" littéralement (consignes/globales.md, inchangé).
    ligne_gabarit = next(l for l in prompt.splitlines() if l.startswith("Commits (dans"))
    assert "[hash backup]" not in ligne_gabarit, (
        "un projet à sauvegarde personnalisée ne doit plus se voir demander "
        f"un hash de sauvegarde inexistant (issue #856) : {ligne_gabarit!r}")
    assert "[hash fix]" in ligne_gabarit
    assert "sauvegarde personnalisée" in ligne_gabarit


def test_gabarit_commits_standard_inchange(depot, tmp_path, monkeypatch):
    """Contrôle : un projet à sauvegarde standard (CMD_BACKUP vide) garde la
    forme « [hash backup] (backup) + [hash fix] (fix) » inchangée."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_CAPTURE, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{__import__('os').pathsep}{__import__('os').environ.get('PATH', '')}")
    fichier_prompt = tmp_path / "prompt.txt"
    monkeypatch.setenv("TEST_856_PROMPT_FILE", str(fichier_prompt))

    ancien_cfg = watcher.CFG
    watcher.CFG = _config_isolee(depot, "test856b")
    try:
        watcher.lancer_claude(8566, "Titre", "corps", dry_run=False, mode=watcher.MODE_ECRITURE,
                               timeout=30, cwd=depot, commit_sauvegarde_watcher="abc123def456")
    finally:
        watcher.CFG = ancien_cfg

    prompt = fichier_prompt.read_text(encoding="utf-8")
    # Gabarit de la ligne « Commits » du rapport final : inchangé, toujours
    # les deux placeholders backup+fix pour un projet à sauvegarde standard.
    assert "Commits (dans" in prompt
    assert "[hash backup] (backup) + [hash fix] (fix)" in prompt
    # La consigne de sauvegarde (plus haut dans le prompt, distincte de la
    # ligne « Commits » du gabarit de rapport) cite bien le vrai hash connu.
    assert "abc123def456"[:12] in prompt


def main() -> int:
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

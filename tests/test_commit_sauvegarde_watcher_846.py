#!/usr/bin/env python3
"""Test de non-régression — issue #846 : le watcher fait lui-même le commit
de sauvegarde avant de lancer l'agent en mode écriture, plutôt que de s'en
remettre à une consigne de prompt que l'agent oubliait régulièrement
(incident Relecture_Bridge #121 : l'agent avait déjà modifié des fichiers
avant de faire ce commit, qui a alors englouti son propre travail).

Couvre, sur des dépôts git jetables (`tempfile.TemporaryDirectory`), les cas
demandés par l'issue :
1. Sauvegarde faite avant le lancement sur un worktree neuf : commit VIDE,
   toujours le premier après `tete_avant_traitement`.
2. Des fichiers non suivis présents : ils sont capturés par le commit, et
   remontés comme « nouveaux suivis » (garde-fou backup/reset).
3. Tentative 2/3 d'un même traitement : `_demarrer_traitement` n'étant
   appelée qu'une fois par traitement, aucun second commit de sauvegarde
   n'apparaît entre les tentatives.
4. RELANCE sur un worktree déjà repris (travail déjà commité) : le commit
   de sauvegarde watcher reste le PREMIER après `tete_avant_traitement` —
   il ne fusionne jamais avec le travail déjà présent.
5. Projet définissant une commande de sauvegarde PERSONNALISÉE dans
   `CMD_BACKUP` (ex. alchess, cas non reconnu par `_cmd_backup_est_standard`
   — issue #847) : comportement conservé à l'identique, le watcher ne
   committe rien lui-même. Le cas où `CMD_BACKUP` est vide OU reconnu comme
   la commande standard de `nouveau_projet.py` est couvert séparément par
   `tests/test_cmd_backup_standard_847.py`.
6. Échec du commit de sauvegarde (ex. verrou git) : repli sur `None`,
   signalé en log, sans lever ni bloquer le traitement.
7. `_finaliser_succes` : le hash du commit de sauvegarde watcher figure
   bien dans le rapport de clôture (substitution du placeholder
   `[hash backup]` si l'agent ne l'a pas fait lui-même).

Exécution :  python3 -m pytest tests/test_commit_sauvegarde_watcher_846.py
        ou : python3 tests/test_commit_sauvegarde_watcher_846.py
"""

import logging
import os
import subprocess
import sys
import tempfile
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


def _ajouter_commit(rep: Path, nom_fichier: str, message: str) -> None:
    (rep / nom_fichier).write_text("contenu\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", message], cwd=rep, check=True, capture_output=True)


def _rev_list(rep: Path, depuis: str) -> list[str]:
    res = subprocess.run(["git", "rev-list", "--reverse", f"{depuis}..HEAD"],
                          cwd=rep, capture_output=True, text=True, check=True)
    return [l for l in res.stdout.splitlines() if l.strip()]


def _config_isolee(rep_travail: Path, nom: str, cmd_backup: str = "") -> watcher.Config:
    return watcher.Config(
        nom=nom, depot="AlainDelree/x",
        rep_travail=rep_travail, topic_ntfy=nom, cmd_backup=cmd_backup,
    )


@pytest.fixture(autouse=True)
def _bouchons_reseau(monkeypatch):
    """Bouchons réseau GitHub, comme les autres tests bout-en-bout de
    watcher.py (ex. test_contexte_decision_historique_845.py) — aucun appel
    réel, `_demarrer_traitement` poste quand même une ACK."""
    monkeypatch.setattr(watcher, "commenter_issue", lambda numero, message: True)
    monkeypatch.setattr(watcher, "notifier_debut_sse", lambda numero: None)
    monkeypatch.setattr(watcher, "notifier_fin_sse", lambda numero: None)
    monkeypatch.setattr(watcher, "_lister_commentaires", lambda numero: [])
    monkeypatch.setattr(watcher, "verifier_preflight_token", lambda cwd=None: None)
    monkeypatch.setattr(watcher, "notifier", lambda *a, **k: None)


@pytest.fixture
def depot(tmp_path):
    rep = tmp_path / "projet"
    rep.mkdir()
    _init_depot_git(rep)
    return rep


def _demarrer(cfg: watcher.Config, numero: int, titre: str = "Titre de test", body: str = ""):
    ancien_cfg = watcher.CFG
    watcher.CFG = cfg
    try:
        return watcher._demarrer_traitement(
            numero, titre, body, watcher.MODE_ECRITURE, "ÉCRITURE",
            dry_run=False, cwd_effectif=cfg.rep_travail)
    finally:
        watcher.CFG = ancien_cfg


# ─── 1. Worktree neuf : commit de sauvegarde VIDE, toujours le premier ──────

def test_commit_vide_worktree_neuf(depot):
    cfg = _config_isolee(depot, "test846a")
    (_est_relance, _debut, _nb, _empreinte, tete_avant,
     _timeout_sugg, _estim, commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8461)

    assert tete_avant is not None
    assert commit_sauvegarde is not None
    assert nouveaux_suivis == ()

    commits = _rev_list(depot, tete_avant)
    assert len(commits) == 1, f"le commit de sauvegarde doit être le SEUL et PREMIER commit : {commits}"
    assert commits[0] == commit_sauvegarde

    diff = subprocess.run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sauvegarde],
                          cwd=depot, capture_output=True, text=True, check=True)
    assert diff.stdout.strip() == "", "le commit de sauvegarde sur un worktree neuf doit être VIDE"

    message = subprocess.run(["git", "log", "-1", "--format=%s", commit_sauvegarde],
                              cwd=depot, capture_output=True, text=True, check=True).stdout.strip()
    assert message.startswith("avant-"), f"convention de message « avant-… » attendue : {message}"


# ─── 2. Fichiers non suivis présents : capturés + remontés (garde-fou) ──────

def test_fichiers_non_suivis_remontes(depot):
    (depot / "nouveau_dossier").mkdir()
    (depot / "nouveau_dossier" / "fichier.txt").write_text("contenu\n", encoding="utf-8")

    cfg = _config_isolee(depot, "test846b")
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8462)

    assert commit_sauvegarde is not None
    assert nouveaux_suivis == ("nouveau_dossier/",), nouveaux_suivis

    suivis = subprocess.run(["git", "ls-files", "nouveau_dossier/"],
                             cwd=depot, capture_output=True, text=True, check=True).stdout
    assert "nouveau_dossier/fichier.txt" in suivis, "le commit aurait dû mettre ce dossier sous suivi"

    commits = _rev_list(depot, tete_avant)
    assert len(commits) == 1


# ─── 3. Tentative 2/3 d'un même traitement : aucun second commit ────────────

FAUX_CLAUDE_ECHEC = """#!/bin/bash
echo "<!-- bridge:verdict:echec -->"
echo "Echec simule (test #846) — aucune ecriture dans le depot."
exit 0
"""


def test_tentative_2_pas_de_nouveau_backup(depot, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_ECHEC, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    cfg = _config_isolee(depot, "test846c")
    (_er, _d, _n, empreinte, tete_avant, _ts, _es,
     commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8463)
    assert commit_sauvegarde is not None

    ancien_cfg = watcher.CFG
    watcher.CFG = cfg
    try:
        for tentative in (1, 2):
            succes, sortie, _stderr, _duree, _verdict_absent = watcher._executer_une_tentative(
                8463, "Titre de test", "", dry_run=False, mode=watcher.MODE_ECRITURE,
                timeout=30, modele="", perimetre_effectif="", cwd_effectif=depot,
                verrou=None, chemin_scratch=None, chemin_worktree=None,
                empreinte_configs_avant=empreinte, tentative=tentative,
                tete_avant_traitement=tete_avant,
                commit_sauvegarde_watcher=commit_sauvegarde,
                backup_watcher_nouveaux_suivis=nouveaux_suivis)
            assert succes is False  # verdict d'échec simulé
    finally:
        watcher.CFG = ancien_cfg

    commits = _rev_list(depot, tete_avant)
    assert len(commits) == 1, (
        f"deux tentatives sur le même traitement ne doivent laisser qu'UN SEUL "
        f"commit de sauvegarde, pas un par tentative : {commits}")


# ─── 4. RELANCE sur un worktree repris (travail déjà commité) ──────────────

def test_relance_backup_separe_travail_precedent(depot):
    _ajouter_commit(depot, "travail_precedent.txt", "travail de la tentative précédente")
    tete_avant_relance = watcher._tete_git(depot)

    cfg = _config_isolee(depot, "test846d")
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, _nouveaux_suivis) = _demarrer(cfg, 8464)

    assert tete_avant == tete_avant_relance, (
        "tete_avant_traitement doit être relevé APRÈS le travail déjà présent "
        "dans le worktree repris (RELANCE), jamais avant")
    assert commit_sauvegarde is not None

    commits = _rev_list(depot, tete_avant)
    assert len(commits) == 1, (
        f"le commit de sauvegarde ne doit JAMAIS fusionner avec le travail "
        f"déjà commité d'une relance précédente : {commits}")
    # Le travail de la tentative précédente reste, lui, ANTÉRIEUR à cette
    # référence — jamais réécrit ni absorbé par le commit de sauvegarde.
    assert (depot / "travail_precedent.txt").exists()


# ─── 5. Projet avec CMD_BACKUP personnalisée (alchess) : comportement conservé

def test_cmd_backup_defini_watcher_ne_committe_pas(depot):
    tete_avant_appel = watcher._tete_git(depot)
    cfg = _config_isolee(depot, "test846e", cmd_backup="python3 outils/sauvegarder.py")
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8465)

    assert commit_sauvegarde is None, "CMD_BACKUP personnalisée : le watcher ne doit rien committer lui-même"
    assert nouveaux_suivis == ()
    assert tete_avant == tete_avant_appel
    assert watcher._tete_git(depot) == tete_avant_appel, "aucun commit ne doit avoir été ajouté"


FAUX_CLAUDE_CAPTURE = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    echo "$prompt" > "$TEST_846_PROMPT_FILE"
fi
echo "<!-- bridge:verdict:succes -->"
echo "Tache terminee (test #846)."
exit 0
"""


def test_cmd_backup_defini_consigne_inchangee_dans_le_prompt(depot, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_CAPTURE, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    fichier_prompt = tmp_path / "prompt.txt"
    monkeypatch.setenv("TEST_846_PROMPT_FILE", str(fichier_prompt))

    cmd_backup = "python3 outils/sauvegarder.py"
    ancien_cfg = watcher.CFG
    watcher.CFG = _config_isolee(depot, "test846f", cmd_backup=cmd_backup)
    try:
        watcher.lancer_claude(8466, "Titre", "corps", dry_run=False, mode=watcher.MODE_ECRITURE,
                               timeout=30, cwd=depot, commit_sauvegarde_watcher=None)
    finally:
        watcher.CFG = ancien_cfg

    prompt = fichier_prompt.read_text(encoding="utf-8")
    assert cmd_backup in prompt
    assert "déjà été fait par le watcher" not in prompt


# ─── 6. Échec du commit de sauvegarde : repli sur None, signalé en log ─────

def test_echec_commit_watcher_repli_sur_none(depot, caplog):
    # Force l'échec de 'git add -A' : un index.lock déjà présent fait échouer
    # toute commande git qui touche l'index, de façon déterministe et
    # portable (pas de dépendance aux permissions du système de fichiers).
    verrou_git = depot / ".git" / "index.lock"
    verrou_git.write_text("", encoding="utf-8")
    try:
        tete_avant_appel = watcher._tete_git(depot)
        cfg = _config_isolee(depot, "test846g")
        with caplog.at_level(logging.WARNING, logger=watcher.log.name):
            (_er, _d, _n, _e, tete_avant, _ts, _es,
             commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8467)
    finally:
        verrou_git.unlink(missing_ok=True)

    assert commit_sauvegarde is None, "le commit de sauvegarde doit échouer avec l'index verrouillé"
    assert nouveaux_suivis == ()
    assert tete_avant == tete_avant_appel
    assert any("846" in m for m in caplog.messages), (
        "l'échec du commit de sauvegarde watcher doit être journalisé (issue #846, point 3)")
    # Le traitement n'est jamais bloqué : tete_avant_traitement reste résolu.
    assert tete_avant is not None


def test_echec_commit_watcher_repli_consigne_prompt_historique(depot, tmp_path, monkeypatch):
    """Repli (point 3) : quand le watcher n'a pas pu faire la sauvegarde
    lui-même (commit_sauvegarde_watcher=None transmis par l'appelant), le
    prompt retombe sur la consigne historique demandant à l'agent de le
    faire — texte inchangé caractère pour caractère."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_CAPTURE, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    fichier_prompt = tmp_path / "prompt.txt"
    monkeypatch.setenv("TEST_846_PROMPT_FILE", str(fichier_prompt))

    ancien_cfg = watcher.CFG
    watcher.CFG = _config_isolee(depot, "test846h")
    try:
        watcher.lancer_claude(8468, "Titre", "corps", dry_run=False, mode=watcher.MODE_ECRITURE,
                               timeout=30, cwd=depot, commit_sauvegarde_watcher=None)
    finally:
        watcher.CFG = ancien_cfg

    prompt = fichier_prompt.read_text(encoding="utf-8")
    assert ("Fais TOUJOURS une sauvegarde de l'état courant avant toute modification "
            "(par exemple un commit git de tout le dossier), afin de permettre un retour arrière.") in prompt
    assert "déjà été fait par le watcher" not in prompt


# ─── 7. _finaliser_succes : le hash figure dans le rapport de clôture ──────

def test_finaliser_succes_remplace_placeholder_hash_backup(depot, monkeypatch):
    monkeypatch.setattr(watcher, "FICHIER_HISTORIQUE", depot.parent / "historique_durees.json")
    monkeypatch.setattr(watcher, "commenter_resultat_avec_retry", lambda numero, message: True)
    monkeypatch.setattr(watcher, "fermer_issue", lambda numero: True)
    monkeypatch.setattr(watcher, "editer_dernier_commentaire", lambda numero, message: True)

    captures = {}

    def _capturer_commentaire(numero, message):
        captures["message"] = message
        return True

    monkeypatch.setattr(watcher, "commenter_resultat_avec_retry", _capturer_commentaire)

    cfg = _config_isolee(depot, "test846i")
    ancien_cfg = watcher.CFG
    watcher.CFG = cfg
    try:
        sortie = (
            "<!-- bridge:verdict:succes -->\n"
            "✅ Tâche terminée — exemple\n"
            f"Commits (dans {depot}) : [hash backup] (backup) + abc1234 (fix)\n"
            "py_compile : OK\n"
        )
        watcher._finaliser_succes(
            8469, "Titre", "", labels=[], mode=watcher.MODE_ECRITURE, timeout=300,
            avertissement_conflit="", avertissement_worktree_deja_pris="",
            avertissement_worktree_repris="", sortie=sortie,
            debut_traitement=0.0, nb_projets_actifs_debut=1, est_relance=False,
            dry_run=False, cwd_effectif=depot, tete_avant_traitement=watcher._tete_git(depot),
            tentative=1, timeout_suggere_lancement=None, estimation_lancement={},
            commit_sauvegarde_watcher="0123456789abcdef",
        )
    finally:
        watcher.CFG = ancien_cfg

    message = captures["message"]
    assert "[hash backup]" not in message
    assert "0123456789ab" in message, message


def main() -> int:
    """Même convention que test_contexte_decision_historique_845.py : exécution
    directe via pytest lui-même (fixtures tmp_path/monkeypatch/caplog)."""
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

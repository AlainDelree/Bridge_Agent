#!/usr/bin/env python3
"""Test de non-régression — issue #901 : mode interactif, étape 2.

Suite de l'étape 1 (#900, marqueur `mode_interactif` posé mais sans effet sur
le lancement). Cette étape lance réellement CCL dans une session tmux
détachée pour une issue `mode_interactif` effective, et la surveille de
façon NON BLOQUANTE au lieu du `claude --print` + `proc.communicate(timeout=
...)` bloquant du chemin automatique (`lancer_claude`), lui-même strictement
inchangé — voir le paramètre `mode_tmux` (False partout sauf dans la
nouvelle branche).

Couvre :
1. `_nom_session_tmux` — nom conventionnel et stable, assaini.
2. `_construire_cmd_claude_interactif` — même construction que
   `_construire_cmd_claude`, sans `--print`.
3. `_ecrire_script_lancement_tmux` — script shell produit (export env,
   cd, exec), prompt correctement échappé même avec espaces/guillemets.
4. `_lancer_session_tmux` — construction de la commande tmux (avec et sans
   le repli `systemd-run --scope`), repli direct si `systemd-run` échoue,
   échec propre si tmux est absent ou si `tmux new-session` échoue.
5. `_surveiller_session_tmux` — surveillance non bloquante avec une session
   simulée (fin normale) et expiration (TIMEOUT dépassé, session encore
   ouverte).
6. `lancer_claude(..., mode_tmux=True)` — garde-fous OS/agent, délégation à
   `_lancer_session_tmux` avec le même `prompt` que le chemin automatique.
7. `_traiter_issue_interactive` — lancement, reprise d'une session déjà
   existante au redémarrage du watcher (point 5), repli automatique si tmux
   est indisponible (point 6), et fin de session SANS rapport / TIMEOUT.
   Depuis l'issue #903 (étape 3, voir tests/test_mode_interactif_rapport_
   903.py), une fin de session sans rapport ferme désormais l'issue SANS le
   label `done` (plus de clôture manuelle) et un TIMEOUT pose `needs-human`.

Exécution :  python3 -m pytest tests/test_mode_interactif_tmux_901.py
        ou : python3 tests/test_mode_interactif_tmux_901.py
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

import watcher  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """CFG minimal et isolé, restauré après le test — même patron que
    tests/test_mode_interactif_900.py. `DOSSIER_RAPPORTS_INTERACTIFS` isolé
    comme `DOSSIER_TMUX` (issue #903) : aucun de ces tests n'écrit de
    rapport, mais l'isolation évite toute collision avec un vrai
    logs/interactif/ sur la machine qui exécute les tests."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t901", depot="AlainDelree/x", rep_travail=tmp_path)
    monkeypatch.setattr(watcher, "DOSSIER_TMUX", tmp_path / "tmux")
    monkeypatch.setattr(watcher, "DOSSIER_RAPPORTS_INTERACTIFS", tmp_path / "interactif")
    yield watcher.CFG
    watcher.CFG = ancien_cfg


# ─── 1. Nom de session tmux ────────────────────────────────────────────────

def test_nom_session_tmux_format():
    assert watcher._nom_session_tmux("bridge_agent", 42) == "bridge-bridge_agent-issue42"


def test_nom_session_tmux_assainit_caracteres_speciaux():
    assert watcher._nom_session_tmux("mon:projet perso", 7) == "bridge-mon_projet_perso-issue7"


# ─── 2. Construction de la commande claude interactive (sans --print) ─────

def test_construire_cmd_claude_interactif_ecriture():
    cmd = watcher._construire_cmd_claude_interactif(watcher.MODE_ECRITURE, "opus", "mon prompt")
    assert "--print" not in cmd
    assert cmd == ["claude", "--model", "opus", "--dangerously-skip-permissions", "mon prompt"]


def test_construire_cmd_claude_interactif_sans_modele():
    cmd = watcher._construire_cmd_claude_interactif(watcher.MODE_LECTURE_ACTIVE, "", "prompt")
    assert cmd == ["claude", "--dangerously-skip-permissions", "prompt"]


def test_construire_cmd_claude_interactif_lecture_sans_skip_permissions():
    """Jamais atteint en pratique (est_interactif écarte la lecture seule),
    mais défensif : reste un vrai sous-ensemble de _construire_cmd_claude."""
    cmd = watcher._construire_cmd_claude_interactif(watcher.MODE_LECTURE, "", "prompt")
    assert "--dangerously-skip-permissions" not in cmd


# ─── 3. Script de lancement (env + cd + exec, prompt échappé) ─────────────

def test_ecrire_script_lancement_tmux(cfg, tmp_path):
    cmd = ["claude", "--model", "opus", "--dangerously-skip-permissions",
           "un prompt avec espaces et des \"guillemets\""]
    chemin = watcher._ecrire_script_lancement_tmux(
        "bridge-t901-issue1", cmd, tmp_path / "projet",
        {"BRIDGE_PROJET": "t901", "BRIDGE_ISSUE": "1"},
    )
    assert chemin.exists()
    contenu = chemin.read_text(encoding="utf-8")
    assert contenu.startswith("#!/bin/sh\n")
    assert "export BRIDGE_PROJET=t901" in contenu
    assert "export BRIDGE_ISSUE=1" in contenu
    assert f"cd {tmp_path / 'projet'}" in contenu or str(tmp_path / "projet") in contenu
    assert "exec claude --model opus --dangerously-skip-permissions" in contenu
    # Le prompt complet doit être présent, correctement protégé par
    # shlex.quote (pas tronqué, pas de guillemets non échappés qui casseraient
    # le shell).
    import shlex
    derniere_ligne = contenu.strip().splitlines()[-1]
    mots = shlex.split(derniere_ligne[len("exec "):])
    assert mots[-1] == "un prompt avec espaces et des \"guillemets\""


# ─── 4. _lancer_session_tmux : construction de la commande tmux ──────────

def test_lancer_session_tmux_hors_groupe_systemd_run(cfg, tmp_path, monkeypatch):
    appels = []

    def faux_which(nom):
        return f"/usr/bin/{nom}" if nom in ("tmux", "systemd-run") else None

    class FauxResultat:
        returncode = 0
        stderr = ""

    def faux_run(argv, **kwargs):
        appels.append(argv)
        return FauxResultat()

    monkeypatch.setattr(watcher.shutil, "which", faux_which)
    monkeypatch.setattr(watcher.subprocess, "run", faux_run)

    succes, info = watcher._lancer_session_tmux(
        "bridge-t901-issue1", ["claude", "prompt"], tmp_path, {"BRIDGE_ISSUE": "1"})

    assert succes is True
    assert info == "hors_groupe"
    assert len(appels) == 1
    argv = appels[0]
    assert argv[:4] == ["systemd-run", "--user", "--scope", "--collect"]
    assert argv[4] == "--unit=bridge-tmux-bridge-t901-issue1"
    assert argv[5] == "--"
    reste = argv[6:]
    assert reste[:6] == ["tmux", "new-session", "-d", "-s", "bridge-t901-issue1", "-c"]
    assert reste[6] == str(tmp_path)
    assert reste[7].endswith("bridge-t901-issue1.sh")


def test_lancer_session_tmux_sans_systemd_run(cfg, tmp_path, monkeypatch):
    appels = []

    def faux_which(nom):
        return "/usr/bin/tmux" if nom == "tmux" else None

    class FauxResultat:
        returncode = 0
        stderr = ""

    def faux_run(argv, **kwargs):
        appels.append(argv)
        return FauxResultat()

    monkeypatch.setattr(watcher.shutil, "which", faux_which)
    monkeypatch.setattr(watcher.subprocess, "run", faux_run)

    succes, info = watcher._lancer_session_tmux(
        "bridge-t901-issue2", ["claude", "prompt"], tmp_path, {})

    assert succes is True
    assert info == "meme_groupe"
    assert len(appels) == 1
    assert appels[0][0] == "tmux"


def test_lancer_session_tmux_repli_si_systemd_run_echoue(cfg, tmp_path, monkeypatch):
    appels = []

    def faux_which(nom):
        return f"/usr/bin/{nom}" if nom in ("tmux", "systemd-run") else None

    class FauxEchec:
        returncode = 1
        stderr = "Failed to connect to bus"

    class FauxSucces:
        returncode = 0
        stderr = ""

    def faux_run(argv, **kwargs):
        appels.append(argv)
        return FauxEchec() if argv[0] == "systemd-run" else FauxSucces()

    monkeypatch.setattr(watcher.shutil, "which", faux_which)
    monkeypatch.setattr(watcher.subprocess, "run", faux_run)

    succes, info = watcher._lancer_session_tmux(
        "bridge-t901-issue3", ["claude", "prompt"], tmp_path, {})

    assert succes is True
    assert info == "meme_groupe", "le repli direct doit être reconnu comme 'meme_groupe'"
    assert len(appels) == 2, "systemd-run tenté d'abord, puis repli direct tmux"
    assert appels[0][0] == "systemd-run"
    assert appels[1][0] == "tmux"


def test_lancer_session_tmux_absent(cfg, tmp_path, monkeypatch):
    monkeypatch.setattr(watcher.shutil, "which", lambda nom: None)

    def jamais_appele(*a, **k):
        raise AssertionError("subprocess.run ne doit pas être appelé si tmux est absent")

    monkeypatch.setattr(watcher.subprocess, "run", jamais_appele)

    succes, message = watcher._lancer_session_tmux(
        "bridge-t901-issue4", ["claude", "prompt"], tmp_path, {})
    assert succes is False
    assert "tmux" in message.lower()


def test_lancer_session_tmux_new_session_echoue(cfg, tmp_path, monkeypatch):
    def faux_which(nom):
        return "/usr/bin/tmux" if nom == "tmux" else None

    class FauxEchec:
        returncode = 1
        stderr = "duplicate session"

    monkeypatch.setattr(watcher.shutil, "which", faux_which)
    monkeypatch.setattr(watcher.subprocess, "run", lambda *a, **k: FauxEchec())

    succes, message = watcher._lancer_session_tmux(
        "bridge-t901-issue5", ["claude", "prompt"], tmp_path, {})
    assert succes is False
    assert "échoué" in message


# ─── 5. Surveillance non bloquante : session simulée + expiration ────────

def test_surveiller_session_tmux_fin_normale(monkeypatch, tmp_path):
    """Fin de session SANS rapport (issue #903 : "rapport" a désormais la
    priorité — voir tests/test_mode_interactif_rapport_903.py — mais une
    session qui disparaît sans qu'aucun fichier n'apparaisse reste
    "terminee", comportement #901 inchangé)."""
    horloge = {"t": 0.0}

    def faux_monotonic():
        horloge["t"] += 1.0
        return horloge["t"]

    existe_sequence = iter([True, True, False])
    monkeypatch.setattr(watcher.time, "monotonic", faux_monotonic)
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: next(existe_sequence))

    resultat = watcher._surveiller_session_tmux(
        "bridge-t901-issue6", echeance=1000.0, chemin_rapport=tmp_path / "aucun_rapport.md")
    assert resultat == "terminee"


def test_surveiller_session_tmux_timeout(monkeypatch, tmp_path):
    horloge = {"t": 0.0}

    def faux_monotonic():
        horloge["t"] += 1.0
        return horloge["t"]

    monkeypatch.setattr(watcher.time, "monotonic", faux_monotonic)
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)

    resultat = watcher._surveiller_session_tmux(
        "bridge-t901-issue7", echeance=3.0, chemin_rapport=tmp_path / "aucun_rapport.md")
    assert resultat == "timeout"


def test_tmux_session_existe_sur_erreur_subprocess(monkeypatch):
    def leve(*a, **k):
        raise FileNotFoundError("tmux introuvable")
    monkeypatch.setattr(watcher.subprocess, "run", leve)
    assert watcher._tmux_session_existe("bridge-x-issue1") is False


# ─── 6. lancer_claude(..., mode_tmux=True) : garde-fous + délégation ──────

def test_lancer_claude_mode_tmux_windows_non_supporte(cfg, monkeypatch):
    monkeypatch.setattr(watcher.os, "name", "nt")
    succes, message = watcher.lancer_claude(
        1, "Titre", "body", dry_run=False, mode=watcher.MODE_ECRITURE,
        timeout=60, mode_tmux=True)
    assert succes is False
    assert "Windows" in message


def test_lancer_claude_mode_tmux_agent_non_claude(cfg, monkeypatch):
    watcher.CFG = watcher.Config(nom="t901b", depot="x/y", rep_travail=Path("/tmp"), agent="vibe")
    succes, message = watcher.lancer_claude(
        1, "Titre", "body", dry_run=False, mode=watcher.MODE_ECRITURE,
        timeout=60, mode_tmux=True)
    assert succes is False
    assert "vibe" in message


def test_lancer_claude_mode_tmux_delegue_a_lancer_session_tmux(cfg, monkeypatch, tmp_path):
    captures = {}

    def faux_lancer_session_tmux(nom_session, cmd, cwd, env_extra):
        captures["nom_session"] = nom_session
        captures["cmd"] = cmd
        captures["cwd"] = cwd
        captures["env_extra"] = env_extra
        return True, "hors_groupe"

    monkeypatch.setattr(watcher, "_lancer_session_tmux", faux_lancer_session_tmux)
    succes, info = watcher.lancer_claude(
        123, "Un titre", "Un corps de tâche", dry_run=False, mode=watcher.MODE_ECRITURE,
        timeout=60, modele="opus", cwd=tmp_path, mode_tmux=True)

    assert succes is True
    assert info == "hors_groupe"
    assert captures["nom_session"] == "bridge-t901-issue123"
    assert captures["cwd"] == tmp_path
    assert captures["env_extra"] == {"BRIDGE_PROJET": "t901", "BRIDGE_ISSUE": "123"}
    assert "--print" not in captures["cmd"]
    assert "--dangerously-skip-permissions" in captures["cmd"]
    # Le prompt (dernier élément) doit contenir le corps de l'issue — même
    # gabarit de prompt que le chemin automatique (étude #888/#901).
    assert "Un corps de tâche" in captures["cmd"][-1]


def test_lancer_claude_mode_tmux_dry_run_ne_lance_rien(cfg, monkeypatch):
    def jamais_appele(*a, **k):
        raise AssertionError("_lancer_session_tmux ne doit pas être appelé en dry-run")
    monkeypatch.setattr(watcher, "_lancer_session_tmux", jamais_appele)

    succes, sortie = watcher.lancer_claude(
        1, "Titre", "body", dry_run=True, mode=watcher.MODE_ECRITURE,
        timeout=60, mode_tmux=True)
    assert succes is True
    assert "DRY-RUN" in sortie


# ─── 7. _traiter_issue_interactive : orchestration complète ──────────────

@pytest.fixture
def commentaires(monkeypatch):
    messages = []
    monkeypatch.setattr(watcher, "commenter_issue", lambda numero, message: messages.append(message) or True)
    return messages


def test_traiter_issue_interactive_lance_et_surveille_jusqu_a_fin_normale(cfg, monkeypatch, tmp_path, commentaires):
    """Fin de session SANS rapport (issue #903) : la clôture par rapport est
    couverte séparément par tests/test_mode_interactif_rapport_903.py — ici,
    `_surveiller_session_tmux` retourne "terminee" (comme à l'étape 2),
    traité désormais par le repli « fin sans rapport » (fermeture SANS
    `done`, jamais une issue laissée ouverte sans label — invariant #903)."""
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    monkeypatch.setattr(watcher, "lancer_claude", lambda *a, **k: (True, "hors_groupe"))
    monkeypatch.setattr(watcher, "_surveiller_session_tmux", lambda nom, echeance, chemin_rapport: "terminee")
    fermetures = []
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda numero: fermetures.append(numero) or True)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda numero: None)

    resultat = watcher._traiter_issue_interactive(
        numero=10, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=1800,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False,
    )

    assert resultat == (True, None)
    assert any("tmux attach" in m for m in commentaires), "la commande d'attache doit être postée (point 3)"
    assert any("sans rapport" in m and watcher.LABEL_FAIT in m for m in commentaires), (
        "le commentaire de repli doit mentionner l'absence de rapport ET le label 'done' (jamais posé)")
    assert fermetures == [10], "la session disparue sans rapport doit être fermée sans 'done' (issue #903)"


def test_traiter_issue_interactive_timeout_pose_needs_human(cfg, monkeypatch, tmp_path, commentaires):
    """TIMEOUT dépassé (issue #903, point 4) : comme à l'étape 2 (session
    tuée, commentaire), avec en plus le label `needs-human` posé — comme le
    fait déjà le chemin automatique après un abandon — pour interdire la
    relance."""
    appels_kill = []
    labels_poses = []
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    monkeypatch.setattr(watcher, "lancer_claude", lambda *a, **k: (True, "meme_groupe"))
    monkeypatch.setattr(watcher, "_surveiller_session_tmux", lambda nom, echeance, chemin_rapport: "timeout")
    monkeypatch.setattr(watcher, "_tuer_session_tmux", lambda nom: appels_kill.append(nom))
    monkeypatch.setattr(watcher, "ajouter_label", lambda numero, label: labels_poses.append((numero, label)))

    resultat = watcher._traiter_issue_interactive(
        numero=11, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=60,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False,
    )

    assert resultat == (True, None)
    assert appels_kill == ["bridge-t901-issue11"]
    assert any("TIMEOUT" in m for m in commentaires)
    assert labels_poses == [(11, watcher.LABEL_ECHEC)], "needs-human doit être posé, interdisant toute relance"
    assert not (tmp_path / "tmux" / "bridge-t901-issue11.sh").exists(), (
        "le script de lancement doit être nettoyé une fois le TIMEOUT traité")


def test_traiter_issue_interactive_reprise_session_existante_ne_relance_pas(cfg, monkeypatch, tmp_path, commentaires):
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)

    def jamais_appele(*a, **k):
        raise AssertionError("lancer_claude ne doit pas être appelé si la session existe déjà")
    monkeypatch.setattr(watcher, "lancer_claude", jamais_appele)
    monkeypatch.setattr(watcher, "_surveiller_session_tmux", lambda nom, echeance, chemin_rapport: "terminee")
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda numero: True)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda numero: None)

    resultat = watcher._traiter_issue_interactive(
        numero=12, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=1800,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False,
    )

    assert resultat == (True, None)
    assert any("déjà en cours" in m or "reprise" in m for m in commentaires)


def test_traiter_issue_interactive_repli_si_lancement_tmux_impossible(cfg, monkeypatch, tmp_path, commentaires):
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    monkeypatch.setattr(watcher, "lancer_claude", lambda *a, **k: (False, "tmux introuvable dans le PATH."))

    def jamais_appele(*a, **k):
        raise AssertionError("aucune surveillance ne doit démarrer si le lancement a échoué")
    monkeypatch.setattr(watcher, "_surveiller_session_tmux", jamais_appele)

    resultat = watcher._traiter_issue_interactive(
        numero=13, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=1800,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False,
    )

    assert resultat == (False, None), "le repli doit laisser l'appelant poursuivre le chemin automatique"
    assert any("repli" in m.lower() for m in commentaires)


def test_traiter_issue_interactive_dry_run_ne_commente_rien(cfg, monkeypatch, tmp_path, commentaires):
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    monkeypatch.setattr(watcher, "lancer_claude", lambda *a, **k: (True, "[DRY-RUN] Tâche simulée."))

    resultat = watcher._traiter_issue_interactive(
        numero=14, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=1800,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=True,
    )

    assert resultat == (True, None)
    assert commentaires == []


def main() -> int:
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

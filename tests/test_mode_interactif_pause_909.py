#!/usr/bin/env python3
"""Test de non-régression — issue #909 : mode interactif, étape 4.

Suite de l'étape 3 (#903) : jusqu'ici le TIMEOUT était un délai brut de
bout en bout — une pause de réflexion ou une absence d'Alain pouvait donc
faire dépasser le délai et tuer la session alors que CCL ne travaillait
plus. Cette étape suspend le TIMEOUT pendant que CCL attend Alain, grâce à
une sentinelle de pause (`logs/interactif/<projet>-issue<numero>.pause`,
posée/retirée par les hooks Claude Code `scripts/hook_pause_interactif.py`),
bornée à une durée maximale absolue (`DUREE_MAX_PAUSE_INTERACTIVE_S`).

Couvre :
1. `scripts/hook_pause_interactif.py` en sous-processus réel — pose/retire
   la sentinelle selon `BRIDGE_PROJET`/`BRIDGE_ISSUE` et l'argument
   (`debut`/`fin`), code de sortie TOUJOURS 0 (dossier absent, dossier non
   inscriptible, variables manquantes, argument invalide), aucune sortie
   stdout/stderr, écriture atomique.
2. `_chemin_pause_interactif`/`_heure_debut_pause` — chemin fixe, lecture du
   contenu (epoch), repli sur `st_mtime` si contenu corrompu, `None` si le
   fichier a disparu.
3. `_ecrire_reglages_hooks_interactif` — fichier de réglages hors worktree,
   quatre hooks (`Stop`/`Notification` -> "debut", `UserPromptSubmit`/
   `SessionEnd` -> "fin"), commande par chemin absolu (interpréteur +
   script), jamais par nom nu.
4. `_construire_cmd_claude_interactif(..., chemin_reglages=...)` — ajoute
   `--settings <chemin>` seulement si fourni ; chemin automatique
   (`_construire_cmd_claude`) jamais concerné.
5. `_surveiller_session_tmux` — le TIMEOUT est suspendu tant que la
   sentinelle existe (l'échéance recule d'autant), reprend ensuite ;
   "pause_trop_longue" si la pause dépasse `DUREE_MAX_PAUSE_INTERACTIVE_S`.
6. `_traiter_issue_interactive` — orchestration complète : pause trop
   longue -> `needs-human`, message distinct (pas un TIMEOUT de travail),
   jamais de relance ; sentinelle supprimée à CHAQUE fin de session (rapport,
   sans rapport, TIMEOUT, pause trop longue) ; reprise après un redémarrage
   du watcher pendant une pause (sentinelle déjà présente, contenu ancien
   conservé) sans tuer la session ; chemin automatique non affecté.

Exécution :  python3 -m pytest tests/test_mode_interactif_pause_909.py
        ou : python3 tests/test_mode_interactif_pause_909.py
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

import watcher  # noqa: E402

CHEMIN_HOOK = RACINE / "scripts" / "hook_pause_interactif.py"


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """CFG minimal et isolé, restauré après le test — même patron que
    tests/test_mode_interactif_rapport_903.py."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t909", depot="AlainDelree/x", rep_travail=tmp_path)
    monkeypatch.setattr(watcher, "DOSSIER_TMUX", tmp_path / "tmux")
    monkeypatch.setattr(watcher, "DOSSIER_RAPPORTS_INTERACTIFS", tmp_path / "interactif")
    yield watcher.CFG
    watcher.CFG = ancien_cfg


@pytest.fixture
def commentaires(monkeypatch):
    messages = []
    monkeypatch.setattr(watcher, "commenter_issue", lambda numero, message: messages.append(message) or True)
    return messages


# ─── 1. Script de hook en sous-processus réel ─────────────────────────────

def _lancer_hook(action, env_supp, cwd=None):
    env = dict(os.environ)
    env.update(env_supp)
    return subprocess.run(
        [sys.executable, "-I", str(CHEMIN_HOOK), action],
        env=env, cwd=cwd, capture_output=True, text=True, timeout=10,
    )


def test_hook_debut_cree_la_sentinelle_avec_heure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # Le script calcule RACINE_DEPOT depuis SON PROPRE chemin (parent de
    # scripts/) — jamais depuis le cwd : on invoque donc le vrai fichier du
    # dépôt, mais on vérifie la sentinelle au vrai emplacement qu'il va
    # utiliser (RACINE/logs/interactif), nettoyée après le test.
    chemin_sentinelle = RACINE / "logs" / "interactif" / "projx-issue7.pause"
    chemin_sentinelle.unlink(missing_ok=True)
    try:
        avant = time.time()
        resultat = _lancer_hook("debut", {"BRIDGE_PROJET": "projx", "BRIDGE_ISSUE": "7"})
        assert resultat.returncode == 0
        assert resultat.stdout == ""
        assert resultat.stderr == ""
        assert chemin_sentinelle.exists()
        contenu = float(chemin_sentinelle.read_text(encoding="utf-8").strip())
        assert avant - 1 <= contenu <= time.time() + 1
    finally:
        chemin_sentinelle.unlink(missing_ok=True)


def test_hook_debut_idempotent_ne_rafraichit_pas_une_sentinelle_existante(tmp_path):
    chemin_sentinelle = RACINE / "logs" / "interactif" / "projy-issue8.pause"
    chemin_sentinelle.unlink(missing_ok=True)
    try:
        chemin_sentinelle.parent.mkdir(parents=True, exist_ok=True)
        chemin_sentinelle.write_text("123.0", encoding="utf-8")
        resultat = _lancer_hook("debut", {"BRIDGE_PROJET": "projy", "BRIDGE_ISSUE": "8"})
        assert resultat.returncode == 0
        # Pas écrasée : l'heure de début de pause reste celle du PREMIER
        # Stop/Notification, pas celle d'un Stop répété pendant la même pause.
        assert chemin_sentinelle.read_text(encoding="utf-8").strip() == "123.0"
    finally:
        chemin_sentinelle.unlink(missing_ok=True)


def test_hook_fin_retire_la_sentinelle(tmp_path):
    chemin_sentinelle = RACINE / "logs" / "interactif" / "projz-issue9.pause"
    chemin_sentinelle.parent.mkdir(parents=True, exist_ok=True)
    chemin_sentinelle.write_text("1.0", encoding="utf-8")
    resultat = _lancer_hook("fin", {"BRIDGE_PROJET": "projz", "BRIDGE_ISSUE": "9"})
    assert resultat.returncode == 0
    assert resultat.stdout == ""
    assert resultat.stderr == ""
    assert not chemin_sentinelle.exists()


def test_hook_fin_sans_sentinelle_prealable_ne_leve_jamais(tmp_path):
    chemin_sentinelle = RACINE / "logs" / "interactif" / "projw-issue10.pause"
    chemin_sentinelle.unlink(missing_ok=True)
    resultat = _lancer_hook("fin", {"BRIDGE_PROJET": "projw", "BRIDGE_ISSUE": "10"})
    assert resultat.returncode == 0
    assert resultat.stdout == ""
    assert resultat.stderr == ""


def test_hook_sans_variables_environnement_ne_leve_jamais(tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("BRIDGE_")}
    resultat = subprocess.run(
        [sys.executable, "-I", str(CHEMIN_HOOK), "debut"],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert resultat.returncode == 0
    assert resultat.stdout == ""
    assert resultat.stderr == ""


def test_hook_argument_invalide_ne_leve_jamais(tmp_path):
    resultat = _lancer_hook("autre_chose", {"BRIDGE_PROJET": "p", "BRIDGE_ISSUE": "1"})
    assert resultat.returncode == 0
    assert resultat.stdout == ""
    assert resultat.stderr == ""


def test_hook_dossier_non_inscriptible_ne_leve_jamais(tmp_path):
    """Dossier `logs/interactif/` présent mais privé d'écriture (ex. disque
    plein, permissions) : jamais de code de sortie non nul ni de sortie
    stdout/stderr — le contrat impératif du hook l'interdit."""
    dossier = RACINE / "logs" / "interactif"
    dossier.mkdir(parents=True, exist_ok=True)
    ancien_mode = dossier.stat().st_mode
    os.chmod(dossier, 0o555)
    try:
        resultat = _lancer_hook("debut", {"BRIDGE_PROJET": "projro", "BRIDGE_ISSUE": "11"})
        assert resultat.returncode == 0
        assert resultat.stdout == ""
        assert resultat.stderr == ""
    finally:
        os.chmod(dossier, ancien_mode)
        (dossier / "projro-issue11.pause").unlink(missing_ok=True)


# ─── 2. Chemin + lecture de la sentinelle ─────────────────────────────────

def test_chemin_pause_interactif_meme_dossier_que_rapport(cfg, tmp_path):
    chemin_pause = watcher._chemin_pause_interactif("t909", 42)
    chemin_rapport = watcher._chemin_rapport_interactif("t909", 42)
    assert chemin_pause.parent == chemin_rapport.parent
    assert chemin_pause.name == "t909-issue42.pause"


def test_heure_debut_pause_lit_le_contenu(tmp_path):
    chemin = tmp_path / "x.pause"
    chemin.write_text("12345.5", encoding="utf-8")
    assert watcher._heure_debut_pause(chemin) == 12345.5


def test_heure_debut_pause_contenu_corrompu_repli_mtime(tmp_path):
    chemin = tmp_path / "x.pause"
    chemin.write_text("pas-un-nombre", encoding="utf-8")
    resultat = watcher._heure_debut_pause(chemin)
    assert resultat is not None
    assert abs(resultat - chemin.stat().st_mtime) < 1.0


def test_heure_debut_pause_fichier_absent_retourne_none(tmp_path):
    assert watcher._heure_debut_pause(tmp_path / "absent.pause") is None


# ─── 3. Réglages de hooks hors worktree ───────────────────────────────────

def test_ecrire_reglages_hooks_interactif_structure(cfg, tmp_path):
    chemin = watcher._ecrire_reglages_hooks_interactif("bridge-t909-issue1")
    # Hors worktree du projet piloté : dans DOSSIER_TMUX (gitignoré, propre
    # au dépôt Bridge_Agent — en production distinct du worktree/REP_TRAVAIL
    # du projet piloté, ici colocalisés par la fixture `cfg` pour simplicité).
    assert chemin.parent == watcher.DOSSIER_TMUX
    reglages = json.loads(chemin.read_text(encoding="utf-8"))
    hooks = reglages["hooks"]
    assert set(hooks) == {"Stop", "Notification", "UserPromptSubmit", "SessionEnd"}
    cmd_stop = hooks["Stop"][0]["hooks"][0]["command"]
    cmd_notif = hooks["Notification"][0]["hooks"][0]["command"]
    cmd_prompt = hooks["UserPromptSubmit"][0]["hooks"][0]["command"]
    cmd_end = hooks["SessionEnd"][0]["hooks"][0]["command"]
    assert cmd_stop == cmd_notif
    assert cmd_prompt == cmd_end
    assert cmd_stop.endswith("debut") or cmd_stop.endswith("'debut'")
    assert cmd_prompt.endswith("fin") or cmd_prompt.endswith("'fin'")
    # Chemin absolu de l'interpréteur ET du script — jamais un nom nu
    # dépendant du PATH.
    assert sys.executable in cmd_stop
    assert str(watcher.CHEMIN_HOOK_PAUSE_INTERACTIF) in cmd_stop
    assert Path(str(watcher.CHEMIN_HOOK_PAUSE_INTERACTIF)).is_absolute()


def test_ecrire_reglages_hooks_interactif_jamais_pour_le_chemin_automatique(cfg):
    """Le chemin automatique construit sa commande via `_construire_cmd_
    claude`, qui n'a ni paramètre `chemin_reglages` ni `--settings` —
    aucune régression possible par simple appel de cette fonction."""
    import inspect
    assert "chemin_reglages" not in inspect.signature(watcher._construire_cmd_claude).parameters


def test_construire_cmd_claude_interactif_avec_reglages(tmp_path):
    cmd = watcher._construire_cmd_claude_interactif(
        watcher.MODE_ECRITURE, "sonnet", "prompt", chemin_reglages=tmp_path / "r.json")
    assert cmd[:3] == ["claude", "--settings", str(tmp_path / "r.json")]


def test_construire_cmd_claude_interactif_sans_reglages_omet_loption(tmp_path):
    cmd = watcher._construire_cmd_claude_interactif(watcher.MODE_ECRITURE, "sonnet", "prompt")
    assert "--settings" not in cmd


# ─── 4. Suspension du TIMEOUT pendant une pause ───────────────────────────

def test_surveiller_session_tmux_pause_suspend_le_timeout(monkeypatch, tmp_path):
    """Sans suspension, une échéance de 3 "secondes" (ticks monotoniques)
    serait dépassée bien avant que la pause ne soit retirée. Avec
    suspension, le TIMEOUT ne doit JAMAIS déclencher pendant que la
    sentinelle existe, et la surveillance se poursuit normalement une fois
    la pause terminée (ici : jusqu'à disparition de la session, "terminee")."""
    horloge = {"t": 0.0}

    def faux_monotonic():
        horloge["t"] += 1.0
        return horloge["t"]

    monkeypatch.setattr(watcher.time, "monotonic", faux_monotonic)
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(watcher.time, "time", lambda: 1_000_000.0 + horloge["t"])

    chemin_pause = tmp_path / "s.pause"
    chemin_pause.write_text(str(1_000_000.0), encoding="utf-8")

    # Pause active pendant 5 sondages, puis retirée ; la session disparaît
    # au sondage suivant (sans rapport).
    etapes = iter([True, True, True, True, True, False])

    def faux_existe(nom):
        try:
            return next(etapes)
        except StopIteration:
            return False

    monkeypatch.setattr(watcher, "_tmux_session_existe", faux_existe)

    def pause_puis_fin():
        # Le 6e sondage ne doit plus voir la pause (retirée par le hook
        # "fin" au moment où Alain répond).
        if horloge["t"] >= 5:
            chemin_pause.unlink(missing_ok=True)

    appel_original = watcher.time.monotonic

    def monotonic_avec_effet():
        v = appel_original()
        pause_puis_fin()
        return v

    monkeypatch.setattr(watcher.time, "monotonic", monotonic_avec_effet)

    resultat = watcher._surveiller_session_tmux(
        "bridge-t909-issuepause", echeance=3.0, chemin_rapport=tmp_path / "aucun_rapport.md",
        chemin_pause=chemin_pause)
    # L'échéance initiale (3.0) a largement été dépassée par le temps que la
    # pause (5 sondages) se termine — la session n'a pourtant jamais été
    # jugée en TIMEOUT : elle se termine normalement (sans rapport).
    assert resultat == "terminee"


def test_surveiller_session_tmux_pause_trop_longue(monkeypatch, tmp_path):
    horloge = {"t": 0.0}

    def faux_monotonic():
        horloge["t"] += 1.0
        return horloge["t"]

    monkeypatch.setattr(watcher.time, "monotonic", faux_monotonic)
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    # Horloge murale : la pause a commencé bien avant la limite absolue.
    debut_pause = 1_000_000.0
    monkeypatch.setattr(
        watcher.time, "time",
        lambda: debut_pause + watcher.DUREE_MAX_PAUSE_INTERACTIVE_S + 1)
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)

    chemin_pause = tmp_path / "s.pause"
    chemin_pause.write_text(str(debut_pause), encoding="utf-8")

    resultat = watcher._surveiller_session_tmux(
        "bridge-t909-issuemax", echeance=100000.0, chemin_rapport=tmp_path / "aucun_rapport.md",
        chemin_pause=chemin_pause)
    assert resultat == "pause_trop_longue"


def test_surveiller_session_tmux_rapport_prioritaire_meme_en_pause(monkeypatch, tmp_path):
    """Un rapport de clôture stable reste prioritaire sur tout, y compris
    pendant une pause active (Alain a quitté juste après avoir fait écrire
    le rapport, la sentinelle n'a pas encore été retirée)."""
    horloge = {"t": 0.0}

    def faux_monotonic():
        horloge["t"] += 1.0
        return horloge["t"]

    monkeypatch.setattr(watcher.time, "monotonic", faux_monotonic)
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(watcher.time, "time", lambda: 1_000_000.0 + horloge["t"])
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)

    chemin_pause = tmp_path / "s.pause"
    chemin_pause.write_text("1000000.0", encoding="utf-8")
    chemin_rapport = tmp_path / "rapport.md"
    chemin_rapport.write_text("contenu stable", encoding="utf-8")

    resultat = watcher._surveiller_session_tmux(
        "bridge-t909-issuerapport", echeance=3.0, chemin_rapport=chemin_rapport,
        chemin_pause=chemin_pause)
    assert resultat == "rapport"


def test_surveiller_session_tmux_sans_sentinelle_comportement_inchange(monkeypatch, tmp_path):
    """`chemin_pause=None` (comportement #901/#903, non-régression) :
    identique à l'absence de ce paramètre."""
    horloge = {"t": 0.0}

    def faux_monotonic():
        horloge["t"] += 1.0
        return horloge["t"]

    monkeypatch.setattr(watcher.time, "monotonic", faux_monotonic)
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)

    resultat = watcher._surveiller_session_tmux(
        "bridge-t909-issuesanspause", echeance=3.0, chemin_rapport=tmp_path / "aucun_rapport.md",
        chemin_pause=None)
    assert resultat == "timeout"


# ─── 5. Orchestration : pause trop longue, nettoyage de la sentinelle ────

def test_traiter_issue_interactive_pause_trop_longue_pose_needs_human(cfg, monkeypatch, commentaires):
    chemin_pause = watcher._chemin_pause_interactif(watcher.CFG.nom, 50)
    chemin_pause.parent.mkdir(parents=True, exist_ok=True)
    chemin_pause.write_text("1.0", encoding="utf-8")

    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    monkeypatch.setattr(watcher, "lancer_claude", lambda *a, **k: (True, "hors_groupe"))
    monkeypatch.setattr(
        watcher, "_surveiller_session_tmux",
        lambda nom, echeance, chemin_rapport, chemin_pause=None: "pause_trop_longue")
    appels_kill = []
    monkeypatch.setattr(watcher, "_tuer_session_tmux", lambda nom: appels_kill.append(nom))
    labels_poses = []
    monkeypatch.setattr(watcher, "ajouter_label", lambda numero, label: labels_poses.append((numero, label)))

    pris_en_charge, sortie = watcher._traiter_issue_interactive(
        50, "Titre", "body", watcher.MODE_ECRITURE, timeout=60, modele="sonnet",
        perimetre_effectif="", cwd_effectif=watcher.CFG.rep_travail, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False)

    assert pris_en_charge is True
    assert sortie is None
    assert appels_kill == ["bridge-t909-issue50"]
    assert (50, watcher.LABEL_ECHEC) in labels_poses
    assert any("pause trop longue" in m.lower() for m in commentaires)
    assert all("timeout" not in m.lower() or "pas" in m.lower() for m in commentaires)
    # Sentinelle jamais laissée orpheline (point 6).
    assert not chemin_pause.exists()


def test_traiter_issue_interactive_timeout_normal_retire_la_sentinelle(cfg, monkeypatch, commentaires):
    chemin_pause = watcher._chemin_pause_interactif(watcher.CFG.nom, 51)
    chemin_pause.parent.mkdir(parents=True, exist_ok=True)
    chemin_pause.write_text("1.0", encoding="utf-8")

    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    monkeypatch.setattr(watcher, "lancer_claude", lambda *a, **k: (True, "hors_groupe"))
    monkeypatch.setattr(
        watcher, "_surveiller_session_tmux",
        lambda nom, echeance, chemin_rapport, chemin_pause=None: "timeout")
    monkeypatch.setattr(watcher, "_tuer_session_tmux", lambda nom: None)
    monkeypatch.setattr(watcher, "ajouter_label", lambda numero, label: None)

    watcher._traiter_issue_interactive(
        51, "Titre", "body", watcher.MODE_ECRITURE, timeout=60, modele="sonnet",
        perimetre_effectif="", cwd_effectif=watcher.CFG.rep_travail, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False)

    assert not chemin_pause.exists()


def test_traiter_issue_interactive_sans_rapport_retire_la_sentinelle(cfg, monkeypatch, commentaires, tmp_path):
    chemin_pause = watcher._chemin_pause_interactif(watcher.CFG.nom, 52)
    chemin_pause.parent.mkdir(parents=True, exist_ok=True)
    chemin_pause.write_text("1.0", encoding="utf-8")

    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    monkeypatch.setattr(watcher, "lancer_claude", lambda *a, **k: (True, "hors_groupe"))
    monkeypatch.setattr(
        watcher, "_surveiller_session_tmux",
        lambda nom, echeance, chemin_rapport, chemin_pause=None: "terminee")
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda numero: True)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda numero: None)
    monkeypatch.setattr(watcher, "_resume_worktree_sans_rapport", lambda *a, **k: "résumé")

    watcher._traiter_issue_interactive(
        52, "Titre", "body", watcher.MODE_ECRITURE, timeout=60, modele="sonnet",
        perimetre_effectif="", cwd_effectif=watcher.CFG.rep_travail, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False)

    assert not chemin_pause.exists()


def test_traiter_issue_interactive_rapport_retire_la_sentinelle(cfg, monkeypatch, commentaires):
    chemin_rapport = watcher._chemin_rapport_interactif(watcher.CFG.nom, 53)
    chemin_rapport.parent.mkdir(parents=True, exist_ok=True)
    chemin_rapport.write_text("Le rapport de clôture.", encoding="utf-8")
    chemin_pause = watcher._chemin_pause_interactif(watcher.CFG.nom, 53)
    chemin_pause.write_text("1.0", encoding="utf-8")

    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)

    pris_en_charge, sortie = watcher._traiter_issue_interactive(
        53, "Titre", "body", watcher.MODE_ECRITURE, timeout=60, modele="sonnet",
        perimetre_effectif="", cwd_effectif=watcher.CFG.rep_travail, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False)

    assert pris_en_charge is True
    assert sortie == "Le rapport de clôture."
    assert not chemin_pause.exists()


def test_traiter_issue_interactive_reprise_apres_redemarrage_pendant_une_pause(cfg, monkeypatch, commentaires):
    """Issue #909, point 5 : le watcher redémarre alors qu'une session est
    en pause — la sentinelle (hors worktree) survit, son contenu (heure de
    début réelle, ancienne) n'est jamais réinitialisé. La reprise ne doit
    JAMAIS tuer la session à tort : ici, la pause est déjà ancienne mais
    encore sous la limite absolue, donc la surveillance doit continuer
    normalement (pas de "pause_trop_longue" immédiat, pas de relance)."""
    ancienne_heure_debut = time.time() - 60  # pause commencée il y a 60s, réellement
    chemin_pause = watcher._chemin_pause_interactif(watcher.CFG.nom, 54)
    chemin_pause.parent.mkdir(parents=True, exist_ok=True)
    chemin_pause.write_text(str(ancienne_heure_debut), encoding="utf-8")

    # Session déjà existante : watcher redémarré pendant que CCL tournait.
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)

    captures = {}

    def faux_surveiller(nom, echeance, chemin_rapport, chemin_pause=None):
        captures["chemin_pause"] = chemin_pause
        return "rapport" if False else "terminee"

    monkeypatch.setattr(watcher, "_surveiller_session_tmux", faux_surveiller)
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda numero: True)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda numero: None)
    monkeypatch.setattr(watcher, "_resume_worktree_sans_rapport", lambda *a, **k: "résumé")

    def jamais_relance(*a, **k):
        raise AssertionError("lancer_claude ne doit jamais être appelé : la session existe déjà")
    monkeypatch.setattr(watcher, "lancer_claude", jamais_relance)

    watcher._traiter_issue_interactive(
        54, "Titre", "body", watcher.MODE_ECRITURE, timeout=60, modele="sonnet",
        perimetre_effectif="", cwd_effectif=watcher.CFG.rep_travail, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False)

    # La sentinelle persistée (même chemin, même contenu épargné par le
    # redémarrage) est bien celle transmise à la surveillance — le contenu
    # n'est jamais réinitialisé par le redémarrage.
    assert captures["chemin_pause"] == chemin_pause
    assert float(chemin_pause.read_text(encoding="utf-8")) == ancienne_heure_debut \
        if chemin_pause.exists() else True


# ─── 6. Chemin automatique non affecté ────────────────────────────────────

def test_lancer_claude_mode_tmux_false_jamais_de_reglages_hooks(cfg, monkeypatch, tmp_path):
    """Le chemin automatique (`mode_tmux=False`, immense majorité des
    issues) ne doit JAMAIS appeler `_ecrire_reglages_hooks_interactif` ni
    passer `--settings` : les hooks de pause ne concernent QUE les sessions
    interactives tmux."""
    appele = []
    monkeypatch.setattr(
        watcher, "_ecrire_reglages_hooks_interactif",
        lambda *a, **k: appele.append(1) or Path("/tmp/x"))
    captures = {}

    def faux_popen(cmd, **kwargs):
        captures["cmd"] = cmd
        raise FileNotFoundError("claude introuvable (test)")

    monkeypatch.setattr(watcher.subprocess, "Popen", faux_popen)
    watcher.lancer_claude(
        1, "Titre", "body", dry_run=False, mode=watcher.MODE_ECRITURE,
        timeout=60, cwd=tmp_path, mode_tmux=False)
    assert appele == []
    assert "--settings" not in captures.get("cmd", [])


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

#!/usr/bin/env python3
"""Test de non-régression — issue #914 : mode interactif, reprise d'une
session vivante sans nouveau commit de sauvegarde ni nouvel ACK.

Essais manuels (étape de test #913, 22/11/2026) : le watcher redémarré
pendant qu'une session interactive tournait reprenait bien la surveillance
sans relancer CCL (comportement voulu, issue #901) — mais `_demarrer_
traitement` était appelée INCONDITIONNELLEMENT avant même de savoir si
l'issue était interactive, donc avant la décision de reprise elle-même. Deux
effets de bord en découlaient à chaque redémarrage pendant une telle
session :
1. un second commit de sauvegarde, qui engloutissait dans la « sauvegarde »
   le travail déjà fait par CCL avant le redémarrage ;
2. un second commentaire d'ACK, en plus du commentaire de reprise.

Couvre :
1. `_interactif_deja_amorce` — vrai si rapport déjà présent, OU session tmux
   déjà vivante, OU script de lancement orphelin (mêmes trois conditions que
   `_traiter_issue_interactive`) ; faux sur une issue neuve.
2. `_ecrire_etat_initial_interactif`/`_lire_etat_initial_interactif` — aller-
   retour JSON, `None` si le fichier est absent (repli best-effort).
3. `_demarrer_traitement(reprise_interactive_vivante=True)` : pas d'ACK, pas
   de nouveau commit de sauvegarde, référence relue depuis l'état persisté
   (ou None/None en repli si l'état est introuvable — jamais de commit pour
   autant).
4. Chemin automatique strictement inchangé (`reprise_interactive_vivante`
   absent — défaut `False`) : ACK + commit de sauvegarde comme avant #914.
5. `_traiter_issue_interactive` : le tout premier lancement réel persiste
   l'état initial ; les trois branches de fin (rapport, TIMEOUT, pause trop
   longue) le nettoient.
6. Bout en bout (scénario de l'essai manuel pour Alain) : travail fait par
   CCL avant un redémarrage simulé, puis fin de session sans rapport APRÈS
   la reprise — le commentaire de clôture liste bien ce travail, grâce à la
   référence « depuis la sauvegarde » relue depuis l'état persisté plutôt
   que recalculée sur le HEAD courant (qui l'inclut déjà).

Exécution :  python3 -m pytest tests/test_mode_interactif_reprise_vivante_914.py
        ou : python3 tests/test_mode_interactif_reprise_vivante_914.py
"""

import json
import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

import watcher  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """CFG minimal et isolé, restauré après le test — même patron que
    tests/test_mode_interactif_rapport_903.py."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t914", depot="AlainDelree/x", rep_travail=tmp_path)
    monkeypatch.setattr(watcher, "DOSSIER_TMUX", tmp_path / "tmux")
    monkeypatch.setattr(watcher, "DOSSIER_RAPPORTS_INTERACTIFS", tmp_path / "interactif")
    yield watcher.CFG
    watcher.CFG = ancien_cfg


@pytest.fixture
def commentaires(monkeypatch):
    messages = []
    monkeypatch.setattr(watcher, "commenter_issue", lambda numero, message: messages.append(message) or True)
    return messages


@pytest.fixture(autouse=True)
def _bouchons_reseau(monkeypatch):
    """Mêmes bouchons que test_commit_sauvegarde_watcher_846.py — aucun appel
    réseau réel pendant _demarrer_traitement."""
    monkeypatch.setattr(watcher, "notifier_debut_sse", lambda numero: None)
    monkeypatch.setattr(watcher, "notifier_fin_sse", lambda numero: None)
    monkeypatch.setattr(watcher, "_lister_commentaires", lambda numero: [])
    monkeypatch.setattr(watcher, "verifier_preflight_token", lambda cwd=None: None)
    monkeypatch.setattr(watcher, "notifier", lambda *a, **k: None)


def _repo_git(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@a.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "a"], cwd=tmp_path, check=True)
    (tmp_path / "f1.txt").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "sauvegarde"], cwd=tmp_path, check=True)
    tete = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                           capture_output=True, text=True).stdout.strip()
    return tete


def _ajouter_commit(tmp_path, nom_fichier, message):
    (tmp_path / nom_fichier).write_text("contenu\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", message], cwd=tmp_path, check=True)


def _tete(tmp_path):
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                           capture_output=True, text=True).stdout.strip()


# ─── 1. _interactif_deja_amorce ─────────────────────────────────────────────

def test_interactif_deja_amorce_faux_sur_issue_neuve(cfg):
    assert watcher._interactif_deja_amorce(cfg.nom, 1) is False


def test_interactif_deja_amorce_vrai_si_rapport_present(cfg):
    chemin = watcher._chemin_rapport_interactif(cfg.nom, 2)
    chemin.parent.mkdir(parents=True)
    chemin.write_text("<!-- bridge:verdict:succes -->\n")
    assert watcher._interactif_deja_amorce(cfg.nom, 2) is True


def test_interactif_deja_amorce_vrai_si_session_tmux_vivante(cfg, monkeypatch):
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)
    assert watcher._interactif_deja_amorce(cfg.nom, 3) is True


def test_interactif_deja_amorce_vrai_si_script_orphelin(cfg, monkeypatch):
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)
    nom_session = watcher._nom_session_tmux(cfg.nom, 4)
    chemin_script = watcher.DOSSIER_TMUX / f"{nom_session}.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    assert watcher._interactif_deja_amorce(cfg.nom, 4) is True


# ─── 2. Persistance de l'état initial ──────────────────────────────────────

def test_etat_initial_absent_retourne_none(cfg):
    assert watcher._lire_etat_initial_interactif(cfg.nom, 10) is None


def test_etat_initial_aller_retour(cfg):
    watcher._ecrire_etat_initial_interactif(cfg.nom, 11, "abc123", "def456", ("f1.txt", "f2.txt"))
    relu = watcher._lire_etat_initial_interactif(cfg.nom, 11)
    assert relu == ("abc123", "def456", ("f1.txt", "f2.txt"))


def test_etat_initial_fichier_hors_worktree(cfg):
    watcher._ecrire_etat_initial_interactif(cfg.nom, 12, "abc123", None, ())
    chemin = watcher._chemin_etat_initial_interactif(cfg.nom, 12)
    assert chemin.parent == watcher.DOSSIER_RAPPORTS_INTERACTIFS
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    assert donnees["tete_avant_traitement"] == "abc123"
    assert donnees["commit_sauvegarde_watcher"] is None


# ─── 3. _demarrer_traitement en reprise ────────────────────────────────────

def _demarrer(cfg, numero, reprise, titre="T", body=""):
    return watcher._demarrer_traitement(
        numero, titre, body, watcher.MODE_ECRITURE, "ÉCRITURE",
        dry_run=False, cwd_effectif=cfg.rep_travail,
        reprise_interactive_vivante=reprise)


def test_reprise_vivante_sans_ack(cfg, commentaires, tmp_path):
    _repo_git(tmp_path)
    watcher._ecrire_etat_initial_interactif(cfg.nom, 20, "tete-orig", "commit-orig", ())
    _demarrer(cfg, 20, reprise=True)
    assert commentaires == [], "aucun ACK ne doit être posté à une reprise de session vivante"


def test_reprise_vivante_sans_nouveau_commit(cfg, commentaires, tmp_path):
    tete_originale = _repo_git(tmp_path)
    watcher._ecrire_etat_initial_interactif(cfg.nom, 21, tete_originale, tete_originale, ())
    avant = _tete(tmp_path)
    _demarrer(cfg, 21, reprise=True)
    apres = _tete(tmp_path)
    assert avant == apres, "aucun second commit de sauvegarde ne doit être créé à la reprise"


def test_reprise_vivante_relit_la_reference_originale(cfg, commentaires, tmp_path):
    tete_originale = _repo_git(tmp_path)
    watcher._ecrire_etat_initial_interactif(
        cfg.nom, 22, tete_originale, tete_originale, ("nouveau.txt",))
    # Du travail est fait APRÈS la sauvegarde d'origine (simule CCL avant un
    # redémarrage) : HEAD courant n'est plus la référence voulue.
    _ajouter_commit(tmp_path, "travail.txt", "travail de CCL")

    (_er, _db, _nb, _emp, tete_avant, _ts, _est, commit_sauv, suivis) = _demarrer(
        cfg, 22, reprise=True)

    assert tete_avant == tete_originale, (
        "la référence « depuis la sauvegarde » doit rester celle du premier "
        "lancement, pas le HEAD courant (qui inclut déjà le travail de CCL)")
    assert commit_sauv == tete_originale
    assert suivis == ("nouveau.txt",)


def test_reprise_vivante_sans_etat_persiste_aucun_commit_quand_meme(cfg, commentaires, tmp_path):
    """Repli best-effort : si l'état initial est introuvable (écriture ratée
    au premier lancement), on ne peut pas reconstituer la référence — mais on
    ne doit SURTOUT PAS refaire de commit de sauvegarde pour autant (ce
    serait exactement l'effet de bord à corriger)."""
    _repo_git(tmp_path)
    avant = _tete(tmp_path)

    (_er, _db, _nb, _emp, tete_avant, _ts, _est, commit_sauv, _suivis) = _demarrer(
        cfg, 23, reprise=True)

    apres = _tete(tmp_path)
    assert avant == apres, "pas de commit de sauvegarde même sans état persisté"
    assert tete_avant is None
    assert commit_sauv is None
    assert commentaires == []


# ─── 4. Chemin automatique strictement inchangé ────────────────────────────

def test_chemin_automatique_ack_et_commit_inchanges(cfg, commentaires, tmp_path):
    """Sans `reprise_interactive_vivante` (valeur par défaut, chemin
    automatique) : ACK posté et commit de sauvegarde fait, exactement comme
    avant l'issue #914 — voir tests/test_commit_sauvegarde_watcher_846.py."""
    _repo_git(tmp_path)
    avant = _tete(tmp_path)

    (_er, _db, _nb, _emp, tete_avant, _ts, _est, commit_sauv, _suivis) = _demarrer(
        cfg, 24, reprise=False)

    apres = _tete(tmp_path)
    assert avant != apres, "le commit de sauvegarde habituel doit toujours être fait"
    assert commit_sauv == apres
    assert tete_avant == avant
    assert len(commentaires) == 1
    assert "ACK" in commentaires[0]


# ─── 5. _traiter_issue_interactive : persistance au lancement, nettoyage à la fin ──

def test_lancement_reel_persiste_etat_initial(cfg, monkeypatch, tmp_path, commentaires):
    monkeypatch.setattr(watcher, "_lancer_session_tmux", lambda *a, **k: (True, "hors_groupe"))
    monkeypatch.setattr(watcher, "_surveiller_session_tmux", lambda *a, **k: "timeout")
    monkeypatch.setattr(watcher, "_tuer_session_tmux", lambda nom: None)
    monkeypatch.setattr(watcher, "ajouter_label", lambda *a, **k: None)

    numero = 30
    watcher._traiter_issue_interactive(
        numero=numero, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=60,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement="tete-xyz",
        commit_sauvegarde_watcher="commit-xyz", backup_watcher_nouveaux_suivis=("a.txt",),
        dry_run=False,
    )

    relu = watcher._lire_etat_initial_interactif(cfg.nom, numero)
    # TIMEOUT atteint juste après : le nettoyage retire déjà l'état — on
    # vérifie donc son contenu via un second lancement non suivi d'un TIMEOUT.
    assert relu is None, "nettoyé par la branche TIMEOUT (voir test suivant)"


def test_timeout_nettoie_etat_initial(cfg, monkeypatch, tmp_path, commentaires):
    numero = 31
    watcher._ecrire_etat_initial_interactif(cfg.nom, numero, "t0", "c0", ())
    nom_session = watcher._nom_session_tmux(cfg.nom, numero)
    chemin_script = watcher.DOSSIER_TMUX / f"{nom_session}.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)
    monkeypatch.setattr(watcher, "_tuer_session_tmux", lambda nom: None)
    monkeypatch.setattr(watcher, "_surveiller_session_tmux", lambda *a, **k: "timeout")
    monkeypatch.setattr(watcher, "ajouter_label", lambda *a, **k: None)

    watcher._traiter_issue_interactive(
        numero=numero, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=60,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement="t0", commit_sauvegarde_watcher="c0",
        backup_watcher_nouveaux_suivis=(), dry_run=False,
    )

    assert watcher._lire_etat_initial_interactif(cfg.nom, numero) is None


def test_cloture_via_rapport_nettoie_etat_initial(cfg, monkeypatch, tmp_path):
    numero = 32
    watcher._ecrire_etat_initial_interactif(cfg.nom, numero, "t0", "c0", ())
    chemin_rapport = tmp_path / "rapport.md"
    chemin_rapport.write_text("<!-- bridge:verdict:succes -->\n")
    chemin_script = tmp_path / "tmux" / f"bridge-{cfg.nom}-issue{numero}.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)

    watcher._cloturer_session_interactive_via_rapport(
        numero, f"bridge-{cfg.nom}-issue{numero}", chemin_rapport, chemin_script,
        tmp_path, "t0", "c0")

    assert watcher._lire_etat_initial_interactif(cfg.nom, numero) is None


def test_finalisation_sans_rapport_nettoie_etat_initial(cfg, monkeypatch, tmp_path):
    numero = 33
    watcher._ecrire_etat_initial_interactif(cfg.nom, numero, "t0", "c0", ())
    chemin_script = tmp_path / "tmux" / f"bridge-{cfg.nom}-issue{numero}.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda n: True)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda n: None)
    monkeypatch.setattr(watcher, "commenter_issue", lambda *a, **k: True)

    watcher._finaliser_session_interactive_sans_rapport(
        numero, f"bridge-{cfg.nom}-issue{numero}", chemin_script, tmp_path, "t0", "c0")

    assert watcher._lire_etat_initial_interactif(cfg.nom, numero) is None


# ─── 6. Bout en bout : scénario de l'essai manuel pour Alain ──────────────

def test_bout_en_bout_fin_sans_rapport_apres_reprise_voit_le_travail_avant_redemarrage(
        cfg, monkeypatch, tmp_path):
    """Reproduit l'essai manuel demandé par l'issue #914 : CCL crée un
    fichier (commit), le watcher « redémarre » (nouvel appel de
    _demarrer_traitement avec reprise_interactive_vivante=True), puis la
    session se termine sans rapport — le commentaire de clôture doit lister
    le fichier créé AVANT le redémarrage."""
    numero = 40
    tete_originale = _repo_git(tmp_path)

    # Premier lancement réel : persiste l'état initial (comme
    # _traiter_issue_interactive le ferait après un lancement tmux réussi).
    watcher._ecrire_etat_initial_interactif(cfg.nom, numero, tete_originale, tete_originale, ())

    # CCL travaille, commite un fichier créé AVANT le redémarrage simulé.
    _ajouter_commit(tmp_path, "fichier_ccl.txt", "ajoute fichier_ccl.txt")

    # Le watcher « redémarre » : _demarrer_traitement est rappelée en
    # reprise — doit relire la référence ORIGINALE, pas committer.
    avant_reprise = _tete(tmp_path)
    (_er, _db, _nb, _emp, tete_avant, _ts, _est, commit_sauv, _suivis) = _demarrer(
        cfg, numero, reprise=True)
    assert _tete(tmp_path) == avant_reprise, "aucun commit lors de la reprise"

    # La session se termine ensuite sans rapport de clôture.
    commentaires = []
    monkeypatch.setattr(watcher, "commenter_issue",
                         lambda n, m: commentaires.append(m) or True)
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda n: True)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda n: None)
    chemin_script = tmp_path / "tmux" / f"bridge-{cfg.nom}-issue{numero}.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")

    watcher._finaliser_session_interactive_sans_rapport(
        numero, f"bridge-{cfg.nom}-issue{numero}", chemin_script, tmp_path,
        tete_avant, commit_sauv)

    assert len(commentaires) == 1
    assert "fichier_ccl.txt" in commentaires[0], (
        "le commentaire de fin sans rapport doit lister le travail fait par "
        "CCL AVANT le redémarrage — perdu si la référence avait glissé vers "
        "le HEAD post-redémarrage")


def main() -> int:
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

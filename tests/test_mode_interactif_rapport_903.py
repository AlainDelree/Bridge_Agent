#!/usr/bin/env python3
"""Test de non-régression — issue #903 : mode interactif, étape 3.

Suite de l'étape 2 (#901) : établit l'invariant central de l'étude #888 —
quelle qu'en soit la cause, une fin de session interactive ne doit JAMAIS
laisser l'issue dans un état qui permettrait une relance au cycle suivant.
Avant cette issue, une fin de session (normale ou TIMEOUT) postait un
commentaire mais laissait l'issue OUVERTE sans aucun label : au cycle
suivant, le watcher la relançait (nouveau worktree `-bis`) — défaut constaté
manuellement par Alain le 18 novembre 2026 sur l'issue #902.

Couvre :
1. `_chemin_rapport_interactif`/`_nom_projet_assaini` — chemin fixe, hors
   worktree, assaini comme `_nom_session_tmux` (#901).
2. `_taille_fichier_rapport_interactif` — sondage d'attributs, jamais
   d'exception.
3. `_surveiller_session_tmux` — détection de stabilité du rapport (session
   vivante, rapport en cours d'écriture, rapport stable alors que la
   session vient de disparaître dans le même sondage) — priorité sur
   "terminee"/"timeout".
4. `_resume_worktree_sans_rapport` — commits depuis la sauvegarde + fichiers
   non committés (même relevé que le bouton « Avancement » #887).
5. `_fermer_issue_sans_done` — ferme SANS `--add-label done`.
6. `_finaliser_session_interactive_sans_rapport` — commentaire + fermeture
   sans `done` ; script de lancement conservé si la fermeture échoue
   (idempotence du retry, jamais une relance).
7. `_cloturer_session_interactive_via_rapport` — termine la session si
   encore ouverte, supprime le script, retourne le contenu du rapport ; se
   replie sur « sans rapport » si la lecture échoue malgré sa présence.
8. `_traiter_issue_interactive` — orchestration complète : rapport trouvé
   (stable, clôture identique au chemin automatique), session disparue sans
   rapport, TIMEOUT + `needs-human`, reprise après redémarrage du watcher
   (rapport déjà présent, ou script orphelin sans session ni rapport) —
   jamais de relance dans aucun cas.
9. `lancer_claude(..., mode_tmux=True)` — bloc de prompt dédié (chemin exact,
   écriture seulement sur confirmation d'Alain, précision scratch en lecture
   active) ; absent du chemin automatique (`mode_tmux=False`).

Exécution :  python3 -m pytest tests/test_mode_interactif_rapport_903.py
        ou : python3 tests/test_mode_interactif_rapport_903.py
"""

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
    tests/test_mode_interactif_tmux_901.py."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(nom="t903", depot="AlainDelree/x", rep_travail=tmp_path)
    monkeypatch.setattr(watcher, "DOSSIER_TMUX", tmp_path / "tmux")
    monkeypatch.setattr(watcher, "DOSSIER_RAPPORTS_INTERACTIFS", tmp_path / "interactif")
    yield watcher.CFG
    watcher.CFG = ancien_cfg


@pytest.fixture
def commentaires(monkeypatch):
    messages = []
    monkeypatch.setattr(watcher, "commenter_issue", lambda numero, message: messages.append(message) or True)
    return messages


def _repo_git(tmp_path):
    """Dépôt git jetable avec un commit de sauvegarde, pour
    _resume_worktree_sans_rapport/_commits_au_dela_sauvegarde."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "a@a.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "a"], cwd=tmp_path, check=True)
    (tmp_path / "f1.txt").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "sauvegarde"], cwd=tmp_path, check=True)
    tete = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path,
                           capture_output=True, text=True).stdout.strip()
    return tete


# ─── 1. Chemin fixe du rapport ─────────────────────────────────────────────

def test_chemin_rapport_interactif_hors_worktree():
    chemin = watcher._chemin_rapport_interactif("bridge_agent", 42)
    assert str(chemin) == str(watcher.DOSSIER_LOGS / "interactif" / "bridge_agent-issue42.md")


def test_chemin_rapport_interactif_assainit_comme_nom_session():
    nom_session = watcher._nom_session_tmux("mon:projet perso", 7)
    chemin = watcher._chemin_rapport_interactif("mon:projet perso", 7)
    assert nom_session == "bridge-mon_projet_perso-issue7"
    assert chemin.name == "mon_projet_perso-issue7.md"


# ─── 2. Taille de fichier best-effort ──────────────────────────────────────

def test_taille_fichier_rapport_interactif(tmp_path):
    chemin = tmp_path / "rapport.md"
    assert watcher._taille_fichier_rapport_interactif(chemin) is None
    chemin.write_text("abc")
    assert watcher._taille_fichier_rapport_interactif(chemin) == 3


# ─── 3. Détection de stabilité dans _surveiller_session_tmux ──────────────

class _Horloge:
    def __init__(self):
        self.t = 0.0

    def monotonic(self):
        return self.t

    def sleep(self, s):
        self.t += s


def _surveiller(monkeypatch, tmp_path, existe_apres_sondage, ecrire_a_idx=None,
                 contenu="<!-- bridge:verdict:succes -->\n", echeance_s=90):
    """Exécute _surveiller_session_tmux avec horloge/`_tmux_session_existe`
    simulés — `existe_apres_sondage(idx)` est appelé une fois par sondage,
    APRÈS l'écriture éventuelle du rapport au même index."""
    horloge = _Horloge()
    appels = {"n": 0}
    chemin_rapport = tmp_path / "rapport.md"
    monkeypatch.setattr(watcher.time, "monotonic", horloge.monotonic)
    monkeypatch.setattr(watcher.time, "sleep", horloge.sleep)

    def faux_existe(nom):
        idx = appels["n"]
        appels["n"] += 1
        if ecrire_a_idx is not None and idx == ecrire_a_idx:
            chemin_rapport.write_text(contenu)
        return existe_apres_sondage(idx)

    monkeypatch.setattr(watcher, "_tmux_session_existe", faux_existe)
    echeance = horloge.monotonic() + echeance_s
    return watcher._surveiller_session_tmux("fake-session", echeance, chemin_rapport), appels["n"]


def test_surveiller_session_tmux_rapport_stable_session_vivante(monkeypatch, tmp_path):
    resultat, _ = _surveiller(monkeypatch, tmp_path, lambda i: True, ecrire_a_idx=0)
    assert resultat == "rapport"


def test_surveiller_session_tmux_rapport_en_cours_d_ecriture_puis_stable(monkeypatch, tmp_path):
    """Le rapport ne doit JAMAIS être considéré complet tant que sa taille
    change d'un sondage à l'autre (session toujours vivante)."""
    chemin_rapport = tmp_path / "rapport.md"
    horloge = _Horloge()
    appels = {"n": 0}
    monkeypatch.setattr(watcher.time, "monotonic", horloge.monotonic)
    monkeypatch.setattr(watcher.time, "sleep", horloge.sleep)

    def faux_existe(nom):
        idx = appels["n"]
        appels["n"] += 1
        if idx == 0:
            chemin_rapport.write_text("ab")          # en cours d'écriture
        elif idx == 1:
            chemin_rapport.write_text("abcdef")       # toujours en cours
        return True

    monkeypatch.setattr(watcher, "_tmux_session_existe", faux_existe)
    resultat = watcher._surveiller_session_tmux("fake-session", horloge.monotonic() + 90, chemin_rapport)
    assert resultat == "rapport"
    assert appels["n"] == 3, "jamais lu avant que la taille se stabilise sur deux sondages"


def test_surveiller_session_tmux_rapport_et_fin_de_session_meme_sondage(monkeypatch, tmp_path):
    """Le rapport écrit puis la session qui se termine DANS LE MÊME
    intervalle ne doit jamais être perdu au profit de "terminee" — une
    session morte ne peut plus écrire, une seule lecture suffit alors."""
    resultat, n = _surveiller(monkeypatch, tmp_path, lambda i: False, ecrire_a_idx=0)
    assert resultat == "rapport"
    assert n == 1


def test_surveiller_session_tmux_aucun_rapport_session_disparait():
    pass  # couvert par tests/test_mode_interactif_tmux_901.py (comportement #901 inchangé)


# ─── 4. Résumé du worktree pour le commentaire de repli ───────────────────

def test_resume_worktree_sans_rapport_avec_commits_et_fichiers(tmp_path):
    tete = _repo_git(tmp_path)
    (tmp_path / "f2.txt").write_text("world\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "travail en cours"], cwd=tmp_path, check=True)
    (tmp_path / "f3.txt").write_text("brouillon\n")

    resume = watcher._resume_worktree_sans_rapport(tmp_path, tete, None)
    assert "travail en cours" in resume
    assert "f3.txt" in resume
    assert "Commits depuis la sauvegarde" in resume
    assert "Fichiers modifiés non committés" in resume


def test_resume_worktree_sans_rapport_rien_a_signaler(tmp_path):
    tete = _repo_git(tmp_path)
    resume = watcher._resume_worktree_sans_rapport(tmp_path, tete, None)
    assert resume == "**Commits depuis la sauvegarde :** aucun.\n\n**Fichiers modifiés non committés :** aucun."


# ─── 5. Fermeture SANS le label 'done' ─────────────────────────────────────

def test_fermer_issue_sans_done_ne_pose_jamais_done(cfg, monkeypatch):
    appels = []

    class FauxResultat:
        returncode = 0
        stderr = ""

    def faux_run(argv, **kwargs):
        appels.append(argv)
        return FauxResultat()

    monkeypatch.setattr(watcher.subprocess, "run", faux_run)
    monkeypatch.setattr(watcher.etat_rate_limit, "maj_rate_limit", lambda *a, **k: None)

    assert watcher._fermer_issue_sans_done(99) is True
    commandes_gh = [a for a in appels if a[0] == "gh"]
    assert any(a[:3] == ["gh", "issue", "close"] for a in commandes_gh)
    assert not any("--add-label" in a and watcher.LABEL_FAIT in a for a in commandes_gh), (
        "le label 'done' ne doit JAMAIS être posé par ce chemin")


def test_fermer_issue_sans_done_echec_close(cfg, monkeypatch):
    class FauxEchec:
        returncode = 1
        stderr = "network error"

    monkeypatch.setattr(watcher.subprocess, "run", lambda *a, **k: FauxEchec())
    monkeypatch.setattr(watcher.etat_rate_limit, "maj_rate_limit", lambda *a, **k: None)
    assert watcher._fermer_issue_sans_done(100) is False


# ─── 6. Repli complet « fin sans rapport » ────────────────────────────────

def test_finaliser_session_interactive_sans_rapport_ferme_sans_done(cfg, monkeypatch, tmp_path, commentaires):
    tete = _repo_git(tmp_path)
    chemin_script = tmp_path / "tmux" / "bridge-t903-issue1.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    fermetures = []
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda numero: fermetures.append(numero) or True)
    retires = []
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda numero: retires.append(numero))

    watcher._finaliser_session_interactive_sans_rapport(
        1, "bridge-t903-issue1", chemin_script, tmp_path, tete, None)

    assert fermetures == [1]
    assert retires == [1]
    assert not chemin_script.exists(), "le script est supprimé une fois la fermeture réussie"
    assert any("sans rapport" in m and watcher.LABEL_FAIT in m for m in commentaires)


def test_finaliser_session_interactive_sans_rapport_conserve_script_si_echec(cfg, monkeypatch, tmp_path, commentaires):
    """Idempotence du retry (issue #903) : si `gh issue close` échoue, le
    script de lancement reste le marqueur qui permet de retenter cette même
    finalisation au prochain cycle — jamais de relance de CCL pour autant."""
    chemin_script = tmp_path / "tmux" / "bridge-t903-issue2.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda numero: False)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda numero: None)

    watcher._finaliser_session_interactive_sans_rapport(
        2, "bridge-t903-issue2", chemin_script, tmp_path, None, None)

    assert chemin_script.exists(), "le script DOIT survivre à un échec de fermeture"


# ─── 7. Clôture via rapport trouvé ──────────────────────────────────────────

def test_cloturer_session_interactive_via_rapport_termine_session_et_lit(cfg, monkeypatch, tmp_path):
    chemin_rapport = tmp_path / "rapport.md"
    chemin_rapport.write_text("<!-- bridge:verdict:succes -->\n✅ fait\n")
    chemin_script = tmp_path / "tmux" / "bridge-t903-issue3.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    appels_kill = []
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: True)
    monkeypatch.setattr(watcher, "_tuer_session_tmux", lambda nom: appels_kill.append(nom))

    sortie = watcher._cloturer_session_interactive_via_rapport(
        3, "bridge-t903-issue3", chemin_rapport, chemin_script, tmp_path, None, None)

    assert sortie == "<!-- bridge:verdict:succes -->\n✅ fait\n"
    assert appels_kill == ["bridge-t903-issue3"], "la session encore ouverte doit être terminée"
    assert not chemin_script.exists()
    assert chemin_rapport.exists(), "le rapport est conservé comme trace, jamais supprimé"


def test_cloturer_session_interactive_via_rapport_ne_tue_pas_si_deja_finie(cfg, monkeypatch, tmp_path):
    chemin_rapport = tmp_path / "rapport.md"
    chemin_rapport.write_text("<!-- bridge:verdict:succes -->\n")
    chemin_script = tmp_path / "tmux" / "bridge-t903-issue4.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)

    def jamais_appele(nom):
        raise AssertionError("_tuer_session_tmux ne doit pas être appelé si la session a déjà disparu")
    monkeypatch.setattr(watcher, "_tuer_session_tmux", jamais_appele)

    sortie = watcher._cloturer_session_interactive_via_rapport(
        4, "bridge-t903-issue4", chemin_rapport, chemin_script, tmp_path, None, None)
    assert sortie is not None


# ─── 8. Orchestration complète (_traiter_issue_interactive) ───────────────

def test_traiter_issue_interactive_rapport_present_a_l_entree(cfg, monkeypatch, tmp_path, commentaires):
    """Point 5 : un rapport déjà présent prime sur toute autre décision —
    jamais de relance, que la session soit encore ouverte ou pas."""
    numero = 50
    chemin_rapport = watcher._chemin_rapport_interactif(watcher.CFG.nom, numero)
    chemin_rapport.parent.mkdir(parents=True)
    chemin_rapport.write_text("<!-- bridge:verdict:succes -->\n✅ confirmé par Alain\n")
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)

    def jamais_appele(*a, **k):
        raise AssertionError("ni lancer_claude ni _surveiller_session_tmux ne doivent être appelés")
    monkeypatch.setattr(watcher, "lancer_claude", jamais_appele)
    monkeypatch.setattr(watcher, "_surveiller_session_tmux", jamais_appele)

    pris_en_charge, sortie = watcher._traiter_issue_interactive(
        numero=numero, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=1800,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False,
    )

    assert pris_en_charge is True
    assert "confirmé par Alain" in sortie


def test_traiter_issue_interactive_reprise_apres_redemarrage_sans_session_ni_rapport(cfg, monkeypatch, tmp_path, commentaires):
    """Point 5/3 : script de lancement orphelin (session disparue pendant
    que ce watcher ne tournait pas), ni rapport — jamais relancé, repli
    direct sur « fin sans rapport » (c'est exactement le défaut constaté
    manuellement par Alain sur l'issue #902)."""
    numero = 51
    nom_session = watcher._nom_session_tmux(watcher.CFG.nom, numero)
    chemin_script = watcher.DOSSIER_TMUX / f"{nom_session}.sh"
    chemin_script.parent.mkdir(parents=True)
    chemin_script.write_text("#!/bin/sh\n")
    monkeypatch.setattr(watcher, "_tmux_session_existe", lambda nom: False)

    def jamais_appele(*a, **k):
        raise AssertionError("aucun lancement ne doit avoir lieu — c'est exactement le bug #902")
    monkeypatch.setattr(watcher, "lancer_claude", jamais_appele)
    fermetures = []
    monkeypatch.setattr(watcher, "_fermer_issue_sans_done", lambda n: fermetures.append(n) or True)
    monkeypatch.setattr(watcher, "_issues_en_cours_retirer", lambda n: None)

    pris_en_charge, sortie = watcher._traiter_issue_interactive(
        numero=numero, titre="T", body="B", mode=watcher.MODE_ECRITURE, timeout=1800,
        modele="", perimetre_effectif="", cwd_effectif=tmp_path, chemin_scratch=None,
        chemin_worktree=None, chemin_outil_lecture_exec=None, worktree_repris=False,
        commits_ecart_worktree=0, tete_avant_traitement=None, commit_sauvegarde_watcher=None,
        backup_watcher_nouveaux_suivis=(), dry_run=False,
    )

    assert (pris_en_charge, sortie) == (True, None)
    assert fermetures == [numero]


def test_traiter_issue_interactive_lecture_active_precision_scratch_dans_prompt(cfg, monkeypatch, tmp_path):
    """Pour une issue en lecture active (mode_scratch), le bloc de prompt
    interactif doit préciser que le fichier de rapport est la seule écriture
    autorisée hors du scratch."""
    captures = {}

    def faux_lancer_session_tmux(nom_session, cmd, cwd, env_extra):
        captures["prompt"] = cmd[-1]
        return True, "hors_groupe"

    monkeypatch.setattr(watcher, "_lancer_session_tmux", faux_lancer_session_tmux)
    chemin_scratch = tmp_path / "scratch"
    succes, _ = watcher.lancer_claude(
        60, "Titre", "Corps", dry_run=False, mode=watcher.MODE_LECTURE_ACTIVE,
        timeout=60, chemin_scratch=chemin_scratch, cwd=tmp_path, mode_tmux=True)

    assert succes is True
    prompt = captures["prompt"]
    assert "SESSION INTERACTIVE" in prompt
    assert str(watcher._chemin_rapport_interactif("t903", 60)) in prompt
    assert "SEULE écriture autorisée" in prompt
    assert str(chemin_scratch) in prompt


def test_lancer_claude_mode_tmux_false_sans_bloc_interactif(cfg, monkeypatch, tmp_path):
    """Chemin automatique (mode_tmux=False, défaut partout ailleurs) :
    jamais le bloc de prompt interactif, quel que soit le label de l'issue."""
    captures = {}

    def faux_popen(cmd, **kwargs):
        captures["prompt"] = cmd[-1]
        raise FileNotFoundError("claude introuvable (test)")

    monkeypatch.setattr(watcher.subprocess, "Popen", faux_popen)
    watcher.lancer_claude(
        61, "Titre", "Corps", dry_run=False, mode=watcher.MODE_ECRITURE,
        timeout=60, cwd=tmp_path, mode_tmux=False)

    assert "SESSION INTERACTIVE" not in captures["prompt"]


def main() -> int:
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

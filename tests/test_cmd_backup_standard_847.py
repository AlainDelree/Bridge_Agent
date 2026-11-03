#!/usr/bin/env python3
"""Test de non-régression — issue #847 : le commit de sauvegarde fait par le
watcher lui-même (issue #846) s'applique désormais aussi quand `CMD_BACKUP`
vaut la commande STANDARD écrite par défaut par `nouveau_projet.py` — un
commit git de tout le dossier, `--allow-empty`, quel que soit le message —
et non plus seulement quand `CMD_BACKUP` est vide. Constat de l'issue : 12
projets sur 13 avaient cette même valeur dans leur `.conf`, ce qui excluait
en pratique tous les projets git de la sauvegarde #846 (y compris
Relecture_Bridge, où l'oubli de l'agent avait motivé #846 — incident #121).

Couvre les cas demandés par l'issue :
1. Commande standard reconnue : le watcher committe (comme CMD_BACKUP vide).
2. Variantes d'espacement/guillemets de la commande standard : reconnues.
3. Commande personnalisée de type alchess : inchangée, le watcher ne
   committe rien, la commande reste transmise à l'agent (couvert aussi côté
   bout-en-bout par `tests/test_commit_sauvegarde_watcher_846.py`).
4. Valeur vide : comportement #846 inchangé (déjà couvert par
   `test_commit_vide_worktree_neuf` dans le fichier #846 — revérifié ici au
   niveau du critère de reconnaissance lui-même).
5. Valeur non reconnue (variante trop éloignée du gabarit) : le watcher ne
   committe pas, par prudence (« dans le doute, ne pas se substituer à
   l'agent »).

Exécution :  python3 -m pytest tests/test_cmd_backup_standard_847.py
        ou : python3 tests/test_cmd_backup_standard_847.py
"""

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

import watcher  # noqa: E402


# ─── 1/2/4/5. Critère de reconnaissance lui-même (`_cmd_backup_est_standard`)

VARIANTES_STANDARD = [
    # Exactement la valeur écrite par nouveau_projet.py (GABARIT_CONF).
    'git add -A && git commit -m "avant-<description>" --allow-empty',
    # Guillemets simples au lieu de doubles.
    "git add -A && git commit -m 'avant-<description>' --allow-empty",
    # Espaces multiples / tabulations autour de && et des arguments.
    'git  add  -A   &&   git commit -m "avant-<description>" --allow-empty',
    'git add -A &&\tgit commit -m "avant-<description>"\t--allow-empty',
    # Espaces de bordure (début/fin de la valeur lue dans le .conf).
    '  git add -A && git commit -m "avant-<description>" --allow-empty  ',
    # Message personnalisé (projet édité à la main) — la description de
    # l'issue n'exige PAS la convention « avant-<description> » dans le
    # message, seulement la structure de la commande.
    'git add -A && git commit -m "sauvegarde avant modification" --allow-empty',
    'git add -A && git commit -m "" --allow-empty',
]


@pytest.mark.parametrize("cmd", VARIANTES_STANDARD)
def test_commande_standard_et_variantes_reconnues(cmd):
    assert watcher._cmd_backup_est_standard(cmd) is True, cmd


VARIANTES_NON_RECONNUES = [
    "",  # vide : cas distinct, pas « reconnu standard » (voir l'appelant)
    "python3 outils/sauvegarder.py",  # alchess : gestionnaire propre, sans commit git
    "git add -A && git commit -m \"avant-<description>\"",  # --allow-empty manquant
    "git commit -am \"avant-<description>\" --allow-empty",  # pas de 'git add -A' séparé
    "git add -A && git commit --allow-empty -m \"avant-<description>\"",  # ordre des drapeaux inversé
    "git add -A && git commit -m avant-<description> --allow-empty",  # message non cité
    "git add -A && git commit -m \"avant-<description>\" --allow-empty && git push",  # commande étendue
]


@pytest.mark.parametrize("cmd", VARIANTES_NON_RECONNUES)
def test_valeurs_non_standard_non_reconnues(cmd):
    assert watcher._cmd_backup_est_standard(cmd) is False, cmd


# ─── Bout-en-bout : le watcher committe réellement sur la commande standard

def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


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
    """Mêmes bouchons réseau que `tests/test_commit_sauvegarde_watcher_846.py`
    — aucun appel GitHub réel, `_demarrer_traitement` poste quand même une
    ACK."""
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


def test_cmd_backup_standard_watcher_committe(depot):
    """Commande standard exacte du gabarit (issue #847, point 1) : le
    watcher fait désormais le commit de sauvegarde lui-même, comme si
    CMD_BACKUP était vide (#846) — l'agent n'a plus à le refaire."""
    cmd_backup = 'git add -A && git commit -m "avant-<description>" --allow-empty'
    cfg = _config_isolee(depot, "test847a", cmd_backup=cmd_backup)
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8471)

    assert commit_sauvegarde is not None, "commande standard : le watcher doit committer lui-même"
    assert nouveaux_suivis == ()

    commits = _rev_list(depot, tete_avant)
    assert len(commits) == 1, f"le commit de sauvegarde doit être le SEUL et PREMIER commit : {commits}"
    assert commits[0] == commit_sauvegarde

    diff = subprocess.run(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit_sauvegarde],
                          cwd=depot, capture_output=True, text=True, check=True)
    assert diff.stdout.strip() == "", "le commit de sauvegarde sur un worktree neuf doit être VIDE"


def test_cmd_backup_standard_variante_espacement_watcher_committe(depot):
    """Variante d'espacement/guillemets de la commande standard (issue #847,
    point 2) : toujours reconnue, le watcher committe."""
    cmd_backup = "git  add  -A &&   git commit -m 'avant-<description>'  --allow-empty"
    cfg = _config_isolee(depot, "test847b", cmd_backup=cmd_backup)
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, _nouveaux_suivis) = _demarrer(cfg, 8472)

    assert commit_sauvegarde is not None, "variante d'espacement de la commande standard : doit être reconnue"
    commits = _rev_list(depot, tete_avant)
    assert len(commits) == 1
    assert commits[0] == commit_sauvegarde


def test_cmd_backup_personnalisee_alchess_watcher_ne_committe_pas(depot):
    """Commande personnalisée de type alchess (issue #847, point 3) :
    comportement #846 inchangé — aucun commit du watcher, la commande reste
    la consigne transmise à l'agent."""
    tete_avant_appel = watcher._tete_git(depot)
    cfg = _config_isolee(depot, "test847c", cmd_backup="python3 outils/sauvegarder.py")
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8473)

    assert commit_sauvegarde is None, "CMD_BACKUP personnalisée : le watcher ne doit rien committer lui-même"
    assert nouveaux_suivis == ()
    assert tete_avant == tete_avant_appel
    assert watcher._tete_git(depot) == tete_avant_appel, "aucun commit ne doit avoir été ajouté"


def test_cmd_backup_vide_watcher_committe(depot):
    """Valeur vide (issue #847, point 4) : comportement #846 inchangé — le
    watcher committe lui-même."""
    cfg = _config_isolee(depot, "test847d", cmd_backup="")
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, _nouveaux_suivis) = _demarrer(cfg, 8474)

    assert commit_sauvegarde is not None
    commits = _rev_list(depot, tete_avant)
    assert len(commits) == 1
    assert commits[0] == commit_sauvegarde


def test_cmd_backup_non_reconnue_agent_committe(depot):
    """Valeur non reconnue avec certitude (issue #847, point 5 : --allow-empty
    manquant) : dans le doute, le watcher ne se substitue pas à l'agent —
    comportement #846 inchangé (aucun commit du watcher)."""
    tete_avant_appel = watcher._tete_git(depot)
    cmd_backup = 'git add -A && git commit -m "avant-<description>"'
    cfg = _config_isolee(depot, "test847e", cmd_backup=cmd_backup)
    (_er, _d, _n, _e, tete_avant, _ts, _es,
     commit_sauvegarde, nouveaux_suivis) = _demarrer(cfg, 8475)

    assert commit_sauvegarde is None, "valeur non reconnue : le watcher ne doit rien committer lui-même"
    assert nouveaux_suivis == ()
    assert tete_avant == tete_avant_appel
    assert watcher._tete_git(depot) == tete_avant_appel, "aucun commit ne doit avoir été ajouté"


def main() -> int:
    """Même convention que les autres tests bout-en-bout de watcher.py :
    exécution directe via pytest lui-même (fixtures tmp_path/monkeypatch)."""
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

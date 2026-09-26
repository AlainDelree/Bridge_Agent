"""scripts/utils.py — utilitaires bas niveau partagés entre watcher.py et les
scripts de scripts/ (issue #617, diagnostic #579 point 1).

Regroupe ici ce qui était dupliqué à l'identique entre watcher.py et
scripts/archiver_historique.py, pour n'avoir plus qu'un seul exemplaire.
"""
import json
import os
import sys
from pathlib import Path

RACINE_DEPOT = Path(__file__).resolve().parent.parent


def ecrire_json_atomique(chemin: Path, donnees) -> None:
    """Écrit `donnees` (JSON) dans `chemin` de façon atomique : fichier
    temporaire (suffixe .tmp<pid> pour éviter toute collision entre process
    concurrents) puis `os.replace`, atomique sur un même système de fichiers
    (POSIX et Windows)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, chemin)


def _pytest_actif() -> bool:
    """True si le process courant est un run pytest, quel qu'il soit."""
    return "PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules


def _script_tests_direct() -> bool:
    """True si le point d'entrée (`__main__`) du process est un fichier situé
    sous `tests/` du dépôt — cas des scripts de tests autonomes (`python3
    tests/test_xxx.py`, sans passer par pytest) que ce dépôt compte aussi
    (ex. tests/test_worktree_parallelisation_337.py, qui exerce le vrai code
    de watcher.py de bout en bout)."""
    point_entree = getattr(sys.modules.get("__main__"), "__file__", None)
    if not point_entree:
        return False
    try:
        Path(point_entree).resolve().relative_to(RACINE_DEPOT / "tests")
        return True
    except ValueError:
        return False


def notifications_reseau_neutralisees() -> bool:
    """True pendant les tests (issue #635) : neutralise globalement les
    notifications réseau best-effort vers new_issue.py —
    scripts/traitement_fin.py (notifier_fin_issue/notifier_debut_issue) et
    scripts/watcher_issues_inbox.py (_poster_best_effort) — sans dépendre
    d'un patch par test. Détecte aussi bien un run pytest qu'un script de
    tests/ exécuté directement. Échappatoire explicite si un test doit un
    jour vérifier l'envoi réel : variable d'environnement
    BRIDGE_AGENT_NOTIFS_RESEAU_FORCEES=1."""
    if os.environ.get("BRIDGE_AGENT_NOTIFS_RESEAU_FORCEES") == "1":
        return False
    return _pytest_actif() or _script_tests_direct()

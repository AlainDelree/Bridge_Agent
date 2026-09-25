"""scripts/utils.py — utilitaires bas niveau partagés entre watcher.py et les
scripts de scripts/ (issue #617, diagnostic #579 point 1).

Regroupe ici ce qui était dupliqué à l'identique entre watcher.py et
scripts/archiver_historique.py, pour n'avoir plus qu'un seul exemplaire.
"""
import json
import os
from pathlib import Path


def ecrire_json_atomique(chemin: Path, donnees) -> None:
    """Écrit `donnees` (JSON) dans `chemin` de façon atomique : fichier
    temporaire (suffixe .tmp<pid> pour éviter toute collision entre process
    concurrents) puis `os.replace`, atomique sur un même système de fichiers
    (POSIX et Windows)."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, chemin)

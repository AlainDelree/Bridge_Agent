#!/usr/bin/env python3
"""scripts/hook_pause_interactif.py — hook Claude Code (étude #888, étape 4 —
issue #909) : pose ou retire le fichier sentinelle de pause d'une session
interactive tmux, pour que watcher.py suspende le TIMEOUT pendant que CCL
attend Alain.

Appelé par les réglages de hooks écrits par watcher.py
(`_ecrire_reglages_hooks_interactif`, passés à `claude --settings <fichier>`,
fichier HORS du worktree du projet piloté — jamais capté par un commit) pour
quatre événements, chacun avec un argument distinct en ligne de commande :
  - `Stop` / `Notification`     -> argv[1] == "debut" (CCL a fini son tour ou
    demande quelque chose = il attend Alain) ;
  - `UserPromptSubmit` / `SessionEnd` -> argv[1] == "fin" (Alain a répondu =
    CCL reprend, ou la session se termine).

Contrat impératif (un hook ne doit JAMAIS perturber la session Claude) :
  - aucune sortie stdout/stderr, dans AUCUN cas ;
  - code de sortie TOUJOURS 0, quelle que soit l'erreur rencontrée (dossier
    absent, non inscriptible, variables d'environnement manquantes,
    arguments invalides...) ;
  - écriture atomique du fichier sentinelle (fichier temporaire + remplacement
    atomique) ;
  - ne dépend ni du PATH ni d'un shell interactif : invoqué via
    `sys.executable` + chemin absolu de ce script (voir
    `_ecrire_reglages_hooks_interactif` dans watcher.py), jamais par un nom
    nu qu'un `PATH` différent résoudrait autrement.

Le projet et le numéro d'issue de la session viennent des variables
d'environnement `BRIDGE_PROJET`/`BRIDGE_ISSUE`, déjà exportées par le script
de lancement tmux (`_ecrire_script_lancement_tmux`, issue #901) — prévues dès
cette étape pour les hooks de l'étude #888.

Le fichier sentinelle (`logs/interactif/<projet>-issue<numero>.pause`, même
dossier et même convention de nom que le rapport de clôture — voir
`_chemin_rapport_interactif`/`_chemin_pause_interactif` dans watcher.py)
contient l'heure de début de la pause (horloge murale, secondes depuis
l'epoch) : c'est watcher.py qui lit ce contenu pour calculer la durée de
pause et, le cas échéant, appliquer la durée maximale absolue.
"""
import os
import re
import sys
import time
from pathlib import Path

# RACINE_DEPOT = parent du dossier scripts/ qui contient CE fichier — jamais
# une constante absolue : permet de tester ce script isolément (copié dans un
# dossier temporaire) sans jamais toucher au vrai logs/interactif/ du dépôt.
RACINE_DEPOT = Path(__file__).resolve().parent.parent
DOSSIER_PAUSE = RACINE_DEPOT / "logs" / "interactif"


def _nom_projet_assaini(nom_projet: str) -> str:
    """Même règle que `watcher._nom_projet_assaini` (issue #901), dupliquée
    ici volontairement : ce script doit rester autonome, sans importer le
    gros watcher.py depuis un hook à chaque tour de Claude. Une seule ligne,
    stable depuis l'issue #901 — risque de divergence négligeable."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", nom_projet)


def _chemin_pause(nom_projet: str, numero: str) -> Path:
    return DOSSIER_PAUSE / f"{_nom_projet_assaini(nom_projet)}-issue{numero}.pause"


def _ecrire_atomique(chemin: Path, contenu: str) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + f".tmp{os.getpid()}")
    tmp.write_text(contenu, encoding="utf-8")
    os.replace(tmp, chemin)


def main() -> int:
    """Ne lève jamais, ne retourne jamais autre chose que 0 — voir le
    contrat impératif ci-dessus : toute anomalie est avalée en silence
    plutôt que de risquer de bloquer ou de perturber Claude Code."""
    try:
        action = sys.argv[1] if len(sys.argv) > 1 else ""
        projet = os.environ.get("BRIDGE_PROJET", "")
        numero = os.environ.get("BRIDGE_ISSUE", "")
        if action not in ("debut", "fin") or not projet or not numero:
            return 0
        chemin = _chemin_pause(projet, numero)
        if action == "debut":
            if not chemin.exists():
                _ecrire_atomique(chemin, str(time.time()))
        else:
            chemin.unlink(missing_ok=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

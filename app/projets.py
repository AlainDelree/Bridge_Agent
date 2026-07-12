"""Fonctions liées aux projets du bridge (un fichier .conf = un projet).

Extraites de new_issue.py à l'étape 3 du refactoring modulaire. Regroupe la
liste des projets, la recherche par nom et l'écriture des clés éditables du
.conf. Le lecteur de config est partagé avec watcher.py, à la racine du projet.
"""

import os
import sys
from pathlib import Path

# Racine du projet (dossier parent du package app/) : watcher.py et le dossier
# configs/ y vivent. On l'ajoute au sys.path pour que « from watcher import »
# fonctionne même si ce module est importé isolément.
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

from watcher import Config, charger_config  # noqa: E402


# Clés modifiables via l'interface (les autres : NOM, DEPOT, REP_TRAVAIL,
# PERIMETRE, CMD_BACKUP se changent à la main dans le .conf).
CLES_EDITABLES = {
    "TOPIC_NTFY", "LABEL", "INTERVALLE", "MAX_ESSAIS",
    "TIMEOUT_CLAUDE", "SCRIPT_BIP", "LOG_TAILLE_MAX_MO", "LOG_ARCHIVES",
    "MODELE_CCL", "MOT_DE_PASSE", "FICHIER_CONTEXTE",
}


def sauvegarder_conf(nom_projet: str, nouvelles_valeurs: dict) -> tuple[bool, str]:
    """Met à jour les clés éditables du .conf en préservant commentaires et
    structure. Les lignes commentées correspondant à une clé éditée sont
    décommentées au passage. Les clés absentes du fichier sont ajoutées à la fin."""
    chemin = DOSSIER_SCRIPT / "configs" / f"{nom_projet}.conf"
    if not chemin.exists():
        return False, f"Fichier introuvable : {chemin.name}"

    a_ecrire = {k.upper(): v for k, v in nouvelles_valeurs.items()
                if k.upper() in CLES_EDITABLES}

    lignes          = chemin.read_text(encoding="utf-8").splitlines()
    nouvelles_lignes = []
    mises_a_jour    = set()

    for ligne in lignes:
        stripped = ligne.strip()
        # Ligne commentée : on regarde si elle cache une clé éditable.
        if stripped.startswith("#"):
            reste = stripped[1:].strip()
            cle, sep, _ = reste.partition("=")
            cle_norm = cle.strip().upper()
            if sep and cle_norm in a_ecrire:
                nouvelles_lignes.append(f"{cle.strip()} = {a_ecrire[cle_norm]}")
                mises_a_jour.add(cle_norm)
                continue
        elif stripped:
            cle, sep, _ = ligne.partition("=")
            cle_norm = cle.strip().upper()
            if sep and cle_norm in a_ecrire:
                nouvelles_lignes.append(f"{cle.strip()} = {a_ecrire[cle_norm]}")
                mises_a_jour.add(cle_norm)
                continue
        nouvelles_lignes.append(ligne)

    # Clés absentes du fichier → on les ajoute à la fin.
    manquantes = set(a_ecrire.keys()) - mises_a_jour
    if manquantes:
        nouvelles_lignes.append("")
        for cle in sorted(manquantes):
            nouvelles_lignes.append(f"{cle} = {a_ecrire[cle]}")

    chemin.write_text("\n".join(nouvelles_lignes) + "\n", encoding="utf-8")
    return True, "Configuration enregistrée."


def lister_projets() -> list[Config]:
    """Retourne la liste des projets disponibles (un .conf = un projet)."""
    projets = []
    for chemin in sorted(DOSSIER_SCRIPT.glob("configs/*.conf")):
        try:
            projets.append(charger_config(chemin))
        except SystemExit:
            pass  # config incomplète ou invalide — ignorée silencieusement
    return projets


def projet_par_nom(nom: str) -> Config | None:
    return next((p for p in lister_projets() if p.nom == nom), None)

"""Fonctions liées aux projets du bridge (un fichier .conf = un projet).

Extraites de new_issue.py à l'étape 3 du refactoring modulaire. Regroupe la
liste des projets, la recherche par nom et l'écriture des clés éditables du
.conf. Le lecteur de config est partagé avec watcher.py, à la racine du projet.
"""

import os
import sys
from pathlib import Path

from flask import jsonify, request

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
    "MODELE_CCL", "MOT_DE_PASSE", "FICHIER_CONTEXTE", "COULEUR",
    "DELAI_INACTIVITE_MIN",
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
    """Retourne la liste des projets disponibles (un .conf = un projet).

    charger_config() ne sort (SystemExit) que si un champ REQUIS manque ou qu'un
    entier est mal formé — il ne vérifie JAMAIS que REP_TRAVAIL pointe vers un
    dossier existant. Un projet à périmètre dynamique (PERIMETRE_DYNAMIQUE = true,
    issue #125), dont le REP_TRAVAIL n'est qu'un placeholder remplacé à
    l'exécution par le REPO_CIBLE de l'issue, est donc chargé normalement et ne
    tombe pas à tort dans le `except SystemExit` ci-dessous (réservé aux configs
    réellement invalides)."""
    projets = []
    for chemin in sorted(DOSSIER_SCRIPT.glob("configs/*.conf")):
        try:
            projets.append(charger_config(chemin))
        except SystemExit:
            pass  # config incomplète ou invalide — ignorée silencieusement
    return projets


def projet_par_nom(nom: str) -> Config | None:
    return next((p for p in lister_projets() if p.nom == nom), None)


# ─── Routes Flask : consultation/écriture du .conf d'un projet ─────────────────

def get_config(nom_projet):
    """Retourne les valeurs actuelles du .conf, relues depuis le disque à
    chaque appel (via charger_config) plutôt que depuis l'objet Config en
    mémoire. Ainsi l'onglet Configuration reflète toujours l'état réel du
    fichier, même s'il a été modifié à la main après le démarrage."""
    chemin = DOSSIER_SCRIPT / "configs" / f"{nom_projet}.conf"
    if not chemin.exists():
        return jsonify(erreur="Projet introuvable."), 404
    try:
        cfg = charger_config(chemin)
    except SystemExit as e:
        # charger_config quitte (sys.exit) si un champ requis manque ou
        # qu'un entier est mal formé : on le rattrape pour ne pas tuer
        # le serveur et renvoyer une erreur exploitable côté onglet.
        return jsonify(erreur=f"Config invalide : {e}"), 400
    return jsonify(
        nom            = cfg.nom,
        depot          = cfg.depot,
        rep_travail    = str(cfg.rep_travail),
        perimetre      = cfg.perimetre,
        cmd_backup     = cfg.cmd_backup,
        topic_ntfy     = cfg.topic_ntfy,
        label          = cfg.label,
        intervalle     = cfg.intervalle,
        max_essais     = cfg.max_essais,
        timeout_claude = cfg.timeout_claude,
        script_bip     = str(cfg.script_bip),
        fichier_contexte = cfg.fichier_contexte,
        log_taille_max_mo = cfg.log_taille_max_mo,
        log_archives   = cfg.log_archives,
        modele_ccl     = cfg.modele_ccl,
        couleur        = cfg.couleur,
        delai_inactivite_min = cfg.delai_inactivite_min,
    )


def post_config(nom_projet):
    """Enregistre les clés éditables dans le .conf."""
    data = request.json or {}
    ok, msg = sauvegarder_conf(nom_projet, data)
    return jsonify(succes=ok, message=msg)

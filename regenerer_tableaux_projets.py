#!/usr/bin/env python3
"""regenerer_tableaux_projets.py — Régénère les tableaux §2 « Projets actifs »
et §7 « Périmètre par projet » de BRIDGE_AGENT_DOC.md depuis `configs/*.conf`
(issue #571).

Avant cette issue, ces deux tableaux (plus une 3ᵉ copie dans
REINSTALLATION_CCW.md — volontairement hors périmètre ici, voir plus bas)
étaient maintenus à la main, indépendamment des `configs/*.conf` réellement
lus par `watcher.py`. Toute divergence (création, suppression, renommage
d'un projet oublié dans un des tableaux) pouvait se reproduire — et s'est
reproduite (`testccwprojet`, nettoyé partout ailleurs mais resté visible
dans ces deux tableaux).

Ce script relit `configs/*.conf` sur disque (source de vérité fonctionnelle,
les champs NOM/DEPOT/REP_TRAVAIL/PERIMETRE) et remplace intégralement le
contenu des tableaux entre des marqueurs HTML dédiés dans
BRIDGE_AGENT_DOC.md — jamais d'édition manuelle. Un fichier `.conf` sans
champ NOM (ex. `configs/ccw_ssh.conf`, config technique de connexion SSH,
pas un projet watcher) est ignoré silencieusement. Les projets sont triés
par ordre alphabétique du NOM (l'ordre chronologique d'ajout historique
n'est pas reconstituable depuis le disque).

Deux usages :
  - Automatique : appelé par `nouveau_projet.py` (Flask et CLI) à la fin de
    la création d'un projet, une fois son `.conf` déjà écrit sur disque, et
    par `supprimer_projet.py` (Flask et CLI, issue #587) à la fin de la
    suppression côté CCL/local d'un projet, une fois son `.conf` déjà
    retiré du disque — un seul mécanisme écrit dans ces tableaux, plutôt que
    des copies parallèles de la même logique d'insertion/retrait.
  - À la demande : `python3 regenerer_tableaux_projets.py`, sans argument,
    pour resynchroniser la doc après un nettoyage manuel (`.conf` ajouté ou
    retiré à la main, hors des deux flux ci-dessus).

Le tableau §7 de `provisioning/windows/REINSTALLATION_CCW.md` (sous-ensemble
des projets avec un service CCW Windows dédié) n'est PAS régénéré par ce
script : sa source de vérité déclarée est le tableau `$Projets` de
`reinstaller_projets_ccw.ps1` (issue #552) — un périmètre différent
(présence d'un service Windows dédié, décision manuelle indépendante des
`.conf` Linux), pas dérivable de `configs/*.conf`.
"""

import re
import sys
from datetime import date
from pathlib import Path

from palette import couleur_affichee
from watcher import lire_conf

RACINE = Path(__file__).resolve().parent
DOSSIER_CONFIGS = RACINE / "configs"
DOC = RACINE / "BRIDGE_AGENT_DOC.md"

MOIS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]

MARQUEUR_DEBUT_ACTIFS = "<!-- DEBUT:TABLEAU_PROJETS_ACTIFS"
MARQUEUR_FIN_ACTIFS = "<!-- FIN:TABLEAU_PROJETS_ACTIFS -->"
MARQUEUR_DEBUT_PERIMETRE = "<!-- DEBUT:TABLEAU_PERIMETRE_PROJETS"
MARQUEUR_FIN_PERIMETRE = "<!-- FIN:TABLEAU_PERIMETRE_PROJETS -->"


def lire_projets(dossier_configs: Path = DOSSIER_CONFIGS) -> list[dict]:
    """Scanne configs/*.conf et renvoie la liste des projets (dicts nom/
    depot/rep_travail/perimetre/couleur), triés par nom. Fichiers sans champ
    NOM ignorés (ex. ccw_ssh.conf).

    couleur_affichee vient de palette.py (issue #620) — avant l'extraction,
    elle vivait dans nouveau_projet.py, qui importe déjà ce module (issue
    #571) : un `from nouveau_projet import couleur_affichee` en tête de CE
    fichier créait un cycle, d'où un import local différé (issue #608).
    palette.py n'a aucune dépendance vers ce module, le cycle n'existe plus."""
    projets = []
    for chemin in sorted(dossier_configs.glob("*.conf")):
        brut = lire_conf(chemin)
        nom = brut.get("NOM")
        if not nom:
            continue
        projets.append({
            "nom": nom,
            "depot": brut.get("DEPOT", ""),
            "rep_travail": brut.get("REP_TRAVAIL", ""),
            "perimetre": brut.get("PERIMETRE") or brut.get("REP_TRAVAIL", ""),
            "couleur": couleur_affichee(nom, brut.get("COULEUR", "")),
        })
    projets.sort(key=lambda p: p["nom"])
    return projets


def _afficher_rep(rep: str) -> str:
    """Affiche le répertoire avec le raccourci ~ comme dans la doc existante."""
    home = str(Path.home())
    return rep.replace(home, "~", 1) if rep.startswith(home) else rep


def _lignes_tableau_actifs(projets: list[dict]) -> list[str]:
    # Colonne « Couleur » ajoutée en DERNIÈRE position (issue #608) : ne pas
    # décaler les colonnes existantes, lues par d'autres consommateurs
    # (relecture_web notamment, seule source pour lui — voir le § « Couleur
    # d'accent des projets »).
    lignes = ["| Nom | Dépôt GitHub | Répertoire de travail CCL | Topic ntfy | Couleur |",
              "|-----|-------------|--------------------------|------------|---------|"]
    for p in projets:
        lignes.append(f"| `{p['nom']}` | {p['depot']} | "
                       f"{_afficher_rep(p['rep_travail'])} | (conf local) | `{p['couleur']}` |")
    return lignes


def _lignes_tableau_perimetre(projets: list[dict]) -> list[str]:
    lignes = ["| Projet | Périmètre autorisé |", "|--------|-------------------|"]
    for p in projets:
        lignes.append(f"| `{p['nom']}` | {p['perimetre']} |")
    return lignes


def _remplacer_entre_marqueurs(texte: str, prefixe_debut: str, marqueur_fin: str,
                               nouvelles_lignes: list[str]) -> str:
    """Remplace le contenu entre le commentaire HTML de début (qui peut
    s'étaler sur plusieurs lignes, jusqu'à son '-->' fermant) identifié par
    `prefixe_debut`, et la ligne `marqueur_fin`, par `nouvelles_lignes`."""
    motif = re.compile(re.escape(prefixe_debut) + r".*?-->\n.*?" + re.escape(marqueur_fin),
                        re.DOTALL)
    m = motif.search(texte)
    if not m:
        raise ValueError(f"marqueurs {prefixe_debut!r}/{marqueur_fin!r} introuvables dans {DOC.name}")
    bloc_debut = re.match(re.escape(prefixe_debut) + r".*?-->", m.group(0), re.DOTALL).group(0)
    nouveau_bloc = bloc_debut + "\n" + "\n".join(nouvelles_lignes) + "\n" + marqueur_fin
    return texte[:m.start()] + nouveau_bloc + texte[m.end():]


def _bump_date(texte: str) -> str:
    """Ne touche que la ligne qui COMMENCE par le marqueur (le vrai pied de
    page, en toute fin de fichier) — pas un `re.sub` sur le texte entier, qui
    remonterait d'abord l'exemple donné en §10 (piège documenté, cf. issue
    #268) : `... de page — \\`*Dernière mise à jour : <date> — ...\\`, tiret
    cadratin` ne commence pas par le marqueur mais le contient."""
    aujourd_hui = date.today()
    date_fr = f"{aujourd_hui.day} {MOIS_FR[aujourd_hui.month]} {aujourd_hui.year}"
    lignes = texte.split("\n")
    for i, ligne in enumerate(lignes):
        if ligne.startswith("*Dernière mise à jour :"):
            lignes[i] = re.sub(
                r"(\*Dernière mise à jour : )[^—]*( —)",
                rf"\g<1>{date_fr}\g<2>",
                ligne, count=1,
            )
            break
    return "\n".join(lignes)


def regenerer(doc_path: Path = DOC, dossier_configs: Path = DOSSIER_CONFIGS) -> dict:
    """Régénère les tableaux §2/§7 depuis configs/*.conf. Renvoie
    {existe, modifie, erreur, n_projets, projets}."""
    if not doc_path.exists():
        return {"existe": False, "modifie": False, "erreur": None,
                "n_projets": 0, "projets": []}

    projets = lire_projets(dossier_configs)
    texte = doc_path.read_text(encoding="utf-8")
    original = texte
    try:
        texte = _remplacer_entre_marqueurs(texte, MARQUEUR_DEBUT_ACTIFS,
                                            MARQUEUR_FIN_ACTIFS,
                                            _lignes_tableau_actifs(projets))
        texte = _remplacer_entre_marqueurs(texte, MARQUEUR_DEBUT_PERIMETRE,
                                            MARQUEUR_FIN_PERIMETRE,
                                            _lignes_tableau_perimetre(projets))
    except ValueError as exc:
        return {"existe": True, "modifie": False, "erreur": str(exc),
                "n_projets": len(projets), "projets": projets}

    modifie = texte != original
    if modifie:
        texte = _bump_date(texte)
        doc_path.write_text(texte, encoding="utf-8")

    return {"existe": True, "modifie": modifie, "erreur": None,
            "n_projets": len(projets), "projets": projets}


def main() -> int:
    resultat = regenerer()
    if not resultat["existe"]:
        print(f"⚠️  {DOC.name} introuvable — rien à faire.")
        return 1
    if resultat["erreur"]:
        print(f"⚠️  {resultat['erreur']}")
        return 1
    noms = ", ".join(p["nom"] for p in resultat["projets"])
    print(f"{resultat['n_projets']} projet(s) trouvé(s) dans configs/*.conf : {noms}")
    if resultat["modifie"]:
        print(f"✓ {DOC.name} mis à jour (§2/§7 régénérés).")
    else:
        print(f"= {DOC.name} déjà à jour — aucune modification.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

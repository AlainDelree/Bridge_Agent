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
import subprocess
import sys
from datetime import date
from pathlib import Path

from palette import couleur_affichee
from watcher import lire_conf

RACINE = Path(__file__).resolve().parent
DOSSIER_CONFIGS = RACINE / "configs"
DOC = RACINE / "BRIDGE_AGENT_DOC.md"

# Timeouts (secondes) des appels git de committer_pousser_doc() (issue #645) :
# même logique que TIMEOUT_GIT_LOCAL/TIMEOUT_GIT_PUSH de nouveau_projet.py —
# court pour les opérations locales (diff/add/commit, jamais de réseau), plus
# généreux pour le push (seul appel réseau du lot).
TIMEOUT_GIT_DOC_LOCAL = 15
TIMEOUT_GIT_DOC_PUSH = 60

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


def _git_doc(racine: Path, *args: str,
            timeout: float = TIMEOUT_GIT_DOC_LOCAL) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["git", *args], cwd=racine,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(
            args=["git", *args], returncode=124, stdout="",
            stderr=f"timeout dépassé ({timeout}s)")


def _commande_manuelle_doc(racine: Path, nom_fichier: str, message: str) -> str:
    return (f"cd {racine}\n"
            f"git add {nom_fichier}\n"
            f'git commit -m "{message}"\n'
            f"git push")


def committer_pousser_doc(message: str, doc_path: Path = DOC) -> dict:
    """Commit + push automatique de BRIDGE_AGENT_DOC.md dans le dépôt
    Bridge_Agent (issue #645) : jusqu'ici, `regenerer()` réécrivait bien le
    fichier sur disque après une création/suppression de projet, mais aucun
    des deux flux appelants ne committait ni ne poussait ce changement —
    Alain devait s'en apercevoir lui-même (`git status`) et le faire à la
    main, sans qu'aucun message ne l'y invite clairement.

    Exception documentée à la règle « CCL ne pousse jamais » (même
    raisonnement que le push initial de `initialiser_git()` dans
    nouveau_projet.py, et que la route pièces jointes de app/issues.py) :
    c'est Alain qui déclenche la création/suppression de projet depuis
    l'interface — jamais un agent — donc ce push n'est pas soumis à cette
    règle.

    `git diff --quiet` (sur le fichier seul) est l'AUTORITÉ qui décide s'il y
    a réellement quelque chose à committer, plutôt que de faire confiance au
    `modifie`/`ok2`/`ok7` renvoyé par l'appelant (`mettre_a_jour_doc()`) :
    c'est ici, au plus près du commit réel, qu'on regarde ce que git
    committerait vraiment — un commit vide n'est jamais créé.

    Renvoie {statut, detail, commande_manuelle} avec statut ∈ :
      - "rien_a_faire" : fichier inchangé, rien commité — pas un problème.
      - "ok"           : commité ET poussé sur origin.
      - "push_echoue"  : commité en LOCAL, le push a échoué (réseau, conflit
                         avec origin…) — le commit reste en place, seul le
                         push est à refaire à la main.
      - "echec"        : git lui-même a échoué avant/pendant le commit (cas
                         rare — dépôt absent, index verrouillé…) ; le fichier
                         reste modifié sur disque, non commité.
    `commande_manuelle` n'est renseigné que pour "push_echoue" et "echec"."""
    racine = doc_path.parent
    nom_fichier = doc_path.name

    res_diff = _git_doc(racine, "diff", "--quiet", "--", nom_fichier)
    if res_diff.returncode == 0:
        return {"statut": "rien_a_faire",
                "detail": f"{nom_fichier} inchangé — rien à committer.",
                "commande_manuelle": None}
    if res_diff.returncode != 1:
        return {"statut": "echec",
                "detail": f"échec de git diff : {res_diff.stderr.strip()}",
                "commande_manuelle": _commande_manuelle_doc(racine, nom_fichier, message)}

    res_add = _git_doc(racine, "add", "--", nom_fichier)
    if res_add.returncode != 0:
        return {"statut": "echec",
                "detail": f"échec de git add : {res_add.stderr.strip()}",
                "commande_manuelle": _commande_manuelle_doc(racine, nom_fichier, message)}

    res_commit = _git_doc(racine, "commit", "-m", message)
    if res_commit.returncode != 0:
        return {"statut": "echec",
                "detail": f"échec de git commit : {res_commit.stderr.strip()}",
                "commande_manuelle": _commande_manuelle_doc(racine, nom_fichier, message)}

    res_push = _git_doc(racine, "push", timeout=TIMEOUT_GIT_DOC_PUSH)
    if res_push.returncode == 0:
        return {"statut": "ok",
                "detail": f"{nom_fichier} commité et poussé sur origin.",
                "commande_manuelle": None}

    return {"statut": "push_echoue",
            "detail": f"{nom_fichier} commité en local — push échoué : "
                      f"{res_push.stderr.strip()}",
            "commande_manuelle": f"cd {racine}\ngit push"}


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

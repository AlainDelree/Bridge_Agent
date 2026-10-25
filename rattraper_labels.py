#!/usr/bin/env python3
"""rattraper_labels.py — Rattrapage des labels GitHub manquants sur tous les
dépôts de projets déjà existants (issue #816).

Contexte : depuis cette issue, chaque watcher crée de lui-même les labels
manquants sur SON dépôt au démarrage (voir labels_github.verifier_labels_
demarrage via watcher.py). Mais un watcher qui tourne déjà ne redémarre pas
tout seul quand un label est ajouté au code — ce script applique la même
vérification (labels_github.creer_labels, idempotente) à TOUS les projets
déclarés d'un coup, sans attendre le prochain redémarrage de chaque watcher.

Usage :
    python3 rattraper_labels.py

Parcourt configs/*.conf (hors ccw.conf, canal technique CCW sans projet
propre — et tout fichier sans champ DEPOT, ex. ccw_ssh.conf) et affiche un
tableau par projet. Ne modifie AUCUN `.conf`, ne touche à aucun label déjà
présent sur un dépôt (couleur/description laissées intactes). Zéro
dépendance externe (stdlib + la commande `gh`, déjà authentifiée).
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from labels_github import creer_labels  # noqa: E402
from watcher import lire_conf  # noqa: E402

DOSSIER_CONFIGS = RACINE / "configs"
FICHIER_CCW_UNIFIE = "ccw.conf"  # canal for-windows commun, pas un projet


def lister_projets_a_rattraper(dossier_configs: Path = DOSSIER_CONFIGS) -> list[tuple[str, str]]:
    """Renvoie la liste (nom, depot) des projets déclarés dans
    configs/*.conf, hors ccw.conf et hors tout fichier sans champ DEPOT
    (ex. ccw_ssh.conf, config technique de connexion SSH)."""
    projets = []
    for chemin in sorted(dossier_configs.glob("*.conf")):
        if chemin.name == FICHIER_CCW_UNIFIE:
            continue
        brut = lire_conf(chemin)
        depot = brut.get("DEPOT")
        if not depot:
            continue
        projets.append((brut.get("NOM") or chemin.stem, depot))
    return projets


def _afficher_tableau(nom: str, depot: str, resultats: list[tuple[str | None, str, str]]):
    if len(resultats) == 1 and resultats[0][1] == "illisible":
        raison = resultats[0][2]
        print(f"\n=== {nom} ({depot}) — liste illisible : {raison} ===")
        return
    deja = sum(1 for _n, s, _d in resultats if s == "deja")
    crees = sum(1 for _n, s, _d in resultats if s == "cree")
    echecs = sum(1 for _n, s, _d in resultats if s == "echec")
    print(f"\n=== {nom} ({depot}) — {deja} présent(s), {crees} créé(s), {echecs} en échec ===")
    for label, statut, detail in resultats:
        marque = {"deja": "•", "cree": "✓", "echec": "❌"}[statut]
        ligne = f"  {marque} {label:<16} {statut}"
        if detail:
            ligne += f" ({detail})"
        print(ligne)


def main() -> int:
    if not DOSSIER_CONFIGS.is_dir():
        print(f"❌ Dossier configs/ introuvable ({DOSSIER_CONFIGS}).", file=sys.stderr)
        return 1

    projets = lister_projets_a_rattraper(DOSSIER_CONFIGS)
    if not projets:
        print("Aucun projet déclaré dans configs/*.conf (hors ccw.conf).")
        return 0

    total_crees = 0
    total_echecs = 0
    total_illisibles = 0
    for nom, depot in projets:
        resultats = creer_labels(depot)
        _afficher_tableau(nom, depot, resultats)
        if len(resultats) == 1 and resultats[0][1] == "illisible":
            total_illisibles += 1
            continue
        total_crees += sum(1 for _n, s, _d in resultats if s == "cree")
        total_echecs += sum(1 for _n, s, _d in resultats if s == "echec")

    detail_illisibles = f", {total_illisibles} liste(s) illisible(s)" if total_illisibles else ""
    print(f"\n{len(projets)} projet(s) traité(s) — {total_crees} label(s) créé(s) au total, "
          f"{total_echecs} échec(s){detail_illisibles}.")
    return 1 if total_echecs else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""scripts/archiver_historique.py — archive les entrées anciennes de
`logs/historique_durees.json` vers `logs/historique_durees_archive_<année>.json`.

Contexte : issue #310 — historique_durees.json accumule toutes les entrées
depuis mai 2026 sans purge et grossit à chaque clôture d'issue. Diagnostic
(lecture du code, préalable à ce script) :
  - `maj_calibration_timeout` (EWMA, calibration TIMEOUT réelle, issue #221,
    watcher.py) est purement incrémentale : elle lit/écrit exclusivement
    etat_timeout.json et etat_ambiance.json, JAMAIS historique_durees.json.
    Ce script ne touche donc PAS à la calibration TIMEOUT en cours.
  - `estimer_duree` (app/issues.py, badge de fiabilité à la création d'une
    issue, issue #108) recalcule une médiane à partir de tout l'historique
    transmis, filtré par projet/type/mode. Un archivage réduit le nombre
    d'échantillons disponibles par catégorie ; ce script garantit donc, par
    catégorie, un plancher d'entrées CONSERVÉES (--n-min) au-delà du seuil
    "sûr" (SEUIL_ESTIM_SUR, app/issues.py) pour ne pas dégrader le badge des
    catégories actives.

Fonctionnement : pour chaque combinaison (projet, type, mode), les --n-min
entrées les plus récentes sont TOUJOURS conservées dans historique_durees.json
quelle que soit leur ancienneté. Au-delà de ce plancher, les entrées dont la
date dépasse --seuil-mois sont déplacées vers le fichier d'archive annuel
correspondant (une entrée archivée va dans le fichier de SON année, pas
l'année d'exécution du script). Les entrées à date illisible/absente sont
conservées par prudence (jamais archivées).

Ce script n'est JAMAIS appelé automatiquement par watcher.py — lancement
manuel uniquement, à la discrétion d'Alain.

Usage :
    python3 scripts/archiver_historique.py                    # exécution réelle, défauts
    python3 scripts/archiver_historique.py --dry-run           # simulation, aucune écriture
    python3 scripts/archiver_historique.py --seuil-mois 3 --n-min 25
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

DOSSIER_SCRIPT = Path(__file__).resolve().parent
DOSSIER_LOGS = DOSSIER_SCRIPT.parent / "logs"
FICHIER_HISTORIQUE_DEFAUT = DOSSIER_LOGS / "historique_durees.json"

# Cohérent avec app/issues.py : SEUIL_ESTIM_SUR = 15 (au-dessus : badge "sûr",
# vert). N_MIN_DEFAUT > SEUIL_ESTIM_SUR pour qu'une catégorie déjà "sûre"
# avant archivage le reste après (avec une marge de confort de 5).
N_MIN_DEFAUT = 20


def _parser_date(valeur):
    """Parse le champ 'date' d'une entrée (ISO 8601, avec ou sans fuseau).
    Retourne un datetime aware (UTC) ou None si absent/illisible."""
    if not valeur or not isinstance(valeur, str):
        return None
    try:
        dt = datetime.fromisoformat(valeur)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _seuil_anciennete(mois: int) -> datetime:
    """Date en dessous de laquelle une entrée est éligible à l'archivage
    (maintenant moins `mois` mois, calcul calendaire exact — pas une
    approximation en jours)."""
    maintenant = datetime.now(timezone.utc)
    annee = maintenant.year
    mois_total = maintenant.month - 1 - mois
    annee += mois_total // 12
    mois_cible = mois_total % 12 + 1
    jour = min(maintenant.day, 28)   # évite les débordements de fin de mois (30/31, février)
    return maintenant.replace(year=annee, month=mois_cible, day=jour)


def _categorie(entree: dict) -> tuple:
    return (entree.get("projet"), entree.get("type"), entree.get("mode"))


def _ecrire_json_atomique(chemin: Path, donnees):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    tmp = chemin.with_name(chemin.name + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(donnees, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, chemin)


def archiver(fichier_historique: Path, seuil_mois: int, n_min: int, dry_run: bool) -> dict:
    """Exécute l'archivage. Retourne un rapport structuré (utilisé aussi bien
    pour l'affichage console que pour des tests)."""
    if not fichier_historique.exists():
        return {"erreur": f"fichier introuvable : {fichier_historique}"}

    try:
        historique = json.loads(fichier_historique.read_text(encoding="utf-8")) or []
    except json.JSONDecodeError as e:
        return {"erreur": f"JSON illisible ({fichier_historique}) : {e}"}

    date_seuil = _seuil_anciennete(seuil_mois)

    # Regroupement par catégorie, en conservant l'index d'origine (pour
    # préserver l'ordre relatif des entrées conservées dans le fichier final).
    par_categorie = defaultdict(list)
    for idx, entree in enumerate(historique):
        par_categorie[_categorie(entree)].append((idx, entree, _parser_date(entree.get("date"))))

    indices_a_archiver = set()
    archives_par_annee = defaultdict(list)
    rapport_categories = {}

    for cat, entrees in par_categorie.items():
        # Plus récent en premier ; date illisible/absente traitée comme "la
        # plus récente possible" (jamais archivée, par prudence).
        entrees_triees = sorted(
            entrees,
            key=lambda t: t[2] or datetime.max.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        n_total = len(entrees_triees)
        n_archivees = 0
        for rang, (idx, entree, date_entree) in enumerate(entrees_triees):
            if rang < n_min:
                continue   # plancher de conservation : toujours gardée
            if date_entree is not None and date_entree < date_seuil:
                indices_a_archiver.add(idx)
                annee = date_entree.year
                archives_par_annee[annee].append(entree)
                n_archivees += 1

        n_conservees = n_total - n_archivees
        rapport_categories["|".join(str(c) for c in cat)] = {
            "n_total": n_total,
            "n_archivees": n_archivees,
            "n_conservees": n_conservees,
        }

    historique_conserve = [e for i, e in enumerate(historique) if i not in indices_a_archiver]

    if not dry_run:
        for annee, entrees_annee in archives_par_annee.items():
            fichier_archive = fichier_historique.with_name(
                f"{fichier_historique.stem}_archive_{annee}.json"
            )
            existant = []
            if fichier_archive.exists():
                try:
                    existant = json.loads(fichier_archive.read_text(encoding="utf-8")) or []
                except json.JSONDecodeError:
                    existant = []
            _ecrire_json_atomique(fichier_archive, existant + entrees_annee)

        _ecrire_json_atomique(fichier_historique, historique_conserve)

    return {
        "erreur": None,
        "dry_run": dry_run,
        "seuil_mois": seuil_mois,
        "n_min": n_min,
        "date_seuil": date_seuil.isoformat(),
        "n_total_avant": len(historique),
        "n_total_archivees": sum(v["n_archivees"] for v in rapport_categories.values()),
        "n_total_conservees": len(historique_conserve),
        "annees_archivees": sorted(archives_par_annee.keys()),
        "categories": rapport_categories,
    }


def _afficher_rapport(rapport: dict, n_min: int):
    if rapport.get("erreur"):
        print(f"ERREUR : {rapport['erreur']}", file=sys.stderr)
        return 1

    mode = "SIMULATION (--dry-run, aucune écriture)" if rapport["dry_run"] else "EXÉCUTION RÉELLE"
    print(f"=== Archivage historique_durees.json — {mode} ===")
    print(f"Seuil d'ancienneté : {rapport['seuil_mois']} mois (avant {rapport['date_seuil']})")
    print(f"Plancher de conservation par catégorie : {rapport['n_min']} entrées les plus récentes")
    print()
    print(f"{'catégorie (projet|type|mode)':<45} {'total':>7} {'archivées':>10} {'conservées':>11} fiabilité")
    for cat, stats in sorted(rapport["categories"].items()):
        alerte = ""
        if stats["n_conservees"] <= 15 and stats["n_total"] > 15:
            alerte = "  <-- ATTENTION : catégorie repassée sous le seuil 'sûr' (15)"
        elif stats["n_archivees"] > 0 and stats["n_conservees"] < n_min:
            alerte = "  <-- ATTENTION : conservées < n-min"
        print(f"{cat:<45} {stats['n_total']:>7} {stats['n_archivees']:>10} {stats['n_conservees']:>11}{alerte}")
    print()
    print(f"Total avant  : {rapport['n_total_avant']} entrées")
    print(f"Archivées    : {rapport['n_total_archivees']} entrées "
          f"(années : {', '.join(str(a) for a in rapport['annees_archivees']) or 'aucune'})")
    print(f"Conservées   : {rapport['n_total_conservees']} entrées")
    print()
    print("etat_timeout.json et etat_ambiance.json : non touchés (hors périmètre de ce script).")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Archive les entrées anciennes de logs/historique_durees.json "
                     "(lancement manuel uniquement, jamais appelé par watcher.py)."
    )
    parser.add_argument("--fichier", type=Path, default=FICHIER_HISTORIQUE_DEFAUT,
                         help=f"chemin de historique_durees.json (défaut : {FICHIER_HISTORIQUE_DEFAUT})")
    parser.add_argument("--seuil-mois", type=int, default=6,
                         help="ancienneté (mois) au-delà de laquelle une entrée est éligible à l'archivage (défaut : 6)")
    parser.add_argument("--n-min", type=int, default=N_MIN_DEFAUT,
                         help=f"nombre minimum d'entrées les plus récentes conservées par catégorie, "
                              f"quelle que soit leur ancienneté (défaut : {N_MIN_DEFAUT})")
    parser.add_argument("--dry-run", action="store_true",
                         help="simule et affiche le rapport sans rien écrire sur disque")
    args = parser.parse_args()

    rapport = archiver(args.fichier, args.seuil_mois, args.n_min, args.dry_run)
    sys.exit(_afficher_rapport(rapport, args.n_min))


if __name__ == "__main__":
    main()

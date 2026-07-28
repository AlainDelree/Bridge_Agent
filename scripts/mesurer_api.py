#!/usr/bin/env python3
"""scripts/mesurer_api.py — échantillonne `gh api rate_limit` à intervalle
régulier et journalise la consommation GraphQL/REST dans un CSV.

Contexte : issue #263 (épuisement du quota GraphQL le 28/07 vers 3h — mesurer
et attribuer la consommation par composant, sans rien corriger). Méthode
complète et résultats : BRIDGE_AGENT_DOC.md §13.

Usage :
    python3 scripts/mesurer_api.py --intervalle 30 --duree 600
    python3 scripts/mesurer_api.py --intervalle 15 --duree 0 --note phase_B   # illimité, Ctrl+C pour arrêter

`gh api rate_limit` est un appel REST qui ne consomme NI le quota `core` NI
le quota `graphql` (vérifié empiriquement — voir rapport issue #263) : la
mesure elle-même ne fausse donc pas le résultat, quel que soit l'intervalle
choisi. L'intervalle par défaut (30s) est un compromis résolution/bruit, pas
une contrainte de quota.
"""
import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

DOSSIER_SCRIPT = Path(__file__).resolve().parent
FICHIER_CSV_DEFAUT = DOSSIER_SCRIPT.parent / "logs" / "mesure_api.csv"

ENTETES = [
    "horodatage", "note",
    "graphql_used", "graphql_remaining", "delta_graphql_used",
    "core_used", "core_remaining", "delta_core_used",
]


def echantillon():
    """Un appel `gh api rate_limit` ; retourne (gql_used, gql_remaining, core_used, core_remaining)."""
    res = subprocess.run(
        ["gh", "api", "rate_limit"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(f"gh api rate_limit a échoué : {res.stderr.strip()}")
    data = json.loads(res.stdout)
    gql = data["resources"]["graphql"]
    core = data["resources"]["core"]
    return gql["used"], gql["remaining"], core["used"], core["remaining"]


def main():
    parser = argparse.ArgumentParser(
        description="Échantillonne gh api rate_limit à intervalle régulier et journalise dans un CSV (issue #263)."
    )
    parser.add_argument("--intervalle", type=int, default=30,
                         help="secondes entre deux échantillons (défaut 30)")
    parser.add_argument("--duree", type=int, default=0,
                         help="durée totale en secondes ; 0 = illimité, arrêt par Ctrl+C (défaut 0)")
    parser.add_argument("--sortie", type=Path, default=FICHIER_CSV_DEFAUT,
                         help=f"fichier CSV de sortie (défaut {FICHIER_CSV_DEFAUT})")
    parser.add_argument("--note", default="",
                         help="étiquette libre ajoutée à chaque ligne (ex. nom de phase A/B/C/D)")
    args = parser.parse_args()

    args.sortie.parent.mkdir(parents=True, exist_ok=True)
    nouveau_fichier = not args.sortie.exists() or args.sortie.stat().st_size == 0

    f = open(args.sortie, "a", newline="", encoding="utf-8")
    writer = csv.writer(f)
    if nouveau_fichier:
        writer.writerow(ENTETES)
        f.flush()

    print(f"Échantillonnage toutes les {args.intervalle}s"
          + (f", pendant {args.duree}s" if args.duree > 0 else ", illimité (Ctrl+C pour arrêter)")
          + f" — sortie : {args.sortie}")

    precedent_gql = None
    precedent_core = None
    debut = time.monotonic()
    n = 0
    try:
        while True:
            gql_used, gql_remaining, core_used, core_remaining = echantillon()
            delta_gql = "" if precedent_gql is None else gql_used - precedent_gql
            delta_core = "" if precedent_core is None else core_used - precedent_core
            horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
            writer.writerow([horodatage, args.note,
                              gql_used, gql_remaining, delta_gql,
                              core_used, core_remaining, delta_core])
            f.flush()
            n += 1
            precedent_gql, precedent_core = gql_used, core_used
            print(f"[{horodatage}] graphql.used={gql_used} (Δ{delta_gql}) "
                  f"remaining={gql_remaining} — core.used={core_used} (Δ{delta_core})")

            if args.duree > 0 and (time.monotonic() - debut) >= args.duree:
                break
            time.sleep(args.intervalle)
    except KeyboardInterrupt:
        print("\nInterrompu (Ctrl+C) — données déjà écrites conservées.")
    finally:
        f.close()

    print(f"Terminé — {n} échantillon(s) écrit(s) dans {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

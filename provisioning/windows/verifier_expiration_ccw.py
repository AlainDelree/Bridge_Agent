#!/usr/bin/env python3
"""Vérifie combien de jours restent avant l'expiration de l'évaluation 90 jours
de la VM Windows CCW-Build (côté Linux/CCL).

Lit provisioning/windows/eval-expiration.json, recalcule la date d'expiration à
partir de `date_installation` + `eval_jours` (la clé `date_expiration` du fichier
n'est qu'informative), puis :

  - si SEUIL_ALERTE jours ou moins restent (ou si déjà expiré), imprime un
    avertissement clair et sort avec un code NON NUL (2), pour permettre une
    intégration ultérieure à une vérification automatisée (cron + ntfy, cf.
    BRIDGE_AGENT_DOC.md §16 / issue #167) ;
  - sinon, confirme calmement le nombre de jours restants et sort avec 0.

Aucune dépendance externe (bibliothèque standard uniquement).

Usage :
    python3 provisioning/windows/verifier_expiration_ccw.py
    python3 provisioning/windows/verifier_expiration_ccw.py --seuil 15
"""

import argparse
import json
import sys
from datetime import date, timedelta
from pathlib import Path

SEUIL_ALERTE_DEFAUT = 10  # jours restants à partir desquels on alerte

# Le fichier de métadonnées est à côté de ce script.
FICHIER_META = Path(__file__).resolve().parent / "eval-expiration.json"

# Codes de sortie
OK = 0
ALERTE = 2
ERREUR = 3


def charger_meta(chemin: Path) -> dict:
    """Lit et valide le fichier de métadonnées."""
    if not chemin.exists():
        print(f"❌ Fichier de métadonnées introuvable : {chemin}", file=sys.stderr)
        sys.exit(ERREUR)
    try:
        with chemin.open(encoding="utf-8") as f:
            meta = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"❌ Impossible de lire {chemin} : {e}", file=sys.stderr)
        sys.exit(ERREUR)

    for cle in ("date_installation", "eval_jours"):
        if cle not in meta:
            print(f"❌ Clé « {cle} » absente de {chemin}", file=sys.stderr)
            sys.exit(ERREUR)
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Vérifie les jours restants avant expiration de l'éval Windows CCW.")
    parser.add_argument(
        "--seuil", type=int, default=SEUIL_ALERTE_DEFAUT,
        help=f"Seuil d'alerte en jours restants (défaut : {SEUIL_ALERTE_DEFAUT}).")
    args = parser.parse_args()

    meta = charger_meta(FICHIER_META)

    try:
        date_install = date.fromisoformat(str(meta["date_installation"]))
    except ValueError as e:
        print(f"❌ date_installation invalide (attendu AAAA-MM-JJ) : {e}", file=sys.stderr)
        return ERREUR
    try:
        eval_jours = int(meta["eval_jours"])
    except (TypeError, ValueError):
        print(f"❌ eval_jours invalide (attendu un entier) : {meta['eval_jours']!r}",
              file=sys.stderr)
        return ERREUR

    date_expiration = date_install + timedelta(days=eval_jours)
    jours_restants = (date_expiration - date.today()).days

    entete = (f"VM CCW-Build — éval {eval_jours} j — installée le "
              f"{date_install.isoformat()} — expire le {date_expiration.isoformat()}")

    if jours_restants < 0:
        print(f"⚠️  {entete}")
        print(f"⚠️  ÉVALUATION EXPIRÉE depuis {-jours_restants} jour(s) !")
        print("    Windows redémarre désormais toutes les heures et casse le service")
        print("    CCW-Watcher. Recréer la VM sans tarder :")
        print("        python3 provisioning/windows/creer_vm_ccw.py --recreate")
        return ALERTE

    if jours_restants <= args.seuil:
        print(f"⚠️  {entete}")
        print(f"⚠️  Plus que {jours_restants} jour(s) avant expiration (seuil : {args.seuil}) !")
        print("    Prévoir la recréation de la VM avant expiration :")
        print("        python3 provisioning/windows/creer_vm_ccw.py --recreate")
        return ALERTE

    print(f"✅ {entete}")
    print(f"✅ Il reste {jours_restants} jour(s) avant expiration — rien à faire "
          f"(alerte à partir de {args.seuil} j).")
    return OK


if __name__ == "__main__":
    sys.exit(main())

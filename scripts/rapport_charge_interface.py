#!/usr/bin/env python3
"""scripts/rapport_charge_interface.py — rapport en LECTURE SEULE du journal
de charge de l'interface web (issue #835, point 5) : logs/charge_interface.log
et ses archives de rotation (logs/charge_interface.log.<horodatage>, voir
JournalRotatifDate dans watcher.py).

Par jour (regroupement sur la date UTC de l'horodatage, puisque
mesure_charge_interface.horodatage() écrit en UTC) :
  - nombre d'échantillons (une ligne de type "echantillon" par minute,
    voir mesure_charge_interface.py) ;
  - processeur serveur moyen, pic et 95e centile PAR MINUTE, en pourcentage
    d'un cœur (cpu_s de l'échantillon / 60s — un échantillon couvrant
    nominalement une minute ; un dépassement notable de 100% signale
    plusieurs cœurs sollicités en parallèle, pas une anomalie en soi) ;
  - nombre total de requêtes HTTP et la route la plus lente du jour (gabarit
    Flask, jamais une URL résolue — voir app/charge_interface.py) ;
  - pour les séries de préparations de la page (lignes "resume_precharge") :
    leur nombre, leur durée médiane et maximale, et le nombre moyen de
    requêtes réseau par série.

CHOIX DOCUMENTÉ : « les N derniers jours » (argument --jours, défaut 7)
désigne les N journées les plus RÉCENTES PRÉSENTES DANS LE JOURNAL, pas les N
derniers jours calendaires à l'instant où le rapport tourne — un serveur
resté éteint une semaine produirait sinon un rapport vide alors que les
données existent. À signaler si ce choix ne convient pas.

N'écrit jamais rien, ne modifie aucun fichier.

Usage :
    python3 scripts/rapport_charge_interface.py
    python3 scripts/rapport_charge_interface.py --jours 14
    python3 scripts/rapport_charge_interface.py --fichier logs/charge_interface.log
"""

import argparse
import glob
import json
import sys
from pathlib import Path
from statistics import median

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DOSSIER_SCRIPT))

CHEMIN_DEFAUT = DOSSIER_SCRIPT / "logs" / "charge_interface.log"
INTERVALLE_ECHANTILLON_S = 60   # voir mesure_charge_interface.INTERVALLE_ECHANTILLON_S


def lire_journal_et_archives(chemin: Path) -> list:
    """Lignes du fichier actif PUIS de ses archives de rotation
    (chemin.log.<horodatage>, voir JournalRotatifDate) — l'ordre entre
    fichiers n'a pas d'importance, le regroupement par jour se fait sur le
    champ `horodatage` de chaque ligne, pas sur l'ordre de lecture. Fichier
    absent → liste vide (pas d'exception)."""
    lignes = []
    if chemin.exists():
        lignes.extend(chemin.read_text(encoding="utf-8").splitlines())
    for archive in sorted(glob.glob(str(chemin) + ".*")):
        lignes.extend(Path(archive).read_text(encoding="utf-8").splitlines())
    return lignes


def parser_lignes(lignes: list) -> list:
    """Parse chaque ligne en JSON, en ignorant SILENCIEUSEMENT toute ligne
    malformée (jamais d'exception sur un journal partiellement corrompu) —
    pure, testable sans fichier."""
    sortie = []
    for ligne in lignes:
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            data = json.loads(ligne)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(data, dict) and data.get("type") in ("echantillon", "resume_precharge"):
            sortie.append(data)
    return sortie


def _jour(horodatage: str) -> str:
    """Date UTC (YYYY-MM-DD) extraite d'un horodatage ISO — les 10 premiers
    caractères suffisent (format produit par mesure_charge_interface.horodatage,
    toujours YYYY-MM-DDTHH:MM:SS+00:00)."""
    return (horodatage or "")[:10]


def centile(valeurs: list, p: float) -> float:
    """p-ième centile (0-100) par interpolation linéaire (méthode usuelle,
    équivalente à numpy.percentile par défaut) — pure, sans dépendance
    externe. Liste vide → 0.0 ; un seul élément → cet élément."""
    if not valeurs:
        return 0.0
    valeurs = sorted(valeurs)
    if len(valeurs) == 1:
        return valeurs[0]
    rang = (p / 100) * (len(valeurs) - 1)
    bas = int(rang)
    haut = min(bas + 1, len(valeurs) - 1)
    frac = rang - bas
    return valeurs[bas] + (valeurs[haut] - valeurs[bas]) * frac


def calculer_rapport(donnees: list, nb_jours: int = 7) -> dict:
    """{ jour: {...stats...} }, limité aux `nb_jours` journées les plus
    RÉCENTES PRÉSENTES dans `donnees` (voir choix documenté en tête de
    fichier) — pure, testable sans fichier ni horloge."""
    par_jour = {}
    for d in donnees:
        jour = _jour(d.get("horodatage"))
        if not jour:
            continue
        par_jour.setdefault(jour, {"echantillons": [], "resumes": []})
        if d["type"] == "echantillon":
            par_jour[jour]["echantillons"].append(d)
        else:
            par_jour[jour]["resumes"].append(d)

    jours_retenus = sorted(par_jour.keys(), reverse=True)[:nb_jours] if nb_jours else sorted(par_jour.keys())

    rapport = {}
    for jour in sorted(jours_retenus):
        echantillons = par_jour[jour]["echantillons"]
        resumes = par_jour[jour]["resumes"]
        pourcentages = [100 * e.get("cpu_s", 0.0) / INTERVALLE_ECHANTILLON_S for e in echantillons]
        nb_requetes_total = sum(e.get("nb_requetes", 0) for e in echantillons)
        route_plus_lente, duree_route_plus_lente = None, 0.0
        for e in echantillons:
            d = e.get("duree_max_s", 0.0) or 0.0
            if e.get("route_plus_lente") and d >= duree_route_plus_lente:
                route_plus_lente, duree_route_plus_lente = e["route_plus_lente"], d

        durees_resume = [r.get("duree_totale_ms", 0.0) for r in resumes]
        durees_max_resume = [r.get("duree_max_ms", 0.0) for r in resumes]
        requetes_resume = [r.get("nb_requetes", 0) for r in resumes]

        rapport[jour] = {
            "nb_echantillons": len(echantillons),
            "cpu_moyen_pct": (sum(pourcentages) / len(pourcentages)) if pourcentages else 0.0,
            "cpu_pic_pct": max(pourcentages) if pourcentages else 0.0,
            "cpu_p95_pct": centile(pourcentages, 95),
            "nb_requetes_total": nb_requetes_total,
            "route_plus_lente": route_plus_lente,
            "duree_route_plus_lente_s": duree_route_plus_lente,
            "nb_series_precharge": len(resumes),
            "duree_mediane_serie_ms": median(durees_resume) if durees_resume else 0.0,
            "duree_max_serie_ms": max(durees_max_resume) if durees_max_resume else 0.0,
            "nb_requetes_moyen_serie": (sum(requetes_resume) / len(requetes_resume)) if requetes_resume else 0.0,
        }
    return rapport


def afficher(rapport: dict) -> None:
    if not rapport:
        print("Aucun échantillon ni résumé de précharge dans ce journal.")
        return
    for jour in sorted(rapport.keys()):
        s = rapport[jour]
        print(f"\n{jour}")
        print(f"  Échantillons serveur     : {s['nb_echantillons']}")
        print(f"  CPU moyen / pic / p95    : {s['cpu_moyen_pct']:.1f}% / "
              f"{s['cpu_pic_pct']:.1f}% / {s['cpu_p95_pct']:.1f}% (d'un cœur)")
        print(f"  Requêtes totales         : {s['nb_requetes_total']}")
        if s["route_plus_lente"]:
            print(f"  Route la plus lente      : {s['route_plus_lente']} "
                  f"({s['duree_route_plus_lente_s']:.3f}s)")
        else:
            print("  Route la plus lente      : (aucune requête)")
        print(f"  Séries de précharge      : {s['nb_series_precharge']}")
        if s["nb_series_precharge"]:
            print(f"  Durée médiane / max série: {s['duree_mediane_serie_ms']:.0f}ms / "
                  f"{s['duree_max_serie_ms']:.0f}ms")
            print(f"  Requêtes moyennes / série: {s['nb_requetes_moyen_serie']:.1f}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                      formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fichier", default=str(CHEMIN_DEFAUT),
                         help="Chemin de logs/charge_interface.log (défaut : celui du projet).")
    parser.add_argument("--jours", type=int, default=7,
                         help="Limite le rapport aux N journées les plus récentes PRÉSENTES "
                              "dans le journal (défaut : 7 ; 0 = tout l'historique).")
    args = parser.parse_args()

    chemin = Path(args.fichier)
    lignes = lire_journal_et_archives(chemin)
    if not lignes:
        print(f"Aucun journal de charge trouvé ({chemin} ni ses archives).")
        return 0

    donnees = parser_lignes(lignes)
    afficher(calculer_rapport(donnees, args.jours))
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Tests du rapport de charge de l'interface web (issue #835, point 5) :
scripts/rapport_charge_interface.py, sur un journal SYNTHÉTIQUE écrit dans un
dossier temporaire (aucune écriture dans le dépôt, aucun accès réseau).

Exécution :  python3 tests/test_rapport_charge_interface_835.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import scripts.rapport_charge_interface as rci  # noqa: E402

SCRIPT = RACINE / "scripts" / "rapport_charge_interface.py"


def _echantillon(horodatage, cpu_s, nb_requetes, duree_totale_s, duree_max_s, route):
    return json.dumps({
        "type": "echantillon", "horodatage": horodatage, "cpu_s": cpu_s,
        "nb_requetes": nb_requetes, "duree_totale_s": duree_totale_s,
        "duree_max_s": duree_max_s, "route_plus_lente": route,
    })


def _resume(horodatage, nb_issues, nb_requetes, duree_totale_ms, duree_max_ms, mode):
    return json.dumps({
        "type": "resume_precharge", "horodatage": horodatage,
        "nb_issues_preparees": nb_issues, "nb_requetes": nb_requetes,
        "duree_totale_ms": duree_totale_ms, "duree_max_ms": duree_max_ms, "mode": mode,
    })


def scenario_parser_lignes_ignore_malformees():
    lignes = [
        "pas du json du tout",
        "{}",
        '{"type": "autre_chose"}',
        _echantillon("2026-10-30T10:00:00+00:00", 6.0, 1, 0.1, 0.1, "/x"),
        "",
        "   ",
    ]
    data = rci.parser_lignes(lignes)
    assert len(data) == 1, data
    assert data[0]["type"] == "echantillon"


def scenario_centile_pur():
    assert rci.centile([], 95) == 0.0
    assert rci.centile([42.0], 95) == 42.0
    # 0,10,20,...,100 : p95 = 95e rang interpolé → 95.0 (11 valeurs, pas de 10).
    valeurs = [float(i) for i in range(0, 101, 10)]
    assert abs(rci.centile(valeurs, 95) - 95.0) < 1e-9, rci.centile(valeurs, 95)
    assert rci.centile(valeurs, 0) == 0.0
    assert rci.centile(valeurs, 100) == 100.0


def _journal_deux_jours():
    """Jour A (2026-10-30) : 2 échantillons (cpu 12s et 30s/minute → 20% et
    50% d'un cœur), 2 séries de précharge. Jour B (2026-10-31) : 1
    échantillon, 0 série. Valeurs choisies pour un calcul à la main simple."""
    return [
        _echantillon("2026-10-30T10:00:00+00:00", 12.0, 10, 1.0, 0.30, "/issue/<nom_projet>/<numero>"),
        _echantillon("2026-10-30T10:01:00+00:00", 30.0, 5, 0.5, 0.80, "/rate-limit"),
        _resume("2026-10-30T10:00:10+00:00", 2, 4, 800.0, 500.0, "moderne"),
        _resume("2026-10-30T10:01:10+00:00", 4, 8, 1200.0, 700.0, "moderne"),
        _echantillon("2026-10-31T09:00:00+00:00", 6.0, 2, 0.2, 0.05, "/journal/<nom_projet>"),
    ]


def scenario_calculer_rapport_agregats_exacts():
    donnees = rci.parser_lignes(_journal_deux_jours())
    rapport = rci.calculer_rapport(donnees, nb_jours=7)
    assert set(rapport.keys()) == {"2026-10-30", "2026-10-31"}, rapport.keys()

    jour_a = rapport["2026-10-30"]
    assert jour_a["nb_echantillons"] == 2
    assert abs(jour_a["cpu_moyen_pct"] - 35.0) < 1e-9, jour_a["cpu_moyen_pct"]   # (20+50)/2
    assert abs(jour_a["cpu_pic_pct"] - 50.0) < 1e-9
    assert jour_a["nb_requetes_total"] == 15
    # La route la plus lente du jour est celle de la ligne au duree_max_s le
    # plus élevé (0.80s, /rate-limit), pas la première rencontrée.
    assert jour_a["route_plus_lente"] == "/rate-limit", jour_a["route_plus_lente"]
    assert abs(jour_a["duree_route_plus_lente_s"] - 0.80) < 1e-9
    assert jour_a["nb_series_precharge"] == 2
    assert abs(jour_a["duree_mediane_serie_ms"] - 1000.0) < 1e-9   # médiane de [800, 1200]
    assert abs(jour_a["duree_max_serie_ms"] - 700.0) < 1e-9        # max de [500, 700]
    assert abs(jour_a["nb_requetes_moyen_serie"] - 6.0) < 1e-9     # (4+8)/2

    jour_b = rapport["2026-10-31"]
    assert jour_b["nb_echantillons"] == 1
    assert jour_b["nb_series_precharge"] == 0
    assert jour_b["duree_mediane_serie_ms"] == 0.0
    assert jour_b["route_plus_lente"] == "/journal/<nom_projet>"


def scenario_argument_jours_limite_aux_plus_recents():
    """Un journal de 3 jours distincts, --jours 2 → ne garde que les 2
    journées les plus RÉCENTES présentes (pas calées sur l'horloge réelle)."""
    lignes = [
        _echantillon("2026-10-29T08:00:00+00:00", 6.0, 1, 0.1, 0.1, "/a"),
        _echantillon("2026-10-30T08:00:00+00:00", 6.0, 1, 0.1, 0.1, "/b"),
        _echantillon("2026-10-31T08:00:00+00:00", 6.0, 1, 0.1, 0.1, "/c"),
    ]
    donnees = rci.parser_lignes(lignes)
    rapport = rci.calculer_rapport(donnees, nb_jours=2)
    assert set(rapport.keys()) == {"2026-10-30", "2026-10-31"}, rapport.keys()

    rapport_tout = rci.calculer_rapport(donnees, nb_jours=0)
    assert set(rapport_tout.keys()) == {"2026-10-29", "2026-10-30", "2026-10-31"}


def scenario_lire_journal_et_archives_inclut_les_rotations():
    with tempfile.TemporaryDirectory() as d:
        base = Path(d) / "charge_interface.log"
        base.write_text(_echantillon("2026-10-31T08:00:00+00:00", 6.0, 1, 0.1, 0.1, "/actif") + "\n",
                         encoding="utf-8")
        archive = Path(d) / "charge_interface.log.2026_10_30_00_00"
        archive.write_text(_echantillon("2026-10-30T08:00:00+00:00", 6.0, 1, 0.1, 0.1, "/archive") + "\n",
                            encoding="utf-8")
        lignes = rci.lire_journal_et_archives(base)
        assert len(lignes) == 2, lignes
        donnees = rci.parser_lignes(lignes)
        assert {d["route_plus_lente"] for d in donnees} == {"/actif", "/archive"}


def scenario_cli_journal_absent_message_clair():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        rep = subprocess.run(
            [sys.executable, str(SCRIPT), "--fichier", str(chemin)],
            capture_output=True, text=True, cwd=str(RACINE))
        assert rep.returncode == 0, rep.stderr
        assert "Aucun journal" in rep.stdout, rep.stdout


def scenario_cli_sortie_affiche_jours_et_statistiques():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        chemin.write_text("\n".join(_journal_deux_jours()) + "\n", encoding="utf-8")
        rep = subprocess.run(
            [sys.executable, str(SCRIPT), "--fichier", str(chemin), "--jours", "7"],
            capture_output=True, text=True, cwd=str(RACINE))
        assert rep.returncode == 0, rep.stderr
        assert "2026-10-30" in rep.stdout
        assert "2026-10-31" in rep.stdout
        assert "/rate-limit" in rep.stdout


def main():
    tests = [
        ("parser_lignes : ignore les lignes malformées/autres types",
         scenario_parser_lignes_ignore_malformees),
        ("centile : cas vide/unique/valeurs connues",
         scenario_centile_pur),
        ("calculer_rapport : agrégats exacts par jour",
         scenario_calculer_rapport_agregats_exacts),
        ("--jours : limite aux journées les plus récentes présentes",
         scenario_argument_jours_limite_aux_plus_recents),
        ("lire_journal_et_archives : inclut les fichiers de rotation",
         scenario_lire_journal_et_archives_inclut_les_rotations),
        ("CLI : journal absent → message clair, code 0",
         scenario_cli_journal_absent_message_clair),
        ("CLI : sortie affiche les jours et leurs statistiques",
         scenario_cli_sortie_affiche_jours_et_statistiques),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

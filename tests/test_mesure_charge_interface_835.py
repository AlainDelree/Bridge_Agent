#!/usr/bin/env python3
"""Tests de l'échantillonneur continu de charge de l'interface web (issue
#835, points 3 et 4) : mesure_charge_interface.py (indépendant de Flask) et
app/charge_interface.py (crochets before_request/after_request, route
/mesure-precharge).

Aucun accès réseau réel (test_client() de Flask, pile WSGI in-process) et
aucune écriture dans le dépôt : chaque scénario qui écrit un journal le fait
dans un dossier temporaire (tempfile.TemporaryDirectory), jamais dans
logs/charge_interface.log.

Exécution :  python3 tests/test_mesure_charge_interface_835.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import logging
import sys
import tempfile
import threading
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import mesure_charge_interface as mci  # noqa: E402
from app import create_app  # noqa: E402
from app import charge_interface as ci  # noqa: E402


def _app():
    app = create_app()
    app.config["TESTING"] = True
    return app


def _journal_temporaire(chemin):
    """Réinitialise le logger nommé module-level pour qu'il écrive dans
    `chemin` (dossier temporaire) plutôt que logs/charge_interface.log —
    logging.getLogger(nom) renvoie le MÊME objet logger entre deux scénarios,
    qui garderait sinon son handler (donc son fichier) du scénario précédent."""
    logger = logging.getLogger("bridge_agent.charge_interface")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    mci._logger = None
    return mock.patch.object(mci, "FICHIER_JOURNAL", chemin)


def _reset_compteurs():
    mci.relever_et_remettre_a_zero()


# ─── mesure_charge_interface.py : logique pure ───────────────────────────────

def scenario_differences_cpu():
    """Secondes de processeur = somme (utilisateur+système) propre ET enfants,
    entre deux échantillons — jamais la valeur absolue d'un seul."""
    Avant = type("T", (), {})()
    Avant.user, Avant.system, Avant.children_user, Avant.children_system = 10.0, 2.0, 1.0, 0.5
    Apres = type("T", (), {})()
    Apres.user, Apres.system, Apres.children_user, Apres.children_system = 10.5, 2.2, 1.3, 0.5
    cpu_s = mci.differences_cpu(Avant, Apres)
    assert abs(cpu_s - (0.5 + 0.2 + 0.3 + 0.0)) < 1e-9, cpu_s


def scenario_ligne_echantillon_format_sans_fuite():
    """La ligne est un JSON valide avec EXACTEMENT les champs attendus —
    aucun titre, numéro d'issue ni secret ne peut s'y trouver puisqu'aucun
    de ces champs n'existe dans la fonction."""
    ligne = mci.ligne_echantillon("2026-11-01T10:00:00+00:00", 0.42, 7, 1.23, 0.5, "/issue/<nom_projet>/<numero>")
    data = json.loads(ligne)
    assert data == {
        "type": "echantillon",
        "horodatage": "2026-11-01T10:00:00+00:00",
        "cpu_s": 0.42,
        "nb_requetes": 7,
        "duree_totale_s": 1.23,
        "duree_max_s": 0.5,
        "route_plus_lente": "/issue/<nom_projet>/<numero>",
    }, data
    assert set(data.keys()) == {"type", "horodatage", "cpu_s", "nb_requetes",
                                 "duree_totale_s", "duree_max_s", "route_plus_lente"}


def scenario_ligne_resume_format_sans_fuite():
    ligne = mci.ligne_resume_precharge("2026-11-01T10:00:00+00:00", 3, 5, 820.0, 410.0, "moderne")
    data = json.loads(ligne)
    assert data == {
        "type": "resume_precharge",
        "horodatage": "2026-11-01T10:00:00+00:00",
        "nb_issues_preparees": 3,
        "nb_requetes": 5,
        "duree_totale_ms": 820.0,
        "duree_max_ms": 410.0,
        "mode": "moderne",
    }, data


def scenario_enregistrer_requete_route_la_plus_lente():
    _reset_compteurs()
    mci.enregistrer_requete("/a", 0.01)
    mci.enregistrer_requete("/b", 0.5)
    mci.enregistrer_requete("/c", 0.2)
    nb, total, maxi, route = mci.relever_et_remettre_a_zero()
    assert nb == 3, nb
    assert abs(total - 0.71) < 1e-9, total
    assert abs(maxi - 0.5) < 1e-9, maxi
    assert route == "/b", route
    # Remise à zéro effective.
    nb2, total2, maxi2, route2 = mci.relever_et_remettre_a_zero()
    assert (nb2, total2, maxi2, route2) == (0, 0.0, 0.0, None)


def scenario_enregistrer_requete_thread_safe():
    """Compteurs protégés par verrou (issue #835 point 3, serveur
    threaded=True) : N threads x M appels concurrents ne doivent perdre
    aucun incrément."""
    _reset_compteurs()
    nb_threads, nb_appels = 20, 200

    def travail():
        for _ in range(nb_appels):
            mci.enregistrer_requete("/concurrent", 0.001)

    threads = [threading.Thread(target=travail) for _ in range(nb_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    nb, total, _maxi, _route = mci.relever_et_remettre_a_zero()
    assert nb == nb_threads * nb_appels, f"attendu {nb_threads * nb_appels}, obtenu {nb}"
    assert abs(total - nb_threads * nb_appels * 0.001) < 1e-6, total


def scenario_ecrire_ligne_et_rotation():
    """ecrire_ligne() écrit bien dans le fichier choisi ; une rotation par
    taille produit une archive (réutilise JournalRotatifDate de watcher.py,
    déjà testée ailleurs — ici on vérifie seulement le branchement)."""
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin), mock.patch.object(mci, "TAILLE_MAX_OCTETS", 200):
            for i in range(50):
                mci.ecrire_ligne(mci.ligne_echantillon(
                    "2026-11-01T10:00:00+00:00", 0.1, i, 1.0, 0.5, "/une-route"))
            assert chemin.exists(), "le fichier actif doit exister"
            archives = list(Path(d).glob("charge_interface.log.*"))
            assert archives, "au moins une archive de rotation attendue avec un seuil aussi bas"
            derniere_ligne = chemin.read_text(encoding="utf-8").strip().splitlines()[-1]
            data = json.loads(derniere_ligne)
            assert data["type"] == "echantillon"


def scenario_demarrer_echantillonnage_ne_bloque_pas():
    """Le thread démarre instantanément (daemon=True) — ne doit jamais
    retarder le retour de la fonction (ce que ferait un éventuel appel
    bloquant au démarrage)."""
    import time
    debut = time.monotonic()
    thread = mci.demarrer_echantillonnage()
    duree = time.monotonic() - debut
    assert thread.daemon, "le thread doit être daemon (s'arrête avec le serveur)"
    assert duree < 1.0, f"demarrer_echantillonnage() ne doit jamais bloquer ({duree:.3f}s)"


# ─── app/charge_interface.py : crochets + route /mesure-precharge ───────────

def scenario_hooks_comptent_une_requete_sans_fuite_de_route():
    """Une requête vers une route PARAMÉTRÉE est comptée sous le GABARIT
    Flask (ex. '/issue/<nom_projet>/<numero>'), jamais sous l'URL résolue
    (qui contiendrait le vrai nom de projet et le vrai numéro d'issue) —
    exigence explicite de l'issue #835 point 3 (aucun numéro d'issue dans
    ces lignes)."""
    _reset_compteurs()
    app = _app()
    with app.test_client() as client:
        client.get("/issue/un_vrai_projet/123456")
    _nb, _total, _maxi, route = mci.relever_et_remettre_a_zero()
    assert route == "/issue/<nom_projet>/<numero>", route
    assert "123456" not in route and "un_vrai_projet" not in route


def scenario_route_resume_accepte_corps_bien_forme():
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "charge_interface.log"
        with _journal_temporaire(chemin):
            app = _app()
            with app.test_client() as client:
                rep = client.post("/mesure-precharge", json={
                    "nb_issues_preparees": 4, "nb_requetes": 9,
                    "duree_totale_ms": 512.0, "duree_max_ms": 211.5, "mode": "repli",
                })
                assert rep.status_code == 200, rep.get_data(as_text=True)
                assert rep.get_json()["succes"] is True
            contenu = chemin.read_text(encoding="utf-8").strip().splitlines()
            assert len(contenu) == 1
            data = json.loads(contenu[0])
            assert data["type"] == "resume_precharge"
            assert data["nb_issues_preparees"] == 4
            assert data["mode"] == "repli"


def scenario_route_resume_rejette_champ_inconnu():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/mesure-precharge", json={
            "nb_issues_preparees": 1, "nb_requetes": 1, "duree_totale_ms": 1,
            "duree_max_ms": 1, "mode": "moderne", "titre_issue": "fuite potentielle",
        })
        assert rep.status_code == 400, rep.status_code
        assert rep.get_json()["succes"] is False


def scenario_route_resume_rejette_champ_manquant():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/mesure-precharge", json={
            "nb_issues_preparees": 1, "nb_requetes": 1, "duree_totale_ms": 1, "mode": "moderne",
        })
        assert rep.status_code == 400, rep.status_code


def scenario_route_resume_rejette_valeur_non_numerique():
    app = _app()
    with app.test_client() as client:
        for champ in ci.CHAMPS_NUMERIQUES_RESUME:
            corps = {
                "nb_issues_preparees": 1, "nb_requetes": 1,
                "duree_totale_ms": 1, "duree_max_ms": 1, "mode": "moderne",
            }
            corps[champ] = "pas un nombre"
            rep = client.post("/mesure-precharge", json=corps)
            assert rep.status_code == 400, f"{champ} : {rep.status_code}"


def scenario_route_resume_rejette_nombre_negatif():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/mesure-precharge", json={
            "nb_issues_preparees": -1, "nb_requetes": 1,
            "duree_totale_ms": 1, "duree_max_ms": 1, "mode": "moderne",
        })
        assert rep.status_code == 400


def scenario_route_resume_rejette_mode_invalide():
    app = _app()
    with app.test_client() as client:
        rep = client.post("/mesure-precharge", json={
            "nb_issues_preparees": 1, "nb_requetes": 1,
            "duree_totale_ms": 1, "duree_max_ms": 1, "mode": "autre_chose",
        })
        assert rep.status_code == 400


def scenario_route_resume_rejette_corps_trop_gros():
    app = _app()
    with app.test_client() as client:
        rep = client.post(
            "/mesure-precharge",
            data="x" * (ci.TAILLE_MAX_CORPS_RESUME + 1),
            content_type="application/json")
        assert rep.status_code == 400
        assert "volumineux" in rep.get_json()["erreur"]


def scenario_route_resume_exige_connexion_si_acces_reseau():
    """Même règle de connexion que le reste de l'interface (login_requis) :
    en --lan/--externe (ACCES_RESEAU + mot de passe configurés), la route
    redirige vers /login sans session."""
    app = _app()
    app.config["ACCES_RESEAU"] = True
    app.config["MOT_DE_PASSE"] = "un_hash_quelconque"
    with app.test_client() as client:
        rep = client.post("/mesure-precharge", json={
            "nb_issues_preparees": 1, "nb_requetes": 1,
            "duree_totale_ms": 1, "duree_max_ms": 1, "mode": "moderne",
        }, follow_redirects=False)
        assert rep.status_code == 302, rep.status_code
        assert "/login" in rep.headers.get("Location", "")


def main():
    tests = [
        ("differences_cpu : somme propre + enfants, entre deux échantillons",
         scenario_differences_cpu),
        ("ligne_echantillon : format JSON exact, aucun champ en trop",
         scenario_ligne_echantillon_format_sans_fuite),
        ("ligne_resume_precharge : format JSON exact",
         scenario_ligne_resume_format_sans_fuite),
        ("enregistrer_requete : compteurs et route la plus lente",
         scenario_enregistrer_requete_route_la_plus_lente),
        ("enregistrer_requete : thread-safe (verrou), aucun incrément perdu",
         scenario_enregistrer_requete_thread_safe),
        ("ecrire_ligne : écriture + rotation par taille (JournalRotatifDate)",
         scenario_ecrire_ligne_et_rotation),
        ("demarrer_echantillonnage : démarre un thread daemon, sans bloquer",
         scenario_demarrer_echantillonnage_ne_bloque_pas),
        ("crochets : route comptée sous le gabarit Flask, jamais l'URL résolue",
         scenario_hooks_comptent_une_requete_sans_fuite_de_route),
        ("route /mesure-precharge : accepte un corps bien formé",
         scenario_route_resume_accepte_corps_bien_forme),
        ("route /mesure-precharge : rejette un champ inconnu",
         scenario_route_resume_rejette_champ_inconnu),
        ("route /mesure-precharge : rejette un champ manquant",
         scenario_route_resume_rejette_champ_manquant),
        ("route /mesure-precharge : rejette une valeur non numérique",
         scenario_route_resume_rejette_valeur_non_numerique),
        ("route /mesure-precharge : rejette un nombre négatif",
         scenario_route_resume_rejette_nombre_negatif),
        ("route /mesure-precharge : rejette un mode invalide",
         scenario_route_resume_rejette_mode_invalide),
        ("route /mesure-precharge : rejette un corps trop gros",
         scenario_route_resume_rejette_corps_trop_gros),
        ("route /mesure-precharge : exige la connexion comme le reste de l'interface",
         scenario_route_resume_exige_connexion_si_acces_reseau),
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

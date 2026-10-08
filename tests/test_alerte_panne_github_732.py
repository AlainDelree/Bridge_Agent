#!/usr/bin/env python3
"""Test de non-régression — issue #732 : alerte explicite quand GitHub est en
panne (interroge githubstatus.com/api/v2/summary.json lors d'un échec de gh
classé « panne probable »).

Couvre, en logique pure, SANS AUCUN accès réseau (summary.json toujours
simulé par un dict Python ou monkeypatché) :
- classer_echec_gh() : panne probable (timeout, erreur réseau, 5xx) vs erreur
  normale (404/401/403/422, gh introuvable) ;
- extraire_resume_statut() / calculer_message_statut() : les trois messages de
  repli, par ordre de gravité, + transition incident → rétabli ;
- verifier_statut() : cache serveur ~60s (au plus un appel réseau simulé par
  minute) ;
- signaler_resultat_gh() : ouverture/fermeture d'un épisode (une ligne par
  épisode, jamais par erreur), calcul de la durée, taille bornée du journal ;
- scripts/resume_pannes_github.py::resumer() : regroupement par mois et cause.

Exécution :  python3 -m pytest tests/test_alerte_panne_github_732.py
        ou : python3 tests/test_alerte_panne_github_732.py
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import app.github_status as gs  # noqa: E402
import resume_pannes_github as resume_mod  # noqa: E402


# ─── classer_echec_gh ───────────────────────────────────────────────────────

def test_classer_echec_gh_timeout_est_une_panne():
    assert gs.classer_echec_gh("Timeout (gh n'a pas répondu en 30s).")


def test_classer_echec_gh_5xx_est_une_panne():
    assert gs.classer_echec_gh("HTTP 502: Bad Gateway (https://api.github.com/...)")
    assert gs.classer_echec_gh("HTTP 503: Service Unavailable")


def test_classer_echec_gh_erreur_reseau_est_une_panne():
    assert gs.classer_echec_gh("dial tcp: lookup api.github.com: Temporary failure in name resolution")
    assert gs.classer_echec_gh("connection refused")


def test_classer_echec_gh_404_nest_pas_une_panne():
    assert not gs.classer_echec_gh("HTTP 404: Not Found (https://api.github.com/repos/x/y)")


def test_classer_echec_gh_403_nest_pas_une_panne():
    assert not gs.classer_echec_gh("HTTP 403: Bad credentials")


def test_classer_echec_gh_422_nest_pas_une_panne():
    assert not gs.classer_echec_gh("HTTP 422: Validation Failed")


def test_classer_echec_gh_rate_limit_nest_pas_une_panne():
    assert not gs.classer_echec_gh("API rate limit exceeded for user ID 123.")


def test_classer_echec_gh_introuvable_nest_pas_une_panne():
    assert not gs.classer_echec_gh("gh introuvable dans le PATH.")


# ─── extraire_resume_statut / calculer_message_statut ───────────────────────

def _summary(indicateur="none", composants=None, incidents=None):
    return {
        "status": {"indicator": indicateur},
        "components": composants or [],
        "incidents": incidents or [],
    }


def test_extraire_resume_statut_filtre_les_composants_utiles():
    data = _summary(composants=[
        {"name": "Issues", "status": "operational"},
        {"name": "Pages", "status": "major_outage"},   # pas surveillé par Bridge_Agent
        {"name": "API Requests", "status": "degraded_performance"},
    ])
    resume = gs.extraire_resume_statut(data)
    noms = {c["nom"] for c in resume["composants"]}
    assert noms == {"Issues", "API Requests"}, noms


def test_calculer_message_statut_incident_signale():
    resume = gs.extraire_resume_statut(_summary(
        indicateur="major",
        composants=[{"name": "Issues", "status": "major_outage"}],
        incidents=[{"name": "Issues API degraded", "status": "investigating"}],
    ))
    resultat = gs.calculer_message_statut(resume, True)
    assert resultat["gravite"] == gs.GRAVITE_INCIDENT
    assert "Issues API degraded" in resultat["message"]
    assert "Issues" in resultat["message"]   # composant concerné cité


def test_calculer_message_statut_operationnel_malgre_erreur():
    resume = gs.extraire_resume_statut(_summary())
    resultat = gs.calculer_message_statut(resume, True)
    assert resultat["gravite"] == gs.GRAVITE_OK
    assert resultat["message"] == gs.MESSAGE_OK


def test_calculer_message_statut_page_injoignable():
    resultat = gs.calculer_message_statut(None, False)
    assert resultat["gravite"] == gs.GRAVITE_INJOIGNABLE
    assert resultat["message"] == gs.MESSAGE_INJOIGNABLE


def test_calculer_message_statut_composant_degrade_sans_incident_nomme():
    """Cas limite : un composant dégradé mais summary.json sans incident listé
    (rare, mais possible juste après la bascule) — le message cite le
    composant plutôt que de retomber sur « opérationnel »."""
    resume = gs.extraire_resume_statut(_summary(
        indicateur="minor",
        composants=[{"name": "Git Operations", "status": "degraded_performance"}],
    ))
    resultat = gs.calculer_message_statut(resume, True)
    assert resultat["gravite"] == gs.GRAVITE_INCIDENT
    assert "Git Operations" in resultat["message"]


# ─── verifier_statut : cache serveur ~60s ───────────────────────────────────

def test_verifier_statut_cache_une_minute(monkeypatch):
    appels = []

    def fausse_interrogation(timeout_s=gs.TIMEOUT_REQUETE_S):
        appels.append(1)
        return _summary(), True

    horloge = {"t": 1000.0}
    monkeypatch.setattr(gs, "_interroger_page_statut", fausse_interrogation)
    monkeypatch.setattr(gs.time, "time", lambda: horloge["t"])
    monkeypatch.setattr(gs, "_cache", {"resume": None, "page_accessible": None, "epoch": 0.0})
    monkeypatch.setattr(gs, "_maj_cause_episode", lambda resultat: None)

    gs.verifier_statut()
    gs.verifier_statut()
    horloge["t"] += 30   # toujours sous SEUIL_CACHE_S (60s)
    gs.verifier_statut()
    assert len(appels) == 1, "trois appels rapprochés ne doivent déclencher qu'UNE requête"

    horloge["t"] += 40   # dépasse les 60s cumulés depuis le premier appel
    gs.verifier_statut()
    assert len(appels) == 2, "après le délai de cache, une nouvelle requête est attendue"


# ─── signaler_resultat_gh / journal des pannes : un épisode, une ligne ──────

def _isoler_fichiers(monkeypatch, tmp_path):
    monkeypatch.setattr(gs, "CHEMIN_JOURNAL", tmp_path / "pannes_github.log")
    monkeypatch.setattr(gs, "CHEMIN_ETAT_EPISODE", tmp_path / "etat_panne_github.json")


def test_episode_ouvert_puis_ferme_ecrit_une_seule_ligne(monkeypatch, tmp_path):
    _isoler_fichiers(monkeypatch, tmp_path)
    horloge = {"t": 2000.0}
    monkeypatch.setattr(gs.time, "time", lambda: horloge["t"])

    # Plusieurs échecs successifs classés panne : UN seul épisode doit s'ouvrir.
    gs.signaler_resultat_gh(False, panne_probable=True, origine="t1")
    horloge["t"] += 5
    gs.signaler_resultat_gh(False, panne_probable=True, origine="t1")
    horloge["t"] += 5
    gs.signaler_resultat_gh(False, panne_probable=True, origine="t1")

    assert gs.episode_en_cours() is not None
    assert not gs.CHEMIN_JOURNAL.exists(), "aucune ligne tant que l'épisode reste ouvert"

    horloge["t"] += 90   # durée totale de l'épisode : 100s
    gs.signaler_resultat_gh(True, origine="t1")   # succès gh → fermeture

    assert gs.episode_en_cours() is None
    lignes = gs.CHEMIN_JOURNAL.read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 1, lignes
    champs = gs.parser_ligne_journal(lignes[0])
    assert champs is not None
    assert champs["duree_s"] == "100"
    assert champs["cause"] == gs.CAUSE_INDETERMINEE   # jamais de vérification statut pendant ce test


def test_echec_normal_sans_panne_probable_nouvre_aucun_episode(monkeypatch, tmp_path):
    _isoler_fichiers(monkeypatch, tmp_path)
    monkeypatch.setattr(gs.time, "time", lambda: 3000.0)

    gs.signaler_resultat_gh(False, panne_probable=False, origine="t2")   # ex. 404
    assert gs.episode_en_cours() is None
    assert not gs.CHEMIN_JOURNAL.exists()


def test_cause_journalisee_reflete_la_derniere_gravite_connue(monkeypatch, tmp_path):
    _isoler_fichiers(monkeypatch, tmp_path)
    horloge = {"t": 4000.0}
    monkeypatch.setattr(gs.time, "time", lambda: horloge["t"])

    gs.signaler_resultat_gh(False, panne_probable=True, origine="t3")
    gs._maj_cause_episode({"gravite": gs.GRAVITE_INCIDENT, "incident_nom": "Issues API",
                            "composants": [{"nom": "Issues", "statut": "major_outage"}]})
    horloge["t"] += 42
    gs.signaler_resultat_gh(True, origine="t3")

    ligne = gs.CHEMIN_JOURNAL.read_text(encoding="utf-8").splitlines()[0]
    champs = gs.parser_ligne_journal(ligne)
    assert champs["cause"] == gs.CAUSES_LABEL[gs.GRAVITE_INCIDENT]
    assert champs["incident"] == "Issues API"
    assert champs["composants"] == "Issues"


def test_journal_borne_purge_les_lignes_trop_anciennes(monkeypatch, tmp_path):
    _isoler_fichiers(monkeypatch, tmp_path)
    maintenant = 10_000_000.0
    vieille_ligne = gs.formater_ligne_journal(
        maintenant - (gs.RETENTION_JOURS + 10) * 86400,
        maintenant - (gs.RETENTION_JOURS + 10) * 86400 + 60,
        60, "cause ancienne", None, [])
    gs.CHEMIN_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    gs.CHEMIN_JOURNAL.write_text(vieille_ligne + "\n", encoding="utf-8")

    monkeypatch.setattr(gs.time, "time", lambda: maintenant)
    nouvelle_ligne = gs.formater_ligne_journal(maintenant - 60, maintenant, 60, "cause récente", None, [])
    gs._ecrire_ligne_journal(nouvelle_ligne)

    lignes = gs.CHEMIN_JOURNAL.read_text(encoding="utf-8").splitlines()
    assert len(lignes) == 1, "la ligne vieille de plus d'un an doit avoir été purgée"
    assert "cause récente" in lignes[0]


# ─── scripts/resume_pannes_github.py ────────────────────────────────────────

def test_resumer_regroupe_par_mois_et_cause():
    lignes = [
        gs.formater_ligne_journal(
            __import__("datetime").datetime(2026, 9, 5, tzinfo=__import__("datetime").timezone.utc).timestamp(),
            __import__("datetime").datetime(2026, 9, 5, 0, 1, tzinfo=__import__("datetime").timezone.utc).timestamp(),
            60, "incident GitHub signalé", "Issues API", []),
        gs.formater_ligne_journal(
            __import__("datetime").datetime(2026, 9, 10, tzinfo=__import__("datetime").timezone.utc).timestamp(),
            __import__("datetime").datetime(2026, 9, 10, 0, 2, tzinfo=__import__("datetime").timezone.utc).timestamp(),
            120, "incident GitHub signalé", "Issues API", []),
        gs.formater_ligne_journal(
            __import__("datetime").datetime(2026, 10, 1, tzinfo=__import__("datetime").timezone.utc).timestamp(),
            __import__("datetime").datetime(2026, 10, 1, 0, 5, tzinfo=__import__("datetime").timezone.utc).timestamp(),
            300, "connexion internet injoignable", None, []),
    ]
    resume = resume_mod.resumer(lignes)
    assert resume[("2026-09", "incident GitHub signalé")] == {"episodes": 2, "duree_s": 180.0}
    assert resume[("2026-10", "connexion internet injoignable")] == {"episodes": 1, "duree_s": 300.0}


def test_resumer_ignore_les_lignes_mal_formees():
    assert resume_mod.resumer(["pas une ligne de journal valide"]) == {}


def test_formater_duree():
    assert resume_mod.formater_duree(45) == "45s"
    assert resume_mod.formater_duree(125) == "2m05"
    assert resume_mod.formater_duree(3725) == "1h02"


def main() -> int:
    tests = [
        ("classer_echec_gh : timeout = panne", test_classer_echec_gh_timeout_est_une_panne, ()),
        ("classer_echec_gh : 5xx = panne", test_classer_echec_gh_5xx_est_une_panne, ()),
        ("classer_echec_gh : erreur réseau = panne", test_classer_echec_gh_erreur_reseau_est_une_panne, ()),
        ("classer_echec_gh : 404 ≠ panne", test_classer_echec_gh_404_nest_pas_une_panne, ()),
        ("classer_echec_gh : 403 ≠ panne", test_classer_echec_gh_403_nest_pas_une_panne, ()),
        ("classer_echec_gh : 422 ≠ panne", test_classer_echec_gh_422_nest_pas_une_panne, ()),
        ("classer_echec_gh : rate limit ≠ panne", test_classer_echec_gh_rate_limit_nest_pas_une_panne, ()),
        ("classer_echec_gh : gh introuvable ≠ panne", test_classer_echec_gh_introuvable_nest_pas_une_panne, ()),
        ("extraire_resume_statut : filtre les composants utiles",
         test_extraire_resume_statut_filtre_les_composants_utiles, ()),
        ("calculer_message_statut : incident signalé", test_calculer_message_statut_incident_signale, ()),
        ("calculer_message_statut : opérationnel malgré erreur",
         test_calculer_message_statut_operationnel_malgre_erreur, ()),
        ("calculer_message_statut : page injoignable", test_calculer_message_statut_page_injoignable, ()),
        ("calculer_message_statut : composant dégradé sans incident nommé",
         test_calculer_message_statut_composant_degrade_sans_incident_nomme, ()),
        ("resumer : regroupe par mois et cause", test_resumer_regroupe_par_mois_et_cause, ()),
        ("resumer : ignore les lignes mal formées", test_resumer_ignore_les_lignes_mal_formees, ()),
        ("formater_duree", test_formater_duree, ()),
    ]
    echecs = 0
    for nom, fn, args in tests:
        try:
            fn(*args)
            print(f"  ✓ {nom}")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
    print("\nAutres scénarios (monkeypatch/tmp_path) : exécuter via pytest.")
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios exécutables sans pytest passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

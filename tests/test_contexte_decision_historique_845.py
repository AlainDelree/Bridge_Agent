#!/usr/bin/env python3
"""Test de non-régression — issue #845 : l'historique des durées
(logs/historique_durees.json) n'enregistrait jusqu'ici que des champs
AGRÉGÉS (projet/type/mode/durée...), sans le numéro de l'issue, la
complexité retenue, le TIMEOUT réellement appliqué, ni l'estimation/
TIMEOUT_suggéré en vigueur AU LANCEMENT — il fallait reconstituer ces
données depuis les commentaires GitHub pour auditer la calibration.

Couvre :
1. `enregistrer_duree()` écrit bien, pour une nouvelle ligne, TOUS les
   nouveaux champs (numero_issue, tentative, timeout_applique, complexite/
   complexite_statut, timeout_suggere_lancement, estimation_lancement).
2. Rétrocompatibilité : une ancienne ligne (sans aucun des nouveaux champs)
   reste lue sans erreur par `estimer_duree()`/`_charger_historique()`, et
   `enregistrer_duree()` peut ajouter une ligne derrière elle sans la
   toucher.
3. `extraire_complexite_pour_historique()` distingue bien COMPLEXITE
   absente / non reconnue (avec la valeur brute d'origine) / valide.
4. Une tentative expirée (`expiree=True`) est enregistrée avec les mêmes
   nouveaux champs que pour un succès.
5. `scripts/archiver_historique.py::archiver()` conserve les nouveaux
   champs d'une ligne déplacée vers le fichier d'archive (déplacement
   d'un dict entier, aucune reconstruction champ par champ).
6. Bout en bout (réseau GitHub remplacé par des bouchons) :
   `_demarrer_traitement()` puis `_finaliser_succes()` enchaînés comme dans
   `_traiter_issue_synchrone()` — l'estimation figée AU LANCEMENT est bien
   celle écrite dans la ligne de clôture, identique à celle qu'aurait
   affichée l'interface juste avant, et INCHANGÉE même si l'historique
   grandit (cette même écriture) avant que la ligne ne soit construite.

Aucun appel réseau ni `gh` réel — uniquement enregistrer_duree/estimer_duree/
extraire_complexite_pour_historique/archiver, en lecture-écriture sur des
fichiers temporaires.

Exécution :  python3 -m pytest tests/test_contexte_decision_historique_845.py
        ou : python3 tests/test_contexte_decision_historique_845.py
"""

import json
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import pytest  # noqa: E402

import watcher  # noqa: E402
from archiver_historique import archiver  # noqa: E402


@pytest.fixture(autouse=True)
def _isoler(tmp_path, monkeypatch):
    """Redirige les fichiers d'état sur des chemins temporaires, comme les
    autres tests de watcher.py (ex. test_lecture_active_327.py) — jamais le
    vrai logs/historique_durees.json du dépôt."""
    monkeypatch.setattr(watcher, "FICHIER_HISTORIQUE", tmp_path / "historique_durees.json")
    monkeypatch.setattr(watcher, "FICHIER_ETAT_TIMEOUT", tmp_path / "etat_timeout.json")
    monkeypatch.setattr(watcher, "FICHIER_ETAT_AMBIANCE", tmp_path / "etat_ambiance.json")
    monkeypatch.setattr(watcher, "FICHIER_JOURNAL_ECRITURES", tmp_path / "journal.jsonl")
    yield


def _derniere_ligne() -> dict:
    return json.loads(watcher.FICHIER_HISTORIQUE.read_text(encoding="utf-8"))[-1]


# ─── 1. Nouvelle ligne : tous les champs présents ──────────────────────────
def test_enregistrer_duree_nouvelle_ligne_tous_les_champs():
    watcher.enregistrer_duree(
        "bridge_agent", "normal", "write", 123.4, "2026-11-02T10:00:00",
        body="| COMPLEXITE | lourd |\n", nb_projets_actifs=2,
        numero_issue=845, tentative=1, timeout_applique=1800,
        complexite_valeur="lourd", complexite_statut="valide", complexite_brute=None,
        timeout_suggere_lancement=1500.7,
        estimation_lancement={"mediane": 600, "n": 12, "fiabilite": "correct"},
    )
    ligne = _derniere_ligne()
    assert ligne["numero_issue"] == 845, ligne
    assert ligne["tentative"] == 1, ligne
    assert ligne["timeout_applique"] == 1800, ligne
    assert ligne["complexite"] == "lourd", ligne
    assert ligne["complexite_statut"] == "valide", ligne
    assert "complexite_brute" not in ligne, ligne  # omis quand la valeur est valide
    assert ligne["timeout_suggere_lancement"] == 1501, ligne  # round()
    assert ligne["estimation_lancement"] == {"mediane": 600, "n": 12, "fiabilite": "correct"}, ligne
    # Champs déjà existants avant #845, inchangés :
    assert ligne["projet"] == "bridge_agent" and ligne["duree"] == 123, ligne


def test_enregistrer_duree_complexite_non_reconnue_conserve_la_valeur_brute():
    watcher.enregistrer_duree(
        "bridge_agent", "normal", "write", 10, "2026-11-02T10:00:00",
        numero_issue=1, tentative=1, timeout_applique=300,
        complexite_valeur="normal", complexite_statut="non_reconnue", complexite_brute="moyen",
    )
    ligne = _derniere_ligne()
    assert ligne["complexite"] == "normal", ligne
    assert ligne["complexite_statut"] == "non_reconnue", ligne
    assert ligne["complexite_brute"] == "moyen", ligne


def test_enregistrer_duree_sans_nouveaux_champs_ne_les_ecrit_pas():
    """Un appelant qui ne fournit aucun des nouveaux paramètres (comportement
    d'avant #845) produit une ligne SANS ces champs — pas de valeur `None`
    bruiteuse pour les lecteurs existants."""
    watcher.enregistrer_duree("bridge_agent", "normal", "write", 10, "2026-11-02T10:00:00")
    ligne = _derniere_ligne()
    for champ in ("numero_issue", "tentative", "timeout_applique", "complexite",
                  "complexite_statut", "complexite_brute",
                  "timeout_suggere_lancement", "estimation_lancement"):
        assert champ not in ligne, ligne


# ─── 2. Rétrocompatibilité : ancienne ligne lue sans erreur ────────────────
def test_ancienne_ligne_lue_sans_erreur_par_estimer_duree():
    ancienne = {"projet": "bridge_agent", "type": "normal", "mode": "write",
                "duree": 200, "date": "2026-09-01T10:00:00"}
    watcher.FICHIER_HISTORIQUE.write_text(json.dumps([ancienne]), encoding="utf-8")
    historique = watcher._charger_historique()
    resultat = watcher.estimer_duree(historique, "bridge_agent", "normal", "write")
    assert resultat["mediane"] == 200, resultat
    assert resultat["n"] == 1, resultat


def test_ancienne_ligne_preservee_quand_une_nouvelle_est_ajoutee():
    ancienne = {"projet": "bridge_agent", "type": "normal", "mode": "write",
                "duree": 200, "date": "2026-09-01T10:00:00"}
    watcher.FICHIER_HISTORIQUE.write_text(json.dumps([ancienne]), encoding="utf-8")
    watcher.enregistrer_duree(
        "bridge_agent", "normal", "write", 300, "2026-11-02T10:00:00",
        numero_issue=845, tentative=1, timeout_applique=900,
        complexite_valeur="normal", complexite_statut="absente", complexite_brute=None,
    )
    historique = json.loads(watcher.FICHIER_HISTORIQUE.read_text(encoding="utf-8"))
    assert len(historique) == 2, historique
    assert historique[0] == ancienne, historique[0]   # inchangée
    assert historique[1]["numero_issue"] == 845, historique[1]


# ─── 3. extraire_complexite_pour_historique : absente / non reconnue / valide
def test_complexite_absente():
    valeur, statut, brute = watcher.extraire_complexite_pour_historique(
        "## En-tête\n\n| PROJET | bridge_agent |\n")
    assert (valeur, statut, brute) == ("normal", "absente", None)


def test_complexite_non_reconnue_garde_la_valeur_dorigine():
    valeur, statut, brute = watcher.extraire_complexite_pour_historique(
        "| COMPLEXITE | moyen |\n")
    assert (valeur, statut, brute) == ("normal", "non_reconnue", "moyen")


def test_complexite_valide():
    for niveau in ("rapide", "court", "normal", "lourd"):
        valeur, statut, brute = watcher.extraire_complexite_pour_historique(
            f"| COMPLEXITE | {niveau} |\n")
        assert (valeur, statut, brute) == (niveau, "valide", None), niveau


def test_complexite_meme_valeur_retenue_que_extraire_complexite():
    """Garde-fou de cohérence (issue #845) : AUCUN changement de la valeur
    utilisée par la calibration — seul le statut est nouveau."""
    for corps in ("", "| COMPLEXITE | moyen |\n", "| COMPLEXITE | lourd |\n"):
        valeur, _statut, _brute = watcher.extraire_complexite_pour_historique(corps)
        assert valeur == watcher.extraire_complexite(corps), corps


# ─── 4. Tentative expirée : mêmes nouveaux champs, durée = plafond atteint ─
def test_tentative_expiree_memes_nouveaux_champs():
    watcher.enregistrer_duree(
        "bridge_agent", "normal", "write", 900, "2026-11-02T10:00:00",
        expiree=True,
        numero_issue=845, tentative=2, timeout_applique=900,
        complexite_valeur="lourd", complexite_statut="valide", complexite_brute=None,
        timeout_suggere_lancement=1200.0,
        estimation_lancement={"mediane": None, "n": 0, "fiabilite": "aucune"},
    )
    ligne = _derniere_ligne()
    assert ligne["expiree"] is True, ligne
    assert ligne["duree"] == 900, ligne   # plafond TIMEOUT atteint, pas une durée réelle
    assert ligne["numero_issue"] == 845, ligne
    assert ligne["tentative"] == 2, ligne
    assert ligne["timeout_applique"] == 900, ligne
    assert ligne["complexite"] == "lourd" and ligne["complexite_statut"] == "valide", ligne
    assert ligne["timeout_suggere_lancement"] == 1200, ligne
    assert ligne["estimation_lancement"] == {"mediane": None, "n": 0, "fiabilite": "aucune"}, ligne


# ─── 5. archiver_historique.py conserve les nouveaux champs ───────────────
def test_archivage_conserve_les_nouveaux_champs(tmp_path):
    fichier = tmp_path / "historique_durees.json"
    ancienne_avec_nouveaux_champs = {
        "projet": "bridge_agent", "type": "normal", "mode": "write",
        "duree": 120, "date": "2020-01-01T10:00:00",
        "numero_issue": 1, "tentative": 1, "timeout_applique": 300,
        "complexite": "rapide", "complexite_statut": "valide",
        "timeout_suggere_lancement": 250, "estimation_lancement": {"mediane": 100, "n": 20, "fiabilite": "sur"},
    }
    fichier.write_text(json.dumps([ancienne_avec_nouveaux_champs]), encoding="utf-8")

    rapport = archiver(fichier, seuil_mois=1, n_min=0, dry_run=False)
    assert rapport.get("erreur") is None, rapport
    assert rapport["n_total_archivees"] == 1, rapport

    fichier_archive = fichier.with_name("historique_durees_archive_2020.json")
    archive = json.loads(fichier_archive.read_text(encoding="utf-8"))
    assert archive == [ancienne_avec_nouveaux_champs], archive


# ─── 6. Bout en bout : _demarrer_traitement() → _finaliser_succes() ───────
def test_bout_en_bout_estimation_figee_au_lancement_et_inchangee(tmp_path, monkeypatch):
    # Historique PRÉ-EXISTANT : 5 issues "bridge_agent|normal|read" à 100s,
    # assez pour une fiabilité 'correct' (SEUIL_ESTIM_CORRECT = 5).
    historique_initial = [
        {"projet": "bridge_agent", "type": "normal", "mode": "read",
         "duree": 100, "date": "2026-10-01T10:00:00"}
        for _ in range(5)
    ]
    watcher.FICHIER_HISTORIQUE.write_text(json.dumps(historique_initial), encoding="utf-8")

    # Bouchons réseau GitHub (aucun appel réel) — mêmes noms que les autres
    # tests bout-en-bout de watcher.py (ex. test_corrections_erreurs_bloquantes_761.py).
    monkeypatch.setattr(watcher, "commenter_issue", lambda numero, message: True)
    monkeypatch.setattr(watcher, "notifier_debut_sse", lambda numero: None)
    monkeypatch.setattr(watcher, "notifier_fin_sse", lambda numero: None)
    monkeypatch.setattr(watcher, "_lister_commentaires", lambda numero: [])
    monkeypatch.setattr(watcher, "verifier_preflight_token", lambda cwd=None: None)
    monkeypatch.setattr(watcher, "commenter_resultat_avec_retry", lambda numero, message: True)
    monkeypatch.setattr(watcher, "fermer_issue", lambda numero: True)
    monkeypatch.setattr(watcher, "editer_dernier_commentaire", lambda numero, message: True)
    monkeypatch.setattr(watcher, "notifier", lambda *a, **k: None)

    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(
        nom="bridge_agent", depot="AlainDelree/depot-inexistant-845",
        rep_travail=tmp_path, topic_ntfy="", max_essais=3, timeout_claude=300,
        notifier_local=False,
    )
    try:
        numero, titre, body = 9845, "Issue de test #845", "| COMPLEXITE | lourd |\n"

        # Même estimation que celle qu'afficherait l'interface JUSTE AVANT le
        # lancement (même historique, même fonction).
        estimation_avant = watcher.estimer_duree(
            watcher._charger_historique(), "bridge_agent", "normal", "read", "lourd")
        assert estimation_avant == {"mediane": 100, "n": 5, "fiabilite": "correct"}

        (est_relance, debut_traitement, nb_projets_actifs_debut, empreinte_configs_avant,
         tete_avant_traitement, timeout_suggere_lancement, estimation_lancement) = \
            watcher._demarrer_traitement(
                numero, titre, body, watcher.MODE_LECTURE, "lecture seule",
                dry_run=True, cwd_effectif=tmp_path)

        # Capturée AU LANCEMENT, identique à l'estimation affichée juste avant.
        assert estimation_lancement == estimation_avant, estimation_lancement

        watcher._finaliser_succes(
            numero, titre, body, labels=[], mode=watcher.MODE_LECTURE, timeout=300,
            avertissement_conflit="", avertissement_worktree_deja_pris="",
            avertissement_worktree_repris="", sortie="✅ Fait.\n<!-- bridge:verdict:succes -->",
            debut_traitement=debut_traitement, nb_projets_actifs_debut=nb_projets_actifs_debut,
            est_relance=est_relance, dry_run=True, cwd_effectif=tmp_path,
            tete_avant_traitement=tete_avant_traitement,
            tentative=1, timeout_suggere_lancement=timeout_suggere_lancement,
            estimation_lancement=estimation_lancement,
        )
    finally:
        watcher.CFG = ancien_cfg

    historique_final = json.loads(watcher.FICHIER_HISTORIQUE.read_text(encoding="utf-8"))
    assert len(historique_final) == 6, historique_final   # les 5 anciennes + cette clôture
    ligne = historique_final[-1]
    assert ligne["numero_issue"] == 9845, ligne
    assert ligne["tentative"] == 1, ligne
    assert ligne["timeout_applique"] == 300, ligne
    assert ligne["complexite"] == "lourd" and ligne["complexite_statut"] == "valide", ligne
    # L'estimation ENREGISTRÉE reste celle d'AVANT cette clôture (n=5), même
    # si l'historique passe maintenant à 6 lignes — jamais recalculée après.
    assert ligne["estimation_lancement"] == {"mediane": 100, "n": 5, "fiabilite": "correct"}, ligne


def main() -> int:
    """Les scénarios ci-dessus ont besoin des fixtures pytest (tmp_path,
    monkeypatch) — exécution directe via pytest lui-même plutôt qu'une
    réimplémentation manuelle de ces fixtures."""
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Test de non-régression — issue #892 : champ d'en-tête optionnel `DOMAINES`
(fichiers de contexte à lire, avec avertissement s'ils manquent).

Couvre les points testables de l'issue :
1. `watcher.domaines_demandes` : extraction/validation tolérante du champ
   `| DOMAINES | nom1, nom2 |` — absent, valide, invalide/tentative de
   chemin.
2. `watcher._bloc_domaines` : la ligne « Lis d'abord : ... » injectée dans
   le prompt juste après CONTEXTE.md — fichier présent, fichier manquant au
   lancement, lot de plusieurs domaines, champ absent (rien injecté).
3. `watcher._avertissement_domaines` : le commentaire de clôture (mode
   écriture uniquement) — fichiers créés listés, fichier toujours manquant
   à la clôture, nom quasi identique, création non citée (seulement si
   DOMAINES est présent), et l'absence totale de vérification en mode
   lecture.
4. `scripts.watcher_issues_inbox` : DOMAINES réinséré à la création (comme
   REPO_CIBLE) et corrigé par une RELANCE (comme TIMEOUT/MODELE/
   SOUS_DOSSIER/REPO_CIBLE) — jamais inséré s'il est absent du corps cible.

Exécution :  python3 -m pytest tests/test_domaines_892.py
        ou : python3 tests/test_domaines_892.py
"""

import subprocess
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import pytest  # noqa: E402

import watcher  # noqa: E402
import watcher_issues_inbox as wii  # noqa: E402


# ─── 1. domaines_demandes — extraction/validation tolérante ───────────────

def test_domaines_absent():
    assert watcher.domaines_demandes("corps sans en-tête particulier.") == ([], [])


def test_domaines_vide():
    assert watcher.domaines_demandes("| DOMAINES |  |\n") == ([], [])


def test_domaines_valide_simple():
    valides, invalides = watcher.domaines_demandes("| DOMAINES | onglet_parametre |\n")
    assert valides == ["onglet_parametre"]
    assert invalides == []


def test_domaines_valides_plusieurs_dedup():
    corps = "| DOMAINES | onglet_parametre, autre_domaine, onglet_parametre |\n"
    valides, invalides = watcher.domaines_demandes(corps)
    assert valides == ["onglet_parametre", "autre_domaine"], "ordre d'apparition, dédupliqué"
    assert invalides == []


@pytest.mark.parametrize("brut", [
    "OngletParametre",       # majuscules
    "onglet-parametre",      # tiret, pas underscore
    "onglet parametre",      # espace interne
    "../../etc/passwd",      # tentative de traversée de chemin
    "../secret",
    "a/b",                   # séparateur de chemin
    "onglet.parametre",      # point
    "éléphant",              # accent
])
def test_domaines_nom_invalide_jamais_un_chemin(brut):
    """Un nom hors convention est ignoré, JAMAIS interprété comme un
    chemin : pas de '/' ni '..' dans la liste des noms valides, quelle que
    soit la valeur fournie."""
    valides, invalides = watcher.domaines_demandes(f"| DOMAINES | {brut} |\n")
    assert valides == []
    assert invalides == [brut]
    assert all("/" not in v and ".." not in v for v in valides)


def test_domaines_melange_valide_et_invalide():
    corps = "| DOMAINES | onglet_parametre, ../hack, autre_domaine |\n"
    valides, invalides = watcher.domaines_demandes(corps)
    assert valides == ["onglet_parametre", "autre_domaine"]
    assert invalides == ["../hack"]


# ─── 2. _bloc_domaines — ligne de prompt « Lis d'abord : ... » ────────────

def test_bloc_domaines_champ_absent_rien_injecte(tmp_path):
    assert watcher._bloc_domaines(8920, "corps sans DOMAINES.", tmp_path) == ""


def test_bloc_domaines_fichier_present(tmp_path):
    dossier = tmp_path / "docs" / "contexte"
    dossier.mkdir(parents=True)
    (dossier / "onglet_parametre.md").write_text("contenu", encoding="utf-8")

    bloc = watcher._bloc_domaines(8921, "| DOMAINES | onglet_parametre |\n", tmp_path)
    assert "Lis d'abord" in bloc
    assert "docs/contexte/onglet_parametre.md" in bloc
    assert "introuvable" not in bloc


def test_bloc_domaines_fichier_manquant_au_lancement(tmp_path, caplog):
    bloc = watcher._bloc_domaines(8922, "| DOMAINES | onglet_parametre |\n", tmp_path)
    assert "docs/contexte/onglet_parametre.md" in bloc
    assert "introuvable" in bloc
    assert "crée-le si l'issue te le demande" in bloc
    assert "signale-le dans ton rapport" in bloc
    assert any("introuvable" in r.message for r in caplog.records)


def test_bloc_domaines_lot_plusieurs_domaines_mixte(tmp_path):
    """Plusieurs domaines dans un même champ : un présent, un manquant —
    chacun listé avec son propre statut."""
    dossier = tmp_path / "docs" / "contexte"
    dossier.mkdir(parents=True)
    (dossier / "present.md").write_text("x", encoding="utf-8")

    bloc = watcher._bloc_domaines(8923, "| DOMAINES | present, manquant |\n", tmp_path)
    assert "docs/contexte/present.md" in bloc
    assert "docs/contexte/present.md (introuvable" not in bloc
    assert "docs/contexte/manquant.md (introuvable" in bloc


def test_bloc_domaines_nom_invalide_ignore_journalise(tmp_path, caplog):
    bloc = watcher._bloc_domaines(8924, "| DOMAINES | Invalide/Nom |\n", tmp_path)
    assert bloc == ""
    assert any("invalide" in r.message.lower() for r in caplog.records)


# ─── 3. _avertissement_domaines — commentaire de clôture ──────────────────

def _init_depot_git(rep: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "master", str(rep)], check=True)
    (rep / "fichier.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", "initial"], cwd=rep, check=True, capture_output=True)


def _commit_tout(rep: Path, message: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=rep, check=True, capture_output=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                     "commit", "-q", "-m", message], cwd=rep, check=True, capture_output=True)
    return watcher._tete_git(rep)


@pytest.fixture
def depot(tmp_path):
    rep = tmp_path / "projet"
    rep.mkdir()
    _init_depot_git(rep)
    return rep


def test_avertissement_lecture_seule_aucune_verification(depot):
    """Issue en lecture seule : aucune vérification de création, même si
    un fichier a par ailleurs été créé sous docs/contexte/ (scratch ou
    autre) entre les deux relevés."""
    tete = watcher._tete_git(depot)
    (depot / "docs" / "contexte").mkdir(parents=True)
    (depot / "docs" / "contexte" / "x.md").write_text("x", encoding="utf-8")
    _commit_tout(depot, "ajout x.md")

    avertissement = watcher._avertissement_domaines(
        8930, "| DOMAINES | x |\n", watcher.MODE_LECTURE, depot, tete)
    assert avertissement == ""


def test_avertissement_ecriture_sans_domaines_liste_les_crees(depot):
    """DOMAINES absent : les créations sous docs/contexte/ sont tout de
    même listées (point a), mais (d) ne s'applique pas (pas de « non
    cité »)."""
    tete = watcher._tete_git(depot)
    (depot / "docs" / "contexte").mkdir(parents=True)
    (depot / "docs" / "contexte" / "onglet_parametre.md").write_text("x", encoding="utf-8")
    _commit_tout(depot, "création demandée dans le corps")

    avertissement = watcher._avertissement_domaines(
        8931, "corps sans champ DOMAINES, création demandée en texte libre.",
        watcher.MODE_ECRITURE, depot, tete)
    assert "onglet_parametre.md" in avertissement
    assert "non cité" not in avertissement


def test_avertissement_rien_cree_rien_signale(depot):
    tete = watcher._tete_git(depot)
    (depot / "fichier.txt").write_text("modifie\n", encoding="utf-8")
    _commit_tout(depot, "fix sans toucher docs/contexte")

    avertissement = watcher._avertissement_domaines(
        8932, "corps sans DOMAINES.", watcher.MODE_ECRITURE, depot, tete)
    assert avertissement == ""


def test_avertissement_fichier_toujours_manquant_a_la_cloture(depot):
    tete = watcher._tete_git(depot)
    (depot / "fichier.txt").write_text("modifie\n", encoding="utf-8")
    _commit_tout(depot, "ne crée pas le fichier demandé")

    avertissement = watcher._avertissement_domaines(
        8933, "| DOMAINES | onglet_parametre |\n", watcher.MODE_ECRITURE, depot, tete)
    assert "docs/contexte/onglet_parametre.md" in avertissement
    assert "cité par DOMAINES" in avertissement


def test_avertissement_nom_quasi_identique(depot):
    """Un fichier déjà existant `OngletParametre.md`, et l'agent crée
    `onglet_parametre.md` — même nom une fois en minuscules sans '_'/'-'."""
    (depot / "docs" / "contexte").mkdir(parents=True)
    (depot / "docs" / "contexte" / "OngletParametre.md").write_text("x", encoding="utf-8")
    _commit_tout(depot, "fichier existant avant la tâche")
    tete = watcher._tete_git(depot)

    (depot / "docs" / "contexte" / "onglet_parametre.md").write_text("y", encoding="utf-8")
    _commit_tout(depot, "création sous un nom légèrement différent")

    avertissement = watcher._avertissement_domaines(
        8934, "corps sans DOMAINES.", watcher.MODE_ECRITURE, depot, tete)
    assert "onglet_parametre.md" in avertissement
    assert "quasi identique" in avertissement
    assert "OngletParametre.md" in avertissement


def test_avertissement_creation_non_citee_seulement_si_domaines_present(depot):
    tete = watcher._tete_git(depot)
    (depot / "docs" / "contexte").mkdir(parents=True)
    (depot / "docs" / "contexte" / "autre_domaine.md").write_text("x", encoding="utf-8")
    _commit_tout(depot, "création d'un domaine non cité par DOMAINES")

    avertissement = watcher._avertissement_domaines(
        8935, "| DOMAINES | onglet_parametre |\n", watcher.MODE_ECRITURE, depot, tete)
    assert "non cité" in avertissement
    assert "autre_domaine.md" in avertissement


def test_avertissement_tete_avant_traitement_absente(depot):
    assert watcher._avertissement_domaines(
        8936, "| DOMAINES | x |\n", watcher.MODE_ECRITURE, depot, None) == ""


# ─── 4. Bout en bout — ligne de prompt via lancer_claude ───────────────────

FAUX_CLAUDE_CAPTURE = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    echo "$prompt" > "$TEST_892_PROMPT_FILE"
fi
echo "<!-- bridge:verdict:succes -->"
echo "Tache terminee (test #892)."
exit 0
"""


def _config_isolee(rep_travail: Path, nom: str) -> watcher.Config:
    return watcher.Config(
        nom=nom, depot="AlainDelree/x",
        rep_travail=rep_travail, topic_ntfy=nom,
    )


def _lancer_avec_faux_claude(tmp_path, monkeypatch, numero, body, nom, rep_travail):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_CAPTURE, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{__import__('os').pathsep}{__import__('os').environ.get('PATH', '')}")
    fichier_prompt = tmp_path / f"prompt_{numero}.txt"
    monkeypatch.setenv("TEST_892_PROMPT_FILE", str(fichier_prompt))

    ancien_cfg = watcher.CFG
    watcher.CFG = _config_isolee(rep_travail, nom)
    try:
        ok, _sortie = watcher.lancer_claude(
            numero, "Titre", body, dry_run=False, mode=watcher.MODE_ECRITURE,
            timeout=30, cwd=rep_travail, commit_sauvegarde_watcher=None)
    finally:
        watcher.CFG = ancien_cfg
    assert ok is True
    return fichier_prompt.read_text(encoding="utf-8")


def test_prompt_champ_absent_comportement_inchange(tmp_path, monkeypatch):
    rep_travail = tmp_path / "projet"
    rep_travail.mkdir()
    prompt = _lancer_avec_faux_claude(tmp_path, monkeypatch, 8940, "corps sans DOMAINES.",
                                       "test892a", rep_travail)
    assert "Lis d'abord" not in prompt


def test_prompt_champ_valide_juste_apres_contexte(tmp_path, monkeypatch):
    rep_travail = tmp_path / "projet"
    rep_travail.mkdir()
    (rep_travail / "docs" / "contexte").mkdir(parents=True)
    (rep_travail / "docs" / "contexte" / "onglet_parametre.md").write_text("x", encoding="utf-8")
    body = "| DOMAINES | onglet_parametre |\n\nTâche."
    prompt = _lancer_avec_faux_claude(tmp_path, monkeypatch, 8941, body, "test892b", rep_travail)
    assert "Lis d'abord : docs/contexte/onglet_parametre.md" in prompt
    # Pas de CONTEXTE.md configuré ici (FICHIER_CONTEXTE vide) : la ligne
    # « Lis d'abord » doit malgré tout apparaître, juste avant le BODY/
    # consignes, sans dépendre d'un bloc CONTEXTE présent.
    assert prompt.index("Lis d'abord") < prompt.index("Instructions :")


# ─── 5. scripts/watcher_issues_inbox.py — création et RELANCE ─────────────

def test_extraire_champs_domaines_brut_et_ligne_retiree_du_corps():
    contenu = (
        "| PROJET   | bridge_agent |\n"
        "| DOMAINES | onglet_parametre, autre_domaine |\n"
        "\n#Titre: Tâche\n\nCorps de la tâche.\n"
    )
    champs = wii.extraire_champs(contenu)
    assert champs["domaines_brut"] == "onglet_parametre, autre_domaine"
    assert "DOMAINES" not in champs["corps"]


def test_construire_body_reinsere_domaines_a_la_creation():
    champs = {
        "titre": "Tâche", "corps": "Corps.", "modele": "", "timeout_brut": None,
        "mode_brut": "écriture", "domaines_brut": "onglet_parametre",
        "repo_cible_brut": "",
    }
    cfg_projet = __import__("types").SimpleNamespace(
        nom="bridge_agent", timeout_claude=300, timeout_chef=1200)
    body, _info_timeout = wii.construire_body(champs, cfg_projet)
    assert "| DOMAINES | onglet_parametre |" in body


def test_fusionner_entete_corrige_domaines_existant():
    corps_existant = (
        "| PROJET   | bridge_agent |\n"
        "| DOMAINES | ancien_nom |\n"
    )
    nouveau, modifies = wii._fusionner_entete(
        corps_existant,
        {"timeout_brut": None, "modele": "", "domaines_brut": "nouveau_nom", "corps": ""},
    )
    assert "| DOMAINES | nouveau_nom |" in nouveau
    assert "ancien_nom" not in nouveau
    assert modifies == ["DOMAINES → nouveau_nom"]


def test_fusionner_entete_domaines_absent_du_corps_cible_jamais_insere():
    corps_existant = "| PROJET | bridge_agent |\n"
    nouveau, modifies = wii._fusionner_entete(
        corps_existant,
        {"timeout_brut": None, "modele": "", "domaines_brut": "nouveau_nom", "corps": ""},
    )
    assert nouveau == corps_existant, "RELANCE ne doit jamais INSÉRER une ligne absente"
    assert modifies == []


def main() -> int:
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

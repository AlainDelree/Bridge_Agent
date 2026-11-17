#!/usr/bin/env python3
"""Test de non-régression — issue #889 : règle commune sur `CONTEXTE.md`
(essentiel seulement, index par domaine, limite de 4000 caractères).

Couvre les points testables de l'issue :
1. `nouveau_projet._ecrire_fichiers_contexte`/`creer_fichiers_contexte`
   créent désormais `CONTEXTE.md` avec un squelette (règles / architecture
   / conventions / index des fichiers de domaine, dans cet ordre) et son
   unique ligne de commentaire sur la limite de 4000 caractères — au lieu
   d'un fichier vide.
2. Idempotence : un `CONTEXTE.md` déjà présent (contenu quelconque) n'est
   JAMAIS écrasé par ce squelette.
3. `watcher.py` : le marqueur de troncature (contexte > 4000 caractères)
   précise maintenant que le reste n'est pas injecté mais reste lisible en
   entier dans le dépôt, et renvoie vers l'index des fichiers de domaine.

Le marqueur de troncature est vérifié bout en bout via `lancer_claude`, en
remplaçant l'exécutable `claude` par un faux script qui capture le prompt
reçu (même technique que `tests/test_commit_sauvegarde_watcher_846.py`) —
aucun appel réseau ni IA réel.

Exécution :  python3 -m pytest tests/test_contexte_domaine_889.py
        ou : python3 tests/test_contexte_domaine_889.py
"""

import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import pytest  # noqa: E402

import nouveau_projet as np_cli  # noqa: E402
import watcher  # noqa: E402

ORDRE_SECTIONS = ("## Règles", "## Architecture", "## Conventions",
                   "## Index des fichiers de domaine")


# ─── 1. Squelette créé, dans l'ordre attendu ───────────────────────────────
def test_ecrire_fichiers_contexte_cree_un_squelette_pas_un_fichier_vide(tmp_path):
    crees, existants = np_cli._ecrire_fichiers_contexte(tmp_path, avec_specs=False)
    assert existants == []
    assert [f.name for f in crees] == ["CONTEXTE.md"]

    contenu = (tmp_path / "CONTEXTE.md").read_text(encoding="utf-8")
    assert contenu != ""
    assert "4000 caractères maximum" in contenu
    assert contenu.count("<!--") == 1, "une seule ligne de commentaire attendue"

    positions = [contenu.index(section) for section in ORDRE_SECTIONS]
    assert positions == sorted(positions), (
        "l'ordre doit être règles / architecture / conventions / index", contenu)


def test_creer_fichiers_contexte_meme_squelette(tmp_path):
    rep = tmp_path / "projet"
    resultat = np_cli.creer_fichiers_contexte(str(rep), avec_specs=False)
    assert resultat["rep_cree"] is True
    assert [f.name for f in resultat["crees"]] == ["CONTEXTE.md"]
    contenu = (rep / "CONTEXTE.md").read_text(encoding="utf-8")
    for section in ORDRE_SECTIONS:
        assert section in contenu


def test_fichiers_specs_restent_vides_seul_contexte_a_le_squelette(tmp_path):
    """Seul CONTEXTE.md reçoit le squelette — les fichiers Specs MVC (§15)
    restent créés vides, comportement inchangé par #889."""
    crees, _existants = np_cli._ecrire_fichiers_contexte(tmp_path, avec_specs=True)
    noms = {f.name: f for f in crees}
    assert set(noms) == {"CONTEXTE.md", *np_cli.FICHIERS_SPECS}
    assert noms["CONTEXTE.md"].read_text(encoding="utf-8") != ""
    for nom_spec in np_cli.FICHIERS_SPECS:
        assert noms[nom_spec].read_text(encoding="utf-8") == ""


# ─── 2. Non-écrasement d'un CONTEXTE.md existant ───────────────────────────
def test_contexte_existant_jamais_ecrase(tmp_path):
    contexte = tmp_path / "CONTEXTE.md"
    contexte.write_text("contenu déjà rédigé par le projet", encoding="utf-8")

    crees, existants = np_cli._ecrire_fichiers_contexte(tmp_path, avec_specs=False)

    assert crees == []
    assert existants == [contexte]
    assert contexte.read_text(encoding="utf-8") == "contenu déjà rédigé par le projet"


def test_creer_fichiers_contexte_existant_jamais_ecrase(tmp_path):
    rep = tmp_path / "projet"
    rep.mkdir()
    contexte = rep / "CONTEXTE.md"
    contexte.write_text("contenu existant", encoding="utf-8")

    resultat = np_cli.creer_fichiers_contexte(str(rep), avec_specs=False)

    assert resultat["crees"] == []
    assert resultat["existants"] == [contexte]
    assert contexte.read_text(encoding="utf-8") == "contenu existant"


# ─── 3. Marqueur de troncature (watcher.py) ────────────────────────────────
FAUX_CLAUDE_CAPTURE = """#!/bin/bash
if [ "$#" -ge 2 ]; then
    prompt="${@: -1}"
    echo "$prompt" > "$TEST_889_PROMPT_FILE"
fi
echo "<!-- bridge:verdict:succes -->"
echo "Tache terminee (test #889)."
exit 0
"""
# MODE_ÉCRITURE (comme tests/test_commit_sauvegarde_watcher_846.py) : seul
# mode où `_construire_cmd_claude` place le prompt en DERNIER argument —
# en MODE_LECTURE, `--allowedTools ...` le suit (issue #546).


def _config_isolee(rep_travail: Path, nom: str, fichier_contexte: str) -> watcher.Config:
    return watcher.Config(
        nom=nom, depot="AlainDelree/x",
        rep_travail=rep_travail, topic_ntfy=nom,
        fichier_contexte=fichier_contexte,
    )


def test_marqueur_troncature_mentionne_index_et_lisibilite_complete(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_CAPTURE, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    fichier_prompt = tmp_path / "prompt.txt"
    monkeypatch.setenv("TEST_889_PROMPT_FILE", str(fichier_prompt))

    rep_travail = tmp_path / "projet"
    rep_travail.mkdir()
    (rep_travail / "CONTEXTE.md").write_text("x" * 4500, encoding="utf-8")

    ancien_cfg = watcher.CFG
    watcher.CFG = _config_isolee(rep_travail, "test889", "CONTEXTE.md")
    try:
        ok, _sortie = watcher.lancer_claude(
            8891, "Titre", "corps", dry_run=False, mode=watcher.MODE_ECRITURE,
            timeout=30, cwd=rep_travail, commit_sauvegarde_watcher=None)
    finally:
        watcher.CFG = ancien_cfg

    assert ok is True
    prompt = fichier_prompt.read_text(encoding="utf-8")
    assert "contexte tronqué à 4000 caractères" in prompt
    assert "n'est pas injectée mais reste lisible en entier" in prompt
    assert "index des fichiers de domaine" in prompt
    assert "x" * 4000 in prompt
    assert "x" * 4500 not in prompt, "le contenu au-delà de 4000 car. ne doit jamais être injecté"


def test_contexte_sous_la_limite_aucun_marqueur(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    faux_claude = bin_dir / "claude"
    faux_claude.write_text(FAUX_CLAUDE_CAPTURE, encoding="utf-8")
    faux_claude.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    fichier_prompt = tmp_path / "prompt.txt"
    monkeypatch.setenv("TEST_889_PROMPT_FILE", str(fichier_prompt))

    rep_travail = tmp_path / "projet"
    rep_travail.mkdir()
    (rep_travail / "CONTEXTE.md").write_text("contexte court", encoding="utf-8")

    ancien_cfg = watcher.CFG
    watcher.CFG = _config_isolee(rep_travail, "test889b", "CONTEXTE.md")
    try:
        ok, _sortie = watcher.lancer_claude(
            8892, "Titre", "corps", dry_run=False, mode=watcher.MODE_ECRITURE,
            timeout=30, cwd=rep_travail, commit_sauvegarde_watcher=None)
    finally:
        watcher.CFG = ancien_cfg

    assert ok is True
    prompt = fichier_prompt.read_text(encoding="utf-8")
    assert "contexte court" in prompt
    assert "tronqué" not in prompt


def main() -> int:
    return pytest.main([str(Path(__file__)), "-q"])


if __name__ == "__main__":
    sys.exit(main())

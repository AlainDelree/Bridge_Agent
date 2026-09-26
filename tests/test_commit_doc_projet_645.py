#!/usr/bin/env python3
"""Test de `regenerer_tableaux_projets.committer_pousser_doc()` — issue #645.

Constat d'origine : `mettre_a_jour_doc()` (nouveau_projet.py / supprimer_projet.py)
réécrivait bien BRIDGE_AGENT_DOC.md sur disque après une création/suppression
de projet, mais aucun des deux flux ne committait ni ne poussait ce
changement dans le dépôt Bridge_Agent — Alain devait s'en apercevoir lui-même
(`git status`) et le faire à la main. `committer_pousser_doc()` couvre cette
étape manquante ; ce fichier teste la fonction en isolation, sur de vrais
dépôts git jetables sous `/tmp` (même esprit que test_init_git_local_258.py),
jamais sur le vrai dépôt Bridge_Agent.

Couvre :
- succès : commit + push réels sur un dépôt bare local (origin) ;
- push en échec (remote pointant vers un chemin inexistant) : le commit
  reste en LOCAL, statut "push_echoue", commande manuelle renvoyée ;
- aucun changement réel du fichier : aucun commit (vide ou non) créé,
  statut "rien_a_faire" ;
- répertoire n'étant pas un dépôt git : échec propre avant tout commit,
  statut "echec".

Exécution :  python3 tests/test_commit_doc_projet_645.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import regenerer_tableaux_projets as rtp  # noqa: E402


def _log(rep: Path, *args: str) -> list[str]:
    res = subprocess.run(["git", "log", *args], cwd=rep,
                         capture_output=True, text=True)
    return res.stdout.strip().splitlines()


def _init_repo_avec_origin(tmp: Path) -> Path:
    """Dépôt bare (origin) + dépôt de travail cloné dessus, avec
    BRIDGE_AGENT_DOC.md déjà commité et poussé — état de départ symétrique au
    vrai dépôt Bridge_Agent. Renvoie le chemin du dépôt de travail."""
    origin = tmp / "origin.git"
    subprocess.run(["git", "init", "--bare", "-b", "master", str(origin)],
                   capture_output=True, text=True, check=True)

    travail = tmp / "travail"
    travail.mkdir()
    subprocess.run(["git", "init", "-b", "master"], cwd=travail,
                   capture_output=True, text=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                   cwd=travail, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=travail, check=True)
    subprocess.run(["git", "remote", "add", "origin", str(origin)],
                   cwd=travail, check=True)

    (travail / "BRIDGE_AGENT_DOC.md").write_text(
        "# BRIDGE_AGENT_DOC\n\nversion initiale\n", encoding="utf-8")
    subprocess.run(["git", "add", "BRIDGE_AGENT_DOC.md"], cwd=travail, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=travail,
                   capture_output=True, text=True, check=True)
    subprocess.run(["git", "push", "-u", "origin", "master"], cwd=travail,
                   capture_output=True, text=True, check=True)
    return travail


def test_commit_et_push_succes():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        travail = _init_repo_avec_origin(tmp)
        doc = travail / "BRIDGE_AGENT_DOC.md"
        doc.write_text(doc.read_text(encoding="utf-8") + "\najout du projet test\n",
                       encoding="utf-8")

        res = rtp.committer_pousser_doc("Ajout du projet test (§2)", doc_path=doc)

        assert res["statut"] == "ok", res
        assert res["commande_manuelle"] is None
        assert "Ajout du projet test" in _log(travail, "--oneline", "-1")[0]

        origin = tmp / "origin.git"
        log_origin = _log(origin, "--oneline", "-1", "master")
        assert "Ajout du projet test" in log_origin[0], (
            f"le commit doit avoir atteint origin/master, pas seulement le local : {log_origin}")
    return {"statut": res["statut"]}


def test_push_echoue_commit_local_conserve():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        travail = _init_repo_avec_origin(tmp)
        # Remote cassé APRÈS l'état initial poussé, pour isoler le push en échec
        # (réseau/conflit) du reste — le commit local doit malgré tout se faire.
        subprocess.run(["git", "remote", "set-url", "origin",
                       str(tmp / "inexistant.git")], cwd=travail, check=True)
        doc = travail / "BRIDGE_AGENT_DOC.md"
        doc.write_text(doc.read_text(encoding="utf-8") + "\nretrait du projet test\n",
                       encoding="utf-8")

        avant = _log(travail, "--oneline")
        res = rtp.committer_pousser_doc("Retrait du projet test (§2)", doc_path=doc)
        apres = _log(travail, "--oneline")

        assert res["statut"] == "push_echoue", res
        assert res["commande_manuelle"] == f"cd {travail}\ngit push"
        assert len(apres) == len(avant) + 1, (
            f"le commit local doit avoir été créé malgré le push en échec : {apres}")
        assert "Retrait du projet test" in apres[0]
    return {"statut": res["statut"], "commande_manuelle": res["commande_manuelle"]}


def test_aucun_changement_pas_de_commit_vide():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        travail = _init_repo_avec_origin(tmp)
        doc = travail / "BRIDGE_AGENT_DOC.md"

        avant = _log(travail, "--oneline")
        res = rtp.committer_pousser_doc("Ajout du projet test (§2)", doc_path=doc)
        apres = _log(travail, "--oneline")

        assert res["statut"] == "rien_a_faire", res
        assert res["commande_manuelle"] is None
        assert apres == avant, "aucun commit ne doit avoir été créé sans changement réel"
    return {"statut": res["statut"]}


def test_pas_un_depot_git_echec_propre():
    """Répertoire n'étant pas (ou plus) un dépôt git : `git diff --quiet`
    échoue avant même de savoir s'il y a un vrai changement — statut "echec",
    pas de tentative de commit."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = tmp / "BRIDGE_AGENT_DOC.md"
        doc.write_text("contenu quelconque\n", encoding="utf-8")

        res = rtp.committer_pousser_doc("Ajout du projet test (§2)", doc_path=doc)

        assert res["statut"] == "echec", res
        assert res["commande_manuelle"] is not None
    return {"statut": res["statut"]}


def main() -> int:
    tests = [
        ("commit + push réels sur origin → statut \"ok\"", test_commit_et_push_succes),
        ("push en échec (remote invalide) → commit local conservé, "
         "statut \"push_echoue\"", test_push_echoue_commit_local_conserve),
        ("aucun changement réel → aucun commit vide, statut \"rien_a_faire\"",
         test_aucun_changement_pas_de_commit_vide),
        ("répertoire pas un dépôt git → échec propre avant tout commit",
         test_pas_un_depot_git_echec_propre),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}  ({rap})")
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

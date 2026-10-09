#!/usr/bin/env python3
"""Test du garde-fou de `regenerer_tableaux_projets.regenerer()` — issue #739.

Constat d'origine : le script lit les projets dans `configs/*.conf` relatif
à son propre emplacement (`Path(__file__).resolve().parent`), sans vérifier
qu'il en trouve au moins un — une liste vide était écrite telle quelle dans
les tableaux §2/§7, vidant leur contenu réel. Reproduit deux fois (issues
#736 et #737) quand `regenerer()` a été appelé depuis un worktree CCL isolé,
dont `configs/` est gitignoré donc absent/vide hors du clone de travail
principal.

Couvre, sur des dossiers jetables sous `/tmp` (jamais sur le vrai
`configs/`/`BRIDGE_AGENT_DOC.md` du dépôt) :
- dossier de configs absent, vide, ou ne contenant que des `.conf` sans
  champ NOM valide : le document reste identique OCTET POUR OCTET, `erreur`
  est renvoyée, `modifie` est False ;
- avec des `.conf` valides : comportement inchangé (tableaux régénérés,
  `erreur` est None) ;
- `main()` (CLI) : code de sortie non nul dans le cas vide.

Exécution :  python3 tests/test_garde_fou_aucun_conf_739.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import io
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import regenerer_tableaux_projets as rtp  # noqa: E402

DOC_FIXTURE = """# BRIDGE_AGENT_DOC

## 2. Projets actifs

<!-- DEBUT:TABLEAU_PROJETS_ACTIFS (généré automatiquement par regenerer_tableaux_projets.py
     depuis configs/*.conf) -->
| Nom | Dépôt GitHub | Répertoire de travail CCL | Topic ntfy | Couleur |
|-----|-------------|--------------------------|------------|---------|
| `existant` | AlainDelree/Existant | ~/Existant | (conf local) | `#123456` |
<!-- FIN:TABLEAU_PROJETS_ACTIFS -->

## 7. Périmètre par projet

<!-- DEBUT:TABLEAU_PERIMETRE_PROJETS (généré automatiquement par regenerer_tableaux_projets.py
     depuis configs/*.conf) -->
| Projet | Périmètre autorisé |
|--------|-------------------|
| `existant` | /home/alain/Existant |
<!-- FIN:TABLEAU_PERIMETRE_PROJETS -->

---

*Dernière mise à jour : 1 janvier 2020 — version de départ du test.*
"""


def _ecrire_doc(tmp: Path) -> Path:
    doc = tmp / "BRIDGE_AGENT_DOC.md"
    doc.write_text(DOC_FIXTURE, encoding="utf-8")
    return doc


def _conf_valide(dossier: Path, nom: str) -> None:
    (dossier / f"{nom}.conf").write_text(
        f"NOM = {nom}\nDEPOT = AlainDelree/{nom.capitalize()}\n"
        f"REP_TRAVAIL = /home/alain/{nom.capitalize()}\n",
        encoding="utf-8")


def test_dossier_configs_absent_doc_inchange():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        avant = doc.read_bytes()
        dossier_configs_absent = tmp / "configs_inexistant"

        res = rtp.regenerer(doc_path=doc, dossier_configs=dossier_configs_absent)

        assert res["modifie"] is False, res
        assert res["erreur"] is not None and "aucun projet" in res["erreur"], res
        assert res["n_projets"] == 0, res
        assert doc.read_bytes() == avant, "le document ne doit pas être touché"
    return {"erreur": res["erreur"]}


def test_dossier_configs_vide_doc_inchange():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        avant = doc.read_bytes()
        dossier_configs = tmp / "configs"
        dossier_configs.mkdir()

        res = rtp.regenerer(doc_path=doc, dossier_configs=dossier_configs)

        assert res["modifie"] is False, res
        assert res["erreur"] is not None, res
        assert doc.read_bytes() == avant
    return {"erreur": res["erreur"]}


def test_configs_sans_nom_valide_doc_inchange():
    """.conf présent mais sans champ NOM (ex. ccw_ssh.conf réel) — ignoré
    silencieusement par lire_projets(), donc liste vide malgré tout."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        avant = doc.read_bytes()
        dossier_configs = tmp / "configs"
        dossier_configs.mkdir()
        (dossier_configs / "ccw_ssh.conf").write_text(
            "HOTE = 192.168.1.1\nPORT = 22\n", encoding="utf-8")

        res = rtp.regenerer(doc_path=doc, dossier_configs=dossier_configs)

        assert res["modifie"] is False, res
        assert res["erreur"] is not None, res
        assert doc.read_bytes() == avant
    return {"erreur": res["erreur"]}


def test_configs_valides_comportement_inchange():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        dossier_configs = tmp / "configs"
        dossier_configs.mkdir()
        _conf_valide(dossier_configs, "nouveauprojet")

        res = rtp.regenerer(doc_path=doc, dossier_configs=dossier_configs)

        assert res["erreur"] is None, res
        assert res["modifie"] is True, res
        assert res["n_projets"] == 1, res
        texte = doc.read_text(encoding="utf-8")
        assert "`nouveauprojet`" in texte
        assert "`existant`" not in texte, "l'ancien contenu doit être remplacé, pas conservé"
    return {"n_projets": res["n_projets"]}


def test_cli_code_sortie_non_nul_cas_vide():
    """main() affiche l'erreur et rend un code non nul quand regenerer()
    renvoie une erreur — stub de regenerer() pour ne jamais toucher au vrai
    BRIDGE_AGENT_DOC.md/configs du dépôt depuis ce test."""
    original = rtp.regenerer
    rtp.regenerer = lambda: {  # noqa: E731
        "existe": True, "modifie": False,
        "erreur": "aucun projet trouvé dans configs/ : régénération annulée, document inchangé.",
        "n_projets": 0, "projets": [],
    }
    try:
        sortie = io.StringIO()
        with redirect_stdout(sortie):
            code = rtp.main()
    finally:
        rtp.regenerer = original

    assert code != 0, f"code de sortie attendu non nul, obtenu {code}"
    assert "aucun projet" in sortie.getvalue()
    return {"code": code}


def main() -> int:
    tests = [
        ("dossier configs absent → doc inchangé octet pour octet, erreur renvoyée",
         test_dossier_configs_absent_doc_inchange),
        ("dossier configs vide → doc inchangé, erreur renvoyée",
         test_dossier_configs_vide_doc_inchange),
        ("configs/*.conf sans champ NOM valide → doc inchangé, erreur renvoyée",
         test_configs_sans_nom_valide_doc_inchange),
        (".conf valide présent → comportement inchangé (régénération normale)",
         test_configs_valides_comportement_inchange),
        ("CLI (main()) → code de sortie non nul dans le cas vide",
         test_cli_code_sortie_non_nul_cas_vide),
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

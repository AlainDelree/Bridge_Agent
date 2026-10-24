#!/usr/bin/env python3
"""Test de la ligne de relecture `<nom>_ccw` du tableau §2 — issue #804.

Contexte : l'outil de relecture (`relecture_web`) ne traite un projet comme
distant (PC Windows, SSH) que si son répertoire de travail, dans le tableau
§2 de BRIDGE_AGENT_DOC.md, est un chemin Windows en barres obliques inverses
(`C:\\CCW\\rummikub`). Un projet qui a un clone Windows dédié reçoit
désormais une clé optionnelle `REP_TRAVAIL_CCW` dans son `.conf` — JAMAIS un
second `.conf` (qui créerait un second watcher/projet partout ailleurs dans
le code, cf. BRIDGE_AGENT_DOC.md et la docstring de
`regenerer_tableaux_projets.py`) — et `regenerer_tableaux_projets.py` en
déduit une seconde ligne `<nom>_ccw`, réservée à la relecture, dans le
tableau §2 uniquement.

Couvre, sur des dossiers jetables sous `/tmp` (jamais sur le vrai
`configs/`/`BRIDGE_AGENT_DOC.md` du dépôt, même technique que
tests/test_garde_fou_aucun_conf_739.py) :
- projet AVEC REP_TRAVAIL_CCW → ligne `<nom>_ccw` ajoutée, juste après la
  ligne du projet (ordre), chemin affiché en barres obliques inverses même
  si saisi avec des barres obliques normales dans le `.conf` ;
- projet SANS cette clé → aucune ligne `_ccw`, comportement inchangé ;
- aucune des deux lignes `<nom>_ccw` n'apparaît dans le tableau §7 ;
- couleur de la ligne `_ccw` : distincte de celle du projet ET de toutes les
  autres couleurs en usage (plusieurs projets `_ccw` simultanément), stable
  (deux régénérations successives sur le même `.conf` → même couleur).

Exécution :  python3 tests/test_tableau_ccw_804.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import re
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import regenerer_tableaux_projets as rtp  # noqa: E402

DOC_FIXTURE = """# BRIDGE_AGENT_DOC

## 2. Projets actifs

<!-- DEBUT:TABLEAU_PROJETS_ACTIFS (test) -->
old
<!-- FIN:TABLEAU_PROJETS_ACTIFS -->

## 7. Périmètre par projet

<!-- DEBUT:TABLEAU_PERIMETRE_PROJETS (test) -->
old
<!-- FIN:TABLEAU_PERIMETRE_PROJETS -->

---

*Dernière mise à jour : 1 janvier 2020 — version de départ du test.*
"""


def _ecrire_doc(tmp: Path) -> Path:
    doc = tmp / "BRIDGE_AGENT_DOC.md"
    doc.write_text(DOC_FIXTURE, encoding="utf-8")
    return doc


def _conf(dossier: Path, nom: str, depot: str, rep: str, rep_ccw: str = "") -> None:
    contenu = f"NOM = {nom}\nDEPOT = {depot}\nREP_TRAVAIL = {rep}\n"
    if rep_ccw:
        contenu += f"REP_TRAVAIL_CCW = {rep_ccw}\n"
    (dossier / f"{nom}.conf").write_text(contenu, encoding="utf-8")


def _lignes_actives(texte: str) -> list[str]:
    bloc = texte.split("<!-- DEBUT:TABLEAU_PROJETS_ACTIFS", 1)[1]
    bloc = bloc.split("<!-- FIN:TABLEAU_PROJETS_ACTIFS -->", 1)[0]
    return [l for l in bloc.splitlines() if l.startswith("| `")]


def test_projet_avec_cle_ajoute_ligne_ccw_apres_la_sienne():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        configs = tmp / "configs"
        configs.mkdir()
        _conf(configs, "rummikub", "AlainDelree/Rummikub", "/home/alain/Rummikub",
              rep_ccw="C:\\CCW\\rummikub")
        _conf(configs, "scrabble", "AlainDelree/Scrabble", "/home/alain/Scrabble")

        res = rtp.regenerer(doc_path=doc, dossier_configs=configs)
        assert res["erreur"] is None, res

        texte = doc.read_text(encoding="utf-8")
        lignes = _lignes_actives(texte)
        noms = [l.split("|")[1].strip().strip("`") for l in lignes]
        assert noms == ["rummikub", "rummikub_ccw", "scrabble"], noms

        ligne_ccw = lignes[1]
        assert "AlainDelree/Rummikub" in ligne_ccw, ligne_ccw
        assert "C:\\CCW\\rummikub" in ligne_ccw, ligne_ccw
    return {"noms": noms}


def test_projet_sans_cle_aucune_ligne_ccw():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        configs = tmp / "configs"
        configs.mkdir()
        _conf(configs, "scrabble", "AlainDelree/Scrabble", "/home/alain/Scrabble")

        res = rtp.regenerer(doc_path=doc, dossier_configs=configs)
        assert res["erreur"] is None, res

        texte = doc.read_text(encoding="utf-8")
        assert "_ccw" not in texte, "aucune ligne _ccw attendue sans REP_TRAVAIL_CCW"
        assert res["n_projets"] == 1, (
            "n_projets doit compter les vrais projets uniquement, jamais une ligne _ccw")
    return {"n_projets": res["n_projets"]}


def test_chemin_barres_obliques_normales_normalise():
    """.conf saisi à la main avec des barres obliques NORMALES (C:/CCW/...) —
    la ligne générée doit malgré tout utiliser des barres obliques inverses,
    seul format reconnu par relecture_web."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        configs = tmp / "configs"
        configs.mkdir()
        _conf(configs, "rummikub", "AlainDelree/Rummikub", "/home/alain/Rummikub",
              rep_ccw="C:/CCW/rummikub")

        res = rtp.regenerer(doc_path=doc, dossier_configs=configs)
        assert res["erreur"] is None, res
        texte = doc.read_text(encoding="utf-8")
        assert "C:\\CCW\\rummikub" in texte, texte
        assert "C:/CCW/rummikub" not in texte, texte
    return {}


def test_ligne_ccw_absente_du_tableau_perimetre():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        configs = tmp / "configs"
        configs.mkdir()
        _conf(configs, "rummikub", "AlainDelree/Rummikub", "/home/alain/Rummikub",
              rep_ccw="C:\\CCW\\rummikub")

        res = rtp.regenerer(doc_path=doc, dossier_configs=configs)
        assert res["erreur"] is None, res
        texte = doc.read_text(encoding="utf-8")
        bloc_perimetre = texte.split("<!-- DEBUT:TABLEAU_PERIMETRE_PROJETS", 1)[1]
        bloc_perimetre = bloc_perimetre.split("<!-- FIN:TABLEAU_PERIMETRE_PROJETS -->", 1)[0]
        assert "rummikub_ccw" not in bloc_perimetre, bloc_perimetre
        assert "`rummikub`" in bloc_perimetre, bloc_perimetre
    return {}


def _couleurs(texte: str) -> dict[str, str]:
    lignes = _lignes_actives(texte)
    paires = {}
    for ligne in lignes:
        m = re.match(r"\| `([^`]+)` \|.*\| `(#[0-9A-Fa-f]{6})` \|", ligne)
        assert m, ligne
        paires[m.group(1)] = m.group(2)
    return paires


def test_couleur_ccw_distincte_et_stable():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        doc = _ecrire_doc(tmp)
        configs = tmp / "configs"
        configs.mkdir()
        _conf(configs, "alchess", "AlainDelree/AlChess", "/home/alain/NicLink",
              rep_ccw="C:\\CCW\\alchess")
        _conf(configs, "rummikub", "AlainDelree/Rummikub", "/home/alain/Rummikub",
              rep_ccw="C:\\CCW\\rummikub")
        _conf(configs, "scrabble", "AlainDelree/Scrabble", "/home/alain/Scrabble")

        res1 = rtp.regenerer(doc_path=doc, dossier_configs=configs)
        assert res1["erreur"] is None, res1
        couleurs_1 = _couleurs(doc.read_text(encoding="utf-8"))

        # Deuxième passage, .conf inchangés -> doit retomber EXACTEMENT sur
        # les mêmes couleurs (stabilité).
        res2 = rtp.regenerer(doc_path=doc, dossier_configs=configs)
        assert res2["erreur"] is None, res2
        couleurs_2 = _couleurs(doc.read_text(encoding="utf-8"))
        assert couleurs_1 == couleurs_2, (couleurs_1, couleurs_2)

        assert couleurs_1["alchess_ccw"] != couleurs_1["alchess"], couleurs_1
        assert couleurs_1["rummikub_ccw"] != couleurs_1["rummikub"], couleurs_1
        assert couleurs_1["alchess_ccw"] != couleurs_1["rummikub_ccw"], couleurs_1
        assert len(set(couleurs_1.values())) == len(couleurs_1), (
            f"collision de couleur détectée : {couleurs_1}")
    return {"couleurs": couleurs_1}


def main() -> int:
    tests = [
        ("projet avec REP_TRAVAIL_CCW → ligne `<nom>_ccw` juste après la sienne",
         test_projet_avec_cle_ajoute_ligne_ccw_apres_la_sienne),
        ("projet sans REP_TRAVAIL_CCW → aucune ligne _ccw, n_projets inchangé",
         test_projet_sans_cle_aucune_ligne_ccw),
        ("chemin à barres obliques normales → normalisé en barres inverses",
         test_chemin_barres_obliques_normales_normalise),
        ("ligne _ccw absente du tableau §7 (périmètre)",
         test_ligne_ccw_absente_du_tableau_perimetre),
        ("couleur de la ligne _ccw : distincte de toutes les autres, stable",
         test_couleur_ccw_distincte_et_stable),
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

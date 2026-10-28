#!/usr/bin/env python3
"""Test de non-régression — issue #825 : l'onglet « En attente » ne
rechargeait sa liste, tant qu'il restait ouvert, que si le NOMBRE
d'éléments de `en_attente/` changeait (`nb_en_attente`, issue #713/#705).
Quand Alain écrase un fichier par une version corrigée de la MÊME issue
(même nom, cf. `_remplacer_item_en_attente`, issue #820), ce nombre ne
change pas : titre/projet/condition/date affichés restaient périmés
jusqu'à un F5.

Cette issue ajoute `signature_attente` (app/issues_inbox.py::
_signature_attente), calculée à partir du nom/mtime/taille de chaque
fichier de `en_attente/` — elle change dès qu'un fichier est ajouté,
retiré ou remplacé, y compris sous le même nom. `GET /issues-inbox/etat`
l'expose au même titre que `nb_en_attente` ; `static/js/attente.js` s'y
abonne en plus du compteur pour déclencher le rechargement (couvert côté
JS par `static/js/tests/attente.test.js::fautRechargerAttente`).

Couvre :
- `_signature_attente` : dossier absent → chaîne vide ; stable à l'identique
  (deux lectures sans changement) ; change sur ajout, retrait, et
  remplacement de contenu sous le même nom (mtime et/ou taille modifiés) ;
  ignore le sous-dossier `.ordre` (DOSSIER_ORDRE_ATTENTE, #819) ;
- `GET /issues-inbox/etat` : expose `signature_attente`, inchangé par un
  simple déplacement (`_ecrire_ordre_attente`), changé par un remplacement
  de fichier qui laisse `nb_en_attente` inchangé.

Aucun appel réseau ni `gh` réel.

Exécution :  python3 tests/test_signature_attente_825.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402

import app.issues_inbox as ii  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402

APP_FLASK = flask.Flask(__name__)


def _route_cfg(tmp: Path) -> "w.ConfigInbox":
    cfg = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                         rejected_dir=tmp / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.en_attente_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _ecrire(chemin: Path, contenu: str, age_s: float) -> None:
    chemin.write_text(contenu, encoding="utf-8")
    t = time.time() - age_s
    os.utime(chemin, (t, t))


# ─── 1. _signature_attente — fonction pure sur le disque ──────────────────

def test_dossier_absent_chaine_vide(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                         rejected_dir=tmp / "issues_inbox" / "rejected")
    assert ii._signature_attente(cfg) == ""
    return {}


def test_dossier_vide_chaine_vide(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    assert ii._signature_attente(cfg) == ""
    return {}


def test_stable_sans_changement(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _ecrire(cfg.en_attente_dir / "a.txt", "contenu a", 10)
    _ecrire(cfg.en_attente_dir / "b.txt", "contenu b", 5)
    sig1 = ii._signature_attente(cfg)
    sig2 = ii._signature_attente(cfg)
    assert sig1 == sig2, (sig1, sig2)
    assert sig1 != ""
    return {"signature": sig1}


def test_change_sur_ajout(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _ecrire(cfg.en_attente_dir / "a.txt", "contenu a", 10)
    avant = ii._signature_attente(cfg)
    _ecrire(cfg.en_attente_dir / "b.txt", "contenu b", 5)
    apres = ii._signature_attente(cfg)
    assert avant != apres, (avant, apres)
    return {}


def test_change_sur_retrait(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _ecrire(cfg.en_attente_dir / "a.txt", "contenu a", 10)
    cible = cfg.en_attente_dir / "b.txt"
    _ecrire(cible, "contenu b", 5)
    avant = ii._signature_attente(cfg)
    cible.unlink()
    apres = ii._signature_attente(cfg)
    assert avant != apres, (avant, apres)
    return {}


def test_change_sur_remplacement_meme_nom_mtime_et_taille_differentes(tmp_dir_factory):
    """Le cas visé par l'issue : Alain écrase un fichier d'en_attente/ par
    une version modifiée de la MÊME issue (même nom, cf.
    _remplacer_item_en_attente, #820) — le NOMBRE d'éléments ne change pas,
    mais la signature doit changer."""
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    cible = cfg.en_attente_dir / "mono.txt"
    _ecrire(cible, "| PROJET | bridge_agent |\n| ATTENTE | ancienne |\n\n#Titre: T.\nAncien corps.\n", 20)
    avant = ii._signature_attente(cfg)
    nb_avant = ii._nb_en_attente(cfg)

    _ecrire(cible, "| PROJET | bridge_agent |\n| ATTENTE | nouvelle |\n\n#Titre: T.\nNouveau corps, plus long.\n", 0)
    apres = ii._signature_attente(cfg)
    nb_apres = ii._nb_en_attente(cfg)

    assert nb_avant == nb_apres == 1, (nb_avant, nb_apres)
    assert avant != apres, "la signature doit changer même si le nombre ne change pas"
    return {"avant": avant, "apres": apres}


def test_change_sur_remplacement_meme_taille_mtime_differente(tmp_dir_factory):
    """Même LONGUEUR de contenu (donc même taille), seule la date de
    modification change — la signature doit tout de même changer (elle ne
    dépend pas QUE de la taille)."""
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    cible = cfg.en_attente_dir / "mono.txt"
    _ecrire(cible, "contenu identique", 20)
    avant = ii._signature_attente(cfg)

    _ecrire(cible, "contenu identiquf", 0)  # même longueur, contenu différent
    apres = ii._signature_attente(cfg)

    assert avant != apres, (avant, apres)
    return {}


def test_ignore_sous_dossier_ordre(tmp_dir_factory):
    """Le sous-dossier .ordre/ (DOSSIER_ORDRE_ATTENTE, #819) n'est jamais un
    fichier d'issue — écrire l'ordre persisté ne doit pas changer la
    signature."""
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _ecrire(cfg.en_attente_dir / "a.txt", "contenu a", 10)
    _ecrire(cfg.en_attente_dir / "b.txt", "contenu b", 5)
    avant = ii._signature_attente(cfg)

    w._ecrire_ordre_attente(cfg, ["b.txt", "a.txt"])
    assert (cfg.en_attente_dir / w.DOSSIER_ORDRE_ATTENTE).is_dir()

    apres = ii._signature_attente(cfg)
    assert avant == apres, (avant, apres)
    return {}


# ─── 2. Route GET /issues-inbox/etat ───────────────────────────────────────

def test_route_etat_inbox_expose_signature_attente(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _ecrire(cfg.en_attente_dir / "a.txt", "contenu a", 10)
    ii.CHEMIN_PID = tmp / "logs" / "watcher-inexistant.pid"
    ii._config = lambda: cfg

    with APP_FLASK.test_request_context("/issues-inbox/etat"):
        rep = ii.etat_inbox()
    corps = rep.get_json()
    assert "signature_attente" in corps, corps
    assert corps["signature_attente"] != "", corps
    return {"signature_attente": corps["signature_attente"]}


def test_route_etat_inbox_signature_changee_par_remplacement_nombre_inchange(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    cible = cfg.en_attente_dir / "mono.txt"
    _ecrire(cible, "| PROJET | bridge_agent |\n| ATTENTE | ancienne |\n\n#Titre: T.\nAncien.\n", 20)
    ii.CHEMIN_PID = tmp / "logs" / "watcher-inexistant.pid"
    ii._config = lambda: cfg

    with APP_FLASK.test_request_context("/issues-inbox/etat"):
        avant = ii.etat_inbox().get_json()

    _ecrire(cible, "| PROJET | bridge_agent |\n| ATTENTE | nouvelle, bien plus longue |\n\n#Titre: T.\nNouveau.\n", 0)

    with APP_FLASK.test_request_context("/issues-inbox/etat"):
        apres = ii.etat_inbox().get_json()

    assert avant["nb_en_attente"] == apres["nb_en_attente"] == 1
    assert avant["signature_attente"] != apres["signature_attente"], (avant, apres)
    return {}


def test_route_etat_inbox_signature_inchangee_par_simple_deplacement(tmp_dir_factory):
    tmp = tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _ecrire(cfg.en_attente_dir / "a.txt", "contenu a", 10)
    _ecrire(cfg.en_attente_dir / "b.txt", "contenu b", 5)
    ii.CHEMIN_PID = tmp / "logs" / "watcher-inexistant.pid"
    ii._config = lambda: cfg

    with APP_FLASK.test_request_context("/issues-inbox/etat"):
        avant = ii.etat_inbox().get_json()

    w._ecrire_ordre_attente(cfg, ["b.txt", "a.txt"])

    with APP_FLASK.test_request_context("/issues-inbox/etat"):
        apres = ii.etat_inbox().get_json()

    assert avant["signature_attente"] == apres["signature_attente"], (avant, apres)
    return {}


def main() -> int:
    tmp_racine = tempfile.TemporaryDirectory()
    compteur = {"n": 0}

    def tmp_dir_factory():
        compteur["n"] += 1
        chemin = Path(tmp_racine.name) / f"t{compteur['n']}"
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    tests = [
        ("_signature_attente : dossier absent → chaîne vide", test_dossier_absent_chaine_vide),
        ("_signature_attente : dossier vide → chaîne vide", test_dossier_vide_chaine_vide),
        ("_signature_attente : stable sans changement", test_stable_sans_changement),
        ("_signature_attente : change sur ajout", test_change_sur_ajout),
        ("_signature_attente : change sur retrait", test_change_sur_retrait),
        ("_signature_attente : change sur remplacement (mtime+taille)", test_change_sur_remplacement_meme_nom_mtime_et_taille_differentes),
        ("_signature_attente : change sur remplacement (même taille, mtime différente)", test_change_sur_remplacement_meme_taille_mtime_differente),
        ("_signature_attente : ignore le sous-dossier .ordre", test_ignore_sous_dossier_ordre),
        ("route /issues-inbox/etat : expose signature_attente", test_route_etat_inbox_expose_signature_attente),
        ("route /issues-inbox/etat : signature changée par remplacement, nombre inchangé", test_route_etat_inbox_signature_changee_par_remplacement_nombre_inchange),
        ("route /issues-inbox/etat : signature inchangée par un simple déplacement", test_route_etat_inbox_signature_inchangee_par_simple_deplacement),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn(tmp_dir_factory)
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")

    tmp_racine.cleanup()
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

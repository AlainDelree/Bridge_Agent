#!/usr/bin/env python3
"""Test de non-régression — issue #819 : ordre MANUEL de l'onglet « En attente »
(boutons monter/descendre, suite #713/#714).

Couvre :
- fonction pure `app.issues_inbox.fusionner_ordre_attente` : ordre mémorisé
  respecté, nouveaux venus ajoutés en fin de liste (plus ancien au plus
  récent), identifiants disparus (lancés/supprimés) abandonnés sans trace ;
- `GET /issues-attente` : repli sur le plus ancien au plus récent en l'absence
  de tout ordre mémorisé (non-régression #713), ordre mémorisé respecté une
  fois un déplacement effectué, auto-guérison (purge des identifiants
  disparus, incorporation des nouveaux venus) à chaque lecture ;
- `POST /issues-attente/deplacer` : échange avec le voisin direct, no-op aux
  deux bords de la liste (toujours un succès, `deplace: false`), identifiant/
  sens invalides refusés, persistance effective sur disque (survit à un
  « redémarrage », simulé par un nouvel appel sans état en mémoire) ;
- le fichier d'ordre est rangé dans un SOUS-DOSSIER d'en_attente/ (jamais un
  fichier directement dans le dossier) : `nb_en_attente` et la liste ne le
  comptent/n'y voient jamais une issue, un déplacement ne modifie jamais le
  CONTENU d'un fichier en attente.

Exécution :  python3 tests/test_ordre_attente_819.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402
import pytest  # noqa: E402

import app.issues_inbox as ii  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402

APP_FLASK = flask.Flask(__name__)


@pytest.fixture
def _tmp_dir_factory(tmp_path_factory):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        return tmp_path_factory.mktemp(f"ordre{compteur['n']}")
    return _make


def _route_cfg(tmp: Path) -> "w.ConfigInbox":
    cfg = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                         rejected_dir=tmp / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.en_attente_dir.mkdir(parents=True, exist_ok=True)
    ii._config = lambda: cfg
    return cfg


def _deposer_attente(cfg, nom: str, age_s: float, condition: str = "x", projet: str = "bridge_agent") -> Path:
    chemin = cfg.en_attente_dir / nom
    chemin.write_text(
        f"| PROJET | {projet} |\n| ATTENTE | {condition} |\n\n#Titre: {nom}.\nCorps.\n",
        encoding="utf-8")
    os.utime(chemin, (time.time() - age_s, time.time() - age_s))
    return chemin


# ─── 1. Fonction pure fusionner_ordre_attente ──────────────────────────────

def test_fusion_sans_ordre_persiste_repli_plus_ancien_d_abord():
    items = [{"id": "b.txt", "date": 10}, {"id": "a.txt", "date": 5}]
    assert ii.fusionner_ordre_attente([], items) == ["a.txt", "b.txt"]
    return {}


def test_fusion_respecte_l_ordre_persiste():
    items = [{"id": "a.txt", "date": 1}, {"id": "b.txt", "date": 2}, {"id": "c.txt", "date": 3}]
    ordre = ii.fusionner_ordre_attente(["c.txt", "a.txt", "b.txt"], items)
    assert ordre == ["c.txt", "a.txt", "b.txt"], ordre
    return {}


def test_fusion_nouveau_venu_ajoute_en_fin():
    items = [{"id": "a.txt", "date": 1}, {"id": "b.txt", "date": 2}, {"id": "nouveau.txt", "date": 99}]
    ordre = ii.fusionner_ordre_attente(["b.txt", "a.txt"], items)
    assert ordre == ["b.txt", "a.txt", "nouveau.txt"], ordre
    return {}


def test_fusion_plusieurs_nouveaux_venus_tries_plus_ancien_d_abord():
    items = [{"id": "connu.txt", "date": 1}, {"id": "recent.txt", "date": 50}, {"id": "ancien.txt", "date": 10}]
    ordre = ii.fusionner_ordre_attente(["connu.txt"], items)
    assert ordre == ["connu.txt", "ancien.txt", "recent.txt"], ordre
    return {}


def test_fusion_identifiant_disparu_abandonne_sans_trace():
    items = [{"id": "a.txt", "date": 1}, {"id": "b.txt", "date": 2}]
    ordre = ii.fusionner_ordre_attente(["lance.txt", "b.txt", "supprime.txt", "a.txt"], items)
    assert ordre == ["b.txt", "a.txt"], ordre
    assert "lance.txt" not in ordre and "supprime.txt" not in ordre
    return {}


# ─── 2. Route GET /issues-attente ──────────────────────────────────────────

def test_liste_sans_deplacement_plus_ancien_d_abord(_tmp_dir_factory):
    """Non-régression #713 : tant qu'Alain n'a jamais rien déplacé, l'ordre
    reste celui du dépôt (mtime), même après un premier appel qui persiste
    désormais un fichier d'ordre (auto-guérison)."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "recent.txt", 5)
    _deposer_attente(cfg, "ancien.txt", 50)

    with APP_FLASK.test_request_context("/issues-attente"):
        rep = ii.issues_attente_liste()
    items = rep.get_json()["items"]
    assert [it["id"] for it in items] == ["ancien.txt", "recent.txt"], items
    return {}


def test_liste_respecte_un_ordre_deja_persiste(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 10)
    _deposer_attente(cfg, "b.txt", 5)
    ii._ecrire_ordre_attente(cfg, ["b.txt", "a.txt"])

    with APP_FLASK.test_request_context("/issues-attente"):
        rep = ii.issues_attente_liste()
    items = rep.get_json()["items"]
    assert [it["id"] for it in items] == ["b.txt", "a.txt"], items
    return {}


def test_liste_purge_les_identifiants_disparus_de_l_ordre_persiste(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 10)
    ii._ecrire_ordre_attente(cfg, ["disparu.txt", "a.txt"])

    with APP_FLASK.test_request_context("/issues-attente"):
        rep = ii.issues_attente_liste()
    assert [it["id"] for it in rep.get_json()["items"]] == ["a.txt"]
    ordre_relu = ii._lire_ordre_attente_persiste(cfg)
    assert ordre_relu == ["a.txt"], ordre_relu
    return {}


def test_fichier_d_ordre_jamais_compte_ni_affiche(_tmp_dir_factory):
    """Le sous-dossier d'ordre, une fois créé par un premier appel, ne doit
    jamais apparaître dans la liste ni dans nb_en_attente (#819, point
    d'attention)."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 10)

    with APP_FLASK.test_request_context("/issues-attente"):
        ii.issues_attente_liste()
    assert ii._chemin_ordre_attente(cfg).exists(), "le fichier d'ordre doit avoir été écrit"

    with APP_FLASK.test_request_context("/issues-attente"):
        rep = ii.issues_attente_liste()
    assert [it["id"] for it in rep.get_json()["items"]] == ["a.txt"]
    assert ii._nb_en_attente(cfg) == 1, "le fichier d'ordre ne doit jamais être compté"
    return {}


def test_deplacement_ne_modifie_jamais_le_contenu_d_un_fichier(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 10)
    _deposer_attente(cfg, "b.txt", 5)
    avant = (cfg.en_attente_dir / "a.txt").read_text(encoding="utf-8")

    with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                         json={"id": "a.txt", "sens": "bas"}):
        ii.issues_attente_deplacer()

    assert (cfg.en_attente_dir / "a.txt").read_text(encoding="utf-8") == avant
    return {}


# ─── 3. Route POST /issues-attente/deplacer ────────────────────────────────

def test_deplacer_echange_avec_le_voisin(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 30)
    _deposer_attente(cfg, "b.txt", 20)
    _deposer_attente(cfg, "c.txt", 10)
    # Ordre initial (mtime) : a, b, c.

    with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                         json={"id": "c.txt", "sens": "haut"}):
        rep = ii.issues_attente_deplacer()
    corps = rep.get_json()
    assert corps["succes"] is True and corps["deplace"] is True, corps

    with APP_FLASK.test_request_context("/issues-attente"):
        items = ii.issues_attente_liste().get_json()["items"]
    assert [it["id"] for it in items] == ["a.txt", "c.txt", "b.txt"], items
    return {"ordre": [it["id"] for it in items]}


def test_deplacer_haut_sur_le_premier_est_un_no_op(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 20)
    _deposer_attente(cfg, "b.txt", 10)

    with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                         json={"id": "a.txt", "sens": "haut"}):
        rep = ii.issues_attente_deplacer()
    corps = rep.get_json()
    assert corps["succes"] is True and corps["deplace"] is False, corps

    with APP_FLASK.test_request_context("/issues-attente"):
        items = ii.issues_attente_liste().get_json()["items"]
    assert [it["id"] for it in items] == ["a.txt", "b.txt"], items
    return {}


def test_deplacer_bas_sur_le_dernier_est_un_no_op(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 20)
    _deposer_attente(cfg, "b.txt", 10)

    with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                         json={"id": "b.txt", "sens": "bas"}):
        rep = ii.issues_attente_deplacer()
    corps = rep.get_json()
    assert corps["succes"] is True and corps["deplace"] is False, corps
    return {}


def test_deplacer_identifiant_introuvable_404(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    _route_cfg(tmp)
    with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                         json={"id": "absent.txt", "sens": "haut"}):
        rep, code = ii.issues_attente_deplacer()
    assert code == 404
    assert rep.get_json()["succes"] is False
    return {}


def test_deplacer_identifiant_avec_separateur_refuse(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    _route_cfg(tmp)
    for identifiant in ("../evasion.txt", "sous/dossier.txt", "sous\\dossier.txt", "..", ""):
        with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                             json={"id": identifiant, "sens": "haut"}):
            rep, code = ii.issues_attente_deplacer()
        assert code == 400, (identifiant, code)
    return {}


def test_deplacer_sens_invalide_refuse(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 10)
    with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                         json={"id": "a.txt", "sens": "gauche"}):
        rep, code = ii.issues_attente_deplacer()
    assert code == 400
    assert rep.get_json()["succes"] is False
    return {}


def test_ordre_survit_a_un_redemarrage_simule(_tmp_dir_factory):
    """Aucun état en mémoire : relire _config()/le disque après un déplacement
    (nouvel appel indépendant, comme un nouveau process new_issue.py) doit
    retrouver exactement l'ordre choisi."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer_attente(cfg, "a.txt", 30)
    _deposer_attente(cfg, "b.txt", 20)
    _deposer_attente(cfg, "c.txt", 10)

    with APP_FLASK.test_request_context("/issues-attente/deplacer", method="POST",
                                         json={"id": "a.txt", "sens": "bas"}):
        ii.issues_attente_deplacer()

    # « Redémarrage » : nouvelle ConfigInbox pointant sur le même dossier disque.
    cfg_relue = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                               rejected_dir=tmp / "issues_inbox" / "rejected")
    ii._config = lambda: cfg_relue

    with APP_FLASK.test_request_context("/issues-attente"):
        items = ii.issues_attente_liste().get_json()["items"]
    assert [it["id"] for it in items] == ["b.txt", "a.txt", "c.txt"], items
    return {}


def main() -> int:
    tmp_racine = tempfile.TemporaryDirectory()
    compteur = {"n": 0}

    def __tmp_dir_factory():
        compteur["n"] += 1
        chemin = Path(tmp_racine.name) / f"t{compteur['n']}"
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    tests = [
        ("fusion : sans ordre persisté → plus ancien d'abord", test_fusion_sans_ordre_persiste_repli_plus_ancien_d_abord),
        ("fusion : respecte l'ordre persisté", test_fusion_respecte_l_ordre_persiste),
        ("fusion : nouveau venu ajouté en fin", test_fusion_nouveau_venu_ajoute_en_fin),
        ("fusion : plusieurs nouveaux venus, triés plus ancien d'abord", test_fusion_plusieurs_nouveaux_venus_tries_plus_ancien_d_abord),
        ("fusion : identifiant disparu abandonné sans trace", test_fusion_identifiant_disparu_abandonne_sans_trace),
        ("liste : sans déplacement → plus ancien d'abord", lambda: test_liste_sans_deplacement_plus_ancien_d_abord(__tmp_dir_factory)),
        ("liste : respecte un ordre déjà persisté", lambda: test_liste_respecte_un_ordre_deja_persiste(__tmp_dir_factory)),
        ("liste : purge les identifiants disparus", lambda: test_liste_purge_les_identifiants_disparus_de_l_ordre_persiste(__tmp_dir_factory)),
        ("liste : fichier d'ordre jamais compté ni affiché", lambda: test_fichier_d_ordre_jamais_compte_ni_affiche(__tmp_dir_factory)),
        ("déplacement : ne modifie jamais le contenu d'un fichier", lambda: test_deplacement_ne_modifie_jamais_le_contenu_d_un_fichier(__tmp_dir_factory)),
        ("deplacer : échange avec le voisin", lambda: test_deplacer_echange_avec_le_voisin(__tmp_dir_factory)),
        ("deplacer : haut sur le premier → no-op", lambda: test_deplacer_haut_sur_le_premier_est_un_no_op(__tmp_dir_factory)),
        ("deplacer : bas sur le dernier → no-op", lambda: test_deplacer_bas_sur_le_dernier_est_un_no_op(__tmp_dir_factory)),
        ("deplacer : identifiant introuvable → 404", lambda: test_deplacer_identifiant_introuvable_404(__tmp_dir_factory)),
        ("deplacer : séparateur de chemin refusé", lambda: test_deplacer_identifiant_avec_separateur_refuse(__tmp_dir_factory)),
        ("deplacer : sens invalide refusé", lambda: test_deplacer_sens_invalide_refuse(__tmp_dir_factory)),
        ("ordre : survit à un redémarrage simulé", lambda: test_ordre_survit_a_un_redemarrage_simule(__tmp_dir_factory)),
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

    tmp_racine.cleanup()
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

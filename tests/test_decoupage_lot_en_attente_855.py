#!/usr/bin/env python3
"""Test de non-régression — issue #855 : un lot (plusieurs blocs `#Titre:`)
déposé À LA MAIN directement dans `issues_inbox/en_attente/` (pour reporter
son lancement sans jamais passer par `issues_inbox/`) n'apparaissait que
comme UNE SEULE ligne dans l'onglet « En attente » — titre du premier bloc,
condition « non précisée » — au lieu d'une ligne par bloc. Contrairement à
un lot arrivé par le circuit normal (champ `ATTENTE`, issue #713), qui est
déjà découpé un bloc par fichier par le watcher (`_ecrire_bloc_en_attente`)
AVANT sa mise en attente, un fichier déposé directement dans `en_attente/`
n'est jamais vu par `traiter_dossier` (qui ne scrute que `issues_inbox/`,
pas son sous-dossier).

Correction : `scripts/watcher_issues_inbox.py::decouper_fichiers_lot_attente`
découpe un tel fichier en un fichier par bloc (même nommage que le circuit
normal, `<stem>__bloc<N><suffixe>`), appelé en auto-guérison par
`app/issues_inbox.py::_items_attente`/`etat_inbox` à chaque lecture.

Couvre :
- un lot de 7 blocs (4 sans `ATTENTE`, 3 avec), déposé directement dans
  `en_attente/`, donne bien 7 lignes via `GET /issues-attente`, avec le bon
  titre/projet/condition pour chacune (cas réel décrit dans l'issue) ;
- aucun bloc perdu ni créé en double : le fichier d'origine disparaît,
  7 fichiers `lot__blocN.txt` apparaissent, le total d'éléments de
  `en_attente/` (lot + fichiers mono-issue déjà présents) reste exact ;
- non-régression — un fichier à un seul bloc déposé directement dans
  `en_attente/` n'est pas touché ; un fichier déjà découpé par le watcher
  (un seul bloc, nommage `__blocN`) n'est pas touché non plus ; `GET
  /issues-inbox/etat` (`nb_en_attente`) reflète le compte après découpage ;
- la règle de remplacement du §3.16/#820 (même `#Titre:` ET même `PROJET`)
  continue de trouver un bloc issu d'un fichier découpé par #855, qu'il
  ait ou non un champ `ATTENTE`.

Aucun appel réseau ni `gh` réel.

Exécution :  python3 tests/test_decoupage_lot_en_attente_855.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

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
        return tmp_path_factory.mktemp(f"decoupe{compteur['n']}")
    return _make


def _route_cfg(tmp: Path) -> "w.ConfigInbox":
    cfg = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                         rejected_dir=tmp / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.en_attente_dir.mkdir(parents=True, exist_ok=True)
    ii._config = lambda: cfg
    return cfg


LOT_7_BLOCS = (
    "#Titre: Tâche A\n| PROJET | bridge_agent |\n| ATTENTE | après l'étape 1 |\nCorpsA.\n"
    "#Titre: Tâche B\n| PROJET | bridge_agent |\nCorpsB.\n"
    "#Titre: Tâche C\n| PROJET | bridge_agent |\n| ATTENTE | après l'étape 2 |\nCorpsC.\n"
    "#Titre: Tâche D\n| PROJET | bridge_agent |\nCorpsD.\n"
    "#Titre: Tâche E\n| PROJET | bridge_agent |\nCorpsE.\n"
    "#Titre: Tâche F\n| PROJET | bridge_agent |\n| ATTENTE | après l'étape 3 |\nCorpsF.\n"
    "#Titre: Tâche G\n| PROJET | bridge_agent |\nCorpsG.\n"
)

TITRES_ATTENDUS = {
    "Tâche A": "après l'étape 1",
    "Tâche B": "",
    "Tâche C": "après l'étape 2",
    "Tâche D": "",
    "Tâche E": "",
    "Tâche F": "après l'étape 3",
    "Tâche G": "",
}


def _deposer(chemin: Path, contenu: str) -> None:
    chemin.write_text(contenu, encoding="utf-8")


# ─── 1. decouper_fichiers_lot_attente (fonction pure sur disque) ──────────

def test_lot_7_blocs_decoupe_en_7_fichiers(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    chemin = cfg.en_attente_dir / "lot.txt"
    _deposer(chemin, LOT_7_BLOCS)

    nb = w.decouper_fichiers_lot_attente(cfg)

    assert nb == 1, nb  # un FICHIER découpé (en 7 blocs), pas 7 fichiers découpés
    assert not chemin.exists(), "le fichier d'origine doit avoir disparu"
    fichiers = sorted(p.name for p in cfg.en_attente_dir.iterdir() if p.is_file())
    assert fichiers == [f"lot__bloc{i}.txt" for i in range(1, 8)], fichiers
    return {}


def test_decoupage_idempotent_deuxieme_appel_sans_effet(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer(cfg.en_attente_dir / "lot.txt", LOT_7_BLOCS)

    w.decouper_fichiers_lot_attente(cfg)
    fichiers_avant = sorted(p.name for p in cfg.en_attente_dir.iterdir() if p.is_file())

    nb_second_appel = w.decouper_fichiers_lot_attente(cfg)

    fichiers_apres = sorted(p.name for p in cfg.en_attente_dir.iterdir() if p.is_file())
    assert nb_second_appel == 0, nb_second_appel
    assert fichiers_apres == fichiers_avant, (fichiers_avant, fichiers_apres)
    return {}


def test_fichier_mono_bloc_depose_a_la_main_inchange(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    chemin = cfg.en_attente_dir / "mono.txt"
    contenu = "| PROJET | bridge_agent |\n| ATTENTE | après fusion |\n\n#Titre: Tâche mono.\nCorps.\n"
    _deposer(chemin, contenu)

    nb = w.decouper_fichiers_lot_attente(cfg)

    assert nb == 0, nb
    assert chemin.exists(), "un fichier à un seul bloc ne doit jamais être touché"
    assert chemin.read_text(encoding="utf-8") == contenu
    return {}


def test_fichier_deja_decoupe_par_le_watcher_inchange(_tmp_dir_factory):
    """Un bloc déjà écrit par _ecrire_bloc_en_attente (circuit normal, #713)
    ne contient jamais qu'UN SEUL #Titre: — même nommage __blocN que notre
    découpage, mais ne doit jamais être re-découpé ou renommé."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    chemin = cfg.en_attente_dir / "autrelot__bloc2.txt"
    contenu = "#Titre: Déjà séparé\n| PROJET | bridge_agent |\n| ATTENTE | x |\nCorps.\n"
    _deposer(chemin, contenu)

    nb = w.decouper_fichiers_lot_attente(cfg)

    assert nb == 0, nb
    assert chemin.exists()
    assert chemin.read_text(encoding="utf-8") == contenu
    return {}


def test_dossier_absent_ne_plante_pas(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                         rejected_dir=tmp / "issues_inbox" / "rejected")
    assert not cfg.en_attente_dir.exists()
    assert w.decouper_fichiers_lot_attente(cfg) == 0
    return {}


# ─── 2. Onglet « En attente » — une ligne par bloc (via GET /issues-attente) ─

def test_lot_7_blocs_une_ligne_par_bloc_dans_l_onglet(_tmp_dir_factory):
    """Scénario de l'issue #855 : un lot de plusieurs blocs, certains avec
    ATTENTE et d'autres sans, déposé directement dans en_attente/."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer(cfg.en_attente_dir / "lot.txt", LOT_7_BLOCS)

    with APP_FLASK.test_request_context("/issues-attente"):
        items = ii.issues_attente_liste().get_json()["items"]

    assert len(items) == 7, items
    obtenus = {it["titre"]: it["condition"] for it in items}
    assert obtenus == TITRES_ATTENDUS, obtenus
    assert all(it["projet"] == "bridge_agent" for it in items), items
    return {}


def test_aucun_bloc_perdu_total_items_identique(_tmp_dir_factory):
    """Le lot de 7 blocs côtoie deux fichiers mono-issue déjà présents dans
    en_attente/ : le total après découpage doit être 7 + 2 = 9, sans perte
    ni doublon."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer(cfg.en_attente_dir / "lot.txt", LOT_7_BLOCS)
    _deposer(cfg.en_attente_dir / "mono1.txt",
             "| PROJET | bridge_agent |\n| ATTENTE | plus tard |\n\n#Titre: Mono un.\nC.\n")
    _deposer(cfg.en_attente_dir / "mono2.txt",
             "| PROJET | scrabble |\n\n#Titre: Mono deux.\nC.\n")

    with APP_FLASK.test_request_context("/issues-attente"):
        items = ii.issues_attente_liste().get_json()["items"]

    assert len(items) == 9, items
    titres = sorted(it["titre"] for it in items)
    assert titres == sorted(list(TITRES_ATTENDUS) + ["Mono un.", "Mono deux."]), titres
    assert len(set(it["id"] for it in items)) == 9, "deux éléments ne doivent jamais partager le même id"
    return {}


def test_etat_inbox_nb_en_attente_reflete_le_decoupage(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer(cfg.en_attente_dir / "lot.txt", LOT_7_BLOCS)

    with APP_FLASK.test_request_context("/issues-inbox/etat"):
        rep = ii.etat_inbox().get_json()

    assert rep["nb_en_attente"] == 7, rep
    return {}


def test_ordre_des_blocs_respecte_celui_du_fichier_d_origine(_tmp_dir_factory):
    """Sans déplacement manuel (#819), l'ordre par défaut est « plus ancien
    au plus récent » : les blocs, découpés dans l'ordre du fichier, doivent
    donc apparaître dans ce même ordre (date d'arrivée du lot conservée,
    plus un décalage infime entre blocs — cf. decouper_fichiers_lot_attente)."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer(cfg.en_attente_dir / "lot.txt", LOT_7_BLOCS)

    with APP_FLASK.test_request_context("/issues-attente"):
        items = ii.issues_attente_liste().get_json()["items"]

    assert [it["titre"] for it in items] == list(TITRES_ATTENDUS), items
    return {}


def test_fichier_mono_bloc_dans_l_onglet_toujours_une_seule_ligne(_tmp_dir_factory):
    """Non-régression : un dépôt manuel mono-issue (sans lot) continue de
    donner exactement une ligne, inchangé depuis #713."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer(cfg.en_attente_dir / "mono.txt",
             "| PROJET | bridge_agent |\n| ATTENTE | après fusion |\n\n#Titre: Tâche mono.\nCorps.\n")

    with APP_FLASK.test_request_context("/issues-attente"):
        items = ii.issues_attente_liste().get_json()["items"]

    assert len(items) == 1, items
    assert items[0]["titre"] == "Tâche mono.", items
    assert items[0]["condition"] == "après fusion", items
    return {}


# ─── 3. Compatibilité avec la règle de remplacement du §3.16/#820 ─────────

def test_remplacement_820_retrouve_un_bloc_issu_du_decoupage(_tmp_dir_factory):
    """Un fichier redéposé avec exactement le même #Titre: ET le même PROJET
    qu'un des blocs du lot (désormais réparti dans lot__bloc2.txt) doit
    continuer à être identifié comme son remplacement — la correspondance se
    fait sur le CONTENU (titre/projet), jamais sur le nom de fichier."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    _deposer(cfg.en_attente_dir / "lot.txt", LOT_7_BLOCS)

    with APP_FLASK.test_request_context("/issues-attente"):
        ii.issues_attente_liste()  # déclenche le découpage

    cible = w._item_en_attente_correspondant(cfg, "Tâche B", "bridge_agent")
    assert cible is not None, "le bloc « Tâche B » (sans ATTENTE) doit être retrouvé"
    assert cible.name == "lot__bloc2.txt", cible.name
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
        ("lot 7 blocs : découpé en 7 fichiers", lambda: test_lot_7_blocs_decoupe_en_7_fichiers(__tmp_dir_factory)),
        ("découpage idempotent : second appel sans effet", lambda: test_decoupage_idempotent_deuxieme_appel_sans_effet(__tmp_dir_factory)),
        ("mono-bloc déposé à la main : inchangé", lambda: test_fichier_mono_bloc_depose_a_la_main_inchange(__tmp_dir_factory)),
        ("déjà découpé par le watcher : inchangé", lambda: test_fichier_deja_decoupe_par_le_watcher_inchange(__tmp_dir_factory)),
        ("dossier absent : ne plante pas", lambda: test_dossier_absent_ne_plante_pas(__tmp_dir_factory)),
        ("onglet : lot 7 blocs → 7 lignes", lambda: test_lot_7_blocs_une_ligne_par_bloc_dans_l_onglet(__tmp_dir_factory)),
        ("onglet : aucun bloc perdu, total exact", lambda: test_aucun_bloc_perdu_total_items_identique(__tmp_dir_factory)),
        ("etat_inbox : nb_en_attente reflète le découpage", lambda: test_etat_inbox_nb_en_attente_reflete_le_decoupage(__tmp_dir_factory)),
        ("onglet : ordre des blocs = ordre du fichier d'origine", lambda: test_ordre_des_blocs_respecte_celui_du_fichier_d_origine(__tmp_dir_factory)),
        ("onglet : mono-bloc → toujours une seule ligne", lambda: test_fichier_mono_bloc_dans_l_onglet_toujours_une_seule_ligne(__tmp_dir_factory)),
        ("remplacement #820 : retrouve un bloc issu du découpage", lambda: test_remplacement_820_retrouve_un_bloc_issu_du_decoupage(__tmp_dir_factory)),
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

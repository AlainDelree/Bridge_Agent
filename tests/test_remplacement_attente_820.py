#!/usr/bin/env python3
"""Test de non-régression — issue #820 : corriger une issue déjà mise de
côté (`issues_inbox/en_attente/`, champ ATTENTE, #713) en redéposant
simplement un fichier de même #Titre: ET même PROJET, au lieu de la
supprimer dans l'onglet « En attente » puis redéposer le fichier corrigé
(qui se retrouvait en bout de file).

Décision de conception (actée avec Alain) : pas de nouveau champ d'en-tête
de type MOD — la règle est implicite (même titre + même PROJET).

Couvre :
- `_item_en_attente_correspondant` : correspondance stricte titre+projet,
  aucune correspondance si l'un des deux diffère ou est vide, premier
  élément de la liste (le plus ancien) choisi en cas de plusieurs
  correspondances ;
- `traiter_fichier` mono-issue : remplacement avec ATTENTE (contenu remplacé,
  condition mise à jour, place conservée), remplacement sans ATTENTE
  (circuit normal de création puis suppression de l'ancien élément
  UNIQUEMENT après succès), fichier rejeté (ancien élément intact), projet
  différent (aucun remplacement, deuxième élément créé) ;
- lot mixte : un bloc remplace (avec ATTENTE), un bloc remplace puis
  supprime après création (sans ATTENTE), les autres blocs suivent leur
  circuit habituel ;
- position conservée dans `GET /issues-attente` après un remplacement, quel
  que soit le nombre d'éléments déjà présents — depuis l'issue #822, via
  l'ordre manuel persisté (#819, figé par `_figer_place_avant_remplacement`
  AVANT l'écriture), PLUS la date affichée elle-même qui doit changer pour
  refléter ce dernier dépôt (place et date ne dépendent plus du même
  mécanisme, contrairement à la version #820 d'origine) ;
- écriture atomique (aucun fichier `.tmp` résiduel après un remplacement).

Aucun appel réseau ni `gh` réel (`_creer_issue`/`_issue_ouverte_meme_titre`
substitués, comme tests/test_champ_attente_713.py).

Exécution :  python3 -m pytest tests/test_remplacement_attente_820.py
"""

import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402
import pytest  # noqa: E402

import app.issues_inbox as ii  # noqa: E402
import app.watchers as watchers_mod  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402

APP_FLASK = flask.Flask(__name__)


@pytest.fixture
def _tmp_dir_factory(tmp_path_factory):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        return tmp_path_factory.mktemp(f"remplace{compteur['n']}")
    return _make


@pytest.fixture(autouse=True)
def _isoler_watcher_issues_inbox():
    noms = ("_creer_issue", "_issue_ouverte_meme_titre", "DOSSIER_SCRIPT", "charger_config")
    originaux = {nom: getattr(w, nom) for nom in noms}
    watchers_original = watchers_mod.demarrer_watcher
    config_original = ii._config
    yield
    for nom, valeur in originaux.items():
        setattr(w, nom, valeur)
    watchers_mod.demarrer_watcher = watchers_original
    ii._config = config_original


def _cfg_projet(depot="AlainDelree/Bridge_Agent", nom="bridge_agent", rep_travail=None):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            max_essais=3, rep_travail=rep_travail or Path(tempfile.gettempdir()),
                            perimetre_dynamique=False)


def _preparer_cfg(tmp_dir: Path, projets=("bridge_agent", "scrabble")) -> "w.ConfigInbox":
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    for projet in projets:
        (tmp_dir / "configs" / f"{projet}.conf").write_text(
            "DEPOT=AlainDelree/Bridge_Agent\n", encoding="utf-8")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: _cfg_projet(rep_travail=tmp_dir, nom=chemin.stem)
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _deposer(chemin: Path, contenu: str, age_s: float = 5) -> None:
    chemin.write_text(contenu, encoding="utf-8")
    os.utime(chemin, (time.time() - age_s, time.time() - age_s))


def _en_attente(cfg: "w.ConfigInbox", nom: str, contenu: str, age_s: float) -> Path:
    cfg.en_attente_dir.mkdir(parents=True, exist_ok=True)
    chemin = cfg.en_attente_dir / nom
    chemin.write_text(contenu, encoding="utf-8")
    os.utime(chemin, (time.time() - age_s, time.time() - age_s))
    return chemin


def _neutraliser_creation(numero_depart: int = 1, echoue: bool = False):
    compteur = {"n": numero_depart}

    def _creer(cfg_i, cfg_p, titre, labels, body):
        if echoue:
            return False, "gh indisponible (simulé)", []
        url = f"https://github.com/AlainDelree/Bridge_Agent/issues/{compteur['n']}"
        compteur["n"] += 1
        return True, url, []

    w._creer_issue = _creer
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)


# ─── 1. _item_en_attente_correspondant ─────────────────────────────────────

def test_correspondance_exacte_titre_et_projet(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    cible = _en_attente(cfg, "a.txt",
                         "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: Corriger ça.\nC.\n", 10)
    trouve = w._item_en_attente_correspondant(cfg, "Corriger ça.", "bridge_agent")
    assert trouve == cible


def test_aucune_correspondance_si_projet_different(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _en_attente(cfg, "a.txt", "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: Même titre.\nC.\n", 10)
    assert w._item_en_attente_correspondant(cfg, "Même titre.", "scrabble") is None


def test_aucune_correspondance_si_titre_different(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _en_attente(cfg, "a.txt", "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: Titre A.\nC.\n", 10)
    assert w._item_en_attente_correspondant(cfg, "Titre B.", "bridge_agent") is None


def test_aucune_correspondance_si_titre_ou_projet_vide(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _en_attente(cfg, "a.txt", "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: T.\nC.\n", 10)
    assert w._item_en_attente_correspondant(cfg, "", "bridge_agent") is None
    assert w._item_en_attente_correspondant(cfg, "T.", "") is None


def test_premier_de_la_liste_choisi_si_plusieurs_correspondances(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    plus_ancien = _en_attente(cfg, "ancien.txt",
                               "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: Doublon.\nC1.\n", 50)
    _en_attente(cfg, "recent.txt",
                "| PROJET | bridge_agent |\n| ATTENTE | y |\n\n#Titre: Doublon.\nC2.\n", 5)
    trouve = w._item_en_attente_correspondant(cfg, "Doublon.", "bridge_agent")
    assert trouve == plus_ancien


# ─── 2. Mono-issue — remplacement AVEC ATTENTE ─────────────────────────────

def test_remplacement_avec_attente_contenu_remplace_place_conservee(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé — remplacement avec ATTENTE")
    w._creer_issue = _jamais_appele

    cible = _en_attente(cfg, "mono.txt",
                         "| PROJET | bridge_agent |\n| ATTENTE | ancienne condition |\n\n"
                         "#Titre: Tâche à corriger.\nAncien corps.\n", 30)
    mtime_avant = cible.stat().st_mtime

    chemin = cfg.inbox_dir / "correction.txt"
    _deposer(chemin,
             "| PROJET | bridge_agent |\n| ATTENTE | nouvelle condition |\n\n"
             "#Titre: Tâche à corriger.\nCorps corrigé.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "le fichier déposé est consommé par le remplacement"
    en_attente = [p for p in cfg.en_attente_dir.iterdir() if p.is_file()]
    assert len(en_attente) == 1, en_attente
    assert en_attente[0].name == "mono.txt", "même fichier, pas de duplication"
    contenu = en_attente[0].read_text(encoding="utf-8")
    assert "nouvelle condition" in contenu, contenu
    assert "ancienne condition" not in contenu, contenu
    assert "Corps corrigé." in contenu, contenu
    # Issue #822 : la date affichée suit désormais le DERNIER dépôt (plus de
    # restauration du mtime d'origine) — elle doit donc avoir AVANCÉ, jusqu'à
    # coller à « maintenant » (heure du remplacement).
    mtime_apres = en_attente[0].stat().st_mtime
    assert mtime_apres > mtime_avant, "la date affichée doit refléter le DERNIER dépôt, pas le premier"
    assert abs(mtime_apres - time.time()) < 5, "la nouvelle date doit être celle du remplacement"
    # La PLACE, elle, reste garantie par l'ordre manuel #819 — figé AVANT
    # l'écriture (voir w._figer_place_avant_remplacement) même pour cet
    # élément jamais encore affiché/déplacé dans l'onglet.
    assert w._lire_ordre_attente_persiste(cfg) == ["mono.txt"], "la place doit être figée dans l'ordre persisté"

    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert lignes and " REMPLACE " in lignes[-1], lignes
    assert "Tâche à corriger." in lignes[-1], lignes[-1]
    assert not any(" EN_ATTENTE " in l for l in lignes[-1:]), "distinct des lignes EN_ATTENTE"


def test_remplacement_projet_different_aucun_remplacement(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé — bloc avec ATTENTE")
    w._creer_issue = _jamais_appele

    _en_attente(cfg, "mono.txt",
                "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: Même titre.\nC.\n", 30)

    chemin = cfg.inbox_dir / "autre.txt"
    _deposer(chemin, "| PROJET | scrabble |\n| ATTENTE | y |\n\n#Titre: Même titre.\nC2.\n")

    w.traiter_fichier(cfg, chemin)

    en_attente = sorted(p.name for p in cfg.en_attente_dir.iterdir())
    assert len(en_attente) == 2, en_attente
    contenus = {p.read_text(encoding="utf-8") for p in cfg.en_attente_dir.iterdir()}
    assert any("bridge_agent" in c and "C." in c for c in contenus)
    assert any("scrabble" in c and "C2." in c for c in contenus)


# ─── 3. Mono-issue — remplacement SANS ATTENTE (lancement) ────────────────

def test_remplacement_sans_attente_creation_puis_suppression_de_l_ancien(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    cible = _en_attente(cfg, "mono.txt",
                         "| PROJET | bridge_agent |\n| ATTENTE | après fusion |\n\n"
                         "#Titre: À lancer maintenant.\nAncien corps.\n", 20)

    chemin = cfg.inbox_dir / "correction.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n\n#Titre: À lancer maintenant.\nCorps final.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert not cible.exists(), "l'ancien élément en attente doit avoir disparu après création réussie"
    assert not list(cfg.en_attente_dir.iterdir()), list(cfg.en_attente_dir.iterdir())

    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    statuts = [l.split(" | ")[2] for l in lignes[-2:]]
    assert "OK" in statuts, lignes
    assert "REMPLACE" in statuts, lignes


def test_remplacement_sans_attente_fichier_rejete_ancien_conserve(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation(echoue=True)

    cible = _en_attente(cfg, "mono.txt",
                         "| PROJET | bridge_agent |\n| ATTENTE | après fusion |\n\n"
                         "#Titre: À corriger.\nAncien corps.\n", 20)
    contenu_avant = cible.read_text(encoding="utf-8")

    chemin = cfg.inbox_dir / "correction.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n\n#Titre: À corriger.\nCorps défaillant.\n")

    w.traiter_fichier(cfg, chemin)

    assert cible.exists(), "le rejet de la création ne doit jamais toucher à l'ancien élément en attente"
    assert cible.read_text(encoding="utf-8") == contenu_avant
    assert list(cfg.rejected_dir.glob("*REJETE*")), "le fichier déposé doit être rejeté"
    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert not any(" REMPLACE " in l for l in lignes), "aucun remplacement tracé puisqu'aucune création réelle"


# ─── 4. Lot mixte ───────────────────────────────────────────────────────────

def test_lot_mixte_remplacement_avec_et_sans_attente(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    cible_a = _en_attente(cfg, "a.txt",
                           "| PROJET | bridge_agent |\n| ATTENTE | cond A |\n\n#Titre: Bloc A.\nAncien A.\n", 40)
    cible_b = _en_attente(cfg, "b.txt",
                           "| PROJET | bridge_agent |\n| ATTENTE | cond B |\n\n#Titre: Bloc B.\nAncien B.\n", 30)

    chemin = cfg.inbox_dir / "lot.txt"
    _deposer(chemin,
             "#Titre: Bloc A.\n| PROJET | bridge_agent |\n| ATTENTE | nouvelle cond A |\nCorps A corrigé.\n"
             "#Titre: Bloc B.\n| PROJET | bridge_agent |\nCorps B final.\n"
             "#Titre: Bloc C.\n| PROJET | bridge_agent |\nCorps C normal.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()

    # Bloc A : ATTENTE -> remplace le contenu de a.txt, toujours en attente.
    assert cible_a.exists(), "a.txt doit survivre (remplacement de contenu, pas suppression)"
    contenu_a = cible_a.read_text(encoding="utf-8")
    assert "nouvelle cond A" in contenu_a and "Corps A corrigé." in contenu_a

    # Bloc B : pas d'ATTENTE -> créé, puis l'ancien b.txt supprimé.
    assert not cible_b.exists(), "b.txt doit avoir disparu après création réussie du bloc B"

    # Bloc C : normal, aucune correspondance -> créé, rien d'autre en_attente.
    restants = sorted(p.name for p in cfg.en_attente_dir.iterdir() if p.is_file())
    assert restants == ["a.txt"], restants

    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    statuts = [l.split(" | ")[2] for l in lignes[-3:]]
    assert statuts.count("OK") == 2, lignes
    assert statuts.count("REMPLACE") == 1, lignes


# ─── 5. Position conservée côté route /issues-attente ─────────────────────

def _route_cfg(tmp: Path) -> "w.ConfigInbox":
    cfg = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                         rejected_dir=tmp / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.en_attente_dir.mkdir(parents=True, exist_ok=True)
    ii._config = lambda: cfg
    return cfg


def test_position_conservee_dans_la_liste_apres_remplacement(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _route_cfg(tmp)
    _neutraliser_creation()

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé")
    w._creer_issue = _jamais_appele

    _en_attente(cfg, "premier.txt",
                "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: Premier.\nC.\n", 60)
    milieu_avant = _en_attente(cfg, "milieu.txt",
                "| PROJET | bridge_agent |\n| ATTENTE | y |\n\n#Titre: À corriger.\nAncien.\n", 40)
    date_avant = milieu_avant.stat().st_mtime
    _en_attente(cfg, "dernier.txt",
                "| PROJET | bridge_agent |\n| ATTENTE | z |\n\n#Titre: Dernier.\nC.\n", 20)

    chemin = cfg.inbox_dir / "correction.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n| ATTENTE | y corrigé |\n\n#Titre: À corriger.\nCorrigé.\n")

    w.traiter_fichier(cfg, chemin)

    with APP_FLASK.test_request_context("/issues-attente"):
        rep = ii.issues_attente_liste()
    items = rep.get_json()["items"]
    # La PLACE ne doit pas bouger — y compris pour ces éléments jamais
    # encore affichés/déplacés avant ce remplacement (aucun ordre.json
    # préexistant dans ce test) : issue #822, le cas explicitement visé.
    assert [it["id"] for it in items] == ["premier.txt", "milieu.txt", "dernier.txt"], items
    milieu = next(it for it in items if it["id"] == "milieu.txt")
    assert milieu["condition"] == "y corrigé", milieu
    # ... mais la DATE affichée, elle, doit changer pour refléter ce
    # dernier dépôt (issue #822) — plus de restauration de la date d'origine.
    assert milieu["date"] > date_avant, milieu


# ─── 6. Écriture atomique ───────────────────────────────────────────────────

def test_remplacement_ecriture_atomique_pas_de_fichier_tmp_residuel(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()
    w._creer_issue = lambda *a, **k: (_ for _ in ()).throw(AssertionError("pas attendu"))

    _en_attente(cfg, "mono.txt",
                "| PROJET | bridge_agent |\n| ATTENTE | ancienne |\n\n#Titre: T.\nAncien.\n", 20)

    chemin = cfg.inbox_dir / "correction.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n| ATTENTE | nouvelle |\n\n#Titre: T.\nNouveau.\n")

    w.traiter_fichier(cfg, chemin)

    noms = sorted(p.name for p in cfg.en_attente_dir.iterdir() if p.is_file())
    assert noms == ["mono.txt"], noms

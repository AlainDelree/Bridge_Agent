#!/usr/bin/env python3
"""Test de non-régression — issue #713 : champ d'en-tête optionnel `ATTENTE`
dans `issues_inbox/` — une valeur non vide met l'issue de côté (dossier
`en_attente/`) au lieu de la créer, en attendant qu'Alain juge la condition
remplie (AUCUNE vérification automatique) et relance via
`POST /issues-attente/lancer`.

Couvre :
- fonctions pures `lire_condition_attente`/`retirer_champ_attente` (valeur
  vide, valeur avec espaces superflus, champ absent, casse du nom, retrait
  sans toucher au reste du bloc) et non-interférence avec l'analyse des
  autres champs d'en-tête (ex. PROJET) via `extraire_champs` ;
- `scripts/watcher_issues_inbox.py::traiter_fichier` avec des dossiers
  temporaires : fichier mono-issue avec le champ (mis de côté tel quel),
  fichier mono-issue sans le champ (inchangé, circuit normal), lot mixte
  (certains blocs créés tout de suite, un bloc mis de côté), lot entièrement
  en attente (fichier d'origine supprimé, rien créé), collision de nom dans
  en_attente/ (suffixe numérique, rien n'est écrasé) ;
- routes Flask `GET /issues-attente`, `POST /issues-attente/lancer` (absence
  de boucle : le fichier relancé ne contient plus le champ ATTENTE et suit
  le circuit normal) et `POST /issues-attente/supprimer`, identifiants
  invalides ou portant un séparateur de chemin refusés ;
- `GET /issues-inbox/etat` : compteur `nb_en_attente`.

Aucun appel réseau ni `gh` réel (`_creer_issue`/`_issue_ouverte_meme_titre`
substitués, comme les autres tests de cette famille, ex. #702/#703/#710).

Exécution :  python3 tests/test_champ_attente_713.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
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
    """Zéro-argument callable produisant un nouveau dossier temporaire par
    appel — même interface que le générateur fourni par main() pour
    l'exécution autonome de ce fichier (`python3 tests/test_champ_attente_713.py`).
    Bâti sur le fixture pytest intégré `tmp_path_factory` (nom distinct pour
    éviter toute collision avec lui, cf. TypeError 'TempPathFactory' object
    is not callable si le paramètre de test s'appelait directement
    `tmp_path_factory`)."""
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        return tmp_path_factory.mktemp(f"attente{compteur['n']}")
    return _make


@pytest.fixture(autouse=True)
def _isoler_watcher_issues_inbox():
    """Restaure après CHAQUE test les attributs substitués dans ce fichier —
    même garde-fou que tests/test_evenements_issues_inbox_631.py (module
    singleton partagé par toute la session pytest)."""
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


def _preparer_cfg(tmp_dir: Path, projets=("bridge_agent",)) -> "w.ConfigInbox":
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


def _deposer(chemin: Path, contenu: str) -> None:
    chemin.write_text(contenu, encoding="utf-8")
    os.utime(chemin, (time.time() - 5, time.time() - 5))  # passe le seuil _fichier_pret (1s)


def _neutraliser_creation(numero_depart: int = 1):
    """`_creer_issue`/`_issue_ouverte_meme_titre` factices — aucun appel `gh`
    réel. Un compteur partagé permet de distinguer plusieurs créations dans
    un même scénario (lot)."""
    compteur = {"n": numero_depart}

    def _creer(cfg_i, cfg_p, titre, labels, body):
        url = f"https://github.com/AlainDelree/Bridge_Agent/issues/{compteur['n']}"
        compteur["n"] += 1
        return True, url

    w._creer_issue = _creer
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)


# ─── 1. Fonctions pures ────────────────────────────────────────────────────

def test_lire_condition_attente_valeur_presente():
    bloc = "| PROJET  | bridge_agent |\n| ATTENTE | après la fusion de l'étape C |\n\n#Titre: T.\nCorps.\n"
    assert w.lire_condition_attente(bloc) == "après la fusion de l'étape C"
    return {}


def test_lire_condition_attente_espaces_superflus_retires():
    bloc = "| ATTENTE |   après fusion   |\n\n#Titre: T.\nCorps.\n"
    assert w.lire_condition_attente(bloc) == "après fusion"
    return {}


def test_lire_condition_attente_valeur_vide_renvoie_none():
    bloc = "| PROJET  | bridge_agent |\n| ATTENTE |  |\n\n#Titre: T.\nCorps.\n"
    assert w.lire_condition_attente(bloc) is None
    return {}


def test_lire_condition_attente_champ_absent_renvoie_none():
    bloc = "| PROJET | bridge_agent |\n\n#Titre: T.\nCorps.\n"
    assert w.lire_condition_attente(bloc) is None
    return {}


def test_lire_condition_attente_insensible_a_la_casse():
    bloc = "| attente | plus tard |\n\n#Titre: T.\nCorps.\n"
    assert w.lire_condition_attente(bloc) == "plus tard"
    return {}


def test_retirer_champ_attente_laisse_le_reste_intact():
    bloc = "| PROJET  | bridge_agent |\n| ATTENTE | plus tard |\n\n#Titre: T.\nCorps.\n"
    reste = w.retirer_champ_attente(bloc)
    assert "ATTENTE" not in reste, reste
    assert "| PROJET  | bridge_agent |" in reste, reste
    assert "#Titre: T." in reste, reste
    assert "Corps." in reste, reste
    return {"reste": reste}


def test_retirer_champ_attente_sans_champ_inchange():
    bloc = "| PROJET | bridge_agent |\n\n#Titre: T.\nCorps.\n"
    assert w.retirer_champ_attente(bloc) == bloc
    return {}


def test_attente_n_interfere_pas_avec_analyse_des_autres_champs():
    """Champ inconnu des validations existantes : ATTENTE ne gêne pas
    l'extraction de PROJET/TIMEOUT/MODE/titre par extraire_champs, et est
    lui-même nettoyé du corps (y compris une valeur vide, pour ne jamais
    laisser une ligne d'en-tête orpheline dans l'issue créée)."""
    bloc = ("| PROJET  | bridge_agent |\n"
            "| ATTENTE | après fusion |\n"
            "| TIMEOUT | 900s |\n"
            "| MODE    | écriture |\n"
            "\n#Titre: Tâche complète.\nCorps utile.\n")
    champs = w.extraire_champs(bloc)
    assert champs["projet"] == "bridge_agent", champs
    assert champs["timeout_brut"] == "900s", champs
    assert champs["mode_brut"] == "écriture", champs
    assert champs["titre"] == "Tâche complète.", champs
    assert champs["attente_brut"] == "après fusion", champs
    assert "ATTENTE" not in champs["corps"], champs["corps"]
    assert champs["corps"] == "Corps utile.", repr(champs["corps"])
    return {}


def test_extraire_champs_attente_vide_ne_laisse_pas_de_ligne_orpheline():
    bloc = "| PROJET | bridge_agent |\n| ATTENTE |  |\n\n#Titre: T.\nCorps.\n"
    champs = w.extraire_champs(bloc)
    assert champs["attente_brut"] is None, champs
    assert "ATTENTE" not in champs["corps"], champs["corps"]
    return {}


# ─── 2. Watcher — dossiers temporaires ─────────────────────────────────────

def test_mono_issue_avec_champ_mis_de_cote(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé pour un bloc ATTENTE")
    w._creer_issue = _jamais_appele

    chemin = cfg.inbox_dir / "mono.txt"
    _deposer(chemin, "| PROJET  | bridge_agent |\n| ATTENTE | après fusion |\n\n#Titre: Tâche mono.\nCorps.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "le fichier d'origine doit avoir disparu (déplacé)"
    en_attente = list(cfg.en_attente_dir.iterdir())
    assert len(en_attente) == 1, en_attente
    assert en_attente[0].name == "mono.txt"
    assert "ATTENTE" in en_attente[0].read_text(encoding="utf-8")

    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert lignes and " EN_ATTENTE " in lignes[-1], lignes
    assert "après fusion" in lignes[-1], lignes[-1]
    return {"derniere_ligne": lignes[-1]}


def test_mono_issue_sans_champ_inchange(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    chemin = cfg.inbox_dir / "mono.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n\n#Titre: Tâche normale.\nCorps.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "créée avec succès : le fichier doit être supprimé"
    assert not cfg.en_attente_dir.exists() or not list(cfg.en_attente_dir.iterdir())
    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert lignes and " OK " in lignes[-1], lignes
    return {}


def test_lot_mixte_deux_creees_une_en_attente(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    chemin = cfg.inbox_dir / "lot.txt"
    _deposer(chemin,
             "#Titre: Bloc un\n| PROJET | bridge_agent |\nCorps1.\n"
             "#Titre: Bloc deux\n| PROJET | bridge_agent |\n| ATTENTE | après l'étape B |\nCorps2.\n"
             "#Titre: Bloc trois\n| PROJET | bridge_agent |\nCorps3.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "lot avec au moins un succès : le fichier d'origine est supprimé"
    en_attente = list(cfg.en_attente_dir.iterdir())
    assert len(en_attente) == 1, en_attente
    assert "ATTENTE" in en_attente[0].read_text(encoding="utf-8")
    assert "Bloc deux" in en_attente[0].read_text(encoding="utf-8")

    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    statuts = [l.split(" | ")[2] for l in lignes[-3:]]
    assert statuts.count("OK") == 2, lignes
    assert statuts.count("EN_ATTENTE") == 1, lignes
    return {"en_attente": en_attente[0].name}


def test_lot_entierement_en_attente_fichier_origine_supprime(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé : lot entièrement en attente")
    w._creer_issue = _jamais_appele
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None

    chemin = cfg.inbox_dir / "lot_attente.txt"
    _deposer(chemin,
             "#Titre: Bloc un\n| PROJET | bridge_agent |\n| ATTENTE | plus tard 1 |\nCorps1.\n"
             "#Titre: Bloc deux\n| PROJET | bridge_agent |\n| ATTENTE | plus tard 2 |\nCorps2.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists(), "lot entièrement en attente : fichier d'origine supprimé"
    en_attente = sorted(p.name for p in cfg.en_attente_dir.iterdir())
    assert len(en_attente) == 2, en_attente
    assert not list(cfg.rejected_dir.glob("*REJETE*")), "rien n'a échoué, rien ne doit être rejeté"
    return {"en_attente": en_attente}


def test_collision_de_nom_en_attente_suffixe(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    cfg.en_attente_dir.mkdir(parents=True, exist_ok=True)
    (cfg.en_attente_dir / "mono.txt").write_text("déjà présent", encoding="utf-8")

    chemin = cfg.inbox_dir / "mono.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n| ATTENTE | plus tard |\n\n#Titre: Nouvelle tâche.\nCorps.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    en_attente = sorted(p.name for p in cfg.en_attente_dir.iterdir())
    assert en_attente == ["mono-1.txt", "mono.txt"], en_attente
    assert (cfg.en_attente_dir / "mono.txt").read_text(encoding="utf-8") == "déjà présent"
    assert "Nouvelle tâche" in (cfg.en_attente_dir / "mono-1.txt").read_text(encoding="utf-8")
    return {"en_attente": en_attente}


# ─── 3. Routes Flask ────────────────────────────────────────────────────────

def _route_cfg(tmp: Path) -> "w.ConfigInbox":
    cfg = w.ConfigInbox(rep_travail=tmp, inbox_dir=tmp / "issues_inbox",
                         rejected_dir=tmp / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.en_attente_dir.mkdir(parents=True, exist_ok=True)
    ii._config = lambda: cfg
    return cfg


def test_route_liste_plus_ancien_d_abord(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)

    recent = cfg.en_attente_dir / "recent.txt"
    recent.write_text("| PROJET | bridge_agent |\n| ATTENTE | cond récente |\n\n#Titre: Récente.\nC.\n",
                       encoding="utf-8")
    os.utime(recent, (time.time() - 5, time.time() - 5))

    ancien = cfg.en_attente_dir / "ancien.txt"
    ancien.write_text("| PROJET | scrabble |\n| ATTENTE | cond ancienne |\n\n#Titre: Ancienne.\nC.\n",
                       encoding="utf-8")
    os.utime(ancien, (time.time() - 50, time.time() - 50))

    with APP_FLASK.test_request_context("/issues-attente"):
        rep = ii.issues_attente_liste()
    items = rep.get_json()["items"]
    assert [it["id"] for it in items] == ["ancien.txt", "recent.txt"], items
    assert items[0]["titre"] == "Ancienne." and items[0]["projet"] == "scrabble"
    assert items[0]["condition"] == "cond ancienne"
    assert items[1]["condition"] == "cond récente"
    return {"ordre": [it["id"] for it in items]}


def test_route_etat_inbox_expose_nb_en_attente(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    (cfg.en_attente_dir / "a.txt").write_text("x", encoding="utf-8")
    (cfg.en_attente_dir / "b.txt").write_text("x", encoding="utf-8")
    ii.CHEMIN_PID = tmp / "logs" / "watcher-inexistant.pid"

    with APP_FLASK.test_request_context("/issues-inbox/etat"):
        rep = ii.etat_inbox()
    corps = rep.get_json()
    assert corps["nb_en_attente"] == 2, corps
    return {"nb_en_attente": corps["nb_en_attente"]}


def test_route_lancer_retire_le_champ_et_rejoint_le_circuit_normal(_tmp_dir_factory):
    """Absence de boucle : le fichier relancé dans issues_inbox/ ne contient
    plus ATTENTE — un traitement normal ultérieur (ici simulé directement)
    le créerait sans jamais le remettre en attente."""
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    (cfg.en_attente_dir / "mono.txt").write_text(
        "| PROJET  | bridge_agent |\n| ATTENTE | après fusion |\n\n#Titre: Tâche.\nCorps.\n",
        encoding="utf-8")

    with APP_FLASK.test_request_context("/issues-attente/lancer", method="POST", json={"id": "mono.txt"}):
        rep = ii.issues_attente_lancer()
    corps = rep.get_json()
    assert corps["succes"] is True, corps

    assert not (cfg.en_attente_dir / "mono.txt").exists(), "retiré d'en_attente/"
    relance = cfg.inbox_dir / corps["fichier"]
    assert relance.exists(), "réécrit dans le dossier d'entrée"
    contenu_relance = relance.read_text(encoding="utf-8")
    assert "ATTENTE" not in contenu_relance, contenu_relance
    assert w.lire_condition_attente(contenu_relance) is None, "ne doit plus jamais se remettre en attente"
    return {"contenu": contenu_relance}


def test_route_lancer_ecriture_atomique_pas_de_fichier_tmp_residuel(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    (cfg.en_attente_dir / "mono.txt").write_text(
        "| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: T.\nC.\n", encoding="utf-8")

    with APP_FLASK.test_request_context("/issues-attente/lancer", method="POST", json={"id": "mono.txt"}):
        ii.issues_attente_lancer()

    noms = sorted(p.name for p in cfg.inbox_dir.iterdir() if p.is_file())
    assert noms == ["mono.txt"], noms
    return {}


def test_route_lancer_identifiant_introuvable_404(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    _route_cfg(tmp)
    with APP_FLASK.test_request_context("/issues-attente/lancer", method="POST", json={"id": "absent.txt"}):
        rep, code = ii.issues_attente_lancer()
    assert code == 404
    assert rep.get_json()["succes"] is False
    return {"code": code}


def test_route_lancer_identifiant_avec_separateur_refuse(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    cible_hors_dossier = cfg.inbox_dir.parent / "evasion.txt"

    for identifiant in ("../evasion.txt", "sous/dossier.txt", "sous\\dossier.txt", "..", ""):
        with APP_FLASK.test_request_context("/issues-attente/lancer", method="POST", json={"id": identifiant}):
            rep, code = ii.issues_attente_lancer()
        assert code == 400, (identifiant, code)
        assert rep.get_json()["succes"] is False

    assert not cible_hors_dossier.exists()
    return {}


def test_route_supprimer_retire_le_fichier(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _route_cfg(tmp)
    cible = cfg.en_attente_dir / "mono.txt"
    cible.write_text("| PROJET | bridge_agent |\n| ATTENTE | x |\n\n#Titre: T.\nC.\n", encoding="utf-8")

    with APP_FLASK.test_request_context("/issues-attente/supprimer", method="POST", json={"id": "mono.txt"}):
        rep = ii.issues_attente_supprimer()
    assert rep.get_json()["succes"] is True
    assert not cible.exists()
    return {}


def test_route_supprimer_identifiant_invalide_refuse(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    _route_cfg(tmp)
    with APP_FLASK.test_request_context("/issues-attente/supprimer", method="POST", json={"id": "../x.txt"}):
        rep, code = ii.issues_attente_supprimer()
    assert code == 400
    assert rep.get_json()["succes"] is False
    return {"code": code}


def test_route_supprimer_identifiant_introuvable_404(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    _route_cfg(tmp)
    with APP_FLASK.test_request_context("/issues-attente/supprimer", method="POST", json={"id": "absent.txt"}):
        rep, code = ii.issues_attente_supprimer()
    assert code == 404
    return {"code": code}


def main() -> int:
    tmp_racine = tempfile.TemporaryDirectory()
    compteur = {"n": 0}

    def __tmp_dir_factory():
        compteur["n"] += 1
        chemin = Path(tmp_racine.name) / f"t{compteur['n']}"
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    tests = [
        ("lire_condition_attente : valeur présente", test_lire_condition_attente_valeur_presente),
        ("lire_condition_attente : espaces superflus retirés", test_lire_condition_attente_espaces_superflus_retires),
        ("lire_condition_attente : valeur vide → None", test_lire_condition_attente_valeur_vide_renvoie_none),
        ("lire_condition_attente : champ absent → None", test_lire_condition_attente_champ_absent_renvoie_none),
        ("lire_condition_attente : insensible à la casse", test_lire_condition_attente_insensible_a_la_casse),
        ("retirer_champ_attente : reste intact", test_retirer_champ_attente_laisse_le_reste_intact),
        ("retirer_champ_attente : sans champ → inchangé", test_retirer_champ_attente_sans_champ_inchange),
        ("ATTENTE n'interfère pas avec les autres champs", test_attente_n_interfere_pas_avec_analyse_des_autres_champs),
        ("extraire_champs : ATTENTE vide ne laisse pas de ligne orpheline", test_extraire_champs_attente_vide_ne_laisse_pas_de_ligne_orpheline),
        ("watcher : mono-issue avec champ → mis de côté", lambda: test_mono_issue_avec_champ_mis_de_cote(__tmp_dir_factory)),
        ("watcher : mono-issue sans champ → inchangé", lambda: test_mono_issue_sans_champ_inchange(__tmp_dir_factory)),
        ("watcher : lot mixte → 2 créées, 1 en attente", lambda: test_lot_mixte_deux_creees_une_en_attente(__tmp_dir_factory)),
        ("watcher : lot entièrement en attente → fichier supprimé", lambda: test_lot_entierement_en_attente_fichier_origine_supprime(__tmp_dir_factory)),
        ("watcher : collision de nom en_attente/ → suffixe", lambda: test_collision_de_nom_en_attente_suffixe(__tmp_dir_factory)),
        ("route /issues-attente : plus ancien d'abord", lambda: test_route_liste_plus_ancien_d_abord(__tmp_dir_factory)),
        ("route /issues-inbox/etat : nb_en_attente", lambda: test_route_etat_inbox_expose_nb_en_attente(__tmp_dir_factory)),
        ("route /issues-attente/lancer : retire le champ, pas de boucle", lambda: test_route_lancer_retire_le_champ_et_rejoint_le_circuit_normal(__tmp_dir_factory)),
        ("route /issues-attente/lancer : écriture atomique, pas de résidu", lambda: test_route_lancer_ecriture_atomique_pas_de_fichier_tmp_residuel(__tmp_dir_factory)),
        ("route /issues-attente/lancer : identifiant introuvable → 404", lambda: test_route_lancer_identifiant_introuvable_404(__tmp_dir_factory)),
        ("route /issues-attente/lancer : séparateur de chemin refusé", lambda: test_route_lancer_identifiant_avec_separateur_refuse(__tmp_dir_factory)),
        ("route /issues-attente/supprimer : retire le fichier", lambda: test_route_supprimer_retire_le_fichier(__tmp_dir_factory)),
        ("route /issues-attente/supprimer : identifiant invalide → 400", lambda: test_route_supprimer_identifiant_invalide_refuse(__tmp_dir_factory)),
        ("route /issues-attente/supprimer : identifiant introuvable → 404", lambda: test_route_supprimer_identifiant_introuvable_404(__tmp_dir_factory)),
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

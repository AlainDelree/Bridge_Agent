#!/usr/bin/env python3
"""Test de non-régression — issue #719 : un fichier (ou lot) dont tous les
blocs restants sont des RELANCE (champ RELANCE, §3.14, issue #516) ne doit
produire AUCUNE ligne « 📥 fichier reçu » dans l'onglet Résultats — rien ne la
remplacerait ni ne l'enlèverait avant le prochain rechargement, puisqu'une
RELANCE réussie ne crée jamais d'issue (donc jamais d'événement
creation_issue). Constaté en réel le 05/10/2026 avec relance_issue_126.txt.

Cause : `_notifier_fichier_recu` était émis dès la prise en charge du fichier
par `traiter_fichier`, AVANT de savoir qu'aucun bloc du fichier ne créerait
jamais d'issue — même mécanisme que celui corrigé dans l'issue #716 pour les
fichiers ATTENTE (voir tests/test_pas_de_ligne_fichier_recu_si_attente_716.py),
mais pour le cas RELANCE.

Couvre (via `scripts/watcher_issues_inbox.py::traiter_fichier`, en
interceptant `_poster_best_effort` comme tests/test_evenements_issues_inbox_
631.py et tests/test_pas_de_ligne_fichier_recu_si_attente_716.py) :
- fichier mono-issue RELANCE réussi : aucun appel `fichier_recu` ;
- lot dont TOUS les blocs sont des RELANCE (réussis) : aucun appel
  `fichier_recu` ;
- lot MIXTE (RELANCE + création normale) : comportement inchangé,
  `fichier_recu` toujours émis une seule fois, en tête ;
- RELANCE refusée (issue introuvable) : comportement inchangé côté visible —
  aucun `fichier_recu` (nouveau), mais `fichier_refuse` toujours émis (la
  ligne rouge s'affiche, comme avant #719) ;
- fichier SANS RELANCE : comportement inchangé, `fichier_recu` toujours
  émis ;
- combinaison avec ATTENTE (#716) : un lot ATTENTE + RELANCE (rien d'autre)
  n'émet toujours aucun `fichier_recu` ; un lot ATTENTE + RELANCE + création
  émet toujours `fichier_recu` une seule fois (comportement #716 inchangé).

Aucun appel réseau ni `gh` réel (`_recuperer_issue`/`_modifier_corps_gh`/
`relancer_issue`/`_creer_issue`/`_issue_ouverte_meme_titre` substitués, comme
tests/test_champ_relance_516.py).

Depuis l'issue #720, une RELANCE réussie co-émet aussi `case_decochee`
(décoche automatique de la case « traité/lu », voir
tests/test_decoche_relance_720.py pour cet aspect) — filtré à part par
`_types_decoches` ci-dessous, SANS RAPPORT avec l'invariant #719 testé ici
(fichier_recu/fichier_refuse).

Exécution :  python3 tests/test_pas_de_ligne_fichier_recu_si_relance_719.py
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

import pytest  # noqa: E402

import app.watchers as watchers_mod  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402


@pytest.fixture(autouse=True)
def _isoler_watcher_issues_inbox():
    """Même garde-fou que tests/test_champ_relance_516.py et tests/
    test_pas_de_ligne_fichier_recu_si_attente_716.py — module singleton
    partagé par toute la session pytest."""
    noms = ("_creer_issue", "_issue_ouverte_meme_titre", "_poster_best_effort",
            "_recuperer_issue", "_modifier_corps_gh", "relancer_issue",
            "demarrer_service_ccw_arriere_plan", "DOSSIER_SCRIPT", "charger_config")
    originaux = {nom: getattr(w, nom) for nom in noms}
    watchers_original = watchers_mod.demarrer_watcher
    yield
    for nom, valeur in originaux.items():
        setattr(w, nom, valeur)
    watchers_mod.demarrer_watcher = watchers_original


def _cfg_projet(depot="AlainDelree/Bridge_Agent", nom="bridge_agent", rep_travail=None,
                 perimetre_dynamique=False):
    return SimpleNamespace(depot=depot, nom=nom, timeout_claude=300, timeout_chef=1200,
                            max_essais=3, rep_travail=rep_travail or Path(tempfile.gettempdir()),
                            perimetre_dynamique=perimetre_dynamique)


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


def _appel_ccw_interdit(*_a, **_k):
    raise AssertionError("demarrer_service_ccw_arriere_plan n'aurait pas dû être appelé "
                          "(aucun label for-windows dans ces scénarios).")


def _neutraliser_relance_succes(numeros=(126,), depot="AlainDelree/Bridge_Agent",
                                 labels=("bridge", "for-linux")):
    """Simule une RELANCE réussie pour chacun des numéros donnés — aucun
    appel `gh` réel, comme tests/test_champ_relance_516.py::scenario_5."""
    def _fausse_recuperation(depot_appel, numero):
        assert numero in numeros, f"numéro inattendu : {numero}"
        return True, "", {
            "number": numero, "state": "OPEN", "title": f"Issue #{numero}",
            "body": "| PROJET | bridge_agent |\n",
            "labels": [{"name": l} for l in labels],
        }

    w._recuperer_issue = _fausse_recuperation
    w._modifier_corps_gh = lambda depot_appel, numero, corps: (True, "")
    w.relancer_issue = lambda depot_appel, numero, commentaire="": (
        "ok", [{"etape": "retrait_label_needs_human", "statut": "succes", "message": ""}])
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)
    w.demarrer_service_ccw_arriere_plan = _appel_ccw_interdit


def _neutraliser_relance_echec(numero: int, motif: str = "introuvable"):
    """Simule une RELANCE refusée (issue cible introuvable)."""
    w._recuperer_issue = lambda depot_appel, numero_appel: (False, motif, None)
    w.demarrer_service_ccw_arriere_plan = _appel_ccw_interdit


def _neutraliser_creation(numero_depart: int = 1):
    compteur = {"n": numero_depart}

    def _creer(cfg_i, cfg_p, titre, labels, body):
        url = f"https://github.com/AlainDelree/Bridge_Agent/issues/{compteur['n']}"
        compteur["n"] += 1
        return True, url

    w._creer_issue = _creer
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)


def _types_recus(appels: list) -> list:
    return [p for u, p in appels if u == w.URL_NOTIFIER_FICHIER_RECU]


def _types_refuses(appels: list) -> list:
    return [p for u, p in appels if u == w.URL_NOTIFIER_FICHIER_REFUSE]


def _types_decoches(appels: list) -> list:
    """Événements `case_decochee` (issue #720) — co-émis par une RELANCE
    réussie, SANS RAPPORT avec l'invariant `fichier_recu` testé par ce
    fichier (issue #719) : filtré à part pour ne pas fausser les assertions
    `== []` ci-dessous, qui ne portent que sur fichier_recu/fichier_refuse."""
    return [p for u, p in appels if u == w.URL_NOTIFIER_CASE_DECOCHEE]


def test_mono_issue_relance_reussie_aucune_ligne_fichier_recu(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126,))

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé pour un bloc RELANCE")
    w._creer_issue = _jamais_appele

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "relance_issue_126.txt"
    _deposer(chemin, "| PROJET  | bridge_agent |\n| RELANCE | #126 |\n\nLa tâche a échoué, relance.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert _types_recus(appels) == [] and _types_refuses(appels) == [], \
        f"aucun fichier_recu/fichier_refuse attendu, obtenu : {appels}"
    # Décoche automatique (issue #720) — SEUL événement co-émis par une
    # RELANCE réussie, hors de portée de l'invariant #719 testé ici.
    assert appels == [(w.URL_NOTIFIER_CASE_DECOCHEE, {"projet": "bridge_agent", "numero": 126})], appels
    return {"appels": appels}


def test_lot_entierement_relance_aucune_ligne_fichier_recu(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126, 127))

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé : lot entièrement RELANCE")
    w._creer_issue = _jamais_appele

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot_relance.txt"
    _deposer(chemin,
             "#Titre: Relance un\n| PROJET | bridge_agent |\n| RELANCE | #126 |\nCorps1.\n"
             "#Titre: Relance deux\n| PROJET | bridge_agent |\n| RELANCE | #127 |\nCorps2.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert _types_recus(appels) == [] and _types_refuses(appels) == [], \
        f"aucun fichier_recu/fichier_refuse attendu, obtenu : {appels}"
    # Décoche automatique (issue #720) pour CHAQUE issue relancée du lot.
    assert _types_decoches(appels) == [{"projet": "bridge_agent", "numero": 126},
                                        {"projet": "bridge_agent", "numero": 127}], appels
    return {"appels": appels}


def test_lot_mixte_relance_et_creation_fichier_recu_toujours_emis(_tmp_dir_factory):
    """Comportement INCHANGÉ (issue #719, cas de non-régression) : un lot
    mixte (un bloc RELANCE, un bloc création normale) émet toujours
    fichier_recu, en tête — comme un lot mixte ATTENTE (#716)."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126,))
    _neutraliser_creation()

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot.txt"
    _deposer(chemin,
             "#Titre: Bloc création\n| PROJET | bridge_agent |\nCorps1.\n"
             "#Titre: Bloc relance\n| PROJET | bridge_agent |\n| RELANCE | #126 |\nCorps2.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(_types_recus(appels)) == 1, appels
    assert appels[0] == (w.URL_NOTIFIER_FICHIER_RECU, {"fichier": "lot.txt"}), appels[0]
    return {"appels": appels}


def test_relance_refusee_ligne_rouge_affichee_sans_fichier_recu(_tmp_dir_factory):
    """RELANCE refusée (issue cible introuvable) : comportement visible
    inchangé — la ligne rouge « fichier refusé » s'affiche toujours — mais
    plus aucun `fichier_recu` ne précède (issue #719 : rien ne l'aurait
    jamais remplacée/enlevée pour un bloc RELANCE)."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_echec(126, motif="issue #126 introuvable dans AlainDelree/Bridge_Agent")

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "relance_issue_126.txt"
    _deposer(chemin, "| PROJET  | bridge_agent |\n| RELANCE | #126 |\n\nLa tâche a échoué, relance.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(list(cfg.rejected_dir.glob("relance_issue_126*"))) == 1
    assert _types_recus(appels) == [], f"aucun fichier_recu attendu, obtenu : {appels}"
    assert len(_types_refuses(appels)) == 1, appels
    assert appels[0][0] == w.URL_NOTIFIER_FICHIER_REFUSE, appels[0]
    return {"appels": appels}


def test_fichier_sans_relance_fichier_recu_toujours_emis(_tmp_dir_factory):
    """Comportement INCHANGÉ (issue #719, cas de non-régression) : un
    fichier mono-issue SANS RELANCE émet toujours fichier_recu."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "mono.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n\n#Titre: Tâche normale.\nCorps.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(_types_recus(appels)) == 1, appels
    assert appels[0] == (w.URL_NOTIFIER_FICHIER_RECU, {"fichier": "mono.txt"}), appels[0]
    return {"appels": appels}


def test_lot_attente_et_relance_sans_creation_aucune_ligne_fichier_recu(_tmp_dir_factory):
    """Combinaison avec ATTENTE (#716) : un lot où un bloc est ATTENTE et
    l'autre RELANCE (aucune création) ne doit toujours produire aucune ligne
    fichier_recu — la correction #719 s'applique aussi aux blocs restants
    après filtrage ATTENTE."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126,))

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé")
    w._creer_issue = _jamais_appele
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot_mixte_attente_relance.txt"
    _deposer(chemin,
             "#Titre: Bloc attente\n| PROJET | bridge_agent |\n| ATTENTE | plus tard |\nCorps1.\n"
             "#Titre: Bloc relance\n| PROJET | bridge_agent |\n| RELANCE | #126 |\nCorps2.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(list(cfg.en_attente_dir.iterdir())) == 1
    assert _types_recus(appels) == [] and _types_refuses(appels) == [], \
        f"aucun fichier_recu/fichier_refuse attendu, obtenu : {appels}"
    # Décoche automatique (issue #720) de l'unique issue relancée du lot.
    assert appels == [(w.URL_NOTIFIER_CASE_DECOCHEE, {"projet": "bridge_agent", "numero": 126})], appels
    return {"appels": appels}


def test_lot_attente_relance_et_creation_fichier_recu_toujours_emis(_tmp_dir_factory):
    """Combinaison avec ATTENTE (#716) : un lot où un bloc est ATTENTE, un
    bloc est RELANCE et un bloc est une création normale émet toujours
    fichier_recu une seule fois — comportement #716 inchangé, la présence
    d'un bloc RELANCE parmi les blocs restants ne doit rien changer dès
    qu'une création subsiste."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_relance_succes(numeros=(126,))
    _neutraliser_creation()
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot_mixte_attente_relance_creation.txt"
    _deposer(chemin,
             "#Titre: Bloc attente\n| PROJET | bridge_agent |\n| ATTENTE | plus tard |\nCorps1.\n"
             "#Titre: Bloc relance\n| PROJET | bridge_agent |\n| RELANCE | #126 |\nCorps2.\n"
             "#Titre: Bloc creation\n| PROJET | bridge_agent |\nCorps3.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(list(cfg.en_attente_dir.iterdir())) == 1
    assert len(_types_recus(appels)) == 1, appels
    assert appels[0] == (w.URL_NOTIFIER_FICHIER_RECU,
                          {"fichier": "lot_mixte_attente_relance_creation.txt"}), appels[0]
    return {"appels": appels}


@pytest.fixture
def _tmp_dir_factory(tmp_path_factory):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        return tmp_path_factory.mktemp(f"recu_relance{compteur['n']}")
    return _make


def main() -> int:
    tmp_racine = tempfile.TemporaryDirectory()
    compteur = {"n": 0}

    def __tmp_dir_factory():
        compteur["n"] += 1
        chemin = Path(tmp_racine.name) / f"t{compteur['n']}"
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    tests = [
        ("mono-issue RELANCE réussie : aucune ligne fichier_recu",
         lambda: test_mono_issue_relance_reussie_aucune_ligne_fichier_recu(__tmp_dir_factory)),
        ("lot entièrement RELANCE : aucune ligne fichier_recu",
         lambda: test_lot_entierement_relance_aucune_ligne_fichier_recu(__tmp_dir_factory)),
        ("lot mixte RELANCE + création : fichier_recu toujours émis (inchangé)",
         lambda: test_lot_mixte_relance_et_creation_fichier_recu_toujours_emis(__tmp_dir_factory)),
        ("RELANCE refusée : ligne rouge affichée, sans fichier_recu",
         lambda: test_relance_refusee_ligne_rouge_affichee_sans_fichier_recu(__tmp_dir_factory)),
        ("fichier sans RELANCE : fichier_recu toujours émis (inchangé)",
         lambda: test_fichier_sans_relance_fichier_recu_toujours_emis(__tmp_dir_factory)),
        ("lot ATTENTE + RELANCE (sans création) : aucune ligne fichier_recu",
         lambda: test_lot_attente_et_relance_sans_creation_aucune_ligne_fichier_recu(__tmp_dir_factory)),
        ("lot ATTENTE + RELANCE + création : fichier_recu toujours émis (inchangé)",
         lambda: test_lot_attente_relance_et_creation_fichier_recu_toujours_emis(__tmp_dir_factory)),
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

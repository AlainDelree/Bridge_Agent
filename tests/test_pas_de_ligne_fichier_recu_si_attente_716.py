#!/usr/bin/env python3
"""Test de non-régression — issue #716 : un fichier (ou lot) ENTIÈREMENT mis
en attente (champ ATTENTE, #713) ne doit produire AUCUNE ligne « 📥 fichier
reçu » dans l'onglet Résultats — rien ne la remplacerait ni ne l'enlèverait
avant le prochain rechargement, puisqu'aucune issue n'est créée et que le
fichier n'est pas refusé (il est mis de côté dans en_attente/). Seul le badge
de l'onglet « En attente » doit signaler son arrivée.

Cause (issue #631) : `_notifier_fichier_recu` était émis dès la prise en
charge du fichier par `traiter_fichier`, AVANT la détection du champ ATTENTE
(#713) — toujours trop tôt pour savoir si une ligne aurait un jour de quoi
être remplacée.

Couvre (via `scripts/watcher_issues_inbox.py::traiter_fichier`, en
interceptant `_poster_best_effort` comme tests/test_evenements_issues_inbox_
631.py) :
- fichier mono-issue avec ATTENTE : aucun appel `fichier_recu` ;
- lot dont TOUS les blocs ont ATTENTE : aucun appel `fichier_recu` ;
- lot MIXTE (un bloc ATTENTE, les autres normaux) : comportement inchangé,
  `fichier_recu` toujours émis (en tête, avant les événements par bloc) ;
- fichier SANS ATTENTE : comportement inchangé, `fichier_recu` toujours émis.

Aucun appel réseau ni `gh` réel (`_creer_issue`/`_issue_ouverte_meme_titre`
substitués, comme tests/test_champ_attente_713.py).

Exécution :  python3 tests/test_pas_de_ligne_fichier_recu_si_attente_716.py
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
    """Même garde-fou que tests/test_champ_attente_713.py et tests/
    test_evenements_issues_inbox_631.py — module singleton partagé par toute
    la session pytest."""
    noms = ("_creer_issue", "_issue_ouverte_meme_titre", "_poster_best_effort",
            "DOSSIER_SCRIPT", "charger_config")
    originaux = {nom: getattr(w, nom) for nom in noms}
    watchers_original = watchers_mod.demarrer_watcher
    yield
    for nom, valeur in originaux.items():
        setattr(w, nom, valeur)
    watchers_mod.demarrer_watcher = watchers_original


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
    compteur = {"n": numero_depart}

    def _creer(cfg_i, cfg_p, titre, labels, body):
        url = f"https://github.com/AlainDelree/Bridge_Agent/issues/{compteur['n']}"
        compteur["n"] += 1
        return True, url

    w._creer_issue = _creer
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)


def _types_recus(appels: list) -> list:
    """Sous-liste des appels best-effort portant sur l'URL fichier_recu —
    pour compter précisément ses occurrences, sans dépendre de l'ordre des
    autres événements (creation_issue / fichier_refuse)."""
    return [p for u, p in appels if u == w.URL_NOTIFIER_FICHIER_RECU]


def test_mono_issue_attente_aucune_ligne_fichier_recu(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé pour un bloc ATTENTE")
    w._creer_issue = _jamais_appele

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "mono.txt"
    _deposer(chemin, "| PROJET  | bridge_agent |\n| ATTENTE | après fusion |\n\n#Titre: Tâche mono.\nCorps.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(list(cfg.en_attente_dir.iterdir())) == 1
    assert appels == [], f"aucun événement attendu, obtenu : {appels}"
    return {"appels": appels}


def test_lot_entierement_attente_aucune_ligne_fichier_recu(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)

    def _jamais_appele(*a, **k):
        raise AssertionError("gh issue create ne doit jamais être appelé : lot entièrement en attente")
    w._creer_issue = _jamais_appele
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot_attente.txt"
    _deposer(chemin,
             "#Titre: Bloc un\n| PROJET | bridge_agent |\n| ATTENTE | plus tard 1 |\nCorps1.\n"
             "#Titre: Bloc deux\n| PROJET | bridge_agent |\n| ATTENTE | plus tard 2 |\nCorps2.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(list(cfg.en_attente_dir.iterdir())) == 2
    assert appels == [], f"aucun événement attendu, obtenu : {appels}"
    return {"appels": appels}


def test_lot_mixte_fichier_recu_toujours_emis(_tmp_dir_factory):
    """Comportement INCHANGÉ (issue #716, cas de non-régression) : un lot
    mixte (un bloc ATTENTE, les autres normaux) émet toujours fichier_recu,
    en tête — la ligne « fichier reçu » apparaît puis est remplacée par la
    première issue créée, comme avant #716."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    _neutraliser_creation()

    appels = []
    w._poster_best_effort = lambda url, payload: appels.append((url, payload))

    chemin = cfg.inbox_dir / "lot.txt"
    _deposer(chemin,
             "#Titre: Bloc un\n| PROJET | bridge_agent |\nCorps1.\n"
             "#Titre: Bloc deux\n| PROJET | bridge_agent |\n| ATTENTE | après l'étape B |\nCorps2.\n"
             "#Titre: Bloc trois\n| PROJET | bridge_agent |\nCorps3.\n")

    w.traiter_fichier(cfg, chemin)

    assert not chemin.exists()
    assert len(list(cfg.en_attente_dir.iterdir())) == 1
    assert len(_types_recus(appels)) == 1, appels
    assert appels[0] == (w.URL_NOTIFIER_FICHIER_RECU, {"fichier": "lot.txt"}), appels[0]
    return {"appels": appels}


def test_fichier_sans_attente_fichier_recu_toujours_emis(_tmp_dir_factory):
    """Comportement INCHANGÉ (issue #716, cas de non-régression) : un
    fichier mono-issue SANS ATTENTE émet toujours fichier_recu."""
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


@pytest.fixture
def _tmp_dir_factory(tmp_path_factory):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        return tmp_path_factory.mktemp(f"recu_attente{compteur['n']}")
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
        ("mono-issue ATTENTE : aucune ligne fichier_recu",
         lambda: test_mono_issue_attente_aucune_ligne_fichier_recu(__tmp_dir_factory)),
        ("lot entièrement ATTENTE : aucune ligne fichier_recu",
         lambda: test_lot_entierement_attente_aucune_ligne_fichier_recu(__tmp_dir_factory)),
        ("lot mixte : fichier_recu toujours émis (inchangé)",
         lambda: test_lot_mixte_fichier_recu_toujours_emis(__tmp_dir_factory)),
        ("fichier sans ATTENTE : fichier_recu toujours émis (inchangé)",
         lambda: test_fichier_sans_attente_fichier_recu_toujours_emis(__tmp_dir_factory)),
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

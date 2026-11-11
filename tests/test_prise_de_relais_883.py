#!/usr/bin/env python3
"""Test de non-régression — issue #883 : le watcher de la tâche planifiée
Windows doit prendre le relais quand l'instance lancée par l'interface
s'arrête, au lieu de rester éteint jusqu'à l'ouverture suivante de session.

Contexte : depuis #881, `scripts/watcher_issues_inbox.py` pose un verrou
d'instance unique et une seconde instance s'arrête aussitôt (code 0). Sous
Windows avec démarrage de session (#864), la tâche planifiée `…-IssuesInbox`
démarre ~20s après l'interface web (qui, elle, démarre sans délai) : elle
perd presque toujours la course au verrou, s'arrête proprement, et le
superviseur (`surveiller_processus_session.ps1`, codes 0/42 = arrêt propre,
pas de redémarrage) ne la relance jamais. Si l'interface s'arrête ensuite
(bouton « Quitter », tâche coupée, plantage), elle arrête aussi SON propre
watcher : plus aucune instance ne traite `issues_inbox/` jusqu'à son retour
— essai réel confirmé (sans perte ni doublon, juste un délai de traitement).

Correctif : l'option `--attendre-si-occupe` (passée UNIQUEMENT par
`installer_demarrage_session.ps1` à la tâche planifiée, jamais au lancement
par l'interface) remplace l'arrêt immédiat par une mise en veille —
`attendre_prise_de_relais()` retente l'acquisition du verrou à intervalle
régulier, sans aucun fichier traité tant qu'il n'est pas acquis, et sans
bruit de log à chaque tentative (une ligne à l'entrée en veille, une à la
prise de relais).

Couvre :
- `attendre_prise_de_relais()` : bloque réellement tant que le verrou est
  tenu, l'acquiert dès sa libération (scénario explicite de l'issue :
  « verrou libéré par l'instance principale » → « prise de relais ») ;
- aucun fichier d'`issues_inbox/` n'est examiné/traité pendant l'attente ;
- exactement deux lignes de log (« En veille », « Prise de relais »), quel
  que soit le nombre de tentatives intermédiaires réellement effectuées ;
- `main()` : comportement par défaut (sans `--attendre-si-occupe`) toujours
  un arrêt immédiat si le verrou est tenu — comportement Linux/instance
  unique STRICTEMENT inchangé (#881) ; avec le flag, attend puis démarre
  normalement (une seule fois le relais pris).

Aucun appel réseau ni `gh` réel.

Exécution :  python3 tests/test_prise_de_relais_883.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import sys
import tempfile
import threading
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import pytest  # noqa: E402

import watcher_issues_inbox as w  # noqa: E402


@pytest.fixture
def _tmp_dir_factory(tmp_path_factory):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        return tmp_path_factory.mktemp(f"relais883_{compteur['n']}")
    return _make


@pytest.fixture(autouse=True)
def _isoler_watcher_issues_inbox():
    """Même garde-fou que tests/test_instance_unique_et_reclamation_881.py —
    module singleton partagé par toute la session pytest : restaure après
    CHAQUE test les attributs substitués."""
    noms = ("CHEMIN_VERROU_INSTANCE", "CHEMIN_PID", "boucle", "configurer_logs",
            "acquerir_verrou_instance_unique", "attendre_prise_de_relais",
            "charger_config_inbox")
    originaux = {nom: getattr(w, nom) for nom in noms}
    yield
    for nom, valeur in originaux.items():
        setattr(w, nom, valeur)


def _preparer_cfg(tmp_dir: Path) -> "w.ConfigInbox":
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
    return cfg


# ─── 1. attendre_prise_de_relais() bloque réellement, acquiert à la
#        libération ──────────────────────────────────────────────────────

def test_attendre_prise_de_relais_bloque_puis_acquiert_a_la_liberation(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    w.CHEMIN_VERROU_INSTANCE = tmp / "watcher-issues_inbox.instance.lock"

    premier = w.acquerir_verrou_instance_unique()
    assert premier is not None, "l'instance principale doit acquérir le verrou"

    resultat = {}

    def _attendre():
        resultat["verrou"] = w.attendre_prise_de_relais(intervalle=0.05)

    thread = threading.Thread(target=_attendre)
    thread.start()

    # Le verrou est encore tenu : le thread en veille ne doit PAS avoir
    # terminé après plusieurs intervalles de retente.
    time.sleep(0.3)
    assert thread.is_alive(), (
        "attendre_prise_de_relais() a rendu la main alors que le verrou de "
        "l'instance principale est toujours tenu — elle ne doit prendre le "
        "relais qu'à sa LIBÉRATION."
    )

    premier.close()  # simule l'arrêt (propre ou brutal) de l'instance principale
    thread.join(timeout=3)

    assert not thread.is_alive(), "la prise de relais n'a pas abouti à temps après la libération"
    assert resultat.get("verrou") is not None, "le verrou aurait dû être acquis après la libération"
    resultat["verrou"].close()
    return {}


# ─── 2. Aucun fichier traité pendant la veille ─────────────────────────────

def test_aucun_fichier_examine_pendant_la_veille(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    w.CHEMIN_VERROU_INSTANCE = tmp / "watcher-issues_inbox.instance.lock"
    cfg = _preparer_cfg(tmp)
    fichier = cfg.inbox_dir / "depose_pendant_veille.txt"
    fichier.write_text("| PROJET | bridge_agent |\n\n#Titre: T.\nCorps.\n", encoding="utf-8")

    premier = w.acquerir_verrou_instance_unique()
    assert premier is not None

    resultat = {}

    def _attendre():
        resultat["verrou"] = w.attendre_prise_de_relais(intervalle=0.05)

    thread = threading.Thread(target=_attendre)
    thread.start()
    try:
        time.sleep(0.3)
        assert fichier.exists() and fichier.parent == cfg.inbox_dir, (
            "le fichier déposé ne doit JAMAIS être déplacé/examiné par une "
            "instance en veille — seule l'instance qui détient RÉELLEMENT le "
            "verrou peut ouvrir issues_inbox/ (attendre_prise_de_relais ne "
            "touche jamais au système de fichiers d'issues_inbox)."
        )
        assert not list(cfg.en_cours_dir.glob("*")) if cfg.en_cours_dir.is_dir() else True
    finally:
        premier.close()
        thread.join(timeout=3)
    assert resultat.get("verrou") is not None
    resultat["verrou"].close()
    return {}


# ─── 3. Exactement deux lignes de log, quel que soit le nombre de
#        tentatives intermédiaires ──────────────────────────────────────────

def test_une_seule_ligne_en_veille_et_une_seule_prise_de_relais(_tmp_dir_factory, caplog):
    tmp = _tmp_dir_factory()
    w.CHEMIN_VERROU_INSTANCE = tmp / "watcher-issues_inbox.instance.lock"

    premier = w.acquerir_verrou_instance_unique()
    assert premier is not None

    resultat = {}

    def _attendre():
        resultat["verrou"] = w.attendre_prise_de_relais(intervalle=0.03)

    with caplog.at_level(logging.INFO, logger="watcher_issues_inbox"):
        thread = threading.Thread(target=_attendre)
        thread.start()
        # Laisse largement le temps à PLUSIEURS tentatives (intervalle 30ms)
        # de se produire avant de libérer le verrou.
        time.sleep(0.4)
        premier.close()
        thread.join(timeout=3)

    messages = [r.message for r in caplog.records]
    lignes_veille = [m for m in messages if "En veille" in m]
    lignes_relais = [m for m in messages if "Prise de relais" in m]
    assert len(lignes_veille) == 1, f"une seule ligne « En veille » attendue : {lignes_veille}"
    assert len(lignes_relais) == 1, f"une seule ligne « Prise de relais » attendue : {lignes_relais}"

    assert resultat.get("verrou") is not None
    resultat["verrou"].close()
    return {}


# ─── 4. main() — comportement par défaut (sans --attendre-si-occupe)
#        strictement inchangé : arrêt immédiat (#881, Linux/instance unique) ─

def test_main_sans_option_quitte_immediatement_si_verrou_tenu(monkeypatch, _tmp_dir_factory):
    tmp = _tmp_dir_factory()
    w.CHEMIN_PID = tmp / "watcher-issues_inbox.pid"

    monkeypatch.setattr(sys, "argv", ["watcher_issues_inbox.py"])
    monkeypatch.setattr(w, "configurer_logs", lambda: None)
    monkeypatch.setattr(w, "acquerir_verrou_instance_unique", lambda: None)

    def _jamais_appelee(*a, **k):
        raise AssertionError("attendre_prise_de_relais() ne doit jamais être appelée sans --attendre-si-occupe")
    monkeypatch.setattr(w, "attendre_prise_de_relais", _jamais_appelee)

    def _boucle_jamais_appelee(*a, **k):
        raise AssertionError("boucle() ne doit jamais démarrer si le verrou n'a pas été acquis")
    monkeypatch.setattr(w, "boucle", _boucle_jamais_appelee)

    with pytest.raises(SystemExit) as exc:
        w.main()
    assert exc.value.code == 0, "arrêt immédiat attendu avec le code 0 (arrêt propre, #881)"
    return {}


# ─── 5. main() — avec --attendre-si-occupe : attend puis démarre une fois le
#        relais pris (scénario demandé par l'issue) ────────────────────────

def test_main_avec_option_attend_puis_demarre_apres_prise_de_relais(monkeypatch, _tmp_dir_factory):
    tmp = _tmp_dir_factory()
    w.CHEMIN_PID = tmp / "watcher-issues_inbox.pid"
    sentinelle_verrou = object()

    monkeypatch.setattr(sys, "argv", ["watcher_issues_inbox.py", "--attendre-si-occupe"])
    monkeypatch.setattr(w, "configurer_logs", lambda: None)
    # Premier essai dans main() : verrou tenu (perdu la course, cas #883).
    monkeypatch.setattr(w, "acquerir_verrou_instance_unique", lambda: None)

    appels_attente = {"n": 0}

    def _attendre_simulee(intervalle=w.INTERVALLE_ATTENTE_VERROU_S):
        appels_attente["n"] += 1
        return sentinelle_verrou
    monkeypatch.setattr(w, "attendre_prise_de_relais", _attendre_simulee)

    appels_boucle = {"n": 0}

    def _boucle_capturee(cfg, once=False, duree_min=0):
        appels_boucle["n"] += 1
    monkeypatch.setattr(w, "boucle", _boucle_capturee)

    w.main()

    assert appels_attente["n"] == 1, "attendre_prise_de_relais() aurait dû être appelée exactement une fois"
    assert appels_boucle["n"] == 1, (
        "boucle() (donc le traitement normal d'issues_inbox/) aurait dû démarrer "
        "une fois le relais pris — jamais avant"
    )
    assert w.CHEMIN_PID.exists(), "le PID doit être publié une fois le verrou RÉELLEMENT acquis"
    return {}


def main() -> int:
    tmp_racine = tempfile.TemporaryDirectory()
    compteur = {"n": 0}

    def __tmp_dir_factory():
        compteur["n"] += 1
        chemin = Path(tmp_racine.name) / f"t{compteur['n']}"
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    # Scénarios 4 et 5 ont besoin de monkeypatch/caplog (fixtures pytest) —
    # repli : exécutés uniquement sous pytest. Le runner autonome ci-dessous
    # couvre les scénarios 1 à 3, indépendants de ces fixtures.
    tests = [
        ("attendre_prise_de_relais bloque puis acquiert à la libération",
         lambda: test_attendre_prise_de_relais_bloque_puis_acquiert_a_la_liberation(__tmp_dir_factory)),
        ("aucun fichier examiné pendant la veille",
         lambda: test_aucun_fichier_examine_pendant_la_veille(__tmp_dir_factory)),
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

    print("  (scénarios 3 à 5 : nécessitent pytest — monkeypatch/caplog — voir "
          "`python3 -m pytest tests/test_prise_de_relais_883.py`)")

    tmp_racine.cleanup()
    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios (hors pytest-only) passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

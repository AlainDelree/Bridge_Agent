#!/usr/bin/env python3
"""Test de non-régression — issue #881 : dépôt d'issues par fichiers, une
seule instance et un traitement sans doublon, même si deux instances du
watcher `scripts/watcher_issues_inbox.py` tournent en même temps.

Contexte : un essai réel sous Windows a produit deux issues GitHub
identiques pour un seul fichier déposé — deux process `watcher_issues_
inbox.py` tournaient en même temps (tâche planifiée de session + lancement
par `new_issue.py` lui-même), chacun ayant vu le fichier avant que l'autre
n'ait créé l'issue (voir le rapport de clôture pour la cause racine établie
par lecture du code : `logs/watcher-issues_inbox.pid`, le seul fichier
consulté par `app.issues_inbox.watcher_inbox_actif()`, n'était écrit QUE par
le lanceur, jamais par le script lui-même).

Couvre :
- `acquerir_verrou_instance_unique()` : exclusif entre deux descripteurs
  distincts (simule deux process), libéré à la fermeture du premier ;
- `_reclamer_fichier()` : réclamation atomique, refuse un second claim sur
  le même nom, ne modifie jamais le nom affiché ;
- `recuperer_fichiers_en_cours_orphelins()` : reprise d'un fichier resté en
  cours sans propriétaire vivant, fichier laissé intact si le propriétaire
  est vivant ;
- scénario demandé explicitement par l'issue #881 : deux traitements
  CONCURRENTS (threads) du même fichier déposé → une seule issue créée ;
- anti-doublon en mémoire (`_creation_en_cours`) : deux FICHIERS distincts
  partageant le même titre, traités concurremment par la même instance,
  pendant que `_issue_ouverte_meme_titre` (GitHub) ne voit encore rien →
  une seule création malgré tout.

Aucun appel réseau ni `gh` réel (`_creer_issue`/`_issue_ouverte_meme_titre`
substitués, comme les autres tests de cette famille).

Exécution :  python3 tests/test_instance_unique_et_reclamation_881.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import sys
import tempfile
import threading
import time
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import pytest  # noqa: E402

import app.watchers as watchers_mod  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402


@pytest.fixture
def _tmp_dir_factory(tmp_path_factory):
    compteur = {"n": 0}

    def _make():
        compteur["n"] += 1
        return tmp_path_factory.mktemp(f"inst881_{compteur['n']}")
    return _make


@pytest.fixture(autouse=True)
def _isoler_watcher_issues_inbox():
    """Restaure après CHAQUE test les attributs substitués — module
    singleton partagé par toute la session pytest (même garde-fou que
    tests/test_champ_attente_713.py), y compris le registre en mémoire de
    l'anti-doublon et les chemins de verrou/PID."""
    noms = ("_creer_issue", "_issue_ouverte_meme_titre", "DOSSIER_SCRIPT",
            "charger_config", "_pid_vivant", "CHEMIN_VERROU_INSTANCE", "CHEMIN_PID")
    originaux = {nom: getattr(w, nom) for nom in noms}
    titres_originaux = {k: set(v) for k, v in w._titres_en_cours_creation.items()}
    watchers_original = watchers_mod.demarrer_watcher
    yield
    for nom, valeur in originaux.items():
        setattr(w, nom, valeur)
    w._titres_en_cours_creation.clear()
    w._titres_en_cours_creation.update(titres_originaux)
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


def _neutraliser_creation_lente(delai_s: float = 0.0):
    """`_creer_issue`/`_issue_ouverte_meme_titre` factices — aucun appel `gh`
    réel. `delai_s` élargit délibérément la fenêtre de course entre deux
    appels concurrents (`time.sleep` relâche le GIL, autorisant une vraie
    interruption entre threads). Compteur partagé, protégé par un verrou
    Python (pas le sujet du test, juste pour un comptage fiable)."""
    compteur = {"n": 0}
    verrou = threading.Lock()

    def _creer(cfg_i, cfg_p, titre, labels, body):
        if delai_s:
            time.sleep(delai_s)
        with verrou:
            compteur["n"] += 1
            n = compteur["n"]
        return True, f"https://github.com/AlainDelree/Bridge_Agent/issues/{n}", []

    w._creer_issue = _creer
    w._issue_ouverte_meme_titre = lambda cfg_p, titre: None
    watchers_mod.demarrer_watcher = lambda cfg_p, forcer=False: (False, 9999)
    return compteur


# ─── 1. Verrou d'instance unique ───────────────────────────────────────────

def test_verrou_instance_exclusif_puis_libere_a_la_fermeture(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    w.CHEMIN_VERROU_INSTANCE = tmp / "watcher-issues_inbox.instance.lock"

    premier = w.acquerir_verrou_instance_unique()
    assert premier is not None, "le premier appel doit acquérir le verrou"

    second = w.acquerir_verrou_instance_unique()
    assert second is None, "un second appel, verrou déjà tenu, doit échouer"

    premier.close()  # simule la fin (propre ou brutale) du premier process

    troisieme = w.acquerir_verrou_instance_unique()
    assert troisieme is not None, "le verrou doit être libéré après la fermeture du premier"
    troisieme.close()
    return {}


# ─── 2. Réclamation atomique ────────────────────────────────────────────────

def test_reclamer_fichier_refuse_un_second_claim_sur_le_meme_nom(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    chemin = cfg.inbox_dir / "foo.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n\n#Titre: T.\nCorps.\n")

    reclame = w._reclamer_fichier(cfg, chemin)
    assert reclame is not None, "la première réclamation doit réussir"
    assert reclame == cfg.en_cours_dir / "foo.txt", reclame
    assert reclame.name == "foo.txt", "le nom affiché ne doit jamais changer (#881)"
    assert not chemin.exists(), "l'original doit avoir disparu de issues_inbox/"

    # Second claim sur un chemin QUI N'EXISTE PLUS (simule la seconde instance
    # arrivée une fraction de seconde trop tard) : rien à réclamer.
    reclame_2 = w._reclamer_fichier(cfg, chemin)
    assert reclame_2 is None
    return {}


def test_reclamer_fichier_refuse_si_nom_deja_occupe_en_cours(_tmp_dir_factory):
    """Le nom est déjà occupé dans en_cours/ (ex. claim actif non orphelin) :
    _reclamer_fichier ne doit JAMAIS écraser — comportement identique sur les
    deux plateformes (voir sa docstring)."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    cfg.en_cours_dir.mkdir(parents=True, exist_ok=True)
    (cfg.en_cours_dir / "foo.txt").write_text("déjà réclamé par une autre instance", encoding="utf-8")

    chemin = cfg.inbox_dir / "foo.txt"
    _deposer(chemin, "| PROJET | bridge_agent |\n\n#Titre: T.\nCorps.\n")

    assert w._reclamer_fichier(cfg, chemin) is None
    assert chemin.exists(), "le fichier déposé doit rester intact, jamais perdu"
    assert (cfg.en_cours_dir / "foo.txt").read_text(encoding="utf-8") == "déjà réclamé par une autre instance"
    return {}


# ─── 3. Reprise après arrêt brutal ──────────────────────────────────────────

def test_reprise_fichier_orphelin_sans_proprietaire_vivant(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    cfg.en_cours_dir.mkdir(parents=True, exist_ok=True)
    orphelin = cfg.en_cours_dir / "orphelin.txt"
    orphelin.write_text("| PROJET | bridge_agent |\n\n#Titre: T.\nCorps.\n", encoding="utf-8")
    w._ecrire_proprietaire(cfg, "orphelin.txt")
    w._pid_vivant = lambda pid: False  # simule un process mort (arrêt brutal)

    nb = w.recuperer_fichiers_en_cours_orphelins(cfg)

    assert nb == 1
    assert not orphelin.exists(), "doit avoir quitté en_cours/"
    assert (cfg.inbox_dir / "orphelin.txt").exists(), "doit être remis dans issues_inbox/"
    assert not w._chemin_proprietaire(cfg, "orphelin.txt").exists(), "sidecar nettoyé"
    return {}


def test_fichier_en_cours_avec_proprietaire_vivant_non_touche(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    cfg.en_cours_dir.mkdir(parents=True, exist_ok=True)
    actif = cfg.en_cours_dir / "actif.txt"
    actif.write_text("| PROJET | bridge_agent |\n\n#Titre: T.\nCorps.\n", encoding="utf-8")
    w._ecrire_proprietaire(cfg, "actif.txt")
    w._pid_vivant = lambda pid: True  # simule un propriétaire toujours vivant

    nb = w.recuperer_fichiers_en_cours_orphelins(cfg)

    assert nb == 0
    assert actif.exists(), "un claim actif ne doit JAMAIS être déplacé"
    assert not (cfg.inbox_dir / "actif.txt").exists()
    return {}


def test_sidecar_absent_traite_comme_propriétaire_mort():
    """Un sidecar illisible/absent ne doit jamais bloquer une reprise."""
    tmp = Path(tempfile.mkdtemp())
    cfg = _preparer_cfg(tmp)
    cfg.en_cours_dir.mkdir(parents=True, exist_ok=True)
    (cfg.en_cours_dir / "sans_sidecar.txt").write_text("contenu", encoding="utf-8")
    # _pid_vivant non substitué ici : le sidecar est simplement absent, donc
    # _proprietaire_vivant doit renvoyer False sans même l'appeler.
    assert w._proprietaire_vivant(cfg, "sans_sidecar.txt") is False
    return {}


# ─── 4. Scénario explicitement demandé par l'issue #881 : deux traitements
#        concurrents du même fichier → une seule issue créée ───────────────

def test_deux_traitements_concurrents_du_meme_fichier_une_seule_issue(_tmp_dir_factory):
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    compteur = _neutraliser_creation_lente(delai_s=0.1)

    fichier = cfg.inbox_dir / "concurrent.txt"
    _deposer(fichier, "| PROJET | bridge_agent |\n\n#Titre: Tâche concurrente.\nCorps.\n")

    threads = [threading.Thread(target=w.traiter_dossier, args=(cfg,)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert compteur["n"] == 1, f"une seule issue attendue, {compteur['n']} créée(s)"
    assert not fichier.exists()
    assert not (cfg.en_cours_dir / "concurrent.txt").exists()
    assert not list(cfg.en_cours_dir.glob("*")) or not any(
        p.is_file() for p in cfg.en_cours_dir.glob("*")
    ), "rien ne doit rester bloqué dans en_cours/"
    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert sum(1 for l in lignes if " | OK | " in l) == 1, lignes
    return {"creations": compteur["n"]}


# ─── 5. Anti-doublon en mémoire : deux FICHIERS distincts, même titre,
#        traités concurremment par la MÊME instance ────────────────────────

def test_anti_doublon_meme_titre_deux_fichiers_concurrents_une_seule_creation(_tmp_dir_factory):
    """`_issue_ouverte_meme_titre` (GitHub) renvoie toujours None ici — même
    une fois la première création terminée — pour isoler précisément ce que
    le registre en mémoire (_creation_en_cours) protège : la fenêtre de
    latence entre une création réelle et le moment où une requête GitHub
    ultérieure la verrait."""
    tmp = _tmp_dir_factory()
    cfg = _preparer_cfg(tmp)
    compteur = _neutraliser_creation_lente(delai_s=0.1)

    titre_commun = "#Titre: Deux dépôts, même titre.\nCorps.\n"
    _deposer(cfg.inbox_dir / "a.txt", "| PROJET | bridge_agent |\n\n" + titre_commun)
    _deposer(cfg.inbox_dir / "b.txt", "| PROJET | bridge_agent |\n\n" + titre_commun)

    threads = [threading.Thread(target=w.traiter_dossier, args=(cfg,)) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert compteur["n"] == 1, (
        f"un seul des deux fichiers doit créer une issue (même titre, même "
        f"instance) — {compteur['n']} créée(s)"
    )
    lignes = cfg.fichier_log.read_text(encoding="utf-8").splitlines()
    assert sum(1 for l in lignes if " | OK | " in l) == 1, lignes
    assert sum(1 for l in lignes if " | REJECTED | " in l) == 1, lignes
    assert any("création est déjà en cours" in l for l in lignes), lignes
    return {"creations": compteur["n"]}


def test_marquer_demarquer_creation_en_cours_registre_pur():
    depot = "x/y"
    assert w._creation_en_cours(depot, "T") is False
    w._marquer_creation_en_cours(depot, "T")
    assert w._creation_en_cours(depot, "T") is True
    w._demarquer_creation_en_cours(depot, "T")
    assert w._creation_en_cours(depot, "T") is False
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
        ("verrou d'instance : exclusif puis libéré à la fermeture",
         lambda: test_verrou_instance_exclusif_puis_libere_a_la_fermeture(__tmp_dir_factory)),
        ("réclamation : refuse un second claim sur le même nom",
         lambda: test_reclamer_fichier_refuse_un_second_claim_sur_le_meme_nom(__tmp_dir_factory)),
        ("réclamation : refuse si le nom est déjà occupé en_cours/",
         lambda: test_reclamer_fichier_refuse_si_nom_deja_occupe_en_cours(__tmp_dir_factory)),
        ("reprise : fichier orphelin sans propriétaire vivant",
         lambda: test_reprise_fichier_orphelin_sans_proprietaire_vivant(__tmp_dir_factory)),
        ("reprise : fichier avec propriétaire vivant non touché",
         lambda: test_fichier_en_cours_avec_proprietaire_vivant_non_touche(__tmp_dir_factory)),
        ("reprise : sidecar absent traité comme propriétaire mort",
         test_sidecar_absent_traite_comme_propriétaire_mort),
        ("deux traitements concurrents du même fichier → une seule issue",
         lambda: test_deux_traitements_concurrents_du_meme_fichier_une_seule_issue(__tmp_dir_factory)),
        ("anti-doublon même instance : deux fichiers, même titre, concurrents → une seule création",
         lambda: test_anti_doublon_meme_titre_deux_fichiers_concurrents_une_seule_creation(__tmp_dir_factory)),
        ("registre marquer/démarquer création en cours",
         test_marquer_demarquer_creation_en_cours_registre_pur),
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

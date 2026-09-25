#!/usr/bin/env python3
"""Test de non-régression — issue #631 : événements SSE `fichier_recu`,
`creation_issue`, `fichier_refuse` sur /stream (backend seul, étape 9a de la
refonte de l'interface web — §6 de ARCHITECTURE.md) + exposition du motif de
refus dans `GET /issues-inbox/etat`.

Couvre :
- `app/fin_issue.py` : les trois routes POST (`notifier_fichier_recu`,
  `notifier_creation_issue`, `notifier_fichier_refuse`) construisent et
  diffusent le bon événement SSE (nom + JSON), rejettent une requête
  incomplète (400), et `emettre_creation_issue()` peut être appelée EN
  DIRECT (sans HTTP), comme le fait `app.issues.envoyer()` ;
- `scripts/watcher_issues_inbox.py` : ORDRE des événements best-effort
  postés pour un fichier mono-bloc (succès/rejet) et pour un lot
  multi-blocs (§3.13) — un `fichier_recu` d'abord, puis un
  `creation_issue`/`fichier_refuse` par bloc dans l'ordre de traitement,
  aucun événement pour un bloc RELANCE (qui ne crée jamais d'issue) ;
- `app/issues_inbox.py::etat_inbox()` : le motif de refus (texte intégral,
  sidecar `<fichier>.motif` écrit par `_deplacer_vers_rejected`) est exposé
  par fichier rejeté, lisible depuis le seul disque (donc après un
  redémarrage de new_issue.py), absent (None) pour un rejet antérieur à
  cette fonctionnalité (pas de sidecar).

Aucun appel réseau ni `gh` réel : les POST best-effort de
`scripts/watcher_issues_inbox.py` sont interceptés via
`w._poster_best_effort`, et `_traiter_bloc` est remplacé par un double
piloté par le contenu de chaque bloc — aucune dépendance à `gh issue
create`/`gh issue list`.

Exécution :  python3 tests/test_evenements_issues_inbox_631.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import os
import queue
import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import flask  # noqa: E402

import app.fin_issue as fi  # noqa: E402
import app.issues_inbox as ii  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402

APP_FLASK = flask.Flask(__name__)


def _reabonner() -> "queue.Queue":
    """Réinitialise la liste d'abonnés SSE de APP_FLASK et y ajoute une
    file fraîche — chaque test récupère ainsi exactement ses propres
    événements, sans résidu d'un test précédent."""
    q = queue.Queue()
    APP_FLASK.config["FIN_ISSUE_ABONNES"] = [q]
    return q


def _payload(message: str) -> dict:
    """Extrait le JSON d'un message SSE `event: ...\\ndata: {...}\\n\\n`."""
    ligne_data = message.split("data: ", 1)[1].strip()
    return json.loads(ligne_data)


# ─── app/fin_issue.py : routes + appel direct ──────────────────────────────

def test_notifier_fichier_recu_diffuse_evenement():
    q = _reabonner()
    with APP_FLASK.test_request_context(
            "/notifier-fichier-recu", method="POST", json={"fichier": "lot.txt"}):
        rep = fi.notifier_fichier_recu()
    assert rep.get_json()["ok"] is True
    message = q.get_nowait()
    assert message.startswith("event: fichier_recu\n"), message
    assert _payload(message) == {"fichier": "lot.txt"}
    return {"message": message.strip()}


def test_notifier_fichier_recu_sans_fichier_400():
    with APP_FLASK.test_request_context("/notifier-fichier-recu", method="POST", json={}):
        rep, code = fi.notifier_fichier_recu()
    assert code == 400
    assert rep.get_json()["ok"] is False
    return {"code": code}


def test_notifier_creation_issue_diffuse_evenement_avec_fichier():
    q = _reabonner()
    with APP_FLASK.test_request_context(
            "/notifier-creation-issue", method="POST",
            json={"projet": "bridge_agent", "numero": 42, "titre": "Une tâche",
                  "fichier": "lot.txt", "labels": ["bridge", "for-linux"],
                  "timing": {"timeout": 300, "max_essais": 3}}):
        rep = fi.notifier_creation_issue()
    assert rep.get_json()["ok"] is True
    assert _payload(q.get_nowait()) == {
        "projet": "bridge_agent", "numero": 42, "titre": "Une tâche", "fichier": "lot.txt",
        "labels": ["bridge", "for-linux"], "timing": {"timeout": 300, "max_essais": 3},
    }
    return {}


def test_notifier_creation_issue_champs_manquants_400():
    with APP_FLASK.test_request_context(
            "/notifier-creation-issue", method="POST", json={"projet": "bridge_agent"}):
        rep, code = fi.notifier_creation_issue()
    assert code == 400
    return {"code": code}


def test_emettre_creation_issue_appel_direct_sans_fichier():
    """Appel EN DIRECT (même process, pas de HTTP), comme le fait
    `app.issues.envoyer()` après une création via le formulaire web — le
    champ `fichier` est absent (None), l'issue ne venant pas d'issues_inbox/."""
    q = _reabonner()
    with APP_FLASK.app_context():
        fi.emettre_creation_issue("bridge_agent", 7, "Titre formulaire")
    assert _payload(q.get_nowait()) == {
        "projet": "bridge_agent", "numero": 7, "titre": "Titre formulaire", "fichier": None,
        "labels": [], "timing": {},
    }
    return {}


def test_notifier_fichier_refuse_diffuse_evenement():
    q = _reabonner()
    with APP_FLASK.test_request_context(
            "/notifier-fichier-refuse", method="POST",
            json={"fichier": "lot.txt", "titre": "Bloc 2", "motif": "PROJET manquant"}):
        rep = fi.notifier_fichier_refuse()
    assert rep.get_json()["ok"] is True
    assert _payload(q.get_nowait()) == {
        "fichier": "lot.txt", "titre": "Bloc 2", "motif": "PROJET manquant",
    }
    return {}


def test_notifier_fichier_refuse_titre_absent_devient_null():
    q = _reabonner()
    with APP_FLASK.test_request_context(
            "/notifier-fichier-refuse", method="POST",
            json={"fichier": "brut.txt", "motif": "extension invalide : attendu .txt"}):
        fi.notifier_fichier_refuse()
    assert _payload(q.get_nowait())["titre"] is None
    return {}


def test_notifier_fichier_refuse_champs_manquants_400():
    with APP_FLASK.test_request_context(
            "/notifier-fichier-refuse", method="POST", json={"fichier": "x.txt"}):
        rep, code = fi.notifier_fichier_refuse()
    assert code == 400
    return {"code": code}


# ─── scripts/watcher_issues_inbox.py : ordre des événements best-effort ────

def _preparer_cfg(tmp_dir: Path) -> "w.ConfigInbox":
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / "bridge_agent.conf").write_text(
        "DEPOT=AlainDelree/Bridge_Agent\n", encoding="utf-8")
    cfg = w.ConfigInbox(rep_travail=tmp_dir, inbox_dir=tmp_dir / "issues_inbox",
                         rejected_dir=tmp_dir / "issues_inbox" / "rejected")
    cfg.inbox_dir.mkdir(parents=True, exist_ok=True)
    cfg.rejected_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def _deposer(chemin: Path, contenu: str) -> None:
    chemin.write_text(contenu, encoding="utf-8")
    os.utime(chemin, (time.time() - 5, time.time() - 5))  # passe le seuil _fichier_pret (1s)


def _types(appels: list) -> list:
    """Reclassifie chaque appel (url, payload) posté en un mot-clé lisible,
    pour comparer facilement l'ORDRE obtenu à l'ordre attendu."""
    correspondance = {
        w.URL_NOTIFIER_FICHIER_RECU:   "recu",
        w.URL_NOTIFIER_CREATION_ISSUE: "creation",
        w.URL_NOTIFIER_FICHIER_REFUSE: "refuse",
    }
    return [correspondance[url] for url, _ in appels]


def test_ordre_evenements_mono_bloc_succes():
    """Fichier à un seul bloc, création réussie : fichier_recu puis
    creation_issue, dans cet ordre, avec le nom de fichier d'origine."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer_cfg(Path(tmp))
        appels = []
        w._poster_best_effort = lambda url, payload: appels.append((url, payload))
        w._traiter_bloc = lambda cfg_i, bloc: (
            True, "Une tâche", "bridge_agent", "",
            "https://github.com/AlainDelree/Bridge_Agent/issues/42",
            ["bridge", "for-linux"], {"timeout": 300, "max_essais": 3})

        chemin = cfg.inbox_dir / "issue.txt"
        _deposer(chemin, "| PROJET | bridge_agent |\n\n#Titre: Une tâche.\nCorps.\n")

        w.traiter_fichier(cfg, chemin)

        assert not chemin.exists(), "fichier traité avec succès : doit être supprimé"
        assert _types(appels) == ["recu", "creation"], appels
        assert appels[0][1] == {"fichier": "issue.txt"}
        assert appels[1][1] == {
            "projet": "bridge_agent", "numero": 42, "titre": "Une tâche", "fichier": "issue.txt",
            "labels": ["bridge", "for-linux"], "timing": {"timeout": 300, "max_essais": 3},
        }
    return {"ordre": _types(appels)}


def test_ordre_evenements_mono_bloc_rejete():
    """Fichier à un seul bloc, rejeté : fichier_recu puis fichier_refuse,
    avec le motif complet et le nom de fichier ORIGINAL (avant renommage
    vers rejected/)."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer_cfg(Path(tmp))
        appels = []
        w._poster_best_effort = lambda url, payload: appels.append((url, payload))
        w._traiter_bloc = lambda cfg_i, bloc: (
            False, "Une tâche", "bridge_agent", "projet inconnu : « x »", "", None, None)

        chemin = cfg.inbox_dir / "issue.txt"
        _deposer(chemin, "| PROJET | x |\n\n#Titre: Une tâche.\nCorps.\n")

        w.traiter_fichier(cfg, chemin)

        assert not chemin.exists()
        assert list(cfg.rejected_dir.glob("*REJETE*"))
        assert _types(appels) == ["recu", "refuse"], appels
        assert appels[0][1] == {"fichier": "issue.txt"}
        assert appels[1][1] == {
            "fichier": "issue.txt", "titre": "Une tâche", "motif": "projet inconnu : « x »",
        }
    return {"ordre": _types(appels)}


def test_ordre_evenements_lot_multi_blocs():
    """Lot de 4 blocs (issue #508) : succès, rejet, succès-sans-création
    (simule une RELANCE : resultat_gh vide → aucun événement, cf.
    _traiter_relance) et succès — un événement par bloc EXPLOITABLE, dans
    l'ordre de traitement, jamais groupé."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer_cfg(Path(tmp))
        appels = []
        w._poster_best_effort = lambda url, payload: appels.append((url, payload))

        def _traiter_bloc_fake(cfg_i, bloc):
            if "Bloc1" in bloc:
                return (True, "Bloc1", "bridge_agent", "",
                        "https://github.com/AlainDelree/Bridge_Agent/issues/10",
                        ["bridge", "for-linux"], {"timeout": 300})
            if "Bloc2" in bloc:
                return (False, "Bloc2", "bridge_agent", "titre manquant", "", None, None)
            if "Bloc3" in bloc:
                # Chemin RELANCE (#516) : succès mais resultat_gh vide, aucune
                # issue n'est créée — voir _traiter_relance.
                return (True, "Bloc3", "bridge_agent", " — relance de #9", "", None, None)
            if "Bloc4" in bloc:
                return (True, "Bloc4", "bridge_agent", "",
                        "https://github.com/AlainDelree/Bridge_Agent/issues/13",
                        ["bridge", "for-linux"], {"timeout": 300})
            raise AssertionError(f"bloc inattendu : {bloc!r}")

        w._traiter_bloc = _traiter_bloc_fake

        chemin = cfg.inbox_dir / "lot.txt"
        _deposer(chemin,
                 "#Titre: Bloc1\nCorps1.\n"
                 "#Titre: Bloc2\nCorps2.\n"
                 "#Titre: Bloc3\nCorps3.\n"
                 "#Titre: Bloc4\nCorps4.\n")

        w.traiter_fichier(cfg, chemin)

        assert not chemin.exists(), "3/4 blocs OK (nb_ok > 0) : le fichier doit être supprimé"
        assert _types(appels) == ["recu", "creation", "refuse", "creation"], appels
        numeros_crees = [p["numero"] for u, p in appels if u == w.URL_NOTIFIER_CREATION_ISSUE]
        assert numeros_crees == [10, 13], numeros_crees
        refus = [p for u, p in appels if u == w.URL_NOTIFIER_FICHIER_REFUSE][0]
        assert refus == {"fichier": "lot.txt", "titre": "Bloc2", "motif": "titre manquant"}
    return {"ordre": _types(appels), "numeros_crees": numeros_crees}


def test_lot_tous_blocs_rejetes_pas_de_doublon():
    """Lot dont TOUS les blocs échouent : le fichier entier est déplacé vers
    rejected/ (comportement #508 inchangé), mais AUCUN événement
    fichier_refuse supplémentaire pour ce déplacement global — chaque bloc a
    déjà émis le sien pendant la boucle (pas de doublon, comme pour la
    journalisation, cf. _deplacer_vers_rejected)."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer_cfg(Path(tmp))
        appels = []
        w._poster_best_effort = lambda url, payload: appels.append((url, payload))
        w._traiter_bloc = lambda cfg_i, bloc: (False, "Bloc", "bridge_agent", "motif", "", None, None)

        chemin = cfg.inbox_dir / "lot.txt"
        _deposer(chemin, "#Titre: Bloc1\nCorps1.\n#Titre: Bloc2\nCorps2.\n")

        w.traiter_fichier(cfg, chemin)

        assert list(cfg.rejected_dir.glob("*REJETE*")), "fichier déplacé vers rejected/"
        # 1 fichier_recu + 2 fichier_refuse (un par bloc) — pas un de plus.
        assert _types(appels) == ["recu", "refuse", "refuse"], appels
    return {"ordre": _types(appels)}


# ─── app/issues_inbox.py::etat_inbox() : motif exposé ──────────────────────

def test_etat_inbox_expose_le_motif_complet():
    """Le motif de refus en texte intégral (accents compris) est exposé par
    `/issues-inbox/etat`, lu depuis le seul disque (sidecar `<nom>.motif`) —
    donc encore consultable après un redémarrage de new_issue.py (aucun état
    en mémoire n'est requis pour le retrouver)."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer_cfg(Path(tmp))
        fichier = cfg.inbox_dir / "mauvais.txt"
        fichier.write_text("contenu", encoding="utf-8")

        motif = "REDACTEUR incohérent avec PROJET : « scrabble » ≠ « bridge_agent »"
        cible = w._deplacer_vers_rejected(cfg, fichier, motif)
        assert cible is not None

        ancien_config = ii._config
        ancien_pid = ii.CHEMIN_PID
        ii._config = lambda: cfg
        ii.CHEMIN_PID = Path(tmp) / "logs" / "watcher-inexistant.pid"
        try:
            with APP_FLASK.test_request_context("/issues-inbox/etat"):
                rep = ii.etat_inbox()
        finally:
            ii._config = ancien_config
            ii.CHEMIN_PID = ancien_pid

        corps = rep.get_json()
        assert len(corps["rejetes"]) == 1, corps["rejetes"]
        assert corps["rejetes"][0]["nom"] == cible.name
        assert corps["rejetes"][0]["motif"] == motif
    return {"motif": corps["rejetes"][0]["motif"]}


def test_etat_inbox_motif_absent_pour_rejet_sans_sidecar():
    """Rétrocompatibilité : un fichier déjà présent dans rejected/ SANS
    sidecar `.motif` (rejet antérieur à #631, ou déposé manuellement) expose
    motif=None plutôt que de lever une erreur."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer_cfg(Path(tmp))
        (cfg.rejected_dir / "ancien__REJETE-motif-tronque.txt").write_text(
            "contenu", encoding="utf-8")

        ancien_config = ii._config
        ancien_pid = ii.CHEMIN_PID
        ii._config = lambda: cfg
        ii.CHEMIN_PID = Path(tmp) / "logs" / "watcher-inexistant.pid"
        try:
            with APP_FLASK.test_request_context("/issues-inbox/etat"):
                rep = ii.etat_inbox()
        finally:
            ii._config = ancien_config
            ii.CHEMIN_PID = ancien_pid

        corps = rep.get_json()
        assert len(corps["rejetes"]) == 1, corps["rejetes"]
        assert corps["rejetes"][0]["motif"] is None
    return {}


def test_etat_inbox_sidecar_motif_exclu_de_la_liste():
    """Le sidecar `<nom>.motif` lui-même ne doit jamais apparaître comme une
    entrée séparée de `rejetes` — un fichier rejeté = une ligne, jamais
    deux."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _preparer_cfg(Path(tmp))
        fichier = cfg.inbox_dir / "mauvais.txt"
        fichier.write_text("contenu", encoding="utf-8")
        w._deplacer_vers_rejected(cfg, fichier, "motif")

        ancien_config = ii._config
        ancien_pid = ii.CHEMIN_PID
        ii._config = lambda: cfg
        ii.CHEMIN_PID = Path(tmp) / "logs" / "watcher-inexistant.pid"
        try:
            with APP_FLASK.test_request_context("/issues-inbox/etat"):
                rep = ii.etat_inbox()
        finally:
            ii._config = ancien_config
            ii.CHEMIN_PID = ancien_pid

        corps = rep.get_json()
        assert len(corps["rejetes"]) == 1, corps["rejetes"]
    return {}


def main() -> int:
    tests = [
        ("notifier_fichier_recu : diffuse l'événement", test_notifier_fichier_recu_diffuse_evenement),
        ("notifier_fichier_recu : champ manquant → 400", test_notifier_fichier_recu_sans_fichier_400),
        ("notifier_creation_issue : diffuse l'événement (avec fichier)", test_notifier_creation_issue_diffuse_evenement_avec_fichier),
        ("notifier_creation_issue : champs manquants → 400", test_notifier_creation_issue_champs_manquants_400),
        ("emettre_creation_issue : appel direct, fichier=None", test_emettre_creation_issue_appel_direct_sans_fichier),
        ("notifier_fichier_refuse : diffuse l'événement", test_notifier_fichier_refuse_diffuse_evenement),
        ("notifier_fichier_refuse : titre absent → null", test_notifier_fichier_refuse_titre_absent_devient_null),
        ("notifier_fichier_refuse : champs manquants → 400", test_notifier_fichier_refuse_champs_manquants_400),
        ("watcher : ordre mono-bloc succès (recu, creation)", test_ordre_evenements_mono_bloc_succes),
        ("watcher : ordre mono-bloc rejeté (recu, refuse)", test_ordre_evenements_mono_bloc_rejete),
        ("watcher : ordre lot 4 blocs (RELANCE sans événement)", test_ordre_evenements_lot_multi_blocs),
        ("watcher : lot tout rejeté — pas de doublon fichier_refuse", test_lot_tous_blocs_rejetes_pas_de_doublon),
        ("etat_inbox : motif complet exposé (sidecar)", test_etat_inbox_expose_le_motif_complet),
        ("etat_inbox : motif absent → None (rétrocompat)", test_etat_inbox_motif_absent_pour_rejet_sans_sidecar),
        ("etat_inbox : sidecar .motif exclu de la liste", test_etat_inbox_sidecar_motif_exclu_de_la_liste),
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

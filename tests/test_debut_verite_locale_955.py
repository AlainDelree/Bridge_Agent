#!/usr/bin/env python3
"""Test de non-régression — issue #955, point 3 : le badge/décompte « en
cours » d'une issue (ligne de l'onglet Résultats, panneau Infrastructure)
venait UNIQUEMENT de `it["debut"]`, calculé par `_debut_traitement()`
(app/issues.py) à partir du dernier commentaire ACK posté par watcher.py sur
GitHub — une pure heuristique textuelle, jamais recoupée avec la réalité
locale (verrou fichier/process).

Scénario constaté le 25/11/2026 sur testvibe : « Arrêter » interrompt
PROPREMENT l'issue #20 en cours via le mécanisme CIBLÉ (#949) — commentaire
« ⛔ Interrompue sur demande (… étude #939) », PAS « Échec après N
tentatives » — puis arrête le watcher. `_debut_traitement()` ne réinitialise
`debut` QUE sur ce second marqueur (issue #588/#525) : le commentaire
d'interruption ciblée n'est jamais reconnu, `debut` reste donc figé sur l'ACK
du cycle interrompu. Une fois needs-human retiré (bouton « Relancer », sans
qu'aucun nouveau watcher ni nouvelle ACK n'ait eu lieu), `issues_en_attente()`
réaffichait ce VIEUX `debut` : l'interface montrait l'issue « en cours », avec
un décompte TIMEOUT reprenant l'heure de la tentative précédente, alors
qu'aucun process ni verrou n'existait plus.

Fix : `issues_en_attente()` ne fait plus jamais confiance à `debut` seul pour
une issue for-linux — il ne vaut « en cours » que si un verrou fichier LOCAL
(`app.watchers.tache_en_cours`, posé par le watcher CCL pour CETTE issue,
TOUJOURS créé avant la moindre ACK) le confirme. Sans ce verrou, `debut` est
remis à None (« en file »), quel que soit l'historique des commentaires
GitHub. Les issues for-windows (CCW, watcher délégué sur une autre machine,
aucun verrou visible ici) restent inchangées : l'absence dans
`tache_en_cours` n'y est jamais une preuve d'arrêt, voir docs/contexte/
interruption_issue.md.

Couvre, SANS vrai `gh` ni vrai sous-processus (`subprocess.run` substitué) :
- for-linux, ACK ancien + interruption ciblée (jamais reconnue par
  `_debut_traitement`), AUCUN verrou local → debut remis à None (le bug
  constaté, désormais corrigé) ;
- même scénario mais verrou local PRÉSENT pour ce numéro (issue réellement en
  cours) → debut conservé, jamais faussement remis à None ;
- for-windows, même ACK ancien, AUCUN verrou local (CCW n'en pose jamais ici)
  → debut conservé tel quel (hors périmètre, comportement inchangé).

Exécution :  python3 tests/test_debut_verite_locale_955.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.issues as ai  # noqa: E402
import app.watchers as aw  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CFG_TESTVIBE = SimpleNamespace(nom="testvibe", depot="AlainDelree/testvibe",
                                 max_essais=3, timeout_claude=300, timeout_chef=1200)


class Patch:
    """Même utilitaire minimal que tests/test_creation_issue_enrichie_634.py
    (pas de dépendance à unittest.mock)."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


def _iso(delta_s: float) -> str:
    dt = datetime.now(timezone.utc) - timedelta(seconds=delta_s)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


class FauxResultat:
    def __init__(self, returncode, stdout=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, ""


def _faux_run_pour(issue: dict, commentaires: list):
    """Fabrique un faux subprocess.run : `gh issue list --label for-linux`
    renvoie `[issue]`, `--label for-windows` renvoie `[]`, `gh issue view
    <numero> --json comments` renvoie `commentaires`."""
    def faux_run(cmd, **kwargs):
        if "list" in cmd:
            label = cmd[cmd.index("--label") + 1]
            corps = [issue] if label in issue["labels_nom"] else []
            return FauxResultat(0, stdout=json.dumps(corps))
        if "view" in cmd:
            return FauxResultat(0, stdout=json.dumps({"comments": commentaires}))
        raise AssertionError(f"commande gh inattendue : {cmd}")
    return faux_run


def _issue_avec_interruption_ciblee_ancienne(numero: int, labels_nom: list[str]) -> tuple[dict, list]:
    """Issue déjà needs-human RETIRÉ (ouverte, sans needs-human dans les
    labels renvoyés par `gh issue list` — déjà le cas réel : LABEL_ECHEC
    n'exclut que needs-human encore PRÉSENT) dont l'historique porte une ACK
    ancienne puis une interruption CIBLÉE (#949) : AUCUN commentaire
    "Échec après N tentatives", donc `_debut_traitement` ne réinitialise
    jamais `debut` par lui-même — exactement le cas réel du 25/11/2026."""
    issue = {
        "number": numero, "title": "Une tâche", "body": "| PROJET | testvibe |\n",
        "labels": [{"name": n} for n in labels_nom], "labels_nom": labels_nom,
    }
    commentaires = [
        {"body": "🤖 ACK — watcher.py a pris en charge cette issue.", "createdAt": _iso(600)},
        {"body": "⛔ Interrompue sur demande (interruption ciblée de cette issue, étude #939).\n\n"
                  "Ce n'est **pas** un échec…", "createdAt": _iso(60)},
    ]
    return issue, commentaires


def scenario_for_linux_sans_verrou_local_debut_remis_a_none():
    """Cause réelle de l'issue #955 : interruption ciblée jamais reconnue par
    _debut_traitement + AUCUN verrou local (watcher arrêté) → `debut` DOIT
    être remis à None, sinon l'interface réaffiche un vieux décompte pour une
    issue qui ne tourne plus."""
    issue, commentaires = _issue_avec_interruption_ciblee_ancienne(20, ["bridge", "for-linux"])
    with Patch(ai, "projet_par_nom", lambda nom: CFG_TESTVIBE if nom == "testvibe" else None), \
         Patch(ai.subprocess, "run", _faux_run_pour(issue, commentaires)), \
         Patch(aw, "tache_en_cours", lambda cfg: []):
        with APP_FLASK.test_request_context("/issues-en-attente/testvibe"):
            rep = ai.issues_en_attente("testvibe")
    corps = rep.get_json()
    assert len(corps) == 1, corps
    assert corps[0]["number"] == 20, corps
    assert corps[0]["debut"] is None, (
        f"debut aurait dû être remis à None (aucun verrou local), obtenu : {corps[0]['debut']}")
    return {"debut": corps[0]["debut"]}


def scenario_for_linux_avec_verrou_local_debut_conserve():
    """Même historique de commentaires, mais un verrou local existe bien pour
    CE numéro (watcher.py la traite réellement) → `debut` ne doit JAMAIS être
    faussement remis à None pour une issue réellement en cours."""
    issue, commentaires = _issue_avec_interruption_ciblee_ancienne(20, ["bridge", "for-linux"])
    verrou_attendu_ack = commentaires[0]["createdAt"]
    with Patch(ai, "projet_par_nom", lambda nom: CFG_TESTVIBE if nom == "testvibe" else None), \
         Patch(ai.subprocess, "run", _faux_run_pour(issue, commentaires)), \
         Patch(aw, "tache_en_cours", lambda cfg: [{"rep": "x", "mode": "ecriture", "numero": 20}]):
        with APP_FLASK.test_request_context("/issues-en-attente/testvibe"):
            rep = ai.issues_en_attente("testvibe")
    corps = rep.get_json()
    assert corps[0]["debut"] == verrou_attendu_ack, (
        f"debut aurait dû rester l'ACK ({verrou_attendu_ack}) — verrou local présent, "
        f"obtenu : {corps[0]['debut']}")
    return {"debut": corps[0]["debut"]}


def scenario_for_windows_hors_perimetre_debut_inchange():
    """Issue for-windows : AUCUN verrou local n'est jamais visible ici pour
    CCW (watcher délégué, autre machine) — la vérité locale ne s'applique
    donc PAS à for-windows, `debut` doit rester tel que calculé par
    _debut_traitement, même sans verrou local (tache_en_cours retourne
    toujours [] pour un projet CCW, ce n'est jamais une preuve d'arrêt)."""
    issue, commentaires = _issue_avec_interruption_ciblee_ancienne(30, ["bridge", "for-windows"])
    ack_attendue = commentaires[0]["createdAt"]
    with Patch(ai, "projet_par_nom", lambda nom: CFG_TESTVIBE if nom == "testvibe" else None), \
         Patch(ai.subprocess, "run", _faux_run_pour(issue, commentaires)), \
         Patch(aw, "tache_en_cours", lambda cfg: []):
        with APP_FLASK.test_request_context("/issues-en-attente/testvibe"):
            rep = ai.issues_en_attente("testvibe")
    corps = rep.get_json()
    assert corps[0]["debut"] == ack_attendue, (
        f"debut d'une issue for-windows ne doit jamais dépendre des verrous locaux CCL, "
        f"attendu {ack_attendue}, obtenu : {corps[0]['debut']}")
    return {"debut": corps[0]["debut"]}


def main() -> int:
    tests = [
        ("#955 : for-linux, interruption ciblée + aucun verrou local → debut remis à None",
         scenario_for_linux_sans_verrou_local_debut_remis_a_none),
        ("#955 : for-linux, verrou local présent → debut JAMAIS faussement remis à None",
         scenario_for_linux_avec_verrou_local_debut_conserve),
        ("#955 : for-windows hors périmètre (CCW) → debut inchangé sans verrou local",
         scenario_for_windows_hors_perimetre_debut_inchange),
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

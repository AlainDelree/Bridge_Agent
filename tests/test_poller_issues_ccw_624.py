#!/usr/bin/env python3
"""Test de non-régression — issue #624 : le poller de notifications
(app/notifications_poller.py) surveille désormais une LISTE d'issues CCW
ouvertes (depot, numéro), et non plus des projets filtrés sur le champ LABEL
de leur .conf (bug introduit par #614, diagnostiqué en #621 — remplace #623).

Couvre, SANS aucun accès réseau/gh réel (toutes les fonctions qui invoquent
`gh` — `_gh_list`, `_gh_view_issue`, `_commentaires_issue` — sont
monkeypatchées, sur le modèle de tests/test_fenetre_transitoire_echec_588.py
qui réutilise déjà `_debut_traitement` sans mock, exercé ici pour de vrai) :

- remplissage de la liste surveillée : balayage initial (`_balayage_initial`,
  tous les projets configurés, pas seulement ceux dont le `.conf` porte
  `LABEL=for-windows`) et ajout direct (`ajouter_issue_surveillee`), filtré
  par `BRIDGE_NOTIF_SCOPE` (défaut `for-windows`) ;
- retrait de la liste dès la transition terminale (done/needs-human) détectée,
  avec l'anti-spam au démarrage (aucune notification pour une transition déjà
  présente à l'amorçage) et le filtre de récence conservés ;
- détection de la prise en charge (ACK), en réutilisant réellement
  `app.issues._debut_traitement` (pas de duplication de la logique) ;
- liste vide → AUCUN appel gh à ce cycle (`_gh_view_issue`/`_commentaires_issue`
  ne sont même pas invoquées).

Exécution :  python3 tests/test_poller_issues_ccw_624.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.notifications_poller as poller  # noqa: E402
import etat_rate_limit  # noqa: E402
import notifications  # noqa: E402
import traitement_fin  # noqa: E402


def _iso(delta_s: float) -> str:
    """Horodatage ISO 8601 (format gh, suffixe Z) à `delta_s` secondes avant
    maintenant (delta_s positif = dans le passé)."""
    dt = datetime.now(timezone.utc) - timedelta(seconds=delta_s)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _cfg(nom="demo", depot="AlainDelree/Demo"):
    return SimpleNamespace(nom=nom, depot=depot, url_ntfy="https://ntfy.sh/demo",
                            script_bip=Path("/inexistant/traitement_fin.py"),
                            tonalite_bip=0)


class _Interdit(Exception):
    """Levée par les fakes `_gh_list`/`_gh_view_issue`/`_commentaires_issue`
    quand ils ne devraient JAMAIS être appelés (scénario liste vide)."""


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with`. Utilitaire minimal, pas de dépendance à unittest.mock (cohérent
    avec le reste de tests/, qui reste en asserts + fonctions pures)."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


def _reinitialiser():
    poller._ISSUES_SURVEILLEES.clear()


# ─── Scénarios : remplissage de la liste ───────────────────────────────────

def scenario_ajout_direct_filtre_scope():
    """ajouter_issue_surveillee respecte BRIDGE_NOTIF_SCOPE (défaut
    for-windows) : une issue for-windows est ajoutée, une issue for-linux ne
    l'est pas — sans distinction de projet (contrairement à l'ancien
    _projets_dans_la_portee, filtré sur le .conf, cf. #614/#621)."""
    _reinitialiser()
    assert poller.ajouter_issue_surveillee("AlainDelree/Demo", 1, ["bridge", "for-windows"]) is True
    assert ("AlainDelree/Demo", 1) in poller._ISSUES_SURVEILLEES
    assert poller.ajouter_issue_surveillee("AlainDelree/Demo", 2, ["bridge", "for-linux"]) is False
    assert ("AlainDelree/Demo", 2) not in poller._ISSUES_SURVEILLEES


def scenario_ajout_direct_idempotent():
    """Ré-ajouter une issue déjà surveillée ne réinitialise pas son état
    (ack_connu conservé) — sinon une relance re-déclencherait un balayage
    complet inutilement à chaque appel."""
    _reinitialiser()
    poller.ajouter_issue_surveillee("AlainDelree/Demo", 1, ["for-windows"])
    poller._ISSUES_SURVEILLEES[("AlainDelree/Demo", 1)]["ack_connu"] = True
    poller.ajouter_issue_surveillee("AlainDelree/Demo", 1, ["for-windows"])
    assert poller._ISSUES_SURVEILLEES[("AlainDelree/Demo", 1)]["ack_connu"] is True


def scenario_balayage_initial_tous_projets():
    """_balayage_initial() interroge TOUS les projets configurés (pas
    seulement ceux dont le .conf porte LABEL=for-windows, bug #614/#621) et
    ajoute chaque issue for-windows ouverte retournée par gh."""
    _reinitialiser()
    projets = [_cfg("alpha", "AlainDelree/Alpha"), _cfg("beta", "AlainDelree/Beta")]
    appels = []

    def faux_gh_list(depot, label, state, champs):
        appels.append((depot, label, state))
        if depot == "AlainDelree/Alpha" and label == "for-windows":
            return [{"number": 42, "labels": [{"name": "for-windows"}]}]
        return []

    with Patch(poller, "lister_projets", lambda: projets), \
         Patch(poller, "_gh_list", faux_gh_list):
        poller._balayage_initial()

    assert ("AlainDelree/Alpha", 42) in poller._ISSUES_SURVEILLEES
    assert ("AlainDelree/Beta", 42) not in poller._ISSUES_SURVEILLEES
    # Un appel par (projet, label dans la portée) — SCOPE=for-windows par
    # défaut → un seul label demandé, pour CHAQUE projet.
    assert appels == [("AlainDelree/Alpha", "for-windows", "open"),
                       ("AlainDelree/Beta", "for-windows", "open")]


# ─── Scénarios : retrait après transition terminale ────────────────────────

def scenario_transition_done_retire_et_notifie():
    """Une issue surveillée qui se ferme avec `done` est notifiée (bip/bulle/
    ntfy + SSE fin_issue) puis RETIRÉE de la liste — hors amorçage."""
    _reinitialiser()
    cfg = _cfg()
    poller.ajouter_issue_surveillee(cfg.depot, 10, ["for-windows"])

    notifs, sse_fin = [], []

    def faux_gh_view(depot, numero, champs):
        return {"state": "CLOSED", "title": "Titre", "labels": [{"name": "done"}],
                "closedAt": _iso(5), "updatedAt": _iso(5)}

    with Patch(poller, "_gh_view_issue", faux_gh_view), \
         Patch(poller, "projet_par_depot", lambda depot: cfg), \
         Patch(notifications, "notifier", lambda *a, **k: notifs.append((a, k))), \
         Patch(traitement_fin, "notifier_fin_issue", lambda p, n: sse_fin.append((p, n))), \
         Patch(etat_rate_limit, "maj_rate_limit", lambda origine: None):
        poller._cycle(premier_passage=False)

    assert (cfg.depot, 10) not in poller._ISSUES_SURVEILLEES
    assert sse_fin == [(cfg.nom, 10)]
    assert len(notifs) == 1


def scenario_transition_a_lamorcage_pas_de_notification():
    """Anti-spam au démarrage (garde conservée) : une transition needs-human
    déjà présente au tout premier cycle est retirée SILENCIEUSEMENT — pas de
    salve pour une transition ancienne découverte au balayage initial."""
    _reinitialiser()
    cfg = _cfg()
    poller.ajouter_issue_surveillee(cfg.depot, 11, ["for-windows"])

    notifs, sse_fin = [], []

    def faux_gh_view(depot, numero, champs):
        return {"state": "OPEN", "title": "Titre", "labels": [{"name": "needs-human"}],
                "updatedAt": _iso(5)}

    with Patch(poller, "_gh_view_issue", faux_gh_view), \
         Patch(poller, "projet_par_depot", lambda depot: cfg), \
         Patch(notifications, "notifier", lambda *a, **k: notifs.append((a, k))), \
         Patch(traitement_fin, "notifier_fin_issue", lambda p, n: sse_fin.append((p, n))), \
         Patch(etat_rate_limit, "maj_rate_limit", lambda origine: None):
        poller._cycle(premier_passage=True)   # AMORÇAGE

    assert (cfg.depot, 11) not in poller._ISSUES_SURVEILLEES
    assert notifs == []
    assert sse_fin == []


def scenario_transition_trop_ancienne_ignoree():
    """Filtre de récence (garde conservée) : une clôture `done` dont
    l'horodatage dépasse BRIDGE_NOTIF_RECENCE_MIN n'est pas notifiée, mais
    l'issue est quand même retirée (elle est de toute façon fermée)."""
    _reinitialiser()
    cfg = _cfg()
    poller.ajouter_issue_surveillee(cfg.depot, 12, ["for-windows"])

    notifs = []

    def faux_gh_view(depot, numero, champs):
        return {"state": "CLOSED", "title": "Titre", "labels": [{"name": "done"}],
                "closedAt": _iso((poller.RECENCE_MIN + 5) * 60), "updatedAt": _iso(5)}

    with Patch(poller, "_gh_view_issue", faux_gh_view), \
         Patch(poller, "projet_par_depot", lambda depot: cfg), \
         Patch(notifications, "notifier", lambda *a, **k: notifs.append((a, k))), \
         Patch(traitement_fin, "notifier_fin_issue", lambda p, n: notifs.append("sse")), \
         Patch(etat_rate_limit, "maj_rate_limit", lambda origine: None):
        poller._cycle(premier_passage=False)

    assert (cfg.depot, 12) not in poller._ISSUES_SURVEILLEES
    assert notifs == []


# ─── Scénarios : ACK réutilisée de /issues-en-attente ──────────────────────

def scenario_ack_detectee_pousse_debut_issue():
    """La détection de prise en charge réutilise app.issues._debut_traitement
    (exercé pour de vrai, pas mocké) : une ACK trouvée déclenche le SSE
    debut_issue, une seule fois (ack_connu mémorisé, pas de re-détection ni de
    ré-appel à _commentaires_issue au cycle suivant)."""
    _reinitialiser()
    cfg = _cfg()
    poller.ajouter_issue_surveillee(cfg.depot, 13, ["for-windows"])

    appels_commentaires = []

    def faux_gh_view(depot, numero, champs):
        return {"state": "OPEN", "title": "Titre", "labels": [{"name": "for-windows"}],
                "updatedAt": _iso(5)}

    def faux_commentaires(cfg_, numero):
        appels_commentaires.append(numero)
        return [{"body": "🤖 ACK — watcher.py a pris en charge cette issue.",
                 "createdAt": _iso(5)}]

    sse_debut = []
    with Patch(poller, "_gh_view_issue", faux_gh_view), \
         Patch(poller, "projet_par_depot", lambda depot: cfg), \
         Patch(poller, "_commentaires_issue", faux_commentaires), \
         Patch(traitement_fin, "notifier_debut_issue", lambda p, n: sse_debut.append((p, n))), \
         Patch(etat_rate_limit, "maj_rate_limit", lambda origine: None):
        poller._cycle(premier_passage=False)
        assert sse_debut == [(cfg.nom, 13)]
        assert poller._ISSUES_SURVEILLEES[(cfg.depot, 13)]["ack_connu"] is True

        # Deuxième cycle : ACK déjà connue → pas de ré-appel à
        # _commentaires_issue, pas de second SSE.
        poller._cycle(premier_passage=False)
        assert appels_commentaires == [13]
        assert sse_debut == [(cfg.nom, 13)]


def scenario_ack_a_lamorcage_pas_de_sse():
    """ACK déjà présente au tout premier cycle : mémorisée SANS pousser le
    SSE debut_issue (même anti-spam qu'au démarrage pour les transitions)."""
    _reinitialiser()
    cfg = _cfg()
    poller.ajouter_issue_surveillee(cfg.depot, 14, ["for-windows"])

    def faux_gh_view(depot, numero, champs):
        return {"state": "OPEN", "title": "Titre", "labels": [{"name": "for-windows"}],
                "updatedAt": _iso(5)}

    def faux_commentaires(cfg_, numero):
        return [{"body": "🤖 ACK — watcher.py a pris en charge cette issue.",
                 "createdAt": _iso(600)}]

    sse_debut = []
    with Patch(poller, "_gh_view_issue", faux_gh_view), \
         Patch(poller, "projet_par_depot", lambda depot: cfg), \
         Patch(poller, "_commentaires_issue", faux_commentaires), \
         Patch(traitement_fin, "notifier_debut_issue", lambda p, n: sse_debut.append((p, n))), \
         Patch(etat_rate_limit, "maj_rate_limit", lambda origine: None):
        poller._cycle(premier_passage=True)

    assert sse_debut == []
    assert poller._ISSUES_SURVEILLEES[(cfg.depot, 14)]["ack_connu"] is True


# ─── Scénario : liste vide → aucun appel gh ─────────────────────────────────

def scenario_liste_vide_aucun_appel_gh():
    """Liste surveillée vide → _cycle() ne doit appeler NI _gh_view_issue NI
    _commentaires_issue NI etat_rate_limit.maj_rate_limit — c'est le cœur du
    fix #624/#621 (coût quasi nul quand CCW n'a aucune issue en cours)."""
    _reinitialiser()
    assert poller._ISSUES_SURVEILLEES == {}

    def interdit(*a, **k):
        raise _Interdit("appel gh alors que la liste surveillée est vide")

    with Patch(poller, "_gh_view_issue", interdit), \
         Patch(poller, "_commentaires_issue", interdit), \
         Patch(etat_rate_limit, "maj_rate_limit", interdit):
        poller._cycle(premier_passage=False)  # ne doit lever aucune exception


def main():
    tests = [
        ("ajout direct filtré par BRIDGE_NOTIF_SCOPE", scenario_ajout_direct_filtre_scope),
        ("ajout direct idempotent (ack_connu préservé)", scenario_ajout_direct_idempotent),
        ("balayage initial : tous les projets, pas seulement LABEL=for-windows", scenario_balayage_initial_tous_projets),
        ("transition done → notifiée puis retirée", scenario_transition_done_retire_et_notifie),
        ("transition déjà présente à l'amorçage → retirée sans notifier", scenario_transition_a_lamorcage_pas_de_notification),
        ("transition trop ancienne → retirée sans notifier", scenario_transition_trop_ancienne_ignoree),
        ("ACK détectée (réutilise _debut_traitement) → SSE debut_issue, une fois", scenario_ack_detectee_pousse_debut_issue),
        ("ACK déjà présente à l'amorçage → pas de SSE", scenario_ack_a_lamorcage_pas_de_sse),
        ("liste vide → aucun appel gh", scenario_liste_vide_aucun_appel_gh),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            fn()
            print(f"  ✓ {nom}")
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

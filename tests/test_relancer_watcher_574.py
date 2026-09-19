#!/usr/bin/env python3
"""Test de non-régression — issue #574 : le bouton web « 🔄 Relancer »
(`app/interruption.py::route_relancer()`, route `/relancer-issue`) redémarre
désormais le watcher CCL cible s'il s'était éteint entre-temps (#200) —
même mécanisme que la création d'issue (`app/issues.py::envoyer`, #202) et
que le bloc RELANCE (`scripts/watcher_issues_inbox.py::_traiter_relance`,
#572).

Couvre, SANS vrai `gh` ni vrai sous-processus watcher (`_retirer_label_gh`/
`_commenter_gh`/`demarrer_watcher` substitués) :
- watcher éteint (for-linux) → redémarré, tracé dans le commentaire posté ET
  dans la réponse JSON ;
- watcher déjà actif → aucune trace, `watcher_demarre=False` ;
- label for-windows (pas for-linux) → `demarrer_watcher` jamais appelé
  (traité par CCW, rien à démarrer côté Linux) ;
- dépôt sans projet configuré → aucun crash, relance quand même effectuée ;
- `demarrer_watcher` qui lève une exception → la relance réussit quand même
  (échec du redémarrage tracé, jamais bloquant) ;
- `forcer=False` systématiquement (idempotent, ne tue jamais un watcher déjà
  actif).

Exécution :  python3 tests/test_relancer_watcher_574.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

from app import interruption  # noqa: E402
import app.watchers as watchers_mod  # noqa: E402

APP_FLASK = flask.Flask(__name__)

CFG_BRIDGE_AGENT = SimpleNamespace(depot="AlainDelree/Bridge_Agent", nom="bridge_agent")


def _appeler_relancer(payload: dict):
    with APP_FLASK.test_request_context("/relancer-issue", json=payload):
        return interruption.route_relancer().get_json()


def _neutraliser_gh(appels: dict):
    """Substitue les deux appels `gh` de relancer_issue() (retrait de label +
    commentaire) — capture le commentaire réellement posté, aucun accès
    réseau."""
    def _faux_retrait(depot, numero, label):
        return "succes", f"Label « {label} » retiré."

    def _faux_commentaire(depot, numero, message):
        appels["commentaire"] = message
        return "succes", "Commentaire posté."

    interruption._retirer_label_gh = _faux_retrait
    interruption._commenter_gh = _faux_commentaire


def scenario_watcher_eteint_redemarre_et_trace():
    """for-linux, watcher éteint (demarrer_watcher retourne demarre=True) :
    redémarré, tracé dans le commentaire GitHub ET dans la réponse JSON."""
    appels = {}
    _neutraliser_gh(appels)
    interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT

    def _faux_demarrer_watcher(cfg, forcer=False):
        assert forcer is False, "doit toujours être appelé avec forcer=False (idempotent)"
        appels["cfg_nom"] = cfg.nom
        return True, 9999

    watchers_mod.demarrer_watcher = _faux_demarrer_watcher

    r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77,
                            "labels": ["bridge", "for-linux"]})

    assert r["succes"], r
    assert r["statut_global"] == "ok", r
    assert r["watcher_demarre"] is True, r
    assert r["watcher_pid"] == 9999, r
    assert appels["cfg_nom"] == "bridge_agent", appels
    assert "redémarré automatiquement" in appels["commentaire"], appels["commentaire"]
    assert "pid 9999" in appels["commentaire"], appels["commentaire"]
    return {"watcher_demarre": r["watcher_demarre"]}


def scenario_watcher_deja_actif_pas_de_trace():
    """for-linux, watcher déjà actif (demarre=False) : aucune trace de
    redémarrage, ni dans le commentaire ni dans la réponse JSON — cohérent
    avec #202/#572 (silencieux quand il n'y a rien à faire)."""
    appels = {}
    _neutraliser_gh(appels)
    interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT
    watchers_mod.demarrer_watcher = lambda cfg, forcer=False: (False, 4242)

    r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77,
                            "labels": ["for-linux"]})

    assert r["succes"], r
    assert r["watcher_demarre"] is False, r
    assert "redémarré" not in appels["commentaire"], appels["commentaire"]
    return {}


def scenario_label_for_windows_watcher_jamais_appele():
    """Issue for-windows : traitée par CCW, rien à démarrer côté Linux —
    demarrer_watcher n'est jamais invoqué."""
    appels = {"demarrer_watcher_appele": False}
    _neutraliser_gh(appels)
    interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT

    def _demarrer_watcher_qui_ne_devrait_pas_etre_appele(cfg, forcer=False):
        appels["demarrer_watcher_appele"] = True
        return True, 1

    watchers_mod.demarrer_watcher = _demarrer_watcher_qui_ne_devrait_pas_etre_appele

    r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77,
                            "labels": ["bridge", "for-windows"]})

    assert r["succes"], r
    assert r["watcher_demarre"] is None, r
    assert not appels["demarrer_watcher_appele"], "demarrer_watcher ne doit pas être appelé pour for-windows"
    assert "redémarré" not in appels["commentaire"], appels["commentaire"]
    return {}


def scenario_depot_sans_projet_configure_aucun_crash():
    """Dépôt sans projet configuré (projet_par_depot renvoie None) : la
    relance réussit quand même, sans tenter de redémarrer quoi que ce
    soit."""
    appels = {"demarrer_watcher_appele": False}
    _neutraliser_gh(appels)
    interruption.projet_par_depot = lambda depot: None

    def _demarrer_watcher_qui_ne_devrait_pas_etre_appele(cfg, forcer=False):
        appels["demarrer_watcher_appele"] = True
        return True, 1

    watchers_mod.demarrer_watcher = _demarrer_watcher_qui_ne_devrait_pas_etre_appele

    r = _appeler_relancer({"depot": "AlainDelree/Depot-Inconnu", "numero": 5,
                            "labels": ["for-linux"]})

    assert r["succes"], r
    assert r["watcher_demarre"] is None, r
    assert not appels["demarrer_watcher_appele"]
    return {}


def scenario_echec_demarrage_watcher_trace_sans_bloquer():
    """demarrer_watcher lève une exception : la relance elle-même réussit
    quand même (label retiré, commentaire posté), l'échec du redémarrage est
    tracé dans le commentaire — jamais transformé en erreur de relance."""
    appels = {}
    _neutraliser_gh(appels)
    interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT

    def _demarrer_watcher_qui_echoue(cfg, forcer=False):
        raise RuntimeError("configs/bridge_agent.conf illisible")

    watchers_mod.demarrer_watcher = _demarrer_watcher_qui_echoue

    r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77,
                            "labels": ["for-linux"]})

    assert r["succes"], r
    assert r["statut_global"] == "ok", r   # la relance elle-même n'échoue pas à cause du watcher
    assert r["watcher_demarre"] is None, r
    assert "échoué" in appels["commentaire"], appels["commentaire"]
    assert "configs/bridge_agent.conf illisible" in appels["commentaire"], appels["commentaire"]
    return {}


def scenario_labels_absents_aucun_redemarrage():
    """Aucun label transmis (payload minimal) : ni for-linux ni for-windows
    → pas de redémarrage tenté, la relance réussit quand même."""
    appels = {"demarrer_watcher_appele": False}
    _neutraliser_gh(appels)
    interruption.projet_par_depot = lambda depot: CFG_BRIDGE_AGENT

    def _demarrer_watcher_qui_ne_devrait_pas_etre_appele(cfg, forcer=False):
        appels["demarrer_watcher_appele"] = True
        return True, 1

    watchers_mod.demarrer_watcher = _demarrer_watcher_qui_ne_devrait_pas_etre_appele

    r = _appeler_relancer({"depot": "AlainDelree/Bridge_Agent", "numero": 77})

    assert r["succes"], r
    assert not appels["demarrer_watcher_appele"]
    return {}


def main():
    ancien_projet_par_depot = interruption.projet_par_depot
    ancien_retrait_label = interruption._retirer_label_gh
    ancien_commentaire = interruption._commenter_gh
    ancien_demarrer_watcher = watchers_mod.demarrer_watcher

    tests = [
        ("route_relancer : watcher éteint → redémarré et tracé (#574)", scenario_watcher_eteint_redemarre_et_trace),
        ("route_relancer : watcher déjà actif → aucune trace (#574)", scenario_watcher_deja_actif_pas_de_trace),
        ("route_relancer : for-windows → demarrer_watcher jamais appelé (#574)", scenario_label_for_windows_watcher_jamais_appele),
        ("route_relancer : dépôt sans projet configuré → aucun crash (#574)", scenario_depot_sans_projet_configure_aucun_crash),
        ("route_relancer : échec démarrage watcher tracé sans bloquer la relance (#574)", scenario_echec_demarrage_watcher_trace_sans_bloquer),
        ("route_relancer : aucun label transmis → aucun redémarrage tenté (#574)", scenario_labels_absents_aucun_redemarrage),
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
        finally:
            interruption.projet_par_depot = ancien_projet_par_depot
            interruption._retirer_label_gh = ancien_retrait_label
            interruption._commenter_gh = ancien_commentaire
            watchers_mod.demarrer_watcher = ancien_demarrer_watcher

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

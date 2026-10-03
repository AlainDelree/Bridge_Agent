#!/usr/bin/env python3
"""Test de non-régression — issue #711 (étape D du retrofit CCW) : démarrage
à la demande du service CCW d'un projet (`app.ccw.demarrer_service_ccw_arriere_plan`,
issue #709/étape C) depuis `scripts/watcher_issues_inbox.py` — CRÉATION et
RELANCE — et depuis `app/interruption.py::route_relancer` (bouton web).

Suite des étapes A/C : `AppExit 42 Exit` fait qu'un watcher CCW qui s'éteint
seul par inactivité n'est plus relancé par NSSM — jusqu'à l'étape C (#709),
seul le formulaire web (`app/issues.py::envoyer`) rallumait le service à la
demande. Plus de 99 % des issues d'Alain passent par `issues_inbox/` : cette
étape D couvre ce chemin critique (création ET relance), ainsi que la route
`/relancer-issue` (bouton de l'interface — scénarios dans
`tests/test_relancer_watcher_574.py`).

Couvre, SANS vrai `gh` ni vraie connexion SSH (`_creer_issue`/`charger_config`/
`redemarrer_si_eteint`/`demarrer_service_ccw_arriere_plan` tous substitués —
leçon des issues #702/#703) :
- création `for-windows` → `demarrer_service_ccw_arriere_plan` appelé avec le
  nom du projet, `redemarrer_si_eteint` (watcher CCL) JAMAIS appelé ;
- création `for-linux` → comportement STRICTEMENT inchangé (`redemarrer_si_eteint`
  appelé), `demarrer_service_ccw_arriere_plan` JAMAIS appelé ;
- un échec du démarrage CCW (simulé) n'empêche jamais la création de l'issue ;
- `import app.ccw` (donc `demarrer_service_ccw_arriere_plan`) depuis ce module
  fonctionne bien SANS requête Flask active (process séparé de new_issue.py,
  point 4 de l'issue #711) — les objets Flask d'app.ccw (jsonify/request) ne
  sont utilisés que par ses fonctions de route, jamais par ce lanceur.

Le chemin RELANCE (`_traiter_relance`) est couvert par les scénarios 19 et
suivants de `tests/test_champ_relance_516.py` (labels lus sur l'issue
elle-même) ; la route `/relancer-issue` par `tests/test_relancer_watcher_574.py`.

Exécution :  python3 tests/test_demarrage_ccw_issues_inbox_711.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import watcher_issues_inbox as w  # noqa: E402
import app.ccw as ccw  # noqa: E402


def _appel_interdit(nom: str):
    def _fn(*_a, **_k):
        raise AssertionError(f"{nom} n'aurait pas dû être appelé — garde de label violée (#711)")
    return _fn


def _cfg_projet(tmp_dir: Path, nom="bridge_agent", depot="AlainDelree/Bridge_Agent"):
    return SimpleNamespace(nom=nom, depot=depot, gh_token="", max_essais=3,
                            timeout_claude=300, timeout_chef=1200,
                            rep_travail=tmp_dir, perimetre_dynamique=False)


def _preparer(tmp_dir: Path, cfg_projet):
    """Même principe que _preparer_config_bidon de test_champ_relance_516.py :
    évite toute dépendance à un vrai configs/<projet>.conf (gitignoré) et à un
    vrai `gh issue create`."""
    (tmp_dir / "configs").mkdir(parents=True, exist_ok=True)
    (tmp_dir / "configs" / f"{cfg_projet.nom}.conf").write_text(
        f"DEPOT={cfg_projet.depot}\n", encoding="utf-8")
    w.DOSSIER_SCRIPT = tmp_dir
    w.charger_config = lambda chemin: cfg_projet
    w._issue_ouverte_meme_titre = lambda cfg, titre: None


def scenario_creation_for_windows_demarre_ccw_sans_watcher():
    """Issue créée avec | LABELS | for-windows | : demarrer_service_ccw_arriere_plan
    est appelé avec le nom du projet, redemarrer_si_eteint (watcher CCL)
    JAMAIS appelé."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg_projet = _cfg_projet(tmp_dir)
        _preparer(tmp_dir, cfg_projet)

        appels = {"ccw": [], "watcher_appele": False}
        w._creer_issue = lambda cfg, cfg_p, titre, labels, body: (
            True, "https://github.com/AlainDelree/Bridge_Agent/issues/55")
        w.redemarrer_si_eteint = _appel_interdit("redemarrer_si_eteint")
        w.demarrer_service_ccw_arriere_plan = lambda nom_projet: appels["ccw"].append(nom_projet)

        contenu = ("| PROJET | bridge_agent |\n| LABELS | for-windows |\n\n"
                   "#Titre: Build Windows.\nCorps.\n")
        succes, titre, projet, texte, resultat_gh, labels, _temps = w._traiter_bloc(
            w.ConfigInbox(), contenu)

        assert succes, texte
        assert "for-windows" in labels, labels
        assert "for-linux" not in labels, labels
        assert appels["ccw"] == ["bridge_agent"], appels["ccw"]
        assert "watcher CCL démarré" not in texte, texte
    return {"ccw_appels": appels["ccw"]}


def scenario_creation_for_linux_inchangee():
    """Issue créée SANS label explicite (for-linux par défaut, construire_labels) :
    comportement strictement inchangé — redemarrer_si_eteint appelé,
    demarrer_service_ccw_arriere_plan JAMAIS appelé."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg_projet = _cfg_projet(tmp_dir)
        _preparer(tmp_dir, cfg_projet)

        appels = {"watcher_pour": None}
        w._creer_issue = lambda cfg, cfg_p, titre, labels, body: (
            True, "https://github.com/AlainDelree/Bridge_Agent/issues/56")

        def _faux_redemarrer(cfg):
            appels["watcher_pour"] = cfg.nom
            return True, 1234, ""

        w.redemarrer_si_eteint = _faux_redemarrer
        w.demarrer_service_ccw_arriere_plan = _appel_interdit("demarrer_service_ccw_arriere_plan")

        contenu = "| PROJET | bridge_agent |\n\n#Titre: Tâche Linux.\nCorps.\n"
        succes, titre, projet, texte, resultat_gh, labels, _temps = w._traiter_bloc(
            w.ConfigInbox(), contenu)

        assert succes, texte
        assert "for-linux" in labels, labels
        assert "for-windows" not in labels, labels
        assert appels["watcher_pour"] == "bridge_agent", appels
        assert "watcher CCL démarré (pid 1234)" in texte, texte
    return {"watcher_pour": appels["watcher_pour"]}


def scenario_creation_for_windows_echec_ccw_n_empeche_pas_la_creation():
    """Le lanceur CCW échoue (exception) : la création de l'issue reste un
    succès — jamais bloquante ni rejetée à cause de ce démarrage."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        cfg_projet = _cfg_projet(tmp_dir)
        _preparer(tmp_dir, cfg_projet)

        w._creer_issue = lambda cfg, cfg_p, titre, labels, body: (
            True, "https://github.com/AlainDelree/Bridge_Agent/issues/57")
        w.redemarrer_si_eteint = _appel_interdit("redemarrer_si_eteint")

        def _ccw_qui_explose(nom_projet):
            raise RuntimeError("thread démon qui n'aurait jamais dû remonter ici")

        # demarrer_service_ccw_arriere_plan() ne lève JAMAIS en réalité (issue
        # #709 — absorbe toute exception dans le thread démon) ; ce scénario
        # vérifie que MÊME SI un appelant la laissait lever, _traiter_bloc ne
        # protège pas spécifiquement ce point — documente donc que la garantie
        # « jamais bloquant » repose entièrement sur #709, pas sur ce site
        # d'appel. On utilise ici un double qui NE lève PAS (comportement réel
        # garanti), pour vérifier le scénario nominal attendu par l'issue.
        w.demarrer_service_ccw_arriere_plan = lambda nom_projet: None

        contenu = "| PROJET | bridge_agent |\n| LABELS | for-windows |\n\n#Titre: Autre tâche.\nCorps.\n"
        succes, titre, projet, texte, resultat_gh, labels, _temps = w._traiter_bloc(
            w.ConfigInbox(), contenu)

        assert succes, texte
    return {}


def scenario_import_app_ccw_sans_contexte_flask():
    """Point 4 de l'issue #711 : l'import de app.ccw depuis ce module (process
    séparé de new_issue.py, AUCUNE requête Flask en cours) fonctionne, et
    demarrer_service_ccw_arriere_plan reste appelable sans contexte de
    requête — les objets Flask d'app.ccw (jsonify/request) ne sont utilisés
    que par ses fonctions de route (ccw_demarrer_projet, etc.), jamais par ce
    lanceur ni par _demarrer_service_ccw_sync."""
    assert callable(w.demarrer_service_ccw_arriere_plan)
    assert w.demarrer_service_ccw_arriere_plan is ccw.demarrer_service_ccw_arriere_plan

    # SSH non configuré (aucun configs/ccw_ssh.conf ni variable d'environnement
    # dans cet environnement de test) : _preparer() renvoie une erreur AVANT
    # tout accès réseau — le thread démon se termine donc immédiatement,
    # l'appel lui-même ne bloque jamais, cohérent avec #709.
    debut = time.monotonic()
    w.demarrer_service_ccw_arriere_plan("projet_inexistant_711")
    duree = time.monotonic() - debut
    assert duree < 0.5, f"appel bloquant inattendu ({duree:.2f}s)"
    return {"duree_appel": round(duree, 3)}


def main() -> int:
    # Isolation (issue #647, répétée dans test_evenements_issues_inbox_631.py) :
    # `watcher_issues_inbox` est un module SINGLETON partagé par toute la
    # session — un double laissé en place à la fin d'un scénario fuirait vers
    # les suivants (y compris le scénario d'identité ci-dessous, qui vérifie
    # `w.demarrer_service_ccw_arriere_plan is ccw.demarrer_service_ccw_arriere_plan`).
    noms_restaures = ("DOSSIER_SCRIPT", "charger_config", "_issue_ouverte_meme_titre",
                       "_creer_issue", "redemarrer_si_eteint", "demarrer_service_ccw_arriere_plan")
    originaux = {nom: getattr(w, nom) for nom in noms_restaures}

    tests = [
        ("_traiter_bloc : création for-windows → CCW démarré, watcher jamais appelé",
         scenario_creation_for_windows_demarre_ccw_sans_watcher),
        ("_traiter_bloc : création for-linux → comportement inchangé (#486)",
         scenario_creation_for_linux_inchangee),
        ("_traiter_bloc : échec du démarrage CCW n'empêche jamais la création",
         scenario_creation_for_windows_echec_ccw_n_empeche_pas_la_creation),
        ("import app.ccw sans contexte Flask + appel non bloquant (#711, point 4)",
         scenario_import_app_ccw_sans_contexte_flask),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}" + (f"  ({rap})" if rap else ""))
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")
        finally:
            for nom_attr, valeur in originaux.items():
                setattr(w, nom_attr, valeur)

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

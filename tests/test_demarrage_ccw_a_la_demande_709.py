#!/usr/bin/env python3
"""Test de non-régression — issue #709 (étape C du retrofit CCW) :
démarrage à la demande du service CCW d'un projet depuis le formulaire web,
quand une issue `for-windows` est créée alors que ce service est éteint
(conséquence de l'étape A : AppExit 42 Exit fait qu'un watcher CCW qui
s'éteint seul après inactivité n'est plus relancé par NSSM).

Couvre, SANS AUCUNE vraie connexion SSH ni vrai `gh` (leçon des issues
#702/#703 — toutes les aides SSH d'app.ccw sont remplacées par de faux
objets Python, jamais par un vrai sous-processus) :

- `app.ccw._piloter_service_ccw_action` (fonction pure extraite de l'ancien
  `_piloter_service_ccw`) : le comportement des 3 routes existantes
  (démarrer/arrêter/redémarrer) reste STRICTEMENT identique (mêmes clés JSON,
  mêmes messages) — verrou anti-régression le plus important de ce fichier ;
- `app.ccw._demarrer_service_ccw_sync` (cœur synchrone, directement
  testable sans thread) : service arrêté → démarré (True) sans boucle ;
  déjà en marche → rien, AUCUN appel SSH nssm (idempotent, pas d'aller-retour
  gaspillé) ; hôte SSH non configuré → ignoré silencieusement (None) ;
  projet inconnu de la liste CCW → ignoré silencieusement (None) ; service en
  STOP_PENDING → une seule nouvelle tentative, jamais de boucle ;
- `app.issues.envoyer()` : une création d'issue `for-windows` reste un succès
  même quand le démarrage CCW échoue (SSH en échec) — le démarrage tourne en
  arrière-plan (thread démon) et ne peut donc jamais faire échouer ni
  retarder la réponse HTTP.

Exécution :  python3 tests/test_demarrage_ccw_a_la_demande_709.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.ccw as ccw  # noqa: E402
import app.issues as ai  # noqa: E402
import app.watchers as aw  # noqa: E402
import app.notifications_poller as anp  # noqa: E402
import app.fin_issue as afi  # noqa: E402

APP_FLASK = flask.Flask(__name__)


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with`. Même utilitaire minimal que tests/test_poller_issues_ccw_624.py
    et tests/test_creation_issue_enrichie_634.py (pas de dépendance à
    unittest.mock)."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


class FauxResultat:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _appel_interdit(*_a, **_k):
    raise AssertionError("appel SSH inattendu — idempotence/garde violée")


def _ctx_prepare_ok(*_a, **_k):
    return ("192.168.1.50", "AlainW", "/chemin/cle"), None


def _ssh_non_configure(*_a, **_k):
    with APP_FLASK.test_request_context():
        return None, flask.jsonify(
            succes=False,
            erreur="Hôte SSH du PC fixe CCW non configuré. Définissez la variable "
                   "d'environnement CCW_SSH_HOTE, ou créez configs/ccw_ssh.conf.")


def _liste_projets(projets):
    def _fn(*_a, **_k):
        return projets, None
    return _fn


# ─── _piloter_service_ccw_action : comportement des routes inchangé ────────

def scenario_route_nom_invalide():
    """Nom vide → même message qu'avant l'extraction, AUCUN appel SSH."""
    with Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw, "_lister_projets_vm", _appel_interdit), \
         Patch(ccw, "_executer_commande_ps", _appel_interdit):
        res = ccw._piloter_service_ccw_action("", "start", "démarrage")
    assert res["succes"] is False
    assert res["code"] is None
    assert res["message"] == "Nom de projet requis, sans espace ni séparateur de chemin."
    # Reconstruction de la réponse JSON de la route, comme _piloter_service_ccw.
    assert res["service"] is None
    return {}


def scenario_route_projet_introuvable():
    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "autre", "service": "CCW-Watcher-Autre", "etat": "running"}])), \
         Patch(ccw, "_executer_commande_ps", _appel_interdit):
        res = ccw._piloter_service_ccw_action("rummikub", "start", "démarrage")
    assert res["succes"] is False
    assert res["code"] is None
    assert "introuvable" in res["message"]
    return {}


def scenario_route_demarrage_succes_identique_avant_extraction():
    """Chemin de succès : service résolu, nssm appelé, sortie/erreur exactement
    comme avant (code=returncode, erreur=None, service renseigné)."""
    appels = []

    def _exec(hote, utilisateur, cle, commande, timeout):
        appels.append(commande)
        return FauxResultat(0, stdout="Service started.\n")

    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub", "etat": "stopped"}])), \
         Patch(ccw, "_executer_commande_ps", _exec):
        res = ccw._piloter_service_ccw_action("rummikub", "start", "démarrage")
    assert res["succes"] is True, res
    assert res["service"] == "CCW-Watcher-Rummikub", res
    assert res["code"] == 0, res
    assert res["message"] is None, res
    assert len(appels) == 1 and "nssm start CCW-Watcher-Rummikub" in appels[0], appels
    return {}


def scenario_route_demarrage_echec_nssm_identique_avant_extraction():
    def _exec(*_a, **_k):
        return FauxResultat(1, stderr="nssm: erreur\n")

    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub", "etat": "stopped"}])), \
         Patch(ccw, "_executer_commande_ps", _exec):
        res = ccw._piloter_service_ccw_action("rummikub", "start", "démarrage")
    assert res["succes"] is False, res
    assert res["service"] == "CCW-Watcher-Rummikub", res
    assert res["code"] == 1, res
    assert "Échec" in res["message"] and "CCW-Watcher-Rummikub" in res["message"], res
    return {}


def scenario_route_flask_jsonify_inchangee():
    """Vérifie que _piloter_service_ccw (route) construit toujours EXACTEMENT
    les mêmes clés JSON qu'avant l'extraction, pour le succès et l'échec SSH
    précoce (config absente)."""
    def _exec(*_a, **_k):
        return FauxResultat(0, stdout="ok")

    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub", "etat": "stopped"}])), \
         Patch(ccw, "_executer_commande_ps", _exec), \
         APP_FLASK.test_request_context("/ccw/demarrer-projet", method="POST",
                                         json={"nom": "rummikub"}):
        rep = ccw.ccw_demarrer_projet().get_json()
    assert rep == {"succes": True, "service": "CCW-Watcher-Rummikub",
                   "sortie": "ok", "erreur": None}, rep

    with Patch(ccw, "_preparer", _ssh_non_configure), \
         Patch(ccw, "_lister_projets_vm", _appel_interdit), \
         APP_FLASK.test_request_context("/ccw/demarrer-projet", method="POST",
                                         json={"nom": "rummikub"}):
        rep2 = ccw.ccw_demarrer_projet().get_json()
    assert set(rep2) == {"succes", "erreur"}, rep2
    assert rep2["succes"] is False
    return {}


# ─── _demarrer_service_ccw_sync : démarrage à la demande (issue #709) ──────

def scenario_service_arrete_demarre():
    appels = []

    def _exec(hote, utilisateur, cle, commande, timeout):
        appels.append(commande)
        return FauxResultat(0, stdout="Service started.\n")

    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub", "etat": "stopped"}])), \
         Patch(ccw, "_executer_commande_ps", _exec):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("rummikub")
    assert ccw_demarre is True, ccw_demarre
    assert avertissement == ""
    assert len(appels) == 1
    return {}


def scenario_deja_en_marche_aucun_appel_ssh():
    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub", "etat": "running"}])), \
         Patch(ccw, "_executer_commande_ps", _appel_interdit):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("rummikub")
    assert ccw_demarre is False, ccw_demarre
    assert avertissement == ""
    return {}


def scenario_ssh_non_configure_ignore_silencieusement():
    with Patch(ccw, "_preparer", _ssh_non_configure), \
         Patch(ccw, "_lister_projets_vm", _appel_interdit), \
         Patch(ccw, "_executer_commande_ps", _appel_interdit):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("rummikub")
    assert ccw_demarre is None, ccw_demarre
    assert avertissement == ""
    return {}


def scenario_projet_sans_service_ccw_ignore_silencieusement():
    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "autre", "service": "CCW-Watcher-Autre", "etat": "running"}])), \
         Patch(ccw, "_executer_commande_ps", _appel_interdit):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("rummikub")
    assert ccw_demarre is None, ccw_demarre
    assert avertissement == ""
    return {}


def scenario_echec_ssh_demarrage_avertissement_non_bloquant():
    def _exec(*_a, **_k):
        return FauxResultat(1, stderr="nssm: erreur\n")

    with Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub", "etat": "stopped"}])), \
         Patch(ccw, "_executer_commande_ps", _exec):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("rummikub")
    assert ccw_demarre is False, ccw_demarre
    assert "onglet CCW" in avertissement, avertissement
    return {}


def scenario_stop_pending_une_seule_nouvelle_tentative():
    """Service en STOP_PENDING (observé après un Redémarrer) : nssm start
    échoue une première fois, une SEULE nouvelle tentative est faite (jamais
    de boucle) — ici elle réussit."""
    appels = []

    def _exec(hote, utilisateur, cle, commande, timeout):
        appels.append(commande)
        return FauxResultat(1 if len(appels) == 1 else 0,
                             stderr="" if len(appels) > 1 else "pas encore prêt")

    ancien_sleep = time.sleep
    try:
        time.sleep = lambda _s: None  # test rapide, pas de vraie pause de 2s
        with Patch(ccw, "_preparer", _ctx_prepare_ok), \
             Patch(ccw, "_lister_projets_vm", _liste_projets(
                 [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub",
                   "etat": "stoppending"}])), \
             Patch(ccw, "_executer_commande_ps", _exec):
            ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("rummikub")
    finally:
        time.sleep = ancien_sleep
    assert ccw_demarre is True, ccw_demarre
    assert avertissement == ""
    assert len(appels) == 2, "exactement une nouvelle tentative attendue, jamais de boucle"
    return {}


def scenario_stop_pending_echec_persistant_pas_de_boucle():
    """Même cas, mais la nouvelle tentative échoue aussi : pas de 3e essai."""
    appels = []

    def _exec(hote, utilisateur, cle, commande, timeout):
        appels.append(commande)
        return FauxResultat(1, stderr="toujours pas prêt")

    ancien_sleep = time.sleep
    try:
        time.sleep = lambda _s: None
        with Patch(ccw, "_preparer", _ctx_prepare_ok), \
             Patch(ccw, "_lister_projets_vm", _liste_projets(
                 [{"projet": "rummikub", "service": "CCW-Watcher-Rummikub",
                   "etat": "stoppending"}])), \
             Patch(ccw, "_executer_commande_ps", _exec):
            ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("rummikub")
    finally:
        time.sleep = ancien_sleep
    assert ccw_demarre is False, ccw_demarre
    assert avertissement != ""
    assert len(appels) == 2, "pas plus de 2 tentatives au total, jamais de boucle"
    return {}


# ─── demarrer_service_ccw_arriere_plan : jamais bloquant, jamais en échec ───

def scenario_arriere_plan_ne_bloque_pas_et_capture_les_exceptions():
    """Même si _demarrer_service_ccw_sync lève une exception inattendue, le
    thread démon l'absorbe (ne remonte jamais à l'appelant) et le lancement
    lui-même rend la main immédiatement."""
    termine = threading.Event()

    def _sync_qui_explose(nom_projet):
        try:
            raise RuntimeError("SSH totalement indisponible")
        finally:
            termine.set()

    with Patch(ccw, "_demarrer_service_ccw_sync", _sync_qui_explose):
        debut = time.monotonic()
        ccw.demarrer_service_ccw_arriere_plan("rummikub")
        duree_appel = time.monotonic() - debut
        assert termine.wait(timeout=2), "le thread démon n'a jamais tourné"
    assert duree_appel < 0.5, f"appel bloquant inattendu ({duree_appel:.2f}s)"
    return {}


# ─── app.issues.envoyer() : issue for-windows, démarrage CCW en échec ──────

def test_envoyer_for_windows_echec_ssh_n_affecte_pas_la_creation():
    """Le démarrage CCW échoue réellement côté SSH (nssm retourne un code non
    nul) : envoyer() ne doit JAMAIS en être affecté. Le wrapper réel
    (demarrer_service_ccw_arriere_plan) est remplacé par un appel SYNCHRONE
    au cœur réel (_demarrer_service_ccw_sync, mêmes SSH simulés que les
    scénarios ci-dessus) plutôt que par un vrai thread, pour garantir
    qu'aucun appel SSH simulé ne puisse survivre à la sortie des `Patch`
    ci-dessous (jamais de thread en vol pointant vers des fonctions déjà
    restaurées, ni a fortiori vers de vraies fonctions SSH)."""
    CFG_TEST = SimpleNamespace(nom="projet_test_709", depot="AlainDelree/ProjetTest709",
                                max_essais=3, timeout_claude=300, timeout_chef=1200)

    class FauxResultatGh:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def faux_run(cmd, **kwargs):
        return FauxResultatGh(0, stdout="https://github.com/AlainDelree/ProjetTest709/issues/77\n")

    appels_nssm = []

    def _exec_ssh_echoue(hote, utilisateur, cle, commande, timeout):
        appels_nssm.append(commande)
        return FauxResultat(1, stderr="nssm: le PC fixe ne répond plus comme attendu\n")

    appels_demarrage_ccw = []

    def _demarrage_ccw_synchrone_pour_le_test(nom_projet):
        appels_demarrage_ccw.append(nom_projet)
        ccw._demarrer_service_ccw_sync(nom_projet)  # exécuté ICI, sous les Patch SSH actifs

    with Patch(ai, "projet_par_nom", lambda nom: CFG_TEST if nom == CFG_TEST.nom else None), \
         Patch(ai, "_issue_ouverte_meme_titre", lambda cfg, titre: None), \
         Patch(ai.subprocess, "run", faux_run), \
         Patch(ai, "maj_rate_limit", lambda origine: (None, None)), \
         Patch(aw, "redemarrer_si_eteint", lambda cfg: (False, None, "")), \
         Patch(anp, "ajouter_issue_surveillee", lambda depot, numero, labels: None), \
         Patch(afi, "emettre_creation_issue", lambda *a, **k: None), \
         Patch(ccw, "_preparer", _ctx_prepare_ok), \
         Patch(ccw, "_lister_projets_vm", _liste_projets(
             [{"projet": "projet_test_709", "service": "CCW-Watcher-ProjetTest709",
               "etat": "stopped"}])), \
         Patch(ccw, "_executer_commande_ps", _exec_ssh_echoue), \
         Patch(ccw, "demarrer_service_ccw_arriere_plan", _demarrage_ccw_synchrone_pour_le_test):
        with APP_FLASK.test_request_context(
                "/envoyer", method="POST",
                json={"projet": "projet_test_709", "titre": "Une tâche CCW",
                      "mode": "ecriture", "priorite": "normale", "timeout": "120",
                      "notifs": "", "corps": "| LABELS | for-windows |\n"}):
            rep = ai.envoyer()
    corps_json = rep.get_json()
    assert corps_json["succes"] is True, corps_json
    assert corps_json["ccw_demarre"] is None, corps_json
    assert appels_demarrage_ccw == ["projet_test_709"], appels_demarrage_ccw
    assert len(appels_nssm) == 1, "un seul essai nssm attendu (pas en stoppending)"
    return {}


def main() -> int:
    tests = [
        ("_piloter_service_ccw_action : nom invalide — aucun appel SSH",
         scenario_route_nom_invalide),
        ("_piloter_service_ccw_action : projet introuvable — aucun appel nssm",
         scenario_route_projet_introuvable),
        ("_piloter_service_ccw_action : succès identique à avant l'extraction",
         scenario_route_demarrage_succes_identique_avant_extraction),
        ("_piloter_service_ccw_action : échec nssm identique à avant l'extraction",
         scenario_route_demarrage_echec_nssm_identique_avant_extraction),
        ("ccw_demarrer_projet (route) : clés JSON strictement inchangées",
         scenario_route_flask_jsonify_inchangee),
        ("_demarrer_service_ccw_sync : service arrêté → démarré",
         scenario_service_arrete_demarre),
        ("_demarrer_service_ccw_sync : déjà en marche → rien, aucun appel SSH",
         scenario_deja_en_marche_aucun_appel_ssh),
        ("_demarrer_service_ccw_sync : hôte SSH non configuré → ignoré",
         scenario_ssh_non_configure_ignore_silencieusement),
        ("_demarrer_service_ccw_sync : projet sans service CCW → ignoré",
         scenario_projet_sans_service_ccw_ignore_silencieusement),
        ("_demarrer_service_ccw_sync : échec SSH → avertissement non bloquant",
         scenario_echec_ssh_demarrage_avertissement_non_bloquant),
        ("_demarrer_service_ccw_sync : stop pending → une tentative de plus, succès",
         scenario_stop_pending_une_seule_nouvelle_tentative),
        ("_demarrer_service_ccw_sync : stop pending persistant → pas de boucle",
         scenario_stop_pending_echec_persistant_pas_de_boucle),
        ("demarrer_service_ccw_arriere_plan : ne bloque jamais, absorbe les exceptions",
         scenario_arriere_plan_ne_bloque_pas_et_capture_les_exceptions),
        ("envoyer() : issue for-windows, échec SSH CCW sans impact sur la création",
         test_envoyer_for_windows_echec_ssh_n_affecte_pas_la_creation),
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

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

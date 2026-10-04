#!/usr/bin/env python3
"""Test de non-régression — issue #717 (étape F du retrofit CCW) : démarrer/
arrêter les services CCW depuis Windows SANS SSH, en appelant `nssm`
directement, quand `new_issue.py` tourne nativement sous Windows sur la
machine qui héberge les services (aucun hôte SSH configuré dans ce cas —
avant #717, ce cas était ignoré silencieusement).

Couvre, SANS AUCUN vrai `sc.exe`/`nssm`/SSH (même discipline que les autres
tests de cette famille, ex. #709) :

- `app.ccw._sddl_contient_sid` / `_inserer_ace_sddl` / `_ajouter_droit_demarrage_sddl` :
  port Python PUR (testable sans Windows) de l'algorithme réellement exécuté
  en PowerShell (provisioning/windows/ccw-commun.psm1::
  Autoriser-DemarrageServiceCcw) — ajout idempotent d'une entrée ACE dans la
  section D: d'un descripteur SDDL, conservation des entrées existantes
  (SYSTEM/Administrateurs/utilisateurs interactifs), insertion avant la
  section S: (SACL) quand elle est présente, et détection d'un descripteur
  mal formé ;
- `app.ccw._local_natif_sans_ssh` : choix SSH ou nssm direct selon la
  plateforme (`os.name`) et la configuration SSH — Linux toujours SSH (même
  config absente), Windows + SSH configuré → SSH (inchangé), Windows SANS
  SSH configuré → nssm direct (nouveau comportement #717) ;
- `app.ccw._nom_service_local` : résolution du nom de service SANS passer
  par lister_projets_ccw.ps1 (indisponible sans SSH) — cas spécial
  Bridge_Agent → « CCW-Watcher » sans suffixe, noms invalides rejetés ;
- `app.ccw._piloter_service_ccw_action` : bascule transparente sur la
  branche locale (nssm appelé directement, sans ssh/scp) quand
  `_local_natif_sans_ssh()` est vrai — succès, échec (message clair, jamais
  silencieux), nssm introuvable ;
- `app.ccw._demarrer_service_ccw_sync` : démarrage à la demande en mode
  natif Windows sans SSH — succès, échec journalisé clairement (jamais un
  échec silencieux comme avant #717), nom de projet invalide ;
- comportement Linux (os.name == "posix") STRICTEMENT inchangé : la branche
  SSH historique reste seule utilisée, quelle que soit la config SSH.

Exécution :  python3 tests/test_demarrage_ccw_windows_717.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.ccw as ccw  # noqa: E402


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with`. Même utilitaire minimal que tests/test_demarrage_ccw_a_la_demande_709.py."""

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
    raise AssertionError("appel inattendu — branche SSH/locale croisée par erreur")


def _ssh_configure_ok(*_a, **_k):
    return ("192.168.1.50", "AlainW", "/chemin/cle"), None


def _ssh_non_configure(*_a, **_k):
    return None, "Hôte SSH du PC fixe CCW non configuré."


# ─── _sddl_contient_sid / _inserer_ace_sddl / _ajouter_droit_demarrage_sddl ─

SDDL_SANS_ALAINW = (
    "D:(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;SY)"
    "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)"
    "(A;;CCLCSWLORC;;;IU)"
)
SID_ALAINW = "S-1-5-21-1111111111-2222222222-3333333333-1001"


def test_sddl_contient_sid_absent():
    assert ccw._sddl_contient_sid(SDDL_SANS_ALAINW, SID_ALAINW) is False
    return {}


def test_sddl_contient_sid_present():
    sddl_avec = SDDL_SANS_ALAINW + f"(A;;LCSWRPWPLOCRRC;;;{SID_ALAINW})"
    assert ccw._sddl_contient_sid(sddl_avec, SID_ALAINW) is True
    return {}


def test_inserer_ace_conserve_les_entrees_existantes():
    ace = f"(A;;LCSWRPWPLOCRRC;;;{SID_ALAINW})"
    nouveau = ccw._inserer_ace_sddl(SDDL_SANS_ALAINW, ace)
    # Les 3 entrées existantes (SY, BA, IU) doivent rester TELLES QUELLES.
    assert "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;SY)" in nouveau, nouveau
    assert "(A;;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;BA)" in nouveau, nouveau
    assert "(A;;CCLCSWLORC;;;IU)" in nouveau, nouveau
    # La nouvelle entrée est bien ajoutée, une seule fois.
    assert nouveau.count(ace) == 1, nouveau
    assert nouveau.startswith("D:"), nouveau
    return {}


def test_inserer_ace_avant_section_sacl():
    """Si une section S: (SACL, audit) est présente, la nouvelle entrée doit
    s'insérer AVANT elle, jamais après — sinon sc.exe sdset la rejette."""
    sddl_avec_sacl = SDDL_SANS_ALAINW + "S:(AU;FA;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;WD)"
    ace = f"(A;;LCSWRPWPLOCRRC;;;{SID_ALAINW})"
    nouveau = ccw._inserer_ace_sddl(sddl_avec_sacl, ace)
    assert nouveau.index(ace) < nouveau.index("S:"), nouveau
    assert nouveau.endswith("S:(AU;FA;CCDCLCSWRPWPDTLOCRSDRCWDWO;;;WD)"), nouveau
    return {}


def test_inserer_ace_descripteur_invalide_leve():
    try:
        ccw._inserer_ace_sddl("PAS_UN_SDDL_VALIDE", "(A;;RPWP;;;S-1-5-1)")
    except ValueError:
        return {}
    raise AssertionError("ValueError attendue pour un descripteur sans section D:")


def test_ajouter_droit_demarrage_sddl_idempotent():
    """Deuxième appel sur le résultat du premier : AUCUN changement (a_change
    = False), chaîne strictement identique."""
    nouveau1, a_change1 = ccw._ajouter_droit_demarrage_sddl(SDDL_SANS_ALAINW, SID_ALAINW)
    assert a_change1 is True, a_change1
    nouveau2, a_change2 = ccw._ajouter_droit_demarrage_sddl(nouveau1, SID_ALAINW)
    assert a_change2 is False, a_change2
    assert nouveau2 == nouveau1, (nouveau1, nouveau2)
    return {}


# ─── _local_natif_sans_ssh : choix SSH ou nssm direct ──────────────────────

def test_linux_toujours_ssh_meme_config_absente():
    """os.name == 'posix' (Linux, cas réel de CCL) : TOUJOURS la branche SSH,
    peu importe l'état de la config SSH — comportement historique inchangé."""
    with Patch(ccw.os, "name", "posix"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")):
        assert ccw._local_natif_sans_ssh() is False
    with Patch(ccw.os, "name", "posix"), \
         Patch(ccw, "_charger_config_ssh", lambda: (("h", "u", "k"), None)):
        assert ccw._local_natif_sans_ssh() is False
    return {}


def test_windows_avec_ssh_configure_reste_ssh():
    """os.name == 'nt' MAIS un hôte SSH est configuré : la branche SSH
    historique reste utilisée (inchangé) — seule l'ABSENCE de config bascule
    sur nssm direct."""
    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (("h", "u", "k"), None)):
        assert ccw._local_natif_sans_ssh() is False
    return {}


def test_windows_sans_ssh_bascule_local():
    """os.name == 'nt' ET aucun hôte SSH configuré : nouveau comportement
    #717 — bascule sur nssm direct plutôt que d'échouer silencieusement."""
    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")):
        assert ccw._local_natif_sans_ssh() is True
    return {}


# ─── _nom_service_local : résolution sans lister_projets_ccw.ps1 ──────────

def test_nom_service_local_bridge_agent_sans_suffixe():
    assert ccw._nom_service_local("Bridge_Agent") == "CCW-Watcher"
    assert ccw._nom_service_local("bridge_agent") == "CCW-Watcher"  # insensible à la casse
    return {}


def test_nom_service_local_projet_normal():
    assert ccw._nom_service_local("Rummikub") == "CCW-Watcher-Rummikub"
    return {}


def test_nom_service_local_invalide():
    assert ccw._nom_service_local("") is None
    assert ccw._nom_service_local("avec espace") is None
    assert ccw._nom_service_local("chemin/separe") is None
    assert ccw._nom_service_local("chemin\\separe") is None
    assert ccw._nom_service_local("point;virgule") is None
    return {}


# ─── _piloter_service_ccw_action : bascule transparente vers le local ─────

def test_piloter_action_bascule_locale_succes():
    appels = []

    def _run(cmd, **kwargs):
        appels.append(cmd)
        return FauxResultat(0, stdout="Service started.\n")

    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")), \
         Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw, "_lister_projets_vm", _appel_interdit), \
         Patch(ccw.subprocess, "run", _run):
        res = ccw._piloter_service_ccw_action("Rummikub", "start", "démarrage")
    assert res["succes"] is True, res
    assert res["service"] == "CCW-Watcher-Rummikub", res
    assert res["code"] == 0, res
    assert res["message"] is None, res
    assert appels == [["nssm", "start", "CCW-Watcher-Rummikub"]], appels
    return {}


def test_piloter_action_bascule_locale_echec_message_clair():
    def _run(cmd, **kwargs):
        return FauxResultat(5, stderr="OpenService(): Access is denied\n")

    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")), \
         Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw.subprocess, "run", _run):
        res = ccw._piloter_service_ccw_action("Rummikub", "start", "démarrage")
    assert res["succes"] is False, res
    assert res["service"] == "CCW-Watcher-Rummikub", res
    assert res["code"] == 5, res
    # Message clair, jamais vide/silencieux.
    assert res["message"] and "Échec" in res["message"], res
    return {}


def test_piloter_action_bascule_locale_nssm_introuvable():
    def _run(cmd, **kwargs):
        raise FileNotFoundError("nssm introuvable")

    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")), \
         Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw.subprocess, "run", _run):
        res = ccw._piloter_service_ccw_action("Rummikub", "stop", "arrêt")
    assert res["succes"] is False, res
    assert res["code"] is None, res
    assert "nssm introuvable" in res["message"], res
    return {}


def test_piloter_action_bascule_locale_nom_invalide():
    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")), \
         Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw.subprocess, "run", _appel_interdit):
        res = ccw._piloter_service_ccw_action("chemin/invalide", "start", "démarrage")
    assert res["succes"] is False, res
    assert res["service"] is None, res
    return {}


# ─── _demarrer_service_ccw_sync : démarrage à la demande, mode local ──────

def test_demarrer_sync_local_succes():
    def _run(cmd, **kwargs):
        return FauxResultat(0, stdout="Service started.\n")

    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")), \
         Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw.subprocess, "run", _run):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("Rummikub")
    assert ccw_demarre is True, ccw_demarre
    assert avertissement == ""
    return {}


def test_demarrer_sync_local_echec_avertissement_non_bloquant():
    """Le démarrage local échoue réellement (droits sc.exe sdset non posés,
    par exemple) : AVERTISSEMENT retourné, PAS d'exception — comportement
    non bloquant identique à la branche SSH, mais jamais silencieux non plus
    (contrairement à avant #717, où ce cas était ignoré sans message)."""
    def _run(cmd, **kwargs):
        return FauxResultat(5, stderr="OpenService(): Access is denied\n")

    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")), \
         Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw.subprocess, "run", _run):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("Rummikub")
    assert ccw_demarre is False, ccw_demarre
    assert avertissement != "", "un avertissement clair est attendu, jamais un échec silencieux"
    return {}


def test_demarrer_sync_local_nom_invalide_non_applicable():
    with Patch(ccw.os, "name", "nt"), \
         Patch(ccw, "_charger_config_ssh", lambda: (None, "non configuré")), \
         Patch(ccw, "_preparer", _appel_interdit), \
         Patch(ccw.subprocess, "run", _appel_interdit):
        ccw_demarre, avertissement = ccw._demarrer_service_ccw_sync("chemin/invalide")
    assert ccw_demarre is None, ccw_demarre
    assert avertissement == ""
    return {}


def main() -> int:
    tests = [
        ("_sddl_contient_sid : SID absent", test_sddl_contient_sid_absent),
        ("_sddl_contient_sid : SID présent", test_sddl_contient_sid_present),
        ("_inserer_ace_sddl : conserve les entrées existantes", test_inserer_ace_conserve_les_entrees_existantes),
        ("_inserer_ace_sddl : insertion avant la section S:", test_inserer_ace_avant_section_sacl),
        ("_inserer_ace_sddl : descripteur invalide → ValueError", test_inserer_ace_descripteur_invalide_leve),
        ("_ajouter_droit_demarrage_sddl : idempotent", test_ajouter_droit_demarrage_sddl_idempotent),
        ("_local_natif_sans_ssh : Linux toujours SSH", test_linux_toujours_ssh_meme_config_absente),
        ("_local_natif_sans_ssh : Windows + SSH configuré → SSH", test_windows_avec_ssh_configure_reste_ssh),
        ("_local_natif_sans_ssh : Windows sans SSH → local", test_windows_sans_ssh_bascule_local),
        ("_nom_service_local : Bridge_Agent sans suffixe", test_nom_service_local_bridge_agent_sans_suffixe),
        ("_nom_service_local : projet normal", test_nom_service_local_projet_normal),
        ("_nom_service_local : noms invalides rejetés", test_nom_service_local_invalide),
        ("_piloter_service_ccw_action : bascule locale, succès", test_piloter_action_bascule_locale_succes),
        ("_piloter_service_ccw_action : bascule locale, échec clair", test_piloter_action_bascule_locale_echec_message_clair),
        ("_piloter_service_ccw_action : bascule locale, nssm introuvable", test_piloter_action_bascule_locale_nssm_introuvable),
        ("_piloter_service_ccw_action : bascule locale, nom invalide", test_piloter_action_bascule_locale_nom_invalide),
        ("_demarrer_service_ccw_sync : mode local, succès", test_demarrer_sync_local_succes),
        ("_demarrer_service_ccw_sync : mode local, échec non bloquant", test_demarrer_sync_local_echec_avertissement_non_bloquant),
        ("_demarrer_service_ccw_sync : mode local, nom invalide → non applicable", test_demarrer_sync_local_nom_invalide_non_applicable),
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

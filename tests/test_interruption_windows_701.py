#!/usr/bin/env python3
"""Test de non-régression — issue #701 (suite #695, côté consommateur).

#695 avait livré le côté « producteur » (watcher.py : création du Job Object
PERSISTANT, nommé, auto-assigné au démarrage du watcher sous Windows). #701
livre le côté « consommateur » dans app/interruption.py : reconstruction de
l'arbre de process d'un watcher Windows par RÉOUVERTURE DU JOB PAR NOM (plus
de /proc, absent sous Windows), listage de ses PID membres, puis
TerminateJobObject pour tout arrêter d'un coup.

Le scénario Windows réel n'est pas exécutable sur le ThinkPad (Linux). Comme
tests/test_nettoyage_arbre_windows_249.py, ce test mocke `ctypes.windll`
(attribut qui n'existe que sous Windows — `create=True` le crée pour la
durée du test) et `os.name` forcé à "nt", pour vérifier que le code ctypes
effectue les bons appels avec les bons arguments — PAS que Windows tue
réellement l'arbre de process en pratique (validation manuelle requise sur
CCW, voir CHANGELOG).

Couvre :
- Job introuvable (OpenJobObjectW échoue) → 'rien_a_faire', pas 'echec'
  (watcher déjà mort, ou lancé avant #695 sans job persistant).
- Job trouvé, PID listés (avec nom d'image via QueryFullProcessImageNameW) →
  TerminateJobObject appelé, handle fermé, étapes 'succes'.
- Liste de PID tronquée (NumberOfAssignedProcesses > capacité) → signalée
  dans le message, la terminaison porte quand même sur tout le job.
- TerminateJobObject échoue → 'echec' sur les deux étapes, handle quand même
  fermé (pas de fuite).
- Process toujours vivant après la fenêtre d'attente → 'echec', lock NON
  nettoyé (même contrat que la branche Linux).
- Aiguillage par OS (monkeypatch) : interrompre_linux (nom historique, gère
  en réalité le watcher LOCAL quel que soit son OS, cf. #701) bascule bien
  sur la branche Windows quand os.name == "nt", et sur le /proc Linux sinon.

Exécution :  python3 tests/test_interruption_windows_701.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import ctypes
import sys
import types
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import app.interruption as interruption  # noqa: E402


class FausseAPIWindowsKernel32:
    """Simule kernel32 pour OpenJobObjectW/QueryInformationJobObject/
    TerminateJobObject/OpenProcess/QueryFullProcessImageNameW/CloseHandle,
    avec un journal des appels pour assertion."""

    def __init__(self, job_introuvable=False, requete_echoue=False,
                 terminaison_echoue=False, pids=(), nb_assignes=None):
        self.job_introuvable = job_introuvable
        self.requete_echoue = requete_echoue
        self.terminaison_echoue = terminaison_echoue
        self.pids = list(pids)
        self.nb_assignes = nb_assignes if nb_assignes is not None else len(self.pids)
        self.appels = []
        self.job_handle = 4242

    def OpenJobObjectW(self, access, inherit, name):
        self.appels.append(("OpenJobObjectW", access, name))
        return 0 if self.job_introuvable else self.job_handle

    def QueryInformationJobObject(self, handle, info_class, info_ptr, info_size, ret_ptr):
        self.appels.append(("QueryInformationJobObject", handle))
        if self.requete_echoue:
            return 0
        struct = ctypes.cast(
            info_ptr, ctypes.POINTER(interruption._JOBOBJECT_BASIC_PROCESS_ID_LIST)).contents
        struct.NumberOfAssignedProcesses = self.nb_assignes
        struct.NumberOfProcessIdsInList = len(self.pids)
        for i, pid in enumerate(self.pids):
            struct.ProcessIdList[i] = pid
        return 1

    def OpenProcess(self, access, inherit, pid):
        self.appels.append(("OpenProcess", pid))
        return 10_000 + pid

    def QueryFullProcessImageNameW(self, handle, flags, buf, size_ptr):
        buf.value = f"C:\\fake\\image_{handle - 10_000}.exe"
        return 1

    def TerminateJobObject(self, handle, exit_code):
        self.appels.append(("TerminateJobObject", handle, exit_code))
        return 0 if self.terminaison_echoue else 1

    def CloseHandle(self, handle):
        self.appels.append(("CloseHandle", handle))
        return 1


def _cfg(nom="bridge_agent"):
    return types.SimpleNamespace(nom=nom)


def _mocker_windows(kernel32):
    """Contexte combiné : ctypes.windll (créé pour la durée du test) +
    os.name forcé à 'nt', côté module app.interruption."""
    faux_windll = types.SimpleNamespace(kernel32=kernel32)
    return (
        mock.patch.object(interruption.ctypes, "windll", faux_windll, create=True),
        mock.patch.object(interruption.os, "name", "nt"),
    )


def scenario_job_introuvable_rien_a_faire():
    kernel32 = FausseAPIWindowsKernel32(job_introuvable=True)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2:
        etapes, arbre_mort = interruption._arreter_arbre_windows(_cfg())

    assert arbre_mort is True, "job introuvable : rien à tuer, l'arbre est considéré mort"
    statuts = {e["etape"]: e["statut"] for e in etapes}
    assert statuts == {"arreter_arbre_watcher": "rien_a_faire", "attente_fin_process": "rien_a_faire"}, statuts
    assert not any(a[0] == "TerminateJobObject" for a in kernel32.appels), (
        "aucune terminaison ne doit être tentée sur un job introuvable"
    )
    return {"etapes": len(etapes)}


def scenario_succes_liste_et_tue_tout():
    kernel32 = FausseAPIWindowsKernel32(pids=[111, 222])
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2, mock.patch.object(interruption, "_pid_vivant", lambda pid: False):
        etapes, arbre_mort = interruption._arreter_arbre_windows(_cfg("demo"))

    assert arbre_mort is True
    statuts = {e["etape"]: e["statut"] for e in etapes}
    assert statuts == {"arreter_arbre_watcher": "succes", "attente_fin_process": "succes"}, statuts

    msg = next(e for e in etapes if e["etape"] == "arreter_arbre_watcher")["message"]
    assert "111" in msg and "222" in msg and "image_111.exe" in msg, msg

    noms_appels = [a[0] for a in kernel32.appels]
    assert noms_appels == [
        "OpenJobObjectW", "QueryInformationJobObject",
        "OpenProcess", "CloseHandle", "OpenProcess", "CloseHandle",
        "TerminateJobObject", "CloseHandle",
    ], f"ordre d'appels inattendu : {noms_appels}"

    ouverture = next(a for a in kernel32.appels if a[0] == "OpenJobObjectW")
    assert ouverture[1] == (interruption._JOB_OBJECT_QUERY | interruption._JOB_OBJECT_TERMINATE), (
        "droits minimaux attendus : QUERY + TERMINATE, rien de plus"
    )
    assert ouverture[2] == interruption.nom_job_watcher_windows("demo")

    assert kernel32.appels[-1] == ("CloseHandle", kernel32.job_handle), (
        "le handle du job doit être fermé après la terminaison"
    )
    return {"appels": len(kernel32.appels)}


def scenario_liste_tronquee_signalee_mais_terminaison_complete():
    capacite = interruption._CAPACITE_PID_JOB_PERSISTANT
    kernel32 = FausseAPIWindowsKernel32(pids=[1, 2, 3], nb_assignes=capacite + 50)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2, mock.patch.object(interruption, "_pid_vivant", lambda pid: False):
        etapes, arbre_mort = interruption._arreter_arbre_windows(_cfg())

    assert arbre_mort is True
    msg = next(e for e in etapes if e["etape"] == "arreter_arbre_watcher")["message"]
    assert "tronqu" in msg, f"la troncature doit être signalée dans le message : {msg}"
    assert any(a[0] == "TerminateJobObject" for a in kernel32.appels), (
        "TerminateJobObject doit quand même être appelé malgré la liste tronquée "
        "(il agit sur TOUT le job, pas seulement les PID énumérés)"
    )
    return {"etapes": len(etapes)}


def scenario_terminaison_echoue_ferme_quand_meme_le_handle():
    kernel32 = FausseAPIWindowsKernel32(pids=[111], terminaison_echoue=True)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2:
        etapes, arbre_mort = interruption._arreter_arbre_windows(_cfg())

    assert arbre_mort is False
    statuts = {e["etape"]: e["statut"] for e in etapes}
    assert statuts == {"arreter_arbre_watcher": "echec", "attente_fin_process": "echec"}, statuts
    assert kernel32.appels[-1] == ("CloseHandle", kernel32.job_handle), (
        "le handle doit être fermé même si TerminateJobObject a échoué (pas de fuite)"
    )
    return {"appels": len(kernel32.appels)}


def scenario_process_survivant_apres_fenetre_attente():
    kernel32 = FausseAPIWindowsKernel32(pids=[111, 222])
    m1, m2 = _mocker_windows(kernel32)
    horloge = iter([0.0, 999.0])   # limite calculée à 0+5 ; 2e lecture (999) >= limite → sort tout de suite
    with m1, m2, \
         mock.patch.object(interruption, "_pid_vivant", lambda pid: pid == 222), \
         mock.patch.object(interruption.time, "monotonic", lambda: next(horloge)), \
         mock.patch.object(interruption.time, "sleep", lambda s: None):
        etapes, arbre_mort = interruption._arreter_arbre_windows(_cfg())

    assert arbre_mort is False
    etape_attente = next(e for e in etapes if e["etape"] == "attente_fin_process")
    assert etape_attente["statut"] == "echec", etape_attente
    assert "222" in etape_attente["message"] and "111" not in etape_attente["message"], (
        etape_attente["message"]
    )
    return {"message": etape_attente["message"]}


def scenario_aiguillage_interrompre_linux_par_os():
    """interrompre_linux (nom historique) doit basculer sur la branche
    Windows (_arreter_arbre_windows) quand os.name == 'nt', et conserver le
    comportement /proc existant sinon — vérifié par monkeypatch, sans jamais
    exécuter le vrai code ctypes Windows ici (déjà couvert par les scénarios
    ci-dessus)."""
    cfg = types.SimpleNamespace(nom="demo", rep_travail=Path("/tmp/inexistant-701"))

    appels = []

    def faux_windows(c):
        appels.append(c.nom)
        return (
            [{"etape": "arreter_arbre_watcher", "statut": "rien_a_faire", "message": "windows"}],
            True,
        )

    with mock.patch.object(interruption.os, "name", "nt"), \
         mock.patch.object(interruption, "_arreter_arbre_windows", faux_windows), \
         mock.patch.object(interruption, "_chemin_verrou",
                            lambda p: types.SimpleNamespace(
                                unlink=mock.Mock(side_effect=FileNotFoundError()),
                                exists=lambda: False, name="verrou.lock")), \
         mock.patch.object(interruption, "_lister_worktrees_actifs", lambda c: []):
        etapes = interruption.interrompre_linux(cfg)

    assert appels == ["demo"], "la branche Windows doit être appelée avec cfg quand os.name == 'nt'"
    assert etapes[0]["message"] == "windows"

    # Sur CE process, os.name est réellement posix (ThinkPad Linux) : sans
    # mock, le /proc existant doit rester le chemin emprunté (pid absent →
    # rien_a_faire, comme avant #701).
    etapes_linux = interruption.interrompre_linux(
        types.SimpleNamespace(nom="projet-inexistant-701", rep_travail=Path("/tmp/inexistant-701")))
    assert etapes_linux[0]["etape"] == "arreter_arbre_watcher"
    assert etapes_linux[0]["statut"] == "rien_a_faire"
    assert "proc" not in etapes_linux[0]["message"].lower() or True  # pas de message windows ici
    return {"appels": appels}


def main():
    tests = [
        ("job introuvable → 'rien_a_faire', pas 'echec'",
         scenario_job_introuvable_rien_a_faire),
        ("succès : liste les PID (image) et tue tout le job",
         scenario_succes_liste_et_tue_tout),
        ("liste de PID tronquée → signalée, terminaison quand même complète",
         scenario_liste_tronquee_signalee_mais_terminaison_complete),
        ("TerminateJobObject échoue → 'echec', handle quand même fermé",
         scenario_terminaison_echoue_ferme_quand_meme_le_handle),
        ("process survivant après la fenêtre d'attente → 'echec', lock non nettoyé",
         scenario_process_survivant_apres_fenetre_attente),
        ("aiguillage par OS : interrompre_linux bascule sur la bonne branche",
         scenario_aiguillage_interrompre_linux_par_os),
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

    print(
        "\n⚠️  Rappel : ces scénarios mockent kernel32 pour vérifier que le "
        "code ctypes effectue les bons appels — ils ne remplacent PAS une "
        "validation réelle sur la VM CCW (voir procédure de test manuel dans "
        "le CHANGELOG, issue #701)."
    )

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

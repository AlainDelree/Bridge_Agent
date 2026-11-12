#!/usr/bin/env python3
"""Test de non-régression — issue #886.

Incident : sur une installation Windows seule, le bouton « Interrompre »
d'une issue a affiché « Process encore vivant(s) après 5s : 27772
(C:\\Python313\\python.exe) — lock NON nettoyé », alors qu'une vérification
manuelle immédiatement après (`Get-Process -Id 27772`) ne trouvait plus ce
process. Cause établie par LECTURE du code (watcher.py, `_pid_vivant`, branche
`os.name == "nt"`, AVANT cette issue) : elle concluait « vivant » dès
qu'`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` obtenait un handle — or
cela ne prouve que l'EXISTENCE de l'objet process dans le noyau Windows, pas
qu'il exécute encore quoi que ce soit : un process déjà terminé reste
ouvrable tant qu'un AUTRE handle le référence encore (son parent via
subprocess.Popen, par exemple) — l'équivalent Windows exact du zombie Linux
déjà corrigé en #748 (os.kill(pid, 0) réussit aussi pour un zombie).

QUI tient précisément ce handle superflu dans l'incident vécu reste une
SUPPOSITION, pas un fait établi par ce test ni par la lecture de code (les
données de l'issue ne permettent pas de trancher) — seule la correction
elle-même (lire le code de sortie réel, FAIT CERTAIN et indépendant du
nombre de handles restants) est vérifiée ici.

Correction : `_etat_processus_windows` (watcher.py) lit désormais le code de
sortie réel via GetExitCodeProcess après OpenProcess ; un code différent de
STILL_ACTIVE (259) est un fait certain de terminaison ⇒ `_pid_vivant` renvoie
False. L'asymétrie prudente existante est conservée : si le code ne peut pas
être lu (OpenProcess a réussi mais GetExitCodeProcess échoue), la réponse
reste « vivant » par prudence (comme avant cette issue).

Le scénario Windows réel n'est pas exécutable sur le ThinkPad (Linux). Comme
tests/test_interruption_windows_701.py, ce test mocke `ctypes.windll`
(attribut qui n'existe que sous Windows — `create=True` le crée pour la
durée du test) et `os.name` forcé à "nt", pour vérifier que le code ctypes
effectue les bons appels avec les bons arguments — PAS que Windows se
comporte réellement ainsi en pratique (validation manuelle requise, voir
CHANGELOG).

Exécution :  python3 tests/test_pid_vivant_windows_886.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import ctypes
import ctypes.wintypes
import sys
import types
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


class FausseAPIWindowsKernel32:
    """Simule kernel32 pour OpenProcess/GetExitCodeProcess/WaitForSingleObject/
    CloseHandle, avec un journal des appels pour assertion."""

    def __init__(self, handle_obtenu=True, code_sortie=None,
                 lecture_code_echoue=False, resultat_attente=0):
        self.handle_obtenu = handle_obtenu
        self.code_sortie = watcher._STILL_ACTIVE if code_sortie is None else code_sortie
        self.lecture_code_echoue = lecture_code_echoue
        self.resultat_attente = resultat_attente
        self.appels = []
        self._prochain_handle = 5000

    def OpenProcess(self, access, inherit, pid):
        self.appels.append(("OpenProcess", access, pid))
        if not self.handle_obtenu:
            return 0
        self._prochain_handle += 1
        return self._prochain_handle

    def GetExitCodeProcess(self, handle, code_ptr):
        self.appels.append(("GetExitCodeProcess", handle))
        if self.lecture_code_echoue:
            return 0
        valeur = ctypes.cast(code_ptr, ctypes.POINTER(ctypes.wintypes.DWORD)).contents
        valeur.value = self.code_sortie
        return 1

    def WaitForSingleObject(self, handle, delai_ms):
        self.appels.append(("WaitForSingleObject", handle, delai_ms))
        return self.resultat_attente

    def CloseHandle(self, handle):
        self.appels.append(("CloseHandle", handle))
        return 1


def _mocker_windows(kernel32):
    faux_windll = types.SimpleNamespace(kernel32=kernel32)
    return (
        mock.patch.object(watcher.ctypes, "windll", faux_windll, create=True),
        mock.patch.object(watcher.os, "name", "nt"),
    )


def scenario_process_reellement_termine_renvoie_mort():
    """Cœur de la correction #886 : OpenProcess réussit (handle encore
    obtenu) MAIS GetExitCodeProcess lit un code != STILL_ACTIVE → le process
    a réellement terminé, _pid_vivant doit renvoyer False (plus 'vivant à
    tort')."""
    kernel32 = FausseAPIWindowsKernel32(handle_obtenu=True, code_sortie=0)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2:
        vivant, code_lu = watcher._etat_processus_windows(27772)
        assert vivant is False, "code de sortie != STILL_ACTIVE : le process a terminé, FAIT CERTAIN"
        assert code_lu is True

        # _pid_vivant doit refléter cette correction (c'est elle que
        # app.interruption._arreter_arbre_windows appelle en pratique).
        assert watcher._pid_vivant(27772) is False, (
            "avant #886, _pid_vivant renvoyait True ici (seule la présence "
            "du handle comptait) — régression du bug corrigé si ce test échoue"
        )

    noms_appels = [a[0] for a in kernel32.appels]
    assert noms_appels.count("CloseHandle") == 2, (
        f"le handle doit être fermé après chaque sonde (pas de fuite) : {kernel32.appels}"
    )
    return {"appels": len(kernel32.appels)}


def scenario_process_toujours_actif_still_active_renvoie_vivant():
    """Non-régression : un process réellement en cours (STILL_ACTIVE) reste
    'vivant' — le comportement légitime n'est pas cassé par la correction."""
    kernel32 = FausseAPIWindowsKernel32(handle_obtenu=True, code_sortie=watcher._STILL_ACTIVE)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2:
        vivant, code_lu = watcher._etat_processus_windows(4242)
        assert vivant is True
        assert code_lu is True
        assert watcher._pid_vivant(4242) is True
    return {"appels": len(kernel32.appels)}


def scenario_pid_introuvable_renvoie_mort_comme_avant():
    """Non-régression #584 : OpenProcess échoue (handle nul) → mort, FAIT
    CERTAIN, comportement INCHANGÉ depuis avant cette issue."""
    kernel32 = FausseAPIWindowsKernel32(handle_obtenu=False)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2:
        vivant, code_lu = watcher._etat_processus_windows(9999)
        assert vivant is False
        assert code_lu is True
        assert watcher._pid_vivant(9999) is False

    assert not any(a[0] == "CloseHandle" for a in kernel32.appels), (
        "aucun handle n'a été obtenu : rien à fermer"
    )
    return {"appels": len(kernel32.appels)}


def scenario_lecture_code_impossible_repli_prudent_vivant():
    """Asymétrie volontaire CONSERVÉE (issue #886, point 2 de la tâche) :
    handle obtenu mais GetExitCodeProcess échoue → AUCUN fait établi, repli
    sur la réponse prudente historique ('vivant'), jamais un faux 'mort'."""
    kernel32 = FausseAPIWindowsKernel32(handle_obtenu=True, lecture_code_echoue=True)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2:
        vivant, code_lu = watcher._etat_processus_windows(1234)
        assert vivant is True, "sonde en échec : repli prudent, jamais conclure à tort qu'il est mort"
        assert code_lu is False, "le code n'a PAS pu être lu : l'appelant doit pouvoir le distinguer"
        assert watcher._pid_vivant(1234) is True

    assert kernel32.appels[-1] == ("CloseHandle", kernel32.appels[-2][1]), (
        "le handle doit être fermé même si GetExitCodeProcess a échoué"
    )
    return {"appels": len(kernel32.appels)}


def scenario_attendre_signal_windows_ouvre_avec_synchronize_et_attend():
    kernel32 = FausseAPIWindowsKernel32(handle_obtenu=True, resultat_attente=watcher._WAIT_OBJECT_0)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2:
        watcher._attendre_signal_windows(555, 50)

    noms_appels = [a[0] for a in kernel32.appels]
    assert noms_appels == ["OpenProcess", "WaitForSingleObject", "CloseHandle"], (
        f"ordre d'appels inattendu : {kernel32.appels}"
    )
    ouverture = kernel32.appels[0]
    assert ouverture[1] == (watcher._PROCESS_QUERY_LIMITED_INFORMATION | watcher._SYNCHRONIZE), (
        "droit SYNCHRONIZE requis en plus de QUERY_LIMITED_INFORMATION pour "
        "WaitForSingleObject, voir issue #886 point 4"
    )
    attente = kernel32.appels[1]
    assert attente[1] == kernel32.appels[2][1], "WaitForSingleObject doit utiliser le même handle que CloseHandle"
    assert attente[2] == 50
    return {"appels": len(kernel32.appels)}


def scenario_attendre_signal_windows_sans_handle_ne_leve_pas():
    """Repli sur un simple sommeil si le handle (avec SYNCHRONIZE) ne peut
    être obtenu — ne doit JAMAIS lever (best-effort, voir docstring)."""
    kernel32 = FausseAPIWindowsKernel32(handle_obtenu=False)
    m1, m2 = _mocker_windows(kernel32)
    with m1, m2, mock.patch.object(watcher.time, "sleep") as faux_sleep:
        watcher._attendre_signal_windows(666, 50)
        faux_sleep.assert_called_once_with(0.05)

    assert not any(a[0] == "WaitForSingleObject" for a in kernel32.appels)
    return {"appels": len(kernel32.appels)}


def scenario_comportement_linux_strictement_inchange():
    """Garde-fou : la correction #886 ne doit toucher QUE la branche
    Windows — sur ce process réellement POSIX (ThinkPad), _pid_vivant garde
    exactement son comportement historique (déjà couvert en détail par
    tests/test_pid_vivant_zombie_748.py)."""
    import os
    assert watcher.os.name != "nt", "ce test doit tourner sur un vrai POSIX pour être significatif"
    assert watcher._pid_vivant(os.getpid()) is True
    assert watcher._pid_vivant(None) is False
    assert watcher._pid_vivant(0) is False
    return {"ok": True}


def main():
    tests = [
        ("process réellement terminé (code != STILL_ACTIVE) → _pid_vivant renvoie False (cœur du fix)",
         scenario_process_reellement_termine_renvoie_mort),
        ("process réellement actif (STILL_ACTIVE) → _pid_vivant renvoie True (non-régression)",
         scenario_process_toujours_actif_still_active_renvoie_vivant),
        ("PID introuvable (OpenProcess échoue) → mort, comportement inchangé (#584)",
         scenario_pid_introuvable_renvoie_mort_comme_avant),
        ("code de sortie illisible → repli prudent 'vivant' conservé (asymétrie documentée)",
         scenario_lecture_code_impossible_repli_prudent_vivant),
        ("_attendre_signal_windows : OpenProcess+SYNCHRONIZE puis WaitForSingleObject",
         scenario_attendre_signal_windows_ouvre_avec_synchronize_et_attend),
        ("_attendre_signal_windows sans handle → repli sommeil, ne lève jamais",
         scenario_attendre_signal_windows_sans_handle_ne_leve_pas),
        ("comportement Linux strictement inchangé par cette issue",
         scenario_comportement_linux_strictement_inchange),
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
        "validation réelle sur un poste Windows (voir procédure de test "
        "manuel dans le CHANGELOG, issue #886)."
    )

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

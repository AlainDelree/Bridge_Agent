#!/usr/bin/env python3
"""Test de non-régression — issue #249.

Le scénario Windows réel (objet Job, CreateJobObject/AssignProcessToJobObject)
n'est pas exécutable sur le ThinkPad (Linux). Ce test vérifie, par mock de
`ctypes.windll` (attribut qui n'existe que sous Windows — `create=True` le
crée pour la durée du test) et de `os.name` forcé à "nt", que :

- `_preparer_job_windows` appelle bien CreateJobObjectW, SetInformationJobObject
  puis AssignProcessToJobObject (dans cet ordre), et retourne un handle
  non-None en cas de succès ;
- `_nettoyer_arbre_claude` appelée avec ce handle ferme bien le job
  (CloseHandle) et journalise le succès ;
- en cas d'échec de CreateJobObjectW (retourne 0/NULL) ou
  d'AssignProcessToJobObject, `_preparer_job_windows` retourne None et
  journalise l'échec (issue #249 point 3 : la plateforme ne doit jamais
  rester silencieuse) — y compris quand `_nettoyer_arbre_claude` est ensuite
  appelée avec job=None ;
- une exception inattendue pendant le nettoyage (CloseHandle qui lève) est
  absorbée et journalisée, jamais remontée (issue #249 point 4).

⚠️ Ce test NE remplace PAS une validation réelle sur la VM CCW : il vérifie
que le code ctypes effectue les bons appels avec les bons arguments, pas que
Windows tue effectivement l'arbre de process en pratique. Une validation par
build réel sur CCW reste nécessaire avant de considérer #249 clos en
production.

Exécution :  python3 tests/test_nettoyage_arbre_windows_249.py
Sortie      :  code 0 si le scénario passe, 1 sinon.
"""

import logging
import sys
import types
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


class FausseAPIWindowsKernel32:
    """Simule kernel32 : CreateJobObjectW/SetInformationJobObject/
    AssignProcessToJobObject/OpenProcess/CloseHandle, avec un journal des
    appels pour assertion."""

    def __init__(self, echouer_creation=False, echouer_assignation=False):
        self.echouer_creation = echouer_creation
        self.echouer_assignation = echouer_assignation
        self.appels = []
        self._prochain_handle = 1000

    def _nouveau_handle(self):
        self._prochain_handle += 1
        return self._prochain_handle

    def CreateJobObjectW(self, sec_attrs, name):
        self.appels.append(("CreateJobObjectW",))
        if self.echouer_creation:
            return 0
        return self._nouveau_handle()

    def SetInformationJobObject(self, job, info_class, info_ptr, info_size):
        self.appels.append(("SetInformationJobObject", job, info_class))
        return 1

    def OpenProcess(self, access, inherit, pid):
        self.appels.append(("OpenProcess", pid))
        return self._nouveau_handle()

    def AssignProcessToJobObject(self, job, process_handle):
        self.appels.append(("AssignProcessToJobObject", job, process_handle))
        return 0 if self.echouer_assignation else 1

    def CloseHandle(self, handle):
        self.appels.append(("CloseHandle", handle))
        return 1


class FauxProc:
    def __init__(self, pid):
        self.pid = pid

    def wait(self, timeout=None):
        return 0


def _capturer_logs():
    messages = []

    class CaptureHandler(logging.Handler):
        def emit(self, record):
            messages.append(record.getMessage())

    handler = CaptureHandler()
    watcher.log.addHandler(handler)
    watcher.log.setLevel(logging.DEBUG)
    return handler, messages


def scenario_preparation_et_nettoyage_reussis():
    kernel32 = FausseAPIWindowsKernel32()
    faux_windll = types.SimpleNamespace(kernel32=kernel32)
    handler, messages = _capturer_logs()
    try:
        with mock.patch.object(watcher.ctypes, "windll", faux_windll, create=True), \
             mock.patch.object(watcher.os, "name", "nt"):
            job = watcher._preparer_job_windows(4242)
            assert job is not None, "un job aurait dû être créé et assigné avec succès"

            noms_appels = [a[0] for a in kernel32.appels]
            assert noms_appels == [
                "CreateJobObjectW", "SetInformationJobObject",
                "OpenProcess", "AssignProcessToJobObject", "CloseHandle",
            ], f"ordre d'appels inattendu : {noms_appels}"
            assignation = next(a for a in kernel32.appels if a[0] == "AssignProcessToJobObject")
            assert assignation[2] > 0, "AssignProcessToJobObject aurait dû recevoir un handle de process ouvert"

            watcher._nettoyer_arbre_claude(FauxProc(4242), job)

            assert kernel32.appels[-1] == ("CloseHandle", job), (
                "la fermeture du handle de job (qui tue toute la descendance "
                "assignée, y compris les process ayant survécu à claude) n'a "
                "pas été appelée en dernier"
            )
    finally:
        watcher.log.removeHandler(handler)

    assert any("Job" in m and "4242" in m for m in messages), (
        f"le succès du nettoyage via objet Job aurait dû être journalisé : {messages}"
    )
    return {"appels": len(kernel32.appels), "warnings": len(messages)}


def scenario_creation_job_echoue_journalise_echec():
    kernel32 = FausseAPIWindowsKernel32(echouer_creation=True)
    faux_windll = types.SimpleNamespace(kernel32=kernel32)
    handler, messages = _capturer_logs()
    try:
        with mock.patch.object(watcher.ctypes, "windll", faux_windll, create=True), \
             mock.patch.object(watcher.os, "name", "nt"):
            job = watcher._preparer_job_windows(4343)
            assert job is None, "CreateJobObjectW a échoué (retour 0) : aucun job ne doit être retourné"

            watcher._nettoyer_arbre_claude(FauxProc(4343), job)
    finally:
        watcher.log.removeHandler(handler)

    messages_4343 = [m for m in messages if "4343" in m]
    assert len(messages_4343) >= 2, (
        f"l'échec de préparation ET l'échec du nettoyage doivent tous deux "
        f"être journalisés (issue #249 point 3 — pas de plateforme "
        f"silencieuse), obtenu : {messages}"
    )
    return {"warnings": len(messages)}


def scenario_assignation_echoue_journalise_et_ferme_le_handle():
    kernel32 = FausseAPIWindowsKernel32(echouer_assignation=True)
    faux_windll = types.SimpleNamespace(kernel32=kernel32)
    handler, messages = _capturer_logs()
    try:
        with mock.patch.object(watcher.ctypes, "windll", faux_windll, create=True), \
             mock.patch.object(watcher.os, "name", "nt"):
            job = watcher._preparer_job_windows(4444)
            assert job is None, "AssignProcessToJobObject a échoué : _preparer_job_windows doit retourner None"
            assert any(a[0] == "CloseHandle" for a in kernel32.appels), (
                "le job créé mais jamais assigné avec succès doit être fermé "
                "immédiatement (pas de fuite de handle)"
            )
    finally:
        watcher.log.removeHandler(handler)

    assert any("4444" in m for m in messages)
    return {"warnings": len(messages)}


def scenario_exception_dans_nettoyage_ne_remonte_pas():
    """Point 4 de #249 : une exception dans le nettoyage (ex. CloseHandle qui
    lève) ne doit jamais s'échapper de _nettoyer_arbre_claude."""

    class KernelQuiExplose:
        def CloseHandle(self, *a):
            raise OSError("échec simulé de CloseHandle")

    faux_windll = types.SimpleNamespace(kernel32=KernelQuiExplose())
    handler, messages = _capturer_logs()
    try:
        with mock.patch.object(watcher.ctypes, "windll", faux_windll, create=True), \
             mock.patch.object(watcher.os, "name", "nt"):
            watcher._nettoyer_arbre_claude(FauxProc(5555), 999)
    finally:
        watcher.log.removeHandler(handler)

    assert any("5555" in m for m in messages)
    return {"warnings": len(messages)}


def main():
    if watcher.os.name == "nt":
        print("  (ce test mocke déjà le cas Windows quelle que soit la plateforme d'exécution)")

    tests = [
        ("préparation + nettoyage réussis (job créé, assigné, puis fermé)",
         scenario_preparation_et_nettoyage_reussis),
        ("échec de CreateJobObjectW → aucun job, échec journalisé",
         scenario_creation_job_echoue_journalise_echec),
        ("échec d'AssignProcessToJobObject → job fermé, aucune fuite, échec journalisé",
         scenario_assignation_echoue_journalise_et_ferme_le_handle),
        ("exception dans le nettoyage (CloseHandle) → jamais remontée",
         scenario_exception_dans_nettoyage_ne_remonte_pas),
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
        "validation réelle sur la VM CCW. Seul un build Windows réel peut "
        "confirmer que l'objet Job tue effectivement l'arbre de process en "
        "pratique."
    )

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

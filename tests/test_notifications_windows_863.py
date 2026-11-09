#!/usr/bin/env python3
"""Test de non-régression — issue #863 : chemin Windows pour la bulle de
bureau (`notifications.py`) et pour le bip (`scripts/traitement_fin.py`),
sans exécuter de vraie notification/lecture audio — la plateforme Windows
est simulée en monkeypatchant `platform.system()` et en interceptant
`subprocess.run`/`winsound`.

Couvre :
- `notifications.notifier_bureau` : sous Windows simulé, appelle
  PowerShell/NotifyIcon (titre/message passés par variables d'environnement,
  jamais interpolés dans le script) au lieu de `notify-send` ; sous Linux
  (réel ou simulé), comportement strictement inchangé (notify-send).
- Urgence 'critical' → icône d'erreur côté bulle Windows.
- Échec PowerShell (absent, ou timeout — cas du watcher en SERVICE Windows
  sans session de bureau) : journalisé, jamais levé.
- `traitement_fin._jouer_wav` : sous Windows simulé, appelle
  `winsound.PlaySound` au lieu d'`aplay` ; sous Linux, inchangé (aplay).
  `winsound` absent (import impossible sur ce poste de test) ou en erreur :
  jamais levé.
- `traitement_fin.main()` : un bip qui échoue (son introuvable, erreur
  quelconque) n'empêche jamais le POST best-effort de fin d'issue qui suit
  (SSE onglet Résultats) — c'est le bug concret corrigé par #863.

Exécution :  python3 -m pytest tests/test_notifications_windows_863.py
"""

import subprocess
import sys
import types
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import notifications  # noqa: E402
import traitement_fin  # noqa: E402


# ─── notifications.notifier_bureau ──────────────────────────────────────────

def test_notifier_bureau_windows_appelle_powershell_pas_notify_send(monkeypatch):
    appels = []
    monkeypatch.setattr(notifications, "platform",
                         types.SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(notifications.subprocess, "run",
                         lambda *a, **k: appels.append((a, k)))

    notifications.notifier_bureau("bridge_agent", "Titre", "Message", "normal")

    assert len(appels) == 1
    argv, kwargs = appels[0]
    cmd = argv[0]
    assert cmd[0] == "powershell.exe"
    assert "notify-send" not in cmd
    assert kwargs["env"]["BRIDGE_NOTIF_TITRE"] == "Titre"
    assert kwargs["env"]["BRIDGE_NOTIF_MESSAGE"] == "Message"
    assert kwargs["env"]["BRIDGE_NOTIF_ICONE"] == "Info"


def test_notifier_bureau_windows_urgence_critical_mappe_icone_error(monkeypatch):
    appels = []
    monkeypatch.setattr(notifications, "platform",
                         types.SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(notifications.subprocess, "run",
                         lambda *a, **k: appels.append((a, k)))

    notifications.notifier_bureau("bridge_agent", "Titre", "Message", "critical")

    assert appels[0][1]["env"]["BRIDGE_NOTIF_ICONE"] == "Error"


def test_notifier_bureau_windows_powershell_absent_ne_leve_pas(monkeypatch):
    monkeypatch.setattr(notifications, "platform",
                         types.SimpleNamespace(system=lambda: "Windows"))

    def leve_absent(*a, **k):
        raise FileNotFoundError("powershell.exe introuvable")
    monkeypatch.setattr(notifications.subprocess, "run", leve_absent)

    # Ne doit JAMAIS lever — une notification qui échoue ne doit jamais
    # bloquer ni faire échouer une issue.
    notifications.notifier_bureau("bridge_agent", "Titre", "Message")


def test_notifier_bureau_windows_timeout_ne_leve_pas(monkeypatch):
    """Simule le cas du watcher tournant en SERVICE Windows sans session de
    bureau ouverte : la bulle ne peut pas s'afficher, PowerShell traîne
    jusqu'au timeout — doit rester sans incidence sur l'appelant."""
    monkeypatch.setattr(notifications, "platform",
                         types.SimpleNamespace(system=lambda: "Windows"))

    def leve_timeout(*a, **k):
        raise subprocess.TimeoutExpired(cmd="powershell.exe", timeout=10)
    monkeypatch.setattr(notifications.subprocess, "run", leve_timeout)

    notifications.notifier_bureau("bridge_agent", "Titre", "Message")


def test_notifier_bureau_linux_inchange(monkeypatch):
    """Comportement Linux strictement inchangé par #863 : notify-send,
    jamais PowerShell."""
    appels = []
    monkeypatch.setattr(notifications, "platform",
                         types.SimpleNamespace(system=lambda: "Linux"))
    monkeypatch.setattr(notifications.subprocess, "run",
                         lambda *a, **k: appels.append((a, k)))

    notifications.notifier_bureau("bridge_agent", "Titre", "Message", "critical")

    assert len(appels) == 1
    cmd = appels[0][0][0]
    assert cmd[0] == "notify-send"
    assert "-u" in cmd and cmd[cmd.index("-u") + 1] == "critical"


# ─── traitement_fin._jouer_wav ──────────────────────────────────────────────

def test_jouer_wav_windows_appelle_winsound_pas_aplay(monkeypatch):
    appels_winsound = []
    appels_subprocess = []
    faux_winsound = types.SimpleNamespace(
        SND_FILENAME=1,
        PlaySound=lambda chemin, flags: appels_winsound.append((chemin, flags)),
    )
    monkeypatch.setattr(traitement_fin, "platform",
                         types.SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(traitement_fin, "winsound", faux_winsound)
    monkeypatch.setattr(traitement_fin.subprocess, "run",
                         lambda *a, **k: appels_subprocess.append((a, k)))

    traitement_fin._jouer_wav("/tmp/faux.wav")

    assert appels_winsound == [("/tmp/faux.wav", 1)]
    assert appels_subprocess == []


def test_jouer_wav_windows_sans_winsound_ne_leve_pas(monkeypatch):
    """`winsound` non importable sur ce poste de test (Linux) : le module
    reste `None` — s'assurer que la fonction n'essaie quand même jamais
    `aplay` et ne lève rien."""
    appels_subprocess = []
    monkeypatch.setattr(traitement_fin, "platform",
                         types.SimpleNamespace(system=lambda: "Windows"))
    monkeypatch.setattr(traitement_fin, "winsound", None)
    monkeypatch.setattr(traitement_fin.subprocess, "run",
                         lambda *a, **k: appels_subprocess.append((a, k)))

    traitement_fin._jouer_wav("/tmp/faux.wav")

    assert appels_subprocess == []


def test_jouer_wav_linux_inchange(monkeypatch):
    appels = []
    monkeypatch.setattr(traitement_fin, "platform",
                         types.SimpleNamespace(system=lambda: "Linux"))
    monkeypatch.setattr(traitement_fin.subprocess, "run",
                         lambda *a, **k: appels.append((a, k)))

    traitement_fin._jouer_wav("/tmp/faux.wav")

    assert appels == [((["aplay", "/tmp/faux.wav"],), {"capture_output": True})]


def test_jouer_wav_absence_outil_ne_leve_jamais(monkeypatch):
    monkeypatch.setattr(traitement_fin, "platform",
                         types.SimpleNamespace(system=lambda: "Linux"))

    def leve_absent(*a, **k):
        raise FileNotFoundError("aplay introuvable")
    monkeypatch.setattr(traitement_fin.subprocess, "run", leve_absent)

    traitement_fin._jouer_wav("/tmp/faux.wav")  # ne doit pas lever


# ─── traitement_fin.main() : le son ne doit jamais bloquer la fin d'issue ──

def test_main_echec_son_napas_bloque_notification_fin(monkeypatch):
    """Le bug concret corrigé par #863 : si le bip échoue (quelle que soit la
    raison, sur quelque système que ce soit), le POST best-effort de fin
    d'issue (rafraîchissement SSE de l'onglet Résultats) doit quand même
    avoir lieu."""
    appels = []
    monkeypatch.setattr(traitement_fin, "son_a_jouer", lambda p, n: "cloche")

    def bip_qui_explose(demitons=0):
        raise RuntimeError("échec simulé de lecture du son")
    monkeypatch.setattr(traitement_fin, "bip", bip_qui_explose)
    monkeypatch.setattr(traitement_fin, "notifier_fin_issue",
                         lambda p, n: appels.append((p, n)))
    monkeypatch.setattr(sys, "argv",
                         ["traitement_fin.py", "--projet", "bridge_agent", "--numero", "863"])

    traitement_fin.main()

    assert appels == [("bridge_agent", "863")]

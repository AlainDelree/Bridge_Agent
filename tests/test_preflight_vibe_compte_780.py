#!/usr/bin/env python3
"""Test de non-régression — issue #780 : le pré-vol d'authentification de
l'agent `vibe` (`verifier_preflight_cle_api_vibe`, introduit par l'issue
#760) ne doit plus signaler d'avertissement pour la seule ABSENCE d'une clé
API Mistral (`MISTRAL_API_KEY` / `~/.vibe/.env`) — cette absence ne prouve
plus rien depuis la bascule sur la connexion par compte, qui persiste la
clé dans le trousseau système (OS keyring) plutôt que dans l'un de ces deux
emplacements (voir `provisioning/vibe/README.md` §3). Aucun test existant
n'exerçait directement cette fonction avant cette issue (vérifié par
recherche dans `tests/`) — ce fichier est donc entièrement nouveau, pas une
adaptation d'un fichier préexistant.

Vérifie :
1. Clé absente (ni variable d'environnement, ni `~/.vibe/.env`) : aucun
   `log.warning` émis (c'était un avertissement systématique avant #780).
2. Clé présente et de forme plausible (variable d'environnement) : aucun
   `log.warning` émis (comportement inchangé).
3. Clé présente mais de forme suspecte (trop courte, ou avec un espace) :
   `log.warning` émis — cette anomalie reste signalée, indépendamment du
   mode d'authentification réellement actif.
4. Non-régression sur l'agent historique : `AGENTS_CONNUS["claude"]` ne
   définit toujours aucune clé `verifier_preflight` — cette issue ne doit
   rien changer à son comportement.

Exécution :  python3 tests/test_preflight_vibe_compte_780.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import logging
import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


class _CaptureWarnings(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.WARNING)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def _verifier_avec_env_isole(monkeypatch_home: Path | None, variable: str | None):
    """Lance `verifier_preflight_cle_api_vibe` avec HOME redirigé vers un
    dossier sans `~/.vibe/.env` réel (jamais le vrai `~/.vibe` de la machine,
    ce test ne doit dépendre d'aucun état local de l'agent), et
    MISTRAL_API_KEY posée (ou absente) selon `variable`. Retourne la liste
    des messages de warning émis."""
    ancien_home = os.environ.get("HOME")
    ancienne_cle = os.environ.get("MISTRAL_API_KEY")
    capture = _CaptureWarnings()
    watcher.log.addHandler(capture)
    try:
        if monkeypatch_home is not None:
            os.environ["HOME"] = str(monkeypatch_home)
        if variable is None:
            os.environ.pop("MISTRAL_API_KEY", None)
        else:
            os.environ["MISTRAL_API_KEY"] = variable
        watcher.verifier_preflight_cle_api_vibe()
    finally:
        watcher.log.removeHandler(capture)
        if ancien_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = ancien_home
        if ancienne_cle is None:
            os.environ.pop("MISTRAL_API_KEY", None)
        else:
            os.environ["MISTRAL_API_KEY"] = ancienne_cle
    return capture.messages


def scenario_absence_cle_aucun_avertissement():
    """Point 1 : aucune clé trouvable (ni variable, ni fichier) -> silence."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        # Pas de ~/.vibe/.env créé sous ce HOME factice : _lire_cle_api_vibe
        # doit retomber sur None sans lever d'exception (OSError avalée).
        messages = _verifier_avec_env_isole(tmp_path, None)
        assert messages == [], (
            f"l'absence de clé API ne doit plus déclencher d'avertissement : {messages}")
    return {"messages": messages}


def scenario_cle_plausible_aucun_avertissement():
    """Point 2 : clé présente et de forme plausible -> silence (inchangé)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        messages = _verifier_avec_env_isole(tmp_path, "mstrl_cleXXXXXXXXXXXXXXXXXXXXXXXX")
        assert messages == [], f"une clé plausible ne devrait déclencher aucun avertissement : {messages}"
    return {"messages": messages}


def scenario_cle_forme_suspecte_avertissement_conserve():
    """Point 3 : clé présente mais trop courte, ou avec un espace -> toujours
    signalé (anomalie positive, indépendante du mode d'authentification)."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        messages_courte = _verifier_avec_env_isole(tmp_path, "trop_courte")
        assert len(messages_courte) == 1 and "forme" in messages_courte[0].lower(), (
            f"une clé trop courte devrait toujours être signalée : {messages_courte}")

        messages_espace = _verifier_avec_env_isole(tmp_path, "cle avec un espace dedans xxxxx")
        assert len(messages_espace) == 1 and "forme" in messages_espace[0].lower(), (
            f"une clé avec un espace devrait toujours être signalée : {messages_espace}")
    return {"messages_courte": messages_courte, "messages_espace": messages_espace}


def scenario_agent_historique_inchange():
    """Point 4 : l'agent `claude` ne définit toujours aucun `verifier_preflight`
    — cette issue ne touche pas à son pré-vol (consigne explicite #780)."""
    assert watcher.AGENTS_CONNUS["claude"].get("verifier_preflight") is None, (
        "l'agent historique ne doit définir aucun verifier_preflight")
    assert watcher.AGENTS_CONNUS["vibe"]["verifier_preflight"] is watcher.verifier_preflight_cle_api_vibe
    return {"claude_sans_verifier_preflight": True, "vibe_preflight_toujours_branche": True}


def main():
    tests = [
        ("absence de clé API Mistral -> plus aucun avertissement",
         scenario_absence_cle_aucun_avertissement),
        ("clé API plausible -> aucun avertissement (inchangé)",
         scenario_cle_plausible_aucun_avertissement),
        ("clé API de forme suspecte -> avertissement toujours émis",
         scenario_cle_forme_suspecte_avertissement_conserve),
        ("agent historique (claude) : pré-vol inchangé",
         scenario_agent_historique_inchange),
    ]

    logging.getLogger().addHandler(logging.NullHandler())
    watcher.log.setLevel(logging.DEBUG)

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

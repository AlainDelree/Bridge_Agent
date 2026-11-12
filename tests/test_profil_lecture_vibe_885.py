#!/usr/bin/env python3
"""Test de non-régression — issue #885 : Vibe 3.1.0 a retiré l'agent intégré
`plan`, utilisé jusqu'ici par `_construire_cmd_vibe` pour MODE_LECTURE
(`--agent plan` échouait avec `Error: Agent 'plan' not found.`, confirmé par
lecture du code source installé de `mistral-vibe==3.1.0`).

Vérifie :
1. `_construire_cmd_vibe` choisit le profil `bridge_lecture` pour
   MODE_LECTURE quand `~/.vibe/agents/bridge_lecture.toml` existe.
2. `_construire_cmd_vibe` continue de choisir `plan` pour MODE_LECTURE quand
   ce fichier est absent (installations Vibe 2.x, ou 3.x non encore
   provisionnées — comportement STRICTEMENT inchangé par rapport à avant
   l'issue #885).
3. MODE_ECRITURE reste inchangé (`bridge_ecriture`) quel que soit l'état de
   `bridge_lecture.toml` — la détection ci-dessus ne doit affecter QUE
   MODE_LECTURE.
4. `_detecter_cause_connue_echec_rapide` reconnaît la signature
   `Error: Agent 'plan' not found.` et retourne un message de remède clair
   (déployer `bridge_lecture.toml`) plutôt que de laisser l'appelant sans
   diagnostic affiné (texte générique de
   `_gerer_tentative_anormalement_rapide`).

`HOME` est redirigé vers un dossier temporaire pour chaque scénario (même
technique que `tests/test_preflight_vibe_compte_780.py`) : aucun risque de
lire/écrire le vrai `~/.vibe/agents/` de la machine qui exécute ce test.
`vibe` n'est jamais invoqué (consigne de l'issue #885, comme #760/#761/#873
avant elle : pas de session réelle, facturée) — les scénarios appellent
directement les fonctions Python concernées.

Exécution :  python3 tests/test_profil_lecture_vibe_885.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import os
import sys
import tempfile
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def _avec_home_isole(contenu_bridge_lecture: str | None):
    """Gestionnaire de contexte minimal : redirige HOME vers un dossier
    temporaire neuf, y dépose (ou non) `~/.vibe/agents/bridge_lecture.toml`,
    restaure HOME à la sortie. `contenu_bridge_lecture=None` : le fichier
    n'est pas créé du tout (dossier `~/.vibe/agents/` absent lui-même)."""

    class _Contexte:
        def __enter__(self):
            self._tmp = tempfile.TemporaryDirectory()
            self._ancien_home = os.environ.get("HOME")
            faux_home = Path(self._tmp.name)
            os.environ["HOME"] = str(faux_home)
            if contenu_bridge_lecture is not None:
                rep_agents = faux_home / ".vibe" / "agents"
                rep_agents.mkdir(parents=True, exist_ok=True)
                (rep_agents / "bridge_lecture.toml").write_text(
                    contenu_bridge_lecture, encoding="utf-8"
                )
            return faux_home

        def __exit__(self, *exc):
            if self._ancien_home is not None:
                os.environ["HOME"] = self._ancien_home
            else:
                os.environ.pop("HOME", None)
            self._tmp.cleanup()

    return _Contexte()


def _plafonds_suffixe() -> list[str]:
    plafonds = watcher.AGENTS_CONNUS["vibe"]["plafonds_session"]
    return [
        "--max-turns", str(plafonds["max_turns"]),
        "--max-price", str(plafonds["max_price_dollars"]),
        "--max-tokens", str(plafonds["max_tokens"]),
    ]


def scenario_profil_bridge_lecture_choisi_si_present():
    """Point 1 : fichier présent → `--agent bridge_lecture`."""
    cwd = Path("/tmp/exemple_perimetre_885")
    with _avec_home_isole("enabled_tools = [\"read_file\", \"grep\"]\n"):
        cmd = watcher._construire_cmd_vibe(watcher.MODE_LECTURE, "", "PROMPT", cwd)

    attendu = (
        ["vibe", "--agent", "bridge_lecture", "--workdir", str(cwd), "--prompt", "PROMPT"]
        + _plafonds_suffixe()
    )
    assert cmd == attendu, f"commande vibe inattendue : {cmd}"
    return {"bridge_lecture_choisi": True}


def scenario_repli_sur_plan_si_absent():
    """Point 2 : fichier absent (dossier ~/.vibe/agents/ même pas créé) →
    `--agent plan`, comportement strictement identique à avant #885."""
    cwd = Path("/tmp/exemple_perimetre_885")
    with _avec_home_isole(None):
        cmd = watcher._construire_cmd_vibe(watcher.MODE_LECTURE, "", "PROMPT", cwd)

    attendu = (
        ["vibe", "--agent", "plan", "--workdir", str(cwd), "--prompt", "PROMPT"]
        + _plafonds_suffixe()
    )
    assert cmd == attendu, f"commande vibe inattendue : {cmd}"
    return {"repli_plan": True}


def scenario_mode_ecriture_inchange_quel_que_soit_bridge_lecture():
    """Point 3 : MODE_ECRITURE reste sur `bridge_ecriture`, que
    `bridge_lecture.toml` existe ou non — la détection ne doit affecter QUE
    MODE_LECTURE."""
    cwd = Path("/tmp/exemple_perimetre_885")
    attendu = (
        ["vibe", "--agent", "bridge_ecriture", "--workdir", str(cwd), "--prompt", "PROMPT"]
        + _plafonds_suffixe()
    )

    with _avec_home_isole("enabled_tools = [\"read_file\", \"grep\"]\n"):
        cmd_avec = watcher._construire_cmd_vibe(watcher.MODE_ECRITURE, "", "PROMPT", cwd)
    assert cmd_avec == attendu, f"commande vibe inattendue (fichier présent) : {cmd_avec}"

    with _avec_home_isole(None):
        cmd_sans = watcher._construire_cmd_vibe(watcher.MODE_ECRITURE, "", "PROMPT", cwd)
    assert cmd_sans == attendu, f"commande vibe inattendue (fichier absent) : {cmd_sans}"

    return {"mode_ecriture_inchange": True}


def scenario_message_echec_clair_plutot_que_erreur_brute():
    """Point 4 : la sortie brute de Vibe (`Error: Agent 'plan' not found.`,
    message observé en production — issue #885) doit être reconnue par
    `_detecter_cause_connue_echec_rapide`, avec un remède qui nomme
    explicitement le profil à déployer, plutôt que de laisser le texte
    générique (qui pointe aujourd'hui, à tort, vers l'authentification)."""
    ancien_cfg = watcher.CFG
    watcher.CFG = watcher.Config(
        nom="test885vibe", depot="AlainDelree/depot-inexistant-test885",
        rep_travail=Path("/tmp/exemple_perimetre_885"), topic_ntfy="test885vibe",
        max_essais=1, timeout_claude=15, notifier_local=False,
        agent="vibe",
    )
    try:
        resultat = watcher._detecter_cause_connue_echec_rapide(
            "Error: Agent 'plan' not found.\n"
        )
    finally:
        watcher.CFG = ancien_cfg

    assert resultat is not None, "la signature aurait dû être reconnue"
    cause, remede = resultat
    assert "plan" in cause.lower(), f"cause inattendue : {cause}"
    assert "bridge_lecture" in remede, f"remède inattendu (profil non nommé) : {remede}"

    return {"signature_reconnue": True, "remede_nomme": True}


def main():
    tests = [
        ("profil bridge_lecture choisi pour MODE_LECTURE si déployé",
         scenario_profil_bridge_lecture_choisi_si_present),
        ("repli sur plan pour MODE_LECTURE si bridge_lecture.toml absent (inchangé)",
         scenario_repli_sur_plan_si_absent),
        ("MODE_ECRITURE (bridge_ecriture) inchangé quel que soit bridge_lecture.toml",
         scenario_mode_ecriture_inchange_quel_que_soit_bridge_lecture),
        ("message de clôture clair pour \"Agent 'plan' not found.\" plutôt que l'erreur brute",
         scenario_message_echec_clair_plutot_que_erreur_brute),
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

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

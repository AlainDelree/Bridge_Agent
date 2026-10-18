#!/usr/bin/env python3
"""Test — issue #771 : choix de l'agent d'exécution (clé AGENT) depuis
l'onglet Configuration.

Couvre :
1. get_config() expose agent/agents_valides/agent_defaut_global, dérivés de
   watcher.AGENTS_CONNUS/AGENT_PAR_DEFAUT (source unique, jamais dupliquée).
2. sauvegarder_conf() accepte une valeur connue (AGENTS_CONNUS) et l'écrit.
3. sauvegarder_conf() REFUSE une valeur inconnue : rien n'est écrit sur
   disque (le fichier garde son ancien AGENT), message d'erreur renvoyé.
4. La protection #318/#724 (garde-fou configs/*.conf pendant une issue
   mode_write dans un AUTRE projet) couvre un changement d'AGENT exactement
   comme les autres clés de l'onglet Configuration (même mécanisme
   générique : etat_configs_legitimes.enregistrer, déjà appelé par
   sauvegarder_conf pour toute clé).

Tests de LOGIQUE PURE uniquement (aucun watcher réel) — mêmes précautions
que tests/test_garde_fou_configs_actions_legitimes_724.py : configs/ et la
trace sont redirigées vers des répertoires jetables.

Exécution :  python3 tests/test_choix_agent_config_771.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402
import watcher  # noqa: E402
import etat_configs_legitimes as ecl  # noqa: E402
from app import projets as route_projets  # noqa: E402

# jsonify() (utilisée par get_config) exige un contexte d'app Flask —
# minimal, jamais monté comme serveur (même patron que
# tests/test_evenements_issues_inbox_631.py).
APP_FLASK = flask.Flask(__name__)


class _TraceIsolee:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._ancien_chemin = ecl.CHEMIN_ETAT
        self._ancien_verrou = ecl.CHEMIN_VERROU
        ecl.CHEMIN_ETAT = Path(self._tmp.name) / "configs_legitimes.json"
        ecl.CHEMIN_VERROU = ecl.CHEMIN_ETAT.with_suffix(".lock")
        return self

    def __exit__(self, *exc):
        ecl.CHEMIN_ETAT = self._ancien_chemin
        ecl.CHEMIN_VERROU = self._ancien_verrou
        self._tmp.cleanup()


class _ConfigsIsoles:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        racine = Path(self._tmp.name)
        self.configs = racine / "configs"
        self.configs.mkdir()
        self._ancien_watcher = watcher.DOSSIER_SCRIPT
        self._ancien_route = route_projets.DOSSIER_SCRIPT
        watcher.DOSSIER_SCRIPT = racine
        route_projets.DOSSIER_SCRIPT = racine
        return self

    def __exit__(self, *exc):
        watcher.DOSSIER_SCRIPT = self._ancien_watcher
        route_projets.DOSSIER_SCRIPT = self._ancien_route
        self._tmp.cleanup()


def test_1_get_config_expose_liste_derivee_de_agents_connus():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        chemin = iso.configs / "projeta.conf"
        chemin.write_text("NOM = projeta\nDEPOT = x/projeta\nREP_TRAVAIL = /tmp/projeta\n",
                           encoding="utf-8")
        import json
        with APP_FLASK.app_context():
            reponse = json.loads(route_projets.get_config("projeta").get_data())
        assert reponse["agent"] == "claude", "AGENT absent → AGENT_PAR_DEFAUT (comportement historique)"
        assert reponse["agents_valides"] == sorted(watcher.AGENTS_CONNUS), \
            "la liste proposée doit venir de watcher.AGENTS_CONNUS, pas d'une liste en dur"
        assert reponse["agent_defaut_global"] == watcher.AGENT_PAR_DEFAUT
    return {"expose": True}


def test_2_sauvegarder_conf_accepte_valeur_connue():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        chemin = iso.configs / "projetb.conf"
        chemin.write_text("NOM = projetb\nDEPOT = x/projetb\nREP_TRAVAIL = /tmp/projetb\n",
                           encoding="utf-8")
        assert "vibe" in watcher.AGENTS_CONNUS, "scénario suppose un 2e agent déjà déclaré"
        ok, msg = route_projets.sauvegarder_conf("projetb", {"AGENT": "vibe"})
        assert ok, msg
        contenu = chemin.read_text(encoding="utf-8")
        assert "AGENT = vibe" in contenu
    return {"accepte": True}


def test_3_sauvegarder_conf_refuse_valeur_inconnue_rien_ecrit():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        chemin = iso.configs / "projetc.conf"
        contenu_original = "NOM = projetc\nDEPOT = x/projetc\nREP_TRAVAIL = /tmp/projetc\nAGENT = claude\n"
        chemin.write_text(contenu_original, encoding="utf-8")

        ok, msg = route_projets.sauvegarder_conf("projetc", {"AGENT": "chatgpt"})

        assert not ok, "une valeur AGENT inconnue ne doit jamais être acceptée"
        assert "chatgpt" in msg and "inconnu" in msg.lower()
        assert chemin.read_text(encoding="utf-8") == contenu_original, \
            "le fichier ne doit pas avoir été modifié — un AGENT inconnu rendrait le watcher incapable de démarrer"
    return {"refuse": True}


def test_4_garde_fou_724_couvre_aussi_le_changement_agent():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        chemin = iso.configs / "projetd.conf"
        chemin.write_text("NOM = projetd\nDEPOT = x/projetd\nREP_TRAVAIL = /tmp/projetd\nAGENT = claude\n",
                           encoding="utf-8")

        instant_debut = time.time()
        empreinte_avant = (watcher._empreinte_configs(), instant_debut)

        ok, _ = route_projets.sauvegarder_conf("projetd", {"AGENT": "vibe"})
        assert ok

        watcher._restaurer_configs_modifies(771, empreinte_avant)

        contenu = chemin.read_text(encoding="utf-8")
        assert "AGENT = vibe" in contenu, (
            "l'enregistrement légitime d'un changement d'AGENT depuis l'onglet "
            "Configuration ne doit pas être annulé par le garde-fou #318"
        )
    return {"conserve": True}


def main() -> int:
    tests = [
        ("1. get_config expose agent/agents_valides dérivés de AGENTS_CONNUS", test_1_get_config_expose_liste_derivee_de_agents_connus),
        ("2. sauvegarder_conf accepte une valeur AGENT connue", test_2_sauvegarder_conf_accepte_valeur_connue),
        ("3. sauvegarder_conf refuse une valeur AGENT inconnue (rien écrit)", test_3_sauvegarder_conf_refuse_valeur_inconnue_rien_ecrit),
        ("4. garde-fou #318/#724 conserve un changement d'AGENT légitime", test_4_garde_fou_724_couvre_aussi_le_changement_agent),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}  — {e}")
        except Exception as e:
            echecs += 1
            print(f"  ✗ {nom}  — exception inattendue : {type(e).__name__}: {e}")

    print(f"\n{len(tests)} scénario(s), {len(tests) - echecs} réussi(s), {echecs} échec(s).")
    if echecs:
        print("❌ Des scénarios sont en échec.")
        return 1
    print("✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

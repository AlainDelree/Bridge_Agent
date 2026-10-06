#!/usr/bin/env python3
"""Test de non-régression — issue #724 : le garde-fou technique configs/*.conf
(issue #318, watcher.py::_restaurer_configs_modifies) ne doit plus annuler les
trois gestes volontaires d'Alain qui passent, eux aussi, par configs/ pendant
qu'une issue mode_write tourne dans N'IMPORTE QUEL projet : création de
projet (`nouveau_projet.ecrire_conf`), suppression de projet
(`supprimer_projet._supprimer_conf`), enregistrement de l'onglet
Configuration (`app/projets.sauvegarder_conf`). Le mécanisme : ces trois
points écrivent une trace horodatée via `etat_configs_legitimes.enregistrer`,
consultée par le garde-fou (`watcher._action_legitime_posterieure`) avant de
restaurer quoi que ce soit — voir les docstrings de ces fonctions.

Tests de LOGIQUE PURE uniquement, sans watcher réel (aucun `claude`/`gh` faux
exécutable, aucun cycle de traitement d'issue) : les fonctions concernées
sont appelées directement. `etat_configs_legitimes.CHEMIN_ETAT`/
`CHEMIN_VERROU`, `watcher.DOSSIER_SCRIPT` et `app.projets.DOSSIER_SCRIPT`
sont monkeypatchés vers des fichiers/répertoires jetables pour chaque
scénario (même précaution que `tests/test_cases_cochees_629.py` et
`tests/test_supprimer_projet_587.py`) : aucun scénario ne touche au vrai
`configs/` ni au vrai `logs/configs_legitimes.json` du dépôt.

Couvre, dans l'ordre demandé par l'issue :
1. nouveau .conf créé par l'UTILISATEUR (nouveau_projet.ecrire_conf) pendant
   une issue mode_write en cours ailleurs → conservé.
2. nouveau .conf créé par l'ISSUE elle-même (écriture directe, sans trace)
   → toujours supprimé.
3. modification d'un .conf par l'onglet Configuration
   (app.projets.sauvegarder_conf) pendant une issue → conservée.
4. modification par l'ISSUE elle-même (écriture directe, sans trace)
   → toujours annulée (restauration du contenu d'avant).
5. suppression d'un projet par l'utilisateur (supprimer_projet._supprimer_conf)
   → le .conf n'est PAS recréé.
6. trace expirée (> etat_configs_legitimes.DUREE_VALIDITE_S) → le garde-fou
   retrouve son comportement strict (suppression malgré une entrée présente
   mais périmée).

Plus deux scénarios sur le module `etat_configs_legitimes` lui-même (aller-
retour enregistrer/instant_legitime, purge d'une entrée expirée à la lecture).

Exécution :  python3 tests/test_garde_fou_configs_actions_legitimes_724.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
import tempfile
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402
import etat_configs_legitimes as ecl  # noqa: E402
import nouveau_projet as np_cli  # noqa: E402
import supprimer_projet as sp_cli  # noqa: E402
from app import projets as route_projets  # noqa: E402


class _TraceIsolee:
    """Redirige etat_configs_legitimes.CHEMIN_ETAT/CHEMIN_VERROU vers un
    fichier jetable — aucun scénario ne touche au vrai
    logs/configs_legitimes.json du dépôt."""

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
    """Redirige configs/ vers un répertoire jetable pour watcher.py,
    nouveau_projet.py et app/projets.py — même précaution, côté configs/,
    que tests/test_supprimer_projet_587.py. Combine toujours avec
    `_TraceIsolee` (la trace et configs/ sont deux états distincts)."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        racine = Path(self._tmp.name)
        self.configs = racine / "configs"
        self.configs.mkdir()

        self._ancien_watcher = watcher.DOSSIER_SCRIPT
        self._ancien_np = np_cli.DOSSIER_CONFIGS
        self._ancien_route = route_projets.DOSSIER_SCRIPT

        watcher.DOSSIER_SCRIPT = racine
        np_cli.DOSSIER_CONFIGS = self.configs
        route_projets.DOSSIER_SCRIPT = racine
        return self

    def __exit__(self, *exc):
        watcher.DOSSIER_SCRIPT = self._ancien_watcher
        np_cli.DOSSIER_CONFIGS = self._ancien_np
        route_projets.DOSSIER_SCRIPT = self._ancien_route
        self._tmp.cleanup()


# ─── etat_configs_legitimes — logique pure du module ───────────────────────

def test_enregistrer_puis_instant_legitime():
    with _TraceIsolee():
        assert ecl.instant_legitime("a.conf") is None
        ecl.enregistrer("a.conf", maintenant=1000.0)
        assert ecl.instant_legitime("a.conf", maintenant=1000.5) == 1000.0
        # Un autre fichier jamais enregistré reste absent.
        assert ecl.instant_legitime("b.conf", maintenant=1000.5) is None
    return {"instant": 1000.0}


def test_instant_legitime_purge_entree_expiree():
    with _TraceIsolee():
        ecl.enregistrer("vieux.conf", maintenant=1000.0)
        maintenant = 1000.0 + ecl.DUREE_VALIDITE_S + 1
        assert ecl.instant_legitime("vieux.conf", maintenant=maintenant) is None
    return {"purge": True}


# ─── Garde-fou #318/#724 — scénarios de l'issue ─────────────────────────────

def test_1_nouveau_conf_utilisateur_conserve():
    with _TraceIsolee(), _ConfigsIsoles():
        instant_debut = time.time()
        empreinte_avant = (watcher._empreinte_configs(), instant_debut)

        # Geste volontaire d'Alain, PENDANT le traitement de l'issue.
        np_cli.ecrire_conf("annuairetoken", "AlainDelree/annuairetoken",
                            "/tmp/annuairetoken", "/tmp/annuairetoken")

        watcher._restaurer_configs_modifies(138, empreinte_avant)

        assert (Path(np_cli.DOSSIER_CONFIGS) / "annuairetoken.conf").exists(), \
            "la création légitime via new_issue.py ne doit pas être annulée"
    return {"conserve": True}


def test_2_nouveau_conf_issue_toujours_supprime():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        instant_debut = time.time()
        empreinte_avant = (watcher._empreinte_configs(), instant_debut)

        # L'ISSUE elle-même écrit directement dans configs/ (aucune trace).
        (iso.configs / "intrus.conf").write_text("NOM = intrus\n", encoding="utf-8")

        watcher._restaurer_configs_modifies(1, empreinte_avant)

        assert not (iso.configs / "intrus.conf").exists(), \
            "un .conf créé par l'issue elle-même (sans trace) doit rester supprimé"
    return {"supprime": True}


def test_3_modification_onglet_configuration_conservee():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        chemin = iso.configs / "projetx.conf"
        chemin.write_text("NOM = projetx\nTOPIC_NTFY = ancien\n", encoding="utf-8")

        instant_debut = time.time()
        empreinte_avant = (watcher._empreinte_configs(), instant_debut)

        ok, _ = route_projets.sauvegarder_conf("projetx", {"TOPIC_NTFY": "nouveau"})
        assert ok

        watcher._restaurer_configs_modifies(2, empreinte_avant)

        contenu = chemin.read_text(encoding="utf-8")
        assert "TOPIC_NTFY = nouveau" in contenu, \
            "l'enregistrement légitime depuis l'onglet Configuration ne doit pas être annulé"
    return {"conserve": True}


def test_4_modification_issue_toujours_annulee():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        chemin = iso.configs / "projety.conf"
        contenu_original = "NOM = projety\nTOPIC_NTFY = ancien\n"
        chemin.write_text(contenu_original, encoding="utf-8")

        instant_debut = time.time()
        empreinte_avant = (watcher._empreinte_configs(), instant_debut)

        # L'ISSUE modifie directement le fichier (aucune trace).
        chemin.write_text("NOM = projety\nTOPIC_NTFY = pirate\n", encoding="utf-8")

        watcher._restaurer_configs_modifies(3, empreinte_avant)

        assert chemin.read_text(encoding="utf-8") == contenu_original, \
            "une modification faite par l'issue elle-même doit toujours être restaurée"
    return {"restaure": True}


def test_5_suppression_projet_utilisateur_pas_recree():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        chemin = iso.configs / "projetz.conf"
        chemin.write_text("NOM = projetz\n", encoding="utf-8")

        instant_debut = time.time()
        empreinte_avant = (watcher._empreinte_configs(), instant_debut)

        # Geste volontaire d'Alain : suppression de projet.
        resultat = sp_cli._supprimer_conf(chemin)
        assert resultat["ok"] and not chemin.exists()

        watcher._restaurer_configs_modifies(4, empreinte_avant)

        assert not chemin.exists(), \
            "la suppression légitime d'un projet ne doit pas recréer son .conf"
    return {"non_recree": True}


def test_6_trace_expiree_comportement_strict():
    with _TraceIsolee(), _ConfigsIsoles() as iso:
        instant_debut = time.time()
        empreinte_avant = (watcher._empreinte_configs(), instant_debut)

        # Une trace a bien existé pour ce fichier, mais il y a longtemps —
        # bien avant le début de CE traitement, et surtout expirée depuis.
        ecl.enregistrer("expire.conf",
                         maintenant=instant_debut - ecl.DUREE_VALIDITE_S - 100)

        # Le fichier apparaît comme nouveau pendant le traitement (écriture
        # directe, comme une issue le ferait) — la trace associée est périmée.
        (iso.configs / "expire.conf").write_text("NOM = expire\n", encoding="utf-8")

        watcher._restaurer_configs_modifies(5, empreinte_avant)

        assert not (iso.configs / "expire.conf").exists(), \
            "une trace périmée ne doit plus protéger un .conf — comportement strict #318"
    return {"strict": True}


def main() -> int:
    tests = [
        ("etat_configs_legitimes — enregistrer puis instant_legitime", test_enregistrer_puis_instant_legitime),
        ("etat_configs_legitimes — purge d'une entrée expirée à la lecture", test_instant_legitime_purge_entree_expiree),
        ("1. nouveau .conf créé par l'utilisateur → conservé", test_1_nouveau_conf_utilisateur_conserve),
        ("2. nouveau .conf créé par l'issue → toujours supprimé", test_2_nouveau_conf_issue_toujours_supprime),
        ("3. modification onglet Configuration → conservée", test_3_modification_onglet_configuration_conservee),
        ("4. modification par l'issue → toujours annulée", test_4_modification_issue_toujours_annulee),
        ("5. suppression de projet utilisateur → .conf non recréé", test_5_suppression_projet_utilisateur_pas_recree),
        ("6. trace expirée → comportement strict retrouvé", test_6_trace_expiree_comportement_strict),
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

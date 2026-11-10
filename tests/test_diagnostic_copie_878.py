#!/usr/bin/env python3
"""Test — issue #878 : journal de diagnostic durable de la copie presse-papier
de l'onglet Résultats (cases à cocher dont le clic reste parfois sans effet,
juste après un redessin de ligne ou après un long retour d'onglet).

Deux couches couvertes séparément :

1. `identite.diagnostic_copie()` — réglage `DIAGNOSTIC_COPIE` de
   `identite_locale.conf`, DÉSACTIVÉ PAR DÉFAUT (même patron que
   `identite.machine_seule()`, tests/test_poste_seul_870.py) : absence de la
   clé ou toute valeur autre que les VALEURS_VRAIES → False, comportement
   inchangé.

2. `app/diagnostic_copie.py::route_diagnostic_copie` — point d'entrée
   MINIMAL : NO-OP strict (aucune écriture, pas même la création du
   répertoire logs/) quand le réglage est désactivé ; sinon écrit UNE ligne
   de texte brut, bornée en longueur et débarrassée de tout retour à la
   ligne (pour rester une ligne de log), jamais interprétée ni exécutée.

Aucun accès au vrai `identite_locale.conf` ni au vrai `logs/` du dépôt
(isolation par monkeypatch/tempdir, comme tests/test_poste_seul_870.py et
tests/test_decoche_relance_720.py).

Exécution :  python3 -m pytest tests/test_diagnostic_copie_878.py
         ou  python3 tests/test_diagnostic_copie_878.py
"""

import sys
import tempfile
from pathlib import Path
from unittest import mock

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import identite  # noqa: E402
from app import diagnostic_copie as route_dc  # noqa: E402

APP_FLASK = flask.Flask(__name__)


# ─── 1. identite.diagnostic_copie() ──────────────────────────────────────

def test_diagnostic_copie_absente_par_defaut():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"  # n'existe pas
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.diagnostic_copie() is False


def test_diagnostic_copie_active_oui():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("DIAGNOSTIC_COPIE = oui\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.diagnostic_copie() is True


def test_diagnostic_copie_valeur_quelconque_reste_inactive():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "identite_locale.conf"
        chemin.write_text("DIAGNOSTIC_COPIE = non\n", encoding="utf-8")
        with mock.patch.object(identite, "FICHIER_IDENTITE_LOCALE", chemin):
            assert identite.diagnostic_copie() is False


# ─── 2. app/diagnostic_copie.py::route_diagnostic_copie ──────────────────

class _JournalIsole:
    """Isole le fichier de log ET le logger mis en cache par
    _obtenir_journal() — sans remettre route_dc._journal à None, le logger
    créé par un test précédent (pointant sur SON tempdir déjà nettoyé)
    serait réutilisé par le test suivant."""

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._ancien_fichier = route_dc.FICHIER_LOG
        self._ancien_journal = route_dc._journal
        route_dc.FICHIER_LOG = Path(self._tmp.name) / "diagnostic_copie.log"
        route_dc._journal = None
        return self

    def __exit__(self, *exc):
        route_dc.FICHIER_LOG = self._ancien_fichier
        route_dc._journal = self._ancien_journal
        self._tmp.cleanup()


def test_route_desactivee_par_defaut_aucune_ecriture_ni_repertoire():
    with _JournalIsole():
        with mock.patch.object(identite, "diagnostic_copie", lambda: False):
            with APP_FLASK.test_request_context(
                    "/diagnostic-copie", method="POST", data=b"une ligne de diagnostic"):
                rep = route_dc.route_diagnostic_copie()
        assert rep[1] == 204
        assert not route_dc.FICHIER_LOG.exists()
        assert not route_dc.FICHIER_LOG.parent.exists() or not any(route_dc.FICHIER_LOG.parent.iterdir())


def test_route_active_ecrit_la_ligne_telle_quelle():
    with _JournalIsole():
        with mock.patch.object(identite, "diagnostic_copie", lambda: True):
            with APP_FLASK.test_request_context(
                    "/diagnostic-copie", method="POST",
                    data=b"date=2026-11-10 etape=ecriture resultat=succes"):
                rep = route_dc.route_diagnostic_copie()
        assert rep[1] == 204
        assert route_dc.FICHIER_LOG.exists()
        contenu = route_dc.FICHIER_LOG.read_text(encoding="utf-8")
        assert "etape=ecriture" in contenu
        assert "resultat=succes" in contenu


def test_route_tronque_une_ligne_trop_longue_a_longueur_max_ligne():
    with _JournalIsole():
        with mock.patch.object(identite, "diagnostic_copie", lambda: True):
            corps = "x" * (route_dc.LONGUEUR_MAX_LIGNE + 500)
            with APP_FLASK.test_request_context(
                    "/diagnostic-copie", method="POST", data=corps.encode("utf-8")):
                route_dc.route_diagnostic_copie()
        contenu = route_dc.FICHIER_LOG.read_text(encoding="utf-8")
        # Ni l'horodatage ("YYYY-MM-DD HH:MM:SS,mmm", espace interne) ni le
        # contenu ("x" répété) ne permettent de couper proprement sur un
        # espace : on compte directement le nombre de "x" consécutifs écrits.
        assert "x" * route_dc.LONGUEUR_MAX_LIGNE in contenu
        assert "x" * (route_dc.LONGUEUR_MAX_LIGNE + 1) not in contenu


def test_route_neutralise_les_retours_a_la_ligne_une_seule_ligne_de_log():
    with _JournalIsole():
        with mock.patch.object(identite, "diagnostic_copie", lambda: True):
            with APP_FLASK.test_request_context(
                    "/diagnostic-copie", method="POST", data=b"ligne1\nligne2\r\nligne3"):
                route_dc.route_diagnostic_copie()
        lignes = route_dc.FICHIER_LOG.read_text(encoding="utf-8").strip().splitlines()
        assert len(lignes) == 1   # \n/\r ne doivent jamais produire une 2e ligne de LOG
        assert "ligne1" in lignes[0] and "ligne2" in lignes[0] and "ligne3" in lignes[0]


def test_route_corps_vide_ou_blanc_necrit_rien():
    with _JournalIsole():
        with mock.patch.object(identite, "diagnostic_copie", lambda: True):
            with APP_FLASK.test_request_context(
                    "/diagnostic-copie", method="POST", data=b"   "):
                rep = route_dc.route_diagnostic_copie()
        assert rep[1] == 204
        assert not route_dc.FICHIER_LOG.exists()


def test_route_rotation_configuree_taille_bornee():
    """Pas un test de rotation RÉELLE (écrire plusieurs Mo serait lent) :
    vérifie juste que le handler est bien un RotatingFileHandler avec une
    borne de taille et un nombre d'archives > 0 — la garantie demandée par
    l'issue #878 (« taille bornée et rotation »)."""
    with _JournalIsole():
        with mock.patch.object(identite, "diagnostic_copie", lambda: True):
            with APP_FLASK.test_request_context(
                    "/diagnostic-copie", method="POST", data=b"ligne"):
                route_dc.route_diagnostic_copie()
        journal = route_dc._obtenir_journal()
        (handler,) = journal.handlers
        assert handler.maxBytes > 0
        assert handler.backupCount > 0


def main() -> int:
    import inspect
    import types
    tests = [(n, f) for n, f in globals().items()
             if n.startswith("test_") and isinstance(f, types.FunctionType)]
    echecs = 0
    for nom, fn in tests:
        if inspect.signature(fn).parameters:
            print(f"  · {nom} (ignoré hors pytest — nécessite un fixture)")
            continue
        try:
            fn()
            print(f"  ✓ {nom}")
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

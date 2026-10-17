#!/usr/bin/env python3
"""Test de non-régression — issue #765.

Vérifie le garde-fou de `tests/lancer_tous_les_tests.py` qui refuse de
lancer la suite si les dépendances du projet (`requirements.txt` +
`requirements-dev.txt`) ne sont pas importables dans l'interpréteur
courant — cas typique d'un environnement virtuel non activé, qui faisait
jusqu'ici échouer d'un coup la quarantaine de fichiers dépendant de
l'interface web, sans indiquer la cause.

1. `dependances_manquantes` détecte un paquet absent sans faux positif sur
   un paquet présent — vérification fondée sur l'import réel, pas sur un
   chemin `venv/` en dur.
2. `main()` s'arrête AVANT d'exécuter le moindre fichier de test dès qu'une
   dépendance déclarée manque, avec un code de retour dédié (2), distinct
   de 0 (succès) et 1 (échec de test) — et un message qui nomme la cause
   probable et la commande d'activation.
3. Non-régression : dans l'environnement réel de ce test (qui tourne donc
   avec les dépendances déjà présentes), `dependances_manquantes()` sans
   argument ne signale rien — le garde-fou ne doit jamais gêner une
   exécution légitime depuis un environnement correctement configuré.

Aucun sous-processus réel n'est lancé (le scénario 2 monkeypatche la
liste de dépendances requises puis appelle `main()` directement) : rapide
et sans dépendance à l'état réel de l'environnement d'exécution.

Exécution :  python3 tests/test_garde_fou_venv_765.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import io
import sys
from contextlib import redirect_stderr, redirect_stdout

import lancer_tous_les_tests as ltl


def scenario_detection_sans_faux_positif():
    """Un paquet de la stdlib (toujours présent) n'est jamais signalé
    manquant ; un nom de paquet inexistant l'est."""
    assert ltl.dependances_manquantes(("sys", "os")) == []
    assert ltl.dependances_manquantes(
        ("sys", "paquet_qui_n_existe_vraiment_pas_765")
    ) == ["paquet_qui_n_existe_vraiment_pas_765"]
    return {"detection_ok": True}


class _DossierTestsEspion:
    """Remplace `DOSSIER_TESTS` pour constater qu'aucun `.glob(...)` n'est
    appelé après le refus — `Path` n'autorise pas l'affectation directe
    d'attribut sur une instance (`__slots__`), d'où ce remplacement complet
    de l'objet plutôt qu'un monkeypatch de sa seule méthode `glob`."""

    def __init__(self):
        self.appels = []

    def glob(self, motif):
        self.appels.append(motif)
        return iter(())


def scenario_arret_avant_execution_code_dedie(monkeypatch):
    """Dépendance requise absente → `main()` retourne le code dédié, AVANT
    tout appel à `DOSSIER_TESTS.glob` (aucun fichier de test exécuté), avec
    un message qui nomme la cause et la commande d'activation."""
    faux_dossier = _DossierTestsEspion()
    monkeypatch.setattr(
        ltl, "DEPENDANCES_REQUISES",
        ("paquet_qui_n_existe_vraiment_pas_765",))
    monkeypatch.setattr(ltl, "DOSSIER_TESTS", faux_dossier)

    sortie_err = io.StringIO()
    with redirect_stdout(io.StringIO()), redirect_stderr(sortie_err):
        code = ltl.main()

    assert code == ltl.CODE_ENVIRONNEMENT_INVALIDE
    assert code not in (0, 1), "le refus doit être distinguable d'un succès ou d'un échec de test"
    assert not faux_dossier.appels, "aucun fichier de test ne doit être listé/exécuté après le refus"
    message = sortie_err.getvalue()
    assert "paquet_qui_n_existe_vraiment_pas_765" in message
    assert "activ" in message.lower(), "le message doit indiquer comment activer l'environnement"
    assert "venv" in message.lower()
    return {"arret_precoce_ok": True}


def scenario_environnement_reel_non_bloquant():
    """Non-régression : dans l'environnement réel de CE test (forcément
    pourvu des dépendances requises, puisque ce fichier s'exécute), le
    garde-fou ne signale rien — il ne doit jamais gêner une exécution
    légitime depuis un environnement correctement configuré."""
    assert ltl.dependances_manquantes() == []
    return {"non_bloquant_ok": True}


class _FauxMonkeypatch:
    """Équivalent minimal de `monkeypatch` de pytest, pour rester un script
    autonome exécutable hors pytest (convention du dépôt, cf. en-tête)."""

    def __init__(self):
        self._restaurations = []

    def setattr(self, obj, nom, valeur):
        self._restaurations.append((obj, nom, getattr(obj, nom)))
        setattr(obj, nom, valeur)

    def defaire(self):
        for obj, nom, ancienne in reversed(self._restaurations):
            setattr(obj, nom, ancienne)


def main():
    tests = [
        ("détection sans faux positif (stdlib vs paquet inexistant)",
         scenario_detection_sans_faux_positif),
        ("dépendance manquante → arrêt avant exécution, code dédié, message clair",
         scenario_arret_avant_execution_code_dedie),
        ("environnement réel (celui de ce test) : garde-fou non bloquant",
         scenario_environnement_reel_non_bloquant),
    ]

    echecs = 0
    for nom, fn in tests:
        mp = _FauxMonkeypatch()
        try:
            if fn is scenario_arret_avant_execution_code_dedie:
                rap = fn(mp)
            else:
                rap = fn()
            print(f"  ✓ {nom}  ({rap})")
        except AssertionError as e:
            echecs += 1
            print(f"  ✗ {nom}\n      {e}")
        except Exception as e:  # noqa: BLE001
            echecs += 1
            print(f"  ✗ {nom} — erreur inattendue : {type(e).__name__}: {e}")
        finally:
            mp.defaire()

    if echecs:
        print(f"\n❌ {echecs} scénario(s) en échec.")
        return 1
    print("\n✅ Tous les scénarios passent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

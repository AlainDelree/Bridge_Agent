#!/usr/bin/env python3
"""Test de non-régression — issue #634 : l'événement SSE `creation_issue`
transporte désormais les labels RÉELS et les données de temps (timeout,
max_essais, backoff, priorite, sans_limite, debut=None, estimation) — tout ce
qui est déjà connu localement à la création, calculé par la fonction UNIQUE
`app.issues.donnees_temps_creation()`, réutilisée par `issues_en_attente()`
pour /issues-en-attente (même source, aucune divergence possible).

Avant #634 : l'événement `creation_issue` ne transportait que
`{projet, numero, titre, fichier}` — la ligne apparaissait avec `labels: []`
et sans donnée de temps côté navigateur, qui devait attendre un fetch
`/issues-en-attente` ultérieur. Ce fetch pouvait échouer à faire apparaître
l'issue (décalage d'indexation de `gh issue list` juste après sa création) :
`chargerTimingProjet()` purgeait alors l'entrée « en file » déjà affichée
avant de la réinjecter — d'où le badge qui disparaissait puis restait absent
jusqu'à `debut_issue`. Voir aussi `static/js/tests/resultats.test.js`
(fusion du timing, `node --test`) pour le correctif côté navigateur.

Couvre :
- `donnees_temps_creation()` : contenu exact pour un cas simple (mode_write,
  TIMEOUT explicite, priorité normale, aucun historique), le cas priorité
  haute (sans_limite), le repli TIMEOUT absent → défaut projet ;
- même fonction, appelée avec un historique peuplé, retourne EXACTEMENT ce que
  `estimer_duree()` calculerait directement avec ce même historique (source
  unique, pas de duplication de calcul) ;
- `app.issues.envoyer()` (formulaire web) : l'appel à
  `app.fin_issue.emettre_creation_issue()` est enrichi des labels réellement
  posés et des données de temps ci-dessus — un SEUL appel `gh` (`issue
  create`), aucun appel GitHub supplémentaire pour construire cet
  enrichissement.

Exécution :  python3 tests/test_creation_issue_enrichie_634.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import flask  # noqa: E402

import app.issues as ai  # noqa: E402
import app.watchers as aw  # noqa: E402
import app.notifications_poller as anp  # noqa: E402
import app.fin_issue as afi  # noqa: E402
from watcher import PAUSE_ENTRE_TENTATIVES  # noqa: E402

APP_FLASK = flask.Flask(__name__)

# Nom de projet et combinaison type/mode DÉLIBÉRÉMENT inédits (jamais utilisés
# par un vrai projet de ce dépôt) : donnees_temps_creation() lit en repli
# logs/etat_timeout.json (calibration EWMA globale au dépôt, pas isolée par
# test) — un nom inédit garantit qu'aucune combinaison réelle n'y correspond,
# quel que soit l'état de ce fichier sur la machine qui exécute le test.
CFG_TEST = SimpleNamespace(nom="projet_test_634", depot="AlainDelree/ProjetTest634",
                            max_essais=3, timeout_claude=300, timeout_chef=1200)


class Patch:
    """Remplace `getattr(module, nom)` par `valeur` ; restaure à la sortie du
    `with`. Même utilitaire minimal que tests/test_poller_issues_ccw_624.py
    (pas de dépendance à unittest.mock)."""

    def __init__(self, module, nom, valeur):
        self.module, self.nom, self.valeur = module, nom, valeur

    def __enter__(self):
        self.original = getattr(self.module, self.nom)
        setattr(self.module, self.nom, self.valeur)
        return self.valeur

    def __exit__(self, *exc):
        setattr(self.module, self.nom, self.original)


# ─── donnees_temps_creation() : contenu ─────────────────────────────────────

def test_donnees_temps_creation_sans_historique():
    body = "| TIMEOUT  | 45s |\n| PRIORITE | normale |\n"
    donnees = ai.donnees_temps_creation(
        CFG_TEST, "Une tâche", body, ["bridge", "for-linux", "mode_write", "notif_pc"],
        historique=[])
    assert donnees == {
        "timeout": 45, "max_essais": 3, "backoff": PAUSE_ENTRE_TENTATIVES,
        "priorite": "normale", "sans_limite": False, "debut": None,
        "estimation": {"mediane": None, "n": 0, "fiabilite": "aucune"},
    }, donnees


def test_donnees_temps_creation_priorite_haute_sans_limite():
    body = "| TIMEOUT  | 45s |\n| PRIORITE | haute |\n"
    donnees = ai.donnees_temps_creation(CFG_TEST, "Une tâche", body, ["bridge", "for-linux"],
                                         historique=[])
    assert donnees["priorite"] == "haute"
    assert donnees["sans_limite"] is True


def test_donnees_temps_creation_timeout_absent_replie_sur_defaut_projet():
    """Pas de champ TIMEOUT dans le body → repli sur cfg.timeout_claude, comme
    _parser_timeout()/issues_en_attente() pour une issue déjà connue de gh."""
    donnees = ai.donnees_temps_creation(CFG_TEST, "Une tâche", "", [], historique=[])
    assert donnees["timeout"] == CFG_TEST.timeout_claude == 300


def test_donnees_temps_creation_meme_resultat_que_estimer_duree():
    """Source UNIQUE (issue #634) : l'estimation renvoyée par
    donnees_temps_creation() est EXACTEMENT celle que estimer_duree()
    calculerait directement avec le même historique — /issues-en-attente et
    l'événement creation_issue ne peuvent donc jamais diverger."""
    historique = [
        {"projet": "projet_test_634", "type": "normal", "mode": "write", "duree": d,
         "expiree": False}
        for d in (100, 120, 90, 110, 105)
    ]
    body = "| TIMEOUT  | 300s |\n| PRIORITE | normale |\n"
    donnees = ai.donnees_temps_creation(CFG_TEST, "Une tâche", body, ["mode_write"],
                                         historique=historique)
    attendu = ai.estimer_duree(historique, "projet_test_634", "normal", "write", "normal")
    assert donnees["estimation"] == attendu, (donnees["estimation"], attendu)
    assert donnees["estimation"]["n"] == 5
    assert donnees["estimation"]["mediane"] is not None


def test_donnees_temps_creation_debut_toujours_none():
    """Une issue tout juste créée n'a par construction jamais été prise en
    charge par le watcher : debut = None quel que soit l'historique."""
    donnees = ai.donnees_temps_creation(CFG_TEST, "Une tâche", "| TIMEOUT | 30s |\n", [],
                                         historique=[{"projet": "projet_test_634",
                                                       "type": "normal", "mode": "read",
                                                       "duree": 50, "expiree": False}])
    assert donnees["debut"] is None


# ─── app.issues.envoyer() : événement creation_issue enrichi bout en bout ──

def test_envoyer_enrichit_creation_issue_sans_appel_gh_supplementaire():
    appels_subprocess = []

    class FauxResultat:
        def __init__(self, returncode, stdout="", stderr=""):
            self.returncode, self.stdout, self.stderr = returncode, stdout, stderr

    def faux_run(cmd, **kwargs):
        appels_subprocess.append(cmd)
        return FauxResultat(0, stdout="https://github.com/AlainDelree/ProjetTest634/issues/99\n")

    capture = {}

    def faux_emettre(projet, numero, titre, fichier=None, labels=None, timing=None):
        capture.update(projet=projet, numero=numero, titre=titre, fichier=fichier,
                        labels=labels, timing=timing)

    with Patch(ai, "projet_par_nom", lambda nom: CFG_TEST if nom == CFG_TEST.nom else None), \
         Patch(ai, "_issue_ouverte_meme_titre", lambda cfg, titre: None), \
         Patch(ai.subprocess, "run", faux_run), \
         Patch(ai, "maj_rate_limit", lambda origine: (None, None)), \
         Patch(aw, "redemarrer_si_eteint", lambda cfg: (False, None, "")), \
         Patch(anp, "ajouter_issue_surveillee", lambda depot, numero, labels: None), \
         Patch(afi, "emettre_creation_issue", faux_emettre):
        with APP_FLASK.test_request_context(
                "/envoyer", method="POST",
                json={"projet": "projet_test_634", "titre": "Une tâche",
                      "mode": "ecriture", "priorite": "normale", "timeout": "120",
                      "notifs": "notif_pc", "corps": ""}):
            rep = ai.envoyer()
        assert rep.get_json()["succes"] is True, rep.get_json()

    assert len(appels_subprocess) == 1, (
        f"un seul appel gh (issue create) attendu, obtenu {len(appels_subprocess)}")
    assert capture["projet"] == "projet_test_634"
    assert capture["numero"] == 99
    assert capture["titre"] == "Une tâche"
    assert capture["fichier"] is None
    assert "notif_pc" in capture["labels"]
    assert "mode_write" in capture["labels"]
    assert capture["timing"]["timeout"] == 120
    assert capture["timing"]["max_essais"] == 3
    assert capture["timing"]["debut"] is None
    assert capture["timing"]["estimation"] is not None
    return {"labels": capture["labels"], "timing": capture["timing"]}


def main() -> int:
    tests = [
        ("donnees_temps_creation : contenu sans historique",
         test_donnees_temps_creation_sans_historique),
        ("donnees_temps_creation : priorité haute → sans_limite",
         test_donnees_temps_creation_priorite_haute_sans_limite),
        ("donnees_temps_creation : TIMEOUT absent → défaut projet",
         test_donnees_temps_creation_timeout_absent_replie_sur_defaut_projet),
        ("donnees_temps_creation : même résultat que estimer_duree() (source unique)",
         test_donnees_temps_creation_meme_resultat_que_estimer_duree),
        ("donnees_temps_creation : debut toujours None",
         test_donnees_temps_creation_debut_toujours_none),
        ("envoyer() : creation_issue enrichi, aucun appel gh de plus",
         test_envoyer_enrichit_creation_issue_sans_appel_gh_supplementaire),
    ]
    echecs = 0
    for nom, fn in tests:
        try:
            rap = fn()
            print(f"  ✓ {nom}" + (f"  ({rap})" if rap else ""))
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

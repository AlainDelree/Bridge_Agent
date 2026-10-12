#!/usr/bin/env python3
"""Test de non-régression — issue #752 : plancher de 900s pour le TIMEOUT par
défaut des issues en écriture dont le fichier déposé ne précise aucun
TIMEOUT.

Couvre :
- `scripts/watcher_issues_inbox.py::construire_body` (calcul du défaut au
  dépôt, §1 de l'issue) : plancher écriture, défaut Chef en écriture,
  lecture/lecture active inchangées, TIMEOUT présent jamais relevé, message
  de signalement (`info_timeout`) retourné pour le journal du Watcher spool
  (§4).
- `watcher.py::extraire_timeout` (filet de sécurité §3) : une issue en
  écriture sans AUCUNE ligne TIMEOUT (créée à la main sur GitHub) reçoit le
  même plancher.
- `nouveau_projet.py::GABARIT_CONF` (§6) : TIMEOUT_CLAUDE à 900 pour les
  nouveaux projets.

Aucun appel réseau/gh — logique pure uniquement.

Exécution :  python3 tests/test_plancher_timeout_ecriture_752.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import watcher  # noqa: E402
import watcher_issues_inbox as w  # noqa: E402
import nouveau_projet  # noqa: E402


def _cfg_projet(nom="bridge_agent", timeout_claude=300, timeout_chef=1200):
    return SimpleNamespace(nom=nom, timeout_claude=timeout_claude, timeout_chef=timeout_chef)


def _champs(titre="Une tâche", mode_brut="écriture", timeout_brut=None, modele=""):
    return {"titre": titre, "mode_brut": mode_brut, "timeout_brut": timeout_brut,
            "modele": modele, "corps": "Corps de l'issue."}


def scenario_1_ecriture_sans_timeout_projet_300():
    """Fichier sans TIMEOUT, en écriture, projet à 300s → plancher 900s."""
    body, info = w.construire_body(_champs(), _cfg_projet(timeout_claude=300))
    assert "| TIMEOUT  | 900s |" in body, body
    assert info == "TIMEOUT absent : défaut de 900s appliqué", info
    return {"info": info}


def scenario_2_ecriture_sans_timeout_projet_1200():
    """Projet déjà plus généreux (1200s) : le défaut reste 1200s, jamais
    abaissé à 900s (le plus grand des deux l'emporte)."""
    body, info = w.construire_body(_champs(), _cfg_projet(timeout_claude=1200))
    assert "| TIMEOUT  | 1200s |" in body, body
    assert info == "TIMEOUT absent : défaut de 1200s appliqué", info
    return {}


def scenario_3_lecture_sans_timeout_inchangee():
    """En lecture, aucun plancher écriture : TIMEOUT_CLAUDE du projet tel quel."""
    body, info = w.construire_body(_champs(mode_brut="lecture"), _cfg_projet(timeout_claude=300))
    assert "| TIMEOUT  | 300s |" in body, body
    assert info == "TIMEOUT absent : défaut de 300s appliqué", info
    return {}


def scenario_3b_lecture_active_sans_timeout_inchangee():
    """Lecture active (scratch) : même règle que lecture, aucun plancher écriture."""
    body, info = w.construire_body(_champs(mode_brut="lecture active"), _cfg_projet(timeout_claude=300))
    assert "| TIMEOUT  | 300s |" in body, body
    return {}


def scenario_4_timeout_present_jamais_releve():
    """Un TIMEOUT de 300s présent dans le fichier est conservé tel quel, même
    en écriture avec un plancher de 900s (jamais relevé) — aucun info_timeout
    (le défaut n'a pas été appliqué)."""
    body, info = w.construire_body(_champs(timeout_brut="300s"), _cfg_projet(timeout_claude=300))
    assert "| TIMEOUT  | 300s |" in body, body
    assert info is None, info
    return {}


def scenario_5_chef_en_ecriture():
    """Tâche Chef en écriture sans TIMEOUT : le plancher écriture s'applique
    EN PLUS de timeout_chef — ici timeout_chef (600s) est sous le plancher,
    le résultat doit être 900s, pas 600s."""
    body, info = w.construire_body(
        _champs(titre="Chef : répartir le travail"),
        _cfg_projet(timeout_claude=300, timeout_chef=600),
    )
    assert "| TIMEOUT  | 900s |" in body, body
    return {}


def scenario_5b_chef_en_lecture_inchange():
    """Tâche Chef en LECTURE sans TIMEOUT : règle actuelle inchangée
    (timeout_chef du projet), aucun plancher écriture appliqué."""
    body, info = w.construire_body(
        _champs(titre="Chef : répartir le travail", mode_brut="lecture"),
        _cfg_projet(timeout_claude=300, timeout_chef=1200),
    )
    assert "| TIMEOUT  | 1200s |" in body, body
    return {}


def scenario_6_filet_securite_watcher_sans_ligne_timeout():
    """watcher.extraire_timeout : issue en écriture sans AUCUNE ligne TIMEOUT
    dans le body (créée à la main sur GitHub) — plancher appliqué."""
    watcher.CFG = watcher.Config(nom="t752", depot="x/y", rep_travail=Path("/tmp"),
                                  timeout_claude=300, timeout_chef=1200)
    body_sans_timeout = "## En-tête\n\n| MODE | écriture |\n\nCorps."
    valeur = watcher.extraire_timeout(body_sans_timeout, "Une tâche", watcher.MODE_ECRITURE)
    assert valeur == 900, valeur
    return {}


def scenario_7_filet_securite_watcher_lecture_inchange():
    """Même filet de sécurité, mais en lecture : aucun plancher, TIMEOUT_CLAUDE
    du projet tel quel."""
    watcher.CFG = watcher.Config(nom="t752", depot="x/y", rep_travail=Path("/tmp"),
                                  timeout_claude=300, timeout_chef=1200)
    body_sans_timeout = "## En-tête\n\nCorps."
    valeur = watcher.extraire_timeout(body_sans_timeout, "Une tâche", watcher.MODE_LECTURE)
    assert valeur == 300, valeur
    return {}


def scenario_8_filet_securite_watcher_timeout_present_jamais_releve():
    """Une ligne TIMEOUT trouvée dans le body n'est jamais relevée par le
    plancher écriture, même sous 900s."""
    watcher.CFG = watcher.Config(nom="t752", depot="x/y", rep_travail=Path("/tmp"),
                                  timeout_claude=300, timeout_chef=1200)
    body = "## En-tête\n\n| TIMEOUT | 120s |\n\nCorps."
    valeur = watcher.extraire_timeout(body, "Une tâche", watcher.MODE_ECRITURE)
    assert valeur == 120, valeur
    return {}


def scenario_9_modele_nouveau_projet_900():
    """Le gabarit .conf écrit par nouveau_projet.py pour un NOUVEAU projet
    fixe TIMEOUT_CLAUDE à 900 (issue #752, §6)."""
    assert "TIMEOUT_CLAUDE    = 900" in nouveau_projet.GABARIT_CONF, \
        "GABARIT_CONF ne fixe plus TIMEOUT_CLAUDE à 900"
    return {}


def main():
    tests = [
        ("construire_body : écriture sans TIMEOUT, projet 300s → 900s", scenario_1_ecriture_sans_timeout_projet_300),
        ("construire_body : écriture sans TIMEOUT, projet 1200s → 1200s (inchangé)", scenario_2_ecriture_sans_timeout_projet_1200),
        ("construire_body : lecture sans TIMEOUT → valeur projet inchangée", scenario_3_lecture_sans_timeout_inchangee),
        ("construire_body : lecture active sans TIMEOUT → valeur projet inchangée", scenario_3b_lecture_active_sans_timeout_inchangee),
        ("construire_body : TIMEOUT présent (300s) jamais relevé", scenario_4_timeout_present_jamais_releve),
        ("construire_body : tâche Chef en écriture → plancher 900s", scenario_5_chef_en_ecriture),
        ("construire_body : tâche Chef en lecture → timeout_chef inchangé", scenario_5b_chef_en_lecture_inchange),
        ("watcher.extraire_timeout : filet de sécurité écriture sans ligne TIMEOUT", scenario_6_filet_securite_watcher_sans_ligne_timeout),
        ("watcher.extraire_timeout : filet de sécurité lecture inchangée", scenario_7_filet_securite_watcher_lecture_inchange),
        ("watcher.extraire_timeout : TIMEOUT trouvé jamais relevé", scenario_8_filet_securite_watcher_timeout_present_jamais_releve),
        ("nouveau_projet.py : gabarit .conf à TIMEOUT_CLAUDE=900", scenario_9_modele_nouveau_projet_900),
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

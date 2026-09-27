#!/usr/bin/env python3
"""Test de non-régression — issues #558/#658/#659 : cohérence de la méthode
utilisée pour poser `AppEnvironmentExtra` via `nssm set` sur les services
NSSM CCW, dans les 3 scripts du dépôt qui la construisent.

Historique (voir issue #659 pour le détail complet) : l'issue #558 avait
diagnostiqué qu'un tableau PowerShell SPLATTÉ (`@variable`) passé à
`nssm set … AppEnvironmentExtra` était fautif, et avait « corrigé » ceci en
joignant les entrées en UNE SEULE chaîne séparée par un saut de ligne `` `n``
— mais SANS reproduire le bug sur un nssm réel (lecture du code seule,
jamais testé avec une ligne PATH, absente du service à l'époque). L'issue
#658 (27/09/2026, PC fixe réel, nssm 2.24) a ensuite constaté empiriquement
l'INVERSE pour une valeur contenant des espaces (PATH, ex. « Program
Files ») : la chaîne unique jointe par `` `n`` ne pose PAS de ligne PATH
effective, alors que des ARGUMENTS SÉPARÉS (un par ligne) fonctionnent bien
— y compris pour cette valeur à espaces, donc a fortiori pour des tokens qui
n'en ont pas.

Issue #659 retient donc les arguments séparés comme SEULE méthode dans tout
le dépôt, dans les 3 scripts qui posent `AppEnvironmentExtra` :
`ajouter_projet_ccw.ps1`, `mettre_a_jour_tokens_ccw.ps1` (déjà aligné par
#658) et `creer_projet_ccw_complet.ps1`. Ce test vérifie :
  - qu'aucun des 3 ne joint plus les entrées en une chaîne unique via
    `[string]::Join("`n", …)` avant `nssm set … AppEnvironmentExtra` ;
  - qu'aucun des 3 ne passe un tableau splatté (`@variable`) à
    `nssm set … AppEnvironmentExtra` (ambiguïté à éviter, cf. #659) ;
  - que chacun passe bien PLUSIEURS arguments scalaires distincts à
    `nssm set … AppEnvironmentExtra`.

Ce test est une analyse STATIQUE du texte des scripts (pas d'exécution
PowerShell ni nssm réels — indisponibles sous Linux).

Exécution :  python3 tests/test_ajouter_projet_ccw_env_558.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import re
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
DOSSIER_PS = RACINE / "provisioning" / "windows"

# Les 3 scripts qui posent AppEnvironmentExtra via nssm set, avec leur chemin.
SCRIPTS = {
    "ajouter_projet_ccw.ps1": DOSSIER_PS / "ajouter_projet_ccw.ps1",
    "mettre_a_jour_tokens_ccw.ps1": DOSSIER_PS / "mettre_a_jour_tokens_ccw.ps1",
    "creer_projet_ccw_complet.ps1": RACINE / "creer_projet_ccw_complet.ps1",
}

# Motif du bug #558 (tableau splatté @variable passé à nssm set … AppEnvironmentExtra).
MOTIF_SPLAT = re.compile(
    r"nssm\s+set\s+\S+\s+AppEnvironmentExtra\s+@\w+", re.IGNORECASE
)

# Motif de l'ancien pattern #558 (chaîne unique construite par jointure `n).
MOTIF_JOIN_CHAINE_UNIQUE = re.compile(r'\[string\]::Join\(\s*"`n"')

# Motif du pattern retenu par #659 : AU MOINS DEUX arguments scalaires ($xxx,
# pas de @) distincts à la suite de AppEnvironmentExtra sur la même commande.
MOTIF_ARGS_SEPARES = re.compile(
    r"nssm\s+set\s+\S+\s+AppEnvironmentExtra\s+\$\w+(\[\d+\])?\s+\$\w+(\[\d+\])?",
    re.IGNORECASE,
)


def _lire(chemin: Path) -> str:
    assert chemin.is_file(), f"script introuvable : {chemin}"
    return chemin.read_text(encoding="utf-8-sig")


def scenario_pas_de_splat():
    """Aucun des 3 scripts ne doit passer un tableau splatté (`@variable`)
    à `nssm set … AppEnvironmentExtra` — c'est le bug #558 originel."""
    for nom, chemin in SCRIPTS.items():
        texte = _lire(chemin)
        trouve = MOTIF_SPLAT.findall(texte)
        assert not trouve, f"{nom} : splat @variable détecté sur AppEnvironmentExtra : {trouve}"
    return {}


def scenario_pas_de_chaine_unique_jointe():
    """Aucun des 3 scripts ne doit plus construire une chaîne UNIQUE jointe
    par `` `n`` pour AppEnvironmentExtra — pattern #558 invalidé par #658/#659
    (ne pose pas de ligne PATH effective avec nssm 2.24, cf. issue #659)."""
    for nom, chemin in SCRIPTS.items():
        texte = _lire(chemin)
        assert not MOTIF_JOIN_CHAINE_UNIQUE.search(texte), (
            f"{nom} : construction par [string]::Join(\"`n\", …) encore présente — "
            "pattern #558 invalidé par #659, à remplacer par des arguments séparés"
        )
    return {}


def scenario_args_separes_partout():
    """Chacun des 3 scripts doit passer PLUSIEURS arguments scalaires
    distincts à `nssm set … AppEnvironmentExtra` (seule méthode retenue,
    issue #659)."""
    for nom, chemin in SCRIPTS.items():
        texte = _lire(chemin)
        assert MOTIF_ARGS_SEPARES.search(texte), (
            f"{nom} : aucun appel « nssm set … AppEnvironmentExtra $a $b » "
            "(arguments séparés) trouvé — le pattern #659 a-t-il régressé ?"
        )
    return {}


def scenario_ajouter_projet_retrouve_path_par_cle():
    """`ajouter_projet_ccw.ps1` doit retrouver PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN
    par clé (pas par position) avant réapplication — l'ordre/le nombre de
    lignes préservées varie selon l'historique du service (PATH absent avant
    #658)."""
    texte = _lire(SCRIPTS["ajouter_projet_ccw.ps1"])
    assert "'PATH', 'GH_TOKEN', 'CLAUDE_CODE_OAUTH_TOKEN'" in texte, (
        "reconstruction par clé (PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN) introuvable"
    )
    return {}


def scenario_le_bug_aurait_ete_detecte_sur_l_ancien_code():
    """Contrôle négatif : le motif de détection du splat matche bien sur le
    texte de l'ANCIENNE ligne fautive (issue #558), pour prouver que ce test
    n'est pas vide de sens."""
    ancienne_ligne = 'nssm set $NomService AppEnvironmentExtra @envExtra | Out-Null'
    assert MOTIF_SPLAT.search(ancienne_ligne), (
        "le motif de détection ne repère pas l'ancien bug #558 — test inutile"
    )
    return {}


def scenario_le_motif_de_jointure_aurait_ete_detecte():
    """Contrôle négatif : le motif de détection de la chaîne unique jointe
    matche bien sur le texte de l'ANCIEN pattern #558 (celui remplacé par
    #659), pour prouver que ce test n'est pas vide de sens."""
    ancienne_ligne = '$envExtraChaine = [string]::Join("`n", $envExtra)'
    assert MOTIF_JOIN_CHAINE_UNIQUE.search(ancienne_ligne), (
        "le motif de détection ne repère pas l'ancien pattern #558 — test inutile"
    )
    return {}


def main():
    tests = [
        ("pas de splat @variable sur AppEnvironmentExtra dans les 3 scripts (bug #558)",
         scenario_pas_de_splat),
        ("plus de chaîne unique jointe par `n pour AppEnvironmentExtra (invalidé par #658/#659)",
         scenario_pas_de_chaine_unique_jointe),
        ("arguments séparés utilisés partout pour AppEnvironmentExtra (méthode #659)",
         scenario_args_separes_partout),
        ("ajouter_projet_ccw.ps1 : retrouve PATH/GH_TOKEN/CLAUDE_CODE_OAUTH_TOKEN par clé",
         scenario_ajouter_projet_retrouve_path_par_cle),
        ("contrôle négatif : le motif détecte bien l'ancien splat fautif (#558)",
         scenario_le_bug_aurait_ete_detecte_sur_l_ancien_code),
        ("contrôle négatif : le motif détecte bien l'ancien pattern de jointure (#558)",
         scenario_le_motif_de_jointure_aurait_ete_detecte),
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

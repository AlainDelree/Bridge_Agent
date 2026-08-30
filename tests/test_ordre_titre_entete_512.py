#!/usr/bin/env python3
"""Test de non-régression — issue #512 : `retirer_ligne_entete()` (watcher
`issues_inbox`) échouait à retirer la ligne du champ `PROJET` (et des autres
champs d'en-tête) quand la ligne `#Titre:` précède l'en-tête tabulaire au lieu
de le suivre — ordre inverse de la convention documentée au §3.3 du DOC.

Cause racine : `_regex_champ()` utilisait `\\s*` (qui inclut le saut de ligne)
juste après l'ancre `^` de début de ligne (mode MULTILINE). Quand la ligne du
champ est précédée d'une ligne VIDE (cas typique quand `#Titre:` précède
l'en-tête : une ligne vide sépare souvent les deux), `^` pouvait matcher au
début de cette ligne vide et `\\s*` avaler son saut de ligne pour atteindre le
« | » de la ligne suivante — le match démarrait alors une ligne trop tôt.
`retirer_ligne_entete()` calculait ensuite la fin de ligne avec
`corps.find("\\n", debut)` : comme `debut` pointait sur la ligne vide (un seul
caractère « \\n »), `fin == debut` et seul CE caractère isolé était retiré —
la ligne du champ elle-même restait intacte dans le corps restant, et
`construire_body()` empilait alors son propre champ `PROJET` recalculé en plus
de celui resté dans `champs["corps"]` (en-tête GitHub avec `PROJET` en double).
Reproduit concrètement sur les issues Scrabble #423/#424/#425 (cf. issue #512).

Corrigé en restreignant `_regex_champ()` aux espaces/tabulations horizontaux
(`[ \\t]*`, jamais le saut de ligne) et en bornant la recherche des champs
d'en-tête (`lire_champ_entete`/`retirer_ligne_entete`) aux
`ZONE_ENTETE_LIGNES` premières lignes du corps — pour qu'une mention
illustrative d'un champ plus bas dans le texte explicatif ne soit plus prise
pour le véritable en-tête (second bug découvert en tentant d'envoyer l'issue
#512 elle-même).

Exécution :  python3 tests/test_ordre_titre_entete_512.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
sys.path.insert(0, str(RACINE / "scripts"))

import watcher_issues_inbox as w  # noqa: E402


def _cfg_projet(nom="bridge_agent"):
    return SimpleNamespace(nom=nom, timeout_claude=300, timeout_chef=1200)


def scenario_1_titre_avant_entete_decore():
    """Reproduction directe de l'issue #512 : #Titre: en première ligne, puis
    ligne vide, puis en-tête tabulaire brut (sans décoration ## En-tête) —
    exactement la forme des fichiers Scrabble #423/#424/#425 en cause."""
    contenu = (
        "#Titre: RACINE_DONNEES_UTILISATEUR doit pointer vers %LOCALAPPDATA%\n"
        "\n"
        "| PROJET | scrabble |\n"
        "| COMPLEXITE | rapide |\n"
        "| RESEAU | non |\n"
        "\n"
        "## Contexte\n"
        "\n"
        "Texte explicatif.\n"
    )
    champs = w.extraire_champs(contenu)
    assert champs["projet"] == "scrabble", (
        f"PROJET mal extrait : {champs['projet']!r}"
    )
    assert "PROJET" not in champs["corps"], (
        "La ligne PROJET aurait dû être retirée du corps restant : "
        f"{champs['corps']!r}"
    )
    body = w.construire_body(champs, _cfg_projet("scrabble"))
    assert body.count("PROJET") == 1, (
        f"Le champ PROJET est dupliqué dans le body final :\n{body}"
    )
    return {"projet": champs["projet"]}


def scenario_2_titre_colle_sans_ligne_vide():
    """Même ordre (titre puis en-tête) mais SANS ligne vide entre les deux —
    doit continuer à fonctionner (n'était pas cassé, à ne pas régresser)."""
    contenu = (
        "#Titre: Un titre quelconque\n"
        "| PROJET | bridge_agent |\n"
        "| MODE | écriture |\n"
        "\n"
        "## Contexte\n"
        "Texte.\n"
    )
    champs = w.extraire_champs(contenu)
    assert champs["projet"] == "bridge_agent"
    assert "PROJET" not in champs["corps"]
    return {"projet": champs["projet"]}


def scenario_3_entete_decore_avant_titre_convention_documentee():
    """Convention documentée au §3.3 du DOC (en-tête AVANT #Titre:) — doit
    rester fonctionnelle après le correctif (non-régression de l'ordre
    existant, pas seulement du nouvel ordre supporté)."""
    contenu = (
        "## En-tête\n"
        "\n"
        "| Champ    | Valeur |\n"
        "|----------|--------|\n"
        "| SOURCE   | CC |\n"
        "| PROJET   | bridge_agent |\n"
        "\n"
        "#Titre: Un titre\n"
        "\n"
        "## Contexte\n"
        "Texte.\n"
    )
    champs = w.extraire_champs(contenu)
    assert champs["projet"] == "bridge_agent"
    assert "PROJET" not in champs["corps"]
    body = w.construire_body(champs, _cfg_projet("bridge_agent"))
    assert body.count("PROJET") == 1, (
        f"Le champ PROJET est dupliqué dans le body final :\n{body}"
    )
    return {"projet": champs["projet"]}


def scenario_4_mention_illustrative_plus_bas_ignoree():
    """Second bug découvert lors des tentatives d'envoi de l'issue #512 : une
    mention illustrative d'un champ PROJET dans le corps explicatif (bien
    après l'en-tête réel) ne doit PAS être retenue à la place du véritable
    en-tête, situé en tout début de fichier."""
    remplissage = "\n".join(f"Ligne de remplissage {i}." for i in range(30))
    contenu = (
        "## En-tête\n"
        "\n"
        "| PROJET   | bridge_agent |\n"
        "| MODE     | écriture |\n"
        "\n"
        "#Titre: Restreindre la zone de recherche des champs d'en-tête\n"
        "\n"
        "## Contexte\n"
        "\n"
        f"{remplissage}\n"
        "\n"
        "Exemple illustratif : `| PROJET | nom_du_projet_scrabble |` ne doit "
        "pas être pris pour le vrai en-tête.\n"
    )
    champs = w.extraire_champs(contenu)
    assert champs["projet"] == "bridge_agent", (
        "La mention illustrative plus bas a été retenue à la place du "
        f"véritable en-tête : {champs['projet']!r}"
    )
    return {"projet": champs["projet"]}


def scenario_5_lire_champ_entete_zone_bornee():
    """Vérifie directement lire_champ_entete/retirer_ligne_entete (pas
    seulement extraire_champs) sur le cas de zone bornée, en isolant le champ
    LABELS pour ne pas dépendre de PROJET."""
    remplissage = "\n".join(f"Ligne {i}." for i in range(30))
    contenu = (
        "#Titre: Titre\n"
        "| PROJET | bridge_agent |\n"
        "\n"
        f"{remplissage}\n"
        "\n"
        "Exemple : `| LABELS | urgent |`\n"
    )
    assert w.lire_champ_entete(contenu, "LABELS") is None, (
        "Une mention de LABELS hors de la zone d'en-tête n'aurait pas dû être lue."
    )
    reste = w.retirer_ligne_entete(contenu, "LABELS")
    assert reste == contenu, (
        "retirer_ligne_entete n'aurait rien dû retirer pour un champ hors zone."
    )
    return {}


def main():
    tests = [
        ("titre avant en-tête tabulaire brut, ligne vide entre les deux (bug #512)",
         scenario_1_titre_avant_entete_decore),
        ("titre avant en-tête tabulaire, collé sans ligne vide",
         scenario_2_titre_colle_sans_ligne_vide),
        ("en-tête décoré avant titre (convention §3.3, non-régression)",
         scenario_3_entete_decore_avant_titre_convention_documentee),
        ("mention illustrative plus bas dans le corps ignorée (bug #512)",
         scenario_4_mention_illustrative_plus_bas_ignoree),
        ("lire/retirer_ligne_entete respectent la zone bornée",
         scenario_5_lire_champ_entete_zone_bornee),
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

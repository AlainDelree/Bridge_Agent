#!/usr/bin/env python3
"""Test de non-régression — issue #777 (incident chesscoach #123) : assouplir
_verdict_final pour tolérer du texte AVANT le marqueur de clôture, sans
réintroduire le défaut corrigé par #762/#763/#764 (marqueur n'importe où dans
le texte, cité en exemple ou en puce de liste, pris à tort pour un verdict).

Vérifie :
1. Texte d'introduction suivi, SUR LA MÊME LIGNE (la toute première de la
   sortie), du marqueur → désormais reconnu comme verdict (cas exact de
   l'incident chesscoach #123 : la tâche était faite, le rapport illisible).
2. Ce même marqueur, cité plus loin dans le texte (pas sur la première
   ligne) — en milieu de phrase, en puce de liste, ou en exemple entre
   apostrophes inverses — ne doit JAMAIS déclencher de verdict à lui seul.
3. Quand une vraie ligne de verdict AUTONOME ouvre la réponse, une citation
   plus loin dans le texte (exemple, <details>) ne l'emporte jamais —
   inchangé depuis #763/#764 (première occurrence).
4. Du texte APRÈS le marqueur, sur la même ligne, reste rejeté : le
   marqueur doit toujours CLORE la ligne où il apparaît.

Pure Python, aucun outil externe.

Exécution :  python3 tests/test_verdict_texte_avant_marqueur_777.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def scenario_texte_avant_marqueur_premiere_ligne_reconnu():
    """Cas exact de l'incident chesscoach #123 : phrase d'intro suivie, sur
    la MÊME ligne (la première de la sortie), du marqueur de clôture."""
    sortie = (
        f"Tâche terminée avec succès. {watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "Détails : correctif appliqué et committé.\n"
    )
    assert watcher._verdict_final(sortie) == watcher.MARQUEUR_VERDICT_SUCCES, (
        "le marqueur précédé de texte sur la première ligne doit désormais "
        "être reconnu (issue #777)")
    return {"prefixe_premiere_ligne_ok": True}


def scenario_texte_avant_marqueur_echec_premiere_ligne_reconnu():
    """Même assouplissement pour le marqueur d'ÉCHEC."""
    sortie = f"Échec : permission refusée. {watcher.MARQUEUR_VERDICT_ECHEC}\n"
    assert watcher._verdict_final(sortie) == watcher.MARQUEUR_VERDICT_ECHEC
    return {"prefixe_echec_ok": True}


def scenario_marqueur_cite_en_milieu_de_phrase_hors_premiere_ligne_ignore():
    """Le marqueur, cité en milieu de phrase (texte des deux côtés) plus
    loin dans le rapport (jamais sur la première ligne), ne doit jamais
    valoir verdict à lui seul — aucune autre ligne de verdict présente ⇒
    None attendu."""
    sortie = (
        "✅ Tâche terminée — audit du format de clôture.\n\n"
        "<details><summary>Détails</summary>\n"
        f"Le gabarit attend une ligne comme `{watcher.MARQUEUR_VERDICT_SUCCES}` "
        "suivie du résumé, jamais les deux combinés sur une seule ligne.\n"
        "</details>\n"
    )
    assert watcher._verdict_final(sortie) is None, (
        "un marqueur cité en milieu de phrase, hors première ligne, ne doit "
        "jamais valoir verdict à lui seul")
    return {"citation_milieu_phrase_ignoree_ok": True}


def scenario_marqueur_employe_comme_puce_de_liste_hors_premiere_ligne_ignore():
    """Le marqueur utilisé comme puce de liste (exemple de gabarit, motif
    historique des faux positifs #762/#763), plus loin dans le rapport —
    jamais sur la première ligne — ne doit jamais valoir verdict."""
    sortie = (
        "✅ Tâche terminée — ajout de tests sur la ligne de clôture.\n\n"
        "Cas couverts par les nouveaux tests :\n"
        f"- {watcher.MARQUEUR_VERDICT_SUCCES}\n"
        f"- {watcher.MARQUEUR_VERDICT_ECHEC}\n"
    )
    assert watcher._verdict_final(sortie) is None, (
        "un marqueur employé comme puce de liste, hors première ligne, ne "
        "doit jamais valoir verdict — faux positif historique #762/#763")
    return {"puce_de_liste_ignoree_ok": True}


def scenario_vraie_ligne_verdict_prioritaire_sur_citation_plus_loin():
    """Une vraie ligne de verdict AUTONOME en première ligne l'emporte
    toujours sur une citation plus loin dans le texte (inchangé #763/#764)."""
    sortie = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "✅ Tâche terminée — vrai rapport.\n\n"
        "<details>\n"
        f"Pour mémoire, le gabarit utilise `{watcher.MARQUEUR_VERDICT_ECHEC}` "
        "en cas d'échec.\n"
        "</details>\n"
    )
    assert watcher._verdict_final(sortie) == watcher.MARQUEUR_VERDICT_SUCCES
    return {"priorite_premiere_ligne_ok": True}


def scenario_texte_apres_marqueur_meme_ligne_toujours_rejete():
    """Portée étroite de l'assouplissement : le marqueur doit toujours CLORE
    sa ligne. Du texte après lui, sur cette même ligne, reste rejeté."""
    sortie = f"{watcher.MARQUEUR_VERDICT_SUCCES} — tâche terminée.\n"
    assert watcher._verdict_final(sortie) is None, (
        "un marqueur suivi de texte sur sa propre ligne ne doit jamais "
        "valoir verdict, même en première ligne")
    return {"texte_apres_marqueur_rejete_ok": True}


def scenario_premiere_ligne_sans_marqueur_repli_sur_ligne_autonome():
    """Si la première ligne ne contient aucun marqueur, on retombe sur la
    recherche d'une ligne AUTONOME ailleurs dans le texte (comportement
    #764 inchangé)."""
    sortie = (
        "Préambule sans aucun marqueur.\n"
        f"{watcher.MARQUEUR_VERDICT_ECHEC}\n"
        "✗ Tâche en échec.\n"
    )
    assert watcher._verdict_final(sortie) == watcher.MARQUEUR_VERDICT_ECHEC
    return {"repli_ligne_autonome_ok": True}


def main():
    tests = [
        ("texte avant le marqueur, 1ère ligne, succès → reconnu (chesscoach #123)",
         scenario_texte_avant_marqueur_premiere_ligne_reconnu),
        ("texte avant le marqueur, 1ère ligne, échec → reconnu",
         scenario_texte_avant_marqueur_echec_premiere_ligne_reconnu),
        ("marqueur cité en milieu de phrase, hors 1ère ligne → ignoré",
         scenario_marqueur_cite_en_milieu_de_phrase_hors_premiere_ligne_ignore),
        ("marqueur en puce de liste, hors 1ère ligne → ignoré (#762/#763)",
         scenario_marqueur_employe_comme_puce_de_liste_hors_premiere_ligne_ignore),
        ("vraie ligne de verdict prioritaire sur une citation plus loin",
         scenario_vraie_ligne_verdict_prioritaire_sur_citation_plus_loin),
        ("texte APRÈS le marqueur sur sa ligne → toujours rejeté",
         scenario_texte_apres_marqueur_meme_ligne_toujours_rejete),
        ("1ère ligne sans marqueur → repli sur une ligne autonome ailleurs",
         scenario_premiere_ligne_sans_marqueur_repli_sur_ligne_autonome),
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

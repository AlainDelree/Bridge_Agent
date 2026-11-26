#!/usr/bin/env python3
"""Test de non-régression — issue #957 (alchess #384/#388/#390) : un message
parasite émis par un tour supplémentaire de claude après qu'une tâche en
arrière-plan (suite de tests complète, sous-agent) se soit terminée et ait
notifié CCL ne doit plus apparaître dans le rapport de clôture publié —
qu'il précède la ligne de verdict, s'intercale entre elle et le résumé
✅/❌, ou la suive, et quelle que soit sa langue. Complète #580/#581
(`_verdict_final`, qui ne traite que l'ABSENCE totale de ligne de verdict) :
ici le vrai rapport reste présent, seulement entouré de parasite —
`_isoler_rapport` (watcher.py) l'en extrait.

Vérifie :
1. Rapport sans aucun parasite → rendu à l'identique (aucune régression).
2. Notification tardive APRÈS le rapport complet (anglais, cas #388) →
   tronqué à la fin du bloc <details> réel.
3. Phrase d'attente AVANT la ligne de verdict (tour conclu à tort sur une
   attente, français, cas #384) → écartée, la ligne de verdict ouvre le
   rapport publié.
4. Deux phrases d'attente ENTRE la ligne de verdict et le résumé ✅/❌
   (anglais, cas #390 — remplace le résumé à la place attendue) → écartées,
   le résumé suit immédiatement la ligne de verdict.
5. Aucune ligne de verdict reconnue (cas #581, déjà traité ailleurs comme un
   échec) → `_isoler_rapport` ne modifie rien (repli inchangé).

Pure Python, aucun outil externe.

Exécution :  python3 tests/test_rapport_parasite_arriere_plan_957.py
Sortie      :  code 0 si tous les scénarios passent, 1 sinon.
"""

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

import watcher  # noqa: E402


def scenario_rapport_sans_parasite_inchange():
    """Rapport conforme au gabarit, sans aucun message parasite : rendu à
    l'identique — aucune régression sur le cas nominal (immense majorité des
    rapports)."""
    sortie = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "✅ Tâche terminée — correctif appliqué.\n"
        "Commits (dans /rep) : abc123 (backup) + def456 (fix)\n"
        "py_compile : OK — push : aucun\n\n"
        "<details>\n<summary>Détails complets</summary>\n\n"
        "Rien à signaler de plus.\n\n</details>\n"
    )
    assert watcher._isoler_rapport(sortie) == sortie, (
        "un rapport sans parasite ne doit jamais être modifié")
    return {"rapport_propre_inchange_ok": True}


def scenario_notification_tardive_apres_rapport_ecartee():
    """Cas #388 : notification tardive en ANGLAIS après le rapport complet
    (sous-agent/tâche d'arrière-plan terminé après coup) — doit être
    tronquée, le rapport réel (jusqu'au dernier </details>) doit rester
    intact."""
    rapport_reel = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "✅ Tâche terminée — suite de tests complète relancée deux fois.\n"
        "Commits (dans /rep) : abc123 (backup) + def456 (fix)\n"
        "py_compile : OK — push : aucun\n\n"
        "<details>\n<summary>Détails complets</summary>\n\n"
        "Deux passes complètes identiques (1947 passed, 88 skipped).\n\n"
        "</details>\n"
    )
    parasite = (
        "\nThe task is already complete — that check was part of my own "
        "workflow, and I finished it: both consecutive full-suite runs "
        "passed identically, and I went on to deliver the final report "
        "above. Nothing further is pending on that front.\n"
    )
    assert watcher._isoler_rapport(rapport_reel + parasite) == rapport_reel, (
        "la notification tardive après le rapport doit être écartée, le "
        "rapport réel conservé intact")
    return {"notification_tardive_apres_ecartee_ok": True}


def scenario_attente_avant_verdict_ecartee():
    """Cas #384 : CCL conclut un tour précédent sur une phrase d'attente, en
    FRANÇAIS, AVANT même la ligne de verdict (celle-ci n'arrive donc pas en
    toute première ligne de la sortie brute) — doit être écartée en entier,
    la ligne de verdict doit ouvrir le rapport isolé."""
    attente = "J'attends la fin de la vérification en arrière-plan avant de continuer.\n"
    rapport_reel = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "✅ Tâche terminée — correctif appliqué.\n"
        "Commits (dans /rep) : abc123 (backup) + def456 (fix)\n"
        "py_compile : OK — push : aucun\n\n"
        "<details>\n<summary>Détails complets</summary>\n\nRAS.\n\n</details>\n"
    )
    assert watcher._isoler_rapport(attente + rapport_reel) == rapport_reel, (
        "une phrase d'attente avant la ligne de verdict doit être écartée, "
        "le rapport isolé doit commencer PAR la ligne de verdict")
    return {"attente_avant_verdict_ecartee_ok": True}


def scenario_attente_entre_verdict_et_resume_ecartee():
    """Cas #390 : la ligne de verdict ouvre bien la réponse, mais DEUX
    phrases d'attente en ANGLAIS prennent la place du résumé ✅ attendu
    juste après — le vrai résultat n'arrive qu'ensuite. Les deux phrases
    doivent être écartées, le résumé ✅ doit suivre immédiatement la ligne
    de verdict dans le rapport isolé."""
    sortie = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "I'll wait here without further action until the background "
        "verification run (second full pass) completes and reports its "
        "result.\n"
        "I'll wait for the background run to complete before continuing.\n"
        "✅ Tâche terminée — vérification en arrière-plan achevée.\n"
        "Commits (dans /rep) : abc123 (backup) + def456 (fix)\n"
        "py_compile : OK — push : aucun\n\n"
        "<details>\n<summary>Détails complets</summary>\n\nRAS.\n\n</details>\n"
    )
    attendu = (
        f"{watcher.MARQUEUR_VERDICT_SUCCES}\n"
        "✅ Tâche terminée — vérification en arrière-plan achevée.\n"
        "Commits (dans /rep) : abc123 (backup) + def456 (fix)\n"
        "py_compile : OK — push : aucun\n\n"
        "<details>\n<summary>Détails complets</summary>\n\nRAS.\n\n</details>\n"
    )
    assert watcher._isoler_rapport(sortie) == attendu, (
        "les deux phrases d'attente entre le verdict et le résumé doivent "
        "être écartées, le résumé ✅ doit suivre immédiatement le verdict")
    return {"attente_entre_verdict_et_resume_ecartee_ok": True}


def scenario_aucun_verdict_reconnu_inchange():
    """Cas #581 (garde-fou déjà existant, en amont, dans
    `_executer_une_tentative`) : aucune ligne de verdict reconnue dans la
    sortie — `_isoler_rapport` ne doit RIEN modifier (repli inchangé), ce
    cas étant déjà traité ailleurs comme un échec."""
    sortie = "Simple note de suivi, hors format, sans aucun marqueur.\n"
    assert watcher._isoler_rapport(sortie) == sortie, (
        "sans aucune ligne de verdict reconnue, la sortie ne doit pas être "
        "modifiée (repli inchangé)")
    return {"aucun_verdict_inchange_ok": True}


def main():
    tests = [
        ("rapport sans parasite → inchangé",
         scenario_rapport_sans_parasite_inchange),
        ("notification tardive (anglais) après le rapport → écartée (#388)",
         scenario_notification_tardive_apres_rapport_ecartee),
        ("phrase d'attente (français) avant la ligne de verdict → écartée (#384)",
         scenario_attente_avant_verdict_ecartee),
        ("phrases d'attente (anglais) entre verdict et résumé → écartées (#390)",
         scenario_attente_entre_verdict_et_resume_ecartee),
        ("aucun verdict reconnu → inchangé (repli, cas #581)",
         scenario_aucun_verdict_reconnu_inchange),
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

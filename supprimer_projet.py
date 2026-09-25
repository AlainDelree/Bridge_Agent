#!/usr/bin/env python3
"""supprimer_projet.py — Suppression / désinstallation CCL d'un projet
Bridge_Agent (issue #587).

Diagnostic #580 : la création d'un projet (`nouveau_projet.py`, issue #98/#99)
écrit 12 traces persistantes réparties CCL/GitHub/CCW, sans qu'aucun flux ne
sache les démonter — décommissionner un projet exigeait jusqu'ici une
chirurgie manuelle sur au moins 8 cibles. Cette issue-ci couvre
volontairement UNIQUEMENT le côté CCL/local, symétrique à `nouveau_projet.py` :

    1. configs/<nom>.conf
    2. Répertoire de travail du projet (contenu + CONTEXTE.md/specs)
    3. Dépôt git local (le répertoire lui-même — jamais le dépôt GitHub distant)
    4. Tableaux §2/§7 de BRIDGE_AGENT_DOC.md (regenerer_tableaux_projets.py)

Explicitement HORS scope (décision actée dans le diagnostic #580, cf. issue
#587) : suppression du dépôt GitHub et de ses labels (geste manuel
volontaire), et tout le côté CCW (clone Windows, configs\\<nom>-ccw.conf,
service NSSM, tokens, entrée $Projets, REINSTALLATION_CCW.md §7) — suivra
dans une issue CCW dédiée.

Usage :
    python3 supprimer_projet.py <nom>              # aperçu puis confirmation interactive
    python3 supprimer_projet.py <nom> --dry-run    # liste ce qui serait supprimé, ne touche à rien
"""

import argparse
import shutil
import sys
from pathlib import Path

import regenerer_tableaux_projets
from nouveau_projet import DOSSIER_CONFIGS
from watcher import lire_conf
import etat_cases_cochees


def conf_chemin(nom: str) -> Path:
    """Chemin de configs/<nom>.conf (n'implique pas qu'il existe)."""
    return DOSSIER_CONFIGS / f"{nom}.conf"


def infos_projet(nom: str) -> dict | None:
    """Lit configs/<nom>.conf avec le même lecteur tolérant que
    regenerer_tableaux_projets.py (`lire_conf` — zéro validation, contrairement
    à `charger_config` de watcher.py) : un .conf déjà partiellement corrompu ne
    doit pas empêcher sa propre suppression. Renvoie None si le fichier
    n'existe pas (nom introuvable — rien à supprimer)."""
    chemin = conf_chemin(nom)
    if not chemin.exists():
        return None
    brut = lire_conf(chemin)
    return {"nom": nom, "depot": brut.get("DEPOT", ""),
            "rep_travail": brut.get("REP_TRAVAIL", ""), "conf": chemin}


def _rep_travail_path(infos: dict) -> Path | None:
    rep = infos.get("rep_travail") or ""
    return Path(rep).expanduser() if rep else None


def _lister_repertoire(rep_path: Path, limite: int = 20) -> list[str]:
    """Chemins relatifs triés du contenu de rep_path (purement informatif,
    pour l'aperçu à blanc et le compte-rendu — jamais utilisé pour décider
    quoi que ce soit)."""
    if not rep_path.exists():
        return []
    return sorted(str(p.relative_to(rep_path)) for p in rep_path.rglob("*"))[:limite]


def previsualiser_suppression(nom: str) -> dict:
    """Mode à blanc (dry-run) : décrit ce qui SERAIT supprimé sans toucher au
    disque ni à BRIDGE_AGENT_DOC.md. Renvoie {existe, nom, depot, conf,
    rep_travail, rep_existe, git_local, nb_fichiers, apercu_fichiers}."""
    infos = infos_projet(nom)
    if infos is None:
        return {"existe": False, "nom": nom}

    rep_path = _rep_travail_path(infos)
    rep_existe = bool(rep_path and rep_path.exists())
    git_local = bool(rep_existe and (rep_path / ".git").exists())
    apercu = _lister_repertoire(rep_path) if rep_existe else []
    nb_total = sum(1 for _ in rep_path.rglob("*")) if rep_existe else 0

    return {"existe": True, "nom": nom, "depot": infos["depot"],
            "conf": str(infos["conf"]),
            "rep_travail": str(rep_path) if rep_path else "",
            "rep_existe": rep_existe, "git_local": git_local,
            "nb_fichiers": nb_total, "apercu_fichiers": apercu}


def _supprimer_repertoire(rep_path: Path | None) -> dict:
    """Supprime le répertoire de travail EN ENTIER — contenu, CONTEXTE.md/
    specs, ET dépôt git local puisque `.git` vit toujours DANS ce répertoire
    (voir `initialiser_git()` de nouveau_projet.py) : cibles 2 et 3 de
    l'issue #587, démontées par la même opération de disque. Idempotent : un
    répertoire déjà absent n'est pas une erreur (nettoyage manuel partiel
    déjà fait)."""
    if rep_path is None or not rep_path.exists():
        chemin = str(rep_path) if rep_path else "(REP_TRAVAIL non défini)"
        return {"ok": True, "existait": False,
                "detail": f"{chemin} — déjà absent, rien à faire."}
    try:
        shutil.rmtree(rep_path)
    except OSError as exc:
        return {"ok": False, "existait": True,
                "detail": f"échec de la suppression de {rep_path} : {exc}"}
    return {"ok": True, "existait": True,
            "detail": f"{rep_path} supprimé (contenu + dépôt git local)."}


def _supprimer_conf(chemin: Path) -> dict:
    if not chemin.exists():
        return {"ok": True, "detail": f"{chemin.name} déjà absent."}
    try:
        chemin.unlink()
    except OSError as exc:
        return {"ok": False, "detail": f"échec de la suppression de {chemin.name} : {exc}"}
    return {"ok": True, "detail": f"{chemin.name} supprimé."}


def mettre_a_jour_doc() -> dict:
    """Même mécanisme que nouveau_projet.mettre_a_jour_doc() (issue #571) :
    à cet instant le .conf du projet est déjà retiré du disque, la
    régénération le fait donc disparaître de §2/§7. Renvoie {existe, ok,
    modifie, erreur}."""
    resultat = regenerer_tableaux_projets.regenerer()
    ok = resultat["existe"] and resultat["erreur"] is None
    return {"existe": resultat["existe"], "ok": ok,
            "modifie": resultat["modifie"], "erreur": resultat["erreur"]}


def supprimer_projet(nom: str, dry_run: bool = False) -> dict:
    """Orchestrateur symétrique à nouveau_projet.creer_projet() : démonte les
    4 cibles CCL/locales de l'issue #587 dans un ordre sûr, en s'arrêtant dès
    qu'une étape échoue plutôt que de continuer aveuglément.

    Ordre choisi — inverse de la création, volontairement : le répertoire de
    travail (contenu + dépôt git local) est retiré EN PREMIER, tant que
    configs/<nom>.conf existe encore pour attester du projet. Si cette étape
    échoue (droits, disque), le .conf est conservé : le projet reste visible/
    enregistré plutôt que de laisser un configs/<nom>.conf sans aucune donnée
    derrière lui — l'inverse (supprimer le .conf d'abord) risquerait un
    dossier orphelin sur disque sans plus aucune trace de son existence. La
    régénération de BRIDGE_AGENT_DOC.md (qui relit configs/*.conf) vient donc
    en dernier, une fois le .conf effectivement retiré.

    Renvoie {succes, nom, dry_run, depot, etapes:[{etape, ok, detail}], erreur}."""
    nom = (nom or "").strip().lower()
    if not nom:
        return {"succes": False, "nom": nom, "dry_run": dry_run, "etapes": [],
                "erreur": "Un nom de projet est requis."}

    infos = infos_projet(nom)
    if infos is None:
        return {"succes": False, "nom": nom, "dry_run": dry_run, "etapes": [],
                "erreur": f"configs/{nom}.conf introuvable — rien à supprimer."}

    if dry_run:
        apercu = previsualiser_suppression(nom)
        etapes = [
            {"etape": "Répertoire de travail (contenu + dépôt git local)",
             "ok": True,
             "detail": (f"{apercu['nb_fichiers']} élément(s) sous "
                        f"{apercu['rep_travail']} seraient supprimés"
                        + (" (dépôt git local inclus)" if apercu["git_local"] else "")
                        + "." if apercu["rep_existe"]
                        else f"{apercu['rep_travail'] or '(REP_TRAVAIL non défini)'} — déjà absent.")},
            {"etape": "Fichier .conf", "ok": True,
             "detail": f"{apercu['conf']} serait supprimé."},
            {"etape": "Documentation", "ok": True,
             "detail": "§2/§7 de BRIDGE_AGENT_DOC.md seraient régénérés depuis "
                       "configs/*.conf, sans ce projet."},
            {"etape": "Cases cochées (état serveur, issue #629)", "ok": True,
             "detail": (f"{len(etat_cases_cochees.lire_cases_cochees(nom))} "
                        "case(s) cochée(s) seraient retirées.")},
        ]
        return {"succes": True, "nom": nom, "dry_run": True,
                "depot": infos["depot"], "etapes": etapes, "erreur": None}

    etapes = []

    # 1. Répertoire de travail (contenu + dépôt git local) — voir l'ordre
    #    choisi dans la docstring ci-dessus.
    rep_path = _rep_travail_path(infos)
    res_rep = _supprimer_repertoire(rep_path)
    etapes.append({"etape": "Répertoire de travail (contenu + dépôt git local)",
                   "ok": res_rep["ok"], "detail": res_rep["detail"]})
    if not res_rep["ok"]:
        return {"succes": False, "nom": nom, "dry_run": False,
                "depot": infos["depot"], "etapes": etapes,
                "erreur": "Échec à l'étape « Répertoire de travail » — arrêt : "
                          "configs/*.conf et BRIDGE_AGENT_DOC.md non touchés."}

    # 2. configs/<nom>.conf.
    res_conf = _supprimer_conf(infos["conf"])
    etapes.append({"etape": "Fichier .conf", "ok": res_conf["ok"],
                   "detail": res_conf["detail"]})
    if not res_conf["ok"]:
        return {"succes": False, "nom": nom, "dry_run": False,
                "depot": infos["depot"], "etapes": etapes,
                "erreur": "Échec à l'étape « Fichier .conf » — arrêt : "
                          "BRIDGE_AGENT_DOC.md non régénéré."}

    # 3. Documentation (§2/§7) — en dernier, une fois le .conf réellement
    #    retiré du disque (sans quoi le projet réapparaîtrait dans §2/§7).
    doc = mettre_a_jour_doc()
    if not doc["existe"]:
        etapes.append({"etape": "Documentation", "ok": False,
                       "detail": "BRIDGE_AGENT_DOC.md introuvable — non mis à jour."})
    elif doc["erreur"]:
        etapes.append({"etape": "Documentation", "ok": False, "detail": doc["erreur"]})
    else:
        etapes.append({"etape": "Documentation", "ok": True,
                       "detail": "§2/§7/date régénérés (projet retiré)."
                                 if doc["modifie"] else "déjà à jour."})

    # 4. Cases cochées côté serveur (issue #629) — nettoyage purement local,
    #    sans lien avec GitHub ni la doc ; un échec ici ne remet pas en
    #    cause les étapes précédentes déjà réalisées avec succès.
    ok_cases, erreur_cases = etat_cases_cochees.supprimer_projet(nom)
    etapes.append({"etape": "Cases cochées (état serveur, issue #629)",
                   "ok": ok_cases,
                   "detail": "coche(s) retirée(s)." if ok_cases else erreur_cases})

    return {"succes": True, "nom": nom, "dry_run": False,
            "depot": infos["depot"], "etapes": etapes, "erreur": None}


# ─── Programme principal (CLI interactif, même esprit que nouveau_projet.py) ──

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Supprime un projet Bridge_Agent côté CCL/local (issue #587).")
    parser.add_argument("nom", help="Nom du projet (configs/<nom>.conf)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Liste ce qui serait supprimé, sans rien toucher.")
    parser.add_argument("--oui", action="store_true",
                        help="Ne pas demander confirmation (usage scripté).")
    args = parser.parse_args()
    nom = args.nom.strip().lower()

    apercu = previsualiser_suppression(nom)
    if not apercu["existe"]:
        print(f"❌ configs/{nom}.conf introuvable — rien à supprimer.")
        return 1

    print(f"\033[1m═══ Suppression du projet « {nom} » ═══\033[0m")
    print(f"   Dépôt GitHub (conservé, non touché) : {apercu['depot']}")
    print(f"   Répertoire de travail : {apercu['rep_travail']}"
          + (f" ({apercu['nb_fichiers']} élément(s))" if apercu["rep_existe"] else " (déjà absent)"))
    print(f"   Dépôt git local       : {'présent, sera supprimé' if apercu['git_local'] else 'absent'}")
    print(f"   Fichier configs/{nom}.conf : sera supprimé")
    print("   BRIDGE_AGENT_DOC.md (§2/§7) : sera régénéré")
    print(f"   Cases cochées (état serveur, issue #629) : "
          f"{len(etat_cases_cochees.lire_cases_cochees(nom))} seront retirées")

    if args.dry_run:
        print("\n(dry-run — rien n'a été modifié)")
        return 0

    if not args.oui:
        rep = input(f"\n   Taper « {nom} » pour confirmer la suppression définitive : ").strip()
        if rep != nom:
            print("   Abandon : confirmation non fournie.")
            return 1

    resultat = supprimer_projet(nom, dry_run=False)
    print()
    for etape in resultat["etapes"]:
        marque = "✓" if etape["ok"] else "❌"
        print(f"   {marque} {etape['etape']} — {etape['detail']}")

    if resultat["succes"]:
        print(f"\n✅ Projet « {nom} » supprimé côté CCL/local.")
        print("   Reste à faire à la main : dépôt GitHub + labels (hors scope, "
              "cf. issue #587), commit puis push des changements locaux "
              "(configs/, doc).")
        return 0
    print(f"\n❌ {resultat['erreur']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""nouveau_projet.py — Création / installation d'un projet Bridge_Agent.

Ajouter un projet au bridge était jusqu'ici une procédure manuelle, non
documentée et sujette à l'oubli (cf. issue #90 : labels manquants sur le dépôt
Ecole → échec silencieux de création d'issue). Ce script interactif couvre les
deux cas — création d'un dépôt neuf ET installation dans un dépôt existant — et
met à jour BRIDGE_AGENT_DOC.md automatiquement.

Usage :
    python3 nouveau_projet.py

Zéro dépendance externe (stdlib + la commande `gh`). Aucun `git push` n'est
effectué : Alain pousse lui-même après vérification.
"""

import re
import subprocess
import sys
import unicodedata
from datetime import date
from pathlib import Path

# Racine du dépôt Bridge_Agent : ce script vit à la racine, à côté de watcher.py
# et du dossier configs/.
RACINE = Path(__file__).resolve().parent
DOSSIER_CONFIGS = RACINE / "configs"
DOC = RACINE / "BRIDGE_AGENT_DOC.md"

# Les 9 labels requis par le watcher (§4 de la doc). color = hex sans '#'.
# On les recrée à l'identique sur chaque nouveau dépôt cible ; sans eux, le
# watcher ne voit pas les issues (for-linux) et le mode écriture reste inerte.
LABELS = [
    ("for-linux",   "0e8a16", "Requis — le watcher ne voit que ces issues"),
    ("for-windows", "0e8a16", "Watcher Windows (CCW) — même principe que for-linux"),
    ("bridge",      "1d76db", "Marque l'issue comme tâche bridge (traçabilité)"),
    ("mode_write",  "d93f0b", "ARME le mode écriture — CCL peut modifier des fichiers"),
    ("needs-human", "b60205", "Posé après 3 échecs — stoppe le retraitement auto"),
    ("done",        "0e8a16", "Posé automatiquement au succès"),
    ("notif_pc",    "fbca04", "Ajoute une notification bureau (notify-send)"),
    ("notif_gsm",   "fbca04", "Ajoute une notification push (ntfy)"),
    ("notif_tous",  "fbca04", "notify-send + ntfy"),
]

# Palette fixe de couleurs d'accent proposées à la création d'un projet (issue
# #121). Une dizaine de teintes bien distinctes, incluant les 5 déjà en usage
# (cohérence visuelle avec l'existant : voir COULEURS_PROJET dans app.js). Une
# couleur est attribuée dès la création et écrite dans le .conf (champ COULEUR) ;
# celles déjà prises par un projet existant sont exclues de la proposition. Hex
# #RRGGBB, écrits en MAJUSCULES mais comparés sans tenir compte de la casse.
PALETTE_COULEURS = [
    "#185FA5",  # bleu       (bridge_agent)
    "#3B6D11",  # vert       (alchess)
    "#BA7517",  # orange     (ff_galerie)
    "#0E8A82",  # turquoise  (scrabble)
    "#6B3FA0",  # violet     (ecole)
    "#B0323A",  # rouge brique
    "#A2348A",  # magenta
    "#3B45A0",  # indigo
    "#7A4E2D",  # brun
    "#556070",  # gris ardoise
]

# Topic ntfy partagé par tous les projets existants (voir configs/*.conf).
# Proposé par défaut ; l'utilisateur peut le changer pour un topic dédié.
TOPIC_NTFY_DEFAUT = "hippocampe-ff-galerie-xyz123"
SCRIPT_BIP_DEFAUT = "/home/alain/NicLink/bip.py"

# Propriétaire GitHub par défaut pour le dépôt proposé (owner/Nom).
OWNER_DEFAUT = "AlainDelree"

# Fichiers Specs MVC (§15) créés en plus de CONTEXTE.md quand l'option est active.
FICHIERS_SPECS = ("CONTEXTE_VUE.md", "CONTEXTE_METIER.md", "CONTEXTE_PERSISTANCE.md")

MOIS_FR = ["", "janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"]


# ─── Entrées / sorties interactives ───────────────────────────────────────────

def titre(txt: str) -> None:
    print(f"\n\033[1m{txt}\033[0m")


def demander(question: str, defaut: str = "") -> str:
    """Pose une question ; renvoie la saisie ou le défaut si l'utilisateur
    valide à vide. Le défaut est affiché entre crochets."""
    suffixe = f" [{defaut}]" if defaut else ""
    try:
        reponse = input(f"  {question}{suffixe} : ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nInterrompu.")
        sys.exit(1)
    return reponse or defaut


def demander_oui_non(question: str, defaut: bool = False) -> bool:
    d = "O/n" if defaut else "o/N"
    rep = demander(f"{question} ({d})").lower()
    if not rep:
        return defaut
    return rep in ("o", "oui", "y", "yes")


def gh(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Lance `gh` avec les arguments donnés. capture=False laisse gh écrire
    directement sur le terminal (utile pour repo create)."""
    return subprocess.run(
        ["gh", *args],
        capture_output=capture,
        text=True,
    )


# ─── Étapes ───────────────────────────────────────────────────────────────────

def valider_nom(nom: str) -> bool:
    """Cohérent avec bridge_agent, alchess, ff_galerie : minuscules, chiffres,
    underscore ; commence par une lettre."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", nom))


# ─── Logique réutilisable (CLI + route Flask) ────────────────────────────────
# Ces fonctions n'affichent rien et ne lisent aucune saisie : elles concentrent
# les actions (gh, écriture de fichiers) pour être appelables aussi bien depuis
# le script interactif que depuis app/nouveau_projet.py. Le comportement
# idempotent (labels, contexte, doc) est identique dans les deux cas.

def conf_existe(nom: str) -> bool:
    """True si configs/<nom>.conf existe déjà (nom déjà pris)."""
    return (DOSSIER_CONFIGS / f"{nom}.conf").exists()


def couleurs_utilisees() -> set[str]:
    """Ensemble des couleurs (hex minuscules) déjà attribuées à un projet
    existant, lues depuis le champ COULEUR de chaque configs/*.conf. Lecture
    minimale et tolérante (même esprit zéro-dépendance que le reste du script) :
    un .conf illisible est simplement ignoré."""
    prises: set[str] = set()
    for chemin in DOSSIER_CONFIGS.glob("*.conf"):
        try:
            for brut in chemin.read_text(encoding="utf-8").splitlines():
                ligne = brut.strip()
                if not ligne or ligne.startswith("#"):
                    continue
                cle, sep, valeur = ligne.partition("=")
                if sep and cle.strip().upper() == "COULEUR":
                    v = valeur.strip().lower()
                    if v:
                        prises.add(v)
        except OSError:
            continue
    return prises


def couleurs_disponibles() -> list[str]:
    """Couleurs de PALETTE_COULEURS non encore attribuées à un projet existant,
    dans l'ordre de la palette. Sert à la fois au modal (pastilles proposées) et
    à creer_projet (repli si aucune couleur n'est choisie)."""
    prises = couleurs_utilisees()
    return [c for c in PALETTE_COULEURS if c.lower() not in prises]


def normaliser_couleur(couleur: str) -> str:
    """Ramène une couleur choisie à une valeur sûre : la couleur telle qu'écrite
    dans la palette si elle est encore disponible (comparaison insensible à la
    casse), sinon la première couleur libre, sinon '' (palette épuisée → repli
    map fixe/hash côté frontend)."""
    dispo = couleurs_disponibles()
    choisie = (couleur or "").strip().lower()
    if choisie:
        for c in dispo:
            if c.lower() == choisie:
                return c
    return dispo[0] if dispo else ""


def depot_defaut(nom: str) -> str:
    """Dépôt GitHub proposé par défaut : owner + nom capitalisé."""
    return f"{OWNER_DEFAUT}/{nom.capitalize()}"


def rep_defaut(nom: str) -> str:
    """Répertoire de travail CCL proposé par défaut."""
    return f"/home/alain/{nom.capitalize()}"


def depot_existe(depot: str) -> bool:
    """True si le dépôt GitHub cible existe déjà (gh repo view)."""
    return gh("repo", "view", depot).returncode == 0


def creer_depot(depot: str, nom: str) -> tuple[bool, str]:
    """Crée le dépôt public. Renvoie (succès, message d'erreur éventuel)."""
    res = gh("repo", "create", depot, "--public",
             "--description", f"Projet {nom} — piloté via Bridge_Agent")
    return res.returncode == 0, res.stderr.strip()


def ecrire_conf(nom: str, depot: str, rep: str, perimetre: str,
                topic: str = TOPIC_NTFY_DEFAUT,
                script_bip: str = SCRIPT_BIP_DEFAUT,
                couleur: str = "") -> Path:
    """Génère configs/<nom>.conf depuis le gabarit. Renvoie le chemin écrit."""
    chemin = DOSSIER_CONFIGS / f"{nom}.conf"
    contenu = GABARIT_CONF.format(
        nom=nom,
        depot=depot,
        rep_travail=rep,
        perimetre=perimetre,
        topic_ntfy=topic,
        script_bip=script_bip,
        couleur=couleur,
    )
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def creer_labels(depot: str) -> list[tuple[str, str, str]]:
    """Crée les labels manquants sur le dépôt cible (idempotent : les présents
    sont laissés intacts). Renvoie une liste ordonnée de (label, statut, detail)
    où statut ∈ {"deja", "cree", "echec"}."""
    res = gh("label", "list", "--repo", depot, "--limit", "200")
    existants = set()
    if res.returncode == 0:
        for ligne in res.stdout.splitlines():
            if ligne.strip():
                existants.add(ligne.split("\t")[0].strip().lower())

    resultats = []
    for nom_label, couleur, description in LABELS:
        if nom_label.lower() in existants:
            resultats.append((nom_label, "deja", ""))
            continue
        r = gh("label", "create", nom_label, "--repo", depot,
               "--color", couleur, "--description", description)
        if r.returncode == 0:
            resultats.append((nom_label, "cree", ""))
        else:
            resultats.append((nom_label, "echec", r.stderr.strip()))
    return resultats


def _ecrire_fichiers_contexte(rep_path: Path,
                              avec_specs: bool) -> tuple[list[Path], list[Path]]:
    """Crée CONTEXTE.md (et les 3 fichiers Specs MVC si demandé) dans un
    répertoire supposé existant. Renvoie (créés, déjà présents). Idempotent :
    les fichiers déjà là sont laissés intacts."""
    crees, existants = [], []
    fichiers = ["CONTEXTE.md"]
    if avec_specs:
        fichiers += list(FICHIERS_SPECS)
    for nom_fic in fichiers:
        f = rep_path / nom_fic
        if f.exists():
            existants.append(f)
        else:
            f.write_text("", encoding="utf-8")
            crees.append(f)
    return crees, existants


def creer_fichiers_contexte(rep: str, avec_specs: bool) -> dict:
    """Version non interactive : crée le répertoire de travail s'il manque puis
    les fichiers contexte. Renvoie {crees, existants, rep_cree}."""
    rep_path = Path(rep).expanduser()
    rep_cree = False
    if not rep_path.exists():
        rep_path.mkdir(parents=True, exist_ok=True)
        rep_cree = True
    crees, existants = _ecrire_fichiers_contexte(rep_path, avec_specs)
    return {"crees": crees, "existants": existants, "rep_cree": rep_cree}


def mettre_a_jour_doc(nom: str, depot: str, rep: str, perimetre: str) -> dict:
    """Insère le projet dans les tableaux §2 et §7 de BRIDGE_AGENT_DOC.md et
    rafraîchit la date en bas. Renvoie {existe, ok2, ok7, ok_date}."""
    if not DOC.exists():
        return {"existe": False, "ok2": False, "ok7": False, "ok_date": False}

    lignes = DOC.read_text(encoding="utf-8").splitlines()

    ligne_2 = (f"| `{nom}` | {depot} | {_afficher_rep(rep)} | (conf local) |")
    ligne_7 = f"| `{nom}` | {perimetre} |"

    ok2 = _inserer_ligne_tableau(lignes, "## 2. Projets actifs", ligne_2)
    ok7 = _inserer_ligne_tableau(lignes, "## 7. Périmètre par projet", ligne_7)

    aujourd_hui = date.today()
    date_fr = f"{aujourd_hui.day} {MOIS_FR[aujourd_hui.month]} {aujourd_hui.year}"
    ok_date = False
    for i, ligne in enumerate(lignes):
        if ligne.startswith("*Dernière mise à jour :"):
            lignes[i] = re.sub(
                r"(\*Dernière mise à jour : )[^—]*( —)",
                rf"\g<1>{date_fr}\g<2>",
                ligne,
            )
            ok_date = True
            break

    DOC.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    return {"existe": True, "ok2": ok2, "ok7": ok7, "ok_date": ok_date}


def creer_projet(nom: str, depot: str = "", rep: str = "", perimetre: str = "",
                 topic: str = "", script_bip: str = "", avec_specs: bool = False,
                 creer_depot_si_absent: bool = True, couleur: str = "") -> dict:
    """Orchestrateur non interactif appelé par la route Flask. Enchaîne les
    mêmes étapes que le script CLI (dépôt, .conf, labels, contexte, doc) et
    renvoie un compte-rendu structuré : {succes, nom, depot, rep, perimetre,
    depot_existait, etapes:[{etape, ok, detail}], erreur}."""
    nom = (nom or "").strip().lower()
    if not nom:
        return {"succes": False, "erreur": "Un nom de projet est requis.", "etapes": []}
    if not valider_nom(nom):
        return {"succes": False, "etapes": [],
                "erreur": "Format de nom invalide (minuscules, chiffres, "
                          "underscore ; commence par une lettre)."}
    if conf_existe(nom):
        return {"succes": False, "etapes": [],
                "erreur": f"configs/{nom}.conf existe déjà — choisir un autre nom "
                          "ou supprimer l'ancien d'abord."}

    depot = (depot or "").strip() or depot_defaut(nom)
    rep = (rep or "").strip() or rep_defaut(nom)
    perimetre = (perimetre or "").strip() or rep
    topic = (topic or "").strip() or TOPIC_NTFY_DEFAUT
    script_bip = (script_bip or "").strip() or SCRIPT_BIP_DEFAUT
    # Couleur d'accent : la couleur choisie si elle est encore libre, sinon la
    # première disponible, sinon '' (palette épuisée → repli map fixe/hash côté
    # frontend). Exclut au passage les couleurs déjà prises (issue #121).
    couleur = normaliser_couleur(couleur)

    etapes = []

    # 1. Dépôt GitHub — installation si existant, création sinon.
    if depot_existe(depot):
        depot_existait = True
        etapes.append({"etape": "Dépôt GitHub", "ok": True,
                       "detail": f"{depot} existe déjà → installation dessus "
                                 "(pas de recréation)."})
    else:
        if not creer_depot_si_absent:
            return {"succes": False, "etapes": etapes, "depot": depot,
                    "erreur": f"Le dépôt {depot} n'existe pas. Cochez la création "
                              "du dépôt pour continuer."}
        ok, err = creer_depot(depot, nom)
        depot_existait = False
        if not ok:
            etapes.append({"etape": "Dépôt GitHub", "ok": False,
                           "detail": f"Échec de la création : {err}"})
            return {"succes": False, "etapes": etapes, "depot": depot,
                    "erreur": f"Impossible de créer {depot} : {err}"}
        etapes.append({"etape": "Dépôt GitHub", "ok": True,
                       "detail": f"{depot} créé (public)."})

    # 2. Fichier configs/<nom>.conf.
    ecrire_conf(nom, depot, rep, perimetre, topic, script_bip, couleur)
    detail_conf = f"configs/{nom}.conf créé (à partir du gabarit)."
    if couleur:
        detail_conf += f" Couleur d'accent : {couleur}."
    etapes.append({"etape": "Fichier .conf", "ok": True, "detail": detail_conf})

    # 3. Labels GitHub requis (idempotent).
    resultats = creer_labels(depot)
    nb_crees = sum(1 for _, s, _ in resultats if s == "cree")
    nb_deja = sum(1 for _, s, _ in resultats if s == "deja")
    echecs = [(n, e) for n, s, e in resultats if s == "echec"]
    detail_labels = f"{nb_crees} nouveau(x), {nb_deja} déjà existant(s)"
    if echecs:
        detail_labels += " ; échecs : " + ", ".join(f"{n} ({e})" for n, e in echecs)
    etapes.append({"etape": "Labels GitHub", "ok": not echecs,
                   "detail": detail_labels})

    # 4. Fichier(s) de contexte (crée le répertoire de travail au besoin).
    ctx = creer_fichiers_contexte(rep, avec_specs)
    noms_crees = [f.name for f in ctx["crees"]]
    if noms_crees:
        detail_ctx = ", ".join(noms_crees) + " créé(s)"
    else:
        detail_ctx = "tous déjà présents"
    if ctx["rep_cree"]:
        detail_ctx = f"répertoire {rep} créé ; " + detail_ctx
    etapes.append({"etape": "Fichiers contexte", "ok": True, "detail": detail_ctx})

    # 5. Mise à jour de BRIDGE_AGENT_DOC.md (§2, §7, date).
    doc = mettre_a_jour_doc(nom, depot, rep, perimetre)
    if not doc["existe"]:
        etapes.append({"etape": "Documentation", "ok": False,
                       "detail": "BRIDGE_AGENT_DOC.md introuvable — non mis à jour."})
    else:
        ok_doc = doc["ok2"] and doc["ok7"]
        etapes.append({"etape": "Documentation", "ok": ok_doc,
                       "detail": "§2/§7/date mis à jour" if ok_doc
                       else "sections §2/§7 non trouvées — à vérifier"})

    return {"succes": True, "nom": nom, "depot": depot, "rep": rep,
            "perimetre": perimetre, "depot_existait": depot_existait,
            "couleur": couleur, "etapes": etapes, "erreur": None}


def etape_nom() -> str:
    titre("1. Nom du projet")
    print("   Identifiant court, minuscules + underscore (ex. bridge_agent, alchess).")
    while True:
        nom = demander("Nom du projet").lower()
        if not nom:
            print("   ⚠️  Un nom est requis.")
            continue
        if not valider_nom(nom):
            print("   ⚠️  Format invalide (minuscules, chiffres, underscore ; "
                  "commence par une lettre).")
            continue
        conf = DOSSIER_CONFIGS / f"{nom}.conf"
        if conf.exists():
            print(f"   ⚠️  configs/{nom}.conf existe déjà — choisir un autre nom "
                  "ou supprimer l'ancien d'abord.")
            continue
        return nom


def etape_depot(nom: str) -> tuple[str, bool]:
    """Renvoie (depot, existait_deja). Crée le dépôt s'il n'existe pas et que
    l'utilisateur confirme."""
    titre("2. Dépôt GitHub cible")
    # Proposition par défaut : owner du dépôt courant + nom capitalisé.
    depot = demander("Dépôt GitHub (owner/nom)", depot_defaut(nom))

    if depot_existe(depot):
        print(f"   ✓ Le dépôt {depot} existe déjà → installation dessus "
              "(pas de recréation).")
        return depot, True

    print(f"   Le dépôt {depot} n'existe pas encore.")
    if not demander_oui_non(f"Créer {depot} (public)", defaut=True):
        print("   Abandon : impossible de continuer sans dépôt cible.")
        sys.exit(1)

    print(f"   Création de {depot}…")
    ok, err = creer_depot(depot, nom)
    if not ok:
        print(f"   ❌ Échec de la création : {err}")
        sys.exit(1)
    print("   ✓ Dépôt créé.")
    return depot, False


def etape_repertoire(nom: str) -> tuple[str, str]:
    """Renvoie (rep_travail, perimetre)."""
    titre("3. Répertoire de travail CCL et périmètre")
    rep = demander("Répertoire de travail CCL", rep_defaut(nom))
    perimetre = demander("Périmètre autorisé (dossiers, séparés par des virgules)", rep)
    return rep, perimetre


def etape_conf(nom: str, depot: str, rep: str, perimetre: str) -> Path:
    titre("4. Fichier configs/<nom>.conf")
    topic = demander("Topic ntfy", TOPIC_NTFY_DEFAUT)
    # Couleur d'accent : proposer la première libre par défaut, laisser choisir
    # parmi les couleurs non encore utilisées (issue #121).
    couleur = etape_couleur()
    chemin = DOSSIER_CONFIGS / f"{nom}.conf"
    contenu = GABARIT_CONF.format(
        nom=nom,
        depot=depot,
        rep_travail=rep,
        perimetre=perimetre,
        topic_ntfy=topic,
        script_bip=SCRIPT_BIP_DEFAUT,
        couleur=couleur,
    )
    chemin.write_text(contenu, encoding="utf-8")
    print(f"   ✓ {chemin.relative_to(RACINE)} créé (à partir du gabarit).")
    if couleur:
        print(f"   ✓ Couleur d'accent : {couleur}.")
    return chemin


def etape_couleur() -> str:
    """Propose les couleurs de la palette non encore utilisées et renvoie le hex
    choisi (ou la première libre si validation à vide). '' si palette épuisée."""
    dispo = couleurs_disponibles()
    if not dispo:
        print("   • Palette épuisée (toutes les couleurs sont prises) — "
              "couleur auto (repli map fixe/hash côté interface).")
        return ""
    print("   Couleurs disponibles (non encore utilisées) :")
    for i, c in enumerate(dispo, 1):
        print(f"     {i}. {c}")
    rep = demander(f"Numéro de couleur (1-{len(dispo)})", "1")
    if rep.isdigit() and 1 <= int(rep) <= len(dispo):
        return dispo[int(rep) - 1]
    return dispo[0]


def etape_labels(depot: str) -> list[str]:
    """Crée les labels manquants sur le dépôt cible. Renvoie la liste des
    labels effectivement créés (les déjà présents sont laissés intacts)."""
    titre("5. Labels GitHub requis")
    res = gh("label", "list", "--repo", depot, "--limit", "200")
    existants = set()
    if res.returncode == 0:
        for ligne in res.stdout.splitlines():
            if ligne.strip():
                existants.add(ligne.split("\t")[0].strip().lower())
    else:
        print(f"   ⚠️  Impossible de lister les labels ({res.stderr.strip()}) — "
              "tentative de création quand même.")

    crees = []
    for nom_label, couleur, description in LABELS:
        if nom_label.lower() in existants:
            print(f"   • {nom_label} : déjà présent, laissé intact.")
            continue
        r = gh("label", "create", nom_label, "--repo", depot,
               "--color", couleur, "--description", description)
        if r.returncode == 0:
            print(f"   ✓ {nom_label} : créé.")
            crees.append(nom_label)
        else:
            print(f"   ❌ {nom_label} : échec ({r.stderr.strip()}).")
    return crees


def etape_contexte(rep: str, avec_specs: bool) -> list[Path]:
    """Crée CONTEXTE.md (et les 3 fichiers Specs MVC si demandé) dans le
    répertoire de travail du projet. Renvoie les fichiers créés."""
    titre("6. Fichier(s) de contexte")
    rep_path = Path(rep).expanduser()
    if not rep_path.exists():
        if demander_oui_non(f"Le répertoire {rep_path} n'existe pas. Le créer",
                            defaut=True):
            rep_path.mkdir(parents=True, exist_ok=True)
        else:
            print("   ⚠️  Contexte non créé (répertoire absent). À faire à la main.")
            return []

    crees = []
    contexte = rep_path / "CONTEXTE.md"
    if contexte.exists():
        print(f"   • {contexte} existe déjà, laissé intact.")
    else:
        contexte.write_text("", encoding="utf-8")
        print(f"   ✓ {contexte} créé (vide).")
        crees.append(contexte)

    if avec_specs:
        for nom_fic in ("CONTEXTE_VUE.md", "CONTEXTE_METIER.md",
                        "CONTEXTE_PERSISTANCE.md"):
            f = rep_path / nom_fic
            if f.exists():
                print(f"   • {f} existe déjà, laissé intact.")
            else:
                f.write_text("", encoding="utf-8")
                print(f"   ✓ {f} créé (vide).")
                crees.append(f)
    return crees


# ─── Mise à jour de la documentation (§2, §7, date) ───────────────────────────

def _inserer_ligne_tableau(lignes: list[str], titre_section: str,
                           nouvelle_ligne: str) -> bool:
    """Insère `nouvelle_ligne` après la dernière ligne de tableau (commençant
    par '|') de la section identifiée par `titre_section`. Renvoie True si
    l'insertion a eu lieu."""
    # Localiser le titre de section (ex. "## 2. Projets actifs").
    debut = None
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith(titre_section):
            debut = i
            break
    if debut is None:
        return False

    # Parcourir jusqu'au tableau, puis mémoriser la dernière ligne '|'.
    derniere_ligne_tableau = None
    for i in range(debut + 1, len(lignes)):
        s = lignes[i].strip()
        if s.startswith("## "):        # section suivante atteinte
            break
        if s.startswith("|"):
            derniere_ligne_tableau = i
    if derniere_ligne_tableau is None:
        return False

    lignes.insert(derniere_ligne_tableau + 1, nouvelle_ligne)
    return True


def _afficher_rep(rep: str) -> str:
    """Affiche le répertoire avec le raccourci ~ comme dans la doc existante."""
    home = str(Path.home())
    return rep.replace(home, "~", 1) if rep.startswith(home) else rep


def etape_doc(nom: str, depot: str, rep: str, perimetre: str) -> bool:
    titre("8. Mise à jour de BRIDGE_AGENT_DOC.md")
    if not DOC.exists():
        print(f"   ⚠️  {DOC.name} introuvable — mise à jour ignorée.")
        return False

    lignes = DOC.read_text(encoding="utf-8").splitlines()

    ligne_2 = (f"| `{nom}` | {depot} | {_afficher_rep(rep)} | (conf local) |")
    ligne_7 = f"| `{nom}` | {perimetre} |"

    ok2 = _inserer_ligne_tableau(lignes, "## 2. Projets actifs", ligne_2)
    # §7 vient après §2 : on réinsère sur la liste déjà modifiée.
    ok7 = _inserer_ligne_tableau(lignes, "## 7. Périmètre par projet", ligne_7)

    # Ligne de date en bas : "*Dernière mise à jour : JJ mois AAAA — …*"
    aujourd_hui = date.today()
    date_fr = f"{aujourd_hui.day} {MOIS_FR[aujourd_hui.month]} {aujourd_hui.year}"
    ok_date = False
    for i, ligne in enumerate(lignes):
        if ligne.startswith("*Dernière mise à jour :"):
            lignes[i] = re.sub(
                r"(\*Dernière mise à jour : )[^—]*( —)",
                rf"\g<1>{date_fr}\g<2>",
                ligne,
            )
            ok_date = True
            break

    DOC.write_text("\n".join(lignes) + "\n", encoding="utf-8")
    print(f"   §2 (Projets actifs)      : {'✓ ligne ajoutée' if ok2 else '⚠️ non trouvée'}")
    print(f"   §7 (Périmètre par projet): {'✓ ligne ajoutée' if ok7 else '⚠️ non trouvée'}")
    print(f"   Date en bas              : {'✓ mise à jour' if ok_date else '⚠️ non trouvée'}")
    return ok2 and ok7


# ─── Gabarit du .conf ─────────────────────────────────────────────────────────

GABARIT_CONF = """# configs/{nom}.conf
# Config du watcher pour le projet {nom}.
# Généré par nouveau_projet.py — ne pas copier un .conf existant à la main.
# Format : CLÉ = valeur. Lignes vides et lignes commençant par # ignorées.

# ─── Requis ───────────────────────────────────────────────────────────────────
NOM         = {nom}
DEPOT       = {depot}
REP_TRAVAIL = {rep_travail}
TOPIC_NTFY  = {topic_ntfy}

# ─── Périmètre CCL (dossiers autorisés, séparés par des virgules) ─────────────
PERIMETRE   = {perimetre}

# ─── Sauvegarde avant modification (mode écriture) ────────────────────────────
CMD_BACKUP  = git add -A && git commit -m "avant-<description>" --allow-empty

# ─── Contexte ───────────────────────────────────────────────────────────────────
FICHIER_CONTEXTE = CONTEXTE.md

# ─── Couleur d'accent dans l'interface (hex #RRGGBB ; vide = repli auto) ───────
# Attribuée à la création (palette de nouveau_projet.py, couleurs déjà prises
# exclues). Le frontend l'utilise en priorité ; à défaut il retombe sur la map
# fixe puis sur un hash HSL du nom (issue #121).
COULEUR          = {couleur}

# ─── Optionnels (le défaut s'applique si la ligne reste commentée) ─────────────
LABEL             = for-linux
INTERVALLE        = 10
MAX_ESSAIS        = 3
TIMEOUT_CLAUDE    = 300
SCRIPT_BIP        = {script_bip}

# ─── Journaux (rotation par taille, archives datées) ──────────────────────────
LOG_TAILLE_MAX_MO = 1
LOG_ARCHIVES      = 5

# ─── Auto-extinction du watcher après inactivité (issue #200) ─────────────────
# Minutes sans aucune issue traitable avant arrêt propre. 0 = désactivé (permanent).
DELAI_INACTIVITE_MIN = 20

# ─── Modèle CCL forcé (vide = défaut) ─────────────────────────────────────────
MODELE_CCL        =

# ─── Mot de passe interface (sha256 ; vide = pas d'authentification) ──────────
# MOT_DE_PASSE    =
"""


# ─── Programme principal ──────────────────────────────────────────────────────

def main() -> None:
    print("\033[1m═══ Bridge_Agent — Nouveau projet ═══\033[0m")
    print("Création ou installation d'un projet dans le bridge inter-agents.")

    if subprocess.run(["which", "gh"], capture_output=True).returncode != 0:
        sys.exit("❌ La commande `gh` (GitHub CLI) est requise mais introuvable.")

    nom = etape_nom()
    depot, depot_existait = etape_depot(nom)
    rep, perimetre = etape_repertoire(nom)
    chemin_conf = etape_conf(nom, depot, rep, perimetre)
    labels_crees = etape_labels(depot)
    fichiers_contexte = etape_contexte(rep, avec_specs=False)

    # 7. Pattern Chef + Specs MVC (prospectif, §15) — question séparée.
    titre("7. Pattern Chef + Specs MVC (optionnel, §15)")
    print("   Crée en plus CONTEXTE_VUE.md, CONTEXTE_METIER.md, "
          "CONTEXTE_PERSISTANCE.md (vides).")
    if demander_oui_non("Mettre en place le pattern Specs MVC", defaut=False):
        fichiers_contexte += etape_contexte(rep, avec_specs=True)

    doc_ok = etape_doc(nom, depot, rep, perimetre)

    # 9. Résumé final.
    titre("✅ Résumé")
    print(f"   Projet          : {nom}")
    print(f"   Dépôt GitHub    : {depot} "
          f"({'existant' if depot_existait else 'créé'})")
    print(f"   Config          : {chemin_conf.relative_to(RACINE)}")
    print(f"   Périmètre       : {perimetre}")
    if labels_crees:
        print(f"   Labels créés    : {', '.join(labels_crees)}")
    else:
        print("   Labels          : tous déjà présents (rien à créer)")
    if fichiers_contexte:
        print("   Contexte        : " +
              ", ".join(str(f) for f in fichiers_contexte))
    print(f"   Documentation   : {'§2/§7/date mis à jour' if doc_ok else 'à vérifier'}")

    print("\n\033[1mReste à faire manuellement :\033[0m")
    print(f"   • Lancer le watcher : "
          f"python3 watcher.py --config configs/{nom}.conf")
    print(f"   • Vérifier puis committer/pousser les changements du dépôt "
          "Bridge_Agent (configs/, doc).")
    print("   • (Optionnel) Piloter le watcher depuis l'interface new_issue.py.")

    rappel_projet_claude(nom)


def rappel_projet_claude(nom: str) -> None:
    """Affiche un encadré ASCII rappelant de créer un Projet Claude dédié pour
    le projet fraîchement créé (action manuelle, hors périmètre du script,
    facilement oubliée). Le nom du projet est injecté dynamiquement.

    Le même rappel doit être proposé sous forme de modal après la création via
    le bouton web (issue #99) — voir le commentaire posté sur cette issue."""
    largeur = 72
    interne = largeur - 4          # colonnes utiles entre les bordures
    barre = "═" * largeur

    def largeur_affichee(txt: str) -> int:
        # Les glyphes « wide » (emoji…) occupent 2 colonnes à l'écran alors que
        # len() n'en compte qu'une : sans ça la bordure droite se décale.
        return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
                   for c in txt)

    def ligne(txt: str = "") -> None:
        # Découpe le texte en lignes tenant dans l'encadré, coupe aux espaces.
        mots, courante = txt.split(), ""
        rendus = []
        for mot in mots:
            essai = f"{courante} {mot}".strip()
            if largeur_affichee(essai) > interne:
                rendus.append(courante)
                courante = mot
            else:
                courante = essai
        rendus.append(courante)
        for r in rendus or [""]:
            bourrage = " " * (interne - largeur_affichee(r))
            print(f"║ {r}{bourrage} ║")

    print()
    print(f"╔{barre}╗")
    ligne(f"💡 Pense à créer un Projet Claude dédié pour « {nom} »")
    ligne()
    ligne(f"Un Projet Claude dédié te donne un espace mémoire séparé dans "
          f"l'interface Claude pour « {nom} ». C'est une action manuelle, "
          "facultative, à faire depuis l'interface Claude.")
    ligne()
    ligne("Settings n'a plus besoin d'être modifié : le §2 de "
          "BRIDGE_AGENT_DOC.md fait foi automatiquement pour la "
          "reconnaissance du projet.")
    print(f"╚{barre}╝")


if __name__ == "__main__":
    main()

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
from datetime import date
from pathlib import Path

# Racine du dépôt Bridge_Agent : ce script vit à la racine, à côté de watcher.py
# et du dossier configs/.
RACINE = Path(__file__).resolve().parent
DOSSIER_CONFIGS = RACINE / "configs"
DOC = RACINE / "BRIDGE_AGENT_DOC.md"

# Les 8 labels requis par le watcher (§4 de la doc). color = hex sans '#'.
# On les recrée à l'identique sur chaque nouveau dépôt cible ; sans eux, le
# watcher ne voit pas les issues (for-linux) et le mode écriture reste inerte.
LABELS = [
    ("for-linux",   "0e8a16", "Requis — le watcher ne voit que ces issues"),
    ("bridge",      "1d76db", "Marque l'issue comme tâche bridge (traçabilité)"),
    ("mode_write",  "d93f0b", "ARME le mode écriture — CCL peut modifier des fichiers"),
    ("needs-human", "b60205", "Posé après 3 échecs — stoppe le retraitement auto"),
    ("done",        "0e8a16", "Posé automatiquement au succès"),
    ("notif_pc",    "fbca04", "Ajoute une notification bureau (notify-send)"),
    ("notif_gsm",   "fbca04", "Ajoute une notification push (ntfy)"),
    ("notif_tous",  "fbca04", "notify-send + ntfy"),
]

# Topic ntfy partagé par tous les projets existants (voir configs/*.conf).
# Proposé par défaut ; l'utilisateur peut le changer pour un topic dédié.
TOPIC_NTFY_DEFAUT = "hippocampe-ff-galerie-xyz123"
SCRIPT_BIP_DEFAUT = "/home/alain/NicLink/bip.py"

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
    owner = "AlainDelree"
    defaut = f"{owner}/{nom.capitalize()}"
    depot = demander("Dépôt GitHub (owner/nom)", defaut)

    existe = gh("repo", "view", depot).returncode == 0
    if existe:
        print(f"   ✓ Le dépôt {depot} existe déjà → installation dessus "
              "(pas de recréation).")
        return depot, True

    print(f"   Le dépôt {depot} n'existe pas encore.")
    if not demander_oui_non(f"Créer {depot} (public)", defaut=True):
        print("   Abandon : impossible de continuer sans dépôt cible.")
        sys.exit(1)

    print(f"   Création de {depot}…")
    res = gh("repo", "create", depot, "--public",
             "--description", f"Projet {nom} — piloté via Bridge_Agent")
    if res.returncode != 0:
        print(f"   ❌ Échec de la création : {res.stderr.strip()}")
        sys.exit(1)
    print("   ✓ Dépôt créé.")
    return depot, False


def etape_repertoire(nom: str) -> tuple[str, str]:
    """Renvoie (rep_travail, perimetre)."""
    titre("3. Répertoire de travail CCL et périmètre")
    defaut_rep = f"/home/alain/{nom.capitalize()}"
    rep = demander("Répertoire de travail CCL", defaut_rep)
    perimetre = demander("Périmètre autorisé (dossiers, séparés par des virgules)", rep)
    return rep, perimetre


def etape_conf(nom: str, depot: str, rep: str, perimetre: str) -> Path:
    titre("4. Fichier configs/<nom>.conf")
    topic = demander("Topic ntfy", TOPIC_NTFY_DEFAUT)
    chemin = DOSSIER_CONFIGS / f"{nom}.conf"
    contenu = GABARIT_CONF.format(
        nom=nom,
        depot=depot,
        rep_travail=rep,
        perimetre=perimetre,
        topic_ntfy=topic,
        script_bip=SCRIPT_BIP_DEFAUT,
    )
    chemin.write_text(contenu, encoding="utf-8")
    print(f"   ✓ {chemin.relative_to(RACINE)} créé (à partir du gabarit).")
    return chemin


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

# ─── Optionnels (le défaut s'applique si la ligne reste commentée) ─────────────
LABEL             = for-linux
INTERVALLE        = 10
MAX_ESSAIS        = 3
TIMEOUT_CLAUDE    = 300
SCRIPT_BIP        = {script_bip}

# ─── Journaux (rotation par taille, archives datées) ──────────────────────────
LOG_TAILLE_MAX_MO = 1
LOG_ARCHIVES      = 5

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


if __name__ == "__main__":
    main()

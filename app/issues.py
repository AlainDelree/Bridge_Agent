"""Gestion des issues du bridge (création, consultation, annulation).

Extraite de new_issue.py à l'étape 7 du refactoring modulaire. Regroupe la
construction du body markdown et des labels, ainsi que les routes Flask liées
aux issues : aperçu de la commande gh, envoi, listes et détail.
"""

import json
import os
import subprocess
import sys  # noqa: F401 (conservé pour parité avec les autres modules extraits)
import tempfile
from pathlib import Path

from flask import jsonify, request

from app.projets import projet_par_nom
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)
# projet_par_nom (app.projets) a déjà inséré la racine dans sys.path : l'import
# du watcher fonctionne. On réutilise ses primitives pour éviter toute dérive
# entre le calcul du watcher et celui du badge (issues #91 et #106).
from watcher import est_titre_chef, PAUSE_ENTRE_TENTATIVES

# Racine du projet (dossier parent du package app/).
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent


# ─── Construction du body et des labels ───────────────────────────────────────

def construire_body(data: dict) -> str:
    """Construit le body markdown depuis les champs du formulaire."""
    mode            = "ÉCRITURE" if data.get("mode") == "ecriture" else "lecture seule"
    priorite        = data.get("priorite", "normale")
    timeout         = data.get("timeout", "300")
    modele_ponctuel = data.get("modele_ponctuel", "").strip()
    corps           = data.get("corps", "").strip()
    nom_projet      = data.get("projet", "").strip()

    lignes = [
        "## En-tête\n",
        "| Champ    | Valeur |",
        "|----------|--------|",
        "| SOURCE   | CC |",
        "| DEST     | CCL |",
        "| RETOUR   | CC |",
        f"| MODE     | {mode} |",
        f"| PRIORITE | {priorite} |",
        f"| TIMEOUT  | {timeout}s |",
        f"| PROJET   | {nom_projet} |",
    ]
    if modele_ponctuel:
        lignes.append(f"| MODELE   | {modele_ponctuel} |")

    return "\n".join(lignes) + f"\n\n{corps}"


def construire_labels(data: dict) -> str:
    """Construit la liste de labels depuis les champs du formulaire."""
    labels = ["bridge", "for-linux"]
    if data.get("mode") == "ecriture":
        labels.append("mode_write")
    notifs = data.get("notifs", [])
    if isinstance(notifs, str):
        notifs = [notifs]
    labels.extend(notifs)
    return ",".join(labels)


# ─── Routes Flask ──────────────────────────────────────────────────────────────

def apercu():
    data   = request.json or {}
    cfg    = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(commande="Projet introuvable.")
    labels = construire_labels(data)
    titre  = data.get("titre", "")
    body   = construire_body(data)
    commande = (
        f"gh issue create \\\n"
        f"  --repo {cfg.depot} \\\n"
        f"  --title \"{titre}\" \\\n"
        f"  --label \"{labels}\" \\\n"
        f"  --body-file /tmp/issue-body.md\n"
        f"\n# ─── Body qui sera envoyé ───────────────────────────────────\n\n"
        f"{body}"
    )
    return jsonify(commande=commande)


def envoyer():
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    titre  = data.get("titre", "").strip()
    if not titre:
        return jsonify(succes=False, erreur="Le titre est obligatoire.")
    labels = construire_labels(data)
    body   = construire_body(data)

    # Fichier temporaire pour le body (évite tout enfer d'échappement shell).
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(body)
        chemin_body = f.name

    try:
        res = subprocess.run(
            ["gh", "issue", "create",
             "--repo",      cfg.depot,
             "--title",     titre,
             "--label",     labels,
             "--body-file", chemin_body],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode == 0:
            return jsonify(succes=True, url=res.stdout.strip())
        else:
            return jsonify(succes=False, erreur=res.stderr.strip() or "Erreur inconnue de gh.")
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, erreur="Timeout (gh n'a pas répondu en 30s).")
    except FileNotFoundError:
        return jsonify(succes=False, erreur="gh introuvable dans le PATH.")
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))
    finally:
        os.unlink(chemin_body)


def issues_liste(nom_projet):
    """Retourne les 30 dernières issues (tous états) du projet via gh."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo",  cfg.depot,
             "--state", "all",
             "--limit", "30",
             "--json",  "number,title,state,labels,createdAt"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return jsonify(erreur=res.stderr.strip() or "Erreur de gh."), 502
        return jsonify(json.loads(res.stdout or "[]"))
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (gh n'a pas répondu en 30s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="gh introuvable dans le PATH."), 500
    except Exception as e:
        return jsonify(erreur=str(e)), 500


def issue_detail(nom_projet, numero):
    """Retourne le détail d'une issue (corps + commentaires) via gh."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    if not str(numero).isdigit():
        return jsonify(erreur="Numéro d'issue invalide."), 400
    try:
        res = subprocess.run(
            ["gh", "issue", "view", str(numero),
             "--repo", cfg.depot,
             "--json", "number,title,body,state,labels,comments,createdAt,closedAt"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return jsonify(erreur=res.stderr.strip() or "Erreur de gh."), 502
        return jsonify(json.loads(res.stdout or "{}"))
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (gh n'a pas répondu en 30s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="gh introuvable dans le PATH."), 500
    except Exception as e:
        return jsonify(erreur=str(e)), 500


# ─── Temps restant estimé des issues ouvertes (issue #91) ─────────────────────
# L'heure de début de traitement d'une issue n'est persistée NULLE PART par le
# watcher (le set issues_en_cours est en mémoire, sans horodatage, et perdu au
# redémarrage). Elle est cependant retrouvable : au démarrage du traitement, le
# watcher poste un commentaire ACK sur l'issue (« ✅ ACK — Issue #N reçue par
# watcher.py … Traitement en cours… »). L'horodatage createdAt de ce commentaire
# EST l'heure de début — source de vérité qui survit à un redémarrage du watcher.
# On la relit ici pour calculer, côté navigateur, un temps restant estimé.

def _parser_timeout(body: str, titre: str = "", cfg=None) -> int:
    """TIMEOUT (secondes) lu dans l'en-tête bridge du body. Miroir de
    watcher.extraire_timeout : si absent/mal formé, retombe sur le défaut projet
    (cfg.timeout_claude), ou sur le défaut Chef plus généreux (cfg.timeout_chef)
    pour les issues « Chef : » (issue #106). Sans cfg, défaut historique 300 s."""
    for ligne in body.splitlines():
        if "TIMEOUT" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip().lower().rstrip("s")
                if valeur.isdigit():
                    return int(valeur)
    if cfg is None:
        return 300
    if est_titre_chef(titre):
        return cfg.timeout_chef
    return cfg.timeout_claude


def _parser_priorite(body: str) -> str:
    """PRIORITE lue dans l'en-tête bridge du body ; défaut 'normale'.
    Miroir de watcher.extraire_priorite."""
    for ligne in body.splitlines():
        if "PRIORITE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                return parts[2].strip().lower()
    return "normale"


def _debut_traitement(commentaires: list) -> str | None:
    """createdAt (ISO) du commentaire ACK que le watcher poste au démarrage du
    traitement, ou None si aucun (issue pas encore prise en charge). gh renvoie
    les commentaires par ordre chronologique : le premier ACK fait foi."""
    for c in commentaires:
        corps = c.get("body") or ""
        if "ACK —" in corps and "watcher.py" in corps:
            return c.get("createdAt")
    return None


def _commentaires_issue(cfg, numero) -> list:
    """Récupère les commentaires d'une issue via gh (liste vide sur erreur)."""
    try:
        res = subprocess.run(
            ["gh", "issue", "view", str(numero),
             "--repo", cfg.depot,
             "--json", "comments"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return []
        return (json.loads(res.stdout or "{}") or {}).get("comments") or []
    except Exception:
        return []


def issues_en_attente(nom_projet):
    """Retourne les issues ouvertes portant le label for-linux (en attente de
    traitement par le watcher). La liste peut être vide.

    Chaque issue est enrichie des champs nécessaires au calcul, côté navigateur,
    d'un temps restant estimé (issue #91), conscient du budget de retry (#106) :
      - timeout      : TIMEOUT par tentative en secondes (défaut projet, ou
                       défaut Chef plus généreux pour les issues « Chef : »)
      - max_essais   : nombre de tentatives du watcher (budget = timeout × ce
                       nombre + backoffs) — le badge ne signale « dépassement »
                       qu'une fois ce budget total épuisé, pas au 1er cycle
      - backoff      : pause (s) entre deux tentatives
      - priorite     : PRIORITE de l'issue
      - sans_limite  : True si priorité haute/critique (retry infini, §6) → pas
                       de deadline, afficher « en cours (pas de limite) »
      - debut        : horodatage ISO du début de traitement (commentaire ACK),
                       ou null si l'issue n'est pas encore prise en charge."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo",  cfg.depot,
             "--label", "for-linux",
             "--state", "open",
             "--json",  "number,title,labels,body"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return jsonify(erreur=res.stderr.strip() or "Erreur de gh."), 502
        issues = json.loads(res.stdout or "[]")
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (gh n'a pas répondu en 30s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="gh introuvable dans le PATH."), 500
    except Exception as e:
        return jsonify(erreur=str(e)), 500

    # Enrichissement : une passe gh view par issue ouverte (nécessaire pour lire
    # les commentaires — gh issue list ne les expose pas). Les issues ouvertes
    # for-linux sont rares (souvent 0-3), le surcoût reste modéré.
    for it in issues:
        body = it.get("body") or ""
        titre = it.get("title") or ""
        priorite = _parser_priorite(body)
        it["timeout"]     = _parser_timeout(body, titre, cfg)
        it["max_essais"]  = cfg.max_essais
        it["backoff"]     = PAUSE_ENTRE_TENTATIVES
        it["priorite"]    = priorite
        it["sans_limite"] = priorite in ("haute", "critique")
        it["debut"]       = _debut_traitement(_commentaires_issue(cfg, it["number"]))
        it.pop("body", None)   # body volumineux : inutile au navigateur
    return jsonify(issues)


def annuler_issue(nom_projet, numero):
    """Ferme une issue créée sur GitHub mais pas encore traitée par le watcher."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(succes=False, message="Projet introuvable."), 404
    if not str(numero).isdigit():
        return jsonify(succes=False, message="Numéro d'issue invalide."), 400
    commentaire = ("Issue annulée manuellement depuis new_issue.py "
                   "avant traitement par le watcher.")
    try:
        res = subprocess.run(
            ["gh", "issue", "close", str(numero),
             "--repo",    cfg.depot,
             "--comment", commentaire],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode == 0:
            return jsonify(succes=True, message=f"Issue #{numero} annulée.")
        return jsonify(succes=False,
                       message=res.stderr.strip() or "Erreur inconnue de gh.")
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, message="Timeout (gh n'a pas répondu en 30s).")
    except FileNotFoundError:
        return jsonify(succes=False, message="gh introuvable dans le PATH.")
    except Exception as e:
        return jsonify(succes=False, message=str(e))


def fermer_issue(nom_projet, numero):
    """Ferme définitivement une issue en échec (label needs-human).

    Après 3 tentatives infructueuses, le watcher pose le label needs-human et
    stoppe le retraitement : une intervention humaine est requise. Une fois
    celle-ci effectuée, ce point d'entrée permet de clore l'issue directement
    depuis l'onglet Résultats, sans passer par l'interface GitHub."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(succes=False, message="Projet introuvable."), 404
    if not str(numero).isdigit():
        return jsonify(succes=False, message="Numéro d'issue invalide."), 400
    commentaire = ("Issue fermée définitivement depuis new_issue.py "
                   "(label needs-human — intervention humaine effectuée).")
    try:
        res = subprocess.run(
            ["gh", "issue", "close", str(numero),
             "--repo",    cfg.depot,
             "--comment", commentaire],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode == 0:
            return jsonify(succes=True, message=f"Issue #{numero} fermée définitivement.")
        return jsonify(succes=False,
                       message=res.stderr.strip() or "Erreur inconnue de gh.")
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, message="Timeout (gh n'a pas répondu en 30s).")
    except FileNotFoundError:
        return jsonify(succes=False, message="gh introuvable dans le PATH.")
    except Exception as e:
        return jsonify(succes=False, message=str(e))

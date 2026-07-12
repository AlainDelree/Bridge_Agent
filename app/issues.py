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


def issues_en_attente(nom_projet):
    """Retourne les issues ouvertes portant le label for-linux (en attente de
    traitement par le watcher). La liste peut être vide."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo",  cfg.depot,
             "--label", "for-linux",
             "--state", "open",
             "--json",  "number,title,labels"],
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

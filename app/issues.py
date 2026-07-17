"""Gestion des issues du bridge (création, consultation, annulation).

Extraite de new_issue.py à l'étape 7 du refactoring modulaire. Regroupe la
construction du body markdown et des labels, ainsi que les routes Flask liées
aux issues : aperçu de la commande gh, envoi, listes et détail.
"""

import json
import os
import re
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
from watcher import est_titre_chef, deduire_type_issue, PAUSE_ENTRE_TENTATIVES

# Racine du projet (dossier parent du package app/).
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent

# Historique des durées réelles alimenté par le watcher (issue #108). Même
# emplacement que watcher.FICHIER_HISTORIQUE — on le recalcule ici plutôt que de
# l'importer pour rester robuste si le watcher n'a pas encore tourné.
FICHIER_HISTORIQUE = DOSSIER_SCRIPT / "logs" / "historique_durees.json"

# Seuils de fiabilité de l'estimation, exprimés en NOMBRE D'ÉCHANTILLONS de la
# catégorie précise (projet+type+mode). Volume réel observé sur le bridge : la
# plupart des catégories ont peu de fermetures, quelques-unes (ex. alchess) en
# cumulent davantage. On garde donc les seuils indicatifs de l'issue #108 :
#   n < 5   → estimation incertaine (rouge)
#   5 ≤ n ≤ 15 → estimation correcte (noir)
#   n > 15  → estimation fiable (vert)
SEUIL_ESTIM_CORRECT = 5    # en dessous : « incertain » (rouge)
SEUIL_ESTIM_SUR     = 15   # au-dessus : « sûr » (vert) ; entre les deux : « correct » (noir)


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


# ─── Diff d'un commit (issue #114) ────────────────────────────────────────────
# L'onglet « Diff » du détail d'une issue affiche le `git show` du/des commit(s)
# détecté(s) dans la réponse CCL. Un hash arrivant depuis le navigateur est une
# entrée non fiable injectée dans une commande git : on le VALIDE strictement
# (7 à 40 caractères hexadécimaux minuscules, rien d'autre) AVANT tout usage.

# Format d'un hash de commit git : 7 à 40 chiffres hexadécimaux. La validation
# stricte (ancrée ^…$) garantit qu'aucun métacaractère shell ni option git
# (préfixe « - ») ne peut passer — l'argument est de toute façon transmis en
# liste (pas via un shell), mais on refuse net toute entrée non conforme.
HASH_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


def diff_commit(nom_projet, hash_commit):
    """Retourne la sortie de `git show <hash>` exécuté dans le répertoire de
    travail du projet, pour un hash de commit détecté dans la réponse CCL.

    Le hash est validé strictement (HASH_COMMIT_RE) avant toute utilisation :
    seul un hash hexadécimal 7-40 caractères est accepté. Git est invoqué en
    liste d'arguments (jamais via un shell), avec -C pour cibler le dépôt du
    projet et -- pour éviter toute interprétation du hash comme un chemin."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    hash_commit = str(hash_commit).lower()
    if not HASH_COMMIT_RE.match(hash_commit):
        return jsonify(erreur="Hash de commit invalide."), 400
    if not cfg.rep_travail.is_dir():
        return jsonify(erreur="Répertoire de travail introuvable."), 404
    try:
        res = subprocess.run(
            ["git", "-C", str(cfg.rep_travail), "show",
             "--no-color", "--stat", "--patch", hash_commit, "--"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            # Commit inconnu du dépôt (ex. backup pas encore poussé/abandonné) :
            # message clair plutôt qu'erreur brute.
            return jsonify(erreur=(res.stderr.strip()
                                   or f"Commit {hash_commit} introuvable.")), 404
        return jsonify(diff=res.stdout)
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (git n'a pas répondu en 30s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="git introuvable dans le PATH."), 500
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
    pour les issues « Chef : » (issue #106). Filet de sécurité #111 : pour une
    tâche « Chef : », plancher à max(valeur_trouvée, cfg.timeout_chef) pour que le
    badge reflète le même budget que le watcher (voir watcher.extraire_timeout).
    Sans cfg, défaut historique 300 s."""
    chef = cfg is not None and est_titre_chef(titre)
    for ligne in body.splitlines():
        if "TIMEOUT" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip().lower().rstrip("s")
                if valeur.isdigit():
                    trouve = int(valeur)
                    return max(trouve, cfg.timeout_chef) if chef else trouve
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
    les commentaires par ordre chronologique : la DERNIÈRE ACK fait foi (issue
    #145). En déroulement normal une seule ACK existe (premier = dernier) ; en
    cas de reprise après interruption du watcher (crash, reset, Éteindre/
    Relancer), plusieurs ACK coexistent et seule la plus récente reflète le
    vrai début de la tentative en cours — sinon le badge inclurait à tort le
    temps mort de l'interruption."""
    debut = None
    for c in commentaires:
        corps = c.get("body") or ""
        if "ACK —" in corps and "watcher.py" in corps:
            debut = c.get("createdAt")
    return debut


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


# ─── Estimation prédictive de durée (issue #108) ──────────────────────────────
# Le badge de décompte (issues #91/#106) mesure le TEMPS RESTANT avant l'échéance
# du TIMEOUT configuré — pas une durée réaliste. On ajoute ici une estimation
# fondée sur l'historique réel des issues fermées du même projet+type+mode
# (médiane), avec un code couleur de fiabilité selon le nombre d'échantillons.

def _charger_historique() -> list:
    """Charge la liste des durées historiques (logs/historique_durees.json).
    Liste vide si le fichier n'existe pas encore ou est illisible/corrompu —
    dans ce cas toutes les catégories seront « pas encore de données »."""
    try:
        if FICHIER_HISTORIQUE.exists():
            return json.loads(FICHIER_HISTORIQUE.read_text(encoding="utf-8")) or []
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _mediane(valeurs: list) -> float:
    """Médiane d'une liste non vide (moyenne des deux centraux si pair)."""
    s = sorted(valeurs)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2


def estimer_duree(historique: list, projet: str, type_issue: str, mode: str) -> dict:
    """Estimation prédictive (médiane des durées) + niveau de fiabilité pour une
    catégorie projet+type+mode (issue #108).

    Retourne un dict prêt pour le navigateur :
      - mediane   : durée médiane en secondes (int), ou None si aucune donnée
      - n         : nombre d'échantillons de la catégorie
      - fiabilite : 'aucune' (pas encore de données) | 'incertain' (rouge) |
                    'correct' (noir) | 'sur' (vert)
    """
    durees = [
        r.get("duree") for r in historique
        if r.get("projet") == projet
        and r.get("type") == type_issue
        and r.get("mode") == mode
        and isinstance(r.get("duree"), (int, float))
    ]
    n = len(durees)
    if n == 0:
        return {"mediane": None, "n": 0, "fiabilite": "aucune"}
    if n < SEUIL_ESTIM_CORRECT:
        fiabilite = "incertain"
    elif n <= SEUIL_ESTIM_SUR:
        fiabilite = "correct"
    else:
        fiabilite = "sur"
    return {"mediane": round(_mediane(durees)), "n": n, "fiabilite": fiabilite}


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
                       ou null si l'issue n'est pas encore prise en charge.
      - estimation   : estimation prédictive de durée (issue #108) — dict
                       {mediane (s|null), n, fiabilite} basé sur la médiane des
                       durées historiques du même projet+type+mode. fiabilite
                       'aucune' → « pas encore de données »."""
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

    # Historique des durées chargé une seule fois pour toutes les issues (issue
    # #108) : sert au calcul de l'estimation prédictive par catégorie.
    historique = _charger_historique()

    # Enrichissement : une passe gh view par issue ouverte (nécessaire pour lire
    # les commentaires — gh issue list ne les expose pas). Les issues ouvertes
    # for-linux sont rares (souvent 0-3), le surcoût reste modéré.
    for it in issues:
        body = it.get("body") or ""
        titre = it.get("title") or ""
        priorite = _parser_priorite(body)
        labels = [(l.get("name") or "").lower() for l in it.get("labels", [])]
        type_issue = deduire_type_issue(titre, body)
        mode = "write" if "mode_write" in labels else "read"
        it["timeout"]     = _parser_timeout(body, titre, cfg)
        it["max_essais"]  = cfg.max_essais
        it["backoff"]     = PAUSE_ENTRE_TENTATIVES
        it["priorite"]    = priorite
        it["sans_limite"] = priorite in ("haute", "critique")
        it["debut"]       = _debut_traitement(_commentaires_issue(cfg, it["number"]))
        # Estimation prédictive (médiane historique du même projet+type+mode),
        # affichée AVANT le badge de décompte, qui reste inchangé (issue #108).
        it["estimation"]  = estimer_duree(historique, cfg.nom, type_issue, mode)
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

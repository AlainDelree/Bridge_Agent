"""Gestion des issues du bridge (création, consultation, annulation).

Extraite de new_issue.py à l'étape 7 du refactoring modulaire. Regroupe la
construction du body markdown et des labels, ainsi que les routes Flask liées
aux issues : aperçu de la commande gh, envoi, listes et détail.
"""

import json
import logging
import os
import re
import subprocess
import sys  # noqa: F401 (conservé pour parité avec les autres modules extraits)
import tempfile
from datetime import datetime
from pathlib import Path

from flask import jsonify, request
from werkzeug.utils import secure_filename

from app.projets import projet_par_nom
from app.auth import login_requis  # noqa: F401 (exporté pour l'enregistrement des routes)
# projet_par_nom (app.projets) a déjà inséré la racine dans sys.path : l'import
# du watcher fonctionne. On réutilise ses primitives pour éviter toute dérive
# entre le calcul du watcher et celui du badge (issues #91 et #106).
from watcher import (est_titre_chef, deduire_type_issue, PAUSE_ENTRE_TENTATIVES,
                     _est_depot_git)

# Racine du projet (dossier parent du package app/).
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent

# ─── Consignes injectées (architecture à trois couches, issue #209) ───────────
# Dossier des consignes injectées automatiquement en tête de chaque corps d'issue,
# entre le tableau d'en-tête et le corps rédigé par Claude Chat. Trois couches,
# de la plus générale à la plus spécifique (§12 de BRIDGE_AGENT_DOC.md) :
#   - consignes/globales.md          : NON-optionnel, injecté dans TOUTE issue
#                                       (rappels de sécurité transversaux) ;
#   - consignes/type_<type>.md       : optionnel, selon le TYPE déduit de l'issue
#                                       (ex. type_chef.md) ;
#   - consignes/projet_<projet>.md   : optionnel, selon le projet ciblé.
# Les couches type/projet sont FACULTATIVES : un fichier absent n'est pas une
# anomalie (aucun log), on n'injecte simplement rien pour cette couche. Seul
# globales.md manquant justifie un logging.warning — sans jamais faire échouer la
# création d'issue (voir _consignes_injectees).
DOSSIER_CONSIGNES = DOSSIER_SCRIPT / "consignes"

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

# ─── Pièces jointes image des issues (issue #191) ─────────────────────────────
# Dossier (relatif au rep_travail du projet) où sont committées les images
# jointes à une issue, puis référencées dans son corps via une URL
# raw.githubusercontent.com. Voir joindre_image() plus bas et §18 de
# BRIDGE_AGENT_DOC.md pour le mécanisme complet et l'exception « push par Alain ».
DOSSIER_PIECES_JOINTES = "issue-attachments"
# Types MIME acceptés → extension canonique du fichier sauvegardé. On n'accepte
# que des formats image passifs qui s'affichent nativement dans les issues GitHub
# (PNG, JPEG, GIF) — pas de code exécutable embarqué, même famille de risque
# (issue #192 pour l'ajout du GIF).
TYPES_IMAGE_ACCEPTES = {
    "image/png":  ".png",
    "image/jpeg": ".jpg",
    "image/gif":  ".gif",
}
# Signatures binaires (magic bytes) de contrôle : on ne se fie pas au seul
# Content-Type déclaré par le navigateur, on vérifie aussi les premiers octets.
# Le GIF a deux signatures historiques (GIF87a / GIF89a) — on accepte les deux.
SIGNATURES_IMAGE = {
    "image/png":  (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif":  (b"GIF87a", b"GIF89a"),
}
TAILLE_MAX_IMAGE = 5 * 1024 * 1024   # 5 Mo — message clair si dépassée


def formats_image_acceptes() -> dict:
    """Descriptif des formats image acceptés, DÉRIVÉ de TYPES_IMAGE_ACCEPTES et
    TAILLE_MAX_IMAGE, pour l'interface (issue #192).

    Source unique de vérité : ce helper évite de dupliquer en dur la liste des
    formats dans le gabarit et le JavaScript. index() le passe au template, qui
    l'utilise pour l'attribut `accept`, le texte « Formats acceptés : … » et la
    variable JS `window.MIMES_IMAGE_ACCEPTES` (garde-fou client). Un futur ajout
    de format dans TYPES_IMAGE_ACCEPTES se répercute donc automatiquement partout.

    Retourne :
      - mimes         : liste des types MIME acceptés (ex. ['image/png', …])
      - accept        : valeur prête pour l'attribut HTML accept (mimes joints)
      - texte         : libellés lisibles joints (ex. 'PNG, JPEG, GIF')
      - taille_max_mo : limite de taille en Mo (int)
    """
    mimes = list(TYPES_IMAGE_ACCEPTES.keys())
    # Libellé lisible dérivé du sous-type MIME : image/png → PNG, image/jpeg →
    # JPEG, image/gif → GIF.
    libelles = [m.split("/", 1)[1].upper() for m in mimes]
    return {
        "mimes":         mimes,
        "accept":        ",".join(mimes),
        "texte":         ", ".join(libelles),
        "taille_max_mo": TAILLE_MAX_IMAGE // (1024 * 1024),
    }


# ─── Construction du body et des labels ───────────────────────────────────────

# Lecture d'un champ d'en-tête « | LABELS | a,b,c | » dans le corps collé (issue
# #161). Miroir Python de lireChampEntete (static/js/app.js) : mot-clé insensible
# à la casse, ancré en début de ligne, la valeur étant la cellule entre le 2e et
# le 3e « | ». On garde la MÊME logique que le parsing d'en-tête côté formulaire
# pour éviter toute divergence de regex.
LABELS_ENTETE_RE = re.compile(r"^\s*\|\s*LABELS\s*\|([^|]*)\|", re.IGNORECASE | re.MULTILINE)


def _parser_labels_entete(corps: str) -> list:
    """Labels supplémentaires lus dans le champ d'en-tête optionnel
    « | LABELS | for-windows,urgent | » du corps collé (issue #161).

    Retourne la liste des labels non vides, chacun débarrassé de ses espaces
    superflus (trim) ; liste vide si le champ est absent. Validation minimale :
    les entrées vides ou uniquement espaces sont ignorées silencieusement et on
    ne vérifie PAS que le label existe sur le dépôt — gh issue create échoue de
    lui-même avec un message clair si le label n'existe pas, et on laisse cette
    erreur remonter normalement."""
    m = LABELS_ENTETE_RE.search(corps or "")
    if not m:
        return []
    return [lab.strip() for lab in m.group(1).split(",") if lab.strip()]


def _lire_consigne(chemin: Path) -> str | None:
    """Contenu texte d'un fichier de consignes (strippé), ou None s'il est absent
    ou illisible. Best-effort : un fichier manquant n'est pas une erreur ici (les
    couches type/projet sont facultatives), c'est l'appelant qui décide s'il faut
    logger l'absence (cas de globales.md uniquement)."""
    try:
        if chemin.is_file():
            texte = chemin.read_text(encoding="utf-8").strip()
            return texte or None
    except OSError:
        pass
    return None


def _consignes_injectees(nom_projet: str, titre: str, corps: str) -> str:
    """Bloc de consignes à injecter entre le tableau d'en-tête et le corps rédigé
    par Claude Chat (architecture à trois couches, issue #209).

    Ordre : globales → type (si présent) → projet (si présent). Chaîne vide si
    aucune couche n'a de contenu. Garde-fous :
      - globales.md manquant → logging.warning clair, mais on N'échoue PAS (le
        reste de l'injection et la création d'issue se poursuivent) ;
      - type_<type>.md / projet_<projet>.md absents → comportement NORMAL, aucune
        injection pour cette couche, sans log ni avertissement bruyant.

    Le TYPE est déduit via watcher.deduire_type_issue (même logique que le reste
    du bridge : champ « | TYPE | … | » du corps sinon préfixe du titre), donc le
    nom de fichier attendu est consignes/type_<type>.md (ex. type_chef.md). Vaut
    aussi bien en mono-issue qu'en mode lot : chaque bloc appelle construire_body
    avec son propre titre/corps/projet, donc son propre TYPE."""
    blocs = []

    # 1. Couche globale — NON-optionnelle (rappels de sécurité transversaux).
    globales = _lire_consigne(DOSSIER_CONSIGNES / "globales.md")
    if globales:
        blocs.append(globales)
    else:
        logging.warning(
            "consignes/globales.md introuvable (%s) : consignes globales non "
            "injectées dans l'issue — création poursuivie malgré tout.",
            DOSSIER_CONSIGNES / "globales.md",
        )

    # 2. Couche par TYPE — facultative. deduire_type_issue renvoie toujours une
    # valeur (repli « normal ») ; on n'injecte que si le fichier correspondant
    # existe réellement, donc « normal » (sans type_normal.md) n'injecte rien.
    type_issue = deduire_type_issue(titre, corps)
    if type_issue:
        consigne_type = _lire_consigne(DOSSIER_CONSIGNES / f"type_{type_issue}.md")
        if consigne_type:
            blocs.append(consigne_type)

    # 3. Couche par projet — facultative (aucun fichier créé par défaut, #209).
    if nom_projet:
        consigne_projet = _lire_consigne(DOSSIER_CONSIGNES / f"projet_{nom_projet}.md")
        if consigne_projet:
            blocs.append(consigne_projet)

    return "\n\n".join(blocs)


def construire_body(data: dict) -> str:
    """Construit le body markdown depuis les champs du formulaire.

    Injecte les consignes à trois couches (globales / type / projet, issue #209)
    entre le tableau d'en-tête et le corps rédigé par Claude Chat — voir
    _consignes_injectees."""
    mode            = "ÉCRITURE" if data.get("mode") == "ecriture" else "lecture seule"
    priorite        = data.get("priorite", "normale")
    timeout         = data.get("timeout", "300")
    modele_ponctuel = data.get("modele_ponctuel", "").strip()
    corps           = data.get("corps", "").strip()
    nom_projet      = data.get("projet", "").strip()
    titre           = data.get("titre", "").strip()

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

    entete    = "\n".join(lignes)
    consignes = _consignes_injectees(nom_projet, titre, corps)
    # Ordre final : en-tête → globales → type → projet → corps. Les parties vides
    # (consignes absentes) sont omises pour ne pas empiler de lignes blanches.
    parties = [p for p in (entete, consignes, corps) if p]
    return "\n\n".join(parties)


def construire_labels(data: dict) -> str:
    """Construit la liste de labels depuis les champs du formulaire."""
    # Labels supplémentaires du champ d'en-tête optionnel « | LABELS | … | »
    # (issue #161), lus d'abord car leur contenu conditionne la pose de
    # for-linux (voir ci-dessous).
    extras = _parser_labels_entete(data.get("corps", ""))
    labels = ["bridge"]
    # Exclusivité for-linux / for-windows (issue #164) : dans l'usage courant une
    # tâche cible CCL OU CCW, rarement les deux. On ne pose donc le label par
    # défaut for-linux QUE si l'en-tête LABELS ne demande pas for-windows —
    # sinon l'issue serait vue à la fois par le watcher CCL et par CCW. Les
    # autres labels standards (mode_write, notifs) restent posés normalement.
    if "for-windows" not in extras:
        labels.append("for-linux")
    if data.get("mode") == "ecriture":
        labels.append("mode_write")
    notifs = data.get("notifs", [])
    if isinstance(notifs, str):
        notifs = [notifs]
    labels.extend(notifs)
    # Les labels de l'en-tête s'AJOUTENT aux labels standards (bridge, for-linux,
    # mode_write, notifs) — on n'en remplace aucun (hormis l'exclusion de
    # for-linux ci-dessus). Dédoublonnage léger pour ne pas répéter un label déjà
    # posé si Alain le liste aussi dans LABELS.
    for extra in extras:
        if extra not in labels:
            labels.append(extra)
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


def _issue_ouverte_meme_titre(cfg, titre: str):
    """Numéro d'une issue OUVERTE du dépôt au titre strictement identique à
    `titre` (comparaison après strip des deux côtés), ou None si aucune.

    Anti-doublon (issue #189) : un double-clic sur « Envoyer » (ou une création
    manuelle) avait produit deux issues jumelles, traitées en parallèle par deux
    claude sur le même dossier. On refuse donc de recréer une issue dont le titre
    existe DÉJÀ sur une issue ouverte du même dépôt. On ne bloque que sur les
    issues OUVERTES : un titre réutilisé plus tard, après fermeture, reste permis.

    On liste les issues ouvertes et on filtre côté Python plutôt que via l'API
    Search de gh (rate-limitée, cf. issue #188). Best-effort : si gh échoue
    (réseau, timeout…), on retourne None et on laisse la création se poursuivre —
    la garde ne doit jamais transformer une panne de vérification en blocage."""
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo",  cfg.depot,
             "--state", "open",
             "--limit", "200",
             "--json",  "number,title"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return None
        for issue in json.loads(res.stdout or "[]"):
            if (issue.get("title") or "").strip() == titre.strip():
                return issue.get("number")
    except Exception:
        return None
    return None


def envoyer():
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    titre  = data.get("titre", "").strip()
    if not titre:
        return jsonify(succes=False, erreur="Le titre est obligatoire.")

    # Anti-doublon (issue #189) : refuser la création si une issue OUVERTE du même
    # dépôt porte déjà exactement ce titre, plutôt que d'empiler un doublon
    # silencieux (les deux finiraient traités en parallèle sur le même dossier).
    doublon = _issue_ouverte_meme_titre(cfg, titre)
    if doublon is not None:
        return jsonify(
            succes=False,
            erreur=f"Une issue portant ce titre est déjà ouverte : #{doublon}"
        )

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
            # Démarrage automatique du watcher (issue #202). Avec l'auto-extinction
            # après inactivité (#200/#201), le watcher du projet peut être éteint au
            # moment où l'on crée une issue : on le rallume ici pour que la tâche
            # soit prise en charge sans étape manuelle. demarrer_watcher(forcer=False)
            # est idempotent (no-op si le watcher tourne déjà). Import différé pour
            # éviter tout cycle d'import entre app.issues et app.watchers.
            #
            # Garde sur les labels : on ne démarre QUE pour les issues for-linux —
            # une issue for-windows est traitée par CCW, rien à lancer côté Linux.
            # watcher_demarre : True = watcher effectivement (re)démarré (il était
            # éteint), False = tournait déjà, None = non applicable (for-windows) ou
            # échec silencieux du démarrage. Un échec ici ne doit JAMAIS transformer
            # une création d'issue réussie en erreur : try/except large qui retombe
            # sur None.
            watcher_demarre = None
            if "for-linux" in labels.split(","):
                try:
                    from app.watchers import demarrer_watcher
                    demarre, _pid = demarrer_watcher(cfg, forcer=False)
                    watcher_demarre = demarre
                except Exception:
                    watcher_demarre = None
            return jsonify(succes=True, url=res.stdout.strip(),
                           watcher_demarre=watcher_demarre)
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


def _branche_courante(rep: Path) -> str | None:
    """Nom de la branche actuellement extraite dans `rep` (ex. 'master', 'main'),
    ou None si indéterminé (dépôt en detached HEAD, git absent…). Sert à
    construire l'URL raw.githubusercontent.com : on déduit la branche
    DYNAMIQUEMENT plutôt que de supposer master/main (issue #191)."""
    try:
        res = subprocess.run(
            ["git", "-C", str(rep), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        nom = res.stdout.strip()
        if res.returncode == 0 and nom and nom != "HEAD":
            return nom
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def joindre_image():
    """Reçoit une image (PNG/JPEG), la committe dans issue-attachments/ du dépôt
    du projet cible, la POUSSE sur origin, et retourne l'URL
    raw.githubusercontent.com correspondante à insérer dans le corps de l'issue
    (issue #191).

    Exception « push » assumée et documentée (§18 de BRIDGE_AGENT_DOC.md) : la
    règle « CCL ne pousse jamais » ne s'applique PAS ici. C'est ALAIN qui agit
    via l'interface (upload manuel de sa part), exactement comme s'il committait
    et poussait l'image lui-même en ligne de commande — CCL/le watcher n'est pas
    l'auteur de ce push.

    Reçue en multipart/form-data : champ fichier `image` + champ `projet`.
    En cas d'échec (type invalide, taille dépassée, pas un dépôt git, push
    refusé…) : message clair et AUCUNE URL retournée, pour ne jamais insérer une
    URL cassée dans le corps de l'issue."""
    nom_projet = (request.form.get("projet") or "").strip()
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable."), 404

    fichier = request.files.get("image")
    if fichier is None or not fichier.filename:
        return jsonify(succes=False, erreur="Aucun fichier reçu."), 400

    # Validation du type : Content-Type déclaré ET magic bytes (on ne se fie pas
    # au seul en-tête du navigateur, trivial à falsifier).
    mimetype = (fichier.mimetype or "").lower()
    if mimetype not in TYPES_IMAGE_ACCEPTES:
        return jsonify(succes=False,
                       erreur=f"Type non supporté : seuls {formats_image_acceptes()['texte']} "
                              "sont acceptés."), 400

    # Lecture complète en mémoire pour vérifier taille et signature avant écriture
    # (les images d'interface restent petites : limite 5 Mo).
    donnees = fichier.read()
    if not donnees:
        return jsonify(succes=False, erreur="Fichier vide."), 400
    if len(donnees) > TAILLE_MAX_IMAGE:
        mo = len(donnees) / (1024 * 1024)
        return jsonify(succes=False,
                       erreur=f"Image trop lourde ({mo:.1f} Mo) — limite : 5 Mo."), 400
    if not any(donnees.startswith(sig) for sig in SIGNATURES_IMAGE[mimetype]):
        return jsonify(succes=False,
                       erreur="Le contenu du fichier ne correspond pas à une image "
                              f"{formats_image_acceptes()['texte']}."), 400

    # Le dépôt doit exister localement ET être un dépôt git (sinon commit/push
    # impossibles : message clair plutôt qu'un échec silencieux).
    rep = cfg.rep_travail
    if not rep.is_dir():
        return jsonify(succes=False,
                       erreur=f"Répertoire de travail introuvable pour « {cfg.nom} »."), 400
    if not _est_depot_git(rep):
        return jsonify(succes=False,
                       erreur=f"Le répertoire de « {cfg.nom} » n'est pas un dépôt git "
                              "(commit/push impossibles)."), 400

    # Nom de fichier horodaté (anti-collision) : 20260720-153045-<nom_original>.ext.
    # secure_filename neutralise chemins et caractères douteux ; on force
    # l'extension canonique du type MIME validé pour cohérence.
    ext = TYPES_IMAGE_ACCEPTES[mimetype]
    base = secure_filename(fichier.filename) or "image"
    base = os.path.splitext(base)[0] or "image"
    horodatage = datetime.now().strftime("%Y%m%d-%H%M%S")
    nom_fichier = f"{horodatage}-{base}{ext}"

    dossier = rep / DOSSIER_PIECES_JOINTES
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        (dossier / nom_fichier).write_bytes(donnees)
    except OSError as e:
        return jsonify(succes=False, erreur=f"Écriture du fichier impossible : {e}"), 500

    chemin_relatif = f"{DOSSIER_PIECES_JOINTES}/{nom_fichier}"

    # Branche courante déduite dynamiquement (master/main/autre) AVANT le push,
    # pour construire l'URL raw ; sans elle on ne pourrait pas garantir une URL
    # correcte, on refuse donc plutôt que de deviner.
    branche = _branche_courante(rep)
    if not branche:
        _nettoyer_fichier(dossier / nom_fichier)
        return jsonify(succes=False,
                       erreur="Branche git indéterminée (detached HEAD ?) — "
                              "impossible de construire l'URL de l'image."), 400

    # git add + commit. Un échec ici laisse le fichier sur disque non suivi :
    # on le retire pour ne pas polluer le répertoire de travail.
    try:
        res_add = subprocess.run(
            ["git", "-C", str(rep), "add", "--", chemin_relatif],
            capture_output=True, text=True, timeout=30
        )
        if res_add.returncode != 0:
            _nettoyer_fichier(dossier / nom_fichier)
            return jsonify(succes=False,
                           erreur=f"git add a échoué : {res_add.stderr.strip()}"), 500
        res_commit = subprocess.run(
            ["git", "-C", str(rep), "commit",
             "-m", f"Pièce jointe issue : {nom_fichier}", "--", chemin_relatif],
            capture_output=True, text=True, timeout=30
        )
        if res_commit.returncode != 0:
            return jsonify(succes=False,
                           erreur=f"git commit a échoué : "
                                  f"{res_commit.stderr.strip() or res_commit.stdout.strip()}"), 500
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, erreur="Timeout git (add/commit).")
    except FileNotFoundError:
        return jsonify(succes=False, erreur="git introuvable dans le PATH."), 500
    except Exception as e:
        return jsonify(succes=False, erreur=str(e)), 500

    # git push — l'action « exceptionnelle » assumée (voir docstring). En cas
    # d'échec (réseau, conflit, pas de remote, pas de droits), on NE retourne
    # PAS d'URL : elle serait cassée tant que le commit n'est pas sur origin.
    # Le commit reste en local (comme un backup), Alain peut le pousser plus tard.
    try:
        res_push = subprocess.run(
            ["git", "-C", str(rep), "push", "origin", f"HEAD:{branche}"],
            capture_output=True, text=True, timeout=120
        )
        if res_push.returncode != 0:
            return jsonify(
                succes=False,
                erreur="Image committée localement mais push refusé — "
                       "aucune URL insérée (l'image ne s'afficherait pas). "
                       f"Détail git : {res_push.stderr.strip() or 'échec du push'}"
            ), 502
    except subprocess.TimeoutExpired:
        return jsonify(succes=False,
                       erreur="Timeout du push git (>120s) — aucune URL insérée."), 504
    except FileNotFoundError:
        return jsonify(succes=False, erreur="git introuvable dans le PATH."), 500
    except Exception as e:
        return jsonify(succes=False, erreur=str(e)), 500

    # Push réussi : l'URL raw pointe vers le fichier désormais présent sur origin.
    url = (f"https://raw.githubusercontent.com/{cfg.depot}/"
           f"{branche}/{chemin_relatif}")
    return jsonify(succes=True, url=url, nom_fichier=nom_fichier)


def _nettoyer_fichier(chemin: Path) -> None:
    """Supprime best-effort un fichier qu'on renonce à committer (échec en amont),
    pour ne pas laisser de fichier non suivi dans le répertoire de travail."""
    try:
        chemin.unlink(missing_ok=True)
    except OSError:
        pass


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
    """Retourne les issues ouvertes destinées à un agent (labels for-linux OU
    for-windows), en attente de traitement par le watcher. La liste peut être
    vide.

    Note (issue #183) : on inclut aussi for-windows (CCW), pas seulement
    for-linux (CCL), afin que les badges de décompte et d'estimation prédictive
    s'affichent aussi pour les issues CCW. `gh issue list --label` combine
    plusieurs --label en ET logique ; or for-linux et for-windows sont
    mutuellement exclusifs (§16), donc un seul appel ne peut jamais les
    retourner ensemble. On fait donc DEUX appels gh (un par label) puis on
    fusionne — approche simple et fiable, indépendante de la syntaxe de
    recherche gh.

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
    # Un appel gh par label (for-linux, for-windows) puis fusion : voir docstring.
    issues = []
    vus = set()
    try:
        for label in ("for-linux", "for-windows"):
            res = subprocess.run(
                ["gh", "issue", "list",
                 "--repo",  cfg.depot,
                 "--label", label,
                 "--state", "open",
                 "--json",  "number,title,labels,body"],
                capture_output=True, text=True, timeout=30
            )
            if res.returncode != 0:
                return jsonify(erreur=res.stderr.strip() or "Erreur de gh."), 502
            for it in json.loads(res.stdout or "[]"):
                # Dédoublonnage par numéro : une issue portant les deux labels
                # (cas rare, non nominal) ne doit apparaître qu'une fois.
                if it.get("number") in vus:
                    continue
                vus.add(it.get("number"))
                issues.append(it)
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
    # for-linux/for-windows sont rares (souvent 0-3), le surcoût reste modéré.
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

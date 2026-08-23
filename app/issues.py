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
import unicodedata
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
                     _est_depot_git, LABEL_ECRITURE, LABEL_SCRATCH,
                     LABEL_NOTIF_PC, LABEL_NOTIF_GSM, LABEL_NOTIF_TOUS)

# Racine du projet (dossier parent du package app/).
DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent

# Consignes injectées (architecture à trois couches, issues #209/#211) : depuis
# #211 la lecture des consignes (consignes/globales.md, type_<type>.md,
# projet_<projet>.md) et leur injection ont été DÉPLACÉES dans watcher.py, où
# elles sont ajoutées au prompt CCL au moment du traitement (couverture
# universelle, tous chemins de création). app/issues.py ne les réinjecte donc
# plus dans le corps de l'issue GitHub. Voir watcher.py::_consignes_injectees et
# §12.1 de BRIDGE_AGENT_DOC.md.

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

# ─── Pièces jointes image des issues (issue #191, isolation #248) ─────────────
# Dossier (à la racine de la branche dédiée NOM_BRANCHE_PIECES_JOINTES, PAS de
# la branche de travail) où sont committées les images jointes à une issue,
# puis référencées dans son corps via une URL raw.githubusercontent.com. Voir
# joindre_image() plus bas et §18 de BRIDGE_AGENT_DOC.md pour le mécanisme
# complet et l'exception « push par Alain ».
DOSSIER_PIECES_JOINTES = "issue-attachments"
# Branche ORPHELINE (aucun ancêtre commun avec master/main) dédiée aux pièces
# jointes (issue #248) : le push de joindre_image() ne publie QUE cette
# référence, jamais la branche de travail — un push sur HEAD:<branche> aurait
# emporté avec lui tout commit local non relu par Alain (violation du
# garde-fou « CCL ne pousse jamais »). Le commit est construit par plomberie
# git (hash-object/read-tree/update-index/write-tree/commit-tree) SANS toucher
# à l'arbre de travail ni à HEAD du dépôt courant : un watcher peut être en
# train d'y exécuter une tâche mode_write au même moment.
NOM_BRANCHE_PIECES_JOINTES = "pieces-jointes"
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


# Table de correspondance MODE (issue #326) : {valeur du radio formulaire →
# (libellé français écrit dans le champ d'en-tête | MODE | …, label GitHub
# posé — None si aucun)}. Le mode n'est plus un booléen en dur (autrefois
# `"ÉCRITURE" if mode == "ecriture" else "lecture seule"` + `if mode ==
# "ecriture": labels.append("mode_write")`) : construire_body et
# construire_labels lisent tous deux cette table, si bien qu'un futur 4e mode
# ne demande qu'une ligne ici.
#
# lecture_active (label mode_scratch, issue #327) : écriture confinée à
# /tmp/bridge_scratch_<projet>/ côté watcher (jamais dans le projet), utile
# aux linters/outils exigeant un vrai fichier de config sur disque. Voir
# watcher.py::_deduire_mode / MODE_LECTURE_ACTIVE pour l'implémentation
# complète (garde-fous niveau 1 prompt + niveau 2 empreinte REP_TRAVAIL).
MODES = {
    "lecture":        ("lecture", None),
    "lecture_active": ("lecture active", "mode_scratch"),
    "ecriture":       ("écriture", "mode_write"),
}


def construire_body(data: dict) -> str:
    """Construit le body markdown depuis les champs du formulaire : tableau
    d'en-tête + corps rédigé par Claude Chat.

    Note (issue #211) : les consignes à trois couches (globales / type / projet)
    ne sont PLUS injectées dans le corps de l'issue ici. Elles le sont désormais
    dans le PROMPT donné à CCL par watcher.py::_consignes_injectees (au moment du
    traitement), sur le modèle de FICHIER_CONTEXTE/CONTEXTE.md — couverture
    universelle quel que soit le chemin de création de l'issue (formulaire web,
    `gh issue create` d'un chef, création manuelle GitHub). Source unique de
    vérité côté watcher, plus de double injection. Voir §12.1 du DOC."""
    mode, _         = MODES.get(data.get("mode"), MODES["lecture"])
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

    entete = "\n".join(lignes)
    # Ordre final : en-tête → corps. Les consignes ne sont plus empilées ici
    # (déplacées dans le prompt CCL, issue #211). Corps vide omis pour ne pas
    # laisser de ligne blanche superflue.
    parties = [p for p in (entete, corps) if p]
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
    _, label_mode = MODES.get(data.get("mode"), MODES["lecture"])
    if label_mode:
        labels.append(label_mode)
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


def joindre_image():
    """Reçoit une image (PNG/JPEG/GIF) et la publie sur la branche ORPHELINE
    dédiée `NOM_BRANCHE_PIECES_JOINTES` (« pieces-jointes »), sans aucun lien
    d'ancêtre avec master/main et sans jamais toucher à l'arbre de travail ni à
    HEAD du dépôt du projet cible. Retourne l'URL raw.githubusercontent.com
    correspondante à insérer dans le corps de l'issue (issues #191, #248).

    Isolation du push (issue #248) : la version initiale (#191) poussait sur
    `HEAD:<branche_courante>` — or git ne peut pas publier un commit sans ses
    ancêtres, ce qui emportait TOUS les commits locaux non encore relus par
    Alain sur la branche de travail (brèche dans « CCL ne pousse jamais »).
    Le commit est désormais construit par PLOMBERIE git (hash-object, puis
    read-tree/update-index/write-tree sur un index temporaire isolé via
    GIT_INDEX_FILE, puis commit-tree) sur une branche qui ne contient QUE
    `issue-attachments/` : aucun commit de code ne peut être emporté, par
    construction. Le fichier n'est jamais écrit dans rep_travail (le blob est
    créé directement en base git depuis un fichier temporaire hors dépôt) : un
    watcher peut être en train d'exécuter une tâche mode_write dans ce même
    clone au moment de l'upload.

    Exception « push » assumée et documentée (§18.2 de BRIDGE_AGENT_DOC.md) :
    c'est ALAIN qui agit via l'interface (upload manuel de sa part), et ce push
    ne publie plus jamais de code — seulement des images sur une branche sans
    aucun rapport avec le travail de l'agent.

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
    chemin_relatif = f"{DOSSIER_PIECES_JOINTES}/{nom_fichier}"

    # Fichier TEMPORAIRE hors du dépôt (jamais écrit dans rep_travail) : sert
    # uniquement de source à `git hash-object`, qui écrit le blob directement
    # dans la base git sans passer par l'arbre de travail.
    try:
        tmp_fd, tmp_chemin = tempfile.mkstemp(prefix="piece-jointe-", suffix=ext)
        with os.fdopen(tmp_fd, "wb") as f:
            f.write(donnees)
    except OSError as e:
        return jsonify(succes=False, erreur=f"Écriture du fichier temporaire impossible : {e}"), 500

    try:
        return _publier_piece_jointe(rep, cfg, tmp_chemin, chemin_relatif, nom_fichier)
    finally:
        _nettoyer_fichier(Path(tmp_chemin))


def _publier_piece_jointe(rep: Path, cfg, tmp_chemin: str, chemin_relatif: str,
                          nom_fichier: str):
    """Construit par plomberie git un commit contenant uniquement
    `chemin_relatif` (blob lu depuis `tmp_chemin`) sur la branche orpheline
    NOM_BRANCHE_PIECES_JOINTES, le pousse, et retourne la réponse Flask
    (URL raw si succès, erreur explicite sinon). N'écrit jamais dans l'arbre de
    travail de `rep` ni ne change HEAD (issue #248) : seuls `.git/objects` (via
    hash-object/write-tree/commit-tree) et un fichier d'index TEMPORAIRE
    (GIT_INDEX_FILE, jamais l'index réel du dépôt) sont utilisés."""
    # 1. Tip actuel de la branche pieces-jointes sur origin, si elle existe déjà
    # (fetch d'une seule réf nommée : ne touche à aucune référence locale, à
    # l'inverse d'un `git pull`). Si la branche n'existe pas encore côté
    # origin, le fetch échoue et on part d'un commit RACINE (sans parent) —
    # c'est la création de la branche à la première pièce jointe publiée.
    try:
        res_fetch = subprocess.run(
            ["git", "-C", str(rep), "fetch", "origin", NOM_BRANCHE_PIECES_JOINTES],
            capture_output=True, text=True, timeout=60
        )
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, erreur="Timeout du fetch git (branche "
                       f"{NOM_BRANCHE_PIECES_JOINTES})."), 504
    except FileNotFoundError:
        return jsonify(succes=False, erreur="git introuvable dans le PATH."), 500

    parent_sha = None
    if res_fetch.returncode == 0:
        res_rev = subprocess.run(
            ["git", "-C", str(rep), "rev-parse", "FETCH_HEAD"],
            capture_output=True, text=True, timeout=10
        )
        if res_rev.returncode == 0 and res_rev.stdout.strip():
            parent_sha = res_rev.stdout.strip()

    # 2. Blob écrit directement dans .git/objects, PAS dans l'arbre de travail.
    try:
        res_hash = subprocess.run(
            ["git", "-C", str(rep), "hash-object", "-w", "--", tmp_chemin],
            capture_output=True, text=True, timeout=30
        )
        if res_hash.returncode != 0:
            return jsonify(succes=False,
                           erreur=f"git hash-object a échoué : {res_hash.stderr.strip()}"), 500
        blob_sha = res_hash.stdout.strip()
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, erreur="Timeout git (hash-object)."), 504

    # 3. Arbre construit sur un index TEMPORAIRE (GIT_INDEX_FILE) — on part du
    # tree du commit parent (read-tree) pour conserver les pièces jointes déjà
    # publiées, puis on ajoute la nouvelle sans jamais toucher à l'index réel
    # du dépôt (donc sans conflit avec un watcher qui y travaillerait).
    tmp_index_fd, tmp_index_chemin = tempfile.mkstemp(prefix="index-pieces-jointes-")
    os.close(tmp_index_fd)
    os.unlink(tmp_index_chemin)  # l'index doit être ABSENT : git le (re)crée au premier accès
    env_index = dict(os.environ, GIT_INDEX_FILE=tmp_index_chemin)
    try:
        if parent_sha:
            res_read = subprocess.run(
                ["git", "-C", str(rep), "read-tree", parent_sha],
                capture_output=True, text=True, timeout=30, env=env_index
            )
            if res_read.returncode != 0:
                return jsonify(succes=False,
                               erreur=f"git read-tree a échoué : {res_read.stderr.strip()}"), 500
        res_upd = subprocess.run(
            ["git", "-C", str(rep), "update-index", "--add", "--cacheinfo",
             f"100644,{blob_sha},{chemin_relatif}"],
            capture_output=True, text=True, timeout=30, env=env_index
        )
        if res_upd.returncode != 0:
            return jsonify(succes=False,
                           erreur=f"git update-index a échoué : {res_upd.stderr.strip()}"), 500
        res_tree = subprocess.run(
            ["git", "-C", str(rep), "write-tree"],
            capture_output=True, text=True, timeout=30, env=env_index
        )
        if res_tree.returncode != 0:
            return jsonify(succes=False,
                           erreur=f"git write-tree a échoué : {res_tree.stderr.strip()}"), 500
        tree_sha = res_tree.stdout.strip()
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, erreur="Timeout git (read-tree/update-index/write-tree)."), 504
    finally:
        _nettoyer_fichier(Path(tmp_index_chemin))

    # 4. Commit-tree : commit racine si première publication, sinon enfant du
    # tip actuel de la branche (parent_sha) — jamais de lien avec master/main.
    args_commit = ["git", "-C", str(rep), "commit-tree", tree_sha]
    if parent_sha:
        args_commit += ["-p", parent_sha]
    args_commit += ["-m", f"Pièce jointe issue : {nom_fichier}"]
    try:
        res_commit = subprocess.run(args_commit, capture_output=True, text=True, timeout=30)
        if res_commit.returncode != 0:
            return jsonify(succes=False,
                           erreur=f"git commit-tree a échoué : {res_commit.stderr.strip()}"), 500
        commit_sha = res_commit.stdout.strip()
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, erreur="Timeout git (commit-tree)."), 504

    # 5. Push de CETTE SEULE référence — jamais HEAD, jamais la branche de
    # travail. Si `parent_sha` a bougé entre temps côté origin (course), ce
    # push est rejeté nativement comme non-fast-forward : aucune écrasement
    # silencieux possible.
    try:
        res_push = subprocess.run(
            ["git", "-C", str(rep), "push", "origin",
             f"{commit_sha}:refs/heads/{NOM_BRANCHE_PIECES_JOINTES}"],
            capture_output=True, text=True, timeout=120
        )
        if res_push.returncode != 0:
            return jsonify(
                succes=False,
                erreur=f"Push refusé sur la branche {NOM_BRANCHE_PIECES_JOINTES} — "
                       "aucune URL insérée (l'image ne s'afficherait pas). "
                       f"Détail git : {res_push.stderr.strip() or 'échec du push'}"
            ), 502
    except subprocess.TimeoutExpired:
        return jsonify(succes=False,
                       erreur="Timeout du push git (>120s) — aucune URL insérée."), 504
    except FileNotFoundError:
        return jsonify(succes=False, erreur="git introuvable dans le PATH."), 500

    # Push réussi : l'URL raw pointe vers la branche pieces-jointes (fixe),
    # jamais vers la branche de travail du projet.
    url = (f"https://raw.githubusercontent.com/{cfg.depot}/"
           f"{NOM_BRANCHE_PIECES_JOINTES}/{chemin_relatif}")
    return jsonify(succes=True, url=url, nom_fichier=nom_fichier)


def _nettoyer_fichier(chemin: Path) -> None:
    """Supprime best-effort un fichier qu'on renonce à committer (échec en amont),
    pour ne pas laisser de fichier non suivi dans le répertoire de travail."""
    try:
        chemin.unlink(missing_ok=True)
    except OSError:
        pass


LIMITE_ISSUES_DEFAUT = 30
LIMITE_ISSUES_MIN = 1
LIMITE_ISSUES_MAX = 50


def _filtrer_issues_bridge(issues: list) -> list:
    """Ignore silencieusement les issues ne portant ni 'for-linux' ni
    'for-windows' (issue #478, pendant côté affichage du garde-fou #477 dans
    watcher.py::lister_issues). Certains dépôts (ex. FF_Galerie) génèrent
    leurs propres issues applicatives qui n'ont aucun rapport avec le bridge
    et ne doivent pas apparaître dans la fenêtre Résultats, qu'elles soient
    ouvertes ou fermées."""
    return [
        i for i in issues
        if any(l.get("name", "") in ("for-linux", "for-windows")
               for l in i.get("labels", []))
    ]


def _limite_issues_requete():
    """Lit le paramètre de requête `limite` (issue #271) : entier borné entre
    LIMITE_ISSUES_MIN et LIMITE_ISSUES_MAX. Toute valeur absente ou invalide
    (non fournie, non entière, hors bornes) retombe sur LIMITE_ISSUES_DEFAUT —
    comportement strictement inchangé pour tout appelant qui ne passe pas ce
    paramètre."""
    brut = request.args.get("limite")
    if brut is None:
        return LIMITE_ISSUES_DEFAUT
    try:
        valeur = int(brut)
    except (TypeError, ValueError):
        return LIMITE_ISSUES_DEFAUT
    return max(LIMITE_ISSUES_MIN, min(LIMITE_ISSUES_MAX, valeur))


def issues_liste(nom_projet):
    """Retourne les dernières issues (tous états) du projet via gh, jusqu'à
    LIMITE_ISSUES_DEFAUT (30) sauf si le paramètre `limite` en fournit une
    autre (issue #271)."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    limite = _limite_issues_requete()
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo",  cfg.depot,
             "--state", "all",
             "--limit", str(limite),
             "--json",  "number,title,state,labels,createdAt"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return jsonify(erreur=res.stderr.strip() or "Erreur de gh."), 502
        return jsonify(_filtrer_issues_bridge(json.loads(res.stdout or "[]")))
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (gh n'a pas répondu en 30s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="gh introuvable dans le PATH."), 500
    except Exception as e:
        return jsonify(erreur=str(e)), 500


def _normaliser_recherche(texte: str) -> str:
    """Normalise un texte pour une comparaison de titre insensible à la casse
    ET aux accents (issue #321, ex. « ecran » doit trouver « Écran ») :
    décomposition Unicode (NFKD) qui sépare les diacritiques des lettres de
    base, suppression de ces diacritiques, puis casefold (plus robuste que
    .lower() pour une comparaison insensible à la casse)."""
    decompose = unicodedata.normalize('NFKD', texte or '')
    sans_accents = ''.join(c for c in decompose if not unicodedata.combining(c))
    return sans_accents.casefold()


def recherche_issues(nom_projet):
    """Recherche par TITRE (jamais le corps) dans les issues d'un projet,
    insensible à la casse et aux accents (issue #321). Réutilise la même
    logique gh que issues_liste : --state all (une issue déjà fermée/done est
    justement ce qu'on cherche à retrouver, cf. doublon #315/#316), --limit
    borné par _limite_issues_requete (portée de recherche PAR PROJET,
    INDÉPENDANTE de la limite d'affichage de l'onglet). Le filtrage se fait
    ici côté serveur, sur le titre uniquement."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
    limite = _limite_issues_requete()
    titre_cherche = _normaliser_recherche(request.args.get("titre", ""))
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo",  cfg.depot,
             "--state", "all",
             "--limit", str(limite),
             "--json",  "number,title,state,labels,createdAt"],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode != 0:
            return jsonify(erreur=res.stderr.strip() or "Erreur de gh."), 502
        toutes = json.loads(res.stdout or "[]")
    except subprocess.TimeoutExpired:
        return jsonify(erreur="Timeout (gh n'a pas répondu en 30s)."), 504
    except FileNotFoundError:
        return jsonify(erreur="gh introuvable dans le PATH."), 500
    except Exception as e:
        return jsonify(erreur=str(e)), 500
    toutes = _filtrer_issues_bridge(toutes)
    if not titre_cherche:
        return jsonify(toutes)
    filtrees = [it for it in toutes
                if titre_cherche in _normaliser_recherche(it.get("title", ""))]
    return jsonify(filtrees)


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
        and r.get("expiree") is not True
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
        # "scratch" (issue #327) : population de durées distincte de "read", au
        # même titre que "write" — sinon l'estimation d'une issue en lecture
        # active emprunterait à tort la population "read" (mélange de profils
        # de durée hétérogènes, même défaut que celui corrigé côté UI par #326).
        if LABEL_ECRITURE in labels:
            mode = "write"
        elif LABEL_SCRATCH in labels:
            mode = "scratch"
        else:
            mode = "read"
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


# ─── Toggle des labels de notification depuis le panneau flottant (issue #384) ─
# Les labels notif_pc/notif_gsm/notif_tous peuvent être modifiés en cours de
# traitement — le watcher les relit au moment de la clôture (voir LABEL_NOTIF_*
# dans watcher.py). Cette route permet de les basculer sans passer par GitHub.
# Whitelist STRICTE : aucun autre label ne peut être posé/retiré via cette route.
LABELS_NOTIF_AUTORISES = {LABEL_NOTIF_PC, LABEL_NOTIF_GSM, LABEL_NOTIF_TOUS}


def modifier_label_notif():
    """Pose ou retire un label de notification (notif_pc/notif_gsm/notif_tous)
    sur une issue GitHub, depuis le panneau flottant d'actions.

    Paramètres JSON : projet, numero, label, actif (bool). Retourne
    {succes: true} ou {succes: false, erreur: ...}."""
    data       = request.json or {}
    nom_projet = (data.get("projet") or "").strip()
    numero     = data.get("numero")
    label      = (data.get("label") or "").strip()
    actif      = bool(data.get("actif"))

    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    if not str(numero).isdigit():
        return jsonify(succes=False, erreur="Numéro d'issue invalide.")
    if label not in LABELS_NOTIF_AUTORISES:
        return jsonify(succes=False, erreur=f"Label non autorisé : « {label} ».")

    option = "--add-label" if actif else "--remove-label"
    try:
        res = subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", cfg.depot,
             option,   label],
            capture_output=True, text=True, timeout=30
        )
        if res.returncode == 0:
            return jsonify(succes=True)
        return jsonify(succes=False,
                       erreur=res.stderr.strip() or "Erreur inconnue de gh.")
    except subprocess.TimeoutExpired:
        return jsonify(succes=False, erreur="Timeout (gh n'a pas répondu en 30s).")
    except FileNotFoundError:
        return jsonify(succes=False, erreur="gh introuvable dans le PATH.")
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))


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

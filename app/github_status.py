"""app/github_status.py — alerte explicite de panne GitHub (issue #732).

Contexte : pendant un incident GitHub (constaté les 06 et 07/10/2026), les
échecs de `gh` affichés (ex. « Résultats — échec de chargement », erreurs 502)
ne disent pas si la cause est une panne GitHub, la connexion internet locale ou
le jeton — il fallait aller vérifier soi-même la page de statut officielle.

Ce module :
1. classe un échec `gh` (classer_echec_gh) — seulement « panne probable » pour
   un timeout, une erreur réseau ou une réponse 5xx, JAMAIS pour une erreur
   normale (404/401/403/422) ni pour la limite de débit (déjà signalée par le
   bandeau ⚡, app/rate_limit.py) ;
2. interroge, avec un cache serveur ~1 minute (SEUIL_CACHE_S), le résumé public
   de statut de GitHub (summary.json de githubstatus.com, SANS authentification
   — verifier_statut()) et en déduit l'un des trois messages de repli (issue
   #732, §3) ;
3. suit un ÉPISODE de panne (pas une erreur individuelle) : ouvert au premier
   échec classé « panne probable » (signaler_resultat_gh), refermé dès qu'un
   appel gh réussit de nouveau — à la fermeture, une ligne est ajoutée à
   logs/pannes_github.log (non versionné, taille bornée à ~RETENTION_JOURS).

Aucune fonction ici ne lève jamais au point d'appel d'un `gh` SURVEILLÉ : une
erreur de la vérification elle-même (page de statut injoignable, disque plein)
reste interne à ce module et retombe sur le message de repli « injoignable »
— jamais une erreur visible supplémentaire côté appelant (contrainte de
l'issue #732)."""

import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("app.github_status")

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent

URL_STATUT = "https://www.githubstatus.com/api/v2/summary.json"
TIMEOUT_REQUETE_S = 5          # délai court : la vérification ne doit jamais ralentir l'utilisateur
SEUIL_CACHE_S = 60             # au plus une requête vers la page de statut par minute

# Composants du statut GitHub utiles à Bridge_Agent (gh issue list/view/
# create/edit/comment passent tous par l'API REST, sauf de rares appels
# GraphQL — Git Operations couvre en plus les push de joindre_image()).
COMPOSANTS_SURVEILLES = {"Issues", "API Requests", "Git Operations", "Webhooks"}

CHEMIN_JOURNAL = DOSSIER_SCRIPT / "logs" / "pannes_github.log"
CHEMIN_ETAT_EPISODE = DOSSIER_SCRIPT / "logs" / "etat_panne_github.json"
RETENTION_JOURS = 370           # bornage de logs/pannes_github.log : ~un an

GRAVITE_INCIDENT = "incident"
GRAVITE_OK = "ok"
GRAVITE_INJOIGNABLE = "injoignable"

MESSAGE_OK = ("GitHub semble opérationnel : l'erreur vient probablement "
              "de votre connexion ou de votre jeton.")
MESSAGE_INJOIGNABLE = ("GitHub et sa page de statut sont injoignables : "
                        "problème de connexion internet probable.")

CAUSES_LABEL = {
    GRAVITE_INCIDENT: "incident GitHub signalé",
    GRAVITE_OK: "erreur locale (GitHub opérationnel)",
    GRAVITE_INJOIGNABLE: "connexion internet injoignable",
}
CAUSE_INDETERMINEE = "cause indéterminée (jamais vérifiée pendant l'épisode)"

# ─── Classification d'un échec gh (issue #732, §1) ─────────────────────────
# Volontairement fondée sur le MESSAGE D'ERREUR final déjà construit par
# chaque appelant (res.stderr.strip(), "Timeout (gh n'a pas répondu en 30s).",
# "gh introuvable dans le PATH.") plutôt que sur les objets subprocess bruts :
# chaque point d'appel a déjà cette chaîne sous la main (pour jsonify(erreur=
# ...)), ce qui évite de plomber des booléens supplémentaires à travers tous
# les call sites existants.
_RE_HTTP_5XX = re.compile(r"http[^0-9]{0,10}5\d\d", re.IGNORECASE)
_MOTS_RESEAU = (
    "could not resolve host", "connection refused", "connection reset",
    "network is unreachable", "no route to host", "timed out", "timeout",
    "délai dépassé", "temporary failure in name resolution",
    "server misbehaving", "dial tcp", "tls handshake", "connection timed out",
    "eof",
)


def classer_echec_gh(message: str) -> bool:
    """True si `message` (texte d'erreur déjà construit par l'appelant) peut
    venir d'une panne GitHub ou d'un problème réseau — timeout, connexion
    impossible, réponse 5xx. False pour une erreur normale (404/401/403/422),
    la limite de débit, ou `gh` absent du PATH (pas un problème GitHub)."""
    texte = (message or "").lower()
    if "introuvable dans le path" in texte:
        return False
    if _RE_HTTP_5XX.search(texte):
        return True
    return any(mot in texte for mot in _MOTS_RESEAU)


# ─── Interrogation de la page de statut (issue #732, §2) ───────────────────

def _interroger_page_statut(timeout_s: float = TIMEOUT_REQUETE_S):
    """GET summary.json, sans authentification. Retourne (donnees, True) en
    succès, ou (None, False) pour TOUTE erreur (réseau, HTTP, JSON) — ne lève
    jamais."""
    try:
        with urllib.request.urlopen(URL_STATUT, timeout=timeout_s) as rep:
            return json.loads(rep.read().decode("utf-8")), True
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        log.debug(f"page de statut GitHub injoignable : {e}")
        return None, False


def extraire_resume_statut(data: dict) -> dict:
    """Résumé pur (testable sans réseau) de summary.json : indicateur global,
    état des composants utiles à Bridge_Agent, incidents en cours."""
    indicateur = ((data or {}).get("status") or {}).get("indicator", "none")
    composants = [
        {"nom": c.get("name"), "statut": c.get("status")}
        for c in (data or {}).get("components") or []
        if c.get("name") in COMPOSANTS_SURVEILLES
    ]
    incidents = [
        {"nom": i.get("name"), "statut": i.get("status")}
        for i in (data or {}).get("incidents") or []
    ]
    return {"indicateur": indicateur, "composants": composants, "incidents": incidents}


def calculer_message_statut(resume: dict | None, page_accessible: bool) -> dict:
    """Les trois messages de repli (issue #732, §3), par ordre de gravité —
    pure, testable avec un résumé simulé. Retourne {gravite, message,
    composants, incident_nom}."""
    if not page_accessible or resume is None:
        return {"gravite": GRAVITE_INJOIGNABLE, "message": MESSAGE_INJOIGNABLE,
                "composants": [], "incident_nom": None}

    composants_touches = [c for c in resume.get("composants") or []
                            if c.get("statut") != "operational"]
    incidents = resume.get("incidents") or []

    if incidents or resume.get("indicateur", "none") != "none" or composants_touches:
        if incidents:
            noms_incidents = ", ".join(i["nom"] for i in incidents if i.get("nom"))
        elif composants_touches:
            noms_incidents = ", ".join(c["nom"] for c in composants_touches if c.get("nom"))
        else:
            noms_incidents = "GitHub"
        message = f"GitHub signale un incident : {noms_incidents}"
        if composants_touches:
            etats = ", ".join(f"{c['nom']} : {c['statut']}" for c in composants_touches)
            message += f" (composants concernés — {etats})"
        return {"gravite": GRAVITE_INCIDENT, "message": message,
                "composants": composants_touches, "incident_nom": noms_incidents}

    return {"gravite": GRAVITE_OK, "message": MESSAGE_OK,
            "composants": [], "incident_nom": None}


_verrou_cache = threading.Lock()
_cache = {"resume": None, "page_accessible": None, "epoch": 0.0}


def verifier_statut(force: bool = False) -> dict:
    """Résultat courant (gravite/message/composants/incident_nom), avec un
    cache serveur d'environ une minute (SEUIL_CACHE_S) : au plus une requête
    réseau vers githubstatus.com par minute, quel que soit le nombre d'appels
    gh en échec entre-temps. Ne lève jamais."""
    with _verrou_cache:
        maintenant = time.time()
        if not force and _cache["epoch"] and (maintenant - _cache["epoch"]) < SEUIL_CACHE_S:
            resume, page_accessible = _cache["resume"], _cache["page_accessible"]
        else:
            try:
                data, page_accessible = _interroger_page_statut()
                resume = extraire_resume_statut(data) if data is not None else None
            except Exception as e:  # jamais d'erreur visible supplémentaire (contrainte §"Contraintes")
                log.warning(f"vérification du statut GitHub en échec : {e}")
                resume, page_accessible = None, False
            _cache["resume"] = resume
            _cache["page_accessible"] = page_accessible
            _cache["epoch"] = maintenant

    resultat = calculer_message_statut(resume, page_accessible)
    _maj_cause_episode(resultat)
    return resultat


# ─── Épisodes de panne (issue #732, §4-5) ───────────────────────────────────
# Persistés sur disque (comme etat_rate_limit.py) pour survivre à un redémarrage
# de new_issue.py en cours d'épisode — sans quoi son début, et donc sa durée,
# seraient perdus au redémarrage demandé après la fusion de cette issue.

_verrou_episode = threading.Lock()


def _lire_episode() -> dict | None:
    try:
        return json.loads(CHEMIN_ETAT_EPISODE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _ecrire_episode(episode: dict | None) -> None:
    try:
        CHEMIN_ETAT_EPISODE.parent.mkdir(parents=True, exist_ok=True)
        if episode is None:
            CHEMIN_ETAT_EPISODE.unlink(missing_ok=True)
            return
        tmp = CHEMIN_ETAT_EPISODE.with_name(CHEMIN_ETAT_EPISODE.name + f".tmp{os.getpid()}")
        tmp.write_text(json.dumps(episode, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CHEMIN_ETAT_EPISODE)
    except OSError as e:
        log.warning(f"écriture de {CHEMIN_ETAT_EPISODE.name} impossible : {e}")


def _maj_cause_episode(resultat: dict) -> None:
    """Met à jour la DERNIÈRE cause connue d'un épisode en cours (sans changer
    son début) — appelée après chaque verifier_statut(), y compris celles
    déclenchées par le polling JS toutes les 60s pendant l'incident."""
    with _verrou_episode:
        episode = _lire_episode()
        if episode is None:
            return
        episode["derniere_gravite"] = resultat["gravite"]
        episode["incident_nom"] = resultat.get("incident_nom")
        episode["composants"] = resultat.get("composants") or []
        _ecrire_episode(episode)


def episode_en_cours() -> dict | None:
    """Épisode de panne actuellement ouvert, ou None — utilisé par la route
    /github-statut pour signaler `panne` au navigateur."""
    with _verrou_episode:
        return _lire_episode()


def signaler_resultat_gh(succes: bool, *, panne_probable: bool = False, origine: str = "") -> None:
    """À appeler juste après CHAQUE appel gh d'un point d'entrée surveillé —
    jamais bloquant, AUCUNE requête réseau ici (seulement lecture/écriture
    d'un petit fichier JSON local). Ouvre un épisode de panne au premier échec
    classé `panne_probable` (classer_echec_gh), le referme dès qu'un appel gh
    réussit de nouveau : UNE ligne de logs/pannes_github.log par épisode,
    jamais par erreur individuelle (issue #732, §5)."""
    try:
        with _verrou_episode:
            episode = _lire_episode()
            if succes:
                if episode is not None:
                    _fermer_episode(episode)
                return
            if panne_probable and episode is None:
                _ouvrir_episode(origine)
    except Exception as e:
        log.warning(f"suivi d'épisode de panne GitHub en échec, sans impact "
                    f"sur l'appel gh lui-même ({origine}) : {e}")


def _ouvrir_episode(origine: str) -> None:
    episode = {
        "debut_epoch": time.time(),
        "origine": origine,
        "derniere_gravite": None,
        "incident_nom": None,
        "composants": [],
    }
    _ecrire_episode(episode)
    log.info(f"Épisode de panne GitHub ouvert (origine : {origine or '?'}).")


def _fermer_episode(episode: dict) -> None:
    fin_epoch = time.time()
    debut_epoch = episode.get("debut_epoch", fin_epoch)
    duree_s = max(0.0, fin_epoch - debut_epoch)
    gravite = episode.get("derniere_gravite")
    cause = CAUSES_LABEL.get(gravite, CAUSE_INDETERMINEE)
    ligne = formater_ligne_journal(debut_epoch, fin_epoch, duree_s, cause,
                                    episode.get("incident_nom"), episode.get("composants") or [])
    _ecrire_ligne_journal(ligne)
    _ecrire_episode(None)
    log.info(f"Épisode de panne GitHub refermé ({cause}, durée {duree_s:.0f}s).")


# ─── Journal des pannes (issue #732, §5) ────────────────────────────────────
# Une ligne texte par épisode, champs "cle=valeur" séparés par " | " — format
# simple, lisible à l'œil et par scripts/resume_pannes_github.py sans
# dépendance JSON (un épisode = une ligne, jamais de structure imbriquée).

def formater_ligne_journal(debut_epoch, fin_epoch, duree_s, cause, incident_nom, composants) -> str:
    debut_iso = datetime.fromtimestamp(debut_epoch, tz=timezone.utc).isoformat(timespec="seconds")
    fin_iso = datetime.fromtimestamp(fin_epoch, tz=timezone.utc).isoformat(timespec="seconds")
    noms_composants = ", ".join(c.get("nom", "?") for c in composants) if composants else ""
    champs = [
        f"debut={debut_iso}",
        f"fin={fin_iso}",
        f"duree_s={round(duree_s)}",
        f"cause={cause}",
        f"incident={incident_nom or ''}",
        f"composants={noms_composants}",
    ]
    return " | ".join(champs)


def parser_ligne_journal(ligne: str) -> dict | None:
    """Inverse de formater_ligne_journal — None si la ligne est mal formée
    (jamais levé). Réutilisée par scripts/resume_pannes_github.py."""
    champs = {}
    for partie in ligne.strip().split(" | "):
        if "=" not in partie:
            return None
        cle, _, valeur = partie.partition("=")
        champs[cle] = valeur
    if not {"debut", "duree_s", "cause"} <= champs.keys():
        return None
    return champs


def _purger_anciennes_lignes(lignes: list, maintenant_epoch: float) -> list:
    """Conserve ~RETENTION_JOURS de recul (taille bornée, issue #732, §5) —
    une ligne mal formée ou sans date lisible est conservée plutôt que perdue
    sans raison."""
    seuil = maintenant_epoch - RETENTION_JOURS * 86400
    gardees = []
    for ligne in lignes:
        champs = parser_ligne_journal(ligne)
        if champs is None:
            gardees.append(ligne)
            continue
        try:
            epoch = datetime.fromisoformat(champs["debut"]).timestamp()
        except ValueError:
            gardees.append(ligne)
            continue
        if epoch >= seuil:
            gardees.append(ligne)
    return gardees


def _ecrire_ligne_journal(ligne: str) -> None:
    try:
        CHEMIN_JOURNAL.parent.mkdir(parents=True, exist_ok=True)
        lignes = []
        if CHEMIN_JOURNAL.exists():
            lignes = CHEMIN_JOURNAL.read_text(encoding="utf-8").splitlines()
        lignes = _purger_anciennes_lignes(lignes, time.time())
        lignes.append(ligne)
        tmp = CHEMIN_JOURNAL.with_name(CHEMIN_JOURNAL.name + f".tmp{os.getpid()}")
        tmp.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        os.replace(tmp, CHEMIN_JOURNAL)
    except OSError as e:
        log.warning(f"écriture de {CHEMIN_JOURNAL.name} impossible : {e}")


# ─── Route Flask ─────────────────────────────────────────────────────────────

def route_statut_github():
    """GET /github-statut — statut courant + épisode de panne en cours (le
    cas échéant). Appelée par le JS à la réception d'un échec gh classé
    `panne_probable`, puis toutes les 60s tant qu'un épisode reste ouvert
    (issue #732, §4). Le cache serveur ~60s (verifier_statut) garantit qu'une
    rafale d'appels gh en échec ne déclenche jamais plus d'une requête réseau
    par minute vers githubstatus.com."""
    from flask import jsonify
    resultat = verifier_statut()
    episode = episode_en_cours()
    return jsonify(
        panne=episode is not None,
        gravite=resultat["gravite"],
        message=resultat["message"],
        composants=resultat["composants"],
        incident_nom=resultat["incident_nom"],
    )

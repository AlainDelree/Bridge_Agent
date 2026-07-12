#!/usr/bin/env python3
"""
new_issue.py — Interface web de création d'issues pour le bridge inter-agents.
Lit les configs configs/*.conf, propose un formulaire pour chaque projet.

Usage :
    python3 new_issue.py                  # mode local (127.0.0.1, HTTP, sans SSL)
    python3 new_issue.py --externe        # exposition réseau (0.0.0.0, HTTPS + mdp)
    python3 new_issue.py --port 5100
    python3 new_issue.py --no-browser
"""

import argparse
import getpass
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import webbrowser
from functools import wraps
from pathlib import Path
from threading import Thread, Timer

from flask import (Response, current_app, jsonify, redirect, render_template,
                   render_template_string, request, session,
                   stream_with_context, url_for)

# Partage du lecteur de config avec watcher.py (même dossier).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from watcher import Config, charger_config  # noqa: E402

# Fabrique de l'application et accesseurs à l'état partagé (app.config).
from app import create_app, etat  # noqa: E402

DOSSIER_SCRIPT = Path(__file__).resolve().parent

# Instance Flask créée au démarrage (main) via create_app(). Déclarée ici pour
# permettre les décorateurs @app.route au niveau module — l'objet est affecté
# avant d'enregistrer les routes.
app = None


# ─── Cycle de vie serveur ↔ onglet navigateur ────────────────────────────────
# Le navigateur émet un heartbeat (POST /heartbeat) toutes les 5 s. Un thread
# daemon coupe le serveur si plus rien n'arrive pendant DELAI_HEARTBEAT_MAX s
# (onglet fermé). Dans l'autre sens, un Ctrl+C (SIGINT/SIGTERM) positionne
# l'état ARRET_DEMANDE : la route SSE /events le détecte et prévient l'onglet.
# L'état partagé (heartbeat, arrêt demandé, tunnel, mode externe, mot de passe)
# vit désormais dans app.config, lu à la requête via app/etat.py.
INTERVALLE_HEARTBEAT = 5        # période de sonde côté serveur (s)
DELAI_HEARTBEAT_MAX  = 15       # au-delà, l'onglet est considéré fermé


# Clés modifiables via l'interface (les autres : NOM, DEPOT, REP_TRAVAIL,
# PERIMETRE, CMD_BACKUP se changent à la main dans le .conf).
CLES_EDITABLES = {
    "TOPIC_NTFY", "LABEL", "INTERVALLE", "MAX_ESSAIS",
    "TIMEOUT_CLAUDE", "SCRIPT_BIP", "LOG_TAILLE_MAX_MO", "LOG_ARCHIVES",
    "MODELE_CCL", "MOT_DE_PASSE", "FICHIER_CONTEXTE",
}


# ─── Sécurité : authentification + filtrage IP ────────────────────────────────
# Le mot de passe d'accès est stocké HASHÉ (sha256) dans configs/bridge_agent.conf
# sous la clé MOT_DE_PASSE. Vide → interface accessible sans authentification.
# Générer le hash avec :  python3 new_issue.py --set-password
MAX_ECHECS_LOGIN = 5   # nombre de tentatives avant blocage de la session
# Le hash du mot de passe (MOT_DE_PASSE) et le drapeau MODE_EXTERNE vivent dans
# app.config : chargés au démarrage (main), lus à la requête via etat.get().
# charger_mot_de_passe() est déplacé dans app/etat.py.


def login_requis(vue):
    """Décorateur : redirige vers /login tant que la session n'est pas
    authentifiée. Inactif si aucun mot de passe n'est configuré ou en mode
    local (login exigé uniquement en mode --externe)."""
    @wraps(vue)
    def enveloppe(*args, **kwargs):
        if (etat.get("MOT_DE_PASSE") and etat.get("MODE_EXTERNE")
                and not session.get("authentifie")):
            return redirect(url_for("login"))
        return vue(*args, **kwargs)
    return enveloppe


def sauvegarder_conf(nom_projet: str, nouvelles_valeurs: dict) -> tuple[bool, str]:
    """Met à jour les clés éditables du .conf en préservant commentaires et
    structure. Les lignes commentées correspondant à une clé éditée sont
    décommentées au passage. Les clés absentes du fichier sont ajoutées à la fin."""
    chemin = DOSSIER_SCRIPT / "configs" / f"{nom_projet}.conf"
    if not chemin.exists():
        return False, f"Fichier introuvable : {chemin.name}"

    a_ecrire = {k.upper(): v for k, v in nouvelles_valeurs.items()
                if k.upper() in CLES_EDITABLES}

    lignes          = chemin.read_text(encoding="utf-8").splitlines()
    nouvelles_lignes = []
    mises_a_jour    = set()

    for ligne in lignes:
        stripped = ligne.strip()
        # Ligne commentée : on regarde si elle cache une clé éditable.
        if stripped.startswith("#"):
            reste = stripped[1:].strip()
            cle, sep, _ = reste.partition("=")
            cle_norm = cle.strip().upper()
            if sep and cle_norm in a_ecrire:
                nouvelles_lignes.append(f"{cle.strip()} = {a_ecrire[cle_norm]}")
                mises_a_jour.add(cle_norm)
                continue
        elif stripped:
            cle, sep, _ = ligne.partition("=")
            cle_norm = cle.strip().upper()
            if sep and cle_norm in a_ecrire:
                nouvelles_lignes.append(f"{cle.strip()} = {a_ecrire[cle_norm]}")
                mises_a_jour.add(cle_norm)
                continue
        nouvelles_lignes.append(ligne)

    # Clés absentes du fichier → on les ajoute à la fin.
    manquantes = set(a_ecrire.keys()) - mises_a_jour
    if manquantes:
        nouvelles_lignes.append("")
        for cle in sorted(manquantes):
            nouvelles_lignes.append(f"{cle} = {a_ecrire[cle]}")

    chemin.write_text("\n".join(nouvelles_lignes) + "\n", encoding="utf-8")
    return True, "Configuration enregistrée."


# ─── Projets ──────────────────────────────────────────────────────────────────

def lister_projets() -> list[Config]:
    """Retourne la liste des projets disponibles (un .conf = un projet)."""
    projets = []
    for chemin in sorted(DOSSIER_SCRIPT.glob("configs/*.conf")):
        try:
            projets.append(charger_config(chemin))
        except SystemExit:
            pass  # config incomplète ou invalide — ignorée silencieusement
    return projets


def projet_par_nom(nom: str) -> Config | None:
    return next((p for p in lister_projets() if p.nom == nom), None)


# ─── Gestion du processus watcher ────────────────────────────────────────────

def chemin_pid(cfg: Config) -> Path:
    return cfg.fichier_log.parent / f"watcher-{cfg.nom}.pid"


def watcher_actif(cfg: Config) -> tuple[bool, int | None]:
    """Retourne (actif, pid). Consulte le fichier PID et vérifie que le
    processus existe encore (os.kill(pid, 0) ne tue pas, il sonde)."""
    pid_file = chemin_pid(cfg)
    if not pid_file.exists():
        return False, None
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)   # lève OSError si le processus est mort
        return True, pid
    except (OSError, ProcessLookupError, ValueError):
        return False, None


def demarrer_watcher(cfg: Config, forcer: bool = True) -> tuple[bool, int]:
    """Lance (ou relance) le watcher du projet.
    Si forcer=False et qu'un watcher tourne déjà, retourne (False, pid_existant).
    Si forcer=True, arrête l'existant avant de redémarrer.
    Retourne (redemarré, pid)."""
    actif, pid_ancien = watcher_actif(cfg)
    if actif and not forcer:
        return False, pid_ancien

    if actif and pid_ancien:
        try:
            os.kill(pid_ancien, signal.SIGTERM)
            time.sleep(0.8)
        except OSError:
            pass

    pid_file = chemin_pid(cfg)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    conf_file      = DOSSIER_SCRIPT / "configs" / f"{cfg.nom}.conf"
    watcher_script = DOSSIER_SCRIPT / "watcher.py"

    proc = subprocess.Popen(
        [sys.executable, str(watcher_script), "--config", str(conf_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid_file.write_text(str(proc.pid))
    return True, proc.pid


def arreter_watcher(cfg: Config) -> tuple[bool, str]:
    """Arrête le watcher du projet via SIGTERM.
    Retourne (succès, message)."""
    actif, pid = watcher_actif(cfg)
    if not actif:
        return False, "watcher déjà inactif"
    try:
        os.kill(pid, signal.SIGTERM)
        chemin_pid(cfg).unlink(missing_ok=True)
        return True, f"watcher arrêté (pid {pid})"
    except OSError as e:
        return False, str(e)


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


TEMPLATE_LOGIN = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bridge Agent — Connexion</title>
<style>
body{font-family:system-ui,sans-serif;font-size:14px;background:#f0efe9;color:#1a1a18;
  min-height:100vh;margin:0;display:flex;align-items:center;justify-content:center;padding:28px 16px}
.carte{background:#fff;border:1px solid #ddd;border-radius:12px;max-width:360px;width:100%;
  padding:28px;box-shadow:0 1px 3px rgba(0,0,0,.05)}
.carte h1{font-size:16px;font-weight:500;margin:0 0 4px;display:flex;align-items:center;gap:9px}
.carte p.sous{color:#888;font-size:12px;margin:0 0 20px}
label{display:block;font-size:12px;color:#555;margin-bottom:6px}
input[type=password]{width:100%;box-sizing:border-box;padding:9px 12px;border:1px solid #ccc;
  border-radius:6px;font-size:14px;color:#1a1a18}
input[type=password]:focus{outline:none;border-color:#1a1a18}
button{width:100%;margin-top:16px;padding:9px 16px;border:1px solid #1a1a18;border-radius:6px;
  font-size:14px;background:#1a1a18;color:#fff;cursor:pointer}
button:hover{background:#333}
button:disabled{background:#999;border-color:#999;cursor:not-allowed}
.erreur{background:#f8d7da;color:#721c24;border-radius:6px;padding:9px 12px;font-size:12px;
  margin-bottom:16px}
</style>
</head>
<body>
  <form class="carte" method="post" action="/login">
    <h1>
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
        <rect x="4" y="11" width="16" height="9" rx="2"/><path d="M8 11V7a4 4 0 018 0v4"/>
      </svg>
      Bridge Agent
    </h1>
    <p class="sous">Accès protégé — saisissez le mot de passe.</p>
    {% if erreur %}<div class="erreur">{{ erreur }}</div>{% endif %}
    <label for="mot_de_passe">Mot de passe</label>
    <input type="password" id="mot_de_passe" name="mot_de_passe" autofocus
           {% if bloque %}disabled{% endif %}>
    <button type="submit" {% if bloque %}disabled{% endif %}>Connexion</button>
  </form>
</body>
</html>"""


# ─── Routes Flask ──────────────────────────────────────────────────────────────

def login():
    """Formulaire de connexion. Redirige vers l'accueil si aucune authentification
    n'est requise ou si la session est déjà authentifiée."""
    if not etat.get("MOT_DE_PASSE") or session.get("authentifie"):
        return redirect(url_for("index"))
    bloque = session.get("echecs", 0) >= MAX_ECHECS_LOGIN
    erreur = ("Trop de tentatives échouées. Redémarrez le serveur pour réessayer."
              if bloque else "")
    return render_template_string(TEMPLATE_LOGIN, erreur=erreur, bloque=bloque)


def login_post():
    """Vérifie le mot de passe saisi (sha256) contre MOT_DE_PASSE du .conf.
    Bloque la session après MAX_ECHECS_LOGIN tentatives échouées."""
    mot_de_passe = etat.get("MOT_DE_PASSE")
    if not mot_de_passe:
        return redirect(url_for("index"))
    if session.get("echecs", 0) >= MAX_ECHECS_LOGIN:
        return render_template_string(
            TEMPLATE_LOGIN, bloque=True,
            erreur="Trop de tentatives échouées. Redémarrez le serveur pour réessayer.")

    saisi = request.form.get("mot_de_passe", "")
    if hashlib.sha256(saisi.encode("utf-8")).hexdigest() == mot_de_passe:
        session["authentifie"] = True
        session.pop("echecs", None)
        return redirect(url_for("index"))

    session["echecs"] = session.get("echecs", 0) + 1
    restantes = MAX_ECHECS_LOGIN - session["echecs"]
    bloque = restantes <= 0
    erreur = ("Trop de tentatives échouées. Redémarrez le serveur pour réessayer."
              if bloque else
              f"Mot de passe incorrect. {restantes} tentative(s) restante(s).")
    return render_template_string(TEMPLATE_LOGIN, erreur=erreur, bloque=bloque)


def logout():
    """Ferme la session et renvoie vers le formulaire de connexion."""
    session.clear()
    return redirect(url_for("login"))


def index():
    return render_template("index.html", projets=lister_projets(),
                           auth_active=bool(etat.get("MOT_DE_PASSE")))


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


def journal(nom_projet):
    """Server-Sent Events : streame le journal du watcher en temps réel."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return Response("Projet introuvable.", status=404)
    fichier_log = cfg.fichier_log

    def generer():
        # ── 1. Les 80 dernières lignes existantes ──────────────────────────
        if fichier_log.exists():
            with open(fichier_log, "r", encoding="utf-8", errors="replace") as f:
                lignes = f.readlines()
            for l in lignes[-80:]:
                yield f"data: {l.rstrip()}\n\n"
        else:
            yield "data: (journal vide — le watcher n'a pas encore démarré)\n\n"

        # ── 2. Nouvelles lignes au fil de l'eau ────────────────────────────
        while True:
            try:
                taille = fichier_log.stat().st_size if fichier_log.exists() else 0
                with open(fichier_log, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(taille)
                    while True:
                        ligne = f.readline()
                        if ligne:
                            taille += len(ligne.encode("utf-8"))
                            yield f"data: {ligne.rstrip()}\n\n"
                        else:
                            time.sleep(0.5)
                            yield ": ping\n\n"  # keepalive (ignoré par onmessage)
                            # Vérifier si le fichier a été rotaté (taille diminuée)
                            nouvelle_taille = fichier_log.stat().st_size if fichier_log.exists() else 0
                            if nouvelle_taille < taille:
                                break  # rotation détectée → réouvrir
            except FileNotFoundError:
                time.sleep(2)
                yield ": ping\n\n"

    return Response(
        generer(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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


def get_config(nom_projet):
    """Retourne les valeurs actuelles du .conf, relues depuis le disque à
    chaque appel (via charger_config) plutôt que depuis l'objet Config en
    mémoire. Ainsi l'onglet Configuration reflète toujours l'état réel du
    fichier, même s'il a été modifié à la main après le démarrage."""
    chemin = DOSSIER_SCRIPT / "configs" / f"{nom_projet}.conf"
    if not chemin.exists():
        return jsonify(erreur="Projet introuvable."), 404
    try:
        cfg = charger_config(chemin)
    except SystemExit as e:
        # charger_config quitte (sys.exit) si un champ requis manque ou
        # qu'un entier est mal formé : on le rattrape pour ne pas tuer
        # le serveur et renvoyer une erreur exploitable côté onglet.
        return jsonify(erreur=f"Config invalide : {e}"), 400
    return jsonify(
        nom            = cfg.nom,
        depot          = cfg.depot,
        rep_travail    = str(cfg.rep_travail),
        perimetre      = cfg.perimetre,
        cmd_backup     = cfg.cmd_backup,
        topic_ntfy     = cfg.topic_ntfy,
        label          = cfg.label,
        intervalle     = cfg.intervalle,
        max_essais     = cfg.max_essais,
        timeout_claude = cfg.timeout_claude,
        script_bip     = str(cfg.script_bip),
        fichier_contexte = cfg.fichier_contexte,
        log_taille_max_mo = cfg.log_taille_max_mo,
        log_archives   = cfg.log_archives,
        modele_ccl     = cfg.modele_ccl,
    )


def post_config(nom_projet):
    """Enregistre les clés éditables dans le .conf."""
    data = request.json or {}
    ok, msg = sauvegarder_conf(nom_projet, data)
    return jsonify(succes=ok, message=msg)


def watchers():
    """Retourne le statut de tous les projets disponibles."""
    resultat = []
    for cfg in lister_projets():
        actif, pid = watcher_actif(cfg)
        resultat.append({
            "nom":   cfg.nom,
            "depot": cfg.depot,
            "actif": actif,
            "pid":   pid,
        })
    return jsonify(resultat)


def lancer_watcher():
    """Lance ou relance le watcher du projet.
    relancer=true → redémarre même s'il tourne déjà.
    relancer=false → démarre seulement s'il est inactif."""
    data    = request.json or {}
    cfg     = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    forcer  = data.get("relancer", True)
    try:
        redemarré, pid = demarrer_watcher(cfg, forcer=forcer)
        return jsonify(succes=True, pid=pid, redemarré=redemarré)
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))


def arreter_watcher_route():
    """Arrête le watcher du projet."""
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    ok, msg = arreter_watcher(cfg)
    return jsonify(succes=ok, message=msg)


def statut(nom_projet):
    """Indique si le watcher de ce projet est en cours d'exécution."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(actif=False)
    actif, pid = watcher_actif(cfg)
    return jsonify(actif=actif, pid=pid)


def heartbeat():
    """Le navigateur signale que l'onglet est toujours ouvert. Met à jour
    l'horodatage surveillé par surveiller_heartbeat()."""
    etat.set("LAST_HEARTBEAT", time.time())
    etat.set("HEARTBEAT_RECU", True)
    return jsonify(ok=True)


def events():
    """SSE dédié au cycle de vie (séparé du journal watcher).
    Envoie un keepalive toutes les 5 s ; dès qu'un signal d'arrêt a été reçu
    (ARRET_DEMANDE), émet un event « shutdown » puis ferme la connexion.
    app.config est capturé ICI (dans le contexte de requête) avant d'entrer
    dans le générateur — current_app n'est plus disponible une fois le
    générateur démarré hors contexte de requête."""
    config = current_app.config   # capturé dans le contexte de requête

    def generer():
        dernier_ping = time.time()
        while True:
            if config.get("ARRET_DEMANDE"):   # lecture directe, pas via etat.get()
                yield "event: shutdown\ndata: stop\n\n"
                return
            time.sleep(0.5)   # sonde fréquente du flag, keepalive espacé
            if time.time() - dernier_ping >= 5:
                yield ": ping\n\n"
                dernier_ping = time.time()

    return Response(
        generer(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def quitter():
    """Arrêt volontaire déclenché par le bouton « Quitter » de l'onglet.
    Positionne ARRET_DEMANDE (l'overlay /events sert de filet de sécurité si
    window.close() est bloqué), répond immédiatement, puis coupe le processus
    après 2 s — le délai laisse le navigateur recevoir la réponse et exécuter
    window.close() avant que le serveur ne disparaisse."""
    etat.set("ARRET_DEMANDE", True)

    def arret_differe():
        time.sleep(2)
        arreter_tunnel()
        os._exit(0)

    Thread(target=arret_differe, daemon=True).start()
    return jsonify(ok=True)


# ─── Point d'entrée ───────────────────────────────────────────────────────────


# ─── Tunnel cloudflared (mode --externe) ─────────────────────────────────────
# En mode --externe, new_issue.py démarre lui-même le tunnel cloudflared
# (« cloudflared tunnel run bridge-agent ») au lancement et l'arrête proprement
# à la fermeture (Ctrl+C / SIGTERM ou bouton « Quitter »). Plus besoin de le
# lancer à la main dans un terminal séparé.
URL_TUNNEL = "https://bridge.frederiqueferette.be"


def demarrer_tunnel(app_instance):
    """Vérifie l'installation de cloudflared et sa config, puis lance le tunnel
    bridge-agent en arrière-plan (stdout/stderr silencieux sauf erreur). Stocke
    le processus dans app.config['PROC_TUNNEL']. Termine le programme (exit 1)
    avec un message clair si un prérequis manque ou si le tunnel meurt
    immédiatement au démarrage."""

    # 1) cloudflared doit être installé.
    if shutil.which("cloudflared") is None:
        print("Erreur : cloudflared est introuvable (which cloudflared).")
        print("Installez cloudflared avant d'utiliser --externe.")
        sys.exit(1)

    # 2) La configuration du tunnel (~/.cloudflared/config.yml) doit exister.
    config_tunnel = Path.home() / ".cloudflared" / "config.yml"
    if not config_tunnel.exists():
        print(f"Erreur : configuration cloudflared introuvable : {config_tunnel}")
        print("Configurez le tunnel cloudflared avant d'utiliser --externe.")
        sys.exit(1)

    # 3) Lancement silencieux (sortie capturée, affichée seulement en cas d'échec).
    proc_tunnel = subprocess.Popen(
        ["cloudflared", "tunnel", "run", "bridge-agent"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # 4) Laisse 2 s au tunnel pour s'établir, puis vérifie qu'il est vivant.
    time.sleep(2)
    if proc_tunnel.poll() is not None:
        try:
            err = proc_tunnel.stderr.read().decode("utf-8", "replace") if proc_tunnel.stderr else ""
        except Exception:
            err = ""
        print("Erreur : le tunnel cloudflared s'est arrêté immédiatement.")
        if err.strip():
            print(err.strip())
        sys.exit(1)

    app_instance.config["PROC_TUNNEL"] = proc_tunnel
    print(f"Tunnel cloudflared démarré (pid {proc_tunnel.pid})")
    print(f"URL : {URL_TUNNEL}")


def arreter_tunnel():
    """Arrête proprement le tunnel cloudflared s'il a été démarré et tourne
    encore. Sans effet si aucun tunnel n'est actif (mode local ou déjà arrêté).
    Fonctionne hors contexte de requête (gestionnaire de signal) en accédant
    directement à app.config via l'instance globale."""
    global app
    if app is None:
        return
    proc_tunnel = app.config.get("PROC_TUNNEL")
    if proc_tunnel is not None and proc_tunnel.poll() is None:
        try:
            proc_tunnel.terminate()
            proc_tunnel.wait(timeout=3)
        except Exception:
            pass
        print("Tunnel cloudflared arrêté.")


def surveiller_heartbeat(app_instance):
    """Thread daemon : coupe le serveur (SIGTERM sur son propre PID) si l'onglet
    navigateur a cessé d'émettre des heartbeats depuis plus de DELAI_HEARTBEAT_MAX
    secondes. Tant qu'aucun heartbeat n'a jamais été reçu (serveur qui démarre,
    ou lancé en --no-browser), aucune surveillance : on n'auto-coupe jamais un
    serveur qui n'a pas encore eu de client. L'état est lu via app.config
    (l'instance est passée au thread car on est hors contexte de requête)."""
    while True:
        time.sleep(INTERVALLE_HEARTBEAT)
        heartbeat_recu = app_instance.config.get("HEARTBEAT_RECU", False)
        last_heartbeat = app_instance.config.get("LAST_HEARTBEAT", 0.0)
        if heartbeat_recu and (time.time() - last_heartbeat) > DELAI_HEARTBEAT_MAX:
            os.kill(os.getpid(), signal.SIGTERM)
            return

def enregistrer_routes(app_instance):
    """Enregistre toutes les routes Flask sur l'instance d'application.
    Les décorateurs @login_requis sont appliqués aux routes protégées."""
    app_instance.add_url_rule("/login", "login", login, methods=["GET"])
    app_instance.add_url_rule("/login", "login_post", login_post, methods=["POST"])
    app_instance.add_url_rule("/logout", "logout", logout)
    app_instance.add_url_rule("/", "index", login_requis(index))
    app_instance.add_url_rule("/apercu", "apercu", login_requis(apercu), methods=["POST"])
    app_instance.add_url_rule("/envoyer", "envoyer", login_requis(envoyer), methods=["POST"])
    app_instance.add_url_rule("/journal/<nom_projet>", "journal", login_requis(journal))
    app_instance.add_url_rule("/issues-liste/<nom_projet>", "issues_liste", login_requis(issues_liste))
    app_instance.add_url_rule("/issue/<nom_projet>/<numero>", "issue_detail", login_requis(issue_detail))
    app_instance.add_url_rule("/issues-en-attente/<nom_projet>", "issues_en_attente", login_requis(issues_en_attente))
    app_instance.add_url_rule("/annuler-issue/<nom_projet>/<numero>", "annuler_issue", login_requis(annuler_issue), methods=["POST"])
    app_instance.add_url_rule("/config/<nom_projet>", "get_config", login_requis(get_config), methods=["GET"])
    app_instance.add_url_rule("/config/<nom_projet>", "post_config", login_requis(post_config), methods=["POST"])
    app_instance.add_url_rule("/watchers", "watchers", login_requis(watchers))
    app_instance.add_url_rule("/lancer-watcher", "lancer_watcher", login_requis(lancer_watcher), methods=["POST"])
    app_instance.add_url_rule("/arreter-watcher", "arreter_watcher_route", login_requis(arreter_watcher_route), methods=["POST"])
    app_instance.add_url_rule("/statut/<nom_projet>", "statut", login_requis(statut))
    app_instance.add_url_rule("/heartbeat", "heartbeat", heartbeat, methods=["POST"])
    app_instance.add_url_rule("/events", "events", login_requis(events))
    app_instance.add_url_rule("/quitter", "quitter", login_requis(quitter), methods=["POST"])


def main():
    global app

    parser = argparse.ArgumentParser(
        description="Interface web de création d'issues — Bridge Agent"
    )
    parser.add_argument("--port", type=int, default=5100,
                        help="Port du serveur web (défaut : 5100)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Ne pas ouvrir le navigateur automatiquement")
    parser.add_argument("--set-password", action="store_true",
                        help="Génère le hash sha256 d'un mot de passe à copier "
                             "dans le .conf, puis quitte sans démarrer le serveur")
    parser.add_argument("--externe", action="store_true",
                        help="Exposition réseau (accès distant via tunnel) : "
                             "host 0.0.0.0 + HTTPS + mot de passe obligatoire. "
                             "Sans cette option : mode local (127.0.0.1, HTTP, "
                             "sans SSL)")
    args = parser.parse_args()

    # Utilitaire : génération du hash du mot de passe d'accès (ne démarre pas le
    # serveur). Le mot de passe est demandé deux fois pour confirmation et n'est
    # jamais affiché ni stocké en clair — seul le hash sha256 est produit.
    if args.set_password:
        mp1 = getpass.getpass("Nouveau mot de passe : ")
        mp2 = getpass.getpass("Confirmez le mot de passe : ")
        if not mp1:
            print("Mot de passe vide — abandon.")
            sys.exit(1)
        if mp1 != mp2:
            print("Les deux saisies diffèrent — abandon.")
            sys.exit(1)
        hache = hashlib.sha256(mp1.encode("utf-8")).hexdigest()
        print("\nCopiez cette ligne dans configs/bridge_agent.conf :\n")
        print(f"MOT_DE_PASSE = {hache}")
        sys.exit(0)

    # Création de l'application Flask et chargement de l'état initial.
    app = create_app()
    app.config["MOT_DE_PASSE"] = etat.charger_mot_de_passe()
    enregistrer_routes(app)

    # Deux modes de fonctionnement :
    #   • local (défaut)      : host 127.0.0.1, HTTP simple, sans SSL. Destiné à
    #     un usage sur place (devant le ThinkPad) — pas d'exposition réseau. Le
    #     mot de passe n'est PAS requis (mais reste appliqué s'il est configuré,
    #     via le décorateur @login_requis : aucune régression en mode local).
    #   • externe (--externe) : host 0.0.0.0, HTTPS + mot de passe OBLIGATOIRES.
    #     Destiné à l'accès distant (téléphone via tunnel).
    if args.externe:
        app.config["MODE_EXTERNE"] = True
        host   = "0.0.0.0"
        schema = "https"

        # En mode externe, refuser de démarrer si aucun mot de passe n'est
        # configuré : l'interface serait exposée au réseau sans authentification.
        if not app.config["MOT_DE_PASSE"]:
            print("Erreur : MOT_DE_PASSE non configuré.")
            print("Lancez d'abord : python3 new_issue.py --set-password")
            sys.exit(1)

        # Emplacement du certificat auto-signé (HTTPS). Généré une fois via :
        #   openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem \
        #     -out ssl/cert.pem -days 3650 -nodes -subj "/CN=bridge-agent-local"
        cert = DOSSIER_SCRIPT / "ssl" / "cert.pem"
        cle  = DOSSIER_SCRIPT / "ssl" / "key.pem"
        if not (cert.exists() and cle.exists()):
            print("Certificat SSL introuvable dans ssl/. Générez-le avec :")
            print('  openssl req -x509 -newkey rsa:4096 -keyout ssl/key.pem \\')
            print('    -out ssl/cert.pem -days 3650 -nodes -subj "/CN=bridge-agent-local"')
            sys.exit(1)
        ssl_context = (str(cert), str(cle))
    else:
        host        = "127.0.0.1"
        schema      = "http"
        ssl_context = None

    # Ctrl+C (SIGINT) ou SIGTERM : on prévient d'abord l'onglet via /events en
    # positionnant ARRET_DEMANDE, puis on laisse ~1,5 s à la connexion SSE pour
    # livrer l'event « shutdown » avant de terminer le processus.
    def gestionnaire_arret(signum, frame):
        app.config["ARRET_DEMANDE"] = True
        arreter_tunnel()
        Timer(1.5, lambda: os._exit(0)).start()

    signal.signal(signal.SIGINT, gestionnaire_arret)
    signal.signal(signal.SIGTERM, gestionnaire_arret)

    # Mode --externe : démarrage automatique du tunnel cloudflared avant
    # d'exposer le serveur. Vérifie les prérequis (cloudflared + config) et
    # quitte proprement (exit 1) en cas de problème. L'arrêt est géré par le
    # gestionnaire de signal ci-dessus et par la route /quitter.
    if args.externe:
        demarrer_tunnel(app)

    # Surveillance des heartbeats du navigateur (daemon → ne bloque jamais
    # l'arrêt du processus si le gestionnaire de signal est lent).
    Thread(target=surveiller_heartbeat, args=(app,), daemon=True).start()

    if not args.no_browser:
        Timer(1.2, lambda: webbrowser.open(f"{schema}://localhost:{args.port}")).start()

    print(f"Bridge Agent — interface web sur {schema}://localhost:{args.port}"
          f" ({'externe' if args.externe else 'local'})")
    print("Ctrl-C pour arrêter.")
    app.run(
        host=host,
        port=args.port,
        ssl_context=ssl_context,
        threaded=True,
        debug=False,
    )


if __name__ == "__main__":
    main()

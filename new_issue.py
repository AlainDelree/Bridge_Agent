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

from flask import (Flask, Response, jsonify, redirect, render_template_string,
                   request, session, url_for)

# Partage du lecteur de config avec watcher.py (même dossier).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from watcher import Config, charger_config  # noqa: E402

DOSSIER_SCRIPT = Path(__file__).resolve().parent

app = Flask(__name__)
# Clé de signature des cookies de session régénérée à chaque démarrage : les
# sessions ne survivent pas à un redémarrage (acceptable) mais la clé n'est
# jamais figée dans le code source — un cookie session['authentifie'] ne peut
# donc pas être forgé à partir du dépôt.
app.config["SECRET_KEY"] = os.urandom(32)


# ─── Cycle de vie serveur ↔ onglet navigateur ────────────────────────────────
# Le navigateur émet un heartbeat (POST /heartbeat) toutes les 5 s. Un thread
# daemon coupe le serveur si plus rien n'arrive pendant DELAI_HEARTBEAT_MAX s
# (onglet fermé). Dans l'autre sens, un Ctrl+C (SIGINT/SIGTERM) positionne
# arret_demande = True : la route SSE /events le détecte et prévient l'onglet.
INTERVALLE_HEARTBEAT = 5        # période de sonde côté serveur (s)
DELAI_HEARTBEAT_MAX  = 15       # au-delà, l'onglet est considéré fermé

last_heartbeat = 0.0            # horodatage du dernier heartbeat reçu
heartbeat_recu = False          # tant qu'aucun heartbeat : pas de surveillance
arret_demande  = False          # passé à True par le gestionnaire de signal

# Processus du tunnel cloudflared, démarré automatiquement en mode --externe
# (None en mode local ou tant que le tunnel n'est pas lancé). Arrêté proprement
# par le gestionnaire de signal et par la route /quitter.
proc_tunnel = None


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


def charger_mot_de_passe() -> str:
    """Hash sha256 du mot de passe d'accès, relu depuis bridge_agent.conf.
    Chaîne vide → aucune authentification exigée."""
    chemin = DOSSIER_SCRIPT / "configs" / "bridge_agent.conf"
    if not chemin.exists():
        return ""
    try:
        return charger_config(chemin).mot_de_passe.strip()
    except SystemExit:
        return ""


MOT_DE_PASSE = charger_mot_de_passe()

# Authentification exigée uniquement en mode --externe (exposition réseau).
# En mode local (127.0.0.1, HTTP), on est déjà sur la machine : le login n'a
# pas de sens. Passé à True dans main() si --externe est présent.
MODE_EXTERNE = False


def login_requis(vue):
    """Décorateur : redirige vers /login tant que la session n'est pas
    authentifiée. Inactif si aucun mot de passe n'est configuré ou en mode
    local (login exigé uniquement en mode --externe)."""
    @wraps(vue)
    def enveloppe(*args, **kwargs):
        if MOT_DE_PASSE and MODE_EXTERNE and not session.get("authentifie"):
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


# ─── Template HTML ────────────────────────────────────────────────────────────

TEMPLATE = r"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<title>Bridge Agent</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;font-size:14px;background:#f0efe9;color:#1a1a18;min-height:100vh;padding:28px 16px;position:relative}
.fenetre{max-width:860px;margin:0 auto;background:#fff;border:1px solid #ddd;border-radius:12px;overflow:hidden}
.entete{padding:14px 20px;border-bottom:1px solid #eee;display:flex;align-items:center;gap:9px}
.entete h1{font-size:15px;font-weight:500}
.entete .statut{margin-left:auto;font-size:12px;color:#888}
.bandeau-projet{display:flex;flex-direction:column;gap:8px;
  padding:14px 20px;border-bottom:1px solid #eee;background:#eef3f8;
  border-left:4px solid #1a1a18}
.bandeau-ligne{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.bandeau-ligne label{font-size:14px;color:#333;font-weight:600;white-space:nowrap}
.bandeau-projet select{padding:8px 12px;border:1px solid #ccc;border-radius:6px;
  font-size:15px;font-weight:600;background:#fff;color:#1a1a18;min-width:240px;
  border-left:4px solid #1a1a18}
.bandeau-projet select:focus{outline:none;border-color:#888}
.projet-actif-label{font-size:14px;font-weight:700;color:#1a1a18;padding:0 2px}
.onglets{display:flex;border-bottom:1px solid #eee;padding:0 20px}
.onglet{padding:9px 16px;font-size:15px;font-weight:500;color:#777;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;user-select:none}
.onglet.actif{color:#1a1a18;font-weight:700;border-bottom-color:#1a1a18}
.panneau{display:none;padding:20px}
.panneau.actif{display:block}
.rangee{display:flex;gap:12px;margin-bottom:14px;align-items:flex-end}
.champ{display:flex;flex-direction:column;gap:5px;flex:1}
.champ label{font-size:12px;color:#666}
.champ select,.champ input[type=text],.champ input[type=number]{
  width:100%;padding:7px 10px;border:1px solid #ddd;border-radius:6px;
  font-size:13px;background:#fff;color:#1a1a18}
.champ select:focus,.champ input:focus,textarea:focus{outline:none;border-color:#888}
textarea{width:100%;padding:10px;border:1px solid #ddd;border-radius:6px;
  font-size:13px;font-family:monospace;resize:vertical;color:#1a1a18;min-height:300px}
.titre-section{font-size:11px;font-weight:500;color:#999;text-transform:uppercase;
  letter-spacing:.06em;margin:16px 0 8px;padding-bottom:6px;border-bottom:1px solid #f0efe9}
.radio-groupe,.case-groupe{display:flex;gap:18px;flex-wrap:wrap;padding:4px 0}
.radio-groupe label,.case-groupe label{font-size:13px;display:flex;align-items:center;gap:6px;cursor:pointer}
.badge-alerte{font-size:11px;padding:2px 7px;border-radius:4px;background:#fff3cd;color:#856404;margin-left:4px}
.barre-envoi{display:flex;justify-content:flex-end;gap:10px;margin-top:18px;
  padding-top:14px;border-top:1px solid #eee}
button{padding:7px 16px;border:1px solid #ccc;border-radius:6px;font-size:13px;
  cursor:pointer;background:#fff;color:#1a1a18}
button:hover{background:#f0efe9}
button:active{transform:scale(.98)}
button.primaire{background:#1a1a18;color:#fff;border-color:#1a1a18}
button.primaire:hover{background:#333}
button.primaire:disabled{background:#999;border-color:#999;cursor:not-allowed}
button.danger{color:#721c24;border-color:#f5c6cb}
button.danger:hover{background:#f8d7da}
.apercu{background:#f8f8f5;border:1px solid #e0dfda;border-radius:6px;padding:14px;
  font-family:monospace;font-size:12px;margin-top:14px;white-space:pre-wrap;
  word-break:break-all;display:none;line-height:1.6}
.message{padding:10px 14px;border-radius:6px;font-size:13px;margin-top:12px;display:none}
.message.succes{background:#d4edda;color:#155724}
.message.erreur{background:#f8d7da;color:#721c24}
.terminal{background:#1a1a18;color:#a0a098;border-radius:8px;padding:14px;
  font-family:monospace;font-size:12px;min-height:360px;max-height:520px;
  overflow-y:auto;line-height:1.7}
.log-info{color:#a0a098}
.log-warn{color:#d4a017}
.log-ok{color:#5cb85c}
.log-err{color:#d9534f}
.barre-journal{display:flex;justify-content:space-between;align-items:center;margin-top:10px}
.barre-journal span{font-size:11px;color:#aaa}
.barre-issue{display:flex;align-items:center;gap:10px;margin-bottom:16px;
  padding-bottom:14px;border-bottom:1px solid #eee}
.barre-issue select{flex:1;padding:7px 10px;border:1px solid #ddd;border-radius:6px;
  font-size:13px;background:#fff;color:#1a1a18;min-width:0}
.barre-issue select:focus{outline:none;border-color:#888}
.zone-issue{min-height:120px}
.issue-vide{color:#aaa;font-size:13px;text-align:center;padding:40px 0}
.issue-titre{font-size:20px;font-weight:600;line-height:1.3;margin-bottom:10px}
.issue-badges{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:14px}
/* Ligne de boutons toggle « filtre par projet » au-dessus de la combobox. */
.filtres-projets{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:12px;align-items:center}
.filtre-projet{display:inline-flex;align-items:center;gap:6px;font-size:12px;
  font-weight:500;padding:5px 11px;border:1px solid #ccc;border-radius:14px;
  background:#fff;color:#333;cursor:pointer;user-select:none;transition:opacity .12s}
.filtre-projet .pastille{width:9px;height:9px;border-radius:50%;flex-shrink:0}
.filtre-projet.inactif{opacity:.4;background:#f2f2f0;color:#999}
.filtre-projet.tous{border-style:dashed;color:#555}
/* Badge du projet source dans l'en-tête du panneau de détail. */
.badge-projet{display:inline-flex;align-items:center;gap:6px;font-size:12px;
  font-weight:600;padding:3px 11px;border-radius:12px;color:#fff;margin-bottom:12px}
.badge-projet .pastille{width:8px;height:8px;border-radius:50%;
  background:rgba(255,255,255,.85);flex-shrink:0}
.badge-etat{font-size:12px;font-weight:500;padding:3px 10px;border-radius:12px}
.badge-etat.ouvert{background:#d4edda;color:#155724}
.badge-etat.ferme{background:#e2e3e5;color:#555}
.badge-label{font-size:11px;padding:3px 9px;border-radius:12px;
  background:#eef;color:#3b3b8f;border:1px solid #dde}
.badge-label.succes{background:#d4edda;color:#155724;border-color:#b7d7c0}
.badge-label.echec{background:#fff3cd;color:#856404;border-color:#f5e0a3}
.badge-label.ecriture{background:#f8d7da;color:#721c24;border-color:#f5c6cb}
.badge-label.gris{background:#eee;color:#666;border-color:#ddd}
.legende-resultats{font-size:12px;color:#888;background:#f8f8f5;
  border:1px solid #e0dfda;border-radius:6px;padding:8px 12px;
  margin-bottom:16px;display:flex;flex-direction:column;gap:2px;line-height:1.55}
.issue-body{background:#f8f8f5;border:1px solid #e0dfda;border-radius:6px;padding:12px;
  font-family:monospace;font-size:12px;white-space:pre-wrap;word-break:break-word;
  max-height:200px;overflow-y:auto;line-height:1.6;margin-bottom:16px}
.issue-sep{font-size:11px;font-weight:500;color:#999;text-transform:uppercase;
  letter-spacing:.06em;margin:16px 0 10px;padding-bottom:6px;border-bottom:1px solid #f0efe9}
.commentaire{position:relative;border:1px solid #e0dfda;border-radius:6px;padding:12px;
  margin-bottom:10px;background:#fff}
.commentaire.resultat{border-color:#b7d7c0;background:#f6fbf7}
.commentaire-auteur{font-size:12px;font-weight:500;color:#555;margin-bottom:6px;
  padding-right:130px}
.btn-copier{position:absolute;top:10px;right:10px;font-size:12px;font-weight:500;
  padding:4px 10px;border:1px solid #7fb08c;border-radius:5px;background:#eaf5ee;
  color:#2c6b41;cursor:pointer}
.btn-copier:hover{background:#dcefe2}
.btn-copier:disabled{cursor:default;border-color:#9ccbaa;color:#3a7a4f}
.commentaire-corps{font-family:monospace;font-size:12px;white-space:pre-wrap;
  word-break:break-word;line-height:1.6;color:#1a1a18}
.bloc-annuler{margin-bottom:16px}
/* Modal de confirmation — overlay en flux normal (position:absolute, pas fixed).
   Le body est positionné (position:relative) : l'overlay le recouvre entièrement. */
.modal-overlay{position:absolute;top:0;left:0;width:100%;min-height:100%;
  background:rgba(0,0,0,.42);display:none;justify-content:center;
  align-items:flex-start;padding:70px 16px 40px;z-index:1000}
.modal-overlay.actif{display:flex}
.modal-carte{background:#fff;border-radius:12px;max-width:460px;width:100%;
  padding:22px 24px;box-shadow:0 10px 40px rgba(0,0,0,.28)}
.modal-titre{font-size:15px;font-weight:600;line-height:1.4;margin-bottom:14px}
.modal-liste{font-family:monospace;font-size:12px;background:#f8f8f5;
  border:1px solid #e0dfda;border-radius:6px;padding:10px 12px;margin-bottom:18px;
  max-height:200px;overflow-y:auto;line-height:1.8;word-break:break-word}
.modal-boutons{display:flex;justify-content:flex-end;gap:10px}
button.danger-plein{background:#a32d2d;color:#fff;border-color:#a32d2d}
button.danger-plein:hover{background:#8f2626}
/* Overlay « serveur arrêté » — flux normal (position:absolute, pas fixed),
   recouvre tout le body (position:relative). Affiché sur Ctrl+C serveur ou
   coupure brutale de la connexion SSE /events. */
.overlay-arret{position:absolute;top:0;left:0;width:100%;min-height:100%;
  background:rgba(20,20,18,.94);display:none;flex-direction:column;
  justify-content:center;align-items:center;gap:22px;padding:60px 20px;
  z-index:2000;text-align:center}
.overlay-arret.actif{display:flex}
.overlay-arret .msg{color:#fff;font-size:18px;font-weight:600;line-height:1.5;
  max-width:520px}
.overlay-arret button{font-size:15px;padding:11px 24px}
</style>
</head>
<body>
<div class="fenetre">

  <div class="entete">
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">
      <circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/>
      <path d="M6 9v1a2 2 0 002 2h4a2 2 0 012 2v1"/>
    </svg>
    <h1>Bridge Agent</h1>
    <span class="statut">{{ projets|length }} projet(s) disponible(s)</span>
    {% if auth_active %}
    <button class="danger" onclick="location.href='/logout'"
            style="font-size:12px;padding:5px 12px">Déconnexion</button>
    {% endif %}
    <button id="btn-quitter" class="danger" onclick="quitter()"
            style="font-size:12px;padding:5px 12px">Quitter</button>
  </div>

  <!-- ─── Bandeau global : sélecteur de projet (pilote tous les onglets sauf Watchers) ─ -->
  <div class="bandeau-projet">

    <!-- Ligne 1 : combobox Projet + bouton (relancer) à sa droite, statut à droite -->
    <div class="bandeau-ligne">
      <label for="projet">Projet :</label>
      <select id="projet" onchange="onProjetChange()">
        {% for p in projets %}
        <option value="{{ p.nom }}">{{ p.nom }} — {{ p.depot }}</option>
        {% endfor %}
      </select>
      <button id="btn-watcher" onclick="lancerWatcher()">Lancer le watcher</button>

      <div id="bandeau-statut" style="display:flex;align-items:center;gap:10px;
           margin-left:auto;padding:6px 12px;background:#f8f8f5;
           border:1px solid #e0dfda;border-radius:6px;font-size:13px">
        <span id="dot-statut" style="width:8px;height:8px;border-radius:50%;
              background:#ccc;flex-shrink:0"></span>
        <span id="texte-statut" style="color:#888">Vérification…</span>
      </div>
    </div>

    <!-- Ligne 2 : « Projet actif : … » en grand, avec la couleur accent du projet -->
    <div id="projet-actif-label" class="projet-actif-label"></div>

    <!-- Ligne 3 : nom du dépôt et du répertoire, sous la combobox et le statut -->
    <div id="info-projet" style="font-size:12px;color:#888;padding:0 2px">
      <span id="info-depot"></span>
      <span id="info-rep-travail"></span>
      <span id="info-perimetre"></span>
    </div>
  </div>

  <div class="onglets">
    <div class="onglet actif" onclick="basculerOnglet('creation')">Nouvelle issue</div>
    <div class="onglet" onclick="basculerOnglet('resultats')">Résultats</div>
    <div class="onglet" onclick="basculerOnglet('journal')">Journal watcher</div>
    <div class="onglet" onclick="basculerOnglet('config')">Configuration</div>
    <div class="onglet" onclick="basculerOnglet('watchers')">Watchers</div>
  </div>

  <!-- ─── Onglet 1 : création d'issue ──────────────────────────────────── -->
  <div id="panneau-creation" class="panneau actif">

    <div class="rangee">
      <div class="champ" style="max-width:150px">
        <label>Priorité</label>
        <select id="priorite">
          <option value="normale">normale</option>
          <option value="haute">haute</option>
          <option value="critique">critique</option>
        </select>
      </div>
      <div class="champ" style="max-width:110px">
        <label>Timeout (s)</label>
        <input type="number" id="timeout" value="300" min="30" step="30">
      </div>
    </div>

    <div class="champ" style="margin-bottom:14px">
      <label>Titre</label>
      <input type="text" id="titre" placeholder="Résumé court et actionnable">
    </div>

    <div class="titre-section">Mode</div>
    <div class="radio-groupe">
      <label><input type="radio" name="mode" value="lecture" checked
                    onchange="mettreAJourBoutonEnvoi()"> Lecture seule</label>
      <label><input type="radio" name="mode" value="ecriture"
                    onchange="mettreAJourBoutonEnvoi()">
        Écriture <span class="badge-alerte">⚠ mode_write</span>
      </label>
    </div>

    <div class="titre-section">Notifications</div>
    <div class="case-groupe">
      <label><input type="checkbox" name="notifs" value="notif_pc"> Bureau (notif_pc)</label>
      <label><input type="checkbox" name="notifs" value="notif_gsm"> GSM (notif_gsm)</label>
      <label><input type="checkbox" name="notifs" value="notif_tous"> Tous (notif_tous)</label>
    </div>

    <div class="titre-section">Corps de la tâche</div>
    <textarea id="corps" placeholder="## Contexte&#10;…&#10;&#10;Ou coller directement avec #Titre: mon titre en première ligne."></textarea>

    <div id="zone-apercu" class="apercu"></div>
    <div id="message" class="message"></div>

    <div class="barre-envoi">
      <select id="modele-ponctuel" title="Modèle CCL pour cette issue uniquement"
              style="font-size:13px;padding:6px 10px;border:1px solid #ddd;
                     border-radius:6px;color:#555;background:#fff">
        <option value="">(modèle par défaut)</option>
        <option value="claude-opus-4-5">claude-opus-4-5</option>
        <option value="claude-sonnet-4-5">claude-sonnet-4-5</option>
        <option value="claude-haiku-4-5">claude-haiku-4-5</option>
      </select>
      <div style="flex:1"></div>
      <button class="danger" onclick="viderFormulaire()">Vider</button>
      <button onclick="afficherApercu()">Aperçu de la commande</button>
      <button class="primaire" id="btn-envoyer" onclick="envoyerIssue()">Envoyer l'issue</button>
    </div>
  </div>

  <!-- ─── Onglet Résultats : visualisation des issues ──────────────────── -->
  <div id="panneau-resultats" class="panneau">

    <!-- Boutons toggle : un par projet + « Tous ». Générés dynamiquement. -->
    <div id="filtres-projets" class="filtres-projets"></div>

    <div class="barre-issue">
      <select id="select-issue" title="Issues récentes de tous les projets" onchange="afficherIssue()"></select>
      <button onclick="naviguerIssue(-1)" title="Issue précédente">←</button>
      <button onclick="naviguerIssue(1)" title="Issue suivante">→</button>
    </div>

    <div class="legende-resultats">
      <span>✅ Traitée avec succès (label done)</span>
      <span>✏️ Lancée en mode écriture (label mode_write)</span>
      <span>⚠️ Échec — intervention humaine requise (label needs-human)</span>
      <span>○ Aucun de ces labels</span>
    </div>

    <div id="zone-issue" class="zone-issue">
      <div class="issue-vide">Aucune issue à afficher</div>
    </div>
  </div>

  <!-- ─── Onglet 2 : gestion des watchers ──────────────────────────────── -->
  <div id="panneau-watchers" class="panneau">
    <table style="width:100%;border-collapse:collapse" id="tableau-watchers">
      <thead>
        <tr style="border-bottom:1px solid #eee">
          <th style="width:36px;padding:8px 0;text-align:center">
            <input type="checkbox" id="cb-tous" onchange="selectionnerTous(this)">
          </th>
          <th style="width:20px"></th>
          <th style="text-align:left;font-size:12px;color:#666;font-weight:500;padding:8px 12px">Projet</th>
          <th style="text-align:left;font-size:12px;color:#666;font-weight:500;padding:8px 12px">Dépôt</th>
          <th style="text-align:left;font-size:12px;color:#666;font-weight:500;padding:8px 0;width:120px">PID</th>
        </tr>
      </thead>
      <tbody id="corps-watchers"></tbody>
    </table>
    <div id="msg-watchers" class="message"></div>
    <div style="display:flex;align-items:center;gap:10px;margin-top:16px;
         padding-top:14px;border-top:1px solid #eee">
      <span style="font-size:12px;color:#aaa" id="compte-selection">0 sélectionné</span>
      <div style="margin-left:auto;display:flex;gap:10px">
        <button onclick="actionWatchers('lancer')">Lancer</button>
        <button onclick="actionWatchers('relancer')">Relancer</button>
        <button class="danger" onclick="actionWatchers('arreter')">Éteindre</button>
      </div>
    </div>
  </div>

  <!-- ─── Onglet 3 : configuration ────────────────────────────────────── -->
  <div id="panneau-config" class="panneau">

    <div class="titre-section">Identité — modification manuelle dans le .conf uniquement</div>
    <div id="config-readonly" style="background:#f8f8f5;border:1px solid #e0dfda;
         border-radius:6px;padding:10px 14px;font-size:12px;font-family:monospace;
         color:#666;line-height:2;margin-bottom:14px"></div>

    <div class="titre-section">Paramètres éditables</div>

    <div class="rangee">
      <div class="champ">
        <label>Topic ntfy</label>
        <input type="text" id="conf-TOPIC_NTFY">
      </div>
      <div class="champ" style="max-width:140px">
        <label>Label</label>
        <input type="text" id="conf-LABEL">
      </div>
    </div>

    <div class="rangee">
      <div class="champ" style="max-width:140px">
        <label>Intervalle (s)</label>
        <input type="number" id="conf-INTERVALLE" min="5" step="5">
      </div>
      <div class="champ" style="max-width:140px">
        <label>Max essais</label>
        <input type="number" id="conf-MAX_ESSAIS" min="1" step="1">
      </div>
      <div class="champ" style="max-width:160px">
        <label>Timeout Claude (s)</label>
        <input type="number" id="conf-TIMEOUT_CLAUDE" min="30" step="30">
      </div>
    </div>

    <div class="champ" style="margin-bottom:14px">
      <label>Script bip</label>
      <input type="text" id="conf-SCRIPT_BIP">
    </div>

    <div class="champ" style="margin-bottom:14px">
      <label>Fichier de contexte projet (relatif au rep. de travail)</label>
      <input type="text" id="conf-FICHIER_CONTEXTE"
             placeholder="ex: CONTEXTE.md ou BRIDGE_AGENT_DOC.md">
    </div>

    <div class="champ" style="margin-bottom:14px">
      <label>Modèle Claude Code (vide = défaut)</label>
      <input type="text" id="conf-MODELE_CCL" placeholder="ex: claude-opus-4-5">
    </div>

    <div class="rangee">
      <div class="champ" style="max-width:180px">
        <label>Taille max journal (Mo)</label>
        <input type="number" id="conf-LOG_TAILLE_MAX_MO" min="1" step="1">
      </div>
      <div class="champ" style="max-width:140px">
        <label>Archives journal</label>
        <input type="number" id="conf-LOG_ARCHIVES" min="1" step="1">
      </div>
    </div>

    <div id="msg-config" class="message"></div>

    <div class="barre-envoi">
      <button onclick="sauvegarderConfig(false)">Enregistrer</button>
      <button class="primaire" onclick="sauvegarderConfig(true)">Enregistrer et relancer</button>
    </div>
  </div>

  <!-- ─── Onglet 4 : journal watcher ───────────────────────────────────── -->
  <div id="panneau-journal" class="panneau">
    <div class="terminal" id="terminal"></div>
    <div class="barre-journal">
      <span id="label-journal">—</span>
      <button onclick="viderTerminal()">Vider l'affichage</button>
    </div>
  </div>

</div>

<!-- ─── Modal de confirmation d'envoi (issues en attente) ─────────────────── -->
<div id="modal-confirmation" class="modal-overlay">
  <div class="modal-carte">
    <div class="modal-titre" id="modal-titre"></div>
    <div class="modal-liste" id="modal-liste"></div>
    <div class="modal-boutons">
      <button id="modal-non">Annuler</button>
      <button class="danger-plein" id="modal-oui">Envoyer quand même</button>
    </div>
  </div>
</div>

<!-- ─── Overlay « serveur arrêté » ────────────────────────────────────────── -->
<div id="overlay-arret" class="overlay-arret">
  <div class="msg">🔴 Serveur arrêté — relancez new_issue.py puis rechargez</div>
  <button onclick="window.location.reload()">Recharger</button>
</div>

<script>
let sourceSSE = null;

let intervalWatchers = null;

// Dernier projet ayant reçu une issue dans CETTE session (onglet ouvert). Sert
// à déclencher un second avertissement dans envoyerIssue() si l'utilisateur
// change de projet juste avant l'envoi. Réinitialisé à chaque rechargement.
let sessionDernierEnvoi = null;

// Couleur d'accent STABLE dérivée du nom du projet (hash simple sur les
// charCodes → teinte HSL). Même nom ⇒ même couleur à chaque session.
function couleurProjet(nom) {
  let h = 0;
  for (let i = 0; i < nom.length; i++) {
    h = (h * 31 + nom.charCodeAt(i)) % 360;
  }
  return 'hsl(' + ((h + 360) % 360) + ', 60%, 34%)';
}

// Applique l'accent visuel du projet : bordure gauche du select et du bandeau,
// et libellé « Projet actif : … » en grand, tous de la même couleur.
function appliquerAccentProjet(nom) {
  const couleur = couleurProjet(nom);
  const select  = document.getElementById('projet');
  const bandeau = document.querySelector('.bandeau-projet');
  const label   = document.getElementById('projet-actif-label');
  if (select)  select.style.borderLeftColor  = couleur;
  if (bandeau) bandeau.style.borderLeftColor  = couleur;
  if (label) {
    label.textContent = 'Projet actif : ' + nom;
    label.style.color = couleur;
  }
}

function basculerOnglet(nom) {
  const noms = ['creation', 'resultats', 'journal', 'config', 'watchers'];
  document.querySelectorAll('.onglet').forEach((o, i) =>
    o.classList.toggle('actif', noms[i] === nom));
  noms.forEach(n =>
    document.getElementById('panneau-' + n).classList.toggle('actif', n === nom));
  if (nom === 'journal')  demarrerJournal();
  if (nom === 'resultats') chargerListeIssues();
  if (nom === 'watchers') {
    chargerWatchers();
    intervalWatchers = setInterval(chargerWatchers, 5000);
  } else {
    clearInterval(intervalWatchers);
  }
  if (nom === 'config') chargerConfig();
}

function onProjetChange() {
  const nom = document.getElementById('projet').value;
  // Mémorise le projet choisi pour le restaurer à la prochaine ouverture.
  try { localStorage.setItem('bridge_projet_actif', nom); } catch(e) {}
  appliquerAccentProjet(nom);
  verifierStatut();
  mettreAJourInfoProjet();
  // L'onglet Résultats est indépendant du sélecteur global (il agrège tous
  // les projets) : on ne le recharge donc PAS ici.
  // Si l'onglet Configuration est actif, recharger sa config pour le
  // nouveau projet (l'onglet lit désormais le sélecteur global #projet).
  if (document.getElementById('panneau-config').classList.contains('actif')) {
    chargerConfig();
  }
}

async function mettreAJourInfoProjet() {
  const nom = document.getElementById('projet').value;
  try {
    const rep = await fetch('/config/' + encodeURIComponent(nom));
    const cfg = await rep.json();
    const depEl = document.getElementById('info-depot');
    const repEl = document.getElementById('info-rep-travail');
    const perEl = document.getElementById('info-perimetre');
    depEl.textContent = '📦 ' + cfg.depot;
    repEl.textContent = ' · 📁 ' + cfg.rep_travail;
    if (cfg.perimetre) {
      perEl.textContent = ' · 🔒 ' + cfg.perimetre;
    } else {
      perEl.textContent = '';
    }
    // Le timeout par défaut suit la valeur TIMEOUT_CLAUDE du projet sélectionné.
    document.getElementById('timeout').value = cfg.timeout_claude || 300;
  } catch(e) {}
}

async function chargerConfig() {
  const nom = document.getElementById('projet').value;
  try {
    const rep = await fetch('/config/' + encodeURIComponent(nom));
    const cfg = await rep.json();

    document.getElementById('config-readonly').innerHTML =
      `NOM = ${cfg.nom}<br>DEPOT = ${cfg.depot}<br>` +
      `REP_TRAVAIL = ${cfg.rep_travail}<br>` +
      (cfg.perimetre  ? `PERIMETRE = ${cfg.perimetre}<br>` : '') +
      (cfg.cmd_backup ? `CMD_BACKUP = ${cfg.cmd_backup}` : '');

    document.getElementById('conf-TOPIC_NTFY').value        = cfg.topic_ntfy        || '';
    document.getElementById('conf-LABEL').value             = cfg.label             || 'for-linux';
    document.getElementById('conf-INTERVALLE').value        = cfg.intervalle        || 10;
    document.getElementById('conf-MAX_ESSAIS').value        = cfg.max_essais        || 3;
    document.getElementById('conf-TIMEOUT_CLAUDE').value    = cfg.timeout_claude    || 300;
    document.getElementById('conf-SCRIPT_BIP').value        = cfg.script_bip        || '';
    document.getElementById('conf-FICHIER_CONTEXTE').value  = cfg.fichier_contexte  || '';
    document.getElementById('conf-MODELE_CCL').value        = cfg.modele_ccl        || '';
    document.getElementById('conf-LOG_TAILLE_MAX_MO').value = cfg.log_taille_max_mo || 1;
    document.getElementById('conf-LOG_ARCHIVES').value      = cfg.log_archives      || 5;
    document.getElementById('msg-config').style.display = 'none';
  } catch(e) {
    const msg = document.getElementById('msg-config');
    msg.textContent = 'Erreur de chargement : ' + e.message;
    msg.className = 'message erreur'; msg.style.display = 'block';
  }
}

async function sauvegarderConfig(relancer) {
  const nom = document.getElementById('projet').value;
  const data = {
    TOPIC_NTFY:        document.getElementById('conf-TOPIC_NTFY').value,
    LABEL:             document.getElementById('conf-LABEL').value,
    INTERVALLE:        document.getElementById('conf-INTERVALLE').value,
    MAX_ESSAIS:        document.getElementById('conf-MAX_ESSAIS').value,
    TIMEOUT_CLAUDE:    document.getElementById('conf-TIMEOUT_CLAUDE').value,
    SCRIPT_BIP:        document.getElementById('conf-SCRIPT_BIP').value,
    FICHIER_CONTEXTE:  document.getElementById('conf-FICHIER_CONTEXTE').value,
    MODELE_CCL:        document.getElementById('conf-MODELE_CCL').value,
    LOG_TAILLE_MAX_MO: document.getElementById('conf-LOG_TAILLE_MAX_MO').value,
    LOG_ARCHIVES:      document.getElementById('conf-LOG_ARCHIVES').value,
  };
  const rep  = await fetch('/config/' + encodeURIComponent(nom), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const json = await rep.json();
  const msg  = document.getElementById('msg-config');
  msg.textContent = json.message;
  msg.className   = 'message ' + (json.succes ? 'succes' : 'erreur');
  msg.style.display = 'block';
  if (json.succes && relancer) {
    await fetch('/lancer-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: nom, relancer: true})
    });
    msg.textContent += ' Watcher relancé.';
  }
}

function demarrerJournal() {
  if (sourceSSE) { sourceSSE.close(); sourceSSE = null; }
  const nom = document.getElementById('projet').value;
  document.getElementById('label-journal').textContent = 'logs/watcher-' + nom + '.log';
  document.getElementById('terminal').innerHTML = '';
  sourceSSE = new EventSource('/journal/' + encodeURIComponent(nom));
  sourceSSE.onmessage = function(e) {
    const term = document.getElementById('terminal');
    const div = document.createElement('div');
    const t = e.data;
    if (t.includes('[WARNING]') || t.includes('⚠'))  div.className = 'log-warn';
    else if (t.includes('[ERROR]'))                    div.className = 'log-err';
    else if (t.includes('✓') || t.includes('succès')) div.className = 'log-ok';
    else                                               div.className = 'log-info';
    div.textContent = t;
    // Les lignes les plus récentes s'affichent en haut
    term.insertBefore(div, term.firstChild);
    term.scrollTop = 0;
  };
  sourceSSE.onerror = function() {
    const term = document.getElementById('terminal');
    const div = document.createElement('div');
    div.className = 'log-warn';
    div.textContent = '— connexion perdue, tentative de reconnexion…';
    term.insertBefore(div, term.firstChild);
    term.scrollTop = 0;
  };
}

function viderTerminal() {
  document.getElementById('terminal').innerHTML = '';
}

// ─── Onglet Résultats : visualisation des issues ──────────────────────────

// Préfixe visuel d'une issue selon ses labels.
// needs-human prime sur tout ; sinon mode_write (✏️) puis done (✅) se cumulent ;
// à défaut, ○.
function prefixeIssue(labels) {
  const noms = (labels || []).map(l => ((l && l.name) || l || '').toLowerCase());
  if (noms.includes('needs-human')) return '⚠️';
  let p = '';
  if (noms.includes('mode_write')) p += '✏️';
  if (noms.includes('done'))       p += '✅';
  return p || '○';
}

// Badge coloré pour un label dans le panneau de détail.
function badgeLabel(nom) {
  const map = {
    'done':        {cls: 'succes',   txt: '✅ succès'},
    'needs-human': {cls: 'echec',    txt: '⚠️ échec'},
    'mode_write':  {cls: 'ecriture', txt: '✏️ écriture'},
    'bridge':      {cls: 'gris',     txt: 'bridge'},
    'for-linux':   {cls: 'gris',     txt: 'for-linux'},
  };
  const b = map[nom] || {cls: 'gris', txt: nom};
  return '<span class="badge-label ' + b.cls + '">' + escapeHtml(b.txt) + '</span>';
}

// ─── Onglet Résultats : vue consolidée multi-projets ──────────────────────
// L'onglet Résultats est INDÉPENDANT du sélecteur global : il agrège les
// issues de TOUS les projets, quel que soit le projet actif en haut.

// Couleur fixe par projet pour l'onglet Résultats (pastilles, badges, boutons
// de filtre). Valeurs stables imposées ; gris par défaut pour les autres.
function couleurProjetResultats(nom) {
  const map = {
    'bridge_agent': '#185FA5',  // bleu
    'alchess':      '#3B6D11',  // vert
    'ff_galerie':   '#BA7517',  // orange
  };
  return map[nom] || '#5F5E5A';  // gris
}

// Liste des noms de projets disponibles (lue depuis le sélecteur global, qui
// est peuplé côté serveur par lister_projets()).
function nomsProjetsDisponibles() {
  return [...document.getElementById('projet').options]
    .map(o => o.value).filter(Boolean);
}

// État de l'onglet Résultats : liste fusionnée des issues (chacune porte son
// projet source) + ensemble des projets actuellement affichés (filtre).
let listeIssuesResultats = [];
let projetsFiltresActifs = new Set();

async function chargerListeIssues() {
  const select = document.getElementById('select-issue');
  select.innerHTML = '<option value="">(chargement…)</option>';
  const noms = nomsProjetsDisponibles();
  if (!noms.length) {
    select.innerHTML = '<option value="">(aucun projet)</option>';
    return;
  }
  try {
    // Chargement en parallèle des 5 dernières issues de chaque projet.
    const listes = await Promise.all(noms.map(async nom => {
      try {
        const rep = await fetch('/issues-liste/' + encodeURIComponent(nom));
        const liste = await rep.json();
        if (!Array.isArray(liste)) return [];
        // Les 5 plus récentes (numéro décroissant) de ce projet.
        return liste
          .slice()
          .sort((a, b) => b.number - a.number)
          .slice(0, 5)
          .map(it => Object.assign({}, it, {projet: nom}));
      } catch(e) {
        return [];
      }
    }));
    // Fusion + tri global par numéro décroissant (plus récentes en premier).
    listeIssuesResultats = listes.flat().sort((a, b) => b.number - a.number);

    // Par défaut, tous les projets sont actifs (visibles).
    projetsFiltresActifs = new Set(noms);
    construireBoutonsFiltre(noms);
    rendreListeIssues(true);
  } catch(e) {
    select.innerHTML = '<option value="">(erreur de chargement)</option>';
  }
}

// (Re)construit la ligne de boutons toggle — un par projet + « Tous ».
function construireBoutonsFiltre(noms) {
  const zone = document.getElementById('filtres-projets');
  zone.innerHTML = '';
  for (const nom of noms) {
    const btn = document.createElement('span');
    btn.className = 'filtre-projet';
    btn.dataset.projet = nom;
    // La couleur du projet est stockée en attribut data ; appliqueCouleurBouton
    // la reporte en texte + bordure quand le bouton est actif (indicateur
    // visible de projet, cohérent avec la pastille et le badge de détail).
    btn.dataset.couleur = couleurProjetResultats(nom);
    btn.onclick = () => basculerFiltreProjet(nom);
    btn.innerHTML = '<span class="pastille" style="background:'
      + couleurProjetResultats(nom) + '"></span>' + escapeHtml(nom);
    zone.appendChild(btn);
  }
  majClassesBoutonsFiltre();
  const tous = document.createElement('span');
  tous.className = 'filtre-projet tous';
  tous.textContent = 'Tous';
  tous.onclick = reactiverTousLesFiltres;
  zone.appendChild(tous);
}

// Active/désactive un projet dans le filtre puis rafraîchit la combobox.
function basculerFiltreProjet(nom) {
  if (projetsFiltresActifs.has(nom)) projetsFiltresActifs.delete(nom);
  else projetsFiltresActifs.add(nom);
  majClassesBoutonsFiltre();
  rendreListeIssues(true);
}

// Remet tous les projets à l'état actif.
function reactiverTousLesFiltres() {
  projetsFiltresActifs = new Set(nomsProjetsDisponibles());
  majClassesBoutonsFiltre();
  rendreListeIssues(true);
}

function majClassesBoutonsFiltre() {
  document.querySelectorAll('#filtres-projets .filtre-projet[data-projet]')
    .forEach(btn => {
      const actif = projetsFiltresActifs.has(btn.dataset.projet);
      btn.classList.toggle('inactif', !actif);
      // Actif : texte + bordure à la couleur du projet (bien visible).
      // Inactif : on efface le style inline pour laisser la classe .inactif
      // (grisé) reprendre la main.
      btn.style.color       = actif ? btn.dataset.couleur : '';
      btn.style.borderColor = actif ? btn.dataset.couleur : '';
    });
}

// (Re)peuple la combobox à partir de listeIssuesResultats, en ne gardant que
// les projets actifs. Chaque option porte son projet + numéro (les numéros
// pouvant se répéter d'un projet à l'autre). Si reset=true, sélectionne et
// affiche la première issue visible.
function rendreListeIssues(reset) {
  const select = document.getElementById('select-issue');
  const visibles = listeIssuesResultats.filter(it => projetsFiltresActifs.has(it.projet));
  select.innerHTML = '';
  if (!visibles.length) {
    select.innerHTML = '<option value="">(aucune issue)</option>';
    document.getElementById('zone-issue').innerHTML =
      '<div class="issue-vide">Aucune issue à afficher</div>';
    return;
  }
  for (const it of visibles) {
    const etat = (it.state || '').toUpperCase() === 'CLOSED' ? 'fermé' : 'ouvert';
    const opt = document.createElement('option');
    opt.value = it.projet + '/' + it.number;
    opt.dataset.projet = it.projet;
    opt.dataset.numero = it.number;
    // La couleur du projet est portée par un attribut data (data-couleur) :
    // Firefox & la plupart des navigateurs ignorent color/style sur <option>,
    // donc on n'y met AUCUN style. La couleur est appliquée sur le <select>
    // lui-même (élément affiché) via majCouleurSelectIssue() ; pour la liste
    // dépliée, les boutons de filtre colorés servent d'indicateur de projet.
    opt.dataset.couleur = couleurProjetResultats(it.projet);
    // ✅ ● bridge_agent #31 — Titre [fermée]
    opt.textContent = `${prefixeIssue(it.labels)} ● ${it.projet} #${it.number} — ${it.title} [${etat}]`;
    select.appendChild(opt);
  }
  if (reset) {
    select.selectedIndex = 0;
    afficherIssue();
  }
  majCouleurSelectIssue();
}

// Applique la couleur du projet de l'option sélectionnée sur le <select>
// lui-même (le seul élément dont color est respecté par tous les navigateurs).
// Ainsi l'item affiché prend la couleur de son projet ; la liste dépliée, elle,
// reste neutre et c'est la rangée de boutons de filtre (colorés) qui indique
// le projet de chaque item.
function majCouleurSelectIssue() {
  const select = document.getElementById('select-issue');
  if (!select) return;
  const opt = select.options[select.selectedIndex];
  const couleur = (opt && opt.dataset.couleur) ? opt.dataset.couleur : '';
  select.style.color = couleur;
  select.style.fontWeight = couleur ? '600' : '';
}

function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t == null ? '' : t;
  return d.innerHTML;
}

async function afficherIssue() {
  const sel = document.getElementById('select-issue');
  const opt = sel.options[sel.selectedIndex];
  // Recolore le <select> à la couleur du projet de l'issue sélectionnée.
  majCouleurSelectIssue();
  // L'onglet Résultats étant multi-projets, le projet source est porté par
  // l'option sélectionnée (dataset), pas par le sélecteur global.
  const nom = opt ? opt.dataset.projet : '';
  const numero = opt ? opt.dataset.numero : '';
  const zone = document.getElementById('zone-issue');
  if (!numero || !nom) {
    zone.innerHTML = '<div class="issue-vide">Aucune issue à afficher</div>';
    return;
  }
  zone.innerHTML = '<div class="issue-vide">Chargement de l\'issue #' + escapeHtml(numero) + '…</div>';
  try {
    const rep = await fetch('/issue/' + encodeURIComponent(nom) + '/' + encodeURIComponent(numero));
    const it = await rep.json();
    if (it.erreur) {
      zone.innerHTML = '<div class="issue-vide">Erreur : ' + escapeHtml(it.erreur) + '</div>';
      return;
    }
    const ferme = (it.state || '').toUpperCase() === 'CLOSED';
    let html = '';
    html += '<div class="issue-titre">#' + escapeHtml(it.number) + ' — ' + escapeHtml(it.title) + '</div>';

    // Badge coloré du projet source (couleur cohérente avec les filtres).
    html += '<div><span class="badge-projet" style="background:'
          + couleurProjetResultats(nom) + '">'
          + '<span class="pastille"></span>' + escapeHtml(nom) + '</span></div>';

    html += '<div class="issue-badges">';
    html += '<span class="badge-etat ' + (ferme ? 'ferme' : 'ouvert') + '">'
          + (ferme ? 'fermé' : 'ouvert') + '</span>';
    for (const lab of (it.labels || [])) {
      html += badgeLabel(lab.name || lab);
    }
    html += '</div>';

    // Bouton « Annuler cette issue » : uniquement si l'issue est ouverte, porte
    // le label for-linux (donc destinée au watcher), n'est pas déjà en échec
    // (needs-human) et n'a encore aucun commentaire. Un commentaire signifie que
    // le watcher a capté l'issue et posté son ACK : CCL tourne déjà, l'annulation
    // serait sans effet — on masque le bouton pour ne pas induire en erreur.
    const nomsLabels = (it.labels || []).map(l => ((l.name || l) || '').toLowerCase());
    const comments = it.comments || [];
    const annulable = !ferme
      && nomsLabels.includes('for-linux')
      && !nomsLabels.includes('needs-human')
      && comments.length === 0;
    if (annulable) {
      html += '<div class="bloc-annuler">'
            + '<button class="danger" onclick="annulerIssue(\'' + nom + '\', '
            + Number(it.number) + ')">'
            + 'Annuler cette issue</button></div>';
    } else if (!ferme
      && nomsLabels.includes('for-linux')
      && !nomsLabels.includes('needs-human')
      && comments.length > 0) {
      html += '<div class="bloc-annuler">'
            + '<span class="traitement-encours">'
            + '⏳ En cours de traitement — annulation impossible</span></div>';
    }

    html += '<div class="issue-body">' + escapeHtml(it.body || '(pas de description)') + '</div>';

    const comms = it.comments || [];
    html += '<div class="issue-sep">Commentaires (' + comms.length + ')</div>';
    if (!comms.length) {
      html += '<div class="issue-vide">Aucun commentaire</div>';
    } else {
      // La réponse de CCL (dernier commentaire) est affichée en premier ;
      // les autres commentaires suivent dans l'ordre chronologique.
      const dernier = comms.length - 1;
      const ordre = [dernier, ...comms.map((_, i) => i).filter(i => i !== dernier)];
      ordre.forEach(i => {
        const c = comms[i];
        const auteur = (c.author && c.author.login) ? c.author.login : (c.author || 'inconnu');
        const resultat = (i === dernier) ? ' resultat' : '';
        // Le dernier commentaire (réponse de CCL) porte un bouton « Copier ».
        const boutonCopier = (i === dernier)
          ? '<button class="btn-copier" onclick="copierReponse(this)">Copier la réponse</button>'
          : '';
        html += '<div class="commentaire' + resultat + '">'
              + boutonCopier
              + '<div class="commentaire-auteur">' + escapeHtml(auteur)
              + (resultat ? ' — résultat CCL' : '') + '</div>'
              + '<div class="commentaire-corps">' + escapeHtml(c.body || '') + '</div>'
              + '</div>';
      });
    }
    zone.innerHTML = html;
  } catch(e) {
    zone.innerHTML = '<div class="issue-vide">Erreur réseau : ' + escapeHtml(e.message) + '</div>';
  }
}

// Copie le texte de la réponse CCL (dernier commentaire) dans le presse-papier.
// Feedback visuel « ✓ Copié ! » pendant 2 s. Fallback silencieux (sélection du
// texte + warning console) si navigator.clipboard est indisponible (non-HTTPS).
async function copierReponse(btn) {
  const bloc = btn.closest('.commentaire');
  const corps = bloc ? bloc.querySelector('.commentaire-corps') : null;
  if (!corps) return;
  const texte = corps.textContent || '';
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
      btn.disabled = true;
      btn.textContent = '✓ Copié !';
      setTimeout(function() {
        btn.textContent = 'Copier la réponse';
        btn.disabled = false;
      }, 2000);
      return;
    } catch(e) {
      console.warn('copierReponse : échec navigator.clipboard, fallback sélection.', e);
    }
  } else {
    console.warn('copierReponse : navigator.clipboard indisponible (contexte non-HTTPS), fallback sélection.');
  }
  // Fallback : on sélectionne le texte du bloc pour permettre un Ctrl+C manuel.
  const sel = window.getSelection();
  if (sel) {
    const range = document.createRange();
    range.selectNodeContents(corps);
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

// Ferme une issue en attente sur GitHub (pas encore traitée par le watcher),
// puis rafraîchit l'affichage et la combobox.
async function annulerIssue(nom, numero) {
  if (!confirm("Annuler (fermer) l'issue #" + numero + " sur GitHub ?")) return;
  try {
    const rep = await fetch('/annuler-issue/' + encodeURIComponent(nom)
                            + '/' + encodeURIComponent(numero), {method: 'POST'});
    const json = await rep.json();
    if (!json.succes) {
      alert('Erreur : ' + (json.message || 'échec de l\'annulation.'));
      return;
    }
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
    return;
  }
  // Recharge la liste (l'issue devient fermée) puis réaffiche la même issue.
  const cible = nom + '/' + numero;
  await chargerListeIssues();
  const sel = document.getElementById('select-issue');
  if ([...sel.options].some(o => o.value === cible)) {
    sel.value = cible;
    await afficherIssue();
  }
}

function naviguerIssue(delta) {
  // Navigation par position dans la liste consolidée visible (les numéros ne
  // sont plus contigus puisqu'ils proviennent de plusieurs projets).
  const select = document.getElementById('select-issue');
  const n = select.options.length;
  if (!n || !select.options[select.selectedIndex] ||
      !select.options[select.selectedIndex].dataset.numero) return;
  let cible = select.selectedIndex + delta;
  if (cible < 0 || cible >= n) return;
  select.selectedIndex = cible;
  afficherIssue();
}

function collecterFormulaire() {
  const notifs = [...document.querySelectorAll('input[name=notifs]:checked')].map(c => c.value);
  return {
    projet:          document.getElementById('projet').value,
    titre:           document.getElementById('titre').value.trim(),
    priorite:        document.getElementById('priorite').value,
    timeout:         document.getElementById('timeout').value,
    mode:            document.querySelector('input[name=mode]:checked').value,
    notifs:          notifs,
    corps:           document.getElementById('corps').value.trim(),
    modele_ponctuel: document.getElementById('modele-ponctuel').value,
  };
}

function afficherMessage(texte, type) {
  const el = document.getElementById('message');
  el.textContent = texte;
  el.className = 'message ' + type;
  el.style.display = 'block';
}

function cacherRetours() {
  document.getElementById('message').style.display = 'none';
  document.getElementById('zone-apercu').style.display = 'none';
}

async function afficherApercu() {
  cacherRetours();
  const data = collecterFormulaire();
  if (!data.titre) { afficherMessage('Le titre est obligatoire.', 'erreur'); return; }
  const rep = await fetch('/apercu', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const json = await rep.json();
  const zone = document.getElementById('zone-apercu');
  zone.textContent = json.commande;
  zone.style.display = 'block';
}

// Affiche le modal de confirmation et résout true (envoyer) / false (annuler).
function afficherModalConfirmation(issues) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    document.getElementById('modal-titre').textContent =
      '⚠️ ' + issues.length + ' issue(s) en attente sur ce projet :';
    document.getElementById('modal-liste').innerHTML = issues.map(it =>
      '#' + escapeHtml(String(it.number)) + ' — ' + escapeHtml(it.title || '(sans titre)')
    ).join('<br>');
    const btnOui = document.getElementById('modal-oui');
    const btnNon = document.getElementById('modal-non');
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

// Modal de confirmation générique (titre + libellés de boutons personnalisés,
// sans liste). Réutilise le même overlay ; restaure les libellés d'origine à la
// fermeture. Résout true (bouton de gauche/oui) ou false (annuler).
function afficherModalGenerique(titre, texteOui, texteNon) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    const liste   = document.getElementById('modal-liste');
    const btnOui  = document.getElementById('modal-oui');
    const btnNon  = document.getElementById('modal-non');
    const ouiAvant = btnOui.textContent;
    const nonAvant = btnNon.textContent;
    document.getElementById('modal-titre').textContent = titre;
    liste.style.display = 'none';
    btnOui.textContent  = texteOui;
    btnNon.textContent  = texteNon;
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      btnOui.textContent = ouiAvant;
      btnNon.textContent = nonAvant;
      liste.style.display = '';
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

// Détecte une incohérence entre le projet sélectionné et le champ PROJET de
// l'en-tête bridge. Fiable : on ne fait plus d'analyse textuelle (source de
// faux positifs) — on lit le champ « | PROJET | … | » que new_issue.py insère
// dans l'en-tête, et que Claude Chat reproduit dans le corps qu'il fournit.
// Retourne {projetIssue, projetSelectionne} si les deux diffèrent, sinon null
// (champ absent → pas de vérification ; identique → pas de modale).
function detecterIncoherenceProjet(data) {
  const corps = data.corps || '';
  // Ligne du tableau markdown : « | PROJET | valeur | ». La valeur est la
  // 3e cellule, capturée entre le 2e et le 3e séparateur « | ».
  const m = corps.match(/^\s*\|\s*PROJET\s*\|([^|]*)\|/im);
  if (!m) return null;                                  // champ absent : pas de vérif
  const projetIssue = m[1].trim();
  if (!projetIssue) return null;                        // valeur vide : pas de vérif
  const projetSelectionne = (data.projet || '').trim();
  if (projetIssue.toLowerCase() === projetSelectionne.toLowerCase()) {
    return null;                                        // identique : pas de modale
  }
  return {projetIssue, projetSelectionne};
}

// Modal d'alerte d'incohérence projet ⇄ corps. Réutilise l'overlay des issues
// en attente pour un rendu cohérent ; restaure libellés et liste à la
// fermeture. Résout true (envoyer quand même) / false (annuler).
function afficherModalIncoherence(projetIssue, projetSelectionne) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    const liste   = document.getElementById('modal-liste');
    const btnOui  = document.getElementById('modal-oui');
    const btnNon  = document.getElementById('modal-non');
    const ouiAvant = btnOui.textContent;
    const nonAvant = btnNon.textContent;
    document.getElementById('modal-titre').textContent = '⚠️ Incohérence détectée';
    liste.style.display = '';
    liste.innerHTML =
      'L\'en-tête de l\'issue indique le projet « <b>' + escapeHtml(projetIssue) + '</b> » '
      + 'mais tu envoies sur <b>' + escapeHtml(projetSelectionne) + '</b>.'
      + '<br><br>Envoyer quand même sur <b>' + escapeHtml(projetSelectionne) + '</b> ?';
    btnOui.textContent = 'Envoyer quand même';
    btnNon.textContent = 'Annuler';
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      btnOui.textContent = ouiAvant;
      btnNon.textContent = nonAvant;
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

async function envoyerIssue() {
  cacherRetours();
  const data = collecterFormulaire();
  if (!data.titre) { afficherMessage('Le titre est obligatoire.', 'erreur'); return; }

  // Avertit si des issues for-linux sont déjà en attente sur ce projet, pour
  // éviter les conflits quand plusieurs issues mode_write s'enchaînent.
  try {
    const repAttente = await fetch('/issues-en-attente/' + encodeURIComponent(data.projet));
    const enAttente  = await repAttente.json();
    if (Array.isArray(enAttente) && enAttente.length) {
      const confirmer = await afficherModalConfirmation(enAttente);
      if (!confirmer) return;   // l'utilisateur a annulé l'envoi
    }
  } catch(e) {
    // La vérification a échoué (réseau, gh…) : on n'empêche pas l'envoi.
  }

  // Second garde-fou : si on a déjà envoyé une issue dans cette session sur un
  // AUTRE projet, on confirme explicitement la cible avant d'envoyer.
  if (sessionDernierEnvoi && sessionDernierEnvoi !== data.projet) {
    const ok = await afficherModalGenerique(
      'Attention : tu envoies sur ' + data.projet
        + ' (dernier envoi : ' + sessionDernierEnvoi + '). Confirmer ?',
      'Oui, envoyer sur ' + data.projet,
      'Annuler');
    if (!ok) return;
  }

  // Garde-fou ciblé : alerte seulement si le champ PROJET de l'en-tête diffère
  // du projet sélectionné (issue partie sur le mauvais dépôt).
  try {
    const incoherence = detecterIncoherenceProjet(data);
    if (incoherence) {
      const ok = await afficherModalIncoherence(
        incoherence.projetIssue, incoherence.projetSelectionne);
      if (!ok) return;   // l'utilisateur a annulé l'envoi
    }
  } catch(e) {
    // La détection a échoué : on n'empêche pas l'envoi.
  }

  const btn = document.getElementById('btn-envoyer');
  btn.disabled = true; btn.textContent = 'Envoi…';
  try {
    const rep = await fetch('/envoyer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const json = await rep.json();
    if (json.succes) {
      afficherMessage('✓ Issue créée : ' + json.url, 'succes');
      sessionDernierEnvoi = data.projet;   // mémorise la cible du dernier envoi
      viderFormulaire(false);
    } else {
      afficherMessage('Erreur : ' + json.erreur, 'erreur');
    }
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
  btn.disabled = false; btn.textContent = "Envoyer l'issue";
}

async function chargerWatchers() {
  const rep  = await fetch('/watchers');
  const liste = await rep.json();
  const tbody = document.getElementById('corps-watchers');
  tbody.innerHTML = '';
  for (const w of liste) {
    const tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid #f0efe9';
    tr.innerHTML = `
      <td style="padding:10px 0;text-align:center">
        <input type="checkbox" class="cb-watcher" value="${w.nom}"
               onchange="mettreAJourCompte()">
      </td>
      <td style="padding:10px 4px">
        <span style="width:8px;height:8px;border-radius:50%;
              background:${w.actif ? '#5cb85c' : '#d9534f'};
              display:inline-block"></span>
      </td>
      <td style="padding:10px 12px;font-size:13px">${w.nom}</td>
      <td style="padding:10px 12px;font-size:13px;color:#888">${w.depot}</td>
      <td style="padding:10px 0;font-size:12px;color:#aaa">
        ${w.actif ? 'pid ' + w.pid : '—'}
      </td>`;
    tbody.appendChild(tr);
  }
  mettreAJourCompte();
  document.getElementById('cb-tous').checked = false;
}

function selectionnerTous(cb) {
  document.querySelectorAll('.cb-watcher').forEach(c => c.checked = cb.checked);
  mettreAJourCompte();
}

function mettreAJourCompte() {
  const n = document.querySelectorAll('.cb-watcher:checked').length;
  document.getElementById('compte-selection').textContent =
    n === 0 ? 'Aucun sélectionné' : `${n} sélectionné(s)`;
}

async function actionWatchers(action) {
  const selectionnes = [...document.querySelectorAll('.cb-watcher:checked')].map(c => c.value);
  if (!selectionnes.length) {
    const msg = document.getElementById('msg-watchers');
    msg.textContent = 'Sélectionne au moins un projet.';
    msg.className = 'message erreur'; msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 3000);
    return;
  }
  document.getElementById('msg-watchers').style.display = 'none';

  const route   = action === 'arreter' ? '/arreter-watcher' : '/lancer-watcher';
  const payload = action === 'lancer'
    ? (nom) => ({projet: nom, relancer: false})
    : (nom) => ({projet: nom, relancer: action === 'relancer'});

  for (const nom of selectionnes) {
    await fetch(route, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload(nom))
    });
  }
  await chargerWatchers();
  await verifierStatut();
}

function mettreAJourBoutonEnvoi() {
  const ecriture = document.querySelector('input[name=mode]:checked').value === 'ecriture';
  const btn = document.getElementById('btn-envoyer');
  btn.style.background    = ecriture ? '#a32d2d' : '#1a1a18';
  btn.style.borderColor   = ecriture ? '#a32d2d' : '#1a1a18';
}

// Détection de « #Titre: … » en première ligne du corps.
// Permet de coller titre + corps en un seul copier-coller dans le champ #corps :
// si la première ligne commence par « #Titre: » (insensible à la casse, espaces
// tolérés après « : »), on déplace ce qui suit dans #titre et on retire cette
// ligne du corps. Le champ #titre reste éditable normalement ; taper directement
// dedans ne déclenche aucun comportement automatique (l'écouteur est sur #corps).
function detecterTitreDansCorps() {
  const corpsEl = document.getElementById('corps');
  const valeur  = corpsEl.value;
  const finLigne      = valeur.indexOf('\n');
  const premiereLigne = finLigne === -1 ? valeur : valeur.slice(0, finLigne);
  const m = premiereLigne.match(/^#titre:\s*(.*)$/i);
  if (!m) return;

  // Mémorise le mode courant : la détection ne touche pas au mode, mais on
  // n'appelle mettreAJourBoutonEnvoi() que s'il a effectivement changé.
  const modeAvant = document.querySelector('input[name=mode]:checked').value;

  document.getElementById('titre').value = m[1].trim();
  // Supprime la première ligne (et son saut de ligne) du corps.
  corpsEl.value = finLigne === -1 ? '' : valeur.slice(finLigne + 1);

  const modeApres = document.querySelector('input[name=mode]:checked').value;
  if (modeApres !== modeAvant) mettreAJourBoutonEnvoi();
}
document.getElementById('corps').addEventListener('input', detecterTitreDansCorps);

async function verifierStatut() {
  const nom = document.getElementById('projet').value;
  try {
    const rep  = await fetch('/statut/' + encodeURIComponent(nom));
    const json = await rep.json();
    const dot  = document.getElementById('dot-statut');
    const txt  = document.getElementById('texte-statut');
    const btn  = document.getElementById('btn-watcher');
    if (json.actif) {
      dot.style.background = '#5cb85c';
      txt.style.color      = '#155724';
      txt.textContent      = 'Watcher actif (pid ' + json.pid + ')';
      btn.textContent      = 'Relancer le watcher';
    } else {
      dot.style.background = '#d9534f';
      txt.style.color      = '#888';
      txt.textContent      = 'Watcher inactif';
      btn.textContent      = 'Lancer le watcher';
    }
  } catch(e) { /* réseau indisponible — on ignore */ }
}

async function lancerWatcher() {
  const btn = document.getElementById('btn-watcher');
  btn.disabled = true; btn.textContent = 'Démarrage…';
  try {
    const rep  = await fetch('/lancer-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: document.getElementById('projet').value})
    });
    const json = await rep.json();
    if (!json.succes) afficherMessage('Erreur watcher : ' + json.erreur, 'erreur');
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
  btn.disabled = false;
  await verifierStatut();
}

// Au chargement : restaure le dernier projet mémorisé (localStorage) s'il
// correspond encore à une option existante, puis initialise l'accent visuel, le
// statut et les infos via onProjetChange(). Sonde ensuite toutes les 5 s.
(function restaurerProjet() {
  const select = document.getElementById('projet');
  let dernier = null;
  try { dernier = localStorage.getItem('bridge_projet_actif'); } catch(e) {}
  if (dernier && [...select.options].some(o => o.value === dernier)) {
    select.value = dernier;
  }
  onProjetChange();
})();
setInterval(verifierStatut, 5000);

// ─── Cycle de vie : onglet ↔ serveur ──────────────────────────────────────
// Deux liens : (1) heartbeat navigateur → serveur, qui laisse le serveur se
// couper tout seul quand l'onglet est fermé ; (2) canal SSE serveur → onglet,
// qui affiche un overlay quand le serveur s'arrête (Ctrl+C ou coupure brutale).
let sourceEvents     = null;
let timerErreurArret = null;

function afficherOverlayArret() {
  const ov = document.getElementById('overlay-arret');
  if (ov) ov.classList.add('actif');
}

// Heartbeat périodique : signale au serveur que l'onglet est toujours ouvert.
function envoyerHeartbeat() {
  fetch('/heartbeat', {method: 'POST'}).catch(() => {});
}

// Avant tout déchargement (F5, Ctrl+R, navigation, fermeture), on pose un
// drapeau : au chargement suivant, sa présence révèle un simple rechargement.
window.addEventListener('beforeunload', function() {
  try { sessionStorage.setItem('_refresh', '1'); } catch(e) {}
});

function demarrerCycleVie() {
  // Distinction refresh / fermeture : si le drapeau est présent, c'était un
  // rechargement — on le retire et on reprend normalement. S'il est absent,
  // c'était une vraie fermeture (mais alors le serveur est déjà coupé : le
  // heartbeat interrompu l'a fait s'arrêter, donc ce code ne s'exécute pas).
  try {
    if (sessionStorage.getItem('_refresh')) sessionStorage.removeItem('_refresh');
  } catch(e) {}

  envoyerHeartbeat();
  setInterval(envoyerHeartbeat, 5000);

  // Canal serveur → onglet.
  sourceEvents = new EventSource('/events');

  // Arrêt propre du serveur (Ctrl+C) : event « shutdown » explicite.
  sourceEvents.addEventListener('shutdown', function() {
    if (timerErreurArret) { clearTimeout(timerErreurArret); timerErreurArret = null; }
    sourceEvents.close();
    afficherOverlayArret();
  });

  // Connexion (r)établie : annule une éventuelle alerte en attente.
  sourceEvents.onopen = function() {
    if (timerErreurArret) { clearTimeout(timerErreurArret); timerErreurArret = null; }
  };

  // Coupure brutale (serveur tué sans signal) : la connexion SSE tombe en
  // erreur. Délai de 3 s avant l'overlay pour ne pas réagir à un micro-freeze ;
  // si la connexion se rétablit entre-temps, onopen annule le timer.
  sourceEvents.onerror = function() {
    if (timerErreurArret) return;
    timerErreurArret = setTimeout(function() {
      timerErreurArret = null;
      afficherOverlayArret();
    }, 3000);
  };
}
demarrerCycleVie();

// Arrêt volontaire depuis l'onglet : window.close() est autorisé par le
// navigateur car déclenché par une action utilisateur (contrairement à Ctrl+C
// côté serveur, qui ne peut que déclencher l'overlay via /events). On prévient
// le serveur (/quitter pose arret_demande puis os._exit après 2 s) et on ferme.
async function quitter() {
  if (!confirm('Arrêter new_issue.py et fermer l\'onglet ?')) return;
  await fetch('/quitter', {method: 'POST'});
  window.close();
}

function viderFormulaire(cacherMsg=true) {
  if (cacherMsg) cacherRetours();
  document.getElementById('titre').value = '';
  document.getElementById('corps').value = '';
  document.getElementById('priorite').value = 'normale';
  // Réinitialise le timeout sur la valeur TIMEOUT_CLAUDE du projet courant.
  mettreAJourInfoProjet();
  document.querySelector('input[name=mode][value=lecture]').checked = true;
  mettreAJourBoutonEnvoi();
  document.querySelectorAll('input[name=notifs]').forEach(c => c.checked = false);
  document.getElementById('modele-ponctuel').value = '';
}
</script>
</body>
</html>"""


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

@app.route("/login", methods=["GET"])
def login():
    """Formulaire de connexion. Redirige vers l'accueil si aucune authentification
    n'est requise ou si la session est déjà authentifiée."""
    if not MOT_DE_PASSE or session.get("authentifie"):
        return redirect(url_for("index"))
    bloque = session.get("echecs", 0) >= MAX_ECHECS_LOGIN
    erreur = ("Trop de tentatives échouées. Redémarrez le serveur pour réessayer."
              if bloque else "")
    return render_template_string(TEMPLATE_LOGIN, erreur=erreur, bloque=bloque)


@app.route("/login", methods=["POST"])
def login_post():
    """Vérifie le mot de passe saisi (sha256) contre MOT_DE_PASSE du .conf.
    Bloque la session après MAX_ECHECS_LOGIN tentatives échouées."""
    if not MOT_DE_PASSE:
        return redirect(url_for("index"))
    if session.get("echecs", 0) >= MAX_ECHECS_LOGIN:
        return render_template_string(
            TEMPLATE_LOGIN, bloque=True,
            erreur="Trop de tentatives échouées. Redémarrez le serveur pour réessayer.")

    saisi = request.form.get("mot_de_passe", "")
    if hashlib.sha256(saisi.encode("utf-8")).hexdigest() == MOT_DE_PASSE:
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


@app.route("/logout")
def logout():
    """Ferme la session et renvoie vers le formulaire de connexion."""
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_requis
def index():
    return render_template_string(TEMPLATE, projets=lister_projets(),
                                  auth_active=bool(MOT_DE_PASSE))


@app.route("/apercu", methods=["POST"])
@login_requis
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


@app.route("/envoyer", methods=["POST"])
@login_requis
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


@app.route("/journal/<nom_projet>")
@login_requis
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


@app.route("/issues-liste/<nom_projet>")
@login_requis
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
             "--json",  "number,title,state,labels"],
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


@app.route("/issue/<nom_projet>/<numero>")
@login_requis
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


@app.route("/issues-en-attente/<nom_projet>")
@login_requis
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


@app.route("/annuler-issue/<nom_projet>/<numero>", methods=["POST"])
@login_requis
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


@app.route("/config/<nom_projet>")
@login_requis
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


@app.route("/config/<nom_projet>", methods=["POST"])
@login_requis
def post_config(nom_projet):
    """Enregistre les clés éditables dans le .conf."""
    data = request.json or {}
    ok, msg = sauvegarder_conf(nom_projet, data)
    return jsonify(succes=ok, message=msg)


@app.route("/watchers")
@login_requis
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


@app.route("/lancer-watcher", methods=["POST"])
@login_requis
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


@app.route("/arreter-watcher", methods=["POST"])
@login_requis
def arreter_watcher_route():
    """Arrête le watcher du projet."""
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    ok, msg = arreter_watcher(cfg)
    return jsonify(succes=ok, message=msg)


@app.route("/statut/<nom_projet>")
@login_requis
def statut(nom_projet):
    """Indique si le watcher de ce projet est en cours d'exécution."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(actif=False)
    actif, pid = watcher_actif(cfg)
    return jsonify(actif=actif, pid=pid)


@app.route("/heartbeat", methods=["POST"])
def heartbeat():
    """Le navigateur signale que l'onglet est toujours ouvert. Met à jour
    l'horodatage surveillé par surveiller_heartbeat()."""
    global last_heartbeat, heartbeat_recu
    last_heartbeat = time.time()
    heartbeat_recu = True
    return jsonify(ok=True)


@app.route("/events")
@login_requis
def events():
    """SSE dédié au cycle de vie (séparé du journal watcher).
    Envoie un keepalive toutes les 5 s ; dès qu'un signal d'arrêt a été reçu
    (arret_demande), émet un event « shutdown » puis ferme la connexion."""
    def generer():
        dernier_ping = time.time()
        while True:
            if arret_demande:
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


@app.route("/quitter", methods=["POST"])
@login_requis
def quitter():
    """Arrêt volontaire déclenché par le bouton « Quitter » de l'onglet.
    Positionne arret_demande (l'overlay /events sert de filet de sécurité si
    window.close() est bloqué), répond immédiatement, puis coupe le processus
    après 2 s — le délai laisse le navigateur recevoir la réponse et exécuter
    window.close() avant que le serveur ne disparaisse."""
    global arret_demande
    arret_demande = True

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


def demarrer_tunnel():
    """Vérifie l'installation de cloudflared et sa config, puis lance le tunnel
    bridge-agent en arrière-plan (stdout/stderr silencieux sauf erreur). Stocke
    le processus dans la variable globale proc_tunnel. Termine le programme
    (exit 1) avec un message clair si un prérequis manque ou si le tunnel meurt
    immédiatement au démarrage."""
    global proc_tunnel

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

    print(f"Tunnel cloudflared démarré (pid {proc_tunnel.pid})")
    print(f"URL : {URL_TUNNEL}")


def arreter_tunnel():
    """Arrête proprement le tunnel cloudflared s'il a été démarré et tourne
    encore. Sans effet si aucun tunnel n'est actif (mode local ou déjà arrêté)."""
    global proc_tunnel
    if proc_tunnel is not None and proc_tunnel.poll() is None:
        try:
            proc_tunnel.terminate()
            proc_tunnel.wait(timeout=3)
        except Exception:
            pass
        print("Tunnel cloudflared arrêté.")


def surveiller_heartbeat():
    """Thread daemon : coupe le serveur (SIGTERM sur son propre PID) si l'onglet
    navigateur a cessé d'émettre des heartbeats depuis plus de DELAI_HEARTBEAT_MAX
    secondes. Tant qu'aucun heartbeat n'a jamais été reçu (serveur qui démarre,
    ou lancé en --no-browser), aucune surveillance : on n'auto-coupe jamais un
    serveur qui n'a pas encore eu de client."""
    while True:
        time.sleep(INTERVALLE_HEARTBEAT)
        if heartbeat_recu and (time.time() - last_heartbeat) > DELAI_HEARTBEAT_MAX:
            os.kill(os.getpid(), signal.SIGTERM)
            return

def main():
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

    # Deux modes de fonctionnement :
    #   • local (défaut)      : host 127.0.0.1, HTTP simple, sans SSL. Destiné à
    #     un usage sur place (devant le ThinkPad) — pas d'exposition réseau. Le
    #     mot de passe n'est PAS requis (mais reste appliqué s'il est configuré,
    #     via le décorateur @login_requis : aucune régression en mode local).
    #   • externe (--externe) : host 0.0.0.0, HTTPS + mot de passe OBLIGATOIRES.
    #     Destiné à l'accès distant (téléphone via tunnel).
    if args.externe:
        global MODE_EXTERNE
        MODE_EXTERNE = True
        host   = "0.0.0.0"
        schema = "https"

        # En mode externe, refuser de démarrer si aucun mot de passe n'est
        # configuré : l'interface serait exposée au réseau sans authentification.
        if not MOT_DE_PASSE:
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
    # positionnant arret_demande, puis on laisse ~1,5 s à la connexion SSE pour
    # livrer l'event « shutdown » avant de terminer le processus.
    def gestionnaire_arret(signum, frame):
        global arret_demande
        arret_demande = True
        arreter_tunnel()
        Timer(1.5, lambda: os._exit(0)).start()

    signal.signal(signal.SIGINT, gestionnaire_arret)
    signal.signal(signal.SIGTERM, gestionnaire_arret)

    # Mode --externe : démarrage automatique du tunnel cloudflared avant
    # d'exposer le serveur. Vérifie les prérequis (cloudflared + config) et
    # quitte proprement (exit 1) en cas de problème. L'arrêt est géré par le
    # gestionnaire de signal ci-dessus et par la route /quitter.
    if args.externe:
        demarrer_tunnel()

    # Surveillance des heartbeats du navigateur (daemon → ne bloque jamais
    # l'arrêt du processus si le gestionnaire de signal est lent).
    Thread(target=surveiller_heartbeat, daemon=True).start()

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

#!/usr/bin/env python3
"""
new_issue.py — Interface web de création d'issues pour le bridge inter-agents.
Lit les configs configs/*.conf, propose un formulaire pour chaque projet.

Usage :
    python3 new_issue.py
    python3 new_issue.py --port 5100
    python3 new_issue.py --no-browser
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask, Response, jsonify, render_template_string, request

# Partage du lecteur de config avec watcher.py (même dossier).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from watcher import Config, charger_config  # noqa: E402

DOSSIER_SCRIPT = Path(__file__).resolve().parent

app = Flask(__name__)
app.config["SECRET_KEY"] = "bridge-agent-local"


# Clés modifiables via l'interface (les autres : NOM, DEPOT, REP_TRAVAIL,
# PERIMETRE, CMD_BACKUP se changent à la main dans le .conf).
CLES_EDITABLES = {
    "TOPIC_NTFY", "LABEL", "INTERVALLE", "MAX_ESSAIS",
    "TIMEOUT_CLAUDE", "SCRIPT_BIP", "LOG_TAILLE_MAX_MO", "LOG_ARCHIVES",
    "MODELE_CCL",
}


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
body{font-family:system-ui,sans-serif;font-size:14px;background:#f0efe9;color:#1a1a18;min-height:100vh;padding:28px 16px}
.fenetre{max-width:860px;margin:0 auto;background:#fff;border:1px solid #ddd;border-radius:12px;overflow:hidden}
.entete{padding:14px 20px;border-bottom:1px solid #eee;display:flex;align-items:center;gap:9px}
.entete h1{font-size:15px;font-weight:500}
.entete .statut{margin-left:auto;font-size:12px;color:#888}
.bandeau-projet{display:flex;flex-direction:column;gap:8px;
  padding:12px 20px;border-bottom:1px solid #eee;background:#faf9f6}
.bandeau-ligne{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.bandeau-ligne label{font-size:13px;color:#555;font-weight:500;white-space:nowrap}
.bandeau-projet select{padding:7px 10px;border:1px solid #ddd;border-radius:6px;
  font-size:13px;background:#fff;color:#1a1a18;min-width:220px}
.bandeau-projet select:focus{outline:none;border-color:#888}
.onglets{display:flex;border-bottom:1px solid #eee;padding:0 20px}
.onglet{padding:10px 16px;font-size:13px;color:#777;cursor:pointer;border-bottom:2px solid transparent;margin-bottom:-1px;user-select:none}
.onglet.actif{color:#1a1a18;font-weight:500;border-bottom-color:#1a1a18}
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
.badge-etat{font-size:12px;font-weight:500;padding:3px 10px;border-radius:12px}
.badge-etat.ouvert{background:#d4edda;color:#155724}
.badge-etat.ferme{background:#e2e3e5;color:#555}
.badge-label{font-size:11px;padding:3px 9px;border-radius:12px;
  background:#eef;color:#3b3b8f;border:1px solid #dde}
.issue-body{background:#f8f8f5;border:1px solid #e0dfda;border-radius:6px;padding:12px;
  font-family:monospace;font-size:12px;white-space:pre-wrap;word-break:break-word;
  max-height:200px;overflow-y:auto;line-height:1.6;margin-bottom:16px}
.issue-sep{font-size:11px;font-weight:500;color:#999;text-transform:uppercase;
  letter-spacing:.06em;margin:16px 0 10px;padding-bottom:6px;border-bottom:1px solid #f0efe9}
.commentaire{border:1px solid #e0dfda;border-radius:6px;padding:12px;margin-bottom:10px;
  background:#fff}
.commentaire.resultat{border-color:#b7d7c0;background:#f6fbf7}
.commentaire-auteur{font-size:12px;font-weight:500;color:#555;margin-bottom:6px}
.commentaire-corps{font-family:monospace;font-size:12px;white-space:pre-wrap;
  word-break:break-word;line-height:1.6;color:#1a1a18}
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

    <!-- Ligne 2 : nom du dépôt et du répertoire, sous la combobox et le statut -->
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
    <textarea id="corps" placeholder="## Contexte&#10;…&#10;&#10;## Tâche demandée&#10;…&#10;&#10;## Résultat attendu&#10;…"></textarea>

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

    <div class="barre-issue">
      <select id="select-issue" title="Issues récentes du projet"></select>
      <button onclick="naviguerIssue(-1)" title="Issue précédente">←</button>
      <button onclick="naviguerIssue(1)" title="Issue suivante">→</button>
      <button class="primaire" onclick="afficherIssue()">Afficher</button>
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

    <div class="champ" style="margin-bottom:14px">
      <label>Projet</label>
      <select id="config-projet" onchange="chargerConfig()">
        {% for p in projets %}
        <option value="{{ p.nom }}">{{ p.nom }}</option>
        {% endfor %}
      </select>
    </div>

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

<script>
let sourceSSE = null;

let intervalWatchers = null;

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
  verifierStatut();
  mettreAJourInfoProjet();
  chargerListeIssues();
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
  const nom = document.getElementById('config-projet').value;
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
  const nom = document.getElementById('config-projet').value;
  const data = {
    TOPIC_NTFY:        document.getElementById('conf-TOPIC_NTFY').value,
    LABEL:             document.getElementById('conf-LABEL').value,
    INTERVALLE:        document.getElementById('conf-INTERVALLE').value,
    MAX_ESSAIS:        document.getElementById('conf-MAX_ESSAIS').value,
    TIMEOUT_CLAUDE:    document.getElementById('conf-TIMEOUT_CLAUDE').value,
    SCRIPT_BIP:        document.getElementById('conf-SCRIPT_BIP').value,
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
    term.appendChild(div);
    term.scrollTop = term.scrollHeight;
  };
  sourceSSE.onerror = function() {
    const div = document.createElement('div');
    div.className = 'log-warn';
    div.textContent = '— connexion perdue, tentative de reconnexion…';
    document.getElementById('terminal').appendChild(div);
  };
}

function viderTerminal() {
  document.getElementById('terminal').innerHTML = '';
}

// ─── Onglet Résultats : visualisation des issues ──────────────────────────
async function chargerListeIssues() {
  const nom = document.getElementById('projet').value;
  const select = document.getElementById('select-issue');
  select.innerHTML = '<option value="">(chargement…)</option>';
  try {
    const rep = await fetch('/issues-liste/' + encodeURIComponent(nom));
    const liste = await rep.json();
    if (!Array.isArray(liste) || !liste.length) {
      select.innerHTML = '<option value="">(aucune issue)</option>';
      return;
    }
    select.innerHTML = '';
    for (const it of liste) {
      const etat = (it.state || '').toUpperCase() === 'CLOSED' ? 'fermé' : 'ouvert';
      const opt = document.createElement('option');
      opt.value = it.number;
      opt.textContent = `#${it.number} — ${it.title} [${etat}]`;
      select.appendChild(opt);
    }
  } catch(e) {
    select.innerHTML = '<option value="">(erreur de chargement)</option>';
  }
}

function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t == null ? '' : t;
  return d.innerHTML;
}

async function afficherIssue() {
  const nom = document.getElementById('projet').value;
  const numero = document.getElementById('select-issue').value;
  const zone = document.getElementById('zone-issue');
  if (!numero) {
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

    html += '<div class="issue-badges">';
    html += '<span class="badge-etat ' + (ferme ? 'ferme' : 'ouvert') + '">'
          + (ferme ? 'fermé' : 'ouvert') + '</span>';
    for (const lab of (it.labels || [])) {
      html += '<span class="badge-label">' + escapeHtml(lab.name || lab) + '</span>';
    }
    html += '</div>';

    html += '<div class="issue-body">' + escapeHtml(it.body || '(pas de description)') + '</div>';

    const comms = it.comments || [];
    html += '<div class="issue-sep">Commentaires (' + comms.length + ')</div>';
    if (!comms.length) {
      html += '<div class="issue-vide">Aucun commentaire</div>';
    } else {
      comms.forEach((c, i) => {
        const auteur = (c.author && c.author.login) ? c.author.login : (c.author || 'inconnu');
        const resultat = (i === comms.length - 1) ? ' resultat' : '';
        html += '<div class="commentaire' + resultat + '">'
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

function naviguerIssue(delta) {
  const select = document.getElementById('select-issue');
  const courant = parseInt(select.value, 10);
  if (isNaN(courant)) return;
  const cible = courant + delta;
  if (cible < 1) return;
  // Aligne la combobox sur la cible si elle y figure ; sinon on garde la valeur.
  const existe = [...select.options].some(o => parseInt(o.value, 10) === cible);
  if (existe) select.value = String(cible);
  else {
    const opt = new Option('#' + cible, String(cible), true, true);
    select.add(opt);
  }
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

async function envoyerIssue() {
  cacherRetours();
  const data = collecterFormulaire();
  if (!data.titre) { afficherMessage('Le titre est obligatoire.', 'erreur'); return; }
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

// Sonde le statut au chargement puis toutes les 5 secondes.
verifierStatut();
mettreAJourInfoProjet();
setInterval(verifierStatut, 5000);

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


# ─── Routes Flask ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(TEMPLATE, projets=lister_projets())


@app.route("/apercu", methods=["POST"])
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


@app.route("/config/<nom_projet>")
def get_config(nom_projet):
    """Retourne les valeurs actuelles du .conf (champs lus + défauts)."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(erreur="Projet introuvable."), 404
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
        log_taille_max_mo = cfg.log_taille_max_mo,
        log_archives   = cfg.log_archives,
        modele_ccl     = cfg.modele_ccl,
    )


@app.route("/config/<nom_projet>", methods=["POST"])
def post_config(nom_projet):
    """Enregistre les clés éditables dans le .conf."""
    data = request.json or {}
    ok, msg = sauvegarder_conf(nom_projet, data)
    return jsonify(succes=ok, message=msg)


@app.route("/watchers")
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
def arreter_watcher_route():
    """Arrête le watcher du projet."""
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    ok, msg = arreter_watcher(cfg)
    return jsonify(succes=ok, message=msg)


@app.route("/statut/<nom_projet>")
def statut(nom_projet):
    """Indique si le watcher de ce projet est en cours d'exécution."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(actif=False)
    actif, pid = watcher_actif(cfg)
    return jsonify(actif=actif, pid=pid)


# ─── Point d'entrée ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Interface web de création d'issues — Bridge Agent"
    )
    parser.add_argument("--port", type=int, default=5100,
                        help="Port du serveur web (défaut : 5100)")
    parser.add_argument("--no-browser", action="store_true",
                        help="Ne pas ouvrir le navigateur automatiquement")
    args = parser.parse_args()

    if not args.no_browser:
        Timer(1.2, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    print(f"Bridge Agent — interface web sur http://localhost:{args.port}")
    print("Ctrl-C pour arrêter.")
    app.run(host="127.0.0.1", port=args.port, debug=False)


if __name__ == "__main__":
    main()

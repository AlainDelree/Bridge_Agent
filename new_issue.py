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


def demarrer_watcher(cfg: Config) -> int:
    """Arrête un éventuel watcher existant, en démarre un nouveau.
    Retourne le PID du nouveau processus."""
    pid_file = chemin_pid(cfg)
    actif, pid_ancien = watcher_actif(cfg)
    if actif and pid_ancien:
        try:
            os.kill(pid_ancien, signal.SIGTERM)
            time.sleep(0.8)   # laisser le temps de s'arrêter proprement
        except OSError:
            pass

    pid_file.parent.mkdir(parents=True, exist_ok=True)
    conf_file   = DOSSIER_SCRIPT / "configs" / f"{cfg.nom}.conf"
    watcher_script = DOSSIER_SCRIPT / "watcher.py"

    proc = subprocess.Popen(
        [sys.executable, str(watcher_script), "--config", str(conf_file)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,   # détaché : survit à la fermeture de Flask
    )
    pid_file.write_text(str(proc.pid))
    return proc.pid


# ─── Construction du body et des labels ───────────────────────────────────────

def construire_body(data: dict) -> str:
    """Construit le body markdown depuis les champs du formulaire."""
    mode     = "ÉCRITURE" if data.get("mode") == "ecriture" else "lecture seule"
    priorite = data.get("priorite", "normale")
    timeout  = data.get("timeout", "300")
    corps    = data.get("corps", "").strip()

    entete = "\n".join([
        "## En-tête\n",
        "| Champ    | Valeur |",
        "|----------|--------|",
        "| SOURCE   | CC |",
        "| DEST     | CCL |",
        "| RETOUR   | CC |",
        f"| MODE     | {mode} |",
        f"| PRIORITE | {priorite} |",
        f"| TIMEOUT  | {timeout}s |",
    ])
    return f"{entete}\n\n{corps}"


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

  <div class="onglets">
    <div class="onglet actif" onclick="basculerOnglet('creation')">Nouvelle issue</div>
    <div class="onglet" onclick="basculerOnglet('journal')">Journal watcher</div>
  </div>

  <!-- ─── Onglet 1 : création d'issue ──────────────────────────────────── -->
  <div id="panneau-creation" class="panneau actif">

    <div id="bandeau-statut" style="display:flex;align-items:center;gap:10px;
         margin-bottom:14px;padding:8px 12px;background:#f8f8f5;
         border:1px solid #e0dfda;border-radius:6px;font-size:13px">
      <span id="dot-statut" style="width:8px;height:8px;border-radius:50%;
            background:#ccc;flex-shrink:0"></span>
      <span id="texte-statut" style="color:#888;flex:1">Vérification…</span>
      <button id="btn-watcher" onclick="lancerWatcher()">Lancer le watcher</button>
    </div>

    <div class="rangee">
      <div class="champ">
        <label>Projet</label>
        <select id="projet" onchange="verifierStatut()">
          {% for p in projets %}
          <option value="{{ p.nom }}">{{ p.nom }} — {{ p.depot }}</option>
          {% endfor %}
        </select>
      </div>
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
      <label><input type="radio" name="mode" value="lecture" checked> Lecture seule</label>
      <label><input type="radio" name="mode" value="ecriture">
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
      <button class="danger" onclick="viderFormulaire()">Vider</button>
      <button onclick="afficherApercu()">Aperçu de la commande</button>
      <button class="primaire" id="btn-envoyer" onclick="envoyerIssue()">Envoyer l'issue</button>
    </div>
  </div>

  <!-- ─── Onglet 2 : journal watcher ───────────────────────────────────── -->
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

function basculerOnglet(nom) {
  document.querySelectorAll('.onglet').forEach((o, i) =>
    o.classList.toggle('actif', (i===0&&nom==='creation')||(i===1&&nom==='journal')));
  document.getElementById('panneau-creation').classList.toggle('actif', nom==='creation');
  document.getElementById('panneau-journal').classList.toggle('actif', nom==='journal');
  if (nom === 'journal') demarrerJournal();
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

function collecterFormulaire() {
  const notifs = [...document.querySelectorAll('input[name=notifs]:checked')].map(c => c.value);
  return {
    projet:   document.getElementById('projet').value,
    titre:    document.getElementById('titre').value.trim(),
    priorite: document.getElementById('priorite').value,
    timeout:  document.getElementById('timeout').value,
    mode:     document.querySelector('input[name=mode]:checked').value,
    notifs:   notifs,
    corps:    document.getElementById('corps').value.trim(),
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
setInterval(verifierStatut, 5000);

function viderFormulaire(cacherMsg=true) {
  if (cacherMsg) cacherRetours();
  document.getElementById('titre').value = '';
  document.getElementById('corps').value = '';
  document.getElementById('priorite').value = 'normale';
  document.getElementById('timeout').value = '300';
  document.querySelector('input[name=mode][value=lecture]').checked = true;
  document.querySelectorAll('input[name=notifs]').forEach(c => c.checked = false);
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


@app.route("/statut/<nom_projet>")
def statut(nom_projet):
    """Indique si le watcher de ce projet est en cours d'exécution."""
    cfg = projet_par_nom(nom_projet)
    if not cfg:
        return jsonify(actif=False)
    actif, pid = watcher_actif(cfg)
    return jsonify(actif=actif, pid=pid)


@app.route("/lancer-watcher", methods=["POST"])
def lancer_watcher():
    """Lance (ou relance) le watcher du projet sélectionné."""
    data = request.json or {}
    cfg  = projet_par_nom(data.get("projet", ""))
    if not cfg:
        return jsonify(succes=False, erreur="Projet introuvable.")
    try:
        pid = demarrer_watcher(cfg)
        return jsonify(succes=True, pid=pid)
    except Exception as e:
        return jsonify(succes=False, erreur=str(e))


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

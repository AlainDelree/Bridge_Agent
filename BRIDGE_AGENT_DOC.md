# Bridge_Agent — Documentation de référence

Document destiné à Claude Chat (CC) pour comprendre et utiliser le bridge
inter-agents d'Alain. À lire en début de conversation impliquant Bridge_Agent.

---

## 1. Vue d'ensemble

Bridge_Agent est un système qui permet à Claude Chat (toi) de déléguer des
tâches à Claude Code Linux (CCL) via des GitHub Issues. CCL s'exécute sur le
ThinkPad d'Alain et surveille les issues en continu.

**Flux complet :**
```
Claude Chat → crée une issue → GitHub → watcher.py détecte → CCL exécute
→ poste le résultat en commentaire → ferme l'issue → notification GSM/bureau
```

---

## 2. Projets actifs

| Nom | Dépôt GitHub | Répertoire de travail CCL | Topic ntfy |
|-----|-------------|--------------------------|------------|
| `bridge_agent` | AlainDelree/Bridge_Agent | ~/Bridge_Agent | (conf local) |
| `alchess` | AlainDelree/AlChess | ~/NicLink | (conf local) |
| `ff_galerie` | AlainDelree/FF_Galerie | ~/FF_Galerie | (conf local) |

Chaque projet a son propre watcher (`watcher.py --config configs/<nom>.conf`)
et son propre journal de log (`logs/watcher-<nom>.log`).

---

## 3. Créer une issue — la méthode normale

Via l'interface web `new_issue.py` (Flask, port 5100) :

```bash
# Mode local (devant le ThinkPad)
python3 new_issue.py

# Mode externe (accès depuis téléphone via Cloudflare)
python3 new_issue.py --externe
# → tunnel cloudflared automatique sur https://bridge.frederiqueferette.be
# → login mot de passe requis
```

**Format du corps pour copier-coller depuis Claude Chat :**

La première ligne du corps peut contenir `#Titre:` — new_issue.py détecte
ce tag et remplit automatiquement le champ Titre. Un seul copier-coller suffit :

```
#Titre: Titre court et actionnable

## Contexte
Pourquoi cette tâche existe.

## Tâche demandée
Description précise. Indiquer explicitement si LECTURE SEULE.

## Résultat attendu
Ce que CCL doit produire ou confirmer.
```

> ⚠️ **Claude Chat doit toujours inclure** `| PROJET | <nom> |` dans l'en-tête
> des issues qu'il génère (nom exact du projet cible : `bridge_agent`,
> `alchess`, `ff_galerie`). Détaillé au §6 « Champs spéciaux ».

---

## 4. Labels disponibles

| Label | Effet |
|-------|-------|
| `for-linux` | **Requis** — le watcher ne voit que ces issues |
| `bridge` | Marque l'issue comme tâche bridge (traçabilité) |
| `mode_write` | **ARME le mode écriture** — CCL peut modifier des fichiers |
| `needs-human` | Posé automatiquement après 3 échecs — stoppe le retraitement |
| `done` | Posé automatiquement au succès |
| `notif_pc` | Ajoute une notification bureau (notify-send) |
| `notif_gsm` | Ajoute une notification push (ntfy) |
| `notif_tous` | notify-send + ntfy |

---

## 5. Modes lecture seule vs écriture

**Lecture seule (défaut)** — CCL peut lire, analyser, grep, rapporter.
Ne peut PAS écrire de fichier ni exécuter de commande modifiant le système.
Idéal pour : diagnostics, audits, lectures de fichiers, comptages.

**Mode écriture (`mode_write`)** — CCL peut modifier des fichiers, exécuter
des commandes, faire des commits git.
Garde-fous automatiques :
- Backup pinné **avant** toute modification (via `CMD_BACKUP` du `.conf`)
- **JAMAIS `git push`** — Alain pousse lui-même après vérification
- Aucune commande destructrice sans demande explicite
- Périmètre strict : CCL ne travaille que dans le dossier configuré

---

## 6. Champs spéciaux dans le corps de l'issue

Le watcher lit ces champs dans le tableau markdown de l'en-tête :

| Champ | Valeur | Effet |
|-------|--------|-------|
| `PRIORITE` | `haute` ou `critique` | Retry infini (au lieu de 3 max) |
| `TIMEOUT` | ex. `600s` | Surcharge le timeout par défaut (300s) |
| `MODELE` | ex. `claude-opus-4-5` | Force un modèle CCL spécifique pour cette issue |
| `PROJET` | ex. `bridge_agent` | Détection d'incohérence dans `new_issue.py` (issue #44). Inséré automatiquement par l'interface. Claude Chat doit l'inclure dans toutes les issues qu'il génère. |

Format dans le corps :
```markdown
| PRIORITE | haute |
| TIMEOUT  | 600s  |
| MODELE   | claude-opus-4-5 |
| PROJET   | bridge_agent |
```

> ⚠️ **Claude Chat doit toujours inclure** `| PROJET | <nom> |` dans l'en-tête
> des issues qu'il génère, avec le nom exact du projet cible
> (`bridge_agent`, `alchess`, `ff_galerie`).

---

## 7. Périmètre par projet

CCL est contraint à un répertoire précis par projet — il refuse de travailler
hors périmètre même si l'issue le demande explicitement :

| Projet | Périmètre autorisé |
|--------|-------------------|
| `bridge_agent` | /home/alain/Bridge_Agent |
| `alchess` | /home/alain/NicLink |
| `ff_galerie` | /home/alain/FF_Galerie |

---

## 8. Sécurité

- **Défense en profondeur** : SSL + mot de passe (mode externe) + watcher
  éteint par défaut + périmètre CCL + git comme filet de retour arrière.
- **Mot de passe** : stocké hashé sha256 dans `configs/bridge_agent.conf`.
  Générer/changer : `python3 new_issue.py --set-password`
- **configs/*.conf** : gitignoré — jamais versionné (contient topic ntfy et
  mot de passe hashé).
- **ssl/** : gitignoré — certificat auto-signé, clé privée jamais versionnée.
- **Repo public** : le dépôt GitHub est public — le code source est lisible
  par tous. C'est sans risque car tout ce qui est sensible est gitignoré :
  `configs/*.conf` (topic ntfy, mot de passe hashé), `ssl/` (clé privée),
  `logs/`, `venv/`. Le repo ne contient que du code et de la documentation.

---

## 9. Accès externe

URL publique via tunnel Cloudflare :
```
https://bridge.frederiqueferette.be
```

Lancé automatiquement par `python3 new_issue.py --externe`.
Nécessite : cloudflared installé + `~/.cloudflared/config.yml` configuré
+ `MOT_DE_PASSE` dans le `.conf`.

**Accès à la doc sans token** : le repo étant public, `BRIDGE_AGENT_DOC.md`
est accessible directement (sans authentification) — utile pour les
instructions personnalisées Claude :
```
https://raw.githubusercontent.com/AlainDelree/Bridge_Agent/master/BRIDGE_AGENT_DOC.md
```

---

## 10. Structure du dépôt Bridge_Agent

```
~/Bridge_Agent/
  watcher.py          — watcher générique (prend --config)
  new_issue.py        — interface web Flask (port 5100)
  configs/            — gitignoré : un .conf par projet
    bridge_agent.conf
    alchess.conf
    ff_galerie.conf
  logs/               — journaux par projet (rotation par taille, archives datées)
    watcher-bridge_agent.log
    watcher-alchess.log
    watcher-ff_galerie.log
  ssl/                — gitignoré : certificat auto-signé
  venv/               — gitignoré : environnement Python
```

---

## 11. Conventions de code

- **Langue** : français pour tout ce qu'Alain et Claude nomment librement
  (identifiants Python, commentaires, clés de config). Anglais conservé pour
  les contrats existants (noms de labels GitHub, drapeaux CLI, mots-clés Python).
- **Issues** : produire titre + corps avec `#Titre:` en première ligne du corps.
  Alain colle le tout dans le champ Corps de new_issue.py — un seul copier-coller.
- **Mode par défaut** : lecture seule. N'armer `mode_write` que si la tâche
  demande explicitement une modification de fichier.
- **Dogfooding** : Bridge_Agent se développe lui-même via ses propres issues.

---

## 12. Règles d'usage

### Règle fondamentale : toujours passer par Claude Chat

Toute modification de Bridge_Agent ou des projets associés doit
être initiée par Claude Chat (CC) sous forme d'issue, même pour
les petits changements (une ligne CSS, un label, une couleur).

**Pourquoi :**
- **Traçabilité** : chaque modif a une issue qui explique le pourquoi,
  un diff connu de CC, un commit git pour le retour arrière.
- **Diagnostic** : si une régression apparaît, CC connaît le contexte
  exact de chaque changement récent.
- **Cohérence** : CC maintient une vision globale de l'architecture
  et évite les effets de bord.

**Workflow :**
1. Alain décrit l'idée à CC dans Claude Chat
2. CC génère l'issue (titre + corps avec `| PROJET | <nom> |`)
3. Alain colle dans new_issue.py et envoie
4. CCL exécute, committe, ne pousse pas
5. Alain vérifie (`git show`) et pousse

**Exception :** les modifications de `configs/*.conf` (`TOPIC_NTFY`,
`FICHIER_CONTEXTE`, etc.) peuvent se faire directement via
l'onglet Configuration de new_issue.py — elles ne touchent
pas au code et sont gitignorées.

---

## 13. Commandes utiles

```bash
# Lancer l'interface web (local)
cd ~/Bridge_Agent && source venv/bin/activate && python3 new_issue.py

# Lancer en mode externe (tunnel Cloudflare + HTTPS + login)
python3 new_issue.py --externe

# Configurer le mot de passe
python3 new_issue.py --set-password

# Lancer un watcher manuellement
python3 watcher.py --config configs/bridge_agent.conf
python3 watcher.py --config configs/bridge_agent.conf --dry-run

# Voir les watcher en cours
ps aux | grep watcher

# Vérifier les commits locaux non poussés
git log --oneline origin/master..HEAD
```

---

*Dernière mise à jour : juillet 2026 — Bridge_Agent v1, 3 projets actifs.*

#!/usr/bin/env python3
"""
watcher.py — Bridge inter-agents (multi-projets)
Surveille les GitHub Issues labelisées 'for-linux' d'un dépôt et les délègue à
Claude Code. Chaque projet est décrit par un fichier de config (--config).

Usage :
    python3 watcher.py --config configs/bridge_agent.conf
    python3 watcher.py --config configs/bridge_agent.conf --dry-run
    python3 watcher.py --config configs/bridge_agent.conf --interval 30

Lancement de plusieurs projets en parallèle :
    python3 watcher.py --config configs/bridge_agent.conf &
    python3 watcher.py --config configs/alchess.conf &
"""

import subprocess
import json
import time
import logging
import argparse
import sys
import os
import glob
import re
import hashlib
import tempfile
import platform
import signal
import shutil
import threading
import ctypes
import ctypes.wintypes
import base64
import binascii
from logging.handlers import RotatingFileHandler
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

# Canaux de notification factorisés (issue #187) : partagés avec new_issue.py
# via notifications.py, à la racine du projet. watcher.py tourne toujours avec
# WorkingDirectory = racine du dépôt (voir systemd/watcher@.service), donc
# l'import direct fonctionne. Les enveloppes bip()/notifier*() ci-dessous
# délèguent à ce module en passant les valeurs du CFG courant.
import notifications
# État partagé du quota GraphQL (issue #615) : rafraîchi après chaque appel gh
# SIGNIFICATIF (fermer_issue ci-dessous), lu par la route Flask /rate-limit.
import etat_rate_limit

# ─── Emplacements fixes (relatifs au script, PAS au cwd du projet) ─────────────
# Les journaux vivent à côté du watcher, quel que soit le projet piloté. Ils ne
# doivent surtout pas atterrir dans le répertoire de travail du projet (il change).
DOSSIER_SCRIPT = Path(__file__).resolve().parent
DOSSIER_LOGS   = DOSSIER_SCRIPT / "logs"

# Script bip PARTAGÉ (issue #630) : chemin utilisé par bip()/notifier()
# ci-dessous QUEL QUE SOIT `SCRIPT_BIP` du `.conf` — réglage par projet
# abandonné au profit du choix par issue (voir traitement_fin.py::son_a_jouer).
SCRIPT_BIP_PARTAGE = DOSSIER_SCRIPT / "scripts" / "traitement_fin.py"

# Code de sortie dédié à l'auto-extinction pour inactivité (issues #199/#200,
# service systemd #596). Distinct de 0 (arrêt normal/interruption manuelle,
# `sys.exit(0)` sur `KeyboardInterrupt`) pour que `systemd/watcher@.service`
# puisse le déclarer en `SuccessExitStatus` sous `Restart=on-failure` : un
# watcher qui s'éteint proprement pour inactivité n'est alors PAS relancé,
# alors qu'un crash (tout autre code de sortie non nul, ou terminaison par
# signal) l'est.
EXIT_INACTIVITE = 42

# Bootstrap automatique d'un service CCW dédié (issue #556, 2/3, champ
# d'en-tête CREATION — voir plus bas et BRIDGE_AGENT_DOC.md §16). Scripts
# PowerShell déjà en place (issue #170/#173/#174) : watcher.py les APPELLE,
# il ne réimplémente rien. DOSSIER_SCRIPT pointe TOUJOURS vers le clone
# Bridge_Agent (un seul watcher.py partagé par tous les services CCW, cf.
# §16 du DOC) : ce chemin résout correctement quel que soit le projet piloté
# par CETTE instance.
DOSSIER_PROVISIONING_WINDOWS = DOSSIER_SCRIPT / "provisioning" / "windows"
# Clé privée de bootstrap (issue #554) : dossier FRÈRE de Bridge_Agent
# (généré par provisionner.ps1 dans <RepCCW>\cles_bootstrap, jamais dans un
# clone git). DOSSIER_SCRIPT.parent == RepCCW, quel que soit son nom réel.
CHEMIN_CLE_PRIVEE_BOOTSTRAP = DOSSIER_SCRIPT.parent / "cles_bootstrap" / "bootstrap_privee.pem"
# Installation manuelle d'OpenSSL sur CCW (point d'attention #557, repris ici
# faute d'avoir #558 déjà mergé) : PAS sur le PATH par défaut, distincte de
# l'openssl embarqué par Git pour Windows utilisé par provisionner.ps1 pour
# la GÉNÉRATION de la paire de clés (Resoudre-OpenSSL côté PowerShell).
CHEMIN_OPENSSL_WIN64 = Path(r"C:\Program Files\OpenSSL-Win64\bin\openssl.exe")
TIMEOUT_CREATION_CLONE    = 600  # ajouter_projet_ccw.ps1 : clone git, potentiellement long
TIMEOUT_CREATION_FINALISE = 60   # finaliser_projet_ccw_auto.ps1 : pas de réseau (NSSM + tokens)

# scripts/traitement_fin.py (issue #352) : notifier_fin_issue()/notifier_debut_
# issue() (#515) y sont importées directement (pas via subprocess comme le bip)
# pour pouvoir les déclencher à chaque fin/début d'issue indépendamment des
# labels notif_* — voir notifier_fin_sse/notifier_debut_sse ci-dessous.
# scripts/ n'est pas un package : on l'ajoute au sys.path.
sys.path.insert(0, str(DOSSIER_SCRIPT / "scripts"))
import traitement_fin
from utils import ecrire_json_atomique as _ecrire_json_atomique

# Consignes injectées dans le PROMPT donné à CCL (architecture à trois couches,
# issues #209 puis #211). Vivent à côté du watcher (racine du dépôt), PAS dans le
# rep_travail du projet piloté : elles sont communes à tous les projets. Trois
# couches, de la plus générale à la plus spécifique (§12.1 de BRIDGE_AGENT_DOC.md) :
#   - consignes/globales.md          : NON-optionnel, injecté pour TOUTE issue
#                                       (rappels de sécurité transversaux) ;
#   - consignes/type_<type>.md       : optionnel, selon le TYPE déduit de l'issue
#                                       (ex. type_chef.md) ;
#   - consignes/projet_<projet>.md   : optionnel, selon le projet piloté.
# Depuis #211 l'injection se fait dans le prompt CCL (via lancer_claude), et NON
# plus dans le corps de l'issue GitHub : couverture universelle quel que soit le
# chemin de création (formulaire web, `gh issue create` d'un chef, création
# manuelle GitHub) — même modèle que FICHIER_CONTEXTE/CONTEXTE.md.
DOSSIER_CONSIGNES = DOSSIER_SCRIPT / "consignes"

# Historique des durées réelles de traitement (issue #108) : un fichier commun,
# une entrée par issue fermée {projet, type, mode, duree, date}. Vit dans logs/
# (déjà gitignoré, cohérent avec les .conf) : donnée de télémétrie locale, pas de
# source à versionner. Lu par app/issues.py pour estimer la durée d'une issue en
# cours (médiane du même projet+type+mode).
FICHIER_HISTORIQUE = DOSSIER_LOGS / "historique_durees.json"

# Traçabilité des écritures sur historique_durees.json / etat_timeout.json
# (issue #521) : une coupure nette de historique_durees.json (perte de données,
# 2026-09-07) n'avait laissé AUCUNE trace exploitable — fichier gitignoré comme
# tout logs/, donc ni diff ni commit ni horodatage pour dater ou expliquer
# l'événement après coup. Plutôt qu'une exception ciblée au .gitignore (le
# fichier grossit à chaque issue close, cf. scripts/archiver_historique.py —
# le suivre en git alourdirait chaque commit de sauvegarde CCL sans rapport
# avec la tâche en cours), un journal séparé append-only (JSON Lines), déjà
# couvert par le .gitignore existant de logs/ : une ligne par écriture
# significative, avec le nombre d'entrées/taille en octets AVANT et APRÈS.
# Une chute anormale (nb_avant très inférieur au nb_apres de la ligne
# précédente) devient visible et datable au moment où elle se produit, plutôt
# que constatée sans preuve après coup. Cf. _journaliser_ecriture.
FICHIER_JOURNAL_ECRITURES = DOSSIER_LOGS / "journal_ecritures_historique.jsonl"

# ─── Calibration automatique du TIMEOUT (issue #221) ───────────────────────────
# Deux fichiers d'état JSON, tous deux sous DOSSIER_LOGS (donc déjà gitignorés,
# et déjà PARTAGÉS entre tous les process watcher — DOSSIER_LOGS est fixe,
# relatif au script, pas au projet piloté, cf. commentaire en tête de fichier) :
#   - etat_timeout.json  : par combinaison (projet, TYPE, mode), l'EWMA de la
#     durée typique et de sa variabilité (issues réussies uniquement), plus le
#     multiplicateur de backoff (issues en timeout) — cf. maj_calibration_timeout.
#   - etat_ambiance.json : facteur d'ambiance F (F_reseau/F_local), EWMA à
#     demi-vie TEMPORELLE, GLOBAL à tous les projets — cf. _maj_ambiance.
# Formule (inspirée de l'algorithme RTO TCP, Jacobson/Karels), validée avec
# Alain :  TIMEOUT_suggéré = (duree_typique + k × variabilite) × F × backoff.
# Cette issue calcule et journalise TIMEOUT_suggéré à chaque clôture d'issue,
# mais NE modifie PAS le TIMEOUT réellement appliqué (celui de l'en-tête de
# l'issue reste seul décisif) — l'exposition/consultation est une 3e issue.
FICHIER_ETAT_TIMEOUT   = DOSSIER_LOGS / "etat_timeout.json"
FICHIER_ETAT_AMBIANCE  = DOSSIER_LOGS / "etat_ambiance.json"

K_VARIABILITE               = 3     # issue #475 : backtest sur 1070 observations (96% couverture, -20% de gaspillage vs K=4)
DEMI_VIE_ISSUES             = 15    # demi-vie de l'EWMA duree_typique/variabilite, EN NOMBRE D'ISSUES
ALPHA_EWMA_ISSUES           = 1 - 0.5 ** (1 / DEMI_VIE_ISSUES)
DEMI_VIE_AMBIANCE_HEURES    = 4.0   # demi-vie de l'EWMA F_reseau/F_local, TEMPORELLE (pas en nb d'issues)
SEUIL_SUCCES_RAPIDE         = 0.7   # succès compté « rapide » si duree_reelle < SEUIL × (duree_typique + k×variabilite)
                                     # — ancré sur le repère historique de la combinaison, PAS sur le TIMEOUT courant
                                     # (issue #590 : ce dernier inclut déjà le backoff, un backoff emballé rendrait
                                     # ce seuil inatteignable et empêcherait toute décroissance).
SUCCES_RAPIDES_POUR_RESET   = 3     # nb de succès rapides consécutifs pour réinitialiser le backoff
FACTEUR_BACKOFF             = 1.5   # multiplicateur appliqué à chaque timeout de la combinaison
# Plancher minimum du TIMEOUT_suggéré (secondes). Proposition à valider avec
# Alain : dans historique_durees.json actuel (546 issues réussies, aucun
# timeout encore enregistré au 2026-07-25), le 5e percentile des durées
# réelles est ~32s — 30s reste juste sous ce seuil, assez bas pour ne jamais
# gêner une issue légitimement courte, assez haut pour éviter qu'une suite de
# quelques échantillons atypiques (issues de 1-3s, probablement des échecs
# immédiats) ne fasse suggérer un TIMEOUT dérisoire pour une combinaison encore
# peu observée.
TIMEOUT_SUGGERE_PLANCHER    = 30
# Plafond absolu du TIMEOUT_suggéré (secondes), appliqué en DERNIER sur le
# résultat final du calcul (filet de sécurité, issue #590). Constaté sur
# relecture_bridge|normal|write|normal : un backoff resté emballé (succès
# rapide jamais atteignable, cf. SEUIL_SUCCES_RAPIDE ci-dessus) a produit un
# TIMEOUT_suggéré ~2 062 012s (~23 jours). Même après le correctif d'ancrage
# sur duree_typique, ce plafond reste une seconde ligne de défense contre tout
# scénario non anticipé qui ferait s'emballer le backoff à nouveau. 3600s (1h)
# reste largement au-dessus des complexités `lourd` observées à ce jour (cf.
# §19.4 du DOC) sans jamais retomber dans l'ordre de grandeur « des millions
# de secondes » d'origine.
TIMEOUT_SUGGERE_PLAFOND     = 3600

# Verrous anti-collision inter-process (issue #189). Chaque traitement pose un
# fichier de verrou associé au répertoire de travail EFFECTIF avant de lancer
# claude, et le libère à la fin (y compris en cas d'échec). But : garantir que
# JAMAIS deux process claude ne travaillent simultanément sur le MÊME dossier —
# là où l'ensemble en mémoire `issues_en_cours` ne protège qu'au sein d'un seul
# process watcher, pas entre deux instances/relances. Le verrou vit sous logs/
# (gitignoré), et NON dans le rep_travail lui-même : un fichier déposé dans le
# dossier de travail serait happé par le `git add -A` de la sauvegarde que CCL
# effectue à chaque tâche en mode écriture, puis committé par erreur.
DOSSIER_VERROUS = DOSSIER_LOGS / "verrous"

# Marge (secondes) ajoutée à la durée de traitement plausible d'une issue pour
# décider qu'un verrou est PÉRIMÉ (orphelin d'un watcher tué brutalement sans
# passer par le finally). Au-delà de cette péremption, aucun claude légitime ne
# peut encore tourner (chaque subprocess a son propre timeout) : le verrou est
# réputé abandonné et peut être repris.
PEREMPTION_MARGE_VERROU = 120

# ─── Protocole partagé (identique pour TOUS les projets) ───────────────────────
# Ces noms de labels sont la logique commune du bridge. Les mettre en config
# permettrait à un projet de diverger et de casser le protocole — c'est
# exactement la dérive qu'on veut éviter. Ils restent donc en dur.
# Le NOM des constantes est en français ; la VALEUR (entre guillemets) est le
# label réel sur GitHub, un contrat qu'on ne touche pas.

LABEL_ECRITURE  = "mode_write"    # ARME le mode écriture (--dangerously-skip-permissions)
LABEL_SCRATCH   = "mode_scratch"  # ARME la lecture active (écriture confinée au scratch, issue #327)
LABEL_ECHEC     = "needs-human"   # posé après échec définitif : stoppe le retraitement auto
LABEL_FAIT      = "done"          # posé au succès

# Posé à la création (issue #647) quand l'en-tête ne porte pas le champ
# optionnel REDACTEUR (issue #599) — signal purement informatif pour l'onglet
# Résultats (badge « Créée sans REDACTEUR »), jamais un rejet : REDACTEUR
# absent reste une création normale (voir valider_redacteur, scripts/
# watcher_issues_inbox.py). Ne bloque jamais rien.
LABEL_SANS_REDACTEUR = "sans-redacteur"

# Garde-fou explicite sur l'AUTEUR de l'issue (issue #563), en complément du
# filtre par labels (#477 ci-dessous dans lister_issues). Jusqu'ici, la seule
# protection contre une issue créée par un tiers était INDIRECTE : poser un
# label exige les droits d'écriture sur le dépôt GitHub, donc un inconnu sur un
# dépôt public ne peut pas rendre sa propre issue éligible. Cette protection
# cesse d'être suffisante dès qu'un collaborateur existe sur le dépôt (droits
# d'écriture, donc capable de labelliser N'IMPORTE QUELLE issue — y compris une
# qu'il n'a pas écrite lui-même) : elle pourrait alors être traitée en
# mode_write, voire déclencher CREATION (bootstrap automatique d'un service
# CCW, #556). En dur plutôt qu'en config (comme LABEL_* ci-dessus) : c'est un
# contrat de sécurité du protocole commun, pas un réglage qui doit pouvoir
# diverger d'un projet à l'autre par erreur.
AUTEURS_AUTORISES = {"AlainDelree"}

# ─── Mode de traitement à trois valeurs (issue #327) ───────────────────────────
# Remplace l'ancien booléen `autoriser_ecriture`, qui ne pouvait piloter que
# DEUX états — insuffisant depuis que #326 introduit un 3e mode, la « lecture
# active » (mode_scratch) : écriture confinée à un dossier scratch, pour les
# outils d'analyse (linters, eslint flat config ≥ 9, ...) qui exigent un vrai
# fichier de config sur disque, jamais dans le projet lui-même.
#
# Cinq points de décision lisent ce MODE unique (au lieu de tester chacun un
# booléen puis, à côté, un `if mode_scratch` empilé) : le flag
# --dangerously-skip-permissions, le bloc de garde-fou du prompt (lancer_claude),
# le backup projet (traiter_issue), le garde-fou technique configs/*.conf niveau
# 2 (#318), et l'étiquette de calibration TIMEOUT (§19). Un futur 4e mode
# n'ajoutera qu'une valeur ici plutôt que de retoucher cinq endroits épars.
MODE_LECTURE        = "lecture"         # défaut : diagnostic, aucune écriture
MODE_LECTURE_ACTIVE = "lecture_active"  # écriture confinée au scratch (label mode_scratch)
MODE_ECRITURE       = "ecriture"        # écriture libre dans REP_TRAVAIL (label mode_write)

# ─── Allowlist fine pour MODE_LECTURE (issue #542, révisé #546) ────────────────
# Confirmé par test direct du CLI `claude` (sans flag) : `git fetch`/`git pull`
# sont bloqués par le système de permissions interactif de Claude Code, qui
# demande une approbation — impossible à satisfaire en session non-interactive
# (`--print`, lancée par watcher.py). MODE_LECTURE n'a jamais eu
# --dangerously-skip-permissions (ce flag est réservé à
# MODE_ECRITURE/MODE_LECTURE_ACTIVE, cf. lancer_claude) : le désarmer entièrement
# pour débloquer ces commandes désarmerait TOUTES les protections en lecture
# seule, sans le filet de sécurité technique (empreinte avant/après) dont
# bénéficie la lecture active — inacceptable.
#
# Solution retenue : --allowedTools, mécanisme de Claude Code qui autorise des
# commandes précises SANS désarmer le reste (toute commande hors de cette liste
# continue de demander une approbation, donc reste bloquée en session
# non-interactive — comportement inchangé, fail-safe). Chaque entrée est un
# préfixe exact de ligne de commande (pas un motif large type "git *") :
#   - `git fetch`           : ne touche jamais l'arbre de travail (met seulement
#                              à jour les refs distantes) — read-only par nature.
#   - `git pull --ff-only`  : échoue si un fast-forward est impossible (jamais de
#                              merge, jamais de perte de travail local) — même
#                              opération que le `git pull --ff-only` que
#                              watcher.py effectue déjà lui-même en début de
#                              cycle sur REP_TRAVAIL (cf. CONTEXTE.md). `git pull`
#                              SANS --ff-only reste bloqué (merge/rebase = écriture
#                              non garantie sans risque).
#
# `Add-Type -AssemblyName` RETIRÉ (issue #546) : ce n'était pas un problème de
# préfixe ou de transmission de la liste, mais un plafond du CLI lui-même —
# confirmé en désassemblant le binaire `claude` installé (recherche de chaînes
# dans node_modules/@anthropic-ai/claude-code-linux-x64/claude) : toute commande
# PowerShell contenant "Add-Type" déclenche un classifieur codé en dur
# (fonction minifiée du type `function Ezp(e){if(fvo(e,"Add-Type"))return
# {behavior:"ask", message:"Command compiles and loads .NET code"}...}`) qui
# force la réponse "ask" — message identique, au mot près, à celui observé sur
# CCW dans l'issue de test. Un "ask" côté CLI exige une confirmation interactive
# et N'EST PAS pilotable par --allowedTools/settings.json : aucune entrée de
# cette liste n'aurait jamais pu débloquer cette commande. Il existe plusieurs
# classifieurs de ce genre, tous spécifiques à l'analyse statique PowerShell
# (Invoke-Expression, New-Object -ComObject, Start-Process -Verb runas, etc.) —
# un futur besoin similaire sur CCW doit d'abord être vérifié contre cette liste
# de classifieurs figés avant de supposer qu'une entrée --allowedTools suffira.
#
# git status/log/diff/show ne sont volontairement PAS dans cette liste : déjà
# testés non bloqués par défaut (heuristique interne de Claude Code), donc rien
# à y ajouter.
#
# Remarque #546 (non totalement élucidée) : sur CCW, un `git pull --ff-only`
# seul — préfixe pourtant exact — a malgré tout été bloqué ("This command
# requires approval", message générique de non-correspondance, PAS un
# classifieur dédié comme ci-dessus). Reproduction impossible depuis CCL : même
# construction de `cmd`, même liste, même ordre d'arguments → succès systématique
# en local (Linux, CLI 2.1.199). Cause plausible mais NON confirmée (accès à
# CCW hors du périmètre de cette tâche) : le passage de plusieurs éléments
# séparés après --allowedTools (option variadique `<tools...>` du CLI) traverse
# deux ré-encodages successifs de la ligne de commande sous Windows
# (list2cmdline de Python, puis le décodeur argv du binaire `claude.exe`) —
# absents côté Linux où execve reçoit l'argv tel quel, sans ré-échappement.
# Plusieurs entrées de cette liste contiennent un espace interne
# ("git pull --ff-only"), donc nécessitent un ré-échappement des guillemets à
# la traversée Windows, contrairement aux entrées sans espace. Correctif
# défensif appliqué : un seul argument, valeurs jointes par virgule (format
# alternatif documenté par `claude --help` : "Comma or space-separated list"),
# ce qui réduit la liste à transmettre à UN SEUL token au lieu de N — supprime
# le risque lié à la reségmentation variadique et minimise la surface exposée
# au ré-échappement Windows. À reconfirmer sur CCW par une nouvelle issue de
# test après ce correctif.
OUTILS_LECTURE_AUTORISES = [
    "Bash(git fetch:*)",
    "Bash(git pull --ff-only:*)",
]


def _deduire_mode(labels: list[str]) -> str:
    """Déduit le MODE de traitement (issue #327) des labels GitHub d'une issue.
    Priorité : mode_write (écriture) > mode_scratch (lecture active) > lecture
    seule par défaut — si les deux labels sont posés par erreur, l'écriture
    l'emporte, cohérent avec l'ancien comportement où seul LABEL_ECRITURE
    testait autoriser_ecriture."""
    if LABEL_ECRITURE in labels:
        return MODE_ECRITURE
    if LABEL_SCRATCH in labels:
        return MODE_LECTURE_ACTIVE
    return MODE_LECTURE


def _etiquette_calibration(mode: str) -> str:
    """Étiquette de calibration TIMEOUT (§19, clé projet|TYPE|mode) associée à
    un MODE de traitement (issue #327) : "write"/"read" existaient déjà,
    "scratch" est ajouté pour que la lecture active ait sa PROPRE population de
    durées — sinon on mélange des profils de durée hétérogènes (mêmes
    conséquences que le problème de mélange de populations corrigé côté UI par
    #326). Ces trois valeurs alimentent aussi bien etat_timeout.json
    (maj_calibration_timeout) que historique_durees.json (enregistrer_duree)."""
    return {MODE_ECRITURE: "write", MODE_LECTURE_ACTIVE: "scratch"}.get(mode, "read")

# Labels de notification (opt-in, cumulatifs avec le bip). Depuis l'issue #187,
# le dispatch concret selon ces labels vit dans notifications.py (module partagé
# avec new_issue.py) ; ces constantes restent ici comme contrat documentaire du
# protocole bridge (valeurs miroir de notifications.LABEL_NOTIF_*).
LABEL_NOTIF_PC   = "notif_pc"     # bip + notify-send (bulle bureau locale)
LABEL_NOTIF_GSM  = "notif_gsm"    # bip + ntfy (push téléphone)
LABEL_NOTIF_TOUS = "notif_tous"   # bip + notify-send + ntfy

PRIORITES_CRITIQUES = {"haute", "critique"}

# Pause (secondes) entre deux tentatives d'une même issue (backoff). Sert aussi
# à calculer, côté navigateur, le budget total de retry du badge (issue #106).
PAUSE_ENTRE_TENTATIVES = 5

# Backoff (secondes) entre les tentatives du COMMENTAIRE DE RÉSULTAT (issue #195).
# Contrairement à l'ACK et au message d'échec (best-effort), la trace du résultat
# est critique : sans elle, fermer l'issue effacerait silencieusement le travail.
# 1 tentative initiale + 3 tentatives espacées de 5, 10 puis 20 s.
DELAIS_RETRY_RESULTAT = (5, 10, 20)

# Marqueur non ambigu identifiant un commentaire de RÉSULTAT posté par le
# watcher (issue #237). Ligne HTML invisible sur GitHub, placée en tête du
# commentaire. Remplace le repérage par sous-chaîne "## Résultat", qui matchait
# aussi "## Résultat attendu" (titre de section présent dans quasi toutes les
# issues) — un faux positif aurait fermé une issue sans rien traiter si ce
# texte apparaissait un jour dans un commentaire.
MARQUEUR_RESULTAT = "<!-- bridge:resultat -->"

# Préfixe du message d'échec définitif posté par watcher.py juste avant de
# poser needs-human (voir plus bas, "❌ Échec après {N} tentatives."). Sert à
# détecter une RELANCE (champ RELANCE, issue #516) : sa présence dans
# l'historique de l'issue AVANT l'ACK courante signale que le worktree peut
# contenir du travail déjà fait par la tentative précédente — la durée
# mesurée serait alors artificiellement courte (issue #592).
MARQUEUR_ECHEC_TENTATIVES = "❌ Échec après"

# Abréviations du dictionnaire bridge
SOURCES = {"CC": "Claude Chat", "CCL": "Claude Code Linux", "CCW": "Claude Code Windows"}

# ─── Configuration par projet (ce qui CHANGE d'un projet à l'autre) ────────────

@dataclass
class Config:
    """Tout ce qui distingue un projet d'un autre. Rempli une fois au démarrage
    depuis le fichier --config, puis lu partout via l'objet global CFG."""
    # Requis
    nom: str             # identifiant court sans espaces (journal, préfixe notif, prompt)
    depot: str           # ex. "AlainDelree/Bridge_Agent"
    rep_travail: Path    # répertoire de travail de Claude Code pour CE projet
    topic_ntfy: str      # topic ntfy pour les push téléphone

    # Optionnels (défauts sensés)
    label: str            = "for-linux"
    intervalle: int       = 10
    max_essais: int       = 3
    timeout_claude: int   = 300
    timeout_chef: int     = 1200   # défaut plus généreux pour les issues « Chef : » sans TIMEOUT explicite (issue #106)
    timeout_diagnostic: int = 90   # timeout court et fixe de la passe diagnostique avant abandon non-critique (issue #124)
    script_bip: Path      = field(default_factory=lambda: DOSSIER_SCRIPT / "scripts" / "traitement_fin.py")
    tonalite_bip: int      = 0     # décalage de tonalité du bip en demi-tons, propre au projet (issue #526) ; 0 = tonalité normale
    log_taille_max_mo: int = 1     # rotation quand le journal dépasse cette taille (Mo)
    log_archives: int      = 5     # nombre d'archives datées conservées
    cmd_backup: str        = ""    # commande de sauvegarde avant modif (mode écriture)
    perimetre: str         = ""    # dossier(s) autorisés pour CCL (vide = pas de restriction)
    modele_ccl: str        = ""    # modèle CCL à utiliser (vide = défaut Claude Code)
    mot_de_passe: str      = ""    # hash sha256 du mot de passe d'accès web (vide = pas d'authentification)
    fichier_contexte: str  = ""    # fichier de contexte projet injecté dans le prompt (chemin relatif au rep_travail ou absolu ; vide = aucun)
    couleur: str           = ""    # couleur d'accent du projet dans l'interface (hex #RRGGBB ; vide = repli map fixe/hash côté frontend)
    perimetre_dynamique: bool = False  # périmètre fourni par l'issue (REPO_CIBLE) plutôt que figé dans le .conf — outil d'audit multi-dépôts (issue #125)
    notifier_local: bool   = True  # ce watcher émet-il lui-même bip/notify-send/ntfy à la fin d'une issue (issue #187) ? True = comportement historique. Mettre à False sur la VM CCW (et éventuellement CCL) pour laisser new_issue.py notifier de façon centralisée sur le ThinkPad, sans doublon.
    delai_inactivite_min: int = 20  # auto-extinction : minutes sans aucune issue traitable avant que le watcher ne s'arrête proprement (issue #200). 0 = désactivé (le watcher tourne indéfiniment, comportement historique).
    libelle_agent: str     = ""    # libellé de l'agent affiché dans l'ACK (ex. "agent Linux", "agent Windows") — vide = déduit automatiquement de la plateforme (issue #239)
    max_write_parallele: int = 2   # parallélisation mode_write via git worktrees (issue #337) : nombre max de tâches mode_write concurrentes, effectivement appliqué (déjà plafonné à 4, issue #568). 1 = comportement séquentiel historique (aucun worktree, aucun thread). 0 = désactivé (identique à 1).
    max_write_parallele_brut: int = 2  # valeur MAX_WRITE_PARALLELE telle que lue dans le .conf, AVANT plafonnement (issue #568) — sert uniquement à détecter et signaler un dépassement manuel à chaque cycle ; ne jamais l'utiliser pour piloter la parallélisation elle-même (voir max_write_parallele).
    seuil_alerte_worktrees: int = 3  # alerte accumulation de worktrees (issue #432) : au-delà de ce nombre de worktrees secondaires actifs (hors REP_TRAVAIL), un log.warning est émis à chaque cycle — le nettoyage (merge + git worktree remove + git branch -d) reste manuel, cf. WORKTREES.md.

    @property
    def url_ntfy(self) -> str:
        return f"https://ntfy.sh/{self.topic_ntfy}"

    @property
    def fichier_log(self) -> Path:
        return DOSSIER_LOGS / f"watcher-{self.nom}.log"

    @property
    def libelle_agent_effectif(self) -> str:
        """Libellé d'agent à afficher dans l'ACK. Priorité : LIBELLE_AGENT du
        .conf s'il est déclaré, sinon détection de plateforme (issue #239) —
        un même watcher.py tourne sur CCL (Linux) et CCW (Windows), et le
        libellé doit refléter la machine qui a réellement traité l'issue plutôt
        qu'un texte figé "agent Linux" trompeur côté Windows."""
        if self.libelle_agent:
            return self.libelle_agent
        return "agent Windows" if platform.system() == "Windows" else "agent Linux"


CHAMPS_REQUIS = ("NOM", "DEPOT", "REP_TRAVAIL", "TOPIC_NTFY")


def lire_conf(chemin: Path) -> dict:
    """Lecteur 'CLÉ = valeur' minimal, zéro dépendance.
    Ignore les lignes vides et les lignes commentées (#). Les clés sont
    normalisées en MAJUSCULES pour tolérer la casse."""
    donnees: dict[str, str] = {}
    for brut in chemin.read_text(encoding="utf-8").splitlines():
        ligne = brut.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, sep, valeur = ligne.partition("=")
        if not sep:                       # ligne sans '=' → ignorée
            continue
        donnees[cle.strip().upper()] = valeur.strip()
    return donnees


def charger_config(chemin: Path) -> Config:
    """Charge et valide un fichier de config. Échoue proprement (message clair +
    sortie) si un champ requis manque ou si un entier est mal formé — mieux vaut
    refuser de démarrer que tourner avec une config bancale."""
    if not chemin.exists():
        sys.exit(f"[config] Fichier introuvable : {chemin}")

    brut = lire_conf(chemin)

    manquants = [c for c in CHAMPS_REQUIS if not brut.get(c)]
    if manquants:
        sys.exit(f"[config] Champs requis manquants dans {chemin.name} : {', '.join(manquants)}")

    def entier(cle: str, defaut: int) -> int:
        val = brut.get(cle)
        if val is None or val == "":
            return defaut
        if not val.lstrip("-").isdigit():
            sys.exit(f"[config] {cle} doit être un entier (lu : '{val}')")
        return int(val)

    def booleen(cle: str, defaut: bool) -> bool:
        val = brut.get(cle)
        if val is None or val == "":
            return defaut
        return val.strip().lower() in ("true", "1", "oui", "yes", "vrai")

    return Config(
        nom         = brut["NOM"],
        depot       = brut["DEPOT"],
        rep_travail = Path(brut["REP_TRAVAIL"]).expanduser(),
        topic_ntfy  = brut["TOPIC_NTFY"],
        label       = brut.get("LABEL") or "for-linux",
        intervalle     = entier("INTERVALLE", 10),
        max_essais     = entier("MAX_ESSAIS", 3),
        timeout_claude = entier("TIMEOUT_CLAUDE", 300),
        timeout_chef   = entier("TIMEOUT_CHEF", 1200),
        timeout_diagnostic = entier("TIMEOUT_DIAGNOSTIC", 90),
        script_bip  = Path(brut["SCRIPT_BIP"]).expanduser() if brut.get("SCRIPT_BIP")
                      else DOSSIER_SCRIPT / "scripts" / "traitement_fin.py",
        tonalite_bip = entier("TONALITE_BIP", 0),
        log_taille_max_mo = entier("LOG_TAILLE_MAX_MO", 1),
        log_archives      = entier("LOG_ARCHIVES", 5),
        cmd_backup        = brut.get("CMD_BACKUP", ""),
        perimetre         = brut.get("PERIMETRE", ""),
        modele_ccl        = brut.get("MODELE_CCL", ""),
        mot_de_passe      = brut.get("MOT_DE_PASSE", ""),
        fichier_contexte  = brut.get("FICHIER_CONTEXTE", ""),
        couleur           = brut.get("COULEUR", ""),
        perimetre_dynamique = booleen("PERIMETRE_DYNAMIQUE", False),
        notifier_local      = booleen("NOTIFIER_LOCAL", True),
        delai_inactivite_min = entier("DELAI_INACTIVITE_MIN", 20),
        libelle_agent       = brut.get("LIBELLE_AGENT", ""),
        max_write_parallele = min(entier("MAX_WRITE_PARALLELE", 2), 4),
        max_write_parallele_brut = entier("MAX_WRITE_PARALLELE", 2),
        seuil_alerte_worktrees = entier("SEUIL_ALERTE_WORKTREES", 3),
    )


# Config globale, remplie dans main() avant toute utilisation.
CFG: Config = None  # type: ignore[assignment]

# ─── Journalisation ───────────────────────────────────────────────────────────
# Le logger existe dès l'import ; ses gestionnaires (fichier + console) sont
# ajoutés dans configurer_logs(), une fois qu'on connaît le nom du projet.
log = logging.getLogger("watcher")


class JournalRotatifDate(RotatingFileHandler):
    """Rotation déclenchée par la TAILLE (héritée de RotatingFileHandler), mais
    l'archive est nommée avec la date/heure de rotation plutôt que .1/.2 :
        watcher-<nom>.log.2026_07_11_08_02
    Le fichier actif garde son nom sans suffixe. Au-delà de backupCount archives,
    les plus anciennes sont supprimées."""

    def doRollover(self):
        if self.stream:
            self.stream.close()
            self.stream = None

        horodatage = datetime.now().strftime("%Y_%m_%d_%H_%M")
        cible = f"{self.baseFilename}.{horodatage}"
        # Deux rotations dans la même minute : on évite l'écrasement.
        if os.path.exists(cible):
            i = 1
            while os.path.exists(f"{cible}_{i}"):
                i += 1
            cible = f"{cible}_{i}"

        if os.path.exists(self.baseFilename):
            os.rename(self.baseFilename, cible)

        self._purger_archives()

        if not self.delay:
            self.stream = self._open()

    def _purger_archives(self):
        """Ne garde que les backupCount archives les plus récentes."""
        if self.backupCount <= 0:
            return
        archives = sorted(glob.glob(f"{self.baseFilename}.*"), key=os.path.getmtime)
        for vieux in archives[:-self.backupCount]:
            try:
                os.remove(vieux)
            except OSError:
                pass


def _forcer_utf8(flux):
    """Reconfigure un flux texte (stdout/stderr) en UTF-8 si possible.

    Sous Windows la console encode par défaut en cp1252 : les messages de log
    contenant de l'Unicode (→ ⚠️ ✗ …) déclenchent alors des UnicodeEncodeError
    répétées (« --- Logging error --- ») qui polluent ccw-service.log (le flux
    stdout est repris par NSSM). reconfigure() existe depuis Python 3.7 ; on le
    garde défensif (getattr) car certains flux redirigés ne l'exposent pas.
    Sous Linux, stdout est déjà en UTF-8 : l'appel est inoffensif (pas de
    régression)."""
    reconfigure = getattr(flux, "reconfigure", None)
    if reconfigure is not None:
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


def configurer_logs(cfg: Config):
    cfg.fichier_log.parent.mkdir(parents=True, exist_ok=True)
    # Portabilité Windows : force l'UTF-8 sur les flux console repris par le
    # StreamHandler (et par NSSM côté CCW). Le FileHandler, lui, reçoit déjà
    # encoding="utf-8" à sa construction.
    _forcer_utf8(sys.stdout)
    _forcer_utf8(sys.stderr)
    handler_fichier = JournalRotatifDate(
        cfg.fichier_log,
        maxBytes=cfg.log_taille_max_mo * 1024 * 1024,
        backupCount=cfg.log_archives,
        encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            handler_fichier,
            logging.StreamHandler(sys.stdout),
        ],
    )

# ─── Utilitaires ──────────────────────────────────────────────────────────────

# ─── Notifications ─────────────────────────────────────────────────────────────
# Depuis l'issue #187, la logique concrète des canaux (bip, notify-send, ntfy)
# vit dans notifications.py, partagé avec new_issue.py. Les fonctions ci-dessous
# sont des ENVELOPPES minces qui délèguent à ce module en injectant les valeurs
# du CFG courant (nom, url_ntfy, script_bip) et le logger du watcher. Les sites
# d'appel existants (succès/échec/alerte critique) restent inchangés.

def bip(fois=1, numero=None):
    """Bip sonore via le script PARTAGÉ (scripts/traitement_fin.py) — depuis
    l'issue #630, toujours ce script et une tonalité neutre, quels que soient
    `SCRIPT_BIP`/`TONALITE_BIP` du `.conf` (réglage par projet abandonné au
    profit du choix par issue, résolu par `traitement_fin.py::son_a_jouer()`
    à partir de `--projet`/`--numero` transmis ci-dessous). `CFG.script_bip`/
    `CFG.tonalite_bip` restent lus (tolérance d'un `.conf` existant qui porte
    encore ces clés) mais ne sont plus exposés à l'onglet Configuration ni
    n'influencent ce chemin (retrait de l'interface à l'issue #643)."""
    notifications.bip(SCRIPT_BIP_PARTAGE, fois, projet=CFG.nom, numero=numero)

def notifier_fin_sse(numero):
    """POST direct vers /notifier-fin-issue (issue #352), appelé à CHAQUE fin
    d'issue (succès ou échec définitif), DÉCOUPLÉ des labels notif_* : à la
    différence de notifier() ci-dessous (bip/notify-send/ntfy, opt-in par
    label), le rafraîchissement SSE de l'onglet Résultats doit être universel.
    Best-effort, timeout court, échec silencieux — voir
    traitement_fin.notifier_fin_issue."""
    traitement_fin.notifier_fin_issue(CFG.nom, numero)

def notifier_debut_sse(numero):
    """POST direct vers /notifier-debut-issue (issue #515), appelé une seule
    fois par traitement, juste après l'ACK — pendant côté DÉBUT de
    notifier_fin_sse : sans cet événement, une issue créée (ex. via
    issues_inbox) pendant qu'aucun onglet Résultats n'est ouvert ne
    déclencherait de rafraîchissement qu'à sa CLÔTURE, or `fin_issue` ne fait
    que mettre à jour une ligne déjà connue du navigateur — jamais en ajouter
    une nouvelle. Best-effort, timeout court, échec silencieux — voir
    traitement_fin.notifier_debut_issue."""
    traitement_fin.notifier_debut_issue(CFG.nom, numero)

def notifier_bureau(titre: str, message: str, urgence: str = "normal"):
    """Bulle de notification bureau via notify-send (voir notifications.py)."""
    notifications.notifier_bureau(CFG.nom, titre, message, urgence, log=log)

def notifier_ntfy(titre: str, message: str, priorite: str = "default"):
    """Notification push ntfy sur le topic du projet (voir notifications.py)."""
    notifications.notifier_ntfy(CFG.url_ntfy, titre, message, priorite, log=log)

def notifier(labels: list[str], titre: str, message: str,
             urgence_bureau: str = "normal", priorite_ntfy: str = "default",
             fois_bip: int = 1, numero=None):
    """Dispatch de notification selon les labels de l'issue.

    Garde issue #187 : si `NOTIFIER_LOCAL = false` dans le .conf, ce watcher
    n'émet AUCUN signal lui-même — la notification est laissée à new_issue.py,
    qui détecte la transition par polling GitHub et notifie de façon centralisée
    sur le ThinkPad d'Alain (évite les doublons, et fait remonter les transitions
    CCW dont le bip/notify-send tomberaient sinon dans la VM). Par défaut True :
    comportement historique préservé (notamment CCL, déjà fonctionnel).

    `numero`, si fourni, permet au bip de notifier new_issue.py de la fin de
    CETTE issue précise pour un rafraîchissement SSE instantané (issue #350).
    Script bip et tonalité : voir bip() ci-dessus (issue #630, toujours le
    script partagé, tonalité neutre — `CFG.script_bip`/`CFG.tonalite_bip` ne
    sont plus utilisés sur ce chemin)."""
    if not CFG.notifier_local:
        return
    notifications.notifier(
        labels, CFG.nom, CFG.url_ntfy, SCRIPT_BIP_PARTAGE,
        titre, message,
        urgence_bureau=urgence_bureau, priorite_ntfy=priorite_ntfy,
        fois_bip=fois_bip, numero=numero, log=log,
    )

def alerte_critique(numero, titre, tentative, labels: list[str]):
    """Alerte pour les issues haute/critique après échec."""
    msg = f"⚠️  ALERTE — Issue #{numero} '{titre}' — tentative {tentative} échouée — nouvelle tentative dans {CFG.intervalle}s"
    log.warning(msg)
    notifier(
        labels,
        titre=f"⚠️ {CFG.nom} #{numero} — alerte critique",
        message=f"Tentative {tentative} échouée : {titre}\nNouvelle tentative dans {CFG.intervalle}s.",
        urgence_bureau="critical",
        priorite_ntfy="high",
        fois_bip=3,  # 3 bips pour l'alerte critique (au lieu du bip simple par défaut)
        numero=numero,
    )

def gh(*args) -> dict | list | None:
    """Lance une commande gh et retourne le JSON parsé."""
    cmd = ["gh", *args, "--json"]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=30)
        if res.returncode != 0:
            log.error(f"gh erreur : {res.stderr.strip()}")
            return None
        return json.loads(res.stdout)
    except Exception as e:
        log.error(f"gh exception : {e}")
        return None

def _est_depot_git(rep: Path) -> bool:
    """Vrai si `rep` est situé dans un arbre de travail git valide (garde-fou du
    rafraîchissement automatique, issue #185). On sonde via
    `git rev-parse --is-inside-work-tree` plutôt qu'en testant l'existence d'un
    `.git` : robuste aux sous-répertoires et aux worktrees. Toute erreur (dossier
    absent, git introuvable) est traitée comme « pas un dépôt »."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=rep, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return res.returncode == 0 and res.stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def _tete_git(rep: Path) -> str | None:
    """SHA de HEAD dans `rep`, ou None si indéterminé. Sert à détecter si un
    `git pull` a réellement avancé l'historique, indépendamment de la locale du
    message git (le fast-forward français « Mise à jour … » contient « à jour »,
    ce qui rend toute détection par chaîne peu fiable — issue #185)."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=rep, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=10,
        )
        return res.stdout.strip() if res.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def rafraichir_depot(rep: Path, dry_run: bool = False):
    """Best-effort : rafraîchit le clone local via `git pull --ff-only` en début
    de cycle, pour qu'un watcher (CCL/CCW) travaille automatiquement sur le code
    le plus récent poussé sur origin, sans git pull manuel (issue #185).

    Sécurité par construction — `--ff-only` ne peut RIEN écraser :
      • historique local et distant non divergés → avance en fast-forward ;
      • déjà à jour ou local en avance (commits locaux poussables) → « Already up
        to date », aucune action ;
      • historique DIVERGÉ (backup+fix commité localement par CCL/CCW, en attente
        de push/revue par Alain) → le pull échoue proprement, RIEN n'est écrasé
        ni perdu ; on poursuit simplement sur le code local existant.

    Jamais bloquant : divergence, réseau indisponible ou dossier hors dépôt git
    sont journalisés (message distinct selon la cause) sans faire échouer le
    cycle — le pull est un confort de fraîcheur, pas une précondition.

    En dry-run, on n'altère pas l'arbre de travail local : on se contente de
    signaler ce qui serait fait (cohérent avec le reste du mode simulation)."""
    if not rep.is_dir():
        return
    if not _est_depot_git(rep):
        log.debug(f"  [pull] {rep} n'est pas un dépôt git — rafraîchissement ignoré.")
        return

    if dry_run:
        log.info(f"  [DRY-RUN] [pull] git pull --ff-only serait lancé dans {rep}.")
        return

    tete_avant = _tete_git(rep)

    try:
        res = subprocess.run(
            ["git", "pull", "--ff-only"],
            cwd=rep, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=60,
        )
    except subprocess.TimeoutExpired:
        log.warning(f"  [pull] échoué : délai dépassé sur git pull dans {rep} (réseau lent ?) — poursuite sur le code local.")
        return
    except Exception as e:
        log.warning(f"  [pull] échoué : {e} — poursuite sur le code local.")
        return

    if res.returncode == 0:
        # Détection avancement locale-indépendante : comparer HEAD avant/après
        # plutôt que le message git (« Mise à jour … » contient « à jour »).
        tete_apres = _tete_git(rep)
        if tete_avant and tete_apres and tete_avant != tete_apres:
            log.info(f"  [pull] {rep} mis à jour ({tete_avant[:7]} → {tete_apres[:7]}).")
        else:
            log.debug(f"  [pull] {rep} déjà à jour.")
        return

    # Échec : distinguer la cause pour un message clair et actionnable.
    err = (res.stderr + "\n" + res.stdout).strip()
    err_bas = err.lower()
    if "fast-forward" in err_bas or "diverg" in err_bas:
        log.info("  [pull] ignoré : commits locaux non poussés (fast-forward impossible — "
                 "backup/fix en attente de revue ?) — pensez à git push. Poursuite sur le code local.")
    elif ("could not resolve host" in err_bas or "connection" in err_bas
          or "unable to access" in err_bas or "timed out" in err_bas
          or "network is unreachable" in err_bas):
        premiere = err.splitlines()[0] if err else "réseau indisponible"
        log.warning(f"  [pull] échoué : réseau indisponible ({premiere}) — poursuite sur le code local.")
    else:
        premiere = err.splitlines()[0] if err else "erreur inconnue"
        log.warning(f"  [pull] échoué : {premiere} — poursuite sur le code local.")


def _lister_worktrees_secondaires(rep_travail: Path = None) -> list[dict]:
    """Liste les worktrees git du projet AUTRES que le worktree principal
    (`rep_travail`, par défaut `CFG.rep_travail`) — les répertoires frères
    créés pour la parallélisation mode_write (issue #337), via `git worktree
    list --porcelain`. Chaque entrée : {"chemin": str, "branche": str}.

    Paramètre explicite (plutôt que le seul `CFG` global) depuis l'issue
    #569 : permet à l'interface web (app/git_etat.py) de réutiliser cette
    fonction pour lister les worktrees de N'IMPORTE QUEL projet, pas
    seulement celui du watcher courant.

    Best-effort : dossier absent ou pas un dépôt git, ou toute erreur
    d'exécution git → liste vide, jamais d'exception propagée."""
    if rep_travail is None:
        rep_travail = CFG.rep_travail
    if not rep_travail.is_dir() or not _est_depot_git(rep_travail):
        return []
    try:
        res = subprocess.run(
            ["git", "-C", str(rep_travail), "worktree", "list", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if res.returncode != 0:
        return []

    worktrees: list[dict] = []
    courant: dict = {}
    for ligne in res.stdout.splitlines():
        if not ligne.strip():
            if courant:
                worktrees.append(courant)
                courant = {}
            continue
        cle, sep, valeur = ligne.partition(" ")
        if cle == "worktree":
            courant = {"chemin": valeur}
        elif cle == "branch":
            courant["branche"] = valeur.removeprefix("refs/heads/")
    if courant:
        worktrees.append(courant)

    principal = str(rep_travail.resolve())
    return [
        w for w in worktrees
        if w.get("chemin") and str(Path(w["chemin"]).resolve()) != principal
    ]


def verifier_accumulation_worktrees() -> None:
    """Alerte accumulation de worktrees (issue #432) : appelée en début de
    cycle, juste après `rafraichir_depot()`. Les worktrees créés pour la
    parallélisation mode_write (issue #337) ne sont jamais supprimés
    automatiquement — Alain merge et nettoie manuellement (`git worktree
    remove` + `git branch -d`, cf. WORKTREES.md §3). Sans signal, ils
    peuvent s'accumuler silencieusement.

    Au-delà de `CFG.seuil_alerte_worktrees` worktrees secondaires actifs
    (défaut 3), émet un log.warning listant chemin + branche de chacun, à
    CHAQUE cycle tant que le nombre reste au-dessus du seuil. En dessous,
    silence total — pas de log superflu. Pas de notification ntfy/bureau,
    volontairement : un WARNING dans le journal watcher suffit, visible
    depuis l'onglet Journal de l'interface web."""
    secondaires = _lister_worktrees_secondaires()
    if len(secondaires) <= CFG.seuil_alerte_worktrees:
        return
    detail = "; ".join(
        f"{w['chemin']} (branche {w.get('branche', '?')})" for w in secondaires
    )
    log.warning(
        f"⚠️  {len(secondaires)} worktrees git actifs pour {CFG.nom} "
        f"(seuil {CFG.seuil_alerte_worktrees}) — pensez à merger/nettoyer "
        f"(git worktree remove + git branch -d) : {detail}"
    )


def verifier_plafond_max_write_parallele() -> None:
    """Plafonnement défensif de MAX_WRITE_PARALLELE (issue #568) : le slider de
    l'onglet Configuration ne peut produire qu'une valeur entre 1 et 4, mais
    rien n'empêche Alain (ou un futur oubli) d'écrire directement une valeur
    ≥ 5 dans le .conf. `charger_config` a déjà plafonné `CFG.max_write_parallele`
    à 4 pour l'exécution en cours — le .conf lui-même n'est JAMAIS modifié
    (règle absolue du projet). Cette fonction, appelée en début de cycle,
    se contente de signaler l'écart tant qu'il persiste : un log.warning à
    CHAQUE cycle plutôt qu'une fois puis silence, cohérent avec
    `verifier_accumulation_worktrees` ci-dessus."""
    if CFG.max_write_parallele_brut <= 4:
        return
    log.warning(
        f"⚠️  MAX_WRITE_PARALLELE={CFG.max_write_parallele_brut} dans le .conf de {CFG.nom} "
        f"dépasse le plafond de 4 — 4 utilisé pour cette exécution (le .conf n'est jamais "
        f"modifié automatiquement ; corrigez-le à la main ou via le slider de l'onglet "
        f"Configuration)."
    )


def lister_issues():
    """Retourne la liste des issues (label du projet) ouvertes."""
    try:
        res = subprocess.run(
            ["gh", "issue", "list",
             "--repo", CFG.depot,
             "--label", CFG.label,
             "--state", "open",
             "--json", "number,title,body,labels,createdAt,author"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur gh issue list : {res.stderr.strip()}")
            return []
        issues = json.loads(res.stdout)
        # Garde-fou supplémentaire, en amont (issue #477) : ignore
        # silencieusement (pas de log, pas de tentative de traitement) toute
        # issue ne portant ni 'for-linux' ni 'for-windows'. Certains dépôts
        # (ex. FF_Galerie) génèrent leurs propres issues applicatives
        # (alertes, bugs détectés en production) qui ne sont pas destinées au
        # bridge. Le filtre existant sur CFG.label (--label ci-dessus) reste
        # inchangé — celui-ci est un filet de sécurité additionnel.
        issues = [
            i for i in issues
            if any(l.get("name", "") in ("for-linux", "for-windows")
                   for l in i.get("labels", []))
        ]
        # Garde-fou explicite sur l'AUTEUR (issue #563, cf. AUTEURS_AUTORISES en
        # tête de fichier). Contrairement au filtre #477 ci-dessus, une issue
        # rejetée ici N'EST PAS un simple non-match anodin : elle porte les BONS
        # labels (donc a été labellisée par quelqu'un ayant les droits
        # d'écriture sur le dépôt) mais ne vient pas d'un auteur autorisé — un
        # événement digne d'attention, d'où le log.warning explicite plutôt
        # qu'un filtrage silencieux.
        issues_autorisees = []
        for i in issues:
            auteur = (i.get("author") or {}).get("login", "")
            if auteur in AUTEURS_AUTORISES:
                issues_autorisees.append(i)
            else:
                log.warning(
                    f"Issue #{i.get('number')} ignorée : auteur '{auteur}' non "
                    f"autorisé (labels valides mais hors {sorted(AUTEURS_AUTORISES)}) — "
                    f"issue #563."
                )
        issues = issues_autorisees
        # Tri FIFO explicite : la plus ancienne issue en premier (issue #134).
        # createdAt est un timestamp ISO 8601 UTC (…Z), donc l'ordre
        # lexicographique croissant équivaut à l'ordre chronologique croissant.
        # On trie côté Python plutôt que via --order/--sort de gh pour rester
        # robuste aux différences de version de la CLI.
        issues.sort(key=lambda i: i.get("createdAt", ""))
        return issues
    except Exception as e:
        log.error(f"Exception lister_issues : {e}")
        return []

def issue_traitable(issue: dict) -> bool:
    """Vrai si l'issue déclenchera un vrai travail ce cycle : ni déjà 'done'
    (finalisation de fermeture seulement, issue #195), ni 'needs-human' (échec
    définitif, ignorée jusqu'à intervention humaine). Sert de définition de
    l'« activité » pour l'auto-extinction (issue #200) : une issue bloquée en
    needs-human ne doit jamais empêcher l'extinction de se déclencher. On se
    fonde uniquement sur les labels (pas d'appel réseau supplémentaire par
    issue) ; le cas 'résultat déjà posté sans label done' reste rare et sera de
    toute façon traité idempotemment par traiter_issue()."""
    labels = [l.get("name", "") for l in issue.get("labels", [])]
    return LABEL_ECHEC not in labels and LABEL_FAIT not in labels

def extraire_priorite(body: str) -> str:
    """Extrait la priorité depuis le body de l'issue (en-tête bridge)."""
    for ligne in body.splitlines():
        if "PRIORITE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                return parts[2].strip().lower()
    return "normale"

def est_titre_chef(titre: str) -> bool:
    """Vrai si le titre désigne une tâche « Chef » (pattern chef/ouvriers, §14).
    Cohérent avec la détection côté navigateur (app.js) : titre commençant par
    « Chef », insensible à la casse (ex. « Chef : orchestrer … »)."""
    return bool(re.match(r"chef\b", (titre or "").strip(), re.IGNORECASE))


# Types d'issue reconnus pour l'historique des durées (issue #108). L'ordre du
# tuple n'a pas d'importance ; « normal » est le repli.
TYPES_ISSUE = ("chef", "ouvrier", "spec_vue", "spec_metier", "spec_persistance", "normal")


def _classer_valeur_type(valeur: str) -> str | None:
    """Normalise une valeur brute (champ TYPE) vers un type canonique, ou None si
    elle ne correspond à rien de connu. Tolère les variantes (métier/metier,
    spec_vue/vue, …)."""
    v = (valeur or "").strip().lower()
    if not v:
        return None
    if "ouvrier" in v:
        return "ouvrier"
    if "chef" in v:
        return "chef"
    if "persistance" in v:
        return "spec_persistance"
    if "métier" in v or "metier" in v:
        return "spec_metier"
    if "vue" in v:
        return "spec_vue"
    return None


def deduire_type_issue(titre: str, body: str) -> str:
    """Déduit le TYPE d'une issue pour l'historique des durées (issue #108).
    Renvoie l'un de TYPES_ISSUE. Priorité : champ « | TYPE | … | » de l'en-tête
    bridge (source explicite, seul canal pour les spec_*), puis préfixe du titre
    (Chef/Ouvrier, cohérent avec est_titre_chef et app.js), sinon « normal »."""
    for ligne in (body or "").splitlines():
        if "| TYPE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                t = _classer_valeur_type(parts[2])
                if t:
                    return t
    # Repli sur le préfixe du titre : on n'y accepte QUE chef/ouvrier (un titre
    # « Ajouter la vue X » ne doit pas devenir spec_vue par accident).
    prefixe = _classer_valeur_type((titre or "").strip().split(":")[0])
    if prefixe in ("chef", "ouvrier"):
        return prefixe
    return "normal"


# ─── Consignes à trois couches injectées dans le prompt CCL (issues #209/#211) ──
# Auparavant (#209) ces consignes étaient injectées dans le CORPS de l'issue par
# app/issues.py::_consignes_injectees, uniquement pour les issues créées via le
# formulaire web. #211 déplace la logique ICI, dans le point d'assemblage unique
# du prompt CCL (lancer_claude), pour couvrir AUSSI les issues créées hors
# formulaire (`gh issue create` par un chef §14, création manuelle GitHub §3).

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
    """Bloc de consignes à trois couches à injecter dans le prompt CCL (issue #211,
    logique reprise de #209).

    Ordre : globales → type (si présent) → projet (si présent). Chaîne vide si
    aucune couche n'a de contenu. Garde-fous (identiques à #209) :
      - globales.md manquant → log.warning clair, mais on N'échoue PAS (le reste
        de l'injection et le traitement de l'issue se poursuivent) ;
      - type_<type>.md / projet_<projet>.md absents → comportement NORMAL, aucune
        injection pour cette couche, sans log ni avertissement bruyant.

    Le TYPE est déduit via deduire_type_issue sur le titre ET le corps RÉELS de
    l'issue traitée — peu importe qui l'a créée (formulaire, chef en CLI, GitHub) —
    donc le nom de fichier attendu est consignes/type_<type>.md (ex. type_chef.md).
    Le projet est celui piloté par ce watcher (CFG.nom)."""
    blocs = []

    # 1. Couche globale — NON-optionnelle (rappels de sécurité transversaux).
    globales = _lire_consigne(DOSSIER_CONSIGNES / "globales.md")
    if globales:
        blocs.append(globales)
    else:
        log.warning(
            "consignes/globales.md introuvable (%s) : consignes globales non "
            "injectées dans le prompt CCL — traitement poursuivi malgré tout.",
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


def _compter_etapes_checklist(body: str) -> int | None:
    """Nombre d'items de checklist Markdown (`- [ ]` / `- [x]`) dans le corps de
    l'issue (issue #220, champ nb_etapes_checklist), ou None si aucune checklist
    n'est présente — valeur brute, aucune interprétation de ce que représentent
    ces items."""
    n = sum(1 for ligne in (body or "").splitlines()
            if re.match(r"\s*[-*]\s*\[[ xX]\]", ligne))
    return n or None


def _detecter_tag_reseau(body: str) -> bool | None:
    """Extrait tag_reseau depuis le champ d'en-tête RESEAU (issue #220, implémenté
    #435) — « | RESEAU | oui | » / « | RESEAU | non | », calqué sur
    extraire_complexite. Insensible à la casse. 'oui' → True, 'non' → False,
    champ absent ou valeur non reconnue → None (aucun mot-clé deviné dans le
    corps). enregistrer_duree omet la clé tag_reseau de l'entrée tant que
    cette fonction renvoie None."""
    for ligne in (body or "").splitlines():
        if "| RESEAU" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip().lower()
                if valeur == "oui":
                    return True
                if valeur == "non":
                    return False
    return None


def _journaliser_ecriture(fichier: str, date_iso: str, *, operation: str,
                          nb_avant: int | None, nb_apres: int | None,
                          taille_avant_octets: int | None,
                          taille_apres_octets: int | None,
                          reinitialise_corruption: bool = False):
    """Ajoute une ligne au journal JSONL des écritures significatives sur
    historique_durees.json / etat_timeout.json (issue #521). Append-only, une
    ligne par écriture : nombre d'entrées et taille en octets AVANT/APRÈS,
    plus reinitialise_corruption=True si cette écriture est repartie d'un
    fichier illisible (le nombre d'entrées AVANT retombe alors à 0/None — la
    signature exacte d'une perte de données comme celle du 2026-09-07). Une
    chute de nb_avant par rapport au nb_apres de la ligne précédente, pour le
    même fichier, permet de dater l'incident — `operation` distingue une
    chute LÉGITIME (ex. "archivage_manuel", scripts/archiver_historique.py,
    qui réduit délibérément le fichier) d'une chute inexpliquée. Best-effort
    strict : ne doit jamais faire échouer l'écriture qu'elle journalise."""
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        ligne = {
            "date": date_iso,
            "fichier": fichier,
            "operation": operation,
            "nb_avant": nb_avant,
            "nb_apres": nb_apres,
            "taille_avant_octets": taille_avant_octets,
            "taille_apres_octets": taille_apres_octets,
            "reinitialise_corruption": reinitialise_corruption,
            "pid": os.getpid(),
        }
        with open(FICHIER_JOURNAL_ECRITURES, "a", encoding="utf-8") as f:
            f.write(json.dumps(ligne, ensure_ascii=False) + "\n")
    except Exception as e:
        log.error(f"Erreur journalisation écriture ({fichier}) : {e}")


def enregistrer_duree(projet: str, type_issue: str, mode: str,
                      duree_s: float | None, date_iso: str, *,
                      body: str = "", nb_projets_actifs: int = 0,
                      expiree: bool = False):
    """Ajoute une mesure de durée réelle (ACK → fermeture, ou ACK → timeout si
    expiree=True) à l'historique commun (issue #108, étendu #220). Best-effort :
    toute erreur est journalisée sans jamais interrompre le traitement de
    l'issue. Le fichier est une liste JSON d'objets ; issue #220 étend chaque
    entrée avec des champs BRUTS (aucune tranche/catégorisation) en préparation
    d'une future calibration automatique du TIMEOUT : longueur_corps_issue,
    nb_etapes_checklist, nb_fichiers_cibles (toujours None ici — pas de
    convention fiable pour lister les fichiers cibles dans un corps libre,
    mieux vaut None qu'une extraction fragile par regex), nb_projets_actifs_au_
    lancement, expiree, et tag_reseau (omis tant qu'aucun marqueur explicite
    n'existe, cf. _detecter_tag_reseau). Journalise aussi chaque écriture dans
    FICHIER_JOURNAL_ECRITURES (issue #521, cf. _journaliser_ecriture)."""
    try:
        DOSSIER_LOGS.mkdir(parents=True, exist_ok=True)
        historique = []
        taille_avant = FICHIER_HISTORIQUE.stat().st_size if FICHIER_HISTORIQUE.exists() else None
        fichier_corrompu = False
        if FICHIER_HISTORIQUE.exists():
            try:
                historique = json.loads(FICHIER_HISTORIQUE.read_text(encoding="utf-8")) or []
            except (json.JSONDecodeError, OSError):
                historique = []   # fichier corrompu : on repart d'une liste vide
                fichier_corrompu = True
        nb_avant = len(historique)
        entree = {
            "projet": projet,
            "type":   type_issue,
            "mode":   mode,
            "duree":  round(duree_s) if duree_s is not None else None,   # secondes
            "date":   date_iso,
            "longueur_corps_issue": len(body or ""),
            "nb_etapes_checklist": _compter_etapes_checklist(body),
            "nb_fichiers_cibles": None,
            "nb_projets_actifs_au_lancement": nb_projets_actifs,
            "expiree": expiree,
            "k_utilise": K_VARIABILITE,
        }
        tag_reseau = _detecter_tag_reseau(body)
        if tag_reseau is not None:
            entree["tag_reseau"] = tag_reseau
        historique.append(entree)
        FICHIER_HISTORIQUE.write_text(
            json.dumps(historique, ensure_ascii=False, indent=2), encoding="utf-8")
        _journaliser_ecriture(
            FICHIER_HISTORIQUE.name, date_iso, operation="cloture_issue",
            nb_avant=nb_avant, nb_apres=len(historique),
            taille_avant_octets=taille_avant,
            taille_apres_octets=FICHIER_HISTORIQUE.stat().st_size,
            reinitialise_corruption=fichier_corrompu,
        )
    except Exception as e:
        log.error(f"Erreur enregistrement historique durée : {e}")


# ─── Calibration automatique du TIMEOUT — mécanique EWMA (issue #221) ──────────
# Fichiers d'état partagés par tous les process watcher (voir constantes en tête
# de fichier). Deux garde-fous communs :
#   - lecture/écriture protégées par un verrou fichier court + écriture atomique
#     (tempfile + os.replace) : plusieurs watchers de projets différents peuvent
#     clore une issue quasi simultanément, AUCUN écrasement concurrent ne doit
#     corrompre l'état ;
#   - best-effort intégral : toute erreur est journalisée sans jamais faire
#     échouer le traitement de l'issue (même contrat que enregistrer_duree).

VERROU_ETAT_PEREMPTION = 30  # secondes — la section critique (lecture JSON + calcul + écriture) dure quelques ms ; au-delà, verrou orphelin (process tué)


def _verrou_etat(chemin_etat: Path) -> Path:
    return chemin_etat.with_name(chemin_etat.name + ".lock")


def _acquerir_verrou_etat(chemin_etat: Path, essais: int = 50, attente_s: float = 0.1) -> bool:
    """Verrou court par création atomique O_CREAT|O_EXCL (portable, même
    mécanisme que acquerir_verrou pour les répertoires de travail — mais durée
    de rétention bien plus courte, cf. VERROU_ETAT_PEREMPTION). Attente active
    bornée (5s max par défaut) : la section critique est toujours brève, pas de
    raison de faire attendre le cycle du watcher longtemps."""
    verrou = _verrou_etat(chemin_etat)
    for _ in range(essais):
        try:
            chemin_etat.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(verrou), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return True
        except FileExistsError:
            try:
                age = time.time() - verrou.stat().st_mtime
            except OSError:
                age = None
            if age is not None and age > VERROU_ETAT_PEREMPTION:
                try:
                    verrou.unlink()
                except OSError:
                    pass
                continue
            time.sleep(attente_s)
        except OSError as e:
            log.warning(f"Verrou d'état {verrou} inobtenable ({e}).")
            return False
    return False


def _liberer_verrou_etat(chemin_etat: Path):
    try:
        _verrou_etat(chemin_etat).unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"Libération du verrou d'état {chemin_etat} impossible ({e}).")


def _lire_json_best_effort(chemin: Path) -> dict:
    if not chemin.exists():
        return {}
    try:
        return json.loads(chemin.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}   # fichier absent/corrompu : on repart d'un état vide


def _maj_etat_json(chemin: Path, fonction_maj, *, date_iso: str | None = None):
    """Lecture-modification-écriture protégée d'un fichier d'état JSON partagé.
    `fonction_maj(donnees)` reçoit le dict courant (vide si absent/corrompu) et
    le modifie en place ; sa valeur de retour, si non None, remplace `donnees`
    avant l'écriture atomique. Verrou non obtenu ou exception : la mise à jour
    est abandonnée pour ce cycle (journalisée), jamais propagée à l'appelant.
    Si `date_iso` est fourni, journalise aussi cette écriture (issue #521, cf.
    _journaliser_ecriture) : nombre d'entrées de premier niveau (ou de
    `donnees["combinaisons"]` s'il existe, cas d'etat_timeout.json) et taille
    en octets, avant/après — même logique de traçabilité que pour
    historique_durees.json, pour repérer une chute anormale au moment où elle
    se produit."""
    if not _acquerir_verrou_etat(chemin):
        log.warning(f"Verrou d'état {chemin.name} non obtenu — mise à jour ignorée pour ce cycle.")
        return
    try:
        taille_avant = chemin.stat().st_size if chemin.exists() else None
        corrompu = False
        if chemin.exists():
            try:
                json.loads(chemin.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                corrompu = True
        donnees = _lire_json_best_effort(chemin)
        nb_avant = len(donnees.get("combinaisons", donnees))
        resultat = fonction_maj(donnees)
        donnees_finales = resultat if resultat is not None else donnees
        _ecrire_json_atomique(chemin, donnees_finales)
        if date_iso is not None:
            nb_apres = len(donnees_finales.get("combinaisons", donnees_finales))
            _journaliser_ecriture(
                chemin.name, date_iso, operation="calibration_timeout",
                nb_avant=nb_avant, nb_apres=nb_apres,
                taille_avant_octets=taille_avant,
                taille_apres_octets=chemin.stat().st_size,
                reinitialise_corruption=corrompu,
            )
    except Exception as e:
        log.error(f"Erreur mise à jour état {chemin.name} : {e}")
    finally:
        _liberer_verrou_etat(chemin)


def _ewma_maj(valeur_precedente: float | None, nouvelle_valeur: float, alpha: float) -> float:
    """EWMA classique à alpha fixe (mise à jour PAR ISSUE, pas temporelle).
    Sans valeur précédente, la série démarre à la première observation."""
    if valeur_precedente is None:
        return nouvelle_valeur
    return alpha * nouvelle_valeur + (1 - alpha) * valeur_precedente


def _alpha_temporel(delta_heures: float, demi_vie_heures: float) -> float:
    """Poids de la nouvelle observation pour une EWMA à demi-vie TEMPORELLE
    (issue #221, F_reseau/F_local) : plus l'écart depuis la dernière mise à
    jour est grand, plus l'ancienne valeur est oubliée. delta_heures <= 0
    (observations quasi simultanées, ou horloge en recul) : traité comme une
    observation fraîche (alpha = 1), plutôt que de produire un poids négatif
    ou nul incohérent."""
    if delta_heures <= 0:
        return 1.0
    return 1 - 0.5 ** (delta_heures / demi_vie_heures)


def _cle_combinaison(projet: str, type_issue: str, mode: str, complexite: str) -> str:
    return f"{projet}|{type_issue}|{mode}|{complexite}"


def _timeout_suggere_borne(duree_typique: float, variabilite: float,
                           f_pertinent: float, backoff: float) -> float:
    """Calcule TIMEOUT_suggéré (formule §19.2 du DOC) et le borne entre
    TIMEOUT_SUGGERE_PLANCHER et TIMEOUT_SUGGERE_PLAFOND — ce dernier (issue
    #590) protège contre tout emballement futur du backoff, même après le
    correctif d'ancrage de SEUIL_SUCCES_RAPIDE sur duree_typique."""
    brut = (duree_typique + K_VARIABILITE * variabilite) * f_pertinent * backoff
    return min(max(brut, TIMEOUT_SUGGERE_PLANCHER), TIMEOUT_SUGGERE_PLAFOND)


def _maj_combinaison_timeout(donnees: dict, cle: str, *, duree_s: float,
                              expiree: bool, relance: bool = False) -> tuple[float | None, dict]:
    """Met à jour, DANS `donnees` (le dict complet d'etat_timeout.json), l'entrée
    de la combinaison `cle`. Retourne (duree_typique_AVANT_maj, etat_APRES_maj).

    Sur timeout (expiree=True) : multiplicateur_backoff *= FACTEUR_BACKOFF
    immédiatement, compteur de succès rapides consécutifs remis à zéro. AUCUNE
    mise à jour de duree_typique/variabilite (ces EWMA ne portent que sur les
    issues RÉUSSIES, cf. §1 de l'issue #221 — un timeout ne mesure pas une
    durée réelle de traitement, seulement le plafond atteint).

    Sur succès d'une RELANCE (expiree=False, relance=True, issue #592) : durée
    traitée comme CENSURÉE, même principe que le timeout ci-dessus — le
    worktree d'une RELANCE (champ RELANCE, #516) peut contenir du travail déjà
    fait par la tentative précédente, la durée mesurée (nouvelle ACK →
    clôture) serait alors artificiellement courte et biaiserait duree_typique/
    variabilite vers le bas. AUCUNE mise à jour de duree_typique/variabilite/
    succès rapides/backoff ; seul n_relances_exclues est incrémenté (traçabilité).

    Sur succès normal (expiree=False, relance=False) : variabilite d'abord (écart absolu à
    duree_typique AVANT cette observation, sinon la mise à jour de
    duree_typique fausserait l'écart mesuré), puis duree_typique. Si la durée
    réelle est < SEUIL_SUCCES_RAPIDE × (duree_typique + K_VARIABILITE×variabilite)
    — le repère historique de LA COMBINAISON elle-même, PAS le TIMEOUT courant
    de cette exécution (issue #590 : ce dernier inclut le backoff courant: un
    backoff déjà emballé rendrait la barre inatteignable et le système ne
    pourrait plus jamais en sortir seul) — incrémente le compteur de succès
    rapides consécutifs ; au bout de SUCCES_RAPIDES_POUR_RESET, réinitialise le
    backoff à 1.0. Un succès non « rapide » remet le compteur à zéro sans
    toucher au backoff lui-même."""
    combinaisons = donnees.setdefault("combinaisons", {})
    etat = combinaisons.setdefault(cle, {
        "duree_typique": None,
        "variabilite": None,
        "multiplicateur_backoff": 1.0,
        "succes_rapides_consecutifs": 0,
        "n_observations": 0,
    })

    duree_typique_avant = etat.get("duree_typique")

    if expiree:
        etat["multiplicateur_backoff"] = etat.get("multiplicateur_backoff", 1.0) * FACTEUR_BACKOFF
        etat["succes_rapides_consecutifs"] = 0
    elif relance:
        etat["n_relances_exclues"] = etat.get("n_relances_exclues", 0) + 1
    else:
        ecart = abs(duree_s - duree_typique_avant) if duree_typique_avant is not None else 0.0
        etat["variabilite"] = _ewma_maj(etat.get("variabilite"), ecart, ALPHA_EWMA_ISSUES)
        etat["duree_typique"] = _ewma_maj(duree_typique_avant, duree_s, ALPHA_EWMA_ISSUES)
        etat["n_observations"] = etat.get("n_observations", 0) + 1

        repere_rapide = etat["duree_typique"] + K_VARIABILITE * (etat.get("variabilite") or 0.0)
        if duree_s < SEUIL_SUCCES_RAPIDE * repere_rapide:
            etat["succes_rapides_consecutifs"] = etat.get("succes_rapides_consecutifs", 0) + 1
            if etat["succes_rapides_consecutifs"] >= SUCCES_RAPIDES_POUR_RESET:
                etat["multiplicateur_backoff"] = 1.0
                etat["succes_rapides_consecutifs"] = 0
        else:
            etat["succes_rapides_consecutifs"] = 0

    return duree_typique_avant, etat


def _maj_ambiance(donnees: dict, cle_f: str, ratio: float, date_iso: str):
    """Met à jour (dans `donnees`, le dict complet d'etat_ambiance.json) l'EWMA
    à demi-vie temporelle de `cle_f` ('F_reseau' ou 'F_local') avec la nouvelle
    observation `ratio`. Sans horodatage précédent exploitable, la série
    démarre à `ratio` (alpha effectif = 1)."""
    bloc = donnees.setdefault(cle_f, {"valeur_ewma": None, "derniere_maj": None})
    delta_h = None
    if bloc.get("valeur_ewma") is not None and bloc.get("derniere_maj"):
        try:
            avant = datetime.fromisoformat(bloc["derniere_maj"])
            maintenant = datetime.fromisoformat(date_iso)
            delta_h = (maintenant - avant).total_seconds() / 3600
        except (ValueError, TypeError):
            delta_h = None
    if delta_h is None:
        bloc["valeur_ewma"] = ratio
    else:
        alpha = _alpha_temporel(delta_h, DEMI_VIE_AMBIANCE_HEURES)
        bloc["valeur_ewma"] = alpha * ratio + (1 - alpha) * bloc["valeur_ewma"]
    bloc["derniere_maj"] = date_iso


def maj_calibration_timeout(*, projet: str, type_issue: str, mode: str,
                            duree_s: float, expiree: bool,
                            body: str, date_iso: str, complexite: str = "normal",
                            relance: bool = False) -> float | None:
    """Point d'entrée de la calibration automatique du TIMEOUT (issue #221),
    appelé après CHAQUE clôture d'issue (succès ou timeout), au même site que
    enregistrer_duree. Met à jour etat_timeout.json (combinaison projet/TYPE/
    mode/complexite, issue #434) et, sur succès avec tag_reseau connu,
    etat_ambiance.json (F_reseau/F_local, global à tous les projets).
    Journalise et retourne le TIMEOUT_suggéré (secondes, plancher/plafond
    appliqués) pour cette combinaison, ou None si le calcul n'a pas pu aboutir (verrou
    d'état non obtenu, ou aucune observation de succès encore enregistrée
    pour cette combinaison).

    `relance` (issue #592) : True quand l'appelant a détecté un commentaire
    d'échec (`_issue_est_relance`) antérieur à l'ACK courante — la durée n'est
    alors pas une mesure fiable (voir `_maj_combinaison_timeout`) et est
    exclue à la fois de duree_typique/variabilite ET de F_reseau/F_local
    ci-dessous (même biais : durée artificiellement courte).

    N'APPLIQUE RIEN au comportement d'exécution actuel : le TIMEOUT réellement
    utilisé pour lancer claude reste exclusivement celui de extraire_timeout()
    — cette fonction ne fait que calculer et journaliser."""
    cle = _cle_combinaison(projet, type_issue, mode, complexite)
    capture = {}

    def _maj_timeout(donnees):
        duree_typique_avant, etat = _maj_combinaison_timeout(
            donnees, cle, duree_s=duree_s, expiree=expiree, relance=relance)
        capture["duree_typique_avant"] = duree_typique_avant
        capture["etat"] = dict(etat)
        return donnees

    _maj_etat_json(FICHIER_ETAT_TIMEOUT, _maj_timeout, date_iso=date_iso)

    etat = capture.get("etat")
    if etat is None:
        log.warning(f"Calibration TIMEOUT [{cle}] : état inobtenable ce cycle — TIMEOUT_suggéré non calculé.")
        return None

    # F n'est alimenté QUE par les succès (comme duree_typique, §1 de l'issue) :
    # un timeout est plafonné à la valeur configurée, pas une mesure de la durée
    # réelle nécessaire — l'inclure biaiserait F vers le haut artificiellement.
    # Et seulement si tag_reseau est explicitement connu (jamais deviné, §2).
    # Une RELANCE (#592) est exclue au même titre — durée elle aussi biaisée.
    tag_reseau = _detecter_tag_reseau(body)
    duree_typique_avant = capture.get("duree_typique_avant")
    if not expiree and not relance and tag_reseau is not None and duree_typique_avant:
        ratio = duree_s / duree_typique_avant
        cle_f = "F_reseau" if tag_reseau else "F_local"

        def _maj_f(donnees, cle_f=cle_f, ratio=ratio):
            _maj_ambiance(donnees, cle_f, ratio, date_iso)
            return donnees

        _maj_etat_json(FICHIER_ETAT_AMBIANCE, _maj_f)

    duree_typique = etat.get("duree_typique")
    if duree_typique is None:
        log.info(f"Calibration TIMEOUT [{cle}] : aucun succès encore enregistré — TIMEOUT_suggéré non calculable.")
        return None

    # F_pertinent pour la SUGGESTION : F_reseau si CETTE issue est taguée réseau,
    # F_local sinon (par défaut en l'absence de tag — hypothèse la moins
    # généreuse). Lecture indépendante de la mise à jour ci-dessus : même une
    # observation qui n'a pas pu alimenter F (tag inconnu) doit pouvoir lire le
    # F déjà établi par d'autres observations.
    ambiance = _lire_json_best_effort(FICHIER_ETAT_AMBIANCE)
    cle_f_lecture = "F_reseau" if tag_reseau else "F_local"
    f_brut = (ambiance.get(cle_f_lecture) or {}).get("valeur_ewma")
    f_pertinent = max(1.0, f_brut) if f_brut is not None else 1.0   # plancher F >= 1.0 : n'allonge jamais, ne raccourcit jamais

    variabilite = etat.get("variabilite") or 0.0
    backoff = etat.get("multiplicateur_backoff", 1.0)
    suggere = _timeout_suggere_borne(duree_typique, variabilite, f_pertinent, backoff)

    log.info(
        f"Calibration TIMEOUT [{cle}] : duree_typique={duree_typique:.1f}s "
        f"variabilite={variabilite:.1f}s F({cle_f_lecture})={f_pertinent:.3f} "
        f"backoff={backoff:.3f} → TIMEOUT_suggéré={suggere:.0f}s"
        + (" [issue expirée]" if expiree else "")
        + (" [RELANCE — durée exclue de la calibration]" if relance else "")
    )
    return suggere


def lire_timeout_suggere(projet: str, type_issue: str, mode: str, complexite: str = "normal",
                         body: str = "") -> float | None:
    """Lit (sans écrire ni verrouiller) le TIMEOUT_suggéré actuellement en
    vigueur pour la combinaison (projet, TYPE, mode, complexite — issue
    #434), à partir de l'état déjà persisté par maj_calibration_timeout
    (issue #221).

    Sert au commentaire de clôture d'une issue en ÉCHEC définitif (issue
    #222) : contrairement au cas succès, l'appel à maj_calibration_timeout
    pour CET échec a déjà eu lieu (une fois par tentative expirée, dans la
    boucle de retry) — le rappeler ici biaiserait l'EWMA en comptant deux
    fois la même observation. Une simple lecture de l'état déjà à jour suffit.
    Best-effort : retourne None si l'état est illisible ou si aucun succès n'a
    encore été enregistré pour cette combinaison (mêmes conditions que
    maj_calibration_timeout).

    body (issue #435) : corps de l'issue échouée, pour lire le tag_reseau via
    _detecter_tag_reseau — même logique que maj_calibration_timeout. Absent
    (chaîne vide) ou tag non trouvé → repli sur F_local, comme avant."""
    try:
        cle = _cle_combinaison(projet, type_issue, mode, complexite)
        combo = _lire_json_best_effort(FICHIER_ETAT_TIMEOUT).get(cle)
        if not combo:
            return None
        duree_typique = combo.get("duree_typique")
        if duree_typique is None:
            return None
        variabilite = combo.get("variabilite") or 0.0
        backoff = combo.get("multiplicateur_backoff", 1.0)

        # F_reseau si le tag RESEAU de cette issue est explicitement connu et
        # positif, F_local sinon (hypothèse la moins généreuse par défaut) —
        # même choix que maj_calibration_timeout.
        tag_reseau = _detecter_tag_reseau(body)
        cle_f = "F_reseau" if tag_reseau else "F_local"
        f_brut = (_lire_json_best_effort(FICHIER_ETAT_AMBIANCE).get(cle_f) or {}).get("valeur_ewma")
        f_pertinent = max(1.0, f_brut) if f_brut is not None else 1.0

        return _timeout_suggere_borne(duree_typique, variabilite, f_pertinent, backoff)
    except Exception as e:
        log.warning(f"Lecture TIMEOUT_suggéré [{projet}/{type_issue}/{mode}] impossible : {e}")
        return None


def formater_bloc_calibration(duree_s: float, timeout_courant: int, suggere: float | None) -> str:
    """Bloc lisible à ajouter au commentaire de clôture GitHub d'une issue
    (issue #222) : durée réelle de traitement et TIMEOUT_suggéré calculé par
    la calibration automatique (issue #221).

    Seul canal fiable pour transmettre cette information calculée localement
    à Claude Chat, qui n'a pas accès direct aux fichiers d'état du ThinkPad
    (etat_timeout.json, etat_ambiance.json, historique_durees.json — tous
    gitignorés)."""
    bloc = f"\n\n---\n⏱️ Durée réelle : {duree_s:.0f}s (TIMEOUT courant : {timeout_courant}s)"
    if suggere is not None:
        bloc += f"\n📊 TIMEOUT_suggéré (calibration automatique, issue #221) : {suggere:.0f}s"
    return bloc


def extraire_timeout(body: str, titre: str = "") -> int:
    """Extrait le TIMEOUT (en secondes) depuis le body de l'issue (en-tête bridge).
    Si absent ou mal formé, retombe sur le défaut du projet — mais un défaut plus
    généreux (CFG.timeout_chef) pour les issues « Chef : » (tâches monolithiques
    plus longues), afin d'éviter un dépassement du seul cycle standard (issue #106).

    Filet de sécurité (issue #111) : pour une tâche « Chef : », on applique
    max(valeur_trouvée, CFG.timeout_chef) au lieu de la première valeur telle
    quelle. L'interface place son tableau d'en-tête (TIMEOUT du formulaire, souvent
    le défaut 300s) AVANT le corps collé ; comme on retient la PREMIÈRE occurrence,
    ce défaut pouvait écraser un « | TIMEOUT | 1200s | » collé plus bas et faire
    échouer une tâche Chef sur un dépassement (cause de #108). Le plancher garantit
    qu'une tâche Chef ne tourne jamais sous son budget dédié, même si une valeur
    plus basse est trouvée en premier."""
    chef = est_titre_chef(titre)
    for ligne in body.splitlines():
        if "TIMEOUT" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip().lower().rstrip("s")
                if valeur.isdigit():
                    trouve = int(valeur)
                    return max(trouve, CFG.timeout_chef) if chef else trouve
    if chef:
        return CFG.timeout_chef
    return CFG.timeout_claude

def extraire_modele(body: str) -> str:
    """Extrait le MODELE depuis le body de l'issue (en-tête bridge).
    Retombe sur CFG.modele_ccl (lui-même vide = défaut Claude Code) si absent."""
    for ligne in body.splitlines():
        if "| MODELE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip()
                if valeur and valeur.lower() not in ("", "-", "défaut", "defaut"):
                    return valeur
    return CFG.modele_ccl

def extraire_complexite(body: str) -> str:
    """Extrait la COMPLEXITE depuis le body de l'issue (en-tête bridge, issue
    #434) — 4e dimension de la clé EWMA de calibration TIMEOUT, aux côtés de
    projet/TYPE/mode : sépare les populations « issue de doc de 250s » et
    « refonte de 1800s » que la clé à 3 dimensions mélangeait.

    Calquée sur extraire_timeout/extraire_modele. Quatre niveaux reconnus
    (insensible à la casse) : rapide / court / normal / lourd. Champ absent
    ou valeur non reconnue → 'normal' (défaut, ~300s = TIMEOUT standard) —
    n'affecte pas l'historique des issues déjà closes, qui n'ont pas ce
    champ (nouvelles clés, recalibration progressive)."""
    niveaux = ("rapide", "court", "normal", "lourd")
    for ligne in body.splitlines():
        if "| COMPLEXITE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip().lower()
                if valeur in niveaux:
                    return valeur
    return "normal"

def extraire_repo_cible(body: str) -> str:
    """Extrait le REPO_CIBLE depuis le body de l'issue (en-tête bridge).
    Calqué sur extraire_timeout/extraire_modele : cherche une ligne
    « | REPO_CIBLE | <chemin absolu> | » et retourne le chemin tel quel (str),
    ou "" si le champ est absent ou vide.

    Ne concerne que les projets à périmètre dynamique (issue #125) : le chemin
    renvoyé sert de périmètre effectif ET de cwd pour cette exécution, après
    validation par valider_repo_cible()."""
    for ligne in body.splitlines():
        if "| REPO_CIBLE" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip()
                if valeur and valeur.lower() not in ("", "-"):
                    return valeur
    return ""

def valider_repo_cible(chemin: str) -> tuple[bool, str]:
    """Valide un REPO_CIBLE avant tout lancement de CCL (issue #125).

    Vérifie, dans cet ordre :
      1. le chemin est absolu et ne contient aucune séquence de traversée '..'
         (Path.resolve() puis comparaison stricte au chemin fourni : toute
         normalisation — '..' ou lien symbolique — le fait diverger et donc
         refuser) ;
      2. le chemin existe et est un dossier ;
      3. le dossier appartient au même utilisateur système que le process
         watcher (st_uid == os.getuid()).

    Retourne (True, "") si tout passe, sinon (False, raison explicite). L'échec
    d'une seule vérification suffit à refuser — c'est une erreur de
    configuration/issue, pas un échec transitoire : aucun retry côté appelant."""
    if not chemin:
        return False, "chemin vide"
    p = Path(chemin)
    if not p.is_absolute():
        return False, "le chemin doit être absolu"
    resolu = p.resolve()
    if resolu != p:
        return False, ("le chemin contient une séquence de traversée '..' ou n'est "
                       "pas canonique (lien symbolique) — fournir un chemin absolu direct")
    if not resolu.is_dir():
        return False, "le chemin n'existe pas ou n'est pas un dossier"
    try:
        proprietaire = resolu.stat().st_uid
    except OSError as e:
        return False, f"impossible de lire les métadonnées du dossier ({e})"
    if proprietaire != os.getuid():
        return False, (f"le dossier n'appartient pas à l'utilisateur du watcher "
                       f"(uid propriétaire {proprietaire} ≠ uid watcher {os.getuid()})")
    return True, ""

def extraire_sous_dossier(body: str) -> str:
    """Extrait le SOUS_DOSSIER depuis le body de l'issue (en-tête bridge, issue
    #550). Calqué sur extraire_repo_cible/extraire_timeout : cherche une ligne
    « | SOUS_DOSSIER | <chemin relatif> | » et retourne le chemin tel quel
    (str), ou "" si le champ est absent ou vide.

    Distinct de REPO_CIBLE (#125, chemin ABSOLU, réservé aux projets
    PERIMETRE_DYNAMIQUE) : SOUS_DOSSIER est un chemin RELATIF, résolu sous
    CFG.rep_travail par valider_sous_dossier(), utilisable sur N'IMPORTE QUEL
    projet sans réglage préalable dans le .conf. Pensé pour le canal unifié
    for-windows (REP_TRAVAIL = dossier PARENT partagé, ex. C:\\CCW_Share,
    contenant plusieurs sous-projets dans CCW\\<projet>\\) — voir le
    commentaire de valider_sous_dossier pour la cause racine que ce champ
    corrige."""
    for ligne in body.splitlines():
        if "| SOUS_DOSSIER" in ligne.upper():
            parts = ligne.split("|")
            if len(parts) >= 3:
                valeur = parts[2].strip()
                if valeur and valeur.lower() not in ("", "-"):
                    return valeur
    return ""

def valider_sous_dossier(rep_travail: Path, sous_dossier: str) -> tuple[bool, str, Path]:
    """Valide un SOUS_DOSSIER avant tout lancement de Claude Code (issue #550).

    Contexte : sur le canal unifié for-windows (service NSSM `CCW-Watcher` de
    base, REP_TRAVAIL = C:\\CCW_Share), le process `claude` démarrait
    jusqu'ici TOUJOURS avec pour cwd REP_TRAVAIL tout entier, même quand
    l'issue ne visait qu'un sous-projet précis (ex. `C:\\CCW_Share\\CCW\\
    gestionmail\\`) — confirmé empiriquement (reproduction locale Linux,
    issue #550) : quand le cwd réel du process diverge du dossier où une
    commande git opère effectivement (atteint via `git -C <chemin>` ou
    `cd <chemin> &&`), Claude Code bloque la commande par une demande
    d'approbation interactive, MÊME si son préfixe correspond exactement à
    une entrée de OUTILS_LECTURE_AUTORISES — `--allowedTools` ne pilote pas
    ce garde-fou-là. `git pull --ff-only` bare (sans -C ni cd), lancé avec un
    cwd déjà positionné sur le bon dossier, n'est en revanche PAS bloqué.
    SOUS_DOSSIER permet de démarrer directement claude avec le bon cwd,
    plutôt que de compter sur l'agent pour naviguer lui-même en cours de
    tâche (ce que la commande git elle-même ne peut pas faire de façon fiable
    sans -C/cd, précisément ce qui déclenche le blocage).

    Vérifie, dans cet ordre :
      1. `sous_dossier` n'est pas un chemin absolu (ni racine POSIX '/...' ni
         lecteur Windows 'C:\\...') — un chemin absolu n'a pas sa place ici,
         c'est REPO_CIBLE (#125) qu'il faut utiliser dans ce cas ;
      2. une fois joint à `rep_travail` et résolu, le résultat reste bien
         SOUS `rep_travail` (Path.relative_to — une séquence '..' ou un lien
         symbolique qui en sortirait est refusé) ;
      3. le chemin résolu existe et est un dossier.

    Retourne (True, "", chemin_résolu) si tout passe, sinon (False, raison
    explicite, Path()) — même logique de refus définitif (pas de retry) que
    valider_repo_cible. Pas de vérification st_uid ici (indisponible sous
    Windows, contrairement à valider_repo_cible) : le chemin reste confiné
    sous rep_travail, qui appartient déjà à l'utilisateur du watcher."""
    if not sous_dossier:
        return False, "chemin vide", Path()
    p = Path(sous_dossier)
    if p.is_absolute():
        return False, ("le chemin doit être RELATIF à REP_TRAVAIL — utiliser REPO_CIBLE "
                       "(projet à PERIMETRE_DYNAMIQUE) pour un chemin absolu"), Path()
    rep_travail_resolu = rep_travail.resolve()
    resolu = (rep_travail_resolu / p).resolve()
    try:
        resolu.relative_to(rep_travail_resolu)
    except ValueError:
        return False, ("le chemin sort de REP_TRAVAIL une fois résolu (séquence '..' ou "
                       "lien symbolique) — fournir un sous-dossier direct"), Path()
    if not resolu.is_dir():
        return False, f"'{resolu}' n'existe pas ou n'est pas un dossier", Path()
    return True, "", resolu

# ─── Bootstrap automatique d'un service CCW dédié (issue #556, 2/3) ────────────
# Champ d'en-tête optionnel CREATION : déclenche, en Python déterministe et
# SANS jamais invoquer `claude` (décision #554 §2.5), la création complète
# d'un service CCW dédié pour un nouveau projet. Convention détaillée dans
# BRIDGE_AGENT_DOC.md §16 (pour le formulaire web à venir, 3/3, #559+) :
#   | CREATION | oui |                — déclencheur (toute autre valeur/absence ignore ce champ)
#   | CREATION_NOM_PROJET | <nom> |   — passé tel quel à ajouter_projet_ccw.ps1 -NomProjet
#   | CREATION_DEPOT | owner/repo |   — passé tel quel à ajouter_projet_ccw.ps1 -Depot
#   | CREATION_TOPIC_NTFY | <topic> | — passé tel quel dans le fichier de valeurs (TOPIC_NTFY=)
#   | CREATION_GH_TOKEN | <base64> |        — token GH_TOKEN chiffré (voir dechiffrer_token_bootstrap)
#   | CREATION_OAUTH_TOKEN | <base64> |     — token CLAUDE_CODE_OAUTH_TOKEN chiffré (idem)
CHAMPS_CREATION = (
    "CREATION_NOM_PROJET",
    "CREATION_DEPOT",
    "CREATION_TOPIC_NTFY",
    "CREATION_GH_TOKEN",
    "CREATION_OAUTH_TOKEN",
)

def _extraire_champ_entete(body: str, nom_champ: str) -> str:
    """Extrait la valeur d'un champ `| NOM_CHAMP | valeur |` de l'en-tête
    bridge (issue #556). Comparaison EXACTE (pas une sous-chaîne comme
    extraire_sous_dossier/extraire_repo_cible) sur le premier segment trimé
    et mis en majuscules : nécessaire ici parce que CREATION est le préfixe
    littéral de CREATION_NOM_PROJET/CREATION_DEPOT/…, une simple recherche
    de sous-chaîne `"| CREATION" in ligne.upper()` matcherait ces AUTRES
    champs par erreur (ex. sur la ligne CREATION_NOM_PROJET). Retourne "" si
    le champ est absent ou vide."""
    for ligne in body.splitlines():
        parts = ligne.split("|")
        if len(parts) >= 3 and parts[1].strip().upper() == nom_champ:
            valeur = parts[2].strip()
            if valeur and valeur.lower() not in ("", "-"):
                return valeur
    return ""

def creation_demandee(body: str) -> bool:
    """Indique si l'issue porte `| CREATION | oui |` (issue #556) — déclencheur
    du bootstrap automatique d'un service CCW dédié, détecté tôt dans le
    dispatch, AVANT tout lancement de claude. Valeurs actives reconnues :
    oui/true/vrai (insensible à la casse). Absent ou toute autre valeur :
    dispatch normal inchangé (lancement de claude comme avant #556)."""
    return _extraire_champ_entete(body, "CREATION").strip().lower() in ("oui", "true", "vrai")

def extraire_champs_creation(body: str) -> dict[str, str]:
    """Extrait les 5 champs CREATION_* du corps de l'issue (issue #556).
    Chaque valeur manquante reste "" — la validation (champs requis tous
    présents) est faite par l'appelant, pas ici."""
    return {champ: _extraire_champ_entete(body, champ) for champ in CHAMPS_CREATION}

def _corps_avec_tokens_retires(body: str) -> str:
    """Retourne `body` avec les valeurs de CREATION_GH_TOKEN/CREATION_OAUTH_TOKEN
    remplacées par un placeholder (issue #556, §2.4 de #554) — limite le temps
    d'exposition résiduel des tokens chiffrés sur GitHub. Sans effet sur le
    reste du corps. Appelée dès que les valeurs sont extraites en mémoire :
    la suite du traitement ne relit plus jamais le corps de l'issue."""
    placeholder = "<retiré après application>"
    lignes = body.splitlines(keepends=True)
    for i, ligne in enumerate(lignes):
        parts = ligne.split("|")
        if len(parts) >= 3 and parts[1].strip().upper() in ("CREATION_GH_TOKEN", "CREATION_OAUTH_TOKEN"):
            parts[2] = f" {placeholder} "
            lignes[i] = "|".join(parts)
    return "".join(lignes)

def _editer_corps_issue(numero: int, nouveau_corps: str) -> bool:
    """Remplace le corps d'une issue (`gh issue edit --body-file`, même
    protection --body-file que commenter_issue contre la limite argv Windows,
    issue #237). Réservé au retrait des tokens chiffrés (issue #556, §2.4)."""
    fichier_tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False,
                encoding="utf-8") as f:
            f.write(nouveau_corps)
            fichier_tmp = f.name
        res = subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--body-file", fichier_tmp],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur édition du corps de l'issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return False
        return True
    except Exception as e:
        log.error(f"Erreur édition du corps de l'issue #{numero} : {e}")
        return False
    finally:
        if fichier_tmp:
            try:
                Path(fichier_tmp).unlink(missing_ok=True)
            except OSError:
                pass

def _resoudre_openssl() -> str:
    """Résout le chemin de l'exécutable openssl (issue #556), robuste au
    point d'attention découvert en #557 : sur CCW, openssl n'est disponible
    qu'après une installation manuelle séparée
    (C:\\Program Files\\OpenSSL-Win64\\bin\\openssl.exe — CHEMIN_OPENSSL_WIN64),
    PAS sur le PATH par défaut. Distinct de l'openssl embarqué par Git pour
    Windows (usr\\bin) qu'utilise provisionner.ps1 pour la GÉNÉRATION de la
    paire de clés (Resoudre-OpenSSL côté PowerShell, issue #554) — dupliqué
    ici plutôt que réutilisé : pas de dot-sourcing PowerShell depuis Python,
    et cette fonction n'a besoin que d'un CHEMIN, pas d'exécuter du PowerShell.

    Ordre de résolution :
      1. `openssl` sur le PATH (shutil.which — couvre Linux/CCL, où openssl
         est quasi toujours présent, et un CCW où l'installeur l'aurait
         ajouté au PATH) ;
      2. l'installation manuelle documentée (#557) ;
      3. le sous-dossier usr\\bin de Git pour Windows, en repli ultime (même
         binaire que celui utilisé à la génération des clés).

    Lève RuntimeError si aucune des trois ne mène à un fichier présent —
    erreur de configuration machine, traitée par l'appelant comme définitive
    (needs-human, aucun retry), jamais comme un échec transitoire."""
    depuis_path = shutil.which("openssl")
    if depuis_path:
        return depuis_path

    candidats = [CHEMIN_OPENSSL_WIN64]
    git_exe = shutil.which("git")
    if git_exe:
        # <GitRoot>\{bin,cmd}\git.exe → deux parents → <GitRoot> → usr\bin
        # (sibling de mingw64/bin/cmd dans une installation Git pour Windows
        # standard), PAS un sous-dossier de mingw64.
        racine_git = Path(git_exe).resolve().parent.parent
        candidats.append(racine_git / "usr" / "bin" / "openssl.exe")

    for candidat in candidats:
        if candidat.is_file():
            return str(candidat)

    raise RuntimeError(
        "openssl introuvable (ni sur le PATH, ni dans l'installation manuelle "
        f"{CHEMIN_OPENSSL_WIN64}, ni dans le usr\\bin de Git) — impossible de "
        "déchiffrer les tokens de bootstrap (issue #556)."
    )

def dechiffrer_token_bootstrap(valeur_base64: str, chemin_cle_privee: Path) -> str:
    """Déchiffre un token de bootstrap encodé en base64 (issue #556).

    Convention (documentée en détail dans BRIDGE_AGENT_DOC.md §16, à
    l'intention du formulaire à venir en 3/3) : le token en clair (UTF-8) est
    chiffré côté formulaire avec la clé PUBLIQUE de bootstrap via
    `openssl pkeyutl -encrypt -pubin -inkey bootstrap_publique.pem
     -pkeyopt rsa_padding_mode:oaep -pkeyopt rsa_oaep_md:sha256`, puis le
    résultat binaire est encodé en base64 SANS retour à la ligne (`base64
    -w0` ou équivalent) pour tenir dans une cellule de tableau markdown.
    Cette fonction inverse exactement cette chaîne : décodage base64 →
    `openssl pkeyutl -decrypt` avec le MÊME padding OAEP/SHA-256 (impératif —
    un mauvais padding fait ÉCHOUER le déchiffrement plutôt que de réussir
    silencieusement avec un résultat corrompu, propriété du padding OAEP) et
    la clé PRIVÉE locale.

    Lève ValueError (base64 invalide) ou RuntimeError (openssl absent ou en
    échec) — toutes deux traitées par l'appelant comme une erreur de
    configuration/issue définitive (needs-human, aucun retry)."""
    try:
        chiffre = base64.b64decode(valeur_base64, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError(f"base64 invalide : {e}") from e

    openssl = _resoudre_openssl()
    fichier_tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="wb", suffix=".bin", delete=False) as f:
            f.write(chiffre)
            fichier_tmp = f.name
        res = subprocess.run(
            [openssl, "pkeyutl", "-decrypt",
             "-inkey", str(chemin_cle_privee),
             "-pkeyopt", "rsa_padding_mode:oaep",
             "-pkeyopt", "rsa_oaep_md:sha256",
             "-in", fichier_tmp],
            capture_output=True, timeout=30
        )
        if res.returncode != 0:
            raise RuntimeError(
                f"openssl pkeyutl -decrypt a échoué (code {res.returncode}) : "
                f"{res.stderr.decode('utf-8', errors='replace').strip()}"
            )
        return res.stdout.decode("utf-8").strip()
    finally:
        if fichier_tmp:
            try:
                Path(fichier_tmp).unlink(missing_ok=True)
            except OSError:
                pass

def _ecrire_fichier_valeurs_creation(topic: str, gh_token: str, oauth_token: str) -> Path:
    """Écrit le fichier temporaire « clé=valeur » consommé par
    `finaliser_projet_ccw_auto.ps1 -FichierValeurs` (issue #556) — MÊME
    format, vérifié par lecture du script avant d'écrire ce code, que celui
    déjà produit par `app/ccw.py` (`ccw_finaliser_projet`) : trois lignes
    `TOPIC_NTFY=`/`GH_TOKEN=`/`CLAUDE_CODE_OAUTH_TOKEN=`, UTF-8, AUCUN espace
    autour du `=` (`Lire-ValeurFichier` côté PowerShell ne rogne que la CLÉ,
    pas la valeur — un espace après `=` finirait dans le token). Permissions
    restreintes en best-effort (0600 ; sans effet réel sous NTFS/Windows,
    seulement sous POSIX — CCW reste protégé par les ACL du dossier temp
    utilisateur). Suppression laissée à l'appelant (finally, comme ccw.py)."""
    fd, chemin = tempfile.mkstemp(prefix="ccw-creation-vals-", suffix=".txt")
    try:
        os.chmod(chemin, 0o600)
    except OSError:
        pass
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(f"TOPIC_NTFY={topic}\n")
        f.write(f"GH_TOKEN={gh_token}\n")
        f.write(f"CLAUDE_CODE_OAUTH_TOKEN={oauth_token}\n")
    return Path(chemin)

def _traiter_creation_projet_ccw(numero: int, body: str, labels: list[str], dry_run: bool) -> None:
    """Bootstrap automatique d'un service CCW dédié (issue #556, 2/3),
    déclenché par `| CREATION | oui |`. ENTIÈREMENT déterministe — n'invoque
    JAMAIS `claude` (décision #554 §2.5) : appelle directement les 2 scripts
    PowerShell déjà testés, EXACTEMENT comme le fait déjà l'onglet CCW de
    l'interface web (`app/ccw.py`, `ccw_ajouter_projet`/`ccw_finaliser_projet`)
    — à la différence près que watcher.py tourne DÉJÀ sur la machine CCW
    cible (appel PowerShell local, pas de couche SSH).

    Prend en charge la TOTALITÉ du cycle de vie de cette issue — pas d'ACK
    séparé (traitement synchrone, une seule tentative, contrairement au
    pipeline lancer_claude) : extraction, retrait immédiat des tokens
    chiffrés du corps GitHub (§2.4 de #554, avant même la tentative de
    déchiffrement), déchiffrement, écriture du fichier de valeurs, appel
    séquentiel des 2 scripts PowerShell, compte-rendu, puis fermeture ou
    `needs-human` selon le résultat. Retire `numero` de `issues_en_cours`
    (appelée avec l'entrée déjà ajoutée par l'appelant) SAUF en cas d'échec
    définitif (`needs-human` posé, cf. `_echec` ci-dessous) : l'issue reste
    alors suivie tant que le label n'est pas retiré manuellement (issue
    #576, même principe que le reste du fichier)."""
    log.info(f"→ Issue #{numero} : champ CREATION détecté — bootstrap automatique d'un service CCW dédié (#556).")

    def _echec(message: str) -> None:
        log.error(f"  ✗ Issue #{numero} (CREATION) : {message}")
        commenter_issue(
            numero,
            f"❌ Bootstrap automatique du service CCW échoué : {message}\n\n"
            f"Label `{LABEL_ECHEC}` posé — corrigez puis retirez-le pour relancer."
        )
        ajouter_label(numero, LABEL_ECHEC)
        notifier(
            labels,
            titre=f"❌ {CFG.nom} #{numero} — bootstrap CCW échoué",
            message=message,
            urgence_bureau="critical",
            priorite_ntfy="high",
            numero=numero,
        )
        notifier_fin_sse(numero)
        # PAS de _issues_en_cours_retirer ici (issue #576) : `needs-human`
        # vient d'être posé — l'issue reste suivie tant que le label n'est
        # pas retiré manuellement (voir la réconciliation dans traiter_issue
        # et en tête de boucle principale). Les issues CREATION portent
        # toujours le label mode_write (seul émetteur : _creer_issue_gh dans
        # app/projet_ccw.py) — occupe donc aussi une place de
        # MAX_WRITE_PARALLELE, comme les autres échecs définitifs mode_write.
        if _deduire_mode(labels) == MODE_ECRITURE:
            _issue_write_bloquee_ajouter(numero)

    champs = extraire_champs_creation(body)
    nom_projet    = champs["CREATION_NOM_PROJET"]
    depot         = champs["CREATION_DEPOT"]
    topic_ntfy    = champs["CREATION_TOPIC_NTFY"]
    gh_chiffre    = champs["CREATION_GH_TOKEN"]
    oauth_chiffre = champs["CREATION_OAUTH_TOKEN"]

    manquants = [nom for nom, valeur in champs.items() if not valeur]
    if manquants:
        _echec(f"champ(s) manquant(s) dans le corps de l'issue : {', '.join(manquants)}.")
        return

    if dry_run:
        log.info(f"[DRY-RUN] Issue #{numero} : bootstrap CCW simulé pour le projet '{nom_projet}' (dépôt {depot}) — aucun script exécuté, aucun token déchiffré.")
        commenter_resultat_avec_retry(
            numero,
            f"{MARQUEUR_RESULTAT}\n## Résultat\n\n"
            f"[DRY-RUN] Bootstrap CCW simulé pour le projet **{nom_projet}** — aucune "
            f"action réelle (ni décryptage, ni script PowerShell exécuté)."
        )
        fermer_issue(numero)
        _issues_en_cours_retirer(numero)
        return

    # §2.4 (#554) : retrait immédiat des tokens du corps GitHub — les valeurs
    # nécessaires sont déjà en mémoire ci-dessus, la suite ne relit plus
    # jamais le corps de l'issue. Best-effort : un échec ici est journalisé
    # mais NE bloque PAS le bootstrap (l'exposition résiduelle est fâcheuse,
    # pas bloquante en soi).
    if not _editer_corps_issue(numero, _corps_avec_tokens_retires(body)):
        log.warning(f"  Issue #{numero} : retrait des tokens du corps GitHub échoué (best-effort, traitement poursuivi).")

    if platform.system() != "Windows":
        _echec("cette opération nécessite les scripts PowerShell CCW — non exécutable sur cette plateforme (agent Linux, hors périmètre CCW).")
        return

    try:
        _resoudre_openssl()
    except RuntimeError as e:
        _echec(str(e))
        return

    if not CHEMIN_CLE_PRIVEE_BOOTSTRAP.is_file():
        _echec(f"clé privée de bootstrap introuvable ({CHEMIN_CLE_PRIVEE_BOOTSTRAP}) — provisionner.ps1 a-t-il été rejoué depuis la dernière réinstallation (issue #554) ?")
        return

    try:
        gh_token    = dechiffrer_token_bootstrap(gh_chiffre, CHEMIN_CLE_PRIVEE_BOOTSTRAP)
        oauth_token = dechiffrer_token_bootstrap(oauth_chiffre, CHEMIN_CLE_PRIVEE_BOOTSTRAP)
    except (ValueError, RuntimeError) as e:
        _echec(f"déchiffrement des tokens impossible ({e}).")
        return
    if not gh_token or not oauth_token:
        _echec("un des deux tokens déchiffrés est vide — chiffrement source probablement invalide.")
        return

    script_ajouter   = DOSSIER_PROVISIONING_WINDOWS / "ajouter_projet_ccw.ps1"
    script_finaliser = DOSSIER_PROVISIONING_WINDOWS / "finaliser_projet_ccw_auto.ps1"
    script_tokens    = DOSSIER_PROVISIONING_WINDOWS / "mettre_a_jour_tokens_ccw.ps1"
    for s in (script_ajouter, script_finaliser, script_tokens):
        if not s.is_file():
            _echec(f"script attendu introuvable : {s} — clone Bridge_Agent incomplet ou en retard ?")
            return

    log.info(f"  Issue #{numero} : ajouter_projet_ccw.ps1 -NomProjet {nom_projet} -Depot {depot}…")
    try:
        res_ajouter = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_ajouter),
             "-NomProjet", nom_projet, "-Depot", depot],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT_CREATION_CLONE,
        )
    except subprocess.TimeoutExpired:
        _echec(f"ajouter_projet_ccw.ps1 a dépassé le délai ({TIMEOUT_CREATION_CLONE}s — clone trop long ?).")
        return
    except Exception as e:
        _echec(f"erreur d'exécution de ajouter_projet_ccw.ps1 : {e}")
        return
    sortie_ajouter = (res_ajouter.stdout or "") + (res_ajouter.stderr or "")
    if res_ajouter.returncode != 0:
        _echec(
            f"ajouter_projet_ccw.ps1 a échoué (code {res_ajouter.returncode}).\n\n"
            f"<details><summary>Log complet</summary>\n\n```\n{sortie_ajouter}\n```\n</details>"
        )
        return

    log.info(f"  Issue #{numero} : finaliser_projet_ccw_auto.ps1 -NomProjet {nom_projet}…")
    chemin_valeurs = _ecrire_fichier_valeurs_creation(topic_ntfy, gh_token, oauth_token)
    try:
        res_finaliser = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(script_finaliser),
             "-NomProjet", nom_projet, "-FichierValeurs", str(chemin_valeurs)],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=TIMEOUT_CREATION_FINALISE,
        )
    except subprocess.TimeoutExpired:
        _echec(f"finaliser_projet_ccw_auto.ps1 a dépassé le délai ({TIMEOUT_CREATION_FINALISE}s).")
        return
    except Exception as e:
        _echec(f"erreur d'exécution de finaliser_projet_ccw_auto.ps1 : {e}")
        return
    finally:
        # finaliser_projet_ccw_auto.ps1 supprime déjà ce fichier dans son
        # propre finally PowerShell — nettoyage Python en DEUXIÈME ligne de
        # défense (même pattern que app/ccw.py, issue #174) : couvre le cas
        # où le script n'a jamais démarré ou a planté avant son propre finally.
        if chemin_valeurs.exists():
            try:
                chemin_valeurs.unlink()
            except OSError:
                pass

    sortie_finaliser = (res_finaliser.stdout or "") + (res_finaliser.stderr or "")
    # Codes de mettre_a_jour_tokens_ccw.ps1, relayés par finaliser_projet_ccw_auto.ps1 :
    # 0 = OK, 2 = à vérifier (avertissement, pas un échec), 1/autre = échec.
    if res_finaliser.returncode not in (0, 2):
        _echec(
            f"finaliser_projet_ccw_auto.ps1 a échoué (code {res_finaliser.returncode}).\n\n"
            f"<details><summary>Log complet</summary>\n\n```\n{sortie_ajouter}\n\n{sortie_finaliser}\n```\n</details>"
        )
        return

    avertissement = ("" if res_finaliser.returncode == 0 else
                      "\n\n⚠️ Tokens appliqués mais vérification finale non concluante (code 2) — relisez le log ci-dessous.")
    message_resultat = (
        f"{MARQUEUR_RESULTAT}\n## Résultat\n\n"
        f"✅ Service CCW dédié « CCW-Watcher-{nom_projet} » créé et finalisé pour le projet "
        f"**{nom_projet}** (dépôt `{depot}`).{avertissement}\n\n"
        f"<details><summary>Log complet</summary>\n\n```\n{sortie_ajouter}\n\n{sortie_finaliser}\n```\n</details>"
    )
    if not commenter_resultat_avec_retry(numero, message_resultat):
        log.error(f"  ✗ Commentaire de résultat #{numero} (CREATION) impossible après retries — issue laissée OUVERTE pour reprise.")
        notifier(
            labels,
            titre=f"⚠️ {CFG.nom} #{numero} — bootstrap CCW résultat non posté",
            message=f"Service CCW « {nom_projet} » créé, mais le commentaire de résultat a échoué (réseau).",
            urgence_bureau="critical",
            priorite_ntfy="high",
            numero=numero,
        )
        _issues_en_cours_retirer(numero)
        return
    if not fermer_issue(numero):
        log.warning(f"  Fermeture de l'issue #{numero} (CREATION) incomplète — sera retentée au prochain cycle (garde d'idempotence).")
    log.info(f"  ✓ Issue #{numero} (CREATION) : service CCW « {nom_projet} » bootstrappé avec succès.")
    notifier(
        labels,
        titre=f"✅ {CFG.nom} #{numero} — service CCW « {nom_projet} » créé",
        message=f"Bootstrap automatique terminé pour le projet {nom_projet}.",
        urgence_bureau="normal",
        priorite_ntfy="default",
        numero=numero,
    )
    notifier_fin_sse(numero)
    _issues_en_cours_retirer(numero)

# ─── Détection de conflit avec un watcher actif (issue #125) ───────────────────
# Variantes LOCALES de app.projets.lister_projets() et app.watchers.watcher_actif() :
# app.projets importe watcher — réutiliser ces fonctions ici créerait un import
# circulaire. On réplique donc la même logique (glob des .conf, sonde du fichier
# PID) plutôt que d'importer le package app depuis le watcher.

def _lister_projets_connus() -> list[Config]:
    """Charge tous les projets (un configs/*.conf = un projet). Équivalent local
    de app.projets.lister_projets() ; ignore silencieusement les configs
    invalides (même contrat : except SystemExit)."""
    projets = []
    for chemin in sorted(DOSSIER_SCRIPT.glob("configs/*.conf")):
        try:
            projets.append(charger_config(chemin))
        except SystemExit:
            pass
    return projets

def _watcher_actif(cfg: Config) -> bool:
    """Vrai si un watcher tourne pour ce projet. Équivalent local de
    app.watchers.watcher_actif() : lit le fichier PID et sonde le processus
    (os.kill(pid, 0) ne tue pas, il vérifie l'existence)."""
    pid_file = DOSSIER_LOGS / f"watcher-{cfg.nom}.pid"
    if not pid_file.exists():
        return False
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, ValueError):
        return False


def _compter_watchers_actifs() -> int:
    """Nombre de watchers actuellement en cours d'exécution, tous projets
    confondus (issue #220, champ nb_projets_actifs_au_lancement de l'historique
    des durées). Réutilise les mêmes fichiers PID (logs/watcher-<nom>.pid, §13 du
    DOC) que detecter_conflit_watcher, plutôt qu'un scan brut du dossier logs/."""
    return sum(1 for cfg in _lister_projets_connus() if _watcher_actif(cfg))


def detecter_conflit_watcher(repo_cible_resolu: Path, projet_courant: str) -> str | None:
    """Cherche un projet connu, watcher actif, dont le rep_travail ou le
    périmètre chevauche repo_cible_resolu (chemins résolus, égalité ou relation
    parent/enfant). Retourne le nom du projet en conflit, ou None.

    Approche pragmatique (issue #125) : pas de verrou distribué, juste de la
    transparence. Le projet courant est exclu (son propre watcher est forcément
    actif puisqu'il traite l'issue en cours)."""
    for cfg in _lister_projets_connus():
        if cfg.nom == projet_courant:
            continue
        if not _watcher_actif(cfg):
            continue
        candidats = [cfg.rep_travail]
        if cfg.perimetre:
            candidats += [Path(part.strip()) for part in cfg.perimetre.split(",")
                          if part.strip()]
        for candidat in candidats:
            try:
                cr = candidat.expanduser().resolve()
            except (OSError, RuntimeError):
                continue
            if (cr == repo_cible_resolu
                    or cr in repo_cible_resolu.parents
                    or repo_cible_resolu in cr.parents):
                return cfg.nom
    return None

def ajouter_label(numero: int, label: str):
    """Ajoute un label à une issue sans la fermer."""
    try:
        subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--add-label", label],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
    except Exception as e:
        log.error(f"Erreur ajout label '{label}' sur issue #{numero} : {e}")

def commenter_issue(numero: int, message: str) -> bool:
    """Poste un commentaire sur une issue.

    Retourne True si `gh` a réussi (returncode 0), False sinon. Avant issue #195
    le code de retour n'était jamais inspecté : `subprocess.run` retourne
    normalement même sur exit non-zéro, donc un échec réseau intermittent de
    `gh issue comment` restait silencieux côté Python.

    Passe le message via `--body-file` (fichier temporaire UTF-8) plutôt que
    `--body <message>` (issue #237) : sous Windows la ligne de commande est
    plafonnée à 32767 caractères, dépassés par un rapport de build
    multi-étapes — `gh` retournait alors un exit code 0 sans avoir rien posté
    (troncature silencieuse en amont). `--body-file` supprime aussi tout
    problème d'échappement de shell."""
    fichier_tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False,
                encoding="utf-8") as f:
            f.write(message)
            fichier_tmp = f.name
        res = subprocess.run(
            ["gh", "issue", "comment", str(numero),
             "--repo", CFG.depot,
             "--body-file", fichier_tmp],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur commentaire issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return False
        return True
    except Exception as e:
        log.error(f"Erreur commentaire issue #{numero} : {e}")
        return False
    finally:
        if fichier_tmp:
            try:
                Path(fichier_tmp).unlink(missing_ok=True)
            except OSError:
                pass

def editer_dernier_commentaire(numero: int, message: str) -> bool:
    """Édite le dernier commentaire posté par le watcher sur l'issue
    (`gh issue comment --edit-last`), au lieu d'en poster un nouveau.

    Sert à enrichir le commentaire de résultat déjà posté avec le bloc de
    calibration TIMEOUT (issue #222) : la durée réelle et le TIMEOUT_suggéré
    ne sont connus qu'APRÈS la fermeture de l'issue (maj_calibration_timeout
    a besoin de duree_reelle), donc après le premier `commenter_resultat_avec_
    retry`. Best-effort : un échec ici n'affecte ni la clôture déjà effectuée
    ni le commentaire déjà en place (juste privé de son bloc calibration).

    Passe le message via `--body-file` pour la même raison que
    `commenter_issue` (issue #237)."""
    fichier_tmp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".md", delete=False,
                encoding="utf-8") as f:
            f.write(message)
            fichier_tmp = f.name
        res = subprocess.run(
            ["gh", "issue", "comment", str(numero),
             "--repo", CFG.depot,
             "--edit-last",
             "--body-file", fichier_tmp],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur édition dernier commentaire issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return False
        return True
    except Exception as e:
        log.error(f"Erreur édition dernier commentaire issue #{numero} : {e}")
        return False
    finally:
        if fichier_tmp:
            try:
                Path(fichier_tmp).unlink(missing_ok=True)
            except OSError:
                pass

def _commentaire_marque_present(numero: int, marqueur: str = MARQUEUR_RESULTAT) -> bool:
    """Relit l'issue et indique si un commentaire portant `marqueur` est bien
    présent (issue #237). Sert à VÉRIFIER qu'un commentaire a réellement été
    créé plutôt que de faire confiance au seul code de retour de `gh` (celui-ci
    peut rendre 0 sans qu'aucun commentaire n'existe, cf. issue #236).

    En cas d'erreur de lecture, retourne False (on ne peut pas confirmer la
    présence => la tentative est traitée comme un échec, quitte à reposter)."""
    try:
        res = subprocess.run(
            ["gh", "issue", "view", str(numero),
             "--repo", CFG.depot,
             "--json", "comments"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur lecture commentaires issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return False
        data = json.loads(res.stdout or "{}")
        return any(marqueur in (c.get("body") or "")
                   for c in data.get("comments", []))
    except Exception as e:
        log.error(f"Erreur vérification présence commentaire issue #{numero} : {e}")
        return False

def _lister_commentaires(numero: int) -> list[str]:
    """Récupère les corps de tous les commentaires actuels de l'issue, dans
    l'ordre chronologique renvoyé par `gh` — sert à détecter une RELANCE
    (issue #592, voir `_issue_est_relance`). Best-effort : liste vide en cas
    d'erreur de lecture (aucune RELANCE détectée plutôt qu'une exception qui
    interromprait le traitement)."""
    try:
        res = subprocess.run(
            ["gh", "issue", "view", str(numero),
             "--repo", CFG.depot,
             "--json", "comments"],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        if res.returncode != 0:
            log.error(f"Erreur lecture commentaires issue #{numero} (code {res.returncode}) : {res.stderr.strip()}")
            return []
        data = json.loads(res.stdout or "{}")
        return [c.get("body") or "" for c in data.get("comments", [])]
    except Exception as e:
        log.error(f"Erreur lecture commentaires issue #{numero} : {e}")
        return []

def _issue_est_relance(commentaires: list[str]) -> bool:
    """True si `commentaires` (historique de l'issue AVANT l'ACK courante)
    contient déjà un message d'échec définitif du watcher (préfixe
    `MARQUEUR_ECHEC_TENTATIVES`, posté avant needs-human) — signe d'une
    RELANCE (champ RELANCE, issue #516) plutôt que d'un premier traitement.
    Voir `maj_calibration_timeout` (issue #592) pour l'usage : la durée
    mesurée pour une RELANCE est alors exclue de la calibration TIMEOUT."""
    return any(MARQUEUR_ECHEC_TENTATIVES in c for c in commentaires)

def commenter_resultat_avec_retry(numero: int, message: str) -> bool:
    """Poste le commentaire de RÉSULTAT avec retry/backoff (issue #195).

    1 tentative initiale, puis jusqu'à 3 tentatives espacées de 5, 10 puis 20 s
    (DELAIS_RETRY_RESULTAT). Retourne True dès qu'une tentative réussit, False si
    toutes échouent. Réservé au commentaire de résultat : l'ACK et le message
    d'échec restent best-effort sans retry.

    VÉRIFICATION post-publication (issue #236/#237) : un exit code 0 de `gh`
    ne suffit plus à conclure au succès — l'incident #236 a montré un
    commentaire jamais créé malgré un code de retour 0 (dépassement de la
    limite argv Windows, cf. `commenter_issue`). Après chaque tentative
    rendant 0, on relit l'issue et on exige la présence effective du
    commentaire (marqueur `MARQUEUR_RESULTAT`, ajouté par l'appelant en tête
    de `message`) avant de retourner True. Si la relecture ne le trouve pas,
    la tentative est traitée comme un échec et on enchaîne sur la suivante."""
    def _tentative() -> bool:
        if not commenter_issue(numero, message):
            return False
        if not _commentaire_marque_present(numero):
            log.error(
                f"  Commentaire de résultat #{numero} : `gh` a rendu 0 mais aucun "
                f"commentaire correspondant n'a été retrouvé à la relecture — "
                f"traité comme un échec (issue #236)."
            )
            return False
        return True

    if _tentative():
        return True
    for delai in DELAIS_RETRY_RESULTAT:
        log.warning(f"  Commentaire de résultat #{numero} échoué — nouvelle tentative dans {delai}s.")
        time.sleep(delai)
        if _tentative():
            return True
    log.error(f"  Commentaire de résultat #{numero} échoué après {1 + len(DELAIS_RETRY_RESULTAT)} tentatives.")
    return False

def resultat_deja_poste(numero: int) -> bool:
    """Garde d'idempotence (issue #195) : indique si l'issue porte déjà un
    commentaire de résultat posté par le watcher.

    Repère le commentaire par `MARQUEUR_RESULTAT` (issue #237), une ligne HTML
    invisible ajoutée en tête du message de résultat — et non plus par la
    sous-chaîne "## Résultat", qui matchait aussi "## Résultat attendu" (titre
    de section présent dans quasi toutes nos issues) : si ce texte atterrissait
    un jour dans un commentaire, l'ancienne garde fermait l'issue sans rien
    traiter.

    Sert à éviter un retraitement complet à tort si l'issue est reprise alors
    qu'un cycle précédent avait réussi le commentaire mais échoué la fermeture
    (coupure réseau entre `comment` et `close`). En cas d'erreur de lecture, on
    retourne False (comportement historique : on retraite) plutôt que de risquer
    de sauter à tort une issue réellement non traitée."""
    return _commentaire_marque_present(numero)

def fermer_issue(numero: int) -> bool:
    """Ferme une issue et ajoute le label 'done'.

    Retourne True seulement si les DEUX sous-commandes (`close` puis
    `add-label`) ont réussi (issue #238, sur le modèle de `commenter_issue`
    depuis #195) : avant #238 aucun des deux codes de retour n'était
    inspecté, si bien qu'une issue pouvait être fermée sans recevoir le
    label 'done', ou le recevoir sans être fermée, en silence complet — deux
    états incohérents ensuite mal interprétés par la garde d'idempotence
    (LABEL_FAIT / resultat_deja_poste en tête de `traiter_issue`) et par
    l'interface web.

    Les deux sous-commandes sont tentées inconditionnellement (comme avant
    #238), pour ne pas transformer un échec de `close` en un label manquant
    évitable. Aucune compensation automatique en cas d'échec partiel : on se
    contente de journaliser l'état incohérent obtenu, pour diagnostic."""
    try:
        res_close = subprocess.run(
            ["gh", "issue", "close", str(numero), "--repo", CFG.depot],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        close_ok = res_close.returncode == 0
        if not close_ok:
            log.error(f"Erreur fermeture issue #{numero} (code {res_close.returncode}) : {res_close.stderr.strip()}")

        res_label = subprocess.run(
            ["gh", "issue", "edit", str(numero),
             "--repo", CFG.depot,
             "--add-label", LABEL_FAIT],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30
        )
        label_ok = res_label.returncode == 0
        if not label_ok:
            log.error(f"Erreur ajout label '{LABEL_FAIT}' sur issue #{numero} (code {res_label.returncode}) : {res_label.stderr.strip()}")

        if close_ok and not label_ok:
            log.error(f"  État incohérent issue #{numero} : FERMÉE mais SANS le label '{LABEL_FAIT}' (pas de compensation automatique).")
        elif label_ok and not close_ok:
            log.error(f"  État incohérent issue #{numero} : label '{LABEL_FAIT}' posé mais issue NON fermée (pas de compensation automatique).")

        # Checkpoint de fin de traitement (issue #615) : rafraîchit le quota
        # GraphQL partagé pour que le widget /rate-limit reflète l'activité de
        # CE watcher dans les secondes qui suivent, sans attendre le prochain
        # polling à intervalle fixe du widget.
        etat_rate_limit.maj_rate_limit("watcher.fermer_issue")

        return close_ok and label_ok
    except Exception as e:
        log.error(f"Erreur fermeture issue #{numero} : {e}")
        return False

def _lister_processus_pgid(pgid: int, exclure_pid: int | None = None) -> list[tuple[int, str]]:
    """POSIX uniquement. Liste (pid, ligne de commande) des process actuellement
    vivants dont le pgid vaut exactement pgid, hors exclure_pid. Lecture directe
    de /proc, sans dépendance externe (psutil). Best-effort : un process qui
    disparaît pendant l'énumération (race normale) est simplement ignoré."""
    resultat = []
    proc_dir = Path("/proc")
    if not proc_dir.is_dir():
        return resultat
    for entree in proc_dir.iterdir():
        if not entree.name.isdigit():
            continue
        pid = int(entree.name)
        if pid == exclure_pid:
            continue
        try:
            if os.getpgid(pid) != pgid:
                continue
            cmdline = entree.joinpath("cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace").strip()
        except (ProcessLookupError, FileNotFoundError, PermissionError):
            continue
        resultat.append((pid, cmdline or "(cmdline indisponible)"))
    return resultat


_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
_JobObjectExtendedLimitInformation = 9
# Seuls droits requis par AssignProcessToJobObject (documentation Microsoft) :
# PROCESS_SET_QUOTA + PROCESS_TERMINATE — plutôt que l'ancien
# _PROCESS_ALL_ACCESS = 0x1F0FFF (valeur pré-Vista, toujours fonctionnelle
# mais bien plus large que nécessaire ; issue #251).
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001
_PROCESS_ACCES_JOB = _PROCESS_SET_QUOTA | _PROCESS_TERMINATE
# Droit minimal (Vista+) pour sonder l'existence d'un process via OpenProcess
# SANS pouvoir agir dessus — utilisé par _pid_vivant (issue #584), même esprit
# de moindre privilège que _PROCESS_ACCES_JOB ci-dessus.
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.wintypes.DWORD),
        ("SchedulingClass", ctypes.wintypes.DWORD),
    ]


class _IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", _IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def _declarer_prototypes_kernel32_windows():
    """Windows uniquement — appelée une seule fois, à l'import du module,
    depuis la garde `if os.name == "nt"` ci-dessous. Déclare restype/argtypes
    des fonctions kernel32 utilisées pour l'objet Job (issue #251, suite
    #249) : sans cela, ctypes suppose par défaut un retour c_int (32 bits
    signés) alors que CreateJobObjectW/OpenProcess retournent un HANDLE — 64
    bits sur Windows x64. La valeur est alors tronquée silencieusement ; ça
    fonctionne tant que le handle noyau reste une petite valeur, mais rien
    ne le garantit, et le handle tronqué est ensuite repassé en argument à
    SetInformationJobObject/AssignProcessToJobObject/CloseHandle où il subit
    une seconde troncature à l'appel. Ne pas exécuter sous Linux : accède à
    ctypes.windll, absent hors Windows."""
    wt = ctypes.wintypes
    k32 = ctypes.windll.kernel32

    k32.CreateJobObjectW.restype = wt.HANDLE
    k32.CreateJobObjectW.argtypes = (wt.LPVOID, wt.LPCWSTR)

    k32.SetInformationJobObject.restype = wt.BOOL
    k32.SetInformationJobObject.argtypes = (wt.HANDLE, ctypes.c_int, wt.LPVOID, wt.DWORD)

    k32.OpenProcess.restype = wt.HANDLE
    k32.OpenProcess.argtypes = (wt.DWORD, wt.BOOL, wt.DWORD)

    k32.AssignProcessToJobObject.restype = wt.BOOL
    k32.AssignProcessToJobObject.argtypes = (wt.HANDLE, wt.HANDLE)

    k32.CloseHandle.restype = wt.BOOL
    k32.CloseHandle.argtypes = (wt.HANDLE,)


if os.name == "nt":
    _declarer_prototypes_kernel32_windows()


def _creer_job_windows_kill_on_close():
    """Windows uniquement. Crée un objet Job noyau avec le flag
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE : fermer son handle (CloseHandle)
    termine immédiatement TOUT process qui y est encore assigné, sans avoir
    besoin de connaître le moindre PID à cet instant-là — à la différence de
    `taskkill /PID <pid> /T /F`, qui doit reparcourir l'arbre généalogique du
    PID au moment de l'appel et échoue donc dès que ce PID n'existe plus
    (voir _nettoyer_arbre_claude). Retourne le handle du job en cas de
    succès, sinon None (chaque échec est journalisé par l'appelant)."""
    job = ctypes.windll.kernel32.CreateJobObjectW(None, None)
    if not job:
        return None

    info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = ctypes.windll.kernel32.SetInformationJobObject(
        job, _JobObjectExtendedLimitInformation,
        ctypes.byref(info), ctypes.sizeof(info),
    )
    if not ok:
        ctypes.windll.kernel32.CloseHandle(job)
        return None
    return job


def _assigner_job_windows(job, pid: int) -> bool:
    """Windows uniquement. Assigne le process `pid` au job `job` — doit être
    appelé pendant que ce process est encore vivant (juste après son
    démarrage), condition nécessaire et suffisante : une fois assigné, un
    process reste dans le job jusqu'à sa mort ou la fermeture du job, qu'il
    ait ou non survécu à claude entre-temps."""
    handle = ctypes.windll.kernel32.OpenProcess(_PROCESS_ACCES_JOB, False, pid)
    if not handle:
        return False
    try:
        return bool(ctypes.windll.kernel32.AssignProcessToJobObject(job, handle))
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _preparer_job_windows(pid: int):
    """Windows uniquement. Crée l'objet Job et y assigne immédiatement `pid`
    (voir _creer_job_windows_kill_on_close / _assigner_job_windows). À
    appeler juste après le Popen du process claude, PENDANT qu'il est
    vivant — c'est le seul moment où l'assignation est possible. Retourne
    le handle à conserver jusqu'à _nettoyer_arbre_claude (qui le fermera),
    ou None si la préparation a échoué à une étape ou l'autre ; chaque échec
    est journalisé ici (issue #249 point 3 : ne jamais rester silencieux)."""
    job = _creer_job_windows_kill_on_close()
    if job is None:
        log.warning(
            f"Objet Job Windows non créé pour claude (PID {pid}) : le "
            f"nettoyage de fin de tâche ne pourra pas garantir la "
            f"terminaison de sa descendance si elle survit (issue #249)."
        )
        return None
    if not _assigner_job_windows(job, pid):
        log.warning(
            f"Échec d'assignation du process claude (PID {pid}) à l'objet "
            f"Job Windows : le nettoyage de fin de tâche ne pourra pas "
            f"garantir la terminaison de sa descendance si elle survit "
            f"(issue #249)."
        )
        try:
            ctypes.windll.kernel32.CloseHandle(job)
        except Exception:
            pass
        return None
    return job


def _nettoyer_arbre_claude(proc: subprocess.Popen, job_windows=None) -> None:
    """Garantit qu'aucun process de l'arbre engendré par CE claude (proc.pid) ne
    survive au retour de lancer_claude (issue #247, révisé #249). Appelée
    depuis un `finally` : couvre indifféremment succès, échec, TimeoutExpired
    et exception.

    Cas réel à l'origine de l'issue : un `cmd.exe` lancé par un script de build
    Windows (pushd + .bat) survivait à la fermeture de l'issue et gardait un
    verrou sur le partage réseau utilisé comme répertoire courant, rendant
    l'exécutable produit injouable jusqu'à un `taskkill` manuel — sans le
    moindre signal dans le journal.

    Pourquoi `taskkill /PID <pid> /T /F` NE SUFFIT PAS (issue #249) : cette
    fonction s'exécute dans le `finally` de lancer_claude, donc APRÈS le
    retour de `proc.communicate()` — à cet instant le process claude est déjà
    terminé et réapé par l'OS. Or taskkill a besoin que le PID cible EXISTE
    ENCORE pour remonter son arbre généalogique ; sur un PID mort, il échoue
    immédiatement (« process not found ») sans toucher un seul descendant.
    C'est exactement le scénario d'origine : le `cmd.exe` orphelin survit à
    `claude`, donc au moment du nettoyage son PID parent n'est plus
    traçable. `CREATE_NEW_PROCESS_GROUP` ne comble pas l'écart : sous
    Windows les groupes de process ne servent qu'au routage de
    Ctrl+C/Ctrl+Break, pas à la terminaison d'une arborescence. Seul un objet
    Job — assigné AVANT que le process ne meure, voir _preparer_job_windows,
    appelé juste après le Popen dans lancer_claude — garantit la terminaison
    de toute la descendance, PID vivant ou non au moment de l'appel.

    Ne cible QUE la descendance du PID claude de CETTE tâche, jamais par nom
    d'exécutable — point critique (#247 point 4) : une erreur ici tuerait le
    watcher lui-même ou un watcher frère sur la même machine.
    - POSIX : proc a été lancé avec start_new_session=True, donc son pgid ==
      son propre pid — un groupe forcément neuf et distinct de celui du
      watcher (et de tout autre watcher). os.killpg cible ce seul groupe.
      Inchangé par #249 : correct et déjà couvert par
      tests/test_nettoyage_arbre_247.py.
    - Windows : fermeture du handle de l'objet Job créé/assigné par
      _preparer_job_windows au démarrage de claude (voir lancer_claude).

    Point 4 (#249) : l'intégralité du corps est enveloppée dans un
    garde-fou — _lister_processus_pgid peut lever une OSError (iterdir sur
    /proc), os.killpg une PermissionError, et l'appel ctypes Windows
    n'importe quelle exception. Aucune de ces exceptions ne doit s'échapper
    de cette fonction : elle est appelée depuis un `finally`, et une
    exception à cet endroit remonterait à travers lancer_claude et
    masquerait sa valeur de retour.
    """
    pid = getattr(proc, "pid", None)
    try:
        if os.name == "nt":
            if job_windows is None:
                log.warning(
                    f"Nettoyage de l'arbre claude (PID {pid}) impossible : "
                    f"aucun objet Job disponible (échec de préparation "
                    f"journalisé au démarrage — voir _preparer_job_windows). "
                    f"Un taskkill de repli n'aurait de toute façon pas pu "
                    f"aider : le PID {pid} est déjà mort à ce stade."
                )
            else:
                ok = False
                try:
                    ok = bool(ctypes.windll.kernel32.CloseHandle(job_windows))
                except Exception as e:
                    log.warning(
                        f"Exception lors de la fermeture de l'objet Job "
                        f"Windows pour le nettoyage de l'arbre claude "
                        f"(PID {pid}) : {e}"
                    )
                if ok:
                    log.warning(
                        f"Arbre de process claude (PID {pid}) nettoyé via "
                        f"fermeture de l'objet Job Windows : tout process "
                        f"encore assigné (y compris ceux ayant survécu à "
                        f"claude) a été terminé."
                    )
                else:
                    log.warning(
                        f"Échec de fermeture de l'objet Job Windows pour le "
                        f"nettoyage de l'arbre claude (PID {pid}) : "
                        f"CloseHandle a échoué — la descendance a pu "
                        f"survivre."
                    )
        else:
            orphelins = _lister_processus_pgid(pid, exclure_pid=pid)
            encore_vivant = proc.poll() is None
            for pid_orphelin, cmdline in orphelins:
                log.warning(
                    f"Descendant orphelin de claude (PID {pid}) tué : PID {pid_orphelin} — {cmdline}"
                )
            if orphelins or encore_vivant:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # déjà mort entre l'énumération et le kill : rien à faire
                except PermissionError as e:
                    log.warning(f"os.killpg refusé pour l'arbre claude (PID {pid}) : {e}")

        try:
            proc.wait(timeout=5)
        except Exception:
            pass  # best-effort : ne jamais faire échouer lancer_claude sur ce nettoyage
    except Exception as e:
        log.warning(
            f"Nettoyage de l'arbre de process claude (PID {pid}) a levé une "
            f"exception inattendue et a été abandonné : {e}"
        )


# Diagnostic CCL amélioré (issue #309) — incident #279 : plusieurs issues
# avaient échoué en ~1,2s avec "Erreur inconnue" (token CCL expiré), sans
# aucune indication exploitable dans le log faute de capture du stderr et de
# vérification préalable de l'authentification.

# Limite de caractères de stderr journalisés en cas d'échec du process claude
# (issue #309) — assez pour un diagnostic d'authentification/réseau, sans
# risquer un dump de plusieurs Mo dans le log.
LIMITE_STDERR_LOG = 2000

# Signatures (recherche insensible à la casse dans stdout+stderr) évoquant un
# token d'authentification CCL manquant ou expiré (issue #309). Liste
# best-effort et non exhaustive : le message exact dépend de la version du
# CLI claude, d'où plusieurs variantes plutôt qu'une correspondance unique.
SIGNATURES_TOKEN_EXPIRE = (
    "not logged in",
    "please run",
    "/login",
    "invalid api key",
    "authentication_error",
    "unauthorized",
    "please authenticate",
    "oauth token",
)


def _extrait_stderr(stderr: str | None, limite: int = LIMITE_STDERR_LOG) -> str:
    """Tronque le stderr capturé du process claude à `limite` caractères, pour
    journalisation en cas d'échec (issue #309)."""
    if not stderr:
        return ""
    stderr = stderr.strip()
    if len(stderr) > limite:
        return stderr[:limite] + f"... [tronqué, {len(stderr)} caractères au total]"
    return stderr


def verifier_preflight_token(cwd: Path = None) -> None:
    """
    Sonde rapide d'authentification CCL (issue #309), à lancer UNE FOIS avant
    les tentatives sur une issue — pas à chaque tentative. But : éviter de
    découvrir un token expiré seulement après plusieurs tentatives ratées avec
    leur timeout complet (incident #279).

    N'appelle PAS `claude --print ""` (argument positionnel vide) : ce dernier
    est rejeté immédiatement par la validation d'arguments du CLI ("Input must
    be provided...") AVANT toute vérification d'authentification, quel que
    soit l'état du token — inutile comme sonde. Une entrée vide est passée via
    stdin à la place, qui atteint bien le contrôle d'authentification.

    Ne bloque JAMAIS le traitement de l'issue : toute exception (timeout,
    claude introuvable, etc.) est avalée silencieusement — le pre-flight
    n'enrichit le log que s'il détecte positivement un problème, il ne fait
    jamais échouer ni retarder le traitement normal.
    """
    try:
        cwd_effectif = CFG.rep_travail if cwd is None else cwd
        resultat = subprocess.run(
            ["claude", "--print"],
            input="",
            cwd=cwd_effectif,
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=5,
        )
        sortie = f"{resultat.stdout or ''}\n{resultat.stderr or ''}".lower()
        if any(signature in sortie for signature in SIGNATURES_TOKEN_EXPIRE):
            log.warning(
                "  ⚠️  Pre-flight : token CCL expiré ou absent — relancer `claude` "
                "interactivement et taper `/login`."
            )
    except Exception:
        pass


def lancer_claude(numero: int, titre: str, body: str, dry_run: bool,
                  mode: str = MODE_LECTURE,
                  timeout: int = None,
                  modele: str = "",
                  prompt_perso: str = None,
                  perimetre: str = None,
                  cwd: Path = None,
                  verrou: Path = None,
                  chemin_scratch: Path = None,
                  chemin_worktree: Path = None) -> tuple[bool, str]:
    """
    Lance Claude Code en mode non-interactif sur une issue.

    `mode` (issue #327, remplace l'ancien booléen autoriser_ecriture) : un des
    trois MODE_* — par défaut MODE_LECTURE (diagnostic, aucune écriture). En
    MODE_ECRITURE (label 'mode_write' posé sciemment) comme en
    MODE_LECTURE_ACTIVE (label 'mode_scratch'), --dangerously-skip-permissions
    est ajouté : la lecture active a besoin d'écrire dans le scratch, ce qui
    désarme les mêmes protections claude que l'écriture libre — d'où le
    garde-fou niveau 2 (empreinte REP_TRAVAIL, voir traiter_issue). Le
    garde-fou anti-push/anti-écriture-projet reste dans le prompt (niveau 1).

    chemin_scratch : requis si mode == MODE_LECTURE_ACTIVE — chemin exact du
    dossier scratch (créé par l'appelant, voir _chemin_scratch), inséré tel
    quel dans le bloc de garde-fou du prompt. Ignoré pour les deux autres modes.

    prompt_perso : si fourni, remplace intégralement le prompt standard (titre/body
    + garde-fou + format de réponse imposé). Sert aux passes qui ont besoin d'un
    prompt sur mesure — ex. la passe diagnostique (issue #124), qui ne doit PAS
    demander de résoudre la tâche. Le reste de la machinerie (dry-run, cwd, timeout,
    modèle, --dangerously-skip-permissions selon le mode) est inchangé.

    perimetre / cwd : surchargent respectivement CFG.perimetre (clause de prompt) et
    CFG.rep_travail (répertoire réel du subprocess). None = valeur du .conf. Servent
    au périmètre dynamique (issue #125) : pour un projet à périmètre dynamique, ces
    deux valeurs viennent du champ REPO_CIBLE de l'issue, pas de la config.

    verrou : chemin du fichier verrou posé par acquerir_verrou pour cette tâche
    (issue #322), si fourni. Sert uniquement à y consigner le pgid du claude
    tout juste lancé (_maj_verrou_pgid), une fois le Popen réussi — permet à un
    watcher suivant de cibler et tuer cet éventuel orphelin si CE watcher meurt
    brutalement avant la fin du traitement. None = pas de verrou associé (ex.
    passe diagnostique) : aucun pgid n'est consigné, comportement inchangé.

    chemin_worktree : chemin du worktree git isolé de cette tâche (issue #337),
    si la parallélisation mode_write y a placé CCL. Sert uniquement à injecter
    dans le prompt un bloc d'avertissement dédié (worktree/branche/consigne
    CHANGELOG-<N>.md) — `cwd` porte déjà le répertoire RÉEL du subprocess
    (worktree ou REP_TRAVAIL). None = traitement hors worktree (comportement
    inchangé, aucun bloc injecté).

    Retourne (succès, sortie).
    """
    if mode == MODE_LECTURE_ACTIVE and chemin_scratch is None:
        raise ValueError("lancer_claude : chemin_scratch requis en MODE_LECTURE_ACTIVE.")

    if timeout is None:
        timeout = CFG.timeout_claude

    perimetre_effectif = CFG.perimetre if perimetre is None else perimetre
    cwd_effectif = CFG.rep_travail if cwd is None else cwd

    if mode == MODE_ECRITURE:
        if CFG.cmd_backup:
            consigne_backup = (
                "- Fais TOUJOURS une sauvegarde avant toute modification, en lançant "
                f"cette commande depuis le répertoire du projet :\n  {CFG.cmd_backup}"
            )
        else:
            consigne_backup = (
                "- Fais TOUJOURS une sauvegarde de l'état courant avant toute modification "
                "(par exemple un commit git de tout le dossier), afin de permettre un retour arrière."
            )
        garde_fou = f"""
MODE ÉCRITURE ACTIVÉ — tu es autorisé à modifier des fichiers, exécuter des
commandes et faire des commits git si la tâche le demande.
RÈGLES DE SÉCURITÉ IMPÉRATIVES :
{consigne_backup}
- Ne fais JAMAIS 'git push' ni 'git push --force' : Alain pousse lui-même,
  manuellement, après avoir vérifié tes commits.
- N'exécute aucune commande destructrice (rm -rf large, git reset --hard sur du
  travail non sauvegardé, git filter-repo, force-push) sans que la tâche le
  demande EXPLICITEMENT.
- En cas de doute, préfère t'arrêter et décrire ce que tu ferais plutôt que d'agir.
"""
    elif mode == MODE_LECTURE_ACTIVE:
        # Défense en profondeur niveau 1 (issue #327, même esprit que le
        # garde-fou configs #318) : cette consigne réduit le risque au cas
        # normal, mais ne suffit pas seule (non-déterminisme du prompt, cf.
        # #290/#291) — le niveau 2 (empreinte REP_TRAVAIL avant/après, dans
        # traiter_issue) reste le filet déterministe qui restaure et signale
        # un échec si elle n'est pas respectée.
        garde_fou = f"""
MODE LECTURE ACTIVE (scratch confiné) ACTIVÉ — tu peux écrire des fichiers,
mais UNIQUEMENT dans le dossier scratch suivant, jamais ailleurs :
  {chemin_scratch}
RÈGLES DE SÉCURITÉ IMPÉRATIVES :
- N'écris JAMAIS dans le répertoire de travail du projet ni nulle part hors de
  {chemin_scratch} — ce dossier scratch sert uniquement aux fichiers qu'un
  outil d'analyse (linter, config générée) exige sur disque pour tourner, par
  exemple {chemin_scratch}/eslint.config.js.
- Ne fais JAMAIS 'git commit', 'git push' ni aucune autre commande modifiant
  l'état du dépôt du projet.
- N'exécute aucune commande destructrice (rm -rf large, git reset --hard, git
  clean, git filter-repo, force-push).
- Ce dossier scratch est ÉPHÉMÈRE : il est supprimé automatiquement à la fin
  de cette tâche, quel qu'en soit le résultat — n'y stocke rien qui doive
  survivre.
- Le livrable attendu reste un RAPPORT de lecture (comme en lecture seule) :
  analyse et constats sur le projet, PAS une modification du projet lui-même.
- Une vérification technique automatique compare l'état du projet avant/après
  cette tâche et annule/restaure toute écriture détectée hors scratch : respecte
  donc strictement cette consigne dès le départ plutôt que de t'y fier.
"""
    else:
        garde_fou = """
MODE LECTURE SEULE — tu ne dois que lire, analyser et rapporter. N'écris aucun
fichier, n'exécute aucune commande modifiant l'état du système ou du dépôt.
"""

    # Contexte projet optionnel : fichier décrivant l'architecture, les
    # conventions, l'historique. Injecté tel quel dans le prompt pour donner à
    # CCL une connaissance du projet sans alourdir chaque issue.
    bloc_contexte = ""
    if CFG.fichier_contexte:
        chemin_ctx = Path(CFG.fichier_contexte).expanduser()
        if not chemin_ctx.is_absolute():
            # cwd_effectif (pas CFG.rep_travail) : en worktree (issue #337), le
            # fichier de contexte relatif doit être lu depuis le worktree — un
            # `git worktree` contient une copie complète des fichiers suivis,
            # CONTEXTE.md y est donc présent au même chemin relatif.
            chemin_ctx = cwd_effectif / chemin_ctx
        if chemin_ctx.exists():
            try:
                contenu = chemin_ctx.read_text(encoding="utf-8", errors="replace")
                LIMITE = 4000
                if len(contenu) > LIMITE:
                    contenu = contenu[:LIMITE] + "\n[...contexte tronqué à 4000 caractères...]"
                bloc_contexte = (
                    f"\nCONTEXTE DU PROJET (lu depuis {chemin_ctx}) :\n"
                    f"---\n{contenu}\n---\n"
                )
            except Exception as e:
                log.warning(f"Lecture du fichier de contexte '{chemin_ctx}' impossible : {e}")
        else:
            log.warning(f"Fichier de contexte '{chemin_ctx}' introuvable — rien injecté.")

    # Consignes à trois couches (globales/type/projet) injectées dans le prompt
    # CCL (issue #211). Placées APRÈS le bloc CONTEXTE et AVANT la clause de
    # périmètre / le garde-fou : choix assumé de regrouper toutes les « règles »
    # (consignes de sécurité globales, spécificités de type/projet, périmètre,
    # garde-fou mode écriture) en fin de prompt, zone la mieux suivie par le
    # modèle. Couverture universelle : quel que soit le chemin de création de
    # l'issue (formulaire web, `gh issue create` d'un chef, création manuelle
    # GitHub), le point de passage unique reste ce prompt. Mêmes garde-fous que
    # #209 (globales.md manquant → warning sans bloquer ; type/projet absents →
    # silencieux) — voir _consignes_injectees.
    bloc_consignes = ""
    consignes = _consignes_injectees(CFG.nom, titre, body)
    if consignes:
        bloc_consignes = f"\nCONSIGNES (injectées automatiquement) :\n---\n{consignes}\n---\n"

    if perimetre_effectif:
        clause_perimetre = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire, modifier ou exécuter des commandes "
            f"que dans les répertoires suivants : {perimetre_effectif}\n"
            f"Toute action en dehors de ce périmètre est interdite, même si la tâche "
            f"le demande explicitement. En cas de doute, arrête-toi et signale-le.\n"
        )
    else:
        clause_perimetre = ""

    # Bloc d'avertissement worktree (issue #337) : injecté UNIQUEMENT quand
    # cette tâche mode_write tourne dans un worktree git isolé (parallélisation
    # active), pour que CCL sache où il se trouve réellement et respecte la
    # convention CHANGELOG-<N>.md (fusionnée plus tard par
    # scripts/fusionner_changelog.py, avant le push d'Alain — jamais dans
    # CHANGELOG.md directement, qui provoquerait un conflit avec les autres
    # worktrees actifs en parallèle).
    bloc_worktree = ""
    if chemin_worktree is not None:
        bloc_worktree = (
            f"\n⚠️ Tu travailles dans un worktree isolé : {chemin_worktree}\n"
            f"Branche : worktree-issue-{numero}\n"
            f"CHANGELOG : écris ton entrée dans CHANGELOG-{numero}.md à la racine de ce "
            f"worktree, PAS dans CHANGELOG.md. Le script fusionner_changelog.py "
            f"intégrera CHANGELOG-{numero}.md dans CHANGELOG.md avant le push.\n"
        )

    if prompt_perso is not None:
        prompt = prompt_perso
    else:
        prompt = f"""Tu es l'agent Linux (CCL) du bridge inter-agents, projet « {CFG.nom} ».
Traite la tâche suivante issue du GitHub Issue #{numero} :

TITRE : {titre}

BODY :
{body}
{bloc_contexte}{bloc_consignes}{clause_perimetre}{bloc_worktree}{garde_fou}
Instructions :
1. Lis attentivement la tâche demandée
2. Effectue le travail demandé (dans les limites du mode ci-dessus)
3. Si tu dois créer une issue for-windows, utilise : gh issue create --repo {CFG.depot} --label "bridge,for-windows" ...
4. Si tu délègues une partie du travail à des sous-agents (outil Task/Agent),
   ATTENDS la fin de TOUS les sous-agents lancés et intègre leurs résultats
   AVANT de produire ta réponse finale ci-dessous — ne la considère jamais
   émise tant qu'un sous-agent reste en cours. Cette invocation est unique et
   non interactive : seule ta toute DERNIÈRE prise de parole est capturée et
   postée telle quelle sur l'issue. Si un sous-agent te notifie qu'il a
   terminé APRÈS que tu aies déjà produit cette réponse finale, n'émets
   AUCUNE nouvelle prise de parole (elle écraserait le rapport déjà produit
   et serait postée à sa place) — ignore silencieusement cette notification
   tardive, ton rapport final reste celui déjà émis.

Réponds avec ce format exact, sans rien ajouter avant ni après :

✅ Tâche terminée — [résumé en une ligne de ce qui a été fait]
Commits (dans {cwd_effectif}) : [hash backup] (backup) + [hash fix] (fix) — ou "aucun" si lecture seule
py_compile : OK / N/A — push : aucun

<details>
<summary>Détails complets</summary>

[Ici : description complète de chaque modification, fichiers touchés,
 lignes ajoutées/supprimées, décisions prises, points d'attention.]

</details>

Le bloc <details> est rendu par GitHub comme un accordéon dépliable —
les informations sont là mais n'encombrent pas la lecture rapide.

Si la tâche échoue, remplace ✅ par ❌ et explique la cause en une ligne.
"""

    if dry_run:
        mode_txt = {
            MODE_ECRITURE:       "ÉCRITURE",
            MODE_LECTURE_ACTIVE: "LECTURE ACTIVE (scratch)",
            MODE_LECTURE:        "lecture seule",
        }[mode]
        log.info(f"[DRY-RUN] Claude Code serait lancé pour issue #{numero} (mode {mode_txt}, cwd {cwd_effectif})")
        return True, f"[DRY-RUN] Tâche simulée avec succès (mode {mode_txt})."

    cmd = ["claude", "--print"]
    if modele:
        cmd += ["--model", modele]
    if mode != MODE_LECTURE:
        cmd.append("--dangerously-skip-permissions")
    cmd.append(prompt)
    if mode == MODE_LECTURE:
        # Issue #542, révisé #546 : allowlist fine plutôt que
        # --dangerously-skip-permissions (voir commentaire sur
        # OUTILS_LECTURE_AUTORISES) — débloque git fetch/pull --ff-only sans
        # désarmer le reste des protections de Claude Code en lecture seule.
        # Un seul argument joint par virgules (et non un token par entrée) :
        # voir la remarque #546 dans le commentaire ci-dessus sur
        # OUTILS_LECTURE_AUTORISES.
        cmd += ["--allowedTools", ",".join(OUTILS_LECTURE_AUTORISES)]

    # Popen (plutôt que subprocess.run) pour garder la main sur le PID : le
    # nettoyage de l'arbre de process (issue #247, révisé #249) doit
    # s'exécuter dans un finally, quel que soit le mode de sortie (succès,
    # échec, timeout, exception), et a besoin du PID pour ne cibler QUE la
    # descendance de CE claude.
    # - POSIX : start_new_session=True donne à ce process une session/un
    #   pgid à lui, préalable nécessaire à os.killpg — voir
    #   _nettoyer_arbre_claude.
    # - Windows : CREATE_NEW_PROCESS_GROUP isole le routage Ctrl+Break de ce
    #   process de celui du watcher (sans rapport avec la terminaison de
    #   l'arbre, assurée par l'objet Job créé/assigné juste après le Popen
    #   ci-dessous — voir _preparer_job_windows).
    kwargs_popen = dict(
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        cwd=cwd_effectif,
    )
    if os.name == "nt":
        kwargs_popen["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kwargs_popen["start_new_session"] = True

    proc = None
    job_windows = None
    try:
        proc = subprocess.Popen(cmd, **kwargs_popen)
        if os.name == "nt":
            # Doit être fait ICI, pendant que proc est vivant : l'assignation
            # au job est la seule chose qui rend le nettoyage fiable (issue
            # #249) — un `taskkill` tenté plus tard, depuis le `finally`,
            # arrive systématiquement trop tard (PID déjà mort et réapé).
            job_windows = _preparer_job_windows(proc.pid)
        elif verrou is not None:
            # Issue #322 : pgid == pid de claude (start_new_session=True) —
            # consigné dans le verrou dès que connu, pour qu'un watcher suivant
            # puisse cibler cet orphelin précis si CE watcher meurt brutalement
            # avant la fin du traitement (voir _nettoyer_orphelin_verrou_perime).
            _maj_verrou_pgid(verrou, proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            if proc.returncode == 0:
                return True, stdout.strip()
            else:
                stderr_propre = stderr.strip()
                extrait = _extrait_stderr(stderr_propre)
                if extrait:
                    log.warning(
                        f"  claude a échoué (code {proc.returncode}) pour issue "
                        f"#{numero} — stderr : {extrait}"
                    )
                else:
                    log.warning(
                        f"  claude a échoué (code {proc.returncode}) pour issue "
                        f"#{numero} — stderr vide."
                    )
                return False, stderr_propre or "Erreur inconnue"
        except subprocess.TimeoutExpired:
            return False, f"Timeout après {timeout}s"
    except FileNotFoundError:
        return False, "Claude Code introuvable (claude non trouvé dans PATH)"
    except Exception as e:
        return False, str(e)
    finally:
        if proc is not None:
            _nettoyer_arbre_claude(proc, job_windows)


def diagnostiquer_echec(numero: int, titre: str, body: str,
                        derniere_erreur: str,
                        perimetre: str = None,
                        cwd: Path = None) -> str | None:
    """Passe diagnostique courte et en LECTURE SEULE, lancée juste avant de poser
    'needs-human' sur une issue non critique abandonnée (issue #124).

    But : donner à Alain quelques pistes concrètes sur la cause du timeout / de
    l'échec répété, sans qu'il ait à ouvrir lui-même une session Claude Code pour
    un diagnostic qui tient souvent en quelques dizaines de secondes de lecture.

    Ne tente JAMAIS de résoudre la tâche : mode=MODE_LECTURE (lecture seule,
    même si l'issue d'origine était en mode écriture ou lecture active) et
    prompt dédié qui demande explicitement de ne PAS corriger. Timeout court et
    fixe (CFG.timeout_diagnostic), indépendant du timeout de la tâche d'origine.

    Best-effort : retourne le texte du diagnostic, ou None si la passe elle-même
    échoue / timeout (l'appelant n'ajoute alors simplement aucune section). On ne
    boucle jamais dessus et on ne retente pas.

    perimetre / cwd : mêmes surcharges que lancer_claude (issue #125). Pour un
    projet à périmètre dynamique, le diagnostic doit lire dans REPO_CIBLE et y
    être lancé, pas dans le rep_travail figé du .conf (placeholder)."""
    perimetre_effectif = CFG.perimetre if perimetre is None else perimetre
    if perimetre_effectif:
        clause_perimetre = (
            f"\nPÉRIMÈTRE STRICT — tu ne dois lire que dans les répertoires "
            f"suivants : {perimetre_effectif}\n"
        )
    else:
        clause_perimetre = ""

    prompt = f"""Tu es l'agent Linux (CCL) du bridge inter-agents, projet « {CFG.nom} ».
Une tâche (GitHub Issue #{numero}) a échoué de façon répétée et va être confiée à
un humain. NE tente PAS de résoudre la tâche : n'écris aucun fichier, n'exécute
aucune commande modifiant l'état du système ou du dépôt.

Ton unique rôle est un diagnostic RAPIDE et en LECTURE SEULE. À partir du titre,
du corps de la tâche et de la dernière erreur ci-dessous, liste les 3 à 5 causes
LES PLUS PROBABLES de ce timeout / échec répété — par exemple : boucle infinie
suspectée, commande interactive qui attend une entrée, opération réseau/IO lente,
dépendance manquante, tâche simplement trop volumineuse pour le timeout configuré,
etc. Reste concret et bref.

TITRE : {titre}

BODY :
{body}

DERNIÈRE ERREUR : {derniere_erreur}
{clause_perimetre}
Réponds uniquement par une courte liste à puces (3 à 5 pistes) des causes les plus
probables, sans préambule ni conclusion, et sans tenter de corriger quoi que ce soit."""

    try:
        succes, sortie = lancer_claude(
            numero, titre, body, dry_run=False,
            mode=MODE_LECTURE,
            timeout=CFG.timeout_diagnostic,
            modele=CFG.modele_ccl,
            prompt_perso=prompt,
            perimetre=perimetre,
            cwd=cwd,
        )
    except Exception as e:
        log.warning(f"  Passe diagnostique #{numero} indisponible (exception : {e}).")
        return None

    if succes and sortie.strip():
        return sortie.strip()
    log.info(f"  Passe diagnostique #{numero} indisponible (échec/timeout) — abandon sans diagnostic.")
    return None

# ─── Traitement d'une issue ────────────────────────────────────────────────────

# Mémoire des issues en cours de traitement (évite les doublons)
issues_en_cours: set[int] = set()
# Verrou dédié (issue #433) : le pattern check-then-act (contient → ajouter)
# reposait implicitement sur le GIL de CPython plutôt que sur une garantie
# formelle. Chaque opération élémentaire (contient/ajouter/retirer) est
# désormais atomique via ce verrou — sans changer le comportement observable
# (la dédup inter-cycles réelle du mode_write parallélisé reste assurée par
# `_threads_ecriture` + `_verrou_threads_ecriture`, cf. commentaires plus bas).
_verrou_issues_en_cours = threading.Lock()


def _issues_en_cours_contient(numero: int) -> bool:
    with _verrou_issues_en_cours:
        return numero in issues_en_cours


def _issues_en_cours_ajouter(numero: int) -> None:
    with _verrou_issues_en_cours:
        issues_en_cours.add(numero)


def _issues_en_cours_retirer(numero: int) -> None:
    with _verrou_issues_en_cours:
        issues_en_cours.discard(numero)


# Issues mode_write bloquées en 'needs-human' (issue #576) : sous-ensemble de
# `issues_en_cours` qui n'ont PLUS de thread actif (l'échec est définitif,
# `_traiter_issue_synchrone` a déjà retourné) mais doivent malgré tout
# continuer à occuper une place de MAX_WRITE_PARALLELE tant qu'Alain n'a pas
# résolu le label manuellement — sans quoi la limite se dégonflerait toute
# seule dès que le thread en échec se termine. Peuplé UNIQUEMENT aux points
# d'abandon définitif qui peuvent survenir en mode_write (SOUS_DOSSIER refusé,
# abandon après épuisement des tentatives, bootstrap CREATION échoué) ; les
# autres échecs définitifs (garde-fou lecture active, REPO_CIBLE) ne
# concernent jamais le
# mode écriture parallélisé et n'y sont donc jamais ajoutés. Verrou partagé
# avec `issues_en_cours` : mêmes garanties d'atomicité, pas de raison d'en
# introduire un second.
_issues_write_bloquees_needs_human: set[int] = set()


def _issue_write_bloquee_ajouter(numero: int) -> None:
    with _verrou_issues_en_cours:
        _issues_write_bloquees_needs_human.add(numero)


def _issue_write_bloquee_retirer(numero: int) -> None:
    with _verrou_issues_en_cours:
        _issues_write_bloquees_needs_human.discard(numero)


def _nb_issues_write_bloquees() -> int:
    with _verrou_issues_en_cours:
        return len(_issues_write_bloquees_needs_human)


def _reconcilier_issues_en_cours_fermees(issues: list[dict]) -> None:
    """Libère les places occupées par des issues fermées MANUELLEMENT sur
    GitHub pendant qu'elles étaient bloquées en needs-human (issue #576, cas
    3 de la tâche demandée) — le seul cas où le retrait du label ne suffit
    pas à détecter la levée : `lister_issues()` ne renvoie que les issues
    OUVERTES (`--state open`), donc une issue fermée disparaît purement et
    simplement de `issues` sans jamais repasser par la relecture de labels
    faite dans `traiter_issue()` (qui suppose l'issue toujours présente dans
    la liste). Appelée UNE fois par cycle, juste après `lister_issues()`, sur
    la liste fraîche complète.

    Ne touche PAS aux issues avec un thread mode_write encore actif (#337) :
    une fermeture manuelle pendant qu'un thread tourne encore ne doit pas
    interrompre ce thread ni fausser son propre nettoyage en fin de
    traitement — le thread se charge lui-même de sa place le moment venu."""
    numeros_ouverts = {i["number"] for i in issues}
    actifs_threads  = {t["numero"] for t in _threads_ecriture_actifs()}
    with _verrou_issues_en_cours:
        suivies = set(issues_en_cours)
    for numero in suivies:
        if numero in numeros_ouverts or numero in actifs_threads:
            continue
        log.info(
            f"  Issue #{numero} : disparue des issues ouvertes (fermeture manuelle "
            f"probable pendant needs-human) — place libérée (issue #576)."
        )
        _issues_en_cours_retirer(numero)
        _issue_write_bloquee_retirer(numero)


# ─── Parallélisation mode_write via git worktrees (issue #337) ─────────────────
# But : permettre à plusieurs issues mode_write de tourner EN PARALLÈLE, chacune
# dans son propre worktree git (répertoire frère isolé, sur sa propre branche),
# sans conflit d'accès fichier — au lieu du traitement strictement séquentiel
# historique (un seul mode_write à la fois, dans REP_TRAVAIL).
#
# `_threads_ecriture` : liste thread-safe (protégée par `_verrou_threads_ecriture`,
# un `threading.Lock` — SANS RAPPORT avec les verrous FICHIER inter-process de
# #189/#322, cf. `acquerir_verrou`) des tâches mode_write actuellement dispatchées
# dans un thread Python. Chaque entrée : {"numero", "worktree" (None si la tâche
# tourne dans REP_TRAVAIL, cf. décision ci-dessous), "thread"}.
#
# Décision de parallélisation (voir `traiter_issue`, point d'entrée public) :
# à `MAX_WRITE_PARALLELE > 1`, TOUTE tâche mode_write d'un lot — y compris la
# PREMIÈRE — est dispatchée dans un thread ciblant un worktree dédié
# (issue #611 : l'ancienne exception qui ciblait REP_TRAVAIL pour le premier
# slot, `worktree=None`, laissait ce premier slot sans isolation — un
# redémarrage du watcher pendant son exécution tuait le processus CCL et
# laissait du travail inachevé mélangé dans REP_TRAVAIL, cf. relecture_bridge
# #73). `_creer_worktree_avec_retries` tente plusieurs noms alternatifs
# (suffixes `-bis`, `-ter`) avant d'abandonner ; ce n'est qu'en tout dernier
# recours, si AUCUNE tentative n'aboutit, que le thread cible REP_TRAVAIL
# (worktree=None) — repli signalé activement (notify-send + log.warning +
# mention dans le compte-rendu de clôture), pas un chemin normal.
#
# `MAX_WRITE_PARALLELE <= 1` désactive la parallélisation ENTRE tâches
# (aucun thread, une seule tâche mode_write à la fois, traitée directement
# dans le thread principal — comportement séquentiel historique) mais PAS
# l'isolation vis-à-vis de REP_TRAVAIL (issue #577) : la tâche reçoit malgré
# tout un worktree dédié, obtenu via `_creer_worktree_avec_retries` puis
# passé directement à `_traiter_issue_synchrone` sans thread. Alain doit
# pouvoir manipuler REP_TRAVAIL (commit, stash, navigation) à tout moment, y
# compris pendant qu'une unique tâche mode_write est en cours, sans jamais
# entrer en collision avec elle.
_verrou_threads_ecriture = threading.Lock()
_threads_ecriture: list[dict] = []


def _nettoyer_threads_ecriture_termines() -> None:
    """Purge, sous verrou, les entrées dont le thread Python est terminé."""
    with _verrou_threads_ecriture:
        _threads_ecriture[:] = [t for t in _threads_ecriture if t["thread"].is_alive()]


def _threads_ecriture_actifs() -> list[dict]:
    """Instantané des tâches mode_write actuellement en thread, APRÈS purge
    des threads terminés. Best-effort de lecture cohérente : le nettoyage et
    la copie sont deux opérations séparées (léger risque qu'un thread se
    termine entre les deux, sans conséquence — juste une entrée fantôme lue
    une fois, purgée au prochain appel)."""
    _nettoyer_threads_ecriture_termines()
    with _verrou_threads_ecriture:
        return list(_threads_ecriture)


def _nb_threads_ecriture_actifs() -> int:
    return len(_threads_ecriture_actifs())


def _chemin_worktree(numero: int, suffixe: str = "") -> Path:
    """Chemin du worktree d'une issue mode_write (issue #337) : répertoire
    FRÈRE de REP_TRAVAIL, nommé d'après le NOM du projet (CFG.nom, pas le nom
    du dossier REP_TRAVAIL — ce sont deux choses potentiellement différentes).

    `suffixe` (issue #611) : `-bis`/`-ter`, utilisé par
    `_creer_worktree_avec_retries` pour les tentatives alternatives quand le
    chemin/la branche standard est déjà pris (reliquat non nettoyé)."""
    return CFG.rep_travail.parent / f"{CFG.nom}-issue{numero}{suffixe}"


def _branche_worktree(numero: int, suffixe: str = "") -> str:
    return f"worktree-issue-{numero}{suffixe}"


def _creer_worktree(numero: int, suffixe: str = "") -> tuple[Path | None, str | None]:
    """Crée le worktree git dédié à l'issue mode_write `numero` (issue #337) :
    `git -C <REP_TRAVAIL> worktree add <chemin> -b worktree-issue-<numero>`.
    `suffixe` (issue #611) : voir `_chemin_worktree` — nom alternatif tenté
    par `_creer_worktree_avec_retries`, qui est l'appelant normal côté
    `traiter_issue` (cette fonction reste appelable directement, suffixe="",
    pour les tests et cas d'appel unique).

    Garde-fous (échec propre, jamais d'exception propagée) : chemin déjà
    existant (vérifié AVANT l'appel git, évite une tentative vouée à
    l'échec), ou `git worktree add` en échec pour toute autre raison (branche
    déjà existante, etc.) — dans les deux cas, retourne (None, ...) et
    journalise ; l'appelant retombe alors sur le traitement séquentiel dans
    REP_TRAVAIL.

    Retourne un tuple `(chemin, raison_deja_pris)`. `raison_deja_pris`
    (issue #589) est une description courte, destinée au compte-rendu de
    clôture de l'issue, UNIQUEMENT quand l'échec est attribuable à un chemin
    ou une branche déjà pris (typiquement : un worktree laissé par une
    tentative précédente non nettoyée) — None dans tous les autres cas
    (succès, ou échec pour une raison différente que l'on ne veut pas
    présumer être un repli notable).

    Les deux vérifications « déjà pris » (chemin, branche) sont faites AVANT
    l'appel à `git worktree add`, plutôt qu'en essayant de reconnaître la
    cause dans le message d'erreur de `git` en cas d'échec : ce message est
    localisé (dépend de la langue du système), une détection par mots-clés y
    serait donc muette sur une machine non-anglophone (issue #589)."""
    chemin = _chemin_worktree(numero, suffixe)
    branche = _branche_worktree(numero, suffixe)
    if chemin.exists():
        raison = f"chemin {chemin} déjà pris par un worktree existant"
        log.warning(
            f"  Worktree #{numero}{suffixe} : {raison} "
            f"(issue #589 : probable reliquat d'une tentative précédente non "
            f"nettoyée — nettoyage TOUJOURS manuel, cf. WORKTREES.md)."
        )
        return None, raison
    verif_branche = subprocess.run(
        ["git", "-C", str(CFG.rep_travail), "rev-parse", "--verify", "--quiet", f"refs/heads/{branche}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
    )
    if verif_branche.returncode == 0:
        raison = f"branche '{branche}' déjà prise (chemin {chemin} libre, mais branche existante)"
        log.warning(
            f"  Worktree #{numero}{suffixe} : {raison} "
            f"(issue #589 : probable reliquat d'une tentative précédente non "
            f"nettoyée — nettoyage TOUJOURS manuel, cf. WORKTREES.md)."
        )
        return None, raison
    try:
        res = subprocess.run(
            ["git", "-C", str(CFG.rep_travail), "worktree", "add", str(chemin), "-b", branche],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        log.warning(f"  Worktree #{numero}{suffixe} : exception à la création ({e}).")
        return None, None
    if res.returncode != 0:
        # Erreur git générique (chemin et branche libres au moment des
        # vérifications ci-dessus, mais `git worktree add` a quand même
        # échoué) — pas de raison_deja_pris : distinct du cas #589.
        log.warning(
            f"  Worktree #{numero}{suffixe} : échec de création — {res.stderr.strip()}."
        )
        return None, None
    log.info(f"  Worktree #{numero}{suffixe} créé : {chemin} (branche {branche}).")
    return chemin, None


def _creer_worktree_avec_retries(numero: int) -> tuple[Path | None, str | None]:
    """Enveloppe `_creer_worktree` avec plusieurs tentatives sous noms
    alternatifs (issue #611) : couvre le cas le plus fréquent d'échec — un
    worktree orphelin non nettoyé qui occupe déjà le chemin/la branche
    standard — sans jamais introduire de worktree permanent partagé.

    Tentatives : `""` (nom standard `<projet>-issue<numero>`), puis `-bis`,
    puis `-ter`, dans cet ordre, MAIS seulement tant que l'échec précédent est
    attribuable à un chemin/branche déjà pris (`raison` renseignée) — une
    erreur git générique (raison=None) n'a aucune chance d'être résolue par un
    simple changement de nom, retenter serait donc inutile : on s'arrête
    immédiatement dans ce cas.

    Retourne `(chemin, None)` dès la première réussite, ou `(None, raison)`
    (raison de la DERNIÈRE tentative) si toutes échouent — charge à
    l'appelant de décider du repli (REP_TRAVAIL en tout dernier recours,
    signalé activement)."""
    raison = None
    for suffixe in ("", "-bis", "-ter"):
        chemin, raison = _creer_worktree(numero, suffixe)
        if chemin is not None:
            return chemin, None
        if raison is None:
            break
    return None, raison


def _signaler_repli_worktree_echoue(numero: int, raison: str | None) -> None:
    """Signalement actif (issue #611) du repli en tout dernier recours dans
    REP_TRAVAIL, quand `_creer_worktree_avec_retries` a épuisé toutes ses
    tentatives pour l'issue mode_write `numero`. Le repli lui-même n'est PAS
    modifié par cette fonction (toujours propre, jamais d'exception) — appelée
    par `traiter_issue` juste avant de l'effectuer, sur trois canaux :
    notify-send immédiat (bulle bureau Linux, instantané et visible si Alain
    est présent, contrairement à ntfy qui peut accuser un délai), un
    log.warning explicite avec le chemin, et une mention dans le compte-rendu
    de clôture de l'issue (assurée séparément par l'appelant, via
    `echec_worktree_deja_pris` transmis à `_traiter_issue_synchrone` —
    mécanisme déjà en place depuis #589)."""
    log.warning(
        f"  Issue #{numero} : AUCUNE tentative de création de worktree n'a abouti "
        f"({raison}) — repli en tout dernier recours dans REP_TRAVAIL "
        f"({CFG.rep_travail}), issue #611."
    )
    notifier_bureau(
        f"Bridge {CFG.nom} — repli worktree #{numero}",
        f"Toutes les tentatives de création de worktree ont échoué pour l'issue #{numero} "
        f"({raison}) — traitement en dernier recours dans REP_TRAVAIL ({CFG.rep_travail}).",
        urgence="critical",
    )


def _chemin_verrou(rep_travail: Path) -> Path:
    """Chemin du fichier de verrou associé à un répertoire de travail donné.

    La clé est le chemin RÉSOLU du rep_travail : deux instances de watcher visant
    le même dossier (même via deux .conf différents, ou une relance) obtiennent
    le MÊME verrou, donc s'excluent mutuellement. Le nom garde un préfixe lisible
    (basename du dossier) suivi d'une empreinte du chemin complet pour rester
    unique et débuggable. Le fichier vit sous DOSSIER_VERROUS (logs/, gitignoré),
    jamais dans rep_travail (cf. commentaire de DOSSIER_VERROUS)."""
    resolu = rep_travail.expanduser().resolve()
    empreinte = hashlib.sha1(str(resolu).encode("utf-8")).hexdigest()[:12]
    return DOSSIER_VERROUS / f"{resolu.name or 'racine'}-{empreinte}.lock"


def _lire_pgid_verrou(verrou: Path) -> int | None:
    """Lit le champ `claude_pgid=<n>` du fichier verrou (issue #322), s'il est
    présent. Retourne None si absent — ancien format, ou verrou posé mais
    claude pas encore lancé au moment où le watcher précédent est mort — ou si
    la lecture échoue. Dans tous ces cas, l'appelant doit se comporter comme
    avant cette issue : reprendre le verrou sans tenter de tuer personne."""
    try:
        contenu = verrou.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    trouve = re.search(r"claude_pgid=(\d+)", contenu)
    if not trouve:
        return None
    try:
        return int(trouve.group(1))
    except ValueError:
        return None


def _maj_verrou_pgid(verrou: Path, pgid: int) -> None:
    """Complète le fichier verrou avec le PGID du claude tout juste lancé
    (issue #322), appelée juste après un Popen réussi — POSIX, pgid == pid du
    claude grâce à start_new_session, voir lancer_claude. Nécessaire car le
    verrou est posé par acquerir_verrou AVANT le lancement de claude (voir
    traiter_issue) : le pgid n'est donc pas encore connu à la pose. Préserve
    les champs existants (pid=.../projet=.../rep=...) et ajoute
    `claude_pgid=<n>` en conservant le format clé=valeur.

    Best-effort pur : ne doit jamais faire échouer lancer_claude ni le
    traitement de l'issue — une erreur ici laisse simplement le verrou sans
    pgid, traité comme l'ancien format par _lire_pgid_verrou."""
    try:
        contenu = verrou.read_text(encoding="utf-8", errors="replace").rstrip("\n")
        verrou.write_text(f"{contenu} claude_pgid={pgid}\n", encoding="utf-8")
    except OSError as e:
        log.warning(f"Mise à jour du verrou {verrou} avec le pgid claude ({pgid}) impossible : {e}")


def _lire_pid_verrou(verrou: Path) -> int | None:
    """Lit le champ `pid=<n>` du fichier verrou — le PID du watcher qui l'a
    posé (voir acquerir_verrou), écrit inconditionnellement dès la création du
    verrou, contrairement à `claude_pgid` qui n'arrive qu'après le Popen
    (voir _maj_verrou_pgid). Retourne None si absent ou lecture impossible."""
    try:
        contenu = verrou.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    trouve = re.search(r"pid=(\d+)", contenu)
    if not trouve:
        return None
    try:
        return int(trouve.group(1))
    except ValueError:
        return None


def _pid_vivant(pid: int | None) -> bool:
    """Sonde best-effort et cross-plateforme (issue #584) : `pid` désigne-t-il
    encore un process vivant ? Pure lecture, ne tue ni ne modifie rien.
    POSIX : os.kill(pid, 0). Windows : OpenProcess en droits minimaux (mêmes
    constantes que _assigner_job_windows, adaptées en lecture seule).

    Asymétrie volontaire, cruciale pour l'usage qu'en fait acquerir_verrou :
    PID introuvable ⇒ False, fait certain (aucun faux négatif possible — un
    PID qui n'existe plus n'existe plus). PID trouvé vivant, sonde en échec,
    ou plateforme non gérée ⇒ True par prudence : un PID mort peut avoir été
    RECYCLÉ par l'OS pour un process totalement différent (surtout après un
    temps long ou un redémarrage), donc « vivant » ne prouve jamais qu'il
    s'agit encore du MÊME process — dans le doute, l'appelant doit retomber
    sur le filet de sécurité existant (verrou encore considéré actif), jamais
    conclure à tort qu'il est orphelin."""
    if not pid or pid <= 0:
        return False
    try:
        if os.name == "nt":
            handle = ctypes.windll.kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return True


def _nettoyer_orphelin_verrou_perime(verrou: Path) -> None:
    """Best-effort (issue #322) — au moment précis où acquerir_verrou reprend un
    verrou PÉRIMÉ, tue l'éventuel claude orphelin encore attaché à ce verrou
    AVANT de le libérer.

    Contexte : un verrou périmé signale un watcher mort BRUTALEMENT (kill -9,
    coupure de courant, plantage Python non capturé) pendant qu'un claude
    tournait — aucun `finally` n'a pu s'exécuter, ni _nettoyer_arbre_claude ni
    liberer_verrou. Sans ce nettoyage, reprendre le verrou lancerait un
    nouveau claude dans le même rep_travail pendant que l'orphelin y écrit
    encore : conflit de fichiers possible — le périmètre empêche de SORTIR du
    dossier, pas deux process d'y entrer en collision.

    Garde-fou anti-reboot (impératif) : après un redémarrage, les PID/pgid
    sont réattribués — le pgid stocké pourrait désigner un process totalement
    différent. On ne tue JAMAIS sur la seule foi du pgid stocké : il faut en
    plus qu'un process de ce pgid existe ENCORE (_lister_processus_pgid) et
    que sa ligne de commande contienne "claude" — identifier par ce que le
    process EST, jamais tuer aveuglément, même esprit que _nettoyer_arbre_claude
    (#247 point 4). Si l'une des conditions manque (pas de pgid stocké,
    process disparu, ou pas un claude), rien n'est tué et le verrou est repris
    normalement, comme avant cette issue.

    POSIX uniquement : os.killpg n'existe pas sous Windows (objet Job, pas de
    pgid — la question ne se pose pas dans les mêmes termes). L'appelant ne
    doit invoquer cette fonction que sous POSIX (garde os.name).

    Enveloppée dans un garde-fou total : _lister_processus_pgid peut lever une
    OSError, os.killpg une PermissionError — aucune ne doit remonter et faire
    échouer l'acquisition du verrou ni le traitement de l'issue."""
    try:
        pgid = _lire_pgid_verrou(verrou)
        if pgid is None:
            return
        processus = _lister_processus_pgid(pgid)
        processus_claude = [(pid, cmdline) for pid, cmdline in processus if "claude" in cmdline.lower()]
        if not processus_claude:
            return   # pgid mort ou recyclé (reboot), ou vivant mais pas un claude : on ne touche à rien
        for pid_orphelin, cmdline in processus_claude:
            log.warning(
                f"Orphelin d'un watcher mort brutalement, nettoyé à la reprise "
                f"du verrou périmé {verrou} : PID {pid_orphelin} (pgid {pgid}) — {cmdline}"
            )
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            return  # déjà mort entre l'énumération et le kill : rien à faire
        except PermissionError as e:
            log.warning(f"os.killpg refusé pour l'orphelin du verrou périmé {verrou} (pgid {pgid}) : {e}")
            return
        fin = time.monotonic() + 5
        while time.monotonic() < fin and _lister_processus_pgid(pgid):
            time.sleep(0.1)
    except Exception as e:
        log.warning(
            f"Nettoyage de l'orphelin du verrou périmé {verrou} a levé une "
            f"exception inattendue et a été abandonné : {e}"
        )


def acquerir_verrou(rep_travail: Path, timeout_projet: int, mode: str = "") -> Path | None:
    """Tente de poser un verrou exclusif sur `rep_travail`. Retourne le chemin du
    verrou si acquis, ou None si un AUTRE traitement le détient déjà (verrou
    vivant) — l'appelant doit alors s'abstenir de lancer claude.

    `mode` (issue #609) : consigné dans le verrou (champ `mode=`) en plus de
    `pid=`/`projet=`/`rep=` — permet à taches_en_cours() ci-dessous, et donc à
    new_issue.py (process séparé, qui n'a pas accès à `issues_en_cours` en
    mémoire), de savoir si la tâche en cours pour un projet est un mode_write
    tournant directement dans REP_TRAVAIL plutôt que dans un worktree isolé
    (repli #589) — l'information que new_issue.py doit signaler visiblement.

    Un verrou plus vieux que la durée de traitement plausible d'une issue est
    considéré comme PÉRIMÉ (orphelin d'un watcher tué sans passer par le finally)
    et repris. La borne tient compte des tentatives multiples : au pire un
    traitement légitime dure max_essais × (timeout + pause) ; au-delà (+ marge),
    plus aucun claude légitime ne tourne.

    Filet complémentaire (issue #584) : un verrou encore JEUNE au sens de cette
    péremption par ancienneté peut malgré tout être orphelin — watcher tué
    brutalement (crash, kill -9, redémarrage de service) alors qu'il détenait
    le verrou, sur un projet dont TIMEOUT est élevé (la péremption ci-dessus
    est calculée à partir de max_essais × timeout_projet, potentiellement des
    dizaines de minutes). Sans ce filet, tout autre traitement visant le même
    rep_travail reste bloqué jusqu'à l'écoulement complet de ce délai — vécu
    sur l'issue #583 (canal unifié for-windows, 48 minutes de blocage). Le PID
    du watcher propriétaire (champ `pid=`, écrit inconditionnellement à la
    pose, voir plus bas) est sondé via `_pid_vivant` : s'il est confirmé mort,
    le verrou est repris IMMÉDIATEMENT, sans attendre la péremption par
    ancienneté. Cette sonde ne peut jamais rendre un verrou encore valide plus
    fragile qu'avant (voir l'asymétrie volontaire documentée sur _pid_vivant).

    Création atomique via O_CREAT|O_EXCL : si un autre process gagne la course
    entre le test de péremption et la création, l'ouverture échoue proprement et
    on renvoie None (pas de double lancement).

    Best-effort sur les erreurs d'E/S annexes : si le dossier de verrous ne peut
    être créé ou le fichier posé (permissions…), on journalise et on renvoie le
    chemin quand même plutôt que de bloquer indéfiniment le traitement — la
    protection en mémoire (issues_en_cours) reste active dans ce cas dégradé."""
    verrou = _chemin_verrou(rep_travail)
    try:
        DOSSIER_VERROUS.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning(f"Dossier de verrous {DOSSIER_VERROUS} incréable ({e}) — verrou désactivé pour cette issue.")
        return verrou   # dégradé : on poursuit, issues_en_cours protège encore dans ce process

    peremption = CFG.max_essais * (timeout_projet + PAUSE_ENTRE_TENTATIVES) + PEREMPTION_MARGE_VERROU

    if verrou.exists():
        try:
            age = time.time() - verrou.stat().st_mtime
        except OSError:
            age = None
        perime_par_age = age is not None and age >= peremption

        # Issue #584 : la péremption par ancienneté n'a pas encore tranché —
        # dernier recours avant de considérer le verrou vivant, sonder si le
        # watcher propriétaire existe encore.
        pid_proprietaire = None
        perime_par_pid_mort = False
        if not perime_par_age:
            pid_proprietaire = _lire_pid_verrou(verrou)
            if pid_proprietaire is not None and not _pid_vivant(pid_proprietaire):
                perime_par_pid_mort = True

        if not perime_par_age and not perime_par_pid_mort:
            return None   # verrou vivant : un autre traitement est en cours sur ce dossier

        if perime_par_pid_mort:
            log.warning(
                f"Verrou orphelin sur {rep_travail} : le watcher propriétaire "
                f"(PID {pid_proprietaire}) n'existe plus — repris immédiatement, "
                f"sans attendre la péremption par ancienneté (âge "
                f"{int(age) if age is not None else '?'}s < {int(peremption)}s, issue #584)."
            )
        else:
            # Verrou périmé par ancienneté (ou stat illisible) : on le reprend.
            log.warning(
                f"Verrou périmé sur {rep_travail} "
                f"(âge {int(age) if age is not None else '?'}s ≥ {int(peremption)}s) — repris "
                f"(watcher précédent probablement tué avant libération)."
            )
        # Issue #322 : avant de reprendre ce verrou périmé, nettoyer l'éventuel
        # claude orphelin d'un watcher mort brutalement (kill -9, coupure,
        # plantage non capturé) — sinon un nouveau claude serait lancé pendant
        # que l'orphelin écrit encore dans le même rep_travail. POSIX
        # uniquement (os.killpg absent sous Windows) ; best-effort strict, ne
        # doit jamais empêcher la reprise du verrou (voir
        # _nettoyer_orphelin_verrou_perime).
        if os.name != "nt":
            _nettoyer_orphelin_verrou_perime(verrou)
        try:
            verrou.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            log.warning(f"Suppression du verrou périmé {verrou} impossible ({e}).")

    try:
        fd = os.open(str(verrou), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        return None   # course perdue : un autre process vient de poser le verrou
    except OSError as e:
        log.warning(f"Pose du verrou {verrou} impossible ({e}) — on poursuit sans verrou fichier.")
        return verrou   # dégradé, comme ci-dessus
    try:
        # `rep=` reste en DERNIÈRE position (avant #609 comme après) : c'est le
        # seul champ dont la valeur (un chemin) pourrait en théorie contenir un
        # caractère imprévu — le garder en fin de ligne évite de perturber le
        # parsing par regex des champs mode/projet/pid qui le précèdent.
        os.write(fd, f"pid={os.getpid()} projet={CFG.nom} mode={mode} rep={rep_travail}\n".encode("utf-8"))
    finally:
        os.close(fd)
    return verrou


def liberer_verrou(verrou: Path | None):
    """Supprime le fichier de verrou (best-effort). Appelée dans un finally pour
    garantir la libération même en cas d'échec/exception du traitement."""
    if not verrou:
        return
    try:
        verrou.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning(f"Libération du verrou {verrou} impossible ({e}).")


def taches_en_cours(nom_projet: str) -> list[dict]:
    """Tâches actuellement en traitement pour `nom_projet`, déterminées via les
    verrous fichier actifs sous DOSSIER_VERROUS (issue #609). Point d'entrée
    PUBLIC pour app/watchers.py (process new_issue.py, séparé du process
    watcher qui traite réellement les issues) : `issues_en_cours`, en mémoire,
    n'est visible que dans le process watcher lui-même — ce garde-fou fichier
    (déjà posé par acquerir_verrou pour TOUTE issue, quel que soit le mode,
    cf. #189) comble ce manque sans nouveau mécanisme dédié.

    Un verrou dont le pid propriétaire (le watcher qui l'a posé, champ `pid=`)
    n'est plus vivant est ignoré : verrou périmé (watcher mort brutalement),
    pas une tâche active — même sonde (_pid_vivant) que acquerir_verrou.

    Retourne une liste de dict {"rep": str, "mode": str} — une entrée par
    verrou actif de ce projet (plusieurs si MAX_WRITE_PARALLELE > 1), vide si
    aucune tâche en cours."""
    resultat = []
    if not DOSSIER_VERROUS.is_dir():
        return resultat
    for verrou in DOSSIER_VERROUS.glob("*.lock"):
        try:
            contenu = verrou.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        champs = dict(re.findall(r"(\w+)=(\S*)", contenu))
        if champs.get("projet") != nom_projet:
            continue
        pid = champs.get("pid")
        try:
            vivant = pid is not None and _pid_vivant(int(pid))
        except ValueError:
            vivant = False
        if not vivant:
            continue
        resultat.append({"rep": champs.get("rep", ""), "mode": champs.get("mode", "")})
    return resultat


def _empreinte_configs() -> dict[str, bytes]:
    """Instantané intégral de configs/*.conf (issue #318), pris juste avant un
    traitement en mode_write. Sert de base à `_restaurer_configs_modifies` pour
    détecter ET annuler toute modification de ce dossier par CCL/CCW — ces
    fichiers (PERIMETRE, TOPIC_NTFY, FICHIER_CONTEXTE, ...) ne sont modifiables
    qu'à la main par Alain (ou via l'onglet Configuration de new_issue.py),
    jamais par une issue, cf. consignes/globales.md. `configs/` est commun à
    TOUS les projets (partagé par ce watcher.py, cf. DOSSIER_SCRIPT) : cette
    empreinte protège donc l'ensemble du dossier, pas seulement le `.conf` du
    projet courant."""
    dossier = DOSSIER_SCRIPT / "configs"
    empreinte = {}
    if dossier.is_dir():
        for chemin in dossier.glob("*.conf"):
            try:
                empreinte[chemin.name] = chemin.read_bytes()
            except OSError:
                pass
    return empreinte


def _detecter_demande_modif_configs(body: str) -> bool:
    """Détection best-effort (issue #318), purement informative : le corps de
    l'issue mentionne-t-il un chemin `configs/*.conf` ? Ne bloque rien —
    l'interdiction réelle vient de la consigne `globales.md` (CCL doit refuser
    lui-même) et de `_restaurer_configs_modifies` (garde-fou technique après
    coup) ; ce simple repérage sert seulement à journaliser un avertissement
    précoce, avant même le lancement de claude."""
    return bool(re.search(r"configs[/\\][\w.-]*\.conf", body or "", re.IGNORECASE))


def _restaurer_configs_modifies(numero: int, empreinte_avant: dict[str, bytes]) -> None:
    """Garde-fou technique (issue #318) : après une exécution mode_write,
    compare configs/*.conf à l'instantané pris juste avant (`_empreinte_configs`)
    et annule toute modification, création ou suppression détectée — fichier
    par fichier, en journalisant un WARNING explicite — sans jamais faire
    échouer le reste du traitement de l'issue (best-effort, aucune exception
    propagée). Seul Alain modifie ces fichiers, à la main."""
    dossier = DOSSIER_SCRIPT / "configs"
    if not dossier.is_dir():
        return
    noms_apres = set()
    try:
        fichiers_apres = list(dossier.glob("*.conf"))
    except OSError:
        fichiers_apres = []
    for chemin in fichiers_apres:
        noms_apres.add(chemin.name)
        contenu_avant = empreinte_avant.get(chemin.name)
        try:
            contenu_apres = chemin.read_bytes()
        except OSError:
            continue
        if contenu_avant is None:
            log.warning(
                f"  ⚠️  Issue #{numero} : nouveau fichier 'configs/{chemin.name}' détecté "
                f"après un traitement mode_write — modification de configs/*.conf interdite "
                f"(consignes/globales.md, issue #318), suppression automatique."
            )
            try:
                chemin.unlink()
            except OSError as e:
                log.error(f"  Suppression de configs/{chemin.name} impossible : {e}")
        elif contenu_apres != contenu_avant:
            log.warning(
                f"  ⚠️  Issue #{numero} : modification de 'configs/{chemin.name}' détectée "
                f"après un traitement mode_write — interdite (consignes/globales.md, issue "
                f"#318), restauration automatique de la version d'avant exécution."
            )
            try:
                chemin.write_bytes(contenu_avant)
            except OSError as e:
                log.error(f"  Restauration de configs/{chemin.name} impossible : {e}")
    for nom, contenu_avant in empreinte_avant.items():
        if nom in noms_apres:
            continue
        log.warning(
            f"  ⚠️  Issue #{numero} : suppression de 'configs/{nom}' détectée après un "
            f"traitement mode_write — interdite (consignes/globales.md, issue #318), "
            f"restauration automatique."
        )
        try:
            (dossier / nom).write_bytes(contenu_avant)
        except OSError as e:
            log.error(f"  Restauration de configs/{nom} impossible : {e}")


# ─── Lecture active : scratch confiné (issue #327) ──────────────────────────────

# Nom de projet valide pour dériver un chemin scratch (voir _chemin_scratch) :
# alphanumérique/tiret/underscore uniquement — exclut par construction tout
# séparateur de chemin et tout '..', donc toute remontée hors de /tmp.
_NOM_PROJET_SCRATCH_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _chemin_scratch(nom_projet: str) -> Path:
    """Chemin du dossier scratch de lecture active (issue #327) :
    /tmp/bridge_scratch_<projet>/. Dérivé STRICTEMENT de CFG.nom (jamais d'une
    valeur fournie par l'issue — la lecture active n'accepte aucun chemin
    arbitraire) et validé strictement : lève ValueError si `nom_projet` est
    vide ou contient autre chose qu'alphanumérique/tiret/underscore (défense en
    profondeur — CFG.nom vient normalement d'un fichier .conf de confiance,
    jamais de l'issue, mais on ne présume rien)."""
    if not nom_projet or not _NOM_PROJET_SCRATCH_RE.match(nom_projet):
        raise ValueError(f"nom de projet invalide pour le chemin scratch : {nom_projet!r}")
    return Path(tempfile.gettempdir()) / f"bridge_scratch_{nom_projet}"


def _nettoyer_scratch(numero: int, chemin: Path) -> None:
    """Supprime le dossier scratch de lecture active (issue #327) en fin de
    traitement — appelée depuis le `finally` de traiter_issue, donc couvre
    indifféremment succès, échec et timeout (même esprit que
    _nettoyer_arbre_claude pour les process). Best-effort : ne lève jamais, une
    erreur ici ne doit pas faire échouer le reste du traitement de l'issue."""
    try:
        if chemin.is_dir():
            shutil.rmtree(chemin, ignore_errors=True)
    except Exception as e:
        log.warning(f"  Nettoyage du dossier scratch {chemin} (issue #{numero}) impossible : {e}")


def _statut_git_rep_travail(cwd: Path) -> dict[str, str] | None:
    """Instantané de l'état git de REP_TRAVAIL sous forme {chemin: code}
    (garde-fou niveau 2, issue #327 — même esprit que _empreinte_configs #318 :
    une empreinte avant/après pour détecter toute écriture qui aurait échappé
    au confinement scratch). `-uall` : les fichiers neufs dans un dossier non
    suivi apparaissent un par un (pas comme une seule entrée « dossier/ ») —
    nécessaire pour restaurer précisément fichier par fichier. Retourne None si
    REP_TRAVAIL n'est pas (ou plus) un dépôt git exploitable — best-effort,
    n'interrompt jamais le traitement de l'issue."""
    if not _est_depot_git(cwd):
        return None
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=cwd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=30,
        )
        if res.returncode != 0:
            return None
    except (OSError, subprocess.SubprocessError):
        return None
    statut: dict[str, str] = {}
    for ligne in res.stdout.splitlines():
        if len(ligne) < 4:
            continue
        code, chemin = ligne[:2], ligne[3:]
        if code[0] == "R" and " -> " in chemin:
            chemin = chemin.split(" -> ", 1)[1]
        statut[chemin] = code
    return statut


def _restaurer_rep_travail_modifie(numero: int, cwd: Path,
                                    statut_avant: dict[str, str]) -> list[str]:
    """Garde-fou technique niveau 2 (issue #327, même esprit que
    _restaurer_configs_modifies #318) : après une exécution en lecture active,
    compare l'état git de REP_TRAVAIL à l'instantané pris juste avant
    (_statut_git_rep_travail) et annule toute écriture NOUVELLE détectée. Le
    dossier scratch (/tmp, hors REP_TRAVAIL) n'apparaît jamais dans cette
    empreinte par construction : il n'est donc jamais emporté par cette
    restauration. Retourne la liste des chemins restaurés (vide = rien
    détecté). Best-effort total : aucune exception ne s'échappe, ne bloque
    jamais le reste du traitement."""
    statut_apres = _statut_git_rep_travail(cwd)
    if statut_apres is None:
        return []
    nouveaux = {chemin: code for chemin, code in statut_apres.items()
                if statut_avant.get(chemin) != code}
    if not nouveaux:
        return []
    for chemin, code in nouveaux.items():
        log.warning(
            f"  ⚠️  Issue #{numero} : lecture active — écriture détectée hors "
            f"scratch dans REP_TRAVAIL : '{chemin}' ({code.strip()}) — "
            f"restauration automatique (garde-fou niveau 2, issue #327)."
        )
    try:
        # Fichiers neufs (untracked '?' ou staged-added 'A') : `git checkout`
        # ne les toucherait pas (rien à restaurer depuis HEAD) — on les
        # désindexe puis supprime. Fichiers déjà suivis (modifiés/supprimés) :
        # `git checkout` les ramène à leur contenu HEAD d'avant exécution.
        neufs     = [c for c, code in nouveaux.items() if code[0] in ("?", "A")]
        existants = [c for c in nouveaux if c not in neufs]
        if neufs:
            subprocess.run(["git", "reset", "--"] + neufs,
                            cwd=cwd, capture_output=True, text=True, timeout=30)
            subprocess.run(["git", "clean", "-fd", "--"] + neufs,
                            cwd=cwd, capture_output=True, text=True, timeout=30)
        if existants:
            subprocess.run(["git", "checkout", "--"] + existants,
                            cwd=cwd, capture_output=True, text=True, timeout=30)
    except Exception as e:
        log.error(f"  Restauration de REP_TRAVAIL (issue #{numero}) incomplète : {e}")
    return list(nouveaux.keys())


def _guards_precoces_et_bootstrap(issue: dict, numero: int, titre: str, body: str,
                                   dry_run: bool) -> list[str] | None:
    """Guards en tête de `_traiter_issue_synchrone` (déjà en cours, déjà en
    échec définitif needs-human, déjà traitée) puis bootstrap CCW (issue
    #556, 2/3). Retourne la liste des labels si le traitement doit continuer,
    ou None si l'appelant doit retourner immédiatement — guard déclenché ou
    bootstrap CCW déjà entièrement géré ici (side effects déjà appliqués)."""
    if _issues_en_cours_contient(numero):
        return None

    labels = [l.get("name", "") for l in issue.get("labels", [])]

    # Une issue déjà 'needs-human' a échoué définitivement : on ne la retraite
    # PAS (sinon boucle infinie) tant qu'un humain n'a pas retiré le label.
    # Suivie malgré tout dans issues_en_cours (issue #576) : occupe une place
    # tant que la place n'est pas explicitement libérée (retrait du label —
    # voir la réconciliation dans traiter_issue() et en tête de boucle
    # principale). Ce chemin couvre notamment la découverte d'une issue déjà
    # 'needs-human' au redémarrage du watcher (issues_en_cours reparti à vide).
    if LABEL_ECHEC in labels:
        log.debug(f"Issue #{numero} déjà marquée '{LABEL_ECHEC}' — ignorée (intervention humaine en attente).")
        _issues_en_cours_ajouter(numero)
        if _deduire_mode(labels) == MODE_ECRITURE:
            _issue_write_bloquee_ajouter(numero)
        return None

    # Garde d'idempotence (issue #195). Une issue peut revenir ici OUVERTE alors
    # que son travail est déjà fait : un cycle précédent avait réussi le
    # commentaire de résultat mais échoué la fermeture (coupure réseau entre
    # `comment` et `close`), ou posé le label `done` sans réussir le `close`. On
    # NE relance PAS claude à tort (double exécution d'une tâche d'écriture) : on
    # se contente de re-tenter la fermeture, puis on rend la main.
    if LABEL_FAIT in labels or resultat_deja_poste(numero):
        log.info(f"  Issue #{numero} déjà traitée (résultat commenté) — finalisation de la fermeture, pas de retraitement.")
        if not fermer_issue(numero):
            log.warning(f"  Finalisation de la fermeture #{numero} toujours incomplète — nouvelle tentative au prochain cycle.")
        return None

    _issues_en_cours_ajouter(numero)

    # Bootstrap automatique CCW (issue #556, 2/3) : entièrement déterministe,
    # détecté et traité AVANT tout lancement de claude — sans rapport avec le
    # pipeline habituel (mode, périmètre, verrou, lancer_claude). Sans objet
    # si le champ CREATION est absent/désactivé : dispatch normal inchangé.
    if creation_demandee(body):
        _traiter_creation_projet_ccw(numero, body, labels, dry_run)
        return None

    return labels


def _deduire_mode_et_logguer(numero: int, titre: str, body: str, labels: list[str],
                              chemin_worktree: Path | None) -> tuple[str, str, str, bool, int, str]:
    """Déduit priorité/critique/timeout/modèle/mode pour cette issue et
    journalise les avertissements associés (mode écriture ou lecture active
    armé, mention configs/*.conf dans le corps). Retourne
    (mode, mode_txt, priorite, critique, timeout, modele)."""
    priorite = extraire_priorite(body)
    critique = priorite in PRIORITES_CRITIQUES
    timeout  = extraire_timeout(body, titre)
    modele   = extraire_modele(body)

    mode = _deduire_mode(labels)

    mode_txt = {
        MODE_ECRITURE:       "ÉCRITURE ⚠️",
        MODE_LECTURE_ACTIVE: "LECTURE ACTIVE (scratch) ⚠️",
        MODE_LECTURE:        "lecture seule",
    }[mode]
    log.info(f"→ Issue #{numero} détectée : '{titre}' [priorité: {priorite}] [mode: {mode_txt}]")
    if mode == MODE_ECRITURE:
        log.warning(f"  ⚠️  MODE ÉCRITURE ARMÉ pour #{numero} (label '{LABEL_ECRITURE}') — actions permises, push interdit.")
        if chemin_worktree is not None:
            log.info(
                f"  Issue #{numero} : traitement en worktree isolé {chemin_worktree} "
                f"(branche {_branche_worktree(numero)}) — parallélisation mode_write, issue #337."
            )
    elif mode == MODE_LECTURE_ACTIVE:
        log.warning(
            f"  ⚠️  MODE LECTURE ACTIVE ARMÉ pour #{numero} (label '{LABEL_SCRATCH}') — "
            f"écriture confinée au scratch, projet protégé par garde-fou niveau 2 (issue #327)."
        )
    if mode != MODE_LECTURE and _detecter_demande_modif_configs(body):
        log.warning(
            f"  ⚠️  Issue #{numero} : le corps mentionne un chemin configs/*.conf — "
            f"rappel : CCL/CCW ne doit JAMAIS modifier ces fichiers (consignes/globales.md, "
            f"issue #318), même si l'issue le demande explicitement. Garde-fou technique actif."
        )
    return mode, mode_txt, priorite, critique, timeout, modele


@dataclass
class ContexteExecution:
    """Périmètre et cwd effectifs résolus pour une exécution de
    `_traiter_issue_synchrone` (issue #619), avec les avertissements à
    reporter dans le compte-rendu de clôture."""
    perimetre_effectif: str
    cwd_effectif: Path
    avertissement_conflit: str
    avertissement_worktree_deja_pris: str


def _resoudre_contexte_execution(numero: int, body: str, mode: str,
                                  chemin_worktree: Path | None,
                                  echec_worktree_deja_pris: str | None) -> ContexteExecution | None:
    """Périmètre effectif de cette exécution (issue #125). Par défaut : celui
    du .conf. Pour un projet à périmètre dynamique, il vient du champ
    REPO_CIBLE de l'issue et devient à la fois le périmètre de la clause de
    prompt ET le cwd réel du subprocess — sinon du worktree isolé (#337) ou
    de SOUS_DOSSIER (#550), même ordre de priorité qu'historiquement. Toute
    erreur de config/issue ici est définitive (pas de retry) : commentaire
    explicite + label 'needs-human' pour stopper la reprise, DÉJÀ posés avant
    de retourner None — l'appelant n'a plus qu'à retourner immédiatement."""
    perimetre_effectif = CFG.perimetre
    cwd_effectif       = CFG.rep_travail
    avertissement_conflit = ""

    # Repli silencieux sur REP_TRAVAIL (issue #589) : rendu visible dans le
    # compte-rendu de clôture, sur le même modèle qu'avertissement_conflit
    # ci-dessus — le repli lui-même n'est PAS modifié (toujours propre,
    # jamais d'exception), seulement signalé.
    avertissement_worktree_deja_pris = ""
    if echec_worktree_deja_pris:
        avertissement_worktree_deja_pris = (
            f"⚠️ Repli sur REP_TRAVAIL : le worktree dédié à cette issue n'a pas "
            f"pu être créé ({echec_worktree_deja_pris}). Comportement volontaire "
            f"(cf. BRIDGE_AGENT_DOC.md) — le travail ci-dessous a bien été fait "
            f"dans REP_TRAVAIL, mais un worktree orphelin est probablement resté "
            f"au chemin concerné. Nettoyage TOUJOURS manuel (jamais de `git "
            f"worktree remove` automatique) — cf. WORKTREES.md.\n\n"
        )

    # Worktree isolé (issue #337) : chemin_travail effectif de CETTE tâche —
    # remplace REP_TRAVAIL comme cwd du subprocess ET comme périmètre du
    # prompt (Claude tourne physiquement dans ce dossier frère, un périmètre
    # resté sur REP_TRAVAIL le bloquerait en pratique). Hors périmètre
    # dynamique uniquement (#125) : les deux mécanismes ne se combinent pas,
    # REPO_CIBLE reste seul décisif si les deux sont actifs par erreur.
    if chemin_worktree is not None and not CFG.perimetre_dynamique:
        cwd_effectif       = chemin_worktree
        perimetre_effectif = str(chemin_worktree)

    if CFG.perimetre_dynamique:
        repo_cible = extraire_repo_cible(body)
        if not repo_cible:
            log.error(f"  Issue #{numero} : PERIMETRE_DYNAMIQUE actif mais champ REPO_CIBLE absent — abandon (aucun repli).")
            commenter_issue(
                numero,
                f"❌ Échec de configuration — ce projet est en **périmètre dynamique** "
                f"(`PERIMETRE_DYNAMIQUE = true`) mais l'issue ne fournit pas de champ "
                f"`| REPO_CIBLE | <chemin absolu> |`. Aucun repli sur le répertoire de "
                f"travail du `.conf` n'est effectué — le périmètre doit être explicite. "
                f"Corrigez l'en-tête de l'issue puis retirez le label `{LABEL_ECHEC}` "
                f"pour relancer."
            )
            ajouter_label(numero, LABEL_ECHEC)
            # PAS de retrait de issues_en_cours (issue #576) : `needs-human`
            # posé, l'issue reste suivie tant que le label n'est pas retiré.
            return None

        valide, raison = valider_repo_cible(repo_cible)
        if not valide:
            log.error(f"  Issue #{numero} : REPO_CIBLE refusé ({raison}) — abandon, aucun lancement de CCL.")
            commenter_issue(
                numero,
                f"❌ `REPO_CIBLE` refusé — `{repo_cible}` : {raison}.\n\n"
                f"Aucun lancement de CCL (erreur de configuration/issue, pas un échec "
                f"transitoire). Corrigez le champ `REPO_CIBLE` puis retirez le label "
                f"`{LABEL_ECHEC}` pour relancer."
            )
            ajouter_label(numero, LABEL_ECHEC)
            # PAS de retrait de issues_en_cours (issue #576) : `needs-human`
            # posé, l'issue reste suivie tant que le label n'est pas retiré.
            return None

        repo_cible_resolu  = Path(repo_cible).resolve()
        perimetre_effectif = str(repo_cible_resolu)
        cwd_effectif       = repo_cible_resolu
        log.info(f"  Périmètre dynamique : REPO_CIBLE = {repo_cible_resolu} (périmètre + cwd de cette exécution).")

        # Transparence (issue #125) : si un autre watcher actif partage ce dossier,
        # on ne bloque pas mais on signale le risque en tête du résultat.
        conflit = detecter_conflit_watcher(repo_cible_resolu, CFG.nom)
        if conflit:
            log.warning(f"  ⚠️  Conflit potentiel : watcher '{conflit}' actif sur {repo_cible_resolu}.")
            avertissement_conflit = (
                f"⚠️ Traitement lancé pendant qu'un watcher actif sur ce dépôt "
                f"(projet {conflit}) pouvait être en train d'écrire — certains constats "
                f"peuvent être obsolètes.\n\n"
            )

    # SOUS_DOSSIER (issue #550) : cwd du subprocess dérivé d'un sous-dossier
    # RELATIF sous REP_TRAVAIL — pour le canal unifié for-windows, où
    # REP_TRAVAIL désigne un dossier PARENT partagé (ex. C:\CCW_Share) et non
    # le sous-projet réellement visé par l'issue (ex. CCW\gestionmail). Voir
    # le commentaire de valider_sous_dossier pour la cause racine (écart
    # cwd/dossier git réel) que ce champ corrige. Sans objet si un worktree
    # isolé ou un périmètre dynamique (REPO_CIBLE) sont déjà actifs pour
    # cette tâche : ces deux mécanismes fixent déjà cwd_effectif eux-mêmes et
    # restent seuls décisifs si combinés par erreur avec SOUS_DOSSIER — même
    # esprit que la priorité worktree/REPO_CIBLE déjà en place ci-dessus.
    # Absent de l'issue (usage historique, sans sous-projet ciblé) :
    # cwd_effectif reste CFG.rep_travail, comportement strictement inchangé.
    if chemin_worktree is None and not CFG.perimetre_dynamique:
        sous_dossier = extraire_sous_dossier(body)
        if sous_dossier:
            valide, raison, chemin_resolu = valider_sous_dossier(CFG.rep_travail, sous_dossier)
            if not valide:
                log.error(f"  Issue #{numero} : SOUS_DOSSIER refusé ({raison}) — abandon, aucun lancement de Claude Code.")
                commenter_issue(
                    numero,
                    f"❌ `SOUS_DOSSIER` refusé — `{sous_dossier}` : {raison}.\n\n"
                    f"Aucun lancement de Claude Code (erreur de configuration/issue, pas un "
                    f"échec transitoire). Corrigez le champ `SOUS_DOSSIER` puis retirez le "
                    f"label `{LABEL_ECHEC}` pour relancer."
                )
                ajouter_label(numero, LABEL_ECHEC)
                # PAS de retrait de issues_en_cours (issue #576) : `needs-human`
                # posé, l'issue reste suivie tant que le label n'est pas retiré.
                # En mode écriture, elle continue en plus d'occuper une place
                # de MAX_WRITE_PARALLELE (voir _issue_write_bloquee_ajouter).
                if mode == MODE_ECRITURE:
                    _issue_write_bloquee_ajouter(numero)
                return None
            cwd_effectif       = chemin_resolu
            perimetre_effectif = str(chemin_resolu)
            log.info(f"  SOUS_DOSSIER : cwd de cette exécution = {chemin_resolu} (issue #550).")

    return ContexteExecution(perimetre_effectif, cwd_effectif, avertissement_conflit, avertissement_worktree_deja_pris)


def _acquerir_verrou_pour_issue(numero: int, cwd_effectif: Path, timeout: int, mode: str):
    """Garde-fou anti-collision inter-process (issue #189) : AVANT l'ACK et
    tout lancement de claude, pose un verrou exclusif sur le répertoire de
    travail effectif. Si un AUTRE process (autre instance/relance de watcher,
    ou un doublon d'issue traité en parallèle) détient déjà ce verrou, on NE
    lance PAS un second claude sur le même dossier : on relâche l'issue
    (retirée de issues_en_cours, sans ACK) pour qu'elle soit reprise au
    prochain cycle, une fois le verrou libéré. issues_en_cours ne protège que
    dans CE process ; le verrou fichier étend la protection entre process.
    Retourne None si le verrou n'a pas pu être acquis (issue déjà retirée de
    issues_en_cours par cette fonction)."""
    verrou = acquerir_verrou(cwd_effectif, timeout, mode)
    if verrou is None:
        log.warning(
            f"  Issue #{numero} différée : un autre traitement détient déjà le verrou "
            f"sur {cwd_effectif} — collision évitée, reprise au prochain cycle."
        )
        _issues_en_cours_retirer(numero)
    return verrou


def _preparer_lecture_active(numero: int, mode: str, dry_run: bool,
                              cwd_effectif: Path) -> tuple[Path | None, dict | None, bool]:
    """Lecture active (issue #327) : dossier scratch créé AVANT tout
    lancement de claude (niveau 1), et empreinte de REP_TRAVAIL prise AVANT
    la première tentative (niveau 2 — voir _restaurer_rep_travail_modifie).
    Appelée avant l'ACK pour ne rien engager (ACK, chrono) si la préparation
    échoue. Retourne (chemin_scratch, statut_rep_travail_avant, ok). Si
    ok=False, l'abandon (commentaire + label needs-human) est déjà géré ici —
    `chemin_scratch` peut néanmoins être non-None (résolu mais `mkdir` en
    échec) et DOIT alors quand même être passé au nettoyage de l'appelant."""
    chemin_scratch = None
    statut_rep_travail_avant = None
    if mode == MODE_LECTURE_ACTIVE and not dry_run:
        try:
            chemin_scratch = _chemin_scratch(CFG.nom)
            chemin_scratch.mkdir(parents=True, exist_ok=True)
        except (ValueError, OSError) as e:
            log.error(f"  Issue #{numero} : préparation du dossier scratch impossible ({e}) — abandon.")
            commenter_issue(
                numero,
                f"❌ Échec de préparation du dossier scratch (lecture active) : {e}. "
                f"Aucun lancement de CCL (erreur de configuration, pas un échec transitoire). "
                f"Corrigez puis retirez le label `{LABEL_ECHEC}` pour relancer."
            )
            ajouter_label(numero, LABEL_ECHEC)
            # PAS de retrait de issues_en_cours (issue #576) : `needs-human`
            # posé, l'issue reste suivie tant que le label n'est pas retiré.
            return (chemin_scratch, statut_rep_travail_avant, False)
        statut_rep_travail_avant = _statut_git_rep_travail(cwd_effectif)
    return (chemin_scratch, statut_rep_travail_avant, True)


def _demarrer_traitement(numero: int, mode: str, mode_txt: str, dry_run: bool,
                          cwd_effectif: Path) -> tuple[bool, float, int, dict | None]:
    """Tout ce qui précède la première tentative `lancer_claude` : détection
    RELANCE, ACK, rafraîchissement SSE, départ du chrono, sonde pre-flight
    token et empreinte configs/*.conf. Retourne (est_relance, debut_traitement,
    nb_projets_actifs_debut, empreinte_configs_avant)."""
    # Détection RELANCE (champ RELANCE, issue #516) AVANT l'ACK courante
    # (issue #592) : un commentaire d'échec définitif déjà présent dans
    # l'historique de l'issue signale que le worktree peut contenir du
    # travail déjà fait par une tentative précédente — la durée mesurée
    # ci-dessous (ACK → clôture) serait alors artificiellement courte.
    # Réutilisé côté succès, plus bas, pour exclure cette durée de la
    # calibration TIMEOUT (maj_calibration_timeout).
    est_relance = _issue_est_relance(_lister_commentaires(numero))

    commenter_issue(
        numero,
        f"✅ ACK — Issue #{numero} reçue par watcher.py ({CFG.libelle_agent_effectif}, projet {CFG.nom}). "
        f"Mode : **{mode_txt}**. Traitement en cours..."
    )
    # Rafraîchissement SSE de l'onglet Résultats dès le DÉBUT réel du
    # traitement (issue #515), pas seulement à sa fin — couvre le cas d'une
    # issue encore inconnue du navigateur (ex. créée via issues_inbox
    # pendant une absence).
    notifier_debut_sse(numero)
    # Départ du chrono de durée réelle (ACK → fermeture), pour l'historique des
    # durées (issue #108). monotonic() pour la mesure d'écoulement (insensible aux
    # changements d'heure système).
    debut_traitement = time.monotonic()
    # Nombre de watchers actifs au lancement DE CETTE ISSUE (issue #220, champ
    # nb_projets_actifs_au_lancement) — figé une fois pour toute la durée du
    # traitement (succès ou timeouts successifs), pas recalculé à chaque tentative.
    nb_projets_actifs_debut = _compter_watchers_actifs()

    # Pre-flight token (issue #309) : une seule sonde avant la première
    # tentative, pas à chaque tentative — voir verifier_preflight_token.
    # Sautée en dry-run (aucun appel claude réel dans ce mode).
    if not dry_run:
        verifier_preflight_token(cwd=cwd_effectif)

    # Garde-fou technique configs/*.conf (issue #318, étendu à la lecture
    # active par #327 : mode_scratch arme aussi --dangerously-skip-permissions,
    # donc mérite la même protection) : instantané pris une seule fois avant
    # la première tentative — chaque tentative est comparée à CE MÊME
    # instantané (l'état légitime d'origine), pas à celui de la tentative
    # précédente, pour rester la référence même après une éventuelle
    # restauration intermédiaire.
    empreinte_configs_avant = (
        _empreinte_configs() if (mode != MODE_LECTURE and not dry_run) else None
    )

    return est_relance, debut_traitement, nb_projets_actifs_debut, empreinte_configs_avant


def _executer_une_tentative(numero: int, titre: str, body: str, dry_run: bool, mode: str,
                             timeout: int, modele: str, perimetre_effectif: str,
                             cwd_effectif: Path, verrou, chemin_scratch: Path | None,
                             chemin_worktree: Path | None, empreinte_configs_avant: dict | None,
                             tentative: int) -> tuple[bool, str]:
    """Une tentative `lancer_claude`, garde-fou de format de clôture (#581) et
    restauration best-effort des configs/*.conf modifiés (#318/#327).
    Retourne (succes, sortie)."""
    succes, sortie = lancer_claude(numero, titre, body, dry_run, mode,
                                   timeout, modele,
                                   perimetre=perimetre_effectif, cwd=cwd_effectif,
                                   verrou=verrou, chemin_scratch=chemin_scratch,
                                   chemin_worktree=chemin_worktree)

    # Garde-fou de format (issue #581) : le prompt standard impose un
    # rapport de clôture marqué par ✅ ou ❌ (« Réponds avec ce format
    # exact »). Cause racine #581 : un sous-agent d'exploration lancé
    # en arrière-plan par claude (Task/Agent tool) peut terminer APRÈS
    # que claude ait déjà produit ce rapport final conforme —
    # `claude --print` reste alors vivant le temps de traiter cette
    # notification tardive et émet un tour supplémentaire (simple note
    # de suivi, hors format), qui ÉCRASE le rapport conforme dans le
    # stdout capturé ci-dessus : exit code 0, donc `succes=True`, mais
    # contenu hors-sujet/hors-format — cas vécu sur #580, rapport réel
    # jamais posté nulle part. Détection volontairement large (marqueur
    # présent N'IMPORTE OÙ dans le texte, pas seulement en tête) : en
    # pratique claude fait fréquemment précéder le rapport d'une courte
    # phrase d'intro ("Commit créé avec succès. Le rapport final :"),
    # anodin et déjà toléré historiquement — seule l'ABSENCE totale du
    # marqueur (cas #580) doit déclencher ce garde-fou, pas sa position.
    # dry_run exclu : sa sortie fixe ("[DRY-RUN] ...") ne respecte
    # jamais ce format et ne passe de toute façon jamais par
    # `commenter_resultat_avec_retry`.
    if succes and not dry_run and not ("✅" in sortie or "❌" in sortie):
        log.warning(
            f"  ✗ Tentative {tentative} : sortie de claude sans aucun "
            f"marqueur ✅/❌ de clôture — probablement une réponse "
            f"tardive (sous-agent en arrière-plan terminé après le "
            f"rapport final, issue #581) ayant écrasé le vrai rapport. "
            f"Traitée comme un échec de cette tentative."
        )
        succes = False
        sortie = (
            "Sortie de claude sans aucun marqueur ✅/❌ de clôture "
            "attendu — probablement une réponse tardive émise après la "
            "fin réelle du traitement (ex. notification d'un sous-agent "
            "en arrière-plan terminé après le rapport final), qui a "
            "écrasé la vraie réponse dans la sortie capturée (issue "
            f"#581). Sortie obtenue : {sortie.strip()[:500]}"
        )

    if empreinte_configs_avant is not None:
        _restaurer_configs_modifies(numero, empreinte_configs_avant)

    return succes, sortie


def _verifier_violation_scratch(numero: int, titre: str, labels: list[str],
                                 cwd_effectif: Path, statut_rep_travail_avant: dict | None) -> bool:
    """Garde-fou technique niveau 2 (issue #327) : après une tentative en
    lecture active, vérifie qu'aucune écriture n'a eu lieu dans le projet hors
    scratch. Détecté ⇒ échec DÉFINITIF immédiat (pas de nouvelle tentative —
    contrairement aux autres échecs, retenter risquerait de répéter la même
    violation), needs-human, sur le même modèle que l'abandon REPO_CIBLE
    invalide de `_resoudre_contexte_execution`. Retourne True si une violation
    a été détectée et traitée (l'appelant doit alors retourner immédiatement),
    False sinon — y compris hors lecture active, où `statut_rep_travail_avant`
    vaut None."""
    if statut_rep_travail_avant is None:
        return False

    chemins_restaures = _restaurer_rep_travail_modifie(numero, cwd_effectif, statut_rep_travail_avant)
    if not chemins_restaures:
        return False

    log.error(
        f"  ✗ Issue #{numero} : lecture active — écriture détectée dans le "
        f"projet hors scratch ({', '.join(chemins_restaures)}) — restaurée, "
        f"échec définitif (garde-fou niveau 2, issue #327)."
    )
    commenter_issue(
        numero,
        f"❌ Lecture active : écriture détectée dans le projet hors scratch — restaurée.\n\n"
        f"Fichier(s) concerné(s) : `{', '.join(chemins_restaures)}`\n\n"
        f"Garde-fou niveau 2 (empreinte REP_TRAVAIL avant/après, issue #327) déclenché : "
        f"la consigne de confinement au dossier scratch n'a pas été respectée malgré le "
        f"garde-fou de prompt (niveau 1). Le projet a été restauré à son état d'avant "
        f"traitement. Intervention humaine requise. Label `{LABEL_ECHEC}` posé : cette "
        f"issue ne sera plus retraitée automatiquement tant que le label n'est pas retiré "
        f"manuellement."
    )
    ajouter_label(numero, LABEL_ECHEC)
    notifier(
        labels,
        titre=f"❌ {CFG.nom} #{numero} — lecture active : écriture hors scratch",
        message=f"'{titre}' : écriture détectée hors scratch en lecture active, projet restauré.",
        urgence_bureau="critical",
        priorite_ntfy="high",
        numero=numero,
    )
    notifier_fin_sse(numero)
    # PAS de retrait de issues_en_cours (issue #576) : `needs-human`
    # posé, l'issue reste suivie tant que le label n'est pas
    # retiré. Mode lecture active (jamais MODE_ECRITURE ici,
    # cf. `statut_rep_travail_avant` posé uniquement pour ce
    # mode) : n'occupe donc jamais de place MAX_WRITE_PARALLELE.
    return True


def _finaliser_succes(numero: int, titre: str, body: str, labels: list[str], mode: str,
                       timeout: int, avertissement_conflit: str,
                       avertissement_worktree_deja_pris: str, sortie: str,
                       debut_traitement: float, nb_projets_actifs_debut: int,
                       est_relance: bool) -> None:
    """Traitement d'une tentative réussie : commentaire de résultat (avec
    retry), fermeture de l'issue, historique des durées, calibration
    automatique du TIMEOUT et notification. Termine toujours le traitement de
    l'issue — l'appelant doit retourner immédiatement après l'appel."""
    log.info(f"  ✓ Issue #{numero} traitée avec succès.")
    message_resultat = f"{MARQUEUR_RESULTAT}\n## Résultat\n\n{avertissement_conflit}{avertissement_worktree_deja_pris}{sortie}"
    # Le commentaire de résultat est critique (issue #195) : on le
    # poste avec retry/backoff et on ne ferme l'issue QUE s'il a réussi.
    if not commenter_resultat_avec_retry(numero, message_resultat):
        # Échec réseau persistant : fermer l'issue effacerait
        # silencieusement le travail. On la laisse OUVERTE (ni `close`
        # ni label `done`) pour reprise au prochain cycle. La garde
        # d'idempotence en tête de traiter_issue évitera de relancer
        # claude à tort si un cycle ultérieur finit par poster le
        # commentaire mais échoue encore la fermeture.
        log.error(
            f"  ✗ Commentaire de résultat #{numero} impossible après retries — "
            f"issue laissée OUVERTE pour reprise (non fermée)."
        )
        notifier(
            labels,
            titre=f"⚠️ {CFG.nom} #{numero} — résultat non posté",
            message=(f"'{titre}' traitée, mais le commentaire de résultat a échoué "
                     f"(réseau). Issue laissée ouverte pour reprise au prochain cycle."),
            urgence_bureau="critical",
            priorite_ntfy="high",
            numero=numero,
        )
        _issues_en_cours_retirer(numero)
        return
    if not fermer_issue(numero):
        log.warning(f"  Fermeture de l'issue #{numero} incomplète (close/label) — sera retentée au prochain cycle via la garde d'idempotence.")
    _issues_en_cours_retirer(numero)
    # Historique des durées (issue #108) : durée réelle ACK → fermeture,
    # catégorisée par projet/type/mode, pour l'estimation prédictive.
    type_issue_close = deduire_type_issue(titre, body)
    mode_close        = _etiquette_calibration(mode)
    complexite_close  = extraire_complexite(body)
    duree_reelle      = time.monotonic() - debut_traitement
    date_iso_close    = datetime.now().isoformat(timespec="seconds")
    enregistrer_duree(
        CFG.nom,
        type_issue_close,
        mode_close,
        duree_reelle,
        date_iso_close,
        body=body,
        nb_projets_actifs=nb_projets_actifs_debut,
    )
    # Calibration automatique du TIMEOUT (issue #221) : met à jour les
    # EWMA duree_typique/variabilite/backoff (par combinaison) et F
    # (global), puis journalise le TIMEOUT_suggéré — sans effet sur le
    # TIMEOUT réellement appliqué (extraire_timeout reste seul décisif).
    suggere = maj_calibration_timeout(
        projet=CFG.nom,
        type_issue=type_issue_close,
        mode=mode_close,
        complexite=complexite_close,
        duree_s=duree_reelle,
        expiree=False,
        body=body,
        date_iso=date_iso_close,
        relance=est_relance,
    )
    # Exposition du TIMEOUT_suggéré dans le commentaire de clôture
    # GitHub (issue #222) : seul canal fiable pour transmettre cette
    # info calculée localement à Claude Chat (pas d'accès direct aux
    # fichiers d'état gitignorés du ThinkPad). Connue seulement APRÈS
    # la fermeture (dépend de duree_reelle) : on édite le commentaire
    # de résultat déjà posté (gh --edit-last) plutôt que d'en poster
    # un second. Best-effort — n'affecte pas la clôture déjà faite.
    if not editer_dernier_commentaire(
            numero, message_resultat + formater_bloc_calibration(duree_reelle, timeout, suggere)):
        log.warning(f"  Ajout du bloc calibration au commentaire #{numero} échoué (best-effort, non bloquant).")
    notifier(
        labels,
        titre=f"✅ {CFG.nom} #{numero} — traitée",
        message=f"'{titre}' traitée avec succès.",
        urgence_bureau="normal",
        priorite_ntfy="default",
        numero=numero,
    )
    notifier_fin_sse(numero)


def _tracer_tentative_expiree(numero: int, titre: str, body: str, mode: str,
                               debut_traitement: float, nb_projets_actifs_debut: int) -> None:
    """Trace du timeout dans l'historique des durées (issue #220) : avant ce
    correctif, une tentative expirée (subprocess.TimeoutExpired dans
    lancer_claude, message "Timeout après <N>s") ne laissait AUCUNE trace
    dans historique_durees.json — seulement dans le log texte du watcher.
    Un enregistrement minimal (expiree=True) est ajouté ICI, PAR TENTATIVE
    expirée (pas seulement à l'abandon définitif), pour permettre de
    compter la fréquence réelle des timeouts dans une future issue — y
    compris pour les issues critiques en retry infini, qui n'atteignent
    jamais la branche d'abandon."""
    type_issue_expire = deduire_type_issue(titre, body)
    mode_expire        = _etiquette_calibration(mode)
    complexite_expire  = extraire_complexite(body)
    duree_expiree      = time.monotonic() - debut_traitement
    date_iso_expire    = datetime.now().isoformat(timespec="seconds")
    enregistrer_duree(
        CFG.nom,
        type_issue_expire,
        mode_expire,
        duree_expiree,
        date_iso_expire,
        body=body,
        nb_projets_actifs=nb_projets_actifs_debut,
        expiree=True,
    )
    # Calibration automatique du TIMEOUT (issue #221) : sur timeout,
    # multiplicateur_backoff *= FACTEUR_BACKOFF immédiatement pour cette
    # combinaison (par tentative expirée, même logique que ci-dessus).
    maj_calibration_timeout(
        projet=CFG.nom,
        type_issue=type_issue_expire,
        mode=mode_expire,
        complexite=complexite_expire,
        duree_s=duree_expiree,
        expiree=True,
        body=body,
        date_iso=date_iso_expire,
    )


def _gerer_abandon_max_essais(numero: int, titre: str, body: str, labels: list[str],
                               mode: str, critique: bool, tentative: int, sortie: str,
                               timeout: int, avertissement_worktree_deja_pris: str,
                               perimetre_effectif: str, cwd_effectif: Path,
                               debut_traitement: float) -> None:
    """Nombre maximal de tentatives atteint (`CFG.max_essais`) : issue
    critique ⇒ nouvelle tentative au prochain cycle (retry infini, jamais de
    needs-human) ; sinon abandon définitif (passe diagnostique, label
    needs-human, notification). Termine toujours le traitement de l'issue —
    l'appelant doit retourner immédiatement après l'appel."""
    if critique:
        alerte_critique(numero, titre, tentative, labels)
        log.warning(f"  Issue critique #{numero} — nouvelle tentative au prochain cycle.")
        _issues_en_cours_retirer(numero)  # sera reprise au prochain poll
        return

    log.error(f"  Issue #{numero} abandonnée après {CFG.max_essais} tentatives.")
    # Passe diagnostique courte, en lecture seule, avant l'abandon
    # définitif (issue #124) : quelques pistes concrètes pour éviter à
    # Alain d'ouvrir lui-même une session juste pour comprendre le
    # timeout. Best-effort — n'ajoute rien si elle échoue/timeout.
    log.info(f"  Passe diagnostique courte (lecture seule, {CFG.timeout_diagnostic}s) pour #{numero}...")
    diagnostic = diagnostiquer_echec(numero, titre, body, sortie,
                                     perimetre=perimetre_effectif,
                                     cwd=cwd_effectif)
    message_echec = (
        f"❌ Échec après {CFG.max_essais} tentatives.\n\n"
        f"{avertissement_worktree_deja_pris}"
        f"Dernière erreur : `{sortie}`\n\n"
    )
    if diagnostic:
        message_echec += (
            f"🔍 Pistes probables (diagnostic automatique) :\n\n"
            f"{diagnostic}\n\n"
        )
    message_echec += (
        f"Intervention humaine requise. Label `{LABEL_ECHEC}` posé : "
        f"cette issue ne sera plus retraitée automatiquement tant que le "
        f"label n'est pas retiré (ou l'issue fermée) manuellement."
    )
    # Exposition du TIMEOUT_suggéré dans le commentaire de clôture
    # GitHub, ici aussi côté échec (issue #222). Simple LECTURE de
    # l'état (lire_timeout_suggere), pas un nouvel appel à
    # maj_calibration_timeout : chaque tentative expirée l'a déjà
    # mis à jour ci-dessus — le rappeler ici compterait deux fois la
    # même observation dans l'EWMA.
    type_issue_echec = deduire_type_issue(titre, body)
    mode_echec        = _etiquette_calibration(mode)
    complexite_echec  = extraire_complexite(body)
    duree_echec       = time.monotonic() - debut_traitement
    suggere_echec     = lire_timeout_suggere(CFG.nom, type_issue_echec, mode_echec, complexite_echec, body)
    message_echec += formater_bloc_calibration(duree_echec, timeout, suggere_echec)
    commenter_issue(numero, message_echec)
    ajouter_label(numero, LABEL_ECHEC)
    notifier(
        labels,
        titre=f"❌ {CFG.nom} #{numero} — échec définitif",
        message=f"'{titre}' abandonnée après {CFG.max_essais} tentatives.\nDernière erreur : {sortie[:200]}",
        urgence_bureau="critical",
        priorite_ntfy="high",
        numero=numero,
    )
    notifier_fin_sse(numero)
    # PAS de retrait de issues_en_cours (issue #576) : `needs-human`
    # posé, l'issue reste suivie tant que le label n'est pas
    # retiré (ou l'issue fermée) manuellement. En mode
    # écriture, elle continue en plus d'occuper une place de
    # MAX_WRITE_PARALLELE (voir _issue_write_bloquee_ajouter).
    if mode == MODE_ECRITURE:
        _issue_write_bloquee_ajouter(numero)


def _nettoyer_apres_traitement(verrou, chemin_scratch: Path | None,
                                chemin_worktree: Path | None, numero: int) -> None:
    """Libération garantie du verrou (succès, échec définitif, exception,
    reprise critique) — sans elle, un crash laisserait un verrou orphelin,
    d'où aussi la péremption côté acquerir_verrou. Nettoyage garanti du
    dossier scratch de lecture active (issue #327), succès/échec/timeout/
    exception confondus — même esprit que _nettoyer_arbre_claude pour les
    process. Fin de tâche en worktree (issue #337) : PAS de `git worktree
    remove` ni de suppression de branche automatique — Alain merge et pousse
    manuellement, on se contente ici de journaliser clairement l'état final
    (numéro, chemin, branche) pour qu'il sache quoi retrouver."""
    liberer_verrou(verrou)
    if chemin_scratch is not None:
        _nettoyer_scratch(numero, chemin_scratch)
    if chemin_worktree is not None:
        log.info(
            f"  Issue #{numero} : fin de traitement en worktree {chemin_worktree} "
            f"(branche {_branche_worktree(numero)}) — worktree CONSERVÉ (aucune "
            f"suppression automatique), fusion/push manuels par Alain."
        )


def _traiter_issue_synchrone(issue: dict, dry_run: bool, chemin_worktree: Path | None = None,
                              echec_worktree_deja_pris: str | None = None):
    """Corps du traitement d'une issue — inchangé depuis avant #337, à
    l'exception du paramètre `chemin_worktree` (issue #337) : chemin du
    worktree git isolé où cette tâche mode_write doit tourner, ou None pour le
    traitement classique dans REP_TRAVAIL. Appelée soit directement (issues
    lecture/lecture active, ou mode_write hors parallélisation), soit depuis un
    thread dédié via `traiter_issue` (point d'entrée public, voir plus bas).

    `echec_worktree_deja_pris` (issue #589) : renseigné par l'appelant quand
    `chemin_worktree` vaut None PARCE QUE `_creer_worktree` a échoué pour
    cause de chemin ou branche déjà pris (repli volontaire sur REP_TRAVAIL,
    cf. BRIDGE_AGENT_DOC.md) — distinct d'un appel normal sans worktree
    (mode lecture, parallélisation désactivée, etc.). Rend ce repli visible
    dans le compte-rendu de clôture, en plus du log.warning déjà émis par
    `_creer_worktree` au moment de l'échec.

    Orchestrateur (issue #619) : chaque étape est déléguée à une sous-fonction
    privée ci-dessus (guards + bootstrap CCW, déduction du mode, résolution du
    périmètre, acquisition du verrou, préparation lecture active, démarrage,
    boucle de tentatives, succès/échec/nettoyage) — comportement inchangé."""
    numero = issue["number"]
    titre  = issue["title"]
    body   = issue.get("body") or ""

    labels = _guards_precoces_et_bootstrap(issue, numero, titre, body, dry_run)
    if labels is None:
        return

    mode, mode_txt, _priorite, critique, timeout, modele = _deduire_mode_et_logguer(
        numero, titre, body, labels, chemin_worktree)

    contexte = _resoudre_contexte_execution(numero, body, mode, chemin_worktree, echec_worktree_deja_pris)
    if contexte is None:
        return
    perimetre_effectif = contexte.perimetre_effectif
    cwd_effectif        = contexte.cwd_effectif
    avertissement_conflit = contexte.avertissement_conflit
    avertissement_worktree_deja_pris = contexte.avertissement_worktree_deja_pris

    verrou = _acquerir_verrou_pour_issue(numero, cwd_effectif, timeout, mode)
    if verrou is None:
        return

    # `chemin_scratch` est référencé dans le `finally` ci-dessous (nettoyage) :
    # il DOIT rester défini (None si non applicable) même sur un retour
    # anticipé depuis le `try`.
    chemin_scratch = None
    try:
        chemin_scratch, statut_rep_travail_avant, ok = _preparer_lecture_active(numero, mode, dry_run, cwd_effectif)
        if not ok:
            return

        est_relance, debut_traitement, nb_projets_actifs_debut, empreinte_configs_avant = \
            _demarrer_traitement(numero, mode, mode_txt, dry_run, cwd_effectif)

        tentative = 0
        while True:
            tentative += 1
            log.info(f"  Tentative {tentative}/{CFG.max_essais if not critique else '∞'}...")

            succes, sortie = _executer_une_tentative(
                numero, titre, body, dry_run, mode, timeout, modele,
                perimetre_effectif, cwd_effectif, verrou, chemin_scratch,
                chemin_worktree, empreinte_configs_avant, tentative)

            if _verifier_violation_scratch(numero, titre, labels, cwd_effectif, statut_rep_travail_avant):
                return

            if succes:
                _finaliser_succes(numero, titre, body, labels, mode, timeout,
                                   avertissement_conflit, avertissement_worktree_deja_pris,
                                   sortie, debut_traitement, nb_projets_actifs_debut, est_relance)
                return

            # Échec
            log.warning(f"  ✗ Tentative {tentative} échouée : {sortie}")

            if sortie.startswith("Timeout après"):
                _tracer_tentative_expiree(numero, titre, body, mode, debut_traitement, nb_projets_actifs_debut)

            if tentative >= CFG.max_essais:
                _gerer_abandon_max_essais(numero, titre, body, labels, mode, critique, tentative,
                                           sortie, timeout, avertissement_worktree_deja_pris,
                                           perimetre_effectif, cwd_effectif, debut_traitement)
                return

            time.sleep(PAUSE_ENTRE_TENTATIVES)  # backoff entre tentatives
    finally:
        _nettoyer_apres_traitement(verrou, chemin_scratch, chemin_worktree, numero)

# ─── Point d'entrée public : dispatch séquentiel / parallèle (issue #337) ──────

def _lancer_thread_ecriture(issue: dict, dry_run: bool, chemin_worktree: Path | None,
                             echec_worktree_deja_pris: str | None = None) -> None:
    """Cible du thread Python dédié à une tâche mode_write parallélisée (issue
    #337). Appelle simplement `_traiter_issue_synchrone` — toute la logique
    (ACK, verrou par chemin_travail, retries, fermeture, notifications) reste
    identique, seul le chemin de travail change. `_threads_ecriture` n'a PAS
    besoin d'être purgé ici explicitement : `_nettoyer_threads_ecriture_termines`
    (appelée à chaque décision de dispatch et en tête de boucle principale)
    détecte `thread.is_alive() == False` dès que cette fonction retourne.

    `echec_worktree_deja_pris` (issue #611) : transmis tel quel quand ce
    thread cible REP_TRAVAIL en tout dernier recours, après épuisement des
    tentatives de `_creer_worktree_avec_retries` — rend ce repli visible dans
    le compte-rendu de clôture (voir `_traiter_issue_synchrone`)."""
    _traiter_issue_synchrone(issue, dry_run, chemin_worktree=chemin_worktree,
                              echec_worktree_deja_pris=echec_worktree_deja_pris)


def traiter_issue(issue: dict, dry_run: bool) -> None:
    """Point d'entrée public, appelé par la boucle principale pour CHAQUE
    issue. Décide, pour une issue mode_write prête, entre traitement
    séquentiel classique et parallélisation via git worktree (issue #337) ;
    délègue tout le reste (lecture, lecture active, mode_write hors
    parallélisation) tel quel à `_traiter_issue_synchrone`, comportement
    inchangé depuis avant #337.

    Décision de parallélisation (voir commentaire de section au-dessus de
    `_threads_ecriture`) :
      - dry-run, ou projet à périmètre dynamique (#125, hors périmètre de
        #337) → jamais de worktree, chemin historique intégral dans
        REP_TRAVAIL.
      - `MAX_WRITE_PARALLELE <= 1` (issue #577) → pas de thread (une seule
        tâche mode_write à la fois, thread principal), mais worktree dédié
        malgré tout : `_creer_worktree_avec_retries` puis
        `_traiter_issue_synchrone` appelée directement (bloquant) avec ce
        worktree. Échec de TOUTES les tentatives → repli direct sur
        REP_TRAVAIL, signalé activement (issue #611).
      - `MAX_WRITE_PARALLELE > 1` → TOUTE tâche mode_write du lot, y compris
        la première (issue #611 — plus d'exception REP_TRAVAIL pour le
        premier slot, cf. #577 contredit par #337), obtient un worktree dédié
        via `_creer_worktree_avec_retries` (nom standard, puis `-bis`/`-ter`
        si le chemin/la branche est déjà pris) + thread. Échec de TOUTES les
        tentatives → repli en tout DERNIER recours sur REP_TRAVAIL, mais
        toujours en thread (pour que la boucle principale reste libre de
        traiter d'autres issues) : le verrou par chemin_travail (#189/#322)
        protège alors contre une collision avec un autre repli concurrent qui
        viserait lui aussi REP_TRAVAIL — simple différé au prochain cycle si
        REP_TRAVAIL est occupé. Signalé activement (notify-send + log.warning
        + mention dans le compte-rendu de clôture, issue #611/#589).
      - À `MAX_WRITE_PARALLELE` déjà atteint → différée au prochain cycle,
        sans même tenter de worktree.

    Issue #576 : une issue mode_write bloquée en `needs-human` (échec
    définitif, sans thread actif) continue d'occuper une place de
    `MAX_WRITE_PARALLELE` tant qu'Alain n'est pas intervenu — voir
    `_issue_write_bloquee_ajouter`/`_nb_issues_write_bloquees`. La place n'est
    libérée que lorsque le label est effectivement retiré (bouton
    « Relancer » #574, fichier RELANCE #516/#572, ou retrait manuel du label)
    ET l'issue toujours ouverte — détecté ci-dessous à la relecture des
    labels frais de CHAQUE cycle. La fermeture manuelle de l'issue (cas où
    elle disparaît purement et simplement de `lister_issues()`) est traitée
    séparément, en tête de boucle principale."""
    numero = issue["number"]
    labels = [l.get("name", "") for l in issue.get("labels", [])]

    # Déjà en cours dans un thread depuis un cycle précédent (mode_write
    # parallélisé) : ne pas re-dispatcher, laisser ce thread poursuivre.
    if any(t["numero"] == numero for t in _threads_ecriture_actifs()):
        return

    if _issues_en_cours_contient(numero):
        if LABEL_ECHEC in labels:
            # Toujours 'needs-human' : occupe sa place tant qu'Alain n'est
            # pas intervenu (issue #576).
            return
        # Le label a été retiré depuis le dernier cycle où cette issue était
        # suivie (bouton « Relancer » #574, fichier RELANCE #516/#572, ou
        # retrait manuel du label sur GitHub, issue toujours ouverte) : place
        # libérée, l'issue redevient éligible au traitement ci-dessous.
        log.info(
            f"  Issue #{numero} : label '{LABEL_ECHEC}' retiré depuis le dernier cycle — "
            f"place libérée, issue de nouveau éligible (issue #576)."
        )
        _issues_en_cours_retirer(numero)
        _issue_write_bloquee_retirer(numero)

    # Issue déjà finalisée (échec définitif ou résultat déjà posté) : chemin
    # rapide direct, pas de worktree à créer pour une issue qui ne va de toute
    # façon rien exécuter (_traiter_issue_synchrone le détecte immédiatement).
    if LABEL_ECHEC in labels or LABEL_FAIT in labels:
        _traiter_issue_synchrone(issue, dry_run)
        return

    mode = _deduire_mode(labels)

    if mode == MODE_ECRITURE and not dry_run and not CFG.perimetre_dynamique:
        actifs   = _threads_ecriture_actifs()
        bloquees = _nb_issues_write_bloquees()
        if len(actifs) + bloquees >= CFG.max_write_parallele:
            # Place(s) toutes occupées — par des threads actifs, et/ou par des
            # issues mode_write bloquées en needs-human (issue #576). Simple
            # `return` (pas de repli séquentiel direct comme auparavant dans
            # le cas plein-de-threads) : on ne sait pas ici si le verrou
            # REP_TRAVAIL est réellement libre, et le but explicite de #576
            # est justement d'empêcher ce repli tant qu'une place needs-human
            # n'est pas libérée.
            log.info(
                f"  Issue #{numero} : MAX_WRITE_PARALLELE ({CFG.max_write_parallele}) occupé "
                f"({len(actifs)} thread(s) actif(s) + {bloquees} bloquée(s) en needs-human, "
                f"issue #576) — traitement différé au prochain cycle."
            )
            return

        if CFG.max_write_parallele > 1:
            # TOUTE tâche mode_write, y compris la première du lot, obtient un
            # worktree dédié (issue #611 — corrige l'incohérence #577/#337 :
            # l'ancien premier slot visait REP_TRAVAIL sans isolation, cf.
            # commentaire de section au-dessus de `_threads_ecriture`).
            # PAS de _issues_en_cours_ajouter(numero) ICI : c'est
            # _traiter_issue_synchrone, exécutée DANS le thread, qui s'en
            # charge (comportement historique) — l'ajouter ici bloquerait le
            # thread dès sa première ligne (garde d'idempotence en tête de
            # _traiter_issue_synchrone). La déduplication inter-cycles est
            # déjà assurée par `_threads_ecriture` (vérifié plus haut).
            chemin_worktree, raison_deja_pris = _creer_worktree_avec_retries(numero)
            if chemin_worktree is not None:
                thread = threading.Thread(
                    target=_lancer_thread_ecriture, args=(issue, dry_run, chemin_worktree),
                    name=f"ecriture-issue-{numero}", daemon=True,
                )
                with _verrou_threads_ecriture:
                    _threads_ecriture.append({"numero": numero, "worktree": chemin_worktree, "thread": thread})
                log.info(
                    f"  Issue #{numero} : lancement dans le worktree {chemin_worktree} "
                    f"({len(actifs) + 1}/{CFG.max_write_parallele}) — parallélisation mode_write (issue #337)."
                )
                thread.start()
                return

            # Toutes les tentatives (nom standard + -bis + -ter) ont échoué :
            # repli en tout DERNIER recours dans REP_TRAVAIL, en tâche de fond
            # comme les autres slots — le verrou par chemin_travail (#189/#322)
            # protège contre une collision avec un autre repli concurrent qui
            # viserait lui aussi REP_TRAVAIL. Signalé activement (issue #611,
            # pas un chemin normal) : notify-send + log.warning ici,
            # + mention dans le compte-rendu de clôture assurée par
            # `_traiter_issue_synchrone` via `echec_worktree_deja_pris`
            # (transmis à travers `_lancer_thread_ecriture`, issue #589).
            _signaler_repli_worktree_echoue(numero, raison_deja_pris)
            thread = threading.Thread(
                target=_lancer_thread_ecriture,
                args=(issue, dry_run, None, raison_deja_pris),
                name=f"ecriture-issue-{numero}", daemon=True,
            )
            with _verrou_threads_ecriture:
                _threads_ecriture.append({"numero": numero, "worktree": None, "thread": thread})
            thread.start()
            return
        else:
            # MAX_WRITE_PARALLELE <= 1 (issue #577) : pas de parallélisation
            # entre tâches mode_write (une seule à la fois, thread principal —
            # PAS de threading.Thread ici), mais REP_TRAVAIL reste isolé
            # d'Alain comme au-dessus du seuil : la tâche obtient malgré tout
            # un worktree dédié, et s'exécute directement (appel bloquant,
            # sans thread) dedans. Échec de TOUTES les tentatives de création
            # du worktree (nom standard + -bis + -ter, issue #611) → repli
            # direct sur REP_TRAVAIL ci-dessous via `chemin_worktree=None`,
            # signalé activement comme pour le cas parallélisé ci-dessus.
            chemin_worktree, raison_deja_pris = _creer_worktree_avec_retries(numero)
            if chemin_worktree is not None:
                log.info(
                    f"  Issue #{numero} : traitement séquentiel dans le worktree "
                    f"{chemin_worktree} — isolation de REP_TRAVAIL systématique "
                    f"(issue #577)."
                )
            else:
                _signaler_repli_worktree_echoue(numero, raison_deja_pris)
            _traiter_issue_synchrone(issue, dry_run, chemin_worktree=chemin_worktree,
                                      echec_worktree_deja_pris=raison_deja_pris)
            return

    _traiter_issue_synchrone(issue, dry_run)

# ─── Boucle principale ─────────────────────────────────────────────────────────

def main():
    global CFG

    parser = argparse.ArgumentParser(description="Bridge watcher — agent Linux (multi-projets)")
    parser.add_argument("--config", required=True, help="Fichier de config du projet (ex. configs/bridge_agent.conf)")
    parser.add_argument("--dry-run", action="store_true", help="Simule sans lancer Claude Code")
    parser.add_argument("--interval", type=int, default=None, help="Surcharge l'intervalle de polling (secondes)")
    args = parser.parse_args()

    # Résolution tolérante du chemin de config : tel quel, sinon relatif au script.
    chemin = Path(args.config)
    if not chemin.exists():
        chemin = DOSSIER_SCRIPT / args.config

    CFG = charger_config(chemin)
    configurer_logs(CFG)

    # Fichier PID auto-publié (issue #596) : jusqu'ici c'était le lanceur
    # (app/watchers.py::demarrer_watcher, via subprocess.Popen) qui écrivait
    # logs/watcher-<nom>.pid après coup. Depuis #596 le watcher peut aussi être
    # lancé directement par systemd (`watcher@<nom>.service`), sans passer par
    # demarrer_watcher : le watcher publie donc lui-même son PID, quel que
    # soit son mode de lancement (terminal, Popen, systemd). Toute la
    # détection existante (app.watchers.watcher_actif, _watcher_actif/
    # detecter_conflit_watcher ci-dessous, app.interruption.interrompre_linux)
    # continue de lire ce même fichier sans autre changement.
    pid_file = DOSSIER_LOGS / f"watcher-{CFG.nom}.pid"
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()))

    intervalle = args.interval if args.interval is not None else CFG.intervalle

    log.info("=" * 60)
    log.info(f"Bridge watcher démarré — projet: {CFG.nom} — dépôt: {CFG.depot} — label: {CFG.label}")
    log.info(f"cwd Claude Code: {CFG.rep_travail} — journal: {CFG.fichier_log}")
    log.info(f"Polling toutes les {intervalle}s — dry-run: {args.dry_run}")
    log.info(f"contexte projet: {CFG.fichier_contexte or 'aucun'}")
    log.info("=" * 60)

    if not CFG.rep_travail.is_dir():
        log.warning(f"⚠️  Le répertoire de travail '{CFG.rep_travail}' n'existe pas (ou n'est pas un dossier). "
                    f"Claude Code échouera tant que ce n'est pas corrigé dans la config.")

    if args.dry_run:
        log.info("[DRY-RUN] Mode simulation activé — Claude Code ne sera pas lancé.")

    if CFG.delai_inactivite_min > 0:
        log.info(f"Auto-extinction activée : arrêt après {CFG.delai_inactivite_min} min sans issue traitable.")
    else:
        log.info("Auto-extinction désactivée (DELAI_INACTIVITE_MIN = 0) — watcher permanent.")

    if CFG.max_write_parallele > 1:
        log.info(f"Parallélisation mode_write via worktrees activée (issue #337) : MAX_WRITE_PARALLELE={CFG.max_write_parallele}.")
    else:
        log.info(f"Parallélisation mode_write désactivée (MAX_WRITE_PARALLELE={CFG.max_write_parallele}) — traitement séquentiel, mais toujours isolé dans un worktree dédié (issue #577), REP_TRAVAIL libre pour Alain.")

    # Horloge monotone d'inactivité (issue #200). Initialisée AVANT la boucle
    # pour qu'un watcher fraîchement démarré ne s'éteigne pas au premier cycle,
    # puis réarmée à chaque cycle comportant au moins une issue traitable.
    derniere_activite = time.monotonic()

    while True:
        # Test d'inactivité en tête de cycle, AVANT lister_issues() et AVANT tout
        # traitement (issue #200). Rester dans la boucle synchrone garantit qu'un
        # cycle de retry en cours (ex. #183, jusqu'à ~20 min) n'est jamais
        # interrompu : on ne teste qu'entre deux cycles complets. delai 0 =
        # mécanisme désactivé.
        if CFG.delai_inactivite_min > 0:
            # Garde-fou parallélisation mode_write (issue #337, point 8) :
            # jamais d'extinction tant qu'un thread mode_write tourne encore,
            # même si le délai d'inactivité est dépassé — un worktree en
            # thread n'est pas nécessairement reflété par `issue_traitable`
            # au même instant (labels re-synchronisés au poll suivant).
            # `_threads_ecriture_actifs()` purge les threads terminés à
            # chaque appel : réévalué à CHAQUE cycle, donc dès qu'un thread se
            # termine, l'extinction redevient possible au cycle suivant.
            threads_ecriture_actifs = _threads_ecriture_actifs()
            if threads_ecriture_actifs:
                log.debug(
                    f"Auto-extinction différée : {len(threads_ecriture_actifs)} "
                    f"tâche(s) mode_write encore active(s) en thread (issue #337)."
                )
            else:
                inactif_s = time.monotonic() - derniere_activite
                if inactif_s > CFG.delai_inactivite_min * 60:
                    log.info(f"⏻ Auto-extinction : aucune issue traitable depuis "
                             f"{CFG.delai_inactivite_min} min — arrêt propre du watcher.")
                    # Nettoyage du fichier PID, par cohérence avec arreter_watcher()
                    # (app/watchers.py) : sans ça l'interface afficherait un PID
                    # orphelin au lieu de « inactif ».
                    pid_file = DOSSIER_LOGS / f"watcher-{CFG.nom}.pid"
                    pid_file.unlink(missing_ok=True)
                    sys.exit(EXIT_INACTIVITE)

        try:
            # Rafraîchissement automatique du clone local en début de cycle
            # (issue #185). Choix : au début du cycle, sur CFG.rep_travail (le
            # clone fixe du projet), plutôt qu'avant chaque issue — c'est le
            # dépôt propre du watcher, il ne change pas d'une issue à l'autre, et
            # un pull par cycle suffit à la fraîcheur voulue. Les projets à
            # périmètre dynamique (REPO_CIBLE par issue) ne sont volontairement
            # PAS rafraîchis ici : ce sont des dépôts-cibles d'audit, pas le clone
            # de travail du watcher. Best-effort, jamais bloquant.
            rafraichir_depot(CFG.rep_travail, dry_run=args.dry_run)
            # Alerte accumulation de worktrees (issue #432), best-effort et
            # silencieuse en dessous du seuil — voir verifier_accumulation_worktrees().
            verifier_accumulation_worktrees()
            # Plafonnement défensif de MAX_WRITE_PARALLELE (issue #568), best-effort et
            # silencieux sous le plafond — voir verifier_plafond_max_write_parallele().
            verifier_plafond_max_write_parallele()
            issues = lister_issues()
            # Libère les places needs-human dont l'issue a été fermée
            # manuellement sur GitHub entre deux cycles (issue #576, cas 3) —
            # AVANT le calcul de travail_a_faire/traiter_issue ci-dessous,
            # sans quoi une place ainsi libérée resterait comptée jusqu'au
            # cycle suivant.
            _reconcilier_issues_en_cours_fermees(issues)
            # Activité = présence d'au moins une issue réellement traitable (ni
            # done, ni needs-human). On réarme AVANT le traitement : le cycle qui
            # suit ne testera l'inactivité qu'une fois ce traitement terminé, donc
            # un retry long n'est jamais interrompu (issue #200).
            travail_a_faire = any(issue_traitable(i) for i in issues)
            if travail_a_faire:
                derniere_activite = time.monotonic()
            if issues:
                log.info(f"{len(issues)} issue(s) en attente.")
                for issue in issues:
                    traiter_issue(issue, dry_run=args.dry_run)
            else:
                log.debug("Aucune issue en attente.")
            # Réarmement APRÈS traitement (issue #217). Le réarme d'avant-cycle
            # (ci-dessus) date le DÉBUT du travail, pas sa fin : le traitement
            # d'une (ou plusieurs) issue(s) peut s'étirer bien au-delà du délai
            # d'inactivité — plusieurs timeouts de 300s + retries en cascade, cf.
            # log watcher-scrabble 24/07/2026 : ~23 min pour une seule issue. Sans
            # ce second réarme, l'horloge resterait « périmée » (figée au début du
            # cycle) et le test d'extinction en tête du cycle SUIVANT se
            # déclencherait immédiatement après un travail réel qui vient tout
            # juste de se terminer (extinction ~14 s après un succès). On réarme
            # donc de nouveau ICI, avec l'instant réel de fin de traitement, dès
            # qu'au moins une issue traitable a été traitée ce cycle. L'extinction
            # reste possible quand plus rien n'est traitable (le flag est faux).
            if travail_a_faire:
                derniere_activite = time.monotonic()
        except KeyboardInterrupt:
            log.info("Watcher arrêté par l'utilisateur.")
            pid_file.unlink(missing_ok=True)
            sys.exit(0)
        except Exception as e:
            log.error(f"Erreur boucle principale : {e}")

        time.sleep(intervalle)

if __name__ == "__main__":
    main()

"""Case « Projet CCW » — chiffrement des tokens et génération automatique des
2 issues croisées (issue #559, 3/3 de la conception #553/#554).

Brique finale du chantier « Projet CCW » : relie l'interface web à ce qui
existe déjà — la paire de clés générée côté CCW (issue #554, 1/3) et le
traitement déterministe du champ `CREATION` dans `watcher.py` (#556, 2/3,
déjà validé en conditions réelles sur `rummikub`, #557). Module DÉDIÉ plutôt
que d'alourdir `app/nouveau_projet.py` (même séparation que `app/ccw.py`) :
appelé par le front-end APRÈS le succès de la création classique du projet
CCL (`np_cli.creer_projet`, route `/nouveau-projet`), jamais avant — voir
`bootstrap_projet_ccw` plus bas.

DÉCISION — cache local de la clé publique de bootstrap (point le plus ouvert
de la conception, #553 §5 point 1 implicite / #559 tâche 1) :
  La clé publique (`C:\\CCW\\cles_bootstrap\\bootstrap_publique.pem`, #554)
  n'est PAS récupérée par un aller-retour SSH à CHAQUE création de projet —
  cela réintroduirait exactement la dépendance à « CCW allumé » que ce
  chantier vise justement à éviter (la case doit fonctionner même PC
  éteint, #553 point 3). Elle est au contraire mise en CACHE localement,
  dans `configs/ccw_bootstrap_publique.pem` (gitignoré : état local de la
  machine CCL, pas du code — la clé n'est pas secrète en elle-même, mais
  spécifique à l'instance CCW courante et sans intérêt dans l'historique
  git, cf. REINSTALLATION_CCW.md §8 sur sa régénération à chaque
  réinstallation). Rafraîchissement MANUEL (bouton dédié dans le bloc
  d'instructions du formulaire → `rafraichir_cle_publique` ci-dessous),
  PAS automatique à chaque soumission — à déclencher après une (première
  génération ou) rotation de la paire de clés côté CCW. Réutilise le
  mécanisme SSH déjà en place et déjà testé (`app/ccw.py` :
  `_charger_config_ssh`/`OPTIONS_SSH`) pour le SEUL cas où une connexion à
  CCW est nécessaire dans tout ce module.

Chiffrement (BRIDGE_AGENT_DOC.md §16.6, à respecter EXACTEMENT — convention
déjà VALIDÉE par le déchiffrement réel côté `watcher.py`, #556/#557) :
RSA/OAEP-SHA256 via `openssl pkeyutl -encrypt`, sortie encodée en base64 sur
UNE SEULE ligne. `_chiffrer_token` ci-dessous est le miroir exact, côté
chiffrement, de `dechiffrer_token_bootstrap` (watcher.py).

Génération des 2 issues (modèle #553 §2.1) : deux issues INDÉPENDANTES sur
le dépôt Bridge_Agent (jamais celui du nouveau projet — c'est le canal
unifié `for-windows` de Bridge_Agent qui porte le bootstrap, cf. §16 du
DOC), liées par référence croisée une fois les deux numéros connus. Anti-
double-soumission : `_issue_ouverte_meme_titre` (app/issues.py, déjà en
place, #189), avec un titre déterministe par projet.
"""

import base64
import datetime
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from flask import jsonify, request

DOSSIER_SCRIPT = Path(__file__).resolve().parent.parent

# Cache local de la clé publique de bootstrap (voir décision en tête de
# fichier) — hors de configs/*.conf (le garde-fou §11 sur les .conf projets
# ne s'y applique pas, et ce n'est de toute façon pas un fichier projet).
CHEMIN_CLE_PUBLIQUE_CACHE = DOSSIER_SCRIPT / "configs" / "ccw_bootstrap_publique.pem"

# Chemin de la clé publique côté CCW — DOIT rester synchronisé avec
# $CheminPublique de provisioning/windows/provisionner.ps1 (issue #554, 1/3).
CHEMIN_CLE_PUBLIQUE_DISTANT = "C:/CCW/cles_bootstrap/bootstrap_publique.pem"

TIMEOUT_OPENSSL   = 30
TIMEOUT_SSH_CLE   = 30
TIMEOUT_GH        = 30

NOM_PROJET_BRIDGE_AGENT = "bridge_agent"


def _config_bridge_agent():
    """Config du projet bridge_agent lui-même (configs/bridge_agent.conf) —
    les 2 issues générées ci-dessous vivent TOUJOURS sur ce dépôt (canal
    unifié `for-windows`, jamais le dépôt du nouveau projet), cf. docstring
    de tête. Import différé (évite tout cycle avec app/projets.py)."""
    from app.projets import projet_par_nom
    return projet_par_nom(NOM_PROJET_BRIDGE_AGENT)


# ─── Cache local de la clé publique de bootstrap ───────────────────────────

def etat_cle_publique():
    """GET /projet-ccw/cle-publique/etat — présence/date du cache local, pour
    que le formulaire informe l'utilisateur AVANT la soumission plutôt que de
    découvrir l'absence de clé après coup (les 2 tokens auraient déjà été
    saisis pour rien)."""
    if not CHEMIN_CLE_PUBLIQUE_CACHE.is_file():
        return jsonify(presente=False)
    horodatage = datetime.datetime.fromtimestamp(CHEMIN_CLE_PUBLIQUE_CACHE.stat().st_mtime)
    return jsonify(presente=True, derniere_maj=horodatage.strftime("%Y-%m-%d %H:%M"))


def rafraichir_cle_publique():
    """POST /projet-ccw/rafraichir-cle — récupère `bootstrap_publique.pem`
    depuis CCW (SSH/scp) et rafraîchit le cache local. SEUL point de ce
    module qui exige CCW allumé — jamais appelé automatiquement à la
    création d'un projet (voir décision en tête de fichier). À relancer
    après une (première génération ou) rotation de la paire de clés côté
    CCW (#554, REINSTALLATION_CCW.md §8)."""
    from app.ccw import _charger_config_ssh, OPTIONS_SSH
    ctx, erreur = _charger_config_ssh()
    if erreur:
        return jsonify(succes=False, erreur=erreur)
    hote, utilisateur, cle_privee = ctx

    CHEMIN_CLE_PUBLIQUE_CACHE.parent.mkdir(parents=True, exist_ok=True)
    fd, chemin_tmp = tempfile.mkstemp(prefix="ccw-cle-pub-", suffix=".pem",
                                       dir=str(CHEMIN_CLE_PUBLIQUE_CACHE.parent))
    os.close(fd)
    try:
        res = subprocess.run(
            ["scp", "-i", cle_privee, *OPTIONS_SSH,
             f"{utilisateur}@{hote}:{CHEMIN_CLE_PUBLIQUE_DISTANT}", chemin_tmp],
            capture_output=True, text=True, timeout=TIMEOUT_SSH_CLE,
        )
    except subprocess.TimeoutExpired:
        return jsonify(succes=False,
            erreur="Délai dépassé en récupérant la clé publique (SSH) — CCW est-il allumé ?")
    except subprocess.SubprocessError as e:
        return jsonify(succes=False, erreur=f"Erreur SSH : {e}")

    if res.returncode != 0:
        Path(chemin_tmp).unlink(missing_ok=True)
        detail = (res.stderr or res.stdout or "").strip()
        return jsonify(succes=False,
            erreur=f"Échec de la récupération (code {res.returncode}). {detail} — "
                   "la paire de clés a-t-elle bien été générée côté CCW (provisionner.ps1, #554) ?")

    contenu = Path(chemin_tmp).read_text(encoding="utf-8", errors="replace")
    Path(chemin_tmp).unlink(missing_ok=True)
    if "BEGIN PUBLIC KEY" not in contenu:
        return jsonify(succes=False,
            erreur="Le fichier récupéré ne ressemble pas à une clé publique PEM — cache NON modifié.")

    CHEMIN_CLE_PUBLIQUE_CACHE.write_text(contenu, encoding="utf-8")
    return jsonify(succes=True, message="Clé publique de bootstrap rafraîchie.")


# ─── Chiffrement des tokens (§16.6 du DOC — miroir de dechiffrer_token_bootstrap) ─

def _chiffrer_token(token: str, chemin_cle_publique: Path) -> str:
    """Chiffre `token` avec la clé PUBLIQUE de bootstrap (RSA/OAEP-SHA256)
    puis encode le résultat en base64 SANS retour à la ligne (issue #556,
    BRIDGE_AGENT_DOC.md §16.6) — convention à NE PAS FAIRE DÉVIER : un
    mauvais padding ferait ÉCHOUER le déchiffrement côté watcher.py plutôt
    que de produire un résultat corrompu (propriété volontaire d'OAEP).
    Lève RuntimeError si openssl est absent ou échoue."""
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError("openssl introuvable sur le PATH (CCL) — impossible de chiffrer les tokens.")
    res = subprocess.run(
        [openssl, "pkeyutl", "-encrypt",
         "-pubin", "-inkey", str(chemin_cle_publique),
         "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"],
        input=token.encode("utf-8"), capture_output=True, timeout=TIMEOUT_OPENSSL,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"openssl pkeyutl -encrypt a échoué (code {res.returncode}) : "
            f"{res.stderr.decode('utf-8', errors='replace').strip()}"
        )
    return base64.b64encode(res.stdout).decode("ascii")


# ─── Construction des 2 issues (modèle #553 §2.1/§2.2/§2.3) ────────────────

def _titre_issue_ccl(nom: str) -> str:
    return f"Projet CCW — ajout de « {nom} » à la réinstallation (reinstaller_projets_ccw.ps1)"


def _titre_issue_ccw(nom: str) -> str:
    return f"Projet CCW — création du service dédié « {nom} »"


def _corps_issue_ccl(nom: str, depot: str, numero_ccw: int | None) -> str:
    from app.issues import formater_entete  # import différé (évite tout cycle, cf. _config_bridge_agent)
    entete = formater_entete("écriture", "normale", 300, "bridge_agent", complexite="rapide")
    reference = f"\nIssue CCW liée (création du service) : #{numero_ccw}.\n" if numero_ccw else ""
    corps = (
        "## Tâche\n\n"
        f"Ajouter le projet « {nom} » (dépôt {depot}) à la liste de "
        "réinstallation CCW (case « Projet CCW » du formulaire, issue #559) :\n\n"
        "1. `provisioning/windows/reinstaller_projets_ccw.ps1` — ajouter une "
        f'entrée `@{{ NomProjet = "{nom}"; Depot = "{depot}" }}` au tableau '
        "`$Projets` (source de vérité, issue #552).\n"
        "2. `provisioning/windows/REINSTALLATION_CCW.md` (§7) — ajouter la "
        "ligne correspondante au tableau de rappel (simple reproduction du "
        "tableau `$Projets` pour la lecture).\n"
        f"{reference}"
    )
    return f"{entete}\n\n{corps}"


def _corps_issue_ccw(nom: str, depot: str, topic: str,
                      gh_chiffre: str, oauth_chiffre: str, numero_ccl: int) -> str:
    # Format EXACT attendu par watcher.py::extraire_champs_creation /
    # creation_demandee (BRIDGE_AGENT_DOC.md §16.6) — six champs, dont les 4
    # premiers après COMPLEXITE forment le bloc CREATION_*, séparé du reste
    # de l'en-tête standard par une ligne vide (même mise en page que
    # l'issue de test réelle #557, déjà traitée avec succès par #556).
    from app.issues import formater_entete  # import différé (évite tout cycle, cf. _config_bridge_agent)
    entete = formater_entete("écriture", "normale", 600, "bridge_agent", complexite="normal")
    entete = "\n".join([
        entete,
        "",
        "| CREATION              | oui |",
        f"| CREATION_NOM_PROJET   | {nom} |",
        f"| CREATION_DEPOT        | {depot} |",
        f"| CREATION_TOPIC_NTFY   | {topic} |",
        f"| CREATION_GH_TOKEN     | {gh_chiffre} |",
        f"| CREATION_OAUTH_TOKEN  | {oauth_chiffre} |",
    ])
    corps = (
        f"\nBootstrap automatique d'un service CCW dédié pour « {nom} » "
        "(case « Projet CCW », issue #559) — traitement ENTIÈREMENT "
        "déterministe par `watcher.py` (#556), AUCUNE session `claude` "
        "invoquée (décision #554 §2.5). Si CCW est éteint à la réception : "
        "cette issue attend simplement dans la file, aucune action "
        "supplémentaire nécessaire.\n\n"
        f"Issue CCL liée (mise à jour de la réinstallation) : #{numero_ccl}.\n"
    )
    return f"{entete}\n{corps}"


# ─── Création d'issue via gh (anti-doublon + gh issue create) ──────────────

def _creer_issue_gh(cfg, titre: str, labels: str, corps: str) -> dict:
    """Crée une issue sur `cfg.depot` — même patron que `app.issues.envoyer`
    (anti-doublon `_issue_ouverte_meme_titre`, `--body-file` pour éviter tout
    enfer d'échappement/troncature argv), dupliqué ici plutôt qu'appelé à
    travers la route Flask (qui lit `request.json`, non réutilisable
    directement pour une création pilotée en Python). Retourne
    {succes, numero, url} ou {succes: False, erreur}."""
    from app.issues import _issue_ouverte_meme_titre

    titre = titre.strip()
    doublon = _issue_ouverte_meme_titre(cfg, titre)
    if doublon is not None:
        return {"succes": False, "erreur": f"Une issue portant ce titre est déjà ouverte : #{doublon}"}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(corps)
        chemin_body = f.name
    try:
        res = subprocess.run(
            ["gh", "issue", "create",
             "--repo",      cfg.depot,
             "--title",     titre,
             "--label",     labels,
             "--body-file", chemin_body],
            capture_output=True, text=True, timeout=TIMEOUT_GH,
        )
        if res.returncode != 0:
            return {"succes": False, "erreur": res.stderr.strip() or "Erreur inconnue de gh."}
        url = res.stdout.strip()
        try:
            numero = int(url.rsplit("/", 1)[-1])
        except ValueError:
            numero = None
        return {"succes": True, "url": url, "numero": numero}
    except subprocess.TimeoutExpired:
        return {"succes": False, "erreur": "Timeout (gh n'a pas répondu en 30s)."}
    except FileNotFoundError:
        return {"succes": False, "erreur": "gh introuvable dans le PATH."}
    except Exception as e:  # noqa: BLE001
        return {"succes": False, "erreur": str(e)}
    finally:
        os.unlink(chemin_body)


def _commenter_issue_gh(depot: str, numero: int, message: str) -> bool:
    """Poste un commentaire (référence croisée) — mêmes garanties que
    `watcher.commenter_issue` (--body-file), dupliqué ici car ce module
    tourne dans le processus Flask, pas dans un watcher.py déjà configuré
    sur ce dépôt précis."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(message)
        chemin_body = f.name
    try:
        res = subprocess.run(
            ["gh", "issue", "comment", str(numero), "--repo", depot, "--body-file", chemin_body],
            capture_output=True, text=True, timeout=TIMEOUT_GH,
        )
        return res.returncode == 0
    except subprocess.SubprocessError:
        return False
    finally:
        os.unlink(chemin_body)


# ─── Route principale ───────────────────────────────────────────────────────

def _depot_existe_deja(depot: str) -> bool:
    """Vérifie que le dépôt cible existe déjà sur GitHub — garde-fou anti
    chicken-and-egg (issue #560) : cette route est appelée séparément, via le
    bouton dédié « Finaliser le bootstrap CCW » du formulaire, APRÈS que
    l'utilisateur a créé un token GitHub fine-grained scopé dessus — ce qui
    n'est possible que si le dépôt existe déjà. Revérifié ici côté serveur
    (jamais confiance seule au JS, même logique que la validation des
    tokens juste en dessous) : si le dépôt n'existe pas, on refuse avant
    même de chiffrer quoi que ce soit ou de créer une issue. Import différé,
    comme `_config_bridge_agent`, pour éviter tout cycle avec
    `app/nouveau_projet.py`."""
    from app.nouveau_projet import np_cli
    return np_cli.depot_existe(depot)


def bootstrap_projet_ccw():
    """POST /projet-ccw/bootstrap — chiffrement des 2 tokens + génération des
    2 issues croisées. Appelée par le front-end SÉPARÉMENT de la création du
    projet CCL, uniquement au clic sur le bouton dédié « Finaliser le
    bootstrap CCW » qui n'apparaît qu'une fois le dépôt confirmé créé (issue
    #560, corrigeant l'ordre du flux #559 — un token GitHub fine-grained ne
    peut être scopé que sur un dépôt qui existe déjà, ce qui exclut de le
    demander dans le même écran/submit que `POST /nouveau-projet`) : reçoit
    {nom, depot, topic, gh_token, oauth_token} — les 3 premiers identiques à
    ceux déjà validés/soumis à `/nouveau-projet`, pas resaisis.

    Validation stricte (déjà faite côté client, revérifiée ici — jamais
    confiance seule au JS) : les 2 tokens sont obligatoires, et le dépôt
    doit réellement exister (`_depot_existe_deja`, #560). Échec partiel
    assumé (§4 de la conception #553, pas de mécanisme transactionnel) :
    si l'issue CCW échoue après que l'issue CCL a réussi, l'issue CCL reste
    (son numéro est renvoyé) — Alain peut réessayer manuellement le volet
    CCW sans dupliquer le volet CCL."""
    data        = request.json or {}
    nom         = (data.get("nom")   or "").strip()
    depot       = (data.get("depot") or "").strip()
    topic       = (data.get("topic") or "").strip()
    gh_token    = data.get("gh_token")    or ""
    oauth_token = data.get("oauth_token") or ""

    if not nom or not depot or not topic:
        return jsonify(succes=False, erreur="nom/depot/topic requis (projet CCL non transmis correctement).")
    if not gh_token or not oauth_token:
        return jsonify(succes=False,
            erreur="Les deux tokens (GH_TOKEN et CLAUDE_CODE_OAUTH_TOKEN) sont requis pour « Projet CCW ».")

    if not CHEMIN_CLE_PUBLIQUE_CACHE.is_file():
        return jsonify(succes=False,
            erreur="Clé publique de bootstrap absente du cache local — cliquez « Rafraîchir la "
                   "clé » (CCW doit être allumé et joignable en SSH) avant de soumettre « Projet CCW ».")

    # Garde-fou #560 : sans ce contrôle, un appel prématuré (avant la
    # création réelle du dépôt) laisserait chiffrer/poster des tokens pour un
    # dépôt inexistant — silencieusement inutile côté CCW.
    if not _depot_existe_deja(depot):
        return jsonify(succes=False,
            erreur=f"Le dépôt {depot} n'existe pas encore sur GitHub — créez d'abord le projet "
                   "(bouton « Créer le projet ») avant de finaliser le bootstrap CCW.")

    try:
        gh_chiffre    = _chiffrer_token(gh_token, CHEMIN_CLE_PUBLIQUE_CACHE)
        oauth_chiffre = _chiffrer_token(oauth_token, CHEMIN_CLE_PUBLIQUE_CACHE)
    except RuntimeError as e:
        return jsonify(succes=False, erreur=f"Chiffrement des tokens impossible : {e}")

    cfg_ba = _config_bridge_agent()
    if not cfg_ba:
        return jsonify(succes=False,
            erreur="Projet bridge_agent introuvable côté CCL (configs/bridge_agent.conf) — impossible "
                   "de créer les issues de bootstrap.")

    # 1. Issue CCL (mise à jour de la réinstallation) — créée en premier,
    #    sans encore connaître le numéro de l'issue CCW (référence croisée
    #    ajoutée en commentaire une fois celle-ci créée, cf. §2.1 de #553).
    res_ccl = _creer_issue_gh(cfg_ba, _titre_issue_ccl(nom),
                               "bridge,for-linux,mode_write", _corps_issue_ccl(nom, depot, None))
    if not res_ccl["succes"]:
        return jsonify(succes=False, erreur=f"Issue CCL (réinstallation) : {res_ccl['erreur']}")

    # 2. Issue CCW (canal unifié for-windows) — porte le bootstrap réel.
    res_ccw = _creer_issue_gh(cfg_ba, _titre_issue_ccw(nom),
                               "bridge,for-windows,mode_write",
                               _corps_issue_ccw(nom, depot, topic, gh_chiffre, oauth_chiffre,
                                                 res_ccl["numero"]))
    if not res_ccw["succes"]:
        return jsonify(succes=False,
            erreur=f"Issue CCL #{res_ccl['numero']} créée, mais l'issue CCW a échoué : "
                   f"{res_ccw['erreur']} — relancer manuellement la création du service CCW.",
            issue_ccl_numero=res_ccl["numero"], issue_ccl_url=res_ccl["url"])

    # 3. Référence croisée dans l'autre sens (best-effort — un échec ici ne
    #    remet pas en cause le succès des 2 créations).
    _commenter_issue_gh(cfg_ba.depot, res_ccl["numero"],
                         f"Issue CCW liée (création du service) : #{res_ccw['numero']}.")

    # 4. Démarrage automatique du watcher for-linux de bridge_agent (même
    #    logique que app.issues.envoyer pour toute issue for-linux, issue
    #    #202) — best-effort, ne doit jamais transformer un succès en échec.
    try:
        from app.watchers import demarrer_watcher
        demarrer_watcher(cfg_ba, forcer=False)
    except Exception:
        pass

    return jsonify(
        succes=True,
        issue_ccl_numero=res_ccl["numero"], issue_ccl_url=res_ccl["url"],
        issue_ccw_numero=res_ccw["numero"], issue_ccw_url=res_ccw["url"],
    )

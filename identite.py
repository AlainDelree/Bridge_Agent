#!/usr/bin/env python3
"""identite.py — identifiant GitHub et autres valeurs propres à l'installation
en cours (issue #859).

Bridge_Agent est pensé pour être installé par quelqu'un d'autre qu'Alain
(compte GitHub différent, nom d'utilisateur Windows différent pour le PC fixe
CCW) : ce module est la SEULE source de vérité pour ces valeurs — plus aucun
autre fichier du dépôt ne doit coder en dur "AlainDelree" ou "AlainW" comme
IDENTIFIANT (les noms de PROJETS réels, type AlChess, restent eux inchangés,
ce ne sont pas des identifiants de compte).

Deux sources, dans cet ordre de priorité :
  1. `identite_locale.conf` à la racine du dépôt (format "CLÉ = valeur",
     comme `configs/*.conf`, mais délibérément HORS de ce dossier — §12 de
     BRIDGE_AGENT_DOC.md interdit à CCL/CCW toute écriture dans
     `configs/*.conf`, et ce fichier de réglages doit pouvoir y échapper même
     par accident). Gitignoré, jamais committé : propre à chaque machine.
       COMPTE_GITHUB   = <login GitHub à utiliser>
       UTILISATEUR_SSH = <compte Windows du PC fixe CCW>
  2. à défaut de COMPTE_GITHUB dans ce fichier : le compte GitHub connecté
     localement (`gh api user --jq .login`). Sur la machine d'Alain, c'est
     déjà `AlainDelree` — comportement inchangé sans rien configurer de plus.
     UTILISATEUR_SSH n'a pas d'équivalent auto-détectable (ce n'est pas une
     notion GitHub) : à défaut de ce fichier, "AlainW" reste le repli
     historique (seule installation existante à ce jour).

compte_github() est mis en cache (une résolution par processus — un appel
`gh` à chaque cycle de polling du watcher serait superflu) : voir watcher.py
(AUTEURS_AUTORISES, garde-fou §8), nouveau_projet.py (propriétaire de dépôt
par défaut) et app/ccw.py (utilisateur SSH par défaut)."""

import functools
import os
import subprocess
from pathlib import Path

RACINE = Path(__file__).resolve().parent
FICHIER_IDENTITE_LOCALE = RACINE / "identite_locale.conf"

# Repli historique de l'utilisateur SSH/Windows du PC fixe CCW — seule
# installation existante à ce jour, sans équivalent auto-détectable comme
# `gh` pour le compte GitHub (voir compte_github ci-dessous).
UTILISATEUR_SSH_HISTORIQUE = "AlainW"


def _lire_identite_locale() -> dict:
    """Lecteur 'CLÉ = valeur' minimal, même format que lire_conf()
    (watcher.py) / _lire_conf_ssh() (app/ccw.py) mais module autonome : ce
    fichier est lu par des modules qui ne doivent pas dépendre les uns des
    autres (watcher.py, nouveau_projet.py, app/ccw.py). Dict vide si le
    fichier n'existe pas ou est illisible."""
    if not FICHIER_IDENTITE_LOCALE.exists():
        return {}
    try:
        brut = FICHIER_IDENTITE_LOCALE.read_text(encoding="utf-8")
    except OSError:
        return {}
    donnees: dict[str, str] = {}
    for ligne in brut.splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cle, sep, valeur = ligne.partition("=")
        if sep:
            donnees[cle.strip().upper()] = valeur.strip()
    return donnees


@functools.lru_cache(maxsize=1)
def compte_github() -> str | None:
    """Identifiant du compte GitHub à utiliser comme source de vérité unique
    — voir le docstring du module pour l'ordre de priorité. None si ni le
    fichier local ni `gh` n'ont pu fournir de valeur (ex. `gh` absent ou non
    authentifié, et aucun identite_locale.conf) : les appelants
    sécurité-critiques (watcher.py, AUTEURS_AUTORISES) doivent alors REFUSER
    de traiter les issues plutôt que d'ouvrir l'accès à tout le monde."""
    local = _lire_identite_locale().get("COMPTE_GITHUB")
    if local:
        return local
    try:
        res = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    login = res.stdout.strip()
    return login or None


def valeur_locale(cle: str, defaut: str = "") -> str:
    """Valeur brute de `cle` dans `identite_locale.conf`, ou `defaut` si le
    fichier est absent ou ne contient pas cette clé — lecture publique
    générique pour d'autres réglages propres à l'installation locale que
    COMPTE_GITHUB/UTILISATEUR_SSH (ex. MAJ_AUTO_DEPOT et ses compagnons,
    issue #868). Volontairement PAS mise en cache comme compte_github() : ce
    fichier n'est relu qu'une poignée de fois par processus appelant (ex. une
    fois au démarrage de new_issue.py), le coût d'une relecture par appel est
    négligeable."""
    return _lire_identite_locale().get(cle.upper(), defaut)


def utilisateur_ssh_defaut() -> str:
    """Utilisateur SSH/Windows par défaut proposé pour le PC fixe CCW
    (app/ccw.py), utilisé seulement si ni la variable d'environnement
    CCW_SSH_UTILISATEUR ni la clé UTILISATEUR de configs/ccw_ssh.conf ne sont
    renseignées. Lit UTILISATEUR_SSH dans identite_locale.conf ; à défaut,
    UTILISATEUR_SSH_HISTORIQUE ("AlainW", comportement inchangé pour
    l'installation d'Alain)."""
    return _lire_identite_locale().get("UTILISATEUR_SSH") or UTILISATEUR_SSH_HISTORIQUE


# Valeurs considérées comme "actif" pour un réglage booléen de
# identite_locale.conf — même ensemble que celui déjà utilisé en dur par
# watcher.tenter_maj_auto_demarrage() pour MAJ_AUTO_DEPOT (issue #868), repris
# ici tel quel pour COPIE_NON_PROPRIETAIRE plutôt que dupliqué sans nom.
VALEURS_VRAIES = ("true", "1", "oui", "yes", "vrai")


def copie_non_proprietaire() -> bool:
    """True si `identite_locale.conf` déclare cette copie de l'outil comme
    n'appartenant pas à Alain (`COPIE_NON_PROPRIETAIRE = oui`, issue #869) —
    toute autre valeur, ou absence de la clé, renvoie False : comportement
    STRICTEMENT INCHANGÉ pour les installations d'Alain (ThinkPad, PC fixe),
    dont `BRIDGE_AGENT_DOC.md` reste la référence des tableaux de projets.

    Pensé pour une copie tenue à jour par `git pull --ff-only` (issue #868,
    `MAJ_AUTO_DEPOT`) chez un tiers sans droits d'écriture sur le dépôt
    d'Alain (ex. ami sur PC Windows seul) : sans ce réglage, créer ou
    supprimer un projet dessus réécrirait les tableaux §2/§7 avec les seuls
    projets de ce tiers, créerait un commit local faisant diverger la copie
    de celle d'Alain (tous les `git pull --ff-only` suivants refusés), puis
    tenterait un push qui échouerait — ou, pire, écraserait la doc d'Alain
    si les droits d'écriture étaient accordés. Voir
    `regenerer_tableaux_projets.regenerer_local()` pour l'effet concret de
    ce réglage (tableaux écrits dans `PROJETS_LOCAUX.md`, fichier local
    gitignoré, à la place de `BRIDGE_AGENT_DOC.md` — jamais d'écriture, de
    commit ni de push sur la doc de l'outil dans ce cas)."""
    return _lire_identite_locale().get("COPIE_NON_PROPRIETAIRE", "").strip().lower() in VALEURS_VRAIES


# Valeurs explicitement "non" pour un réglage booléen à trois états
# (actif / inactif / absent), où l'absence de la clé a un sens DIFFÉRENT de
# la valeur "non" explicite — utilisé uniquement par DEPOT_PRIVE_PAR_DEFAUT
# (issue #879) ci-dessous. COPIE_NON_PROPRIETAIRE/MACHINE_SEULE n'en ont pas
# besoin : pour eux, absent et "non" se comportent déjà pareil (False).
VALEURS_FAUSSES = ("false", "0", "non", "no", "faux")


def depot_public_par_defaut() -> bool:
    """True si la case « Dépôt public » du formulaire de nouveau projet doit
    être COCHÉE par défaut (dépôt créé public sauf décision contraire de
    l'utilisateur) — issue #879. `DEPOT_PRIVE_PAR_DEFAUT` de
    `identite_locale.conf` prime sur `copie_non_proprietaire()` ci-dessus,
    dans les DEUX sens :
      - DEPOT_PRIVE_PAR_DEFAUT = oui : privé par défaut (renvoie False), même
        sans COPIE_NON_PROPRIETAIRE — pour qui veut ce choix sur SA PROPRE
        installation (ex. Alain, sur la sienne).
      - DEPOT_PRIVE_PAR_DEFAUT = non : public par défaut (renvoie True), même
        avec COPIE_NON_PROPRIETAIRE actif.
      - absent (cas normal, aucun des deux réglages ne s'en sert) : repli sur
        `not copie_non_proprietaire()` — public par défaut comme aujourd'hui,
        SAUF sur une copie non-propriétaire de l'outil (issue #869, ex. ami
        sur PC Windows seul) où le contenu d'un projet n'a pas à devenir
        public par simple oubli : privé par défaut dans ce seul cas."""
    brut = _lire_identite_locale().get("DEPOT_PRIVE_PAR_DEFAUT", "").strip().lower()
    if brut in VALEURS_VRAIES:
        return False
    if brut in VALEURS_FAUSSES:
        return True
    return not copie_non_proprietaire()


def relecture_disponible() -> bool:
    """True si l'outil de relecture (`Relecture_Bridge`, issue #578) est
    effectivement présent sur CETTE machine — détection la plus simple et la
    plus fiable après lecture de son usage ci-dessous : l'existence du
    script `installer.sh` que l'encart de rappel de l'interface invite à
    relancer (static/js/app.js::afficherRappelInstaller). Ce chemin
    (`~/Relecture_Bridge/installer.sh`) est propre à l'installation d'Alain
    — absent sur la machine d'un tiers (copie non-propriétaire ou non),
    d'où cette vérification plutôt qu'un affichage inconditionnel de
    l'encart (issue #870). Comportement inchangé sur la machine d'Alain,
    où ce chemin existe réellement."""
    return (Path.home() / "Relecture_Bridge" / "installer.sh").exists()


def machine_seule() -> bool:
    """True si `identite_locale.conf` déclare cette machine comme jouant
    TOUS les rôles, sans second poste CCW délégué (`MACHINE_SEULE = oui`,
    issue #870) — toute autre valeur, ou absence de la clé, renvoie False :
    comportement STRICTEMENT INCHANGÉ pour les installations d'Alain
    (ThinkPad, PC fixe CCW), où ce réglage n'est pas posé.

    Nom repris de la « solution de fond » déjà évoquée (non implémentée) au
    §16.1 de `BRIDGE_AGENT_DOC.md` et au §4 de
    `provisioning/windows/ROUTAGE_LABELS_POSTE_SEUL.md` (issue #866/#867) —
    mais son PÉRIMÈTRE ici est volontairement plus étroit : seulement
    masquer, côté interface web, l'onglet « CCW » et la case « Projet CCW »
    du formulaire de nouveau projet (qui n'ont aucune utilité, et induisent
    en erreur, sur un poste qui n'a pas de second poste joignable). Le
    routage effectif des labels `for-linux`/`for-windows` décrit dans ces
    deux documents (issue #867) reste hors périmètre — ce réglage ne
    l'implémente PAS, il ne fait que masquer ces deux éléments d'interface."""
    return _lire_identite_locale().get("MACHINE_SEULE", "").strip().lower() in VALEURS_VRAIES


def token_github_env_present() -> bool:
    """True si `GH_TOKEN` ou `GITHUB_TOKEN` est présent (non vide) dans
    l'environnement du PROCESSUS ACTUEL (celui de l'interface web,
    `new_issue.py`) — issue #882. C'est un FAIT lu directement dans
    `os.environ`, pas une supposition sur le mode d'authentification
    réellement utilisé par `gh` : `gh` (CLI GitHub) donne TOUJOURS la
    priorité à `GH_TOKEN`/`GITHUB_TOKEN` sur sa propre authentification
    (`gh auth login`, jeton de trousseau) dès que l'une de ces deux
    variables est présente dans son environnement — comportement documenté
    de `gh` lui-même, pas une hypothèse de ce module.

    Sert à décider si l'avertissement « Dépôt privé : GH_TOKEN doit avoir
    les permissions nécessaires… » (`modale_nouveau_projet.html`, issue
    #529) s'applique : sans l'une de ces deux variables, `gh repo create`
    passe par le jeton de trousseau de `gh auth login`, qui a en général
    déjà toutes les permissions nécessaires accordées à la connexion —
    l'avertissement, pensé pour un jeton scopé étroitement (type
    fine-grained, cf. `CREATION_GH_TOKEN` du bootstrap CCW, `app/ccw.py`),
    ne le concerne pas dans ce cas. Sur l'installation d'Alain, où
    `new_issue.py` tourne avec `GH_TOKEN` exporté dans son environnement,
    cette fonction renvoie True et l'avertissement reste affiché, inchangé.

    Volontairement PAS mise en cache (contrairement à compte_github()) :
    lire deux variables d'environnement est gratuit, et ce fait pourrait en
    théorie changer entre deux requêtes si le processus est relancé avec un
    environnement différent."""
    return bool((os.environ.get("GH_TOKEN") or "").strip()
                or (os.environ.get("GITHUB_TOKEN") or "").strip())


def diagnostic_copie() -> bool:
    """True si `identite_locale.conf` active le journal de diagnostic durable
    de la copie presse-papier de l'onglet Résultats (`DIAGNOSTIC_COPIE = oui`,
    issue #878) — toute autre valeur, ou absence de la clé, renvoie False :
    DÉSACTIVÉ PAR DÉFAUT, comportement inchangé tant que ce réglage n'est pas
    posé.

    Enquête sur des clics « sans effet » sur la case à cocher de copie,
    intermittents, juste après un redessin de ligne (fin d'issue en direct)
    ou après une longue inactivité de l'onglet (reconnexion du flux /stream).
    Lu UNE SEULE FOIS au démarrage du serveur (app/vues.py::index), transmis à
    la page via `window.DIAGNOSTIC_COPIE` (templates/fragments/scripts.html)
    — PAS un réglage côté navigateur (localStorage) : il doit survivre aux
    rechargements, aux changements de navigateur et aux fermetures d'onglet,
    ce qu'un réglage par onglet ne permettrait pas.

    Pour l'activer : ajouter `DIAGNOSTIC_COPIE = oui` dans
    `identite_locale.conf` (racine du dépôt) puis relancer `new_issue.py`.
    Journal écrit par `app/diagnostic_copie.py` dans
    `logs/diagnostic_copie.log` (gitignoré, taille bornée avec rotation) —
    une ligne par clic sur une case de copie, voir ce module et
    `static/js/socle/diagnostic_copie.js` pour le détail des champs et
    `VERIFICATIONS_MANUELLES.md` (section issue #878) pour quoi y relever."""
    return _lire_identite_locale().get("DIAGNOSTIC_COPIE", "").strip().lower() in VALEURS_VRAIES

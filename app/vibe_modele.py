"""Réglage du modèle actif de l'agent Vibe (issue #766).

``~/.vibe/config.toml`` est un fichier de COMPTE (Mistral), pas de projet :
il s'applique à TOUS les projets qui tournent sur cet agent, quel que soit le
projet actuellement sélectionné dans l'interface. Ces routes ne prennent donc
pas de ``<nom_projet>`` — même famille que ``app/son.py`` (réglage global de
la machine, pas du ``.conf`` d'un projet) — et vivent dans leur PROPRE onglet
(``fragments/onglet_vibe.html``), pas dans l'onglet Configuration (qui édite
le ``.conf`` d'un projet).

Forme réelle du fichier (constatée en lisant ``~/.vibe/config.toml`` et le
code source de l'outil installé — ``vibe.core.config.vibe_schema``/``models``
— plutôt que supposée ; aucune session Vibe réelle lancée, consigne héritée
des issues #760/#761) ::

    active_model = "devstral2"
    [[models]]
    name = "mistral-vibe-cli-latest"
    provider = "mistral"
    alias = "devstral2"
    input_price = 0.4
    output_price = 2.0

- ``name``/``provider``/``alias`` sont les seuls champs que Vibe exige pour
  qu'une entrée survive à sa réconciliation (``_REQUIRED_MODEL_FIELDS`` dans
  ``vibe.app_server._config_write``) ; tout le reste (``input_price``,
  ``display_name``, ``temperature``…) a une valeur par défaut côté outil.
  Plutôt que de recopier ici la liste complète (qui se périmerait au premier
  champ ajouté par une future version de Vibe), ``_schema()`` ci-dessous
  l'INTROSPECTE à chaque lecture à partir des entrées réellement présentes
  dans le fichier — ``CHAMPS_REQUIS_PAR_DEFAUT`` ne sert que de repli tant
  qu'aucune entrée n'existe encore à observer (section inoffensive).

- Vibe RÉÉCRIT ce fichier à chaque démarrage (réconciliation avec le compte) :
  toute écriture d'ici doit donc préserver ce qu'elle ne gère pas plutôt que
  de régénérer le fichier à partir d'une représentation reconstruite.
  Lecture : ``tomllib`` (stdlib, lecture seule) suffit et donne la sémantique
  TOML complète. Écriture : CHIRURGICALE au niveau ligne (``_segments_modeles``
  ci-dessous) — seules les lignes concernées par l'opération demandée sont
  touchées, tout le reste du texte d'origine (commentaires, réglages inconnus,
  autres blocs ``[[models]]``) est recopié tel quel.

- Alias intégrés : un seul est garanti présent sur toute installation Vibe
  (``mistral-medium-3.5``, le modèle par défaut du schéma — voir
  ``DEFAULT_ACTIVE_MODEL_CONFIG`` dans ``vibe.core.config.vibe_schema``). Le
  compte Mistral peut en exposer d'autres (admin/GrowthBook), impossibles à
  énumérer depuis ce seul fichier sans appel réseau au compte —
  ``ALIAS_RESERVES_CONNUS`` reste donc un filet BEST-EFFORT (avertissement,
  pas un blocage) : la seule collision certaine, et donc bloquée sans
  confirmation possible, est un doublon d'alias AU SEIN du fichier lui-même.
"""

import re
import shutil
import time
import tomllib
from pathlib import Path

from flask import jsonify, request

CHEMIN_VIBE_CONFIG = Path.home() / ".vibe" / "config.toml"
DOSSIER_SAUVEGARDES = Path.home() / ".vibe" / "bridge_sauvegardes"
NB_SAUVEGARDES_CONSERVEES = 10

ALIAS_RESERVES_CONNUS = {"mistral-medium-3.5"}

# Repli tant qu'aucune entrée [[models]] n'existe encore à introspecter.
CHAMPS_REQUIS_PAR_DEFAUT = ("name", "provider", "alias")

_RE_ENTETE_MODELES = re.compile(r"^\s*\[\[\s*models\s*\]\]\s*(#.*)?\s*$")
_RE_ENTETE_TABLE = re.compile(r"^\s*\[")
_RE_ACTIVE_MODEL = re.compile(r"^\s*active_model\s*=")
_RE_CLE_TOML = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*")


def _vibe_installe() -> bool:
    return shutil.which("vibe") is not None


def _lire_texte() -> str | None:
    try:
        return CHEMIN_VIBE_CONFIG.read_text(encoding="utf-8")
    except OSError:
        return None


def _segments_modeles(lignes: list[str]) -> list[tuple[int, int]]:
    """Bornes [début, fin) de chaque bloc ``[[models]]`` du fichier, par
    numéro de ligne. Un bloc se termine à l'en-tête de table suivant (n'importe
    lequel, ``[[models]]`` ou non) ou à la fin du fichier. Ne gère pas une
    chaîne TOML multi-lignes commençant une ligne par ``[`` à l'intérieur d'un
    bloc — absent de tout fichier produit par Vibe observé (valeurs de modèle
    toujours scalaires ou tableaux en ligne)."""
    segments = []
    debut = None
    for i, ligne in enumerate(lignes):
        if _RE_ENTETE_MODELES.match(ligne):
            if debut is not None:
                segments.append((debut, i))
            debut = i
            continue
        if debut is not None and _RE_ENTETE_TABLE.match(ligne):
            segments.append((debut, i))
            debut = None
    if debut is not None:
        segments.append((debut, len(lignes)))
    return segments


def _alias_du_segment(lignes: list[str], debut: int, fin: int) -> str | None:
    bloc = "".join(lignes[debut:fin])
    try:
        donnees = tomllib.loads(bloc)
    except tomllib.TOMLDecodeError:
        return None
    modeles = donnees.get("models") or []
    if not modeles or not isinstance(modeles[0], dict):
        return None
    return modeles[0].get("alias")


def _schema(modeles: list[dict]) -> dict:
    """Détermine les champs requis/connus à PARTIR des entrées réellement
    présentes dans le fichier (jamais d'une liste figée dans le code, voir
    docstring du module)."""
    if not modeles:
        return {"champs_requis": list(CHAMPS_REQUIS_PAR_DEFAUT), "champs_connus": {}}
    cles_par_modele = [set(m.keys()) for m in modeles]
    requis = set.intersection(*cles_par_modele)
    toutes = set.union(*cles_par_modele)
    optionnels = toutes - requis
    connus = {}
    for cle in optionnels:
        valeurs = [m[cle] for m in modeles if cle in m]
        numerique = bool(valeurs) and all(
            isinstance(v, (int, float)) and not isinstance(v, bool) for v in valeurs
        )
        connus[cle] = "nombre" if numerique else "texte"
    return {"champs_requis": sorted(requis) or list(CHAMPS_REQUIS_PAR_DEFAUT), "champs_connus": connus}


def _etat() -> dict:
    """État complet consommé par l'interface : disponibilité, modèle actif,
    modèles déclarés (avec ``actif``), schéma introspecté pour le formulaire
    d'ajout. Ne lève jamais — absence du fichier/de l'outil = section
    inoffensive, pas une erreur (point de vigilance de l'issue #766)."""
    base = {
        "disponible": False,
        "vibe_installe": _vibe_installe(),
        "fichier_existe": CHEMIN_VIBE_CONFIG.exists(),
        "modele_actif": None,
        "modeles": [],
        "schema": _schema([]),
        "alias_reserves_connus": sorted(ALIAS_RESERVES_CONNUS),
    }
    if not base["fichier_existe"]:
        return base

    texte = _lire_texte()
    if texte is None:
        return {**base, "erreur": "fichier illisible"}

    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        return {**base, "erreur": f"TOML invalide : {e}"}

    actif = donnees.get("active_model") or None
    modeles = []
    for m in donnees.get("models") or []:
        if not isinstance(m, dict) or "alias" not in m:
            continue
        entree = dict(m)
        entree["actif"] = entree["alias"] == actif
        modeles.append(entree)

    return {
        **base,
        "disponible": True,
        "modele_actif": actif,
        "modeles": modeles,
        "schema": _schema([{k: v for k, v in m.items() if k != "actif"} for m in modeles]),
    }


def _sauvegarder() -> Path | None:
    """Copie de sauvegarde datée avant toute écriture (point de vigilance de
    l'issue #766 : le fichier n'est pas versionné et vit hors du dépôt).
    Conserve les ``NB_SAUVEGARDES_CONSERVEES`` dernières, purge le reste."""
    if not CHEMIN_VIBE_CONFIG.exists():
        return None
    DOSSIER_SAUVEGARDES.mkdir(parents=True, exist_ok=True)
    horodatage = time.strftime("%Y%m%d-%H%M%S")
    cible = DOSSIER_SAUVEGARDES / f"config-{horodatage}.toml"
    compteur = 1
    while cible.exists():
        cible = DOSSIER_SAUVEGARDES / f"config-{horodatage}-{compteur}.toml"
        compteur += 1
    shutil.copy2(CHEMIN_VIBE_CONFIG, cible)
    for ancienne in sorted(DOSSIER_SAUVEGARDES.glob("config-*.toml"))[:-NB_SAUVEGARDES_CONSERVEES]:
        ancienne.unlink(missing_ok=True)
    return cible


def _ecrire_si_valide(nouveau_texte: str) -> tuple[bool, str]:
    """N'écrit JAMAIS un résultat qui laisserait le fichier sans modèle actif
    valide (point de vigilance de l'issue #766) — valide le texte produit
    AVANT de l'écrire, pas après."""
    try:
        donnees = tomllib.loads(nouveau_texte)
    except tomllib.TOMLDecodeError as e:
        return False, f"écriture annulée : résultat TOML invalide ({e})"
    actif = donnees.get("active_model") or ""
    alias_connus = {m.get("alias") for m in donnees.get("models") or [] if isinstance(m, dict)}
    if not actif or actif not in alias_connus:
        return False, "écriture annulée : le résultat n'aurait plus de modèle actif valide"
    CHEMIN_VIBE_CONFIG.write_text(nouveau_texte, encoding="utf-8")
    return True, ""


def _toml_valeur(valeur) -> str:
    if isinstance(valeur, bool):
        return "true" if valeur else "false"
    if isinstance(valeur, (int, float)):
        return str(valeur)
    texte = str(valeur)
    texte = (texte.replace("\\", "\\\\").replace('"', '\\"')
             .replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r"))
    return f'"{texte}"'


def _definir_actif(alias: str) -> tuple[bool, str]:
    texte = _lire_texte()
    if texte is None:
        return False, "fichier config.toml introuvable"
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        return False, f"fichier config.toml invalide : {e}"

    alias_connus = {m.get("alias") for m in donnees.get("models") or [] if isinstance(m, dict)}
    if alias not in alias_connus:
        return False, f"alias inconnu dans le fichier : {alias!r}"
    if donnees.get("active_model") == alias:
        return True, ""

    lignes = texte.splitlines(keepends=True)
    segments = _segments_modeles(lignes)

    def dans_un_segment(i: int) -> bool:
        return any(debut <= i < fin for debut, fin in segments)

    remplace = False
    for i, ligne in enumerate(lignes):
        if dans_un_segment(i):
            continue
        if _RE_ACTIVE_MODEL.match(ligne):
            lignes[i] = f'active_model = "{alias}"\n'
            remplace = True
            break
    if not remplace:
        lignes.insert(0, f'active_model = "{alias}"\n')

    _sauvegarder()
    return _ecrire_si_valide("".join(lignes))


def _ajouter_modele(champs: dict, forcer: bool) -> tuple[bool, str, dict]:
    texte = _lire_texte()
    if texte is None:
        return False, "fichier config.toml introuvable", {}
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        return False, f"fichier config.toml invalide : {e}", {}

    modeles_bruts = [m for m in donnees.get("models") or [] if isinstance(m, dict)]
    alias_existants = {m.get("alias") for m in modeles_bruts}
    schema = _schema(modeles_bruts)

    alias = str(champs.get("alias", "")).strip()
    if not alias:
        return False, "alias requis", {}
    if alias in alias_existants:
        return False, (
            f"un modèle porte déjà l'alias {alias!r} dans ce fichier — "
            "collision certaine (l'un des deux serait silencieusement "
            "ignoré), rejetée"
        ), {}

    def _vide(cle: str) -> bool:
        valeur = champs.get(cle)
        if isinstance(valeur, (int, float)) and not isinstance(valeur, bool):
            return False
        return not str(valeur or "").strip()

    manquants = [c for c in schema["champs_requis"] if _vide(c)]
    if manquants:
        return False, f"champ(s) requis manquant(s) : {', '.join(manquants)}", {}

    if alias in ALIAS_RESERVES_CONNUS and not forcer:
        return False, (
            f"l'alias {alias!r} correspond à un modèle intégré connu de "
            "Vibe — Vibe risque de l'écraser silencieusement à son prochain "
            "démarrage (réconciliation avec le compte). Confirmez "
            "explicitement pour l'ajouter quand même."
        ), {"necessite_confirmation": True}

    lignes_bloc = ["[[models]]\n"]
    for cle, valeur in champs.items():
        cle = str(cle).strip()
        if cle == "actif" or not _RE_CLE_TOML.fullmatch(cle):
            continue
        lignes_bloc.append(f"{cle} = {_toml_valeur(valeur)}\n")

    prefixe = texte if texte.endswith("\n") else texte + "\n"
    nouveau_texte = prefixe + "\n" + "".join(lignes_bloc)

    _sauvegarder()
    ok, err = _ecrire_si_valide(nouveau_texte)
    return ok, err, {}


def _retirer_modele(alias: str) -> tuple[bool, str]:
    texte = _lire_texte()
    if texte is None:
        return False, "fichier config.toml introuvable"
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        return False, f"fichier config.toml invalide : {e}"

    alias_connus = {m.get("alias") for m in donnees.get("models") or [] if isinstance(m, dict)}
    if alias not in alias_connus:
        return False, f"alias inconnu dans le fichier : {alias!r}"
    if donnees.get("active_model") == alias:
        return False, "impossible de retirer le modèle actif — choisissez-en un autre d'abord"
    if len(alias_connus) <= 1:
        return False, "impossible de retirer le dernier modèle déclaré"

    lignes = texte.splitlines(keepends=True)
    segments = _segments_modeles(lignes)
    cible = next(
        ((debut, fin) for debut, fin in segments if _alias_du_segment(lignes, debut, fin) == alias),
        None,
    )
    if cible is None:
        return False, f"bloc [[models]] de l'alias {alias!r} introuvable dans le fichier"

    debut, fin = cible
    nouvelles_lignes = lignes[:debut] + lignes[fin:]

    _sauvegarder()
    return _ecrire_si_valide("".join(nouvelles_lignes))


# ─────────────────────────────────────────────────────────────────────────
# Routes Flask
# ─────────────────────────────────────────────────────────────────────────

def etat_vibe_modele():
    """GET /vibe-modele/etat — état courant, pour peupler la section au
    chargement de l'onglet."""
    return jsonify(**_etat())


def activer_vibe_modele():
    """POST /vibe-modele/activer {"alias": "..."} — change active_model."""
    data = request.get_json(silent=True) or {}
    alias = str(data.get("alias", "")).strip()
    if not alias:
        return jsonify(erreur="alias requis"), 400
    ok, erreur = _definir_actif(alias)
    if not ok:
        return jsonify(erreur=erreur), 400
    return jsonify(succes=True, **_etat())


def ajouter_vibe_modele():
    """POST /vibe-modele/ajouter {"champs": {...}, "forcer": bool} — déclare
    un nouveau modèle. "forcer" confirme explicitement un alias en collision
    avec ALIAS_RESERVES_CONNUS (sinon 409 + necessite_confirmation)."""
    data = request.get_json(silent=True) or {}
    champs = data.get("champs")
    if not isinstance(champs, dict):
        return jsonify(erreur="champs requis (objet)"), 400
    forcer = bool(data.get("forcer", False))
    ok, erreur, extra = _ajouter_modele(champs, forcer)
    if not ok:
        statut = 409 if extra.get("necessite_confirmation") else 400
        return jsonify(erreur=erreur, **extra), statut
    return jsonify(succes=True, **_etat())


def retirer_vibe_modele():
    """POST /vibe-modele/retirer {"alias": "..."} — refuse si actif ou
    dernier modèle restant."""
    data = request.get_json(silent=True) or {}
    alias = str(data.get("alias", "")).strip()
    if not alias:
        return jsonify(erreur="alias requis"), 400
    ok, erreur = _retirer_modele(alias)
    if not ok:
        return jsonify(erreur=erreur), 400
    return jsonify(succes=True, **_etat())

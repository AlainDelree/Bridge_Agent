#!/usr/bin/env python3
"""palette.py — Science des couleurs des projets Bridge_Agent.

Extrait de nouveau_projet.py (issue #620, diagnostic #579 point 2) : ce bloc
(génération algorithmique de palette, garanties WCAG/Lab, couleur des
projets) est autonome, sans dépendance vers le reste de nouveau_projet.py —
d'où son extraction dans un module dédié. Bénéfice secondaire : permet à
regenerer_tableaux_projets.py d'importer couleur_affichee() en tête de
fichier plutôt que via un import différé (l'import différé existait
uniquement pour éviter un cycle avec nouveau_projet.py, qui n'a plus lieu
d'être une fois la fonction sortie de ce module).

nouveau_projet.py garde ses propres fonctions couleurs_utilisees() /
couleurs_disponibles() (dépendantes de configs/*.conf) et importe
COULEURS_PROJETS_EXISTANTS / PALETTE_COULEURS depuis ce module.
"""

import colorsys
import math

# ─── Système de couleur des projets (issues #535, #539) ───────────────────────
# Remplace l'ancienne palette figée à la main (PALETTE_COULEURS/
# COULEURS_LEGACY_SANS_CONF de l'issue #534, corrigée collision par collision)
# par une GÉNÉRATION algorithmique : teinte + clarté en HSL, saturation fixée
# à 100%, avec TROIS garanties vérifiées PAR LE CODE (plus par relecture
# visuelle) — voir generer_palette() ci-dessous :
#   1. Contraste texte NOIR / fond >= SEUIL_CONTRASTE_NOIR (WCAG AA texte
#      normal). Le style visé partout où la couleur de projet sert d'accent
#      est désormais « fond coloré + texte noir » (voir styleAccentProjet
#      dans app.js) — c'est donc CE contraste-là qui doit tenir, plus celui
#      d'un texte coloré sur fond clair comme avant #535.
#   2. Distance perceptuelle (CIE76, espace Lab) >= SEUIL_DISTANCE_MIN entre
#      CHAQUE paire de couleurs de la palette — la garantie qui manquait à
#      l'ancien système (collision ecole/ff_galerie découverte après #534
#      malgré des hex déjà différents : une vérification visuelle ne suffit
#      pas à garantir une distance perceptuelle réelle).
#   3. Écart de TEINTE (angle Lab a*b*, voir _teinte_lab) >= SEUIL_ECART_
#      TEINTE_MIN entre chaque paire — ajouté en #539 : le seuil de garde de
#      15 posé en #535 s'est révélé insuffisant dans 3 cas réels (alchess/
#      rummikub, ecole/chesscoach, actualise/gestionmail) alors même que leur
#      distance CIE76 dépassait LARGEMENT 15 (56 et 52 pour les deux premières
#      paires, mesurées sur les couleurs réellement en usage — donc pas « de
#      justesse » comme on le supposait). La cause : ces paires ont un écart
#      de teinte Lab quasi nul (1,6° et 0,4°) — seules leur clarté et leur
#      chroma diffèrent. CIE76 (distance euclidienne L/a*/b*) pondère cet
#      écart de clarté/chroma exactement comme un écart de teinte, alors que
#      l'œil, sur une petite pastille, identifie D'ABORD la teinte : deux
#      couleurs de même teinte mais de clarté différente se lisent comme deux
#      NUANCES d'une même couleur, pas comme deux couleurs distinctes — un
#      axe que le seuil global de #535 ne couvrait pas. Remonter
#      SEUIL_DISTANCE_MIN seul n'aurait rien changé (56 et 52 sont déjà très
#      au-dessus de tout seuil raisonnable) : c'est SEUIL_ECART_TEINTE_MIN qui
#      fait le travail. Conséquence pratique : chaque teinte ne peut plus
#      accueillir qu'un nombre limité de couleurs (une par « tranche » d'angle
#      Lab) — la palette générée est donc volontairement plus petite qu'avant
#      (voir NB_COULEURS_PALETTE).
#
# Sur le contraste (issue #535, point 1) : à saturation 100%, le contraste
# obtenu avec du texte noir dépend FORTEMENT de la teinte (la luminance
# relative WCAG pondère les canaux R/V/B différemment : 0.2126/0.7152/0.0722),
# pas seulement de la clarté HSL affichée. Calcul exact (voir
# _plancher_contraste_teinte) : le bleu pur (H≈240°) est la teinte la PLUS
# exigeante, avec besoin d'une clarté d'au moins ~69% pour atteindre 4.5:1 —
# contre ~24% pour un vert/jaune et ~40-46% pour un rouge/magenta.
# L'hypothèse de départ de l'issue (rouge/magenta comme pires cas) ne se
# vérifie donc PAS : ce sont bleu/violet les plus contraignants. Plutôt qu'un
# plancher unique remonté au pire cas (qui écraserait la plage utile des
# autres teintes), chaque teinte reçoit son PROPRE plancher de clarté calculé
# par _plancher_effectif — jamais moins lisible que nécessaire, jamais plus
# restreint qu'il ne faut.
SATURATION_PALETTE     = 100  # %, fixe (issue #535)
CLARTE_MIN_ESTHETIQUE  = 40   # %, plancher de base avant correction contraste
CLARTE_MAX             = 90   # %, plafond (au-delà, couleur trop délavée)
SEUIL_CONTRASTE_NOIR   = 4.5  # ratio WCAG AA texte normal (texte noir / fond)
SEUIL_DISTANCE_MIN     = 20   # deltaE76 (Lab) minimal entre deux couleurs de
                              # la palette — remonté de 15 à 20 (issue #539) ;
                              # défense en profondeur, mais voir surtout
                              # SEUIL_ECART_TEINTE_MIN ci-dessous, seuil qui a
                              # réellement empêché les 3 collisions signalées
SEUIL_ECART_TEINTE_MIN = 15   # °, écart minimal d'angle de teinte Lab (issue
                              # #539) entre deux couleurs de la palette — voir
                              # le point 3 ci-dessus ; 15° laisse une marge
                              # large au-dessus des écarts observés sur les
                              # paires trop proches signalées (0,4° à 6,5°)
NB_COULEURS_PALETTE    = 30   # demandé à generer_palette() ; avec les deux
                              # seuils ci-dessus la grille s'épuise bien avant
                              # (~5 couleurs libres au-delà des 11 projets
                              # historiques, voir COULEURS_PROJETS_EXISTANTS) —
                              # une combinaison teinte+distance stricte laisse
                              # nécessairement moins de couleurs vraiment
                              # distinctes qu'un seuil de distance seul
_HUE_STEP = 4   # ° — résolution de la grille de candidats de generer_palette
_L_STEP   = 2   # % — résolution de la grille de candidats de generer_palette


def _hsl_vers_hex(h: float, s: float, l: float) -> str:
    """HSL (h en degrés, s/l en %) → hex #RRGGBB majuscules."""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def _linearise_srgb(c: float) -> float:
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance_relative(r: float, g: float, b: float) -> float:
    """Luminance relative WCAG (r/g/b dans [0,1])."""
    return (0.2126 * _linearise_srgb(r) + 0.7152 * _linearise_srgb(g)
            + 0.0722 * _linearise_srgb(b))


def _contraste_avec_noir(h: float, s: float, l: float) -> float:
    """Ratio de contraste WCAG entre texte noir (#000) et fond HSL(h,s,l)."""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    return (_luminance_relative(r, g, b) + 0.05) / 0.05


def _plancher_contraste_teinte(h: float, s: float = SATURATION_PALETTE) -> float:
    """Plus petite clarté (%, résolution 0.5) pour laquelle HSL(h,s,l) offre un
    contraste >= SEUIL_CONTRASTE_NOIR avec du texte noir. Calculé, pas deviné
    (issue #535, point 1)."""
    l = 0.0
    while l <= 100.0:
        if _contraste_avec_noir(h, s, l) >= SEUIL_CONTRASTE_NOIR:
            return l
        l += 0.5
    return 100.0


def _plancher_effectif(h: float) -> float:
    """Plancher de clarté réellement appliqué pour une teinte donnée : le plus
    grand des deux (esthétique de départ de l'issue, ou correction de
    contraste si la teinte l'exige — jamais l'inverse : la consigne de
    l'issue est de ne pas sacrifier la lisibilité pour rester à 40%)."""
    return max(CLARTE_MIN_ESTHETIQUE, _plancher_contraste_teinte(h))


def _lab_depuis_hsl(h: float, s: float, l: float) -> tuple[float, float, float]:
    """HSL → Lab (CIE 1976), pour le calcul de distance perceptuelle."""
    r, g, b = colorsys.hls_to_rgb((h % 360) / 360.0, l / 100.0, s / 100.0)
    r, g, b = _linearise_srgb(r), _linearise_srgb(g), _linearise_srgb(b)
    x = r * 0.4124 + g * 0.3576 + b * 0.1805
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = r * 0.0193 + g * 0.1192 + b * 0.9505
    xn, yn, zn = 0.9505, 1.0, 1.089

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x / xn), f(y / yn), f(z / zn)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def _distance_lab(c1: tuple[float, float, float], c2: tuple[float, float, float]) -> float:
    """Distance perceptuelle CIE76 (euclidienne dans Lab) entre deux couleurs."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _teinte_lab(lab: tuple[float, float, float]) -> float:
    """Angle de teinte (°, 0-360) dans le plan a*/b* du Lab (issue #539).
    Deux couleurs peuvent avoir une distance CIE76 énorme (clarté et/ou
    chroma très différents) tout en partageant quasiment le même angle —
    l'œil les lit alors comme deux NUANCES de la même couleur plutôt que
    comme deux couleurs distinctes. C'est cet angle, pas la distance globale,
    qui a effectivement séparé les 3 paires signalées en #539."""
    _, a, b = lab
    return math.degrees(math.atan2(b, a)) % 360


def _ecart_teinte(h1: float, h2: float) -> float:
    """Écart angulaire minimal (°, 0-180) entre deux angles de teinte Lab."""
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


def _lab_depuis_hex(hexv: str) -> tuple[float, float, float]:
    """Hex #RRGGBB → Lab, en passant par HSL (même chemin que _lab_depuis_hsl,
    pour rester cohérent avec le reste du module)."""
    hexv = hexv.lstrip("#")
    r, g, b = (int(hexv[i:i + 2], 16) / 255 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return _lab_depuis_hsl(h * 360, s * 100, l * 100)


def generer_palette(n: int, couleurs_a_eviter: dict[str, str] | None = None) -> list[str]:
    """Génère jusqu'à n couleurs HSL (saturation 100%, clarté variable par
    teinte) en hex, telles que CHAQUE paire — y compris avec couleurs_a_eviter
    — respecte à la fois SEUIL_DISTANCE_MIN (Lab, CIE76) et
    SEUIL_ECART_TEINTE_MIN (angle de teinte Lab) — garanti par construction et
    revérifié explicitement en fin de fonction (assert qui échoue bruyamment
    si la garantie n'est pas tenue, plutôt qu'une relecture visuelle).

    couleurs_a_eviter (issue #539, point 4) : couleurs hex déjà attribuées
    (typiquement COULEURS_PROJETS_EXISTANTS) que la palette générée doit EN
    PLUS respecter, sans pour autant figurer dans le résultat retourné. Sans
    ce paramètre, la garantie ne portait que sur les couleurs générées ENTRE
    ELLES — pas sur les couleurs gelées en dur — et c'est précisément ce trou
    qui a permis à gestionmail (créé après #535, couleur choisie dans cette
    même palette générée) de se retrouver trop proche d'actualise malgré la
    vérification : leur écart de teinte n'était simplement jamais contrôlé.

    Algorithme glouton « farthest-point » sur une grille de candidats
    (teinte × clarté, chaque teinte bornée par son propre plancher de
    contraste — voir _plancher_effectif), en partant de couleurs_a_eviter
    comme réservations initiales : à chaque étape, on choisit — parmi les
    candidats qui respectent les deux seuils vis-à-vis de TOUT ce qui est déjà
    retenu — celui le plus éloigné (au sens Lab) des couleurs déjà retenues.
    S'il n'existe plus aucun candidat valide, la génération s'arrête et
    renvoie moins de n couleurs (jamais plus ; jamais une couleur qui viole
    l'une des deux garanties) — la combinaison des deux seuils limite
    mécaniquement le nombre de couleurs vraiment distinctes disponibles.

    Déterministe (aucun aléatoire) : un appel avec les mêmes arguments renvoie
    toujours la même liste."""
    candidats = []
    h = 0.0
    while h < 360.0:
        plancher = _plancher_effectif(h)
        l = plancher
        while l <= CLARTE_MAX:
            lab = _lab_depuis_hsl(h, SATURATION_PALETTE, l)
            candidats.append((h, l, lab, _teinte_lab(lab)))
            l += _L_STEP
        h += _HUE_STEP

    choisis = []
    for hexv in (couleurs_a_eviter or {}).values():
        lab = _lab_depuis_hex(hexv)
        choisis.append((None, None, lab, _teinte_lab(lab)))

    def valide(c: tuple) -> bool:
        for ch in choisis:
            if _distance_lab(c[2], ch[2]) < SEUIL_DISTANCE_MIN:
                return False
            if _ecart_teinte(c[3], ch[3]) < SEUIL_ECART_TEINTE_MIN:
                return False
        return True

    nouveaux = []
    restants = candidats
    while len(nouveaux) < n:
        meilleur_i, meilleure_marge = None, -1.0
        for i, c in enumerate(restants):
            if not valide(c):
                continue
            marge = min((_distance_lab(c[2], ch[2]) for ch in choisis), default=float("inf"))
            if marge > meilleure_marge:
                meilleur_i, meilleure_marge = i, marge
        if meilleur_i is None:
            break
        choisi = restants.pop(meilleur_i)
        choisis.append(choisi)
        nouveaux.append(choisi)

    for i in range(len(nouveaux)):
        assert _contraste_avec_noir(nouveaux[i][0], SATURATION_PALETTE, nouveaux[i][1]) >= SEUIL_CONTRASTE_NOIR
    for i in range(len(choisis)):
        for j in range(i + 1, len(choisis)):
            assert _distance_lab(choisis[i][2], choisis[j][2]) >= SEUIL_DISTANCE_MIN, (
                f"Palette générée invalide : couleurs {i} et {j} trop proches "
                f"(distance Lab < {SEUIL_DISTANCE_MIN})."
            )
            assert _ecart_teinte(choisis[i][3], choisis[j][3]) >= SEUIL_ECART_TEINTE_MIN, (
                f"Palette générée invalide : couleurs {i} et {j} de teinte trop "
                f"proche (écart < {SEUIL_ECART_TEINTE_MIN}°)."
            )

    return [_hsl_vers_hex(h, SATURATION_PALETTE, l) for h, l, _, _ in nouveaux]


# Couleurs des projets EXISTANTS, pilotées depuis le code plutôt que depuis
# leur .conf (issue #535) : aucune couleur de l'ancien système (issue #534)
# n'a une saturation de 100%, et la quasi-totalité échoue au contraste texte
# noir (vérifié — seuls actualise et scrabble passaient de justesse, mais pas
# à 100% de saturation). Plutôt que de corriger projet par projet comme pour
# ecole/ff_galerie en #534, TOUS les projets existants basculent ici sur une
# couleur générée par le nouveau système. Contrainte de l'issue #535
# respectée : configs/*.conf n'est PAS modifié, un projet ayant déjà un champ
# COULEUR (apiselect, actualise, bloc_score, chesscoach,
# diagnostique_programme, rummikub) garde sa valeur en fichier, simplement
# non affichée — voir la priorité dans couleurs_utilisees() ci-dessous et
# dans COULEURS_PROJET de app.js (qui DOIT rester en synchro avec ce
# dictionnaire).
# Valeurs GELÉES EN DUR (littéraux, pas PALETTE_COULEURS[i]) : les figer rend
# les couleurs des projets existants immunisées contre un futur ajustement des
# constantes de génération (_HUE_STEP, CLARTE_MAX, etc.) — sans ce gel, changer
# une constante recolorerait silencieusement tous les projets existants.
#
# Issue #539 — 4 valeurs corrigées (les 7 autres, satisfaisantes, sont
# inchangées ; correction ciblée, même esprit que #534) :
#   - alchess  (était #00FF00) : collision avec rummikub (#ADFF8F) — distance
#     CIE76 déjà de 56 (bien au-dessus de l'ancien seuil de 15) mais écart de
#     teinte Lab de seulement 1,6° — même teinte, juste plus clair/moins
#     saturé en apparence. alchess n'a pas de champ COULEUR persisté en .conf
#     (contrairement à rummikub) : c'est donc elle qui est réassignée, même
#     convention qu'en #534 (ecole/ff_galerie changées, actualise/apiselect,
#     eux persistés, conservés).
#   - ecole (était #DE85FF) : collision avec chesscoach (#BB00FF) — distance
#     52, écart de teinte 0,4°. ecole n'a pas de champ COULEUR persisté →
#     réassignée (chesscoach conservée). Nouvelle teinte ambre/moutarde, clin
#     d'œil à la couleur « olive/moutarde » qu'ecole portait déjà entre #534
#     et #535.
#   - actualise (était #086BFF) : collision avec gestionmail — gestionmail
#     est un projet créé APRÈS #535, sa couleur ne vit que dans son .conf
#     (configs/gestionmail.conf, hors périmètre de cette correction et de
#     toute façon jamais modifiable par CCL/CCW) : le seul levier disponible
#     est donc actualise, pilotée par ce dictionnaire. Nouvelle teinte
#     délibérément écartée de toute la zone bleu-violet (197°-320° d'angle
#     Lab) où se concentraient déjà ff_galerie, l'ancienne actualise et
#     chesscoach — marge par rapport à la couleur de gestionmail non vérifiée
#     directement (voir rapport de clôture de l'issue) mais largement
#     améliorée par construction.
#   - bloc_score (était #FFB0AB) : collision DÉCOUVERTE en appliquant le
#     nouveau seuil (non signalée dans l'issue) avec bridge_agent (#EB0000) —
#     écart de teinte de seulement 13,2°, sous le nouveau plancher de 15°.
#     bloc_score réassignée (bridge_agent, le projet racine du bridge,
#     n'est pas retouché) ; nouvelle teinte toujours dans la même famille
#     rose/saumon pâle que l'originale.
#
# Issue #540 — ff_galerie et ecole, projets à l'arrêt, RETIRÉS de ce
# dictionnaire (au lieu d'y être remplacés par COULEUR_PROJET_INACTIF) :
# leurs anciennes couleurs dédiées (#A6B8FF, #CC7400) redeviennent ainsi
# disponibles pour un futur projet (voir couleurs_utilisees() plus bas, et
# le gain concret sur couleurs_disponibles() vérifié en clôture d'issue).
# Les inclure ICI avec la valeur grise a été tenté puis abandonné : ce
# dictionnaire est aussi passé en couleurs_a_eviter à generer_palette(), qui
# raisonne en angle de teinte Lab (_teinte_lab) — un gris (saturation 0) a un
# a*/b* quasi nul, donc un angle atan2(0,0) dégénéré à 0°, qui entre en
# collision avec l'exclusion de teinte prévue pour les rouges et fait échouer
# l'assertion de generer_palette (vérifié concrètement, pas supposé). Leur
# couleur d'affichage grise vit donc UNIQUEMENT dans COULEURS_PROJET côté
# app.js (source de vérité pour l'affichage), pas ici (source de vérité pour
# la réservation de couleurs actives) — voir COULEUR_PROJET_INACTIF ci-dessous
# et §"Couleur d'accent des projets" de BRIDGE_AGENT_DOC.md pour la procédure
# de recyclage à réutiliser pour un futur projet mis à l'arrêt.
COULEURS_PROJETS_EXISTANTS = {
    "bridge_agent":           "#EB0000",
    "alchess":                "#00D68F",
    "actualise":              "#009DD6",
    "scrabble":               "#7AFFFF",
    "apiselect":              "#FFD429",
    "diagnostique_programme": "#FC00A8",
    "bloc_score":             "#FF8595",
    "chesscoach":             "#BB00FF",
    "rummikub":               "#ADFF8F",
}

# Gris neutre partagé par tous les projets à l'arrêt (issue #540) — signale
# volontairement l'absence d'identité propre, donc pas de contrainte de
# saturation 100% ni de distance/teinte Lab (ce n'est pas une couleur de
# PALETTE_COULEURS, voir juste au-dessus). Seule contrainte conservée : le
# contraste texte noir >= SEUIL_CONTRASTE_NOIR, vérifié (4,62:1, calculé avec
# _contraste_avec_noir(0, 0, 46) — même fonction que pour les couleurs
# actives). DOIT rester en synchro avec la constante de même nom côté
# app.js (seul endroit où elle est réellement utilisée, voir plus haut).
COULEUR_PROJET_INACTIF = "#767676"

# Projets dont la couleur dédiée a été recyclée (issue #540, procédure décrite
# ci-dessus) : leur couleur affichée est le gris COULEUR_PROJET_INACTIF, piloté
# côté app.js dans COULEURS_PROJET (seule source de vérité pour l'affichage —
# ces clés n'existent volontairement PAS dans COULEURS_PROJETS_EXISTANTS,
# voir le commentaire juste au-dessus). Ensemble MIROIR ajouté par l'issue
# #608 pour que regenerer_tableaux_projets.py puisse reproduire fidèlement
# cette même règle dans la colonne « Couleur » du tableau §2 sans dupliquer
# couleurProjet() (JS) : à tenir à jour à la même occasion que COULEURS_PROJET
# (étape 2 de la procédure de recyclage ci-dessus).
PROJETS_COULEUR_RECYCLEE = frozenset({"ff_galerie", "ecole"})

# Clarté (HSL) de secours pour couleur_hash_projet() ci-dessous — même valeur,
# même raison que CLARTE_HASH_PROJET côté app.js (voir son commentaire) : 72%
# couvre, avec marge, toutes les teintes à saturation 100% pour un contraste
# texte noir >= SEUIL_CONTRASTE_NOIR.
CLARTE_HASH_PROJET = 72


def couleur_hash_projet(nom: str) -> str:
    """Couleur de secours dérivée du nom, en hex — miroir de couleurHashProjet()
    (static/js/app.js) : même hash (charCodes, base 31, mod 360), même teinte
    HSL saturation 100%/clarté CLARTE_HASH_PROJET, converti en hex via
    _hsl_vers_hex plutôt que renvoyé en 'hsl(...)' pour rester au même format
    que les deux autres niveaux de priorité de couleur_affichee()."""
    h = 0
    for c in nom:
        h = (h * 31 + ord(c)) % 360
    return _hsl_vers_hex(h, SATURATION_PALETTE, CLARTE_HASH_PROJET)


def couleur_affichee(nom: str, couleur_conf: str = "") -> str:
    """Couleur RÉELLEMENT affichée pour `nom` (pastilles/badges/fond d'accent
    de l'interface web) — même ordre de priorité que couleurProjet() dans
    static/js/app.js, réutilisé plutôt que réécrit (issue #608) :
      1. COULEURS_PROJETS_EXISTANTS (gelée en dur pour les projets déjà
         existants au moment de #535, quel que soit leur .conf) ;
      2. PROJETS_COULEUR_RECYCLEE → COULEUR_PROJET_INACTIF, pour un projet mis
         à l'arrêt (issue #540) ;
      3. sinon `couleur_conf` (champ COULEUR du .conf, laissé à la charge de
         l'appelant — source de vérité pour un projet créé après #535) ;
      4. sinon un hash de secours dérivé du nom (couleur_hash_projet) : ne
         devrait normalement jamais s'activer pour un projet déjà installé
         (creer_projet() écrit toujours un COULEUR en .conf), sauf .conf
         modifié/tronqué à la main — évite de casser la génération du tableau
         plutôt que de la faire échouer sur un projet sans aucune des trois
         sources ci-dessus."""
    if nom in COULEURS_PROJETS_EXISTANTS:
        return COULEURS_PROJETS_EXISTANTS[nom]
    if nom in PROJETS_COULEUR_RECYCLEE:
        return COULEUR_PROJET_INACTIF
    if couleur_conf:
        return couleur_conf
    return couleur_hash_projet(nom)


# Palette proposée à la création d'un NOUVEAU projet (remplace l'ancienne
# liste figée à la main). Calculée une fois à l'import — déterministe, cf.
# generer_palette. Une couleur est attribuée dès la création et écrite dans
# le .conf (champ COULEUR) ; celles déjà prises par un projet existant sont
# exclues de la proposition (voir couleurs_disponibles ci-dessous). Hex
# #RRGGBB en MAJUSCULES, comparés sans tenir compte de la casse.
#
# Issue #539, point 4 : COULEURS_PROJETS_EXISTANTS est passé en
# couleurs_a_eviter, pas seulement en post-filtrage comme couleurs_utilisees()
# le fait déjà plus bas — sans ça, generer_palette() ne garantirait la
# distance/teinte qu'ENTRE les couleurs qu'elle génère, pas vis-à-vis des 11
# couleurs gelées en dur. C'est exactement ce trou qui avait laissé passer la
# collision actualise/gestionmail : gestionmail a pris une couleur de cette
# même palette, valide par rapport aux autres couleurs générées, mais jamais
# vérifiée par rapport à actualise (gelée à part). Avec ce paramètre, toute
# couleur encore proposée à un futur projet est garantie distincte de TOUS
# les projets existants, pas seulement des autres couleurs de la palette.
PALETTE_COULEURS = generer_palette(NB_COULEURS_PALETTE, COULEURS_PROJETS_EXISTANTS)

#!/usr/bin/env python3
"""nouveau_projet.py — Création / installation d'un projet Bridge_Agent.

Ajouter un projet au bridge était jusqu'ici une procédure manuelle, non
documentée et sujette à l'oubli (cf. issue #90 : labels manquants sur le dépôt
Ecole → échec silencieux de création d'issue). Ce script interactif couvre les
deux cas — création d'un dépôt neuf ET installation dans un dépôt existant — et
met à jour BRIDGE_AGENT_DOC.md automatiquement.

Usage :
    python3 nouveau_projet.py

Zéro dépendance externe (stdlib + les commandes `gh` et `git`). Cas dépôt
existant : comportement inchangé, aucun `git push`. Cas dépôt neuf (issue
#257) : le répertoire de travail est initialisé (git init + remote HTTPS +
commit) puis **poussé** — exception documentée à la règle « Alain pousse
lui-même » (§18.2 de la doc) : c'est Alain qui déclenche la création de
projet, jamais un agent. Le reste (configs/, doc Bridge_Agent) n'est
toujours jamais poussé automatiquement.
"""

import colorsys
import math
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

import regenerer_tableaux_projets

# Racine du dépôt Bridge_Agent : ce script vit à la racine, à côté de watcher.py
# et du dossier configs/.
RACINE = Path(__file__).resolve().parent
DOSSIER_CONFIGS = RACINE / "configs"
DOC = RACINE / "BRIDGE_AGENT_DOC.md"

# Les 9 labels requis par le watcher (§4 de la doc). color = hex sans '#'.
# On les recrée à l'identique sur chaque nouveau dépôt cible ; sans eux, le
# watcher ne voit pas les issues (for-linux) et le mode écriture reste inerte.
LABELS = [
    ("for-linux",   "0e8a16", "Requis — le watcher ne voit que ces issues"),
    ("for-windows", "0e8a16", "Watcher Windows (CCW) — même principe que for-linux"),
    ("bridge",      "1d76db", "Marque l'issue comme tâche bridge (traçabilité)"),
    ("mode_write",  "d93f0b", "ARME le mode écriture — CCL peut modifier des fichiers"),
    ("needs-human", "b60205", "Posé après 3 échecs — stoppe le retraitement auto"),
    ("done",        "0e8a16", "Posé automatiquement au succès"),
    ("notif_pc",    "fbca04", "Ajoute une notification bureau (notify-send)"),
    ("notif_gsm",   "fbca04", "Ajoute une notification push (ntfy)"),
    ("notif_tous",  "fbca04", "notify-send + ntfy"),
]

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

# Topic ntfy partagé par tous les projets existants (voir configs/*.conf).
# Proposé par défaut ; l'utilisateur peut le changer pour un topic dédié.
TOPIC_NTFY_DEFAUT = "hippocampe-ff-galerie-xyz123"
SCRIPT_BIP_DEFAUT = "/home/alain/Bridge_Agent/scripts/bip_Cloche.py"

# Modèle CCL forcé par défaut sur tout nouveau projet (voir configs/*.conf) :
# évite tout repli silencieux vers Opus sur le plan Max. Reste modifiable
# à la main dans le .conf après génération (issue #489).
MODELE_CCL_DEFAUT = "claude-sonnet-5"

# Propriétaire GitHub par défaut pour le dépôt proposé (owner/Nom).
OWNER_DEFAUT = "AlainDelree"

# Fichiers Specs MVC (§15) créés en plus de CONTEXTE.md quand l'option est active.
FICHIERS_SPECS = ("CONTEXTE_VUE.md", "CONTEXTE_METIER.md", "CONTEXTE_PERSISTANCE.md")

# .gitignore minimal écrit à l'initialisation git d'un répertoire de travail
# neuf (issue #257), seulement s'il n'en existe pas déjà un.
GITIGNORE_MINIMAL = """venv/
__pycache__/
*.pyc
*.log
.env
"""

# Timeouts (secondes) des appels git de initialiser_git() (issue #258) : courts
# pour les opérations locales (init/remote/add/commit, jamais de réseau), plus
# généreux pour le push (le seul appel réseau du lot — cohérent avec les 30s/120s
# déjà en place ailleurs dans le bridge pour commenter_issue/pièces jointes).
TIMEOUT_GIT_LOCAL = 15
TIMEOUT_GIT_PUSH = 60

# Fichiers que le script crée lui-même dans le répertoire de travail (contexte
# + gitignore auto) : exclus de la détection de contenu préexistant (issue
# #258) — leur seule présence ne doit pas bloquer le push automatique.
FICHIERS_CREES_PAR_SCRIPT = frozenset({"CONTEXTE.md", ".gitignore", *FICHIERS_SPECS})


# ─── Entrées / sorties interactives ───────────────────────────────────────────

def titre(txt: str) -> None:
    print(f"\n\033[1m{txt}\033[0m")


def demander(question: str, defaut: str = "") -> str:
    """Pose une question ; renvoie la saisie ou le défaut si l'utilisateur
    valide à vide. Le défaut est affiché entre crochets."""
    suffixe = f" [{defaut}]" if defaut else ""
    try:
        reponse = input(f"  {question}{suffixe} : ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nInterrompu.")
        sys.exit(1)
    return reponse or defaut


def demander_oui_non(question: str, defaut: bool = False) -> bool:
    d = "O/n" if defaut else "o/N"
    rep = demander(f"{question} ({d})").lower()
    if not rep:
        return defaut
    return rep in ("o", "oui", "y", "yes")


def gh(*args: str, capture: bool = True) -> subprocess.CompletedProcess:
    """Lance `gh` avec les arguments donnés. capture=False laisse gh écrire
    directement sur le terminal (utile pour repo create)."""
    return subprocess.run(
        ["gh", *args],
        capture_output=capture,
        text=True,
    )


# ─── Étapes ───────────────────────────────────────────────────────────────────

def valider_nom(nom: str) -> bool:
    """Cohérent avec bridge_agent, alchess, ff_galerie : minuscules, chiffres,
    underscore ; commence par une lettre."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_]*", nom))


# ─── Logique réutilisable (CLI + route Flask) ────────────────────────────────
# Ces fonctions n'affichent rien et ne lisent aucune saisie : elles concentrent
# les actions (gh, écriture de fichiers) pour être appelables aussi bien depuis
# le script interactif que depuis app/nouveau_projet.py. Le comportement
# idempotent (labels, contexte, doc) est identique dans les deux cas.

def conf_existe(nom: str) -> bool:
    """True si configs/<nom>.conf existe déjà (nom déjà pris)."""
    return (DOSSIER_CONFIGS / f"{nom}.conf").exists()


def couleurs_utilisees() -> set[str]:
    """Ensemble des couleurs (hex minuscules) déjà attribuées à un projet
    existant : celles pilotées depuis le code pour les projets existants (voir
    COULEURS_PROJETS_EXISTANTS, issue #535) plus celles lues depuis le champ
    COULEUR de chaque configs/*.conf (encore pertinent pour un futur projet
    créé sous le nouveau système, dont la couleur reste celle du .conf).
    Lecture minimale et tolérante (même esprit zéro-dépendance que le reste du
    script) : un .conf illisible est simplement ignoré."""
    prises: set[str] = {c.lower() for c in COULEURS_PROJETS_EXISTANTS.values()}
    for chemin in DOSSIER_CONFIGS.glob("*.conf"):
        try:
            for brut in chemin.read_text(encoding="utf-8").splitlines():
                ligne = brut.strip()
                if not ligne or ligne.startswith("#"):
                    continue
                cle, sep, valeur = ligne.partition("=")
                if sep and cle.strip().upper() == "COULEUR":
                    v = valeur.strip().lower()
                    if v:
                        prises.add(v)
        except OSError:
            continue
    return prises


def couleurs_disponibles() -> list[str]:
    """Couleurs de PALETTE_COULEURS non encore attribuées à un projet existant,
    dans l'ordre de la palette. Sert à la fois au modal (pastilles proposées) et
    à creer_projet (repli si aucune couleur n'est choisie)."""
    prises = couleurs_utilisees()
    return [c for c in PALETTE_COULEURS if c.lower() not in prises]


def normaliser_couleur(couleur: str) -> str:
    """Ramène une couleur choisie à une valeur sûre : la couleur telle qu'écrite
    dans la palette si elle est encore disponible (comparaison insensible à la
    casse), sinon la première couleur libre, sinon '' (palette épuisée → repli
    map fixe/hash côté frontend)."""
    dispo = couleurs_disponibles()
    choisie = (couleur or "").strip().lower()
    if choisie:
        for c in dispo:
            if c.lower() == choisie:
                return c
    return dispo[0] if dispo else ""


def depot_defaut(nom: str) -> str:
    """Dépôt GitHub proposé par défaut : owner + nom capitalisé."""
    return f"{OWNER_DEFAUT}/{nom.capitalize()}"


def rep_defaut(nom: str) -> str:
    """Répertoire de travail CCL proposé par défaut."""
    return f"/home/alain/{nom.capitalize()}"


def depot_existe(depot: str) -> bool:
    """True si le dépôt GitHub cible existe déjà (gh repo view)."""
    return gh("repo", "view", depot).returncode == 0


def creer_depot(depot: str, nom: str, public: bool = True) -> tuple[bool, str]:
    """Crée le dépôt, public ou privé selon `public` (issue #528 ; défaut
    public, cohérent avec le comportement historique). Renvoie (succès,
    message d'erreur éventuel)."""
    res = gh("repo", "create", depot, "--public" if public else "--private",
             "--description", f"Projet {nom} — piloté via Bridge_Agent")
    return res.returncode == 0, res.stderr.strip()


def ecrire_conf(nom: str, depot: str, rep: str, perimetre: str,
                topic: str = TOPIC_NTFY_DEFAUT,
                script_bip: str = SCRIPT_BIP_DEFAUT,
                couleur: str = "") -> Path:
    """Génère configs/<nom>.conf depuis le gabarit. Renvoie le chemin écrit."""
    chemin = DOSSIER_CONFIGS / f"{nom}.conf"
    contenu = GABARIT_CONF.format(
        nom=nom,
        depot=depot,
        rep_travail=rep,
        perimetre=perimetre,
        topic_ntfy=topic,
        script_bip=script_bip,
        couleur=couleur,
        modele_ccl=MODELE_CCL_DEFAUT,
    )
    chemin.write_text(contenu, encoding="utf-8")
    return chemin


def creer_labels(depot: str) -> list[tuple[str, str, str]]:
    """Crée les labels manquants sur le dépôt cible (idempotent : les présents
    sont laissés intacts). Renvoie une liste ordonnée de (label, statut, detail)
    où statut ∈ {"deja", "cree", "echec"}."""
    res = gh("label", "list", "--repo", depot, "--limit", "200")
    existants = set()
    if res.returncode == 0:
        for ligne in res.stdout.splitlines():
            if ligne.strip():
                existants.add(ligne.split("\t")[0].strip().lower())

    resultats = []
    for nom_label, couleur, description in LABELS:
        if nom_label.lower() in existants:
            resultats.append((nom_label, "deja", ""))
            continue
        r = gh("label", "create", nom_label, "--repo", depot,
               "--color", couleur, "--description", description)
        if r.returncode == 0:
            resultats.append((nom_label, "cree", ""))
        else:
            resultats.append((nom_label, "echec", r.stderr.strip()))
    return resultats


def _ecrire_fichiers_contexte(rep_path: Path,
                              avec_specs: bool) -> tuple[list[Path], list[Path]]:
    """Crée CONTEXTE.md (et les 3 fichiers Specs MVC si demandé) dans un
    répertoire supposé existant. Renvoie (créés, déjà présents). Idempotent :
    les fichiers déjà là sont laissés intacts."""
    crees, existants = [], []
    fichiers = ["CONTEXTE.md"]
    if avec_specs:
        fichiers += list(FICHIERS_SPECS)
    for nom_fic in fichiers:
        f = rep_path / nom_fic
        if f.exists():
            existants.append(f)
        else:
            f.write_text("", encoding="utf-8")
            crees.append(f)
    return crees, existants


def creer_fichiers_contexte(rep: str, avec_specs: bool) -> dict:
    """Version non interactive : crée le répertoire de travail s'il manque puis
    les fichiers contexte. Renvoie {crees, existants, rep_cree}."""
    rep_path = Path(rep).expanduser()
    rep_cree = False
    if not rep_path.exists():
        rep_path.mkdir(parents=True, exist_ok=True)
        rep_cree = True
    crees, existants = _ecrire_fichiers_contexte(rep_path, avec_specs)
    return {"crees": crees, "existants": existants, "rep_cree": rep_cree}


def _url_https(depot: str) -> str:
    """URL HTTPS du dépôt (jamais SSH — toute l'installation gh/bridge est en
    HTTPS avec authentification `gh`, cf. §9 de la doc)."""
    return f"https://github.com/{depot}.git"


def _commandes_git_manuelles(rep_path: Path, depot: str, complet: bool) -> str:
    """Bloc de commandes à exécuter à la main. `complet` : bloc entier
    (init+remote+commit+push, cas refusé/échoué dès `git init`) ou juste le
    push (init déjà fait, seul le push a échoué)."""
    if not complet:
        return f"cd {rep_path} && git push -u origin master"
    url = _url_https(depot)
    return (f"cd {rep_path}\n"
            f"git init -b master\n"
            f"git remote add origin {url}\n"
            f'git add -A && git commit -m "Initialisation du projet"\n'
            f"git push -u origin master")


def _fichiers_suivis_preexistants(rep_path: Path, git_runner) -> list[str]:
    """Fichiers que git suivrait RÉELLEMENT, autres que ceux que le script
    vient de créer lui-même (CONTEXTE.md, fichiers Specs, .gitignore) —
    issue #260, corrige #258. Se fonde sur l'index git (`git diff --cached
    --name-only`), interrogé APRÈS écriture du `.gitignore` minimal et
    `git add -A` : contrairement à un scan brut du disque (`rglob`, version
    #258), un contenu exclu par ce `.gitignore` (`venv/`, `__pycache__/`,
    `*.pyc`, `*.log`, `.env`) n'a jamais atteint l'index et n'apparaît donc
    plus ici — c'est ce que git commit/push emporterait réellement. Une
    liste non vide signale un répertoire qui contenait déjà du contenu
    SUIVI avant l'initialisation git : le dépôt étant nouvellement créé
    (public ou privé selon le choix fait à sa création — issue #528), ce
    contenu ne doit pas être publié sans relecture. `git_runner` est le
    point d'entrée `_git()` de l'appelant, déjà borné par TIMEOUT_GIT_LOCAL
    et tolérant au dépassement — réutilisé tel quel, pas de second timeout à
    gérer ici. Chemins relatifs à rep_path, triés, pour un affichage stable
    côté CLI/web."""
    res = git_runner("diff", "--cached", "--name-only")
    if res.returncode != 0:
        return []
    fichiers = [ligne for ligne in res.stdout.splitlines() if ligne.strip()]
    return sorted(f for f in fichiers if Path(f).name not in FICHIERS_CREES_PAR_SCRIPT)


def _corriger_email_noreply(git_runner) -> str | None:
    """Filet de sécurité avant le tout premier commit (issue #530) : sans
    adresse noreply, `user.email` expose l'adresse email réelle dans les
    métadonnées auteur/committer de chaque commit — visible publiquement une
    fois le dépôt poussé. `git_runner` (le `_git()` de l'appelant, cwd déjà
    fixé sur le dépôt) donne l'email EFFECTIF (local au dépôt tout juste
    initialisé, ou à défaut la config globale — `git config user.email` sans
    `--local` ni `--global` résout déjà cette priorité). S'il correspond déjà
    au format noreply GitHub (`*@users.noreply.github.com` — cas normal sur
    cette machine), ne fait rien et renvoie None : ce garde-fou doit rester
    silencieux quand tout va bien. Sinon, récupère la vraie adresse noreply
    du compte via `gh api user` (`id`+`login`, format documenté par GitHub :
    `<id>+<login>@users.noreply.github.com` — c'est exactement celle déjà en
    config globale sur cette machine) et la pose en config LOCALE au dépôt
    (jamais globale, pour ne pas modifier silencieusement un réglage qui
    dépasse ce projet). Renvoie l'adresse posée, ou None si déjà correcte OU
    si `gh api user` échoue (pas de compte accessible — la création du
    projet ne doit pas échouer pour autant, le commit part alors avec
    l'email trouvé tel quel)."""
    email_actuel = git_runner("config", "user.email").stdout.strip()
    if email_actuel.endswith("@users.noreply.github.com"):
        return None

    identifiant = gh("api", "user", "-q", ".id")
    login = gh("api", "user", "-q", ".login")
    if identifiant.returncode != 0 or login.returncode != 0:
        return None
    identifiant, login = identifiant.stdout.strip(), login.stdout.strip()
    if not identifiant or not login:
        return None

    email_noreply = f"{identifiant}+{login}@users.noreply.github.com"
    git_runner("config", "user.email", email_noreply)
    return email_noreply


def initialiser_git(rep: str, depot: str) -> dict:
    """Initialise le dépôt git local du répertoire de travail (issue #257) :
    `git init` sur la branche `master`, `git remote add origin` en **HTTPS**
    (jamais SSH), `.gitignore` minimal s'il est absent, commit initial, puis
    push. Si REP_TRAVAIL est déjà un dépôt git (installation sur un projet
    existant — le cas de tous les projets actuels), ne fait strictement rien.

    Exception documentée à la règle « CCL ne pousse jamais » (§18.2 de la
    doc, même raisonnement que la route pièces jointes) : c'est Alain qui
    déclenche la création de projet — jamais un agent — donc ce push initial
    n'est pas soumis à cette règle. Un échec du push (réseau, droits, ou
    timeout — issue #258) ne fait PAS échouer l'étape : le commit reste
    local et `commande_manuelle` indique la commande à relancer à la main.

    Second garde-fou (issue #258, affiné #260) : cette exception ne repose
    que sur le fait que le dépôt DISTANT vient d'être créé et ne contient
    encore aucun travail d'un tiers — elle ne dit rien du contenu LOCAL du
    répertoire. Si REP_TRAVAIL désigne un dossier préexistant non versionné
    contenant déjà des fichiers que git SUIVRAIT (donc hors de ce
    qu'exclurait le `.gitignore` minimal — cas explicitement couvert par ce
    script), le push n'est donc PAS déclenché automatiquement :
    init/remote/.gitignore/commit sont faits, mais le push reste à lancer à
    la main après relecture. Un `venv/` ou `__pycache__/` préexistant, lui,
    n'a jamais atteint l'index git et ne déclenche pas cette retenue
    (issue #260 : la détection portait auparavant sur le contenu brut du
    disque, avant même l'écriture du `.gitignore`, ce qui faisait remonter
    des milliers d'entrées jamais destinées à être commitées).

    Renvoie {ok, deja_git, push_ok, contenu_preexistant, detail,
    commande_manuelle}. `contenu_preexistant` est la liste (triée, chemins
    relatifs) des fichiers détectés ; `push_ok` vaut None aussi bien en cas
    d'échec avant le push (git init raté) qu'en cas de retenue volontaire
    (contenu préexistant) — c'est `contenu_preexistant` qui distingue les
    deux côté appelant."""
    rep_path = Path(rep).expanduser()
    if (rep_path / ".git").exists():
        return {"ok": True, "deja_git": True, "push_ok": None,
                "contenu_preexistant": [], "email_corrige": None,
                "detail": "déjà un dépôt git — inchangé.",
                "commande_manuelle": None}

    def _git(*args: str, timeout: float = TIMEOUT_GIT_LOCAL) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(["git", *args], cwd=rep_path,
                                  capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(
                args=["git", *args], returncode=124, stdout="",
                stderr=f"timeout dépassé ({timeout}s)")

    res_init = _git("init", "-b", "master")
    if res_init.returncode != 0:
        return {"ok": False, "deja_git": False, "push_ok": None,
                "contenu_preexistant": [], "email_corrige": None,
                "detail": f"échec de git init : {res_init.stderr.strip()}",
                "commande_manuelle": _commandes_git_manuelles(rep_path, depot,
                                                               complet=True)}

    url = _url_https(depot)
    _git("remote", "add", "origin", url)

    gitignore = rep_path / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(GITIGNORE_MINIMAL, encoding="utf-8")

    _git("add", "-A")

    # Détection APRÈS `.gitignore` + `git add -A` (issue #260, corrige #258) :
    # on regarde ce que git a réellement indexé, pas le contenu brut du
    # disque — un `venv/`/`__pycache__/` exclu par le `.gitignore` minimal
    # n'a jamais atteint l'index et ne compte donc pas comme préexistant.
    preexistants = _fichiers_suivis_preexistants(rep_path, _git)

    # Filet de sécurité issue #530 : avant le tout premier commit, s'assurer
    # que l'email git effectif est bien l'adresse noreply GitHub du compte —
    # sans quoi l'adresse réelle de l'utilisateur se retrouverait exposée
    # dans les métadonnées auteur/committer, publiquement une fois poussé.
    email_corrige = _corriger_email_noreply(_git)

    _git("commit", "-m", "Initialisation du projet", "--allow-empty")

    detail = (f"git init (branche master), remote origin {url} (HTTPS), "
              ".gitignore minimal, commit initial")
    if email_corrige:
        detail += (f" — ⚠ email git réel détecté, corrigé en local sur ce "
                   f"dépôt : {email_corrige}")

    if preexistants:
        detail += (f" — ⚠ push automatique retenu : {len(preexistants)} "
                   "fichier(s) préexistant(s) détecté(s) dans le répertoire "
                   f"({', '.join(preexistants[:10])}"
                   f"{', …' if len(preexistants) > 10 else ''}) ; ce contenu "
                   "n'a pas été relu.")
        return {"ok": True, "deja_git": False, "push_ok": None,
                "contenu_preexistant": preexistants, "email_corrige": email_corrige,
                "detail": detail,
                "commande_manuelle": _commandes_git_manuelles(rep_path, depot,
                                                               complet=False)}

    res_push = _git("push", "-u", "origin", "master", timeout=TIMEOUT_GIT_PUSH)
    push_ok = res_push.returncode == 0

    commande_manuelle = None
    if push_ok:
        detail += ", poussé sur origin/master."
    else:
        detail += (" — ⚠ push initial échoué (commit resté local) : "
                   + res_push.stderr.strip())
        commande_manuelle = _commandes_git_manuelles(rep_path, depot,
                                                       complet=False)

    return {"ok": True, "deja_git": False, "push_ok": push_ok,
            "contenu_preexistant": [], "email_corrige": email_corrige,
            "detail": detail, "commande_manuelle": commande_manuelle}


def mettre_a_jour_doc() -> dict:
    """Régénère les tableaux §2/§7 de BRIDGE_AGENT_DOC.md depuis
    configs/*.conf (délègue à regenerer_tableaux_projets — issue #571). Le
    .conf du nouveau projet est déjà écrit sur disque à ce stade (étape 2
    de creer_projet), donc la régénération depuis le disque le voit déjà.
    Renvoie {existe, ok2, ok7, ok_date}."""
    resultat = regenerer_tableaux_projets.regenerer()
    ok = resultat["existe"] and resultat["erreur"] is None
    return {"existe": resultat["existe"], "ok2": ok, "ok7": ok,
            "ok_date": resultat["modifie"]}


def creer_projet(nom: str, depot: str = "", rep: str = "", perimetre: str = "",
                 topic: str = "", script_bip: str = "", avec_specs: bool = False,
                 creer_depot_si_absent: bool = True, couleur: str = "",
                 public: bool = True) -> dict:
    """Orchestrateur non interactif appelé par la route Flask. Enchaîne les
    mêmes étapes que le script CLI (dépôt, .conf, labels, contexte, doc) et
    renvoie un compte-rendu structuré : {succes, nom, depot, rep, perimetre,
    depot_existait, etapes:[{etape, ok, detail}], erreur}. `public` (issue
    #528) détermine la visibilité du dépôt s'il doit être créé ; sans effet
    si le dépôt existe déjà (sa visibilité n'est alors pas modifiée)."""
    nom = (nom or "").strip().lower()
    if not nom:
        return {"succes": False, "erreur": "Un nom de projet est requis.", "etapes": []}
    if not valider_nom(nom):
        return {"succes": False, "etapes": [],
                "erreur": "Format de nom invalide (minuscules, chiffres, "
                          "underscore ; commence par une lettre)."}
    if conf_existe(nom):
        return {"succes": False, "etapes": [],
                "erreur": f"configs/{nom}.conf existe déjà — choisir un autre nom "
                          "ou supprimer l'ancien d'abord."}

    depot = (depot or "").strip() or depot_defaut(nom)
    rep = (rep or "").strip() or rep_defaut(nom)
    perimetre = (perimetre or "").strip() or rep
    topic = (topic or "").strip() or TOPIC_NTFY_DEFAUT
    script_bip = (script_bip or "").strip() or SCRIPT_BIP_DEFAUT
    # Couleur d'accent : la couleur choisie si elle est encore libre, sinon la
    # première disponible, sinon '' (palette épuisée → repli map fixe/hash côté
    # frontend). Exclut au passage les couleurs déjà prises (issue #121).
    couleur = normaliser_couleur(couleur)

    etapes = []

    # 1. Dépôt GitHub — installation si existant, création sinon.
    if depot_existe(depot):
        depot_existait = True
        etapes.append({"etape": "Dépôt GitHub", "ok": True,
                       "detail": f"{depot} existe déjà → installation dessus "
                                 "(pas de recréation)."})
    else:
        if not creer_depot_si_absent:
            return {"succes": False, "etapes": etapes, "depot": depot,
                    "erreur": f"Le dépôt {depot} n'existe pas. Cochez la création "
                              "du dépôt pour continuer."}
        ok, err = creer_depot(depot, nom, public=public)
        depot_existait = False
        if not ok:
            etapes.append({"etape": "Dépôt GitHub", "ok": False,
                           "detail": f"Échec de la création : {err}"})
            return {"succes": False, "etapes": etapes, "depot": depot,
                    "erreur": f"Impossible de créer {depot} : {err}"}
        etapes.append({"etape": "Dépôt GitHub", "ok": True,
                       "detail": f"{depot} créé ({'public' if public else 'privé'})."})

    # 2. Fichier configs/<nom>.conf.
    ecrire_conf(nom, depot, rep, perimetre, topic, script_bip, couleur)
    detail_conf = f"configs/{nom}.conf créé (à partir du gabarit)."
    if couleur:
        detail_conf += f" Couleur d'accent : {couleur}."
    etapes.append({"etape": "Fichier .conf", "ok": True, "detail": detail_conf})

    # 3. Labels GitHub requis (idempotent).
    resultats = creer_labels(depot)
    nb_crees = sum(1 for _, s, _ in resultats if s == "cree")
    nb_deja = sum(1 for _, s, _ in resultats if s == "deja")
    echecs = [(n, e) for n, s, e in resultats if s == "echec"]
    detail_labels = f"{nb_crees} nouveau(x), {nb_deja} déjà existant(s)"
    if echecs:
        detail_labels += " ; échecs : " + ", ".join(f"{n} ({e})" for n, e in echecs)
    etapes.append({"etape": "Labels GitHub", "ok": not echecs,
                   "detail": detail_labels})

    # 4. Fichier(s) de contexte (crée le répertoire de travail au besoin).
    ctx = creer_fichiers_contexte(rep, avec_specs)
    noms_crees = [f.name for f in ctx["crees"]]
    if noms_crees:
        detail_ctx = ", ".join(noms_crees) + " créé(s)"
    else:
        detail_ctx = "tous déjà présents"
    if ctx["rep_cree"]:
        detail_ctx = f"répertoire {rep} créé ; " + detail_ctx
    etapes.append({"etape": "Fichiers contexte", "ok": True, "detail": detail_ctx})

    # 5. Dépôt git local du répertoire de travail (issue #257) — sans quoi le
    # projet est inutilisable (git pull --ff-only et commit de sauvegarde du
    # watcher échouent). Rien à faire si déjà un dépôt git.
    git_res = initialiser_git(rep, depot)
    etapes.append({"etape": "Dépôt git local", "ok": git_res["ok"],
                   "detail": git_res["detail"]})

    # 6. Mise à jour de BRIDGE_AGENT_DOC.md (§2, §7, date).
    doc = mettre_a_jour_doc()
    if not doc["existe"]:
        etapes.append({"etape": "Documentation", "ok": False,
                       "detail": "BRIDGE_AGENT_DOC.md introuvable — non mis à jour."})
    else:
        ok_doc = doc["ok2"] and doc["ok7"]
        etapes.append({"etape": "Documentation", "ok": ok_doc,
                       "detail": "§2/§7/date mis à jour" if ok_doc
                       else "sections §2/§7 non trouvées — à vérifier"})

    return {"succes": True, "nom": nom, "depot": depot, "rep": rep,
            "perimetre": perimetre, "depot_existait": depot_existait,
            "couleur": couleur, "etapes": etapes, "erreur": None,
            "git_deja_git": git_res["deja_git"],
            "git_push_ok": git_res["push_ok"],
            "git_contenu_preexistant": git_res["contenu_preexistant"],
            "git_commande_manuelle": git_res["commande_manuelle"]}


def etape_nom() -> str:
    titre("1. Nom du projet")
    print("   Identifiant court, minuscules + underscore (ex. bridge_agent, alchess).")
    while True:
        nom = demander("Nom du projet").lower()
        if not nom:
            print("   ⚠️  Un nom est requis.")
            continue
        if not valider_nom(nom):
            print("   ⚠️  Format invalide (minuscules, chiffres, underscore ; "
                  "commence par une lettre).")
            continue
        conf = DOSSIER_CONFIGS / f"{nom}.conf"
        if conf.exists():
            print(f"   ⚠️  configs/{nom}.conf existe déjà — choisir un autre nom "
                  "ou supprimer l'ancien d'abord.")
            continue
        return nom


def etape_depot(nom: str) -> tuple[str, bool]:
    """Renvoie (depot, existait_deja). Crée le dépôt s'il n'existe pas et que
    l'utilisateur confirme — public ou privé selon son choix (issue #528),
    défaut public pour rester cohérent avec le comportement historique."""
    titre("2. Dépôt GitHub cible")
    # Proposition par défaut : owner du dépôt courant + nom capitalisé.
    depot = demander("Dépôt GitHub (owner/nom)", depot_defaut(nom))

    if depot_existe(depot):
        print(f"   ✓ Le dépôt {depot} existe déjà → installation dessus "
              "(pas de recréation).")
        return depot, True

    print(f"   Le dépôt {depot} n'existe pas encore.")
    if not demander_oui_non(f"Créer {depot}", defaut=True):
        print("   Abandon : impossible de continuer sans dépôt cible.")
        sys.exit(1)

    public = demander_oui_non("Dépôt public (non = privé)", defaut=True)
    if not public:
        print("   ⚠️  Dépôt privé : vérifier que GH_TOKEN dispose des "
              "permissions nécessaires sur ce dépôt, sinon la création "
              "ci-dessous — ou un appel gh/git ultérieur (issues, push) — "
              "échouera avec une erreur d'authentification.")

    print(f"   Création de {depot} ({'public' if public else 'privé'})…")
    ok, err = creer_depot(depot, nom, public=public)
    if not ok:
        print(f"   ❌ Échec de la création : {err}")
        sys.exit(1)
    print("   ✓ Dépôt créé.")
    return depot, False


def etape_repertoire(nom: str) -> tuple[str, str]:
    """Renvoie (rep_travail, perimetre)."""
    titre("3. Répertoire de travail CCL et périmètre")
    rep = demander("Répertoire de travail CCL", rep_defaut(nom))
    perimetre = demander("Périmètre autorisé (dossiers, séparés par des virgules)", rep)
    return rep, perimetre


def etape_conf(nom: str, depot: str, rep: str, perimetre: str) -> Path:
    titre("4. Fichier configs/<nom>.conf")
    topic = demander("Topic ntfy", TOPIC_NTFY_DEFAUT)
    # Couleur d'accent : proposer la première libre par défaut, laisser choisir
    # parmi les couleurs non encore utilisées (issue #121).
    couleur = etape_couleur()
    chemin = DOSSIER_CONFIGS / f"{nom}.conf"
    contenu = GABARIT_CONF.format(
        nom=nom,
        depot=depot,
        rep_travail=rep,
        perimetre=perimetre,
        topic_ntfy=topic,
        script_bip=SCRIPT_BIP_DEFAUT,
        couleur=couleur,
        modele_ccl=MODELE_CCL_DEFAUT,
    )
    chemin.write_text(contenu, encoding="utf-8")
    print(f"   ✓ {chemin.relative_to(RACINE)} créé (à partir du gabarit).")
    if couleur:
        print(f"   ✓ Couleur d'accent : {couleur}.")
    return chemin


def etape_couleur() -> str:
    """Propose les couleurs de la palette non encore utilisées et renvoie le hex
    choisi (ou la première libre si validation à vide). '' si palette épuisée."""
    dispo = couleurs_disponibles()
    if not dispo:
        print("   • Palette épuisée (toutes les couleurs sont prises) — "
              "couleur auto (repli map fixe/hash côté interface).")
        return ""
    print("   Couleurs disponibles (non encore utilisées) :")
    for i, c in enumerate(dispo, 1):
        print(f"     {i}. {c}")
    rep = demander(f"Numéro de couleur (1-{len(dispo)})", "1")
    if rep.isdigit() and 1 <= int(rep) <= len(dispo):
        return dispo[int(rep) - 1]
    return dispo[0]


def etape_labels(depot: str) -> list[str]:
    """Crée les labels manquants sur le dépôt cible. Renvoie la liste des
    labels effectivement créés (les déjà présents sont laissés intacts)."""
    titre("5. Labels GitHub requis")
    res = gh("label", "list", "--repo", depot, "--limit", "200")
    existants = set()
    if res.returncode == 0:
        for ligne in res.stdout.splitlines():
            if ligne.strip():
                existants.add(ligne.split("\t")[0].strip().lower())
    else:
        print(f"   ⚠️  Impossible de lister les labels ({res.stderr.strip()}) — "
              "tentative de création quand même.")

    crees = []
    for nom_label, couleur, description in LABELS:
        if nom_label.lower() in existants:
            print(f"   • {nom_label} : déjà présent, laissé intact.")
            continue
        r = gh("label", "create", nom_label, "--repo", depot,
               "--color", couleur, "--description", description)
        if r.returncode == 0:
            print(f"   ✓ {nom_label} : créé.")
            crees.append(nom_label)
        else:
            print(f"   ❌ {nom_label} : échec ({r.stderr.strip()}).")
    return crees


def etape_contexte(rep: str, avec_specs: bool) -> list[Path]:
    """Crée CONTEXTE.md (et les 3 fichiers Specs MVC si demandé) dans le
    répertoire de travail du projet. Renvoie les fichiers créés."""
    titre("6. Fichier(s) de contexte")
    rep_path = Path(rep).expanduser()
    if not rep_path.exists():
        if demander_oui_non(f"Le répertoire {rep_path} n'existe pas. Le créer",
                            defaut=True):
            rep_path.mkdir(parents=True, exist_ok=True)
        else:
            print("   ⚠️  Contexte non créé (répertoire absent). À faire à la main.")
            return []

    crees = []
    contexte = rep_path / "CONTEXTE.md"
    if contexte.exists():
        print(f"   • {contexte} existe déjà, laissé intact.")
    else:
        contexte.write_text("", encoding="utf-8")
        print(f"   ✓ {contexte} créé (vide).")
        crees.append(contexte)

    if avec_specs:
        for nom_fic in ("CONTEXTE_VUE.md", "CONTEXTE_METIER.md",
                        "CONTEXTE_PERSISTANCE.md"):
            f = rep_path / nom_fic
            if f.exists():
                print(f"   • {f} existe déjà, laissé intact.")
            else:
                f.write_text("", encoding="utf-8")
                print(f"   ✓ {f} créé (vide).")
                crees.append(f)
    return crees


def etape_git(depot: str, rep: str) -> dict:
    """Initialise le dépôt git local du répertoire de travail (issue #257),
    après confirmation — cohérent avec les autres étapes, qui demandent
    toutes. Rien n'est demandé si REP_TRAVAIL est déjà un dépôt git (cas
    laissé strictement inchangé). Renvoie le même dict que initialiser_git()."""
    titre("8. Dépôt git local")
    rep_path = Path(rep).expanduser()
    if (rep_path / ".git").exists():
        print(f"   ✓ {rep_path} est déjà un dépôt git — inchangé.")
        return {"ok": True, "deja_git": True, "push_ok": None,
                "detail": "déjà un dépôt git — inchangé.",
                "commande_manuelle": None}

    url = _url_https(depot)
    print(f"   {rep_path} n'est pas encore un dépôt git.")
    print("   Sans initialisation, « git pull --ff-only » (watcher) et le "
          "commit de sauvegarde (mode écriture) échoueront systématiquement.")
    if not demander_oui_non(
            f"Initialiser git (init sur master, remote origin {url} en "
            "HTTPS, .gitignore, commit initial, PUIS push)", defaut=True):
        cmd = _commandes_git_manuelles(rep_path, depot, complet=True)
        print("   ⚠️  Non initialisé — reste à faire à la main avant tout usage :")
        for ligne in cmd.splitlines():
            print(f"      {ligne}")
        return {"ok": False, "deja_git": False, "push_ok": None,
                "detail": "non initialisé (refusé) — à faire à la main.",
                "commande_manuelle": cmd}

    resultat = initialiser_git(rep, depot)
    if resultat.get("email_corrige"):
        print(f"   ⚠️  Email git réel détecté (pas l'adresse noreply GitHub) "
              f"— corrigé en config LOCALE à ce dépôt : {resultat['email_corrige']}")
    if resultat["push_ok"]:
        print("   ✓ dépôt initialisé (branche master, remote HTTPS) et poussé "
              "sur origin/master.")
    elif resultat["contenu_preexistant"]:
        print("   ✓ dépôt initialisé, commit local créé.")
        print("   ⚠️  push NON déclenché : le répertoire contenait déjà du "
              "contenu non relu. Fichiers préexistants détectés :")
        for f in resultat["contenu_preexistant"][:10]:
            print(f"      - {f}")
        if len(resultat["contenu_preexistant"]) > 10:
            print(f"      … et {len(resultat['contenu_preexistant']) - 10} "
                  "autre(s).")
        print(f"   Après vérification, lancer : {resultat['commande_manuelle']}")
    elif resultat["ok"]:
        print("   ✓ dépôt initialisé, commit local créé.")
        print(f"   ⚠️  push initial échoué — à relancer à la main : "
              f"{resultat['commande_manuelle']}")
    else:
        print(f"   ❌ {resultat['detail']}")
    return resultat


# ─── Mise à jour de la documentation (§2, §7, date) ───────────────────────────
# Régénération complète depuis configs/*.conf, déléguée à
# regenerer_tableaux_projets.py (issue #571) — un seul mécanisme écrit dans
# ces tableaux, plutôt que cette insertion ligne à ligne et sa jumelle
# mettre_a_jour_doc() (route Flask) maintenues indépendamment.

def etape_doc() -> bool:
    titre("9. Mise à jour de BRIDGE_AGENT_DOC.md")
    resultat = regenerer_tableaux_projets.regenerer()
    if not resultat["existe"]:
        print(f"   ⚠️  {DOC.name} introuvable — mise à jour ignorée.")
        return False
    if resultat["erreur"]:
        print(f"   ⚠️  {resultat['erreur']}")
        return False
    if resultat["modifie"]:
        print(f"   §2/§7 régénérés depuis configs/*.conf "
              f"({resultat['n_projets']} projet(s)).")
    else:
        print("   §2/§7 déjà à jour — aucune modification.")
    return True


# ─── Gabarit du .conf ─────────────────────────────────────────────────────────

GABARIT_CONF = """# configs/{nom}.conf
# Config du watcher pour le projet {nom}.
# Généré par nouveau_projet.py — ne pas copier un .conf existant à la main.
# Format : CLÉ = valeur. Lignes vides et lignes commençant par # ignorées.

# ─── Requis ───────────────────────────────────────────────────────────────────
NOM         = {nom}
DEPOT       = {depot}
REP_TRAVAIL = {rep_travail}
TOPIC_NTFY  = {topic_ntfy}

# ─── Périmètre CCL (dossiers autorisés, séparés par des virgules) ─────────────
PERIMETRE   = {perimetre}

# ─── Sauvegarde avant modification (mode écriture) ────────────────────────────
CMD_BACKUP  = git add -A && git commit -m "avant-<description>" --allow-empty

# ─── Contexte ───────────────────────────────────────────────────────────────────
FICHIER_CONTEXTE = CONTEXTE.md

# ─── Couleur d'accent dans l'interface (hex #RRGGBB ; vide = repli auto) ───────
# Attribuée à la création (palette de nouveau_projet.py, couleurs déjà prises
# exclues). Le frontend l'utilise en priorité ; à défaut il retombe sur la map
# fixe puis sur un hash HSL du nom (issue #121).
COULEUR          = {couleur}

# ─── Optionnels (le défaut s'applique si la ligne reste commentée) ─────────────
LABEL             = for-linux
INTERVALLE        = 10
MAX_ESSAIS        = 3
TIMEOUT_CLAUDE    = 300
SCRIPT_BIP        = {script_bip}
# Décalage de tonalité du bip en demi-tons, propre à ce projet (issue #526).
# 0 = tonalité normale ; réglable aussi depuis l'onglet Configuration.
# TONALITE_BIP    = 0

# Nombre de tâches mode_write concurrentes via git worktrees (issue #337),
# 1-4, plafonné à 4 (issue #568). 2 = défaut ; réglable aussi depuis l'onglet
# Configuration.
# MAX_WRITE_PARALLELE = 2

# ─── Journaux (rotation par taille, archives datées) ──────────────────────────
LOG_TAILLE_MAX_MO = 1
LOG_ARCHIVES      = 5

# ─── Auto-extinction du watcher après inactivité (issue #200) ─────────────────
# Minutes sans aucune issue traitable avant arrêt propre. 0 = désactivé (permanent).
DELAI_INACTIVITE_MIN = 20

# ─── Modèle CCL forcé (vide = défaut) ─────────────────────────────────────────
MODELE_CCL        = {modele_ccl}

# ─── Mot de passe interface (sha256 ; vide = pas d'authentification) ──────────
# MOT_DE_PASSE    =
"""


# ─── Programme principal ──────────────────────────────────────────────────────

def main() -> None:
    print("\033[1m═══ Bridge_Agent — Nouveau projet ═══\033[0m")
    print("Création ou installation d'un projet dans le bridge inter-agents.")

    if subprocess.run(["which", "gh"], capture_output=True).returncode != 0:
        sys.exit("❌ La commande `gh` (GitHub CLI) est requise mais introuvable.")

    nom = etape_nom()
    depot, depot_existait = etape_depot(nom)
    rep, perimetre = etape_repertoire(nom)
    chemin_conf = etape_conf(nom, depot, rep, perimetre)
    labels_crees = etape_labels(depot)
    fichiers_contexte = etape_contexte(rep, avec_specs=False)

    # 7. Pattern Chef + Specs MVC (prospectif, §15) — question séparée.
    titre("7. Pattern Chef + Specs MVC (optionnel, §15)")
    print("   Crée en plus CONTEXTE_VUE.md, CONTEXTE_METIER.md, "
          "CONTEXTE_PERSISTANCE.md (vides).")
    if demander_oui_non("Mettre en place le pattern Specs MVC", defaut=False):
        fichiers_contexte += etape_contexte(rep, avec_specs=True)

    git_res = etape_git(depot, rep)
    doc_ok = etape_doc()

    # 10. Résumé final.
    titre("✅ Résumé")
    print(f"   Projet          : {nom}")
    print(f"   Dépôt GitHub    : {depot} "
          f"({'existant' if depot_existait else 'créé'})")
    print(f"   Config          : {chemin_conf.relative_to(RACINE)}")
    print(f"   Périmètre       : {perimetre}")
    if labels_crees:
        print(f"   Labels créés    : {', '.join(labels_crees)}")
    else:
        print("   Labels          : tous déjà présents (rien à créer)")
    if fichiers_contexte:
        print("   Contexte        : " +
              ", ".join(str(f) for f in fichiers_contexte))
    if git_res["deja_git"]:
        print("   Dépôt git local : déjà un dépôt git — inchangé")
    elif git_res["push_ok"]:
        print("   Dépôt git local : initialisé (master, remote HTTPS) et "
              "poussé sur origin/master")
    elif git_res["contenu_preexistant"]:
        print(f"   Dépôt git local : initialisé, commit local — push NON "
              f"automatique ({len(git_res['contenu_preexistant'])} fichier(s) "
              "préexistant(s) non relu(s))")
    elif git_res["ok"]:
        print("   Dépôt git local : initialisé, commit local — push manuel requis")
    else:
        print("   Dépôt git local : NON initialisé — le projet est inutilisable "
              "en l'état")
    print(f"   Documentation   : {'§2/§7/date mis à jour' if doc_ok else 'à vérifier'}")

    print("\n\033[1mReste à faire manuellement :\033[0m")
    print(f"   Côté projet {nom} créé :")
    print(f"   • Rédiger {rep}/CONTEXTE.md — créé VIDE, injecté dans chaque "
          "prompt CCL (plafonné à 4000 caractères).")
    if git_res.get("commande_manuelle"):
        if git_res.get("contenu_preexistant"):
            print("   • Push initial volontairement NON déclenché — contenu "
                  "préexistant non relu :")
            for f in git_res["contenu_preexistant"][:10]:
                print(f"       - {f}")
            if len(git_res["contenu_preexistant"]) > 10:
                print(f"       … et {len(git_res['contenu_preexistant']) - 10} "
                      "autre(s).")
            print("     Après vérification, lancer :")
        else:
            print("   • Initialisation git incomplète — à terminer à la main :")
        for ligne in git_res["commande_manuelle"].splitlines():
            print(f"       {ligne}")
    print(f"   • Lancer le watcher : "
          f"python3 watcher.py --config configs/{nom}.conf")
    print("   • (Optionnel) Piloter le watcher depuis l'interface new_issue.py.")
    print(f"   Côté dépôt Bridge_Agent (distinct du projet {nom}) :")
    print("   • Vérifier puis committer/pousser les changements locaux "
          "(configs/, doc).")

    rappel_projet_claude(nom)


def rappel_projet_claude(nom: str) -> None:
    """Affiche un encadré ASCII rappelant de créer un Projet Claude dédié pour
    le projet fraîchement créé (action manuelle, hors périmètre du script,
    facilement oubliée). Le nom du projet est injecté dynamiquement.

    Le même rappel doit être proposé sous forme de modal après la création via
    le bouton web (issue #99) — voir le commentaire posté sur cette issue."""
    largeur = 72
    interne = largeur - 4          # colonnes utiles entre les bordures
    barre = "═" * largeur

    def largeur_affichee(txt: str) -> int:
        # Les glyphes « wide » (emoji…) occupent 2 colonnes à l'écran alors que
        # len() n'en compte qu'une : sans ça la bordure droite se décale.
        return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1
                   for c in txt)

    def ligne(txt: str = "") -> None:
        # Découpe le texte en lignes tenant dans l'encadré, coupe aux espaces.
        mots, courante = txt.split(), ""
        rendus = []
        for mot in mots:
            essai = f"{courante} {mot}".strip()
            if largeur_affichee(essai) > interne:
                rendus.append(courante)
                courante = mot
            else:
                courante = essai
        rendus.append(courante)
        for r in rendus or [""]:
            bourrage = " " * (interne - largeur_affichee(r))
            print(f"║ {r}{bourrage} ║")

    print()
    print(f"╔{barre}╗")
    ligne(f"💡 Pense à créer un Projet Claude dédié pour « {nom} »")
    ligne()
    ligne(f"Un Projet Claude dédié te donne un espace mémoire séparé dans "
          f"l'interface Claude pour « {nom} ». C'est une action manuelle, "
          "facultative, à faire depuis l'interface Claude.")
    ligne()
    ligne("Settings n'a plus besoin d'être modifié : le §2 de "
          "BRIDGE_AGENT_DOC.md fait foi automatiquement pour la "
          "reconnaissance du projet.")
    print(f"╚{barre}╝")


if __name__ == "__main__":
    main()

## #683 — point de rupture CSS pour écran plafonné ~1360×768 (poste fixe CCW)

Le PC fixe CCW est plafonné matériellement à 1360×768 (Intel HD Graphics
Ivy Bridge/G2020, aucun pilote plus récent disponible, câble VGA —
confirmé le 28/09/2026, remplacement prévu sous 1-2 mois mais l'interface
doit rester utilisable en attendant). À cette résolution, l'interface
n'avait qu'un seul point de rupture CSS existant, à `max-width:900px`
(`static/css/resultats.css`, issue #628/#633), trop étroit pour couvrir
1360px : la barre du haut, les onglets et le panneau latéral
« Infrastructure » se chevauchaient.

Deux nouveaux blocs `@media (max-width:1400px)`, dédiés et distincts du
`900px` existant (aucune touche à ce dernier, comportement mobile/tablette
inchangé) :
- `static/css/resultats.css` : `.resultats-layout{flex-direction:column}`,
  `.panneau-lateral-col{width:100%}`, `.panneau-lateral{width:auto}` —
  mêmes règles que le repli 900px, le panneau latéral Infrastructure passe
  sous le corps de l'onglet Résultats au lieu d'à côté.
- `static/css/base.css` : `.entete{flex-wrap:wrap}` et
  `.onglets{flex-wrap:wrap}` (+ `row-gap`) — la barre du haut (projet,
  boutons Nouveau projet/Lancer le watcher/Quitter) et les onglets
  (Résultats/Journal watcher/Configuration/CCW/Nouvelle issue) s'empilent
  proprement sur plusieurs lignes au lieu de déborder ou de forcer un
  défilement horizontal.

Seuil choisi à 1400px (marge au-dessus de 1360px pour absorber la
scrollbar verticale du navigateur) plutôt qu'exactement 1360px. Vérifié
par capture d'écran Playwright (serveur de dev local, sans configs de
projet dans ce worktree isolé) : à 1360×768 le panneau passe bien sous le
contenu sans chevauchement ; à 1600px de large le comportement d'origine
(panneau à côté) est inchangé — pas de régression sur écran large.
Aucune refonte visuelle : uniquement ces deux points de rupture ciblés,
réversibles en supprimant les blocs `@media` ajoutés.

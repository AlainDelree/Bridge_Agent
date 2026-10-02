## #700 — [fermé]/[ouvert] toujours visible en fin de ligne, même titre tronqué

- Bug : numéro, titre et suffixe `[fermé]`/`[ouvert]` étaient concaténés
  dans un seul span `ligne-texte` (`static/js/app.js`), tronqué par
  l'ellipsis CSS (`overflow:hidden;text-overflow:ellipsis;white-space:
  nowrap`). Pour un titre assez long, l'ellipsis coupait avant d'atteindre
  `[fermé]`/`[ouvert]`, qui disparaissait alors complètement de la ligne.
- `static/js/app.js` (~ligne 913) : le suffixe `[fermé]`/`[ouvert]` sort
  du span `ligne-texte` (qui ne garde que `#N — ` + titre) et devient un
  span `ligne-etat` distinct, placé juste après.
- `static/css/resultats.css` : nouvelle règle `.ligne-issue .ligne-etat`
  avec `flex-shrink:0;white-space:nowrap` pour ne jamais être rogné par
  l'ellipsis. Les règles de couleur/barré de `.resultat-traite` (normal,
  hover, sélectionnée) étendues à `.ligne-etat` pour rester cohérentes
  avec `.ligne-texte` (le comportement visuel sur une ligne cochée/
  traitée reste identique à avant, juste réparti sur deux spans).
- Résultat : sur une ligne de titre long, le titre se tronque avec une
  ellipsis (…), mais `[fermé]`/`[ouvert]` reste toujours visible en fin
  de ligne, quelle que soit la longueur du titre.

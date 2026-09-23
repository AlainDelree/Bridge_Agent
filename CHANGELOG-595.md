## 23 septembre 2026 — issue #595

Modal « Supprimer le projet » (zone dangereuse) : le bouton « Supprimer
définitivement » restait visuellement identique (rouge plein) même une
fois désactivé (`disabled`), car aucune règle CSS ne stylait cet état —
un utilisateur pouvait croire le bouton actif alors qu'un clic ne
déclenchait rien (comportement natif HTML silencieux, sans retour
visuel). La logique de grisage elle-même (`spMajBoutonEtat()` dans
`static/js/app.js`, issue #587) était déjà correcte : bouton désactivé
à l'ouverture, tant que les 3 cases ne sont pas cochées et que le nom
retapé ne correspond pas exactement au projet ciblé. Ajout de
`button.danger-plein:disabled{...}` dans `static/css/style.css` (fond
gris `#ccc`, texte `#888`, curseur `not-allowed`) pour que l'état
désactivé soit visible, symétriquement à `button.primaire:disabled`
déjà existant. Vérifié en conditions réelles (Playwright + Chromium
headless, projet de test temporaire hors dépôt) : gris tant que le nom
est incorrect, rouge dès la correspondance exacte.

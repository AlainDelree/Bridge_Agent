## 19 septembre 2026 — issue #575

Incident réel en mode `--externe` sur mobile : le bouton « Déconnexion »
se trouve pile sous le doigt quand on veut fermer le panneau
Infrastructure sur petit écran — clic accidentel, déconnexion
immédiate, obligeant à retaper le mot de passe.

`templates/index.html` : le bouton « Déconnexion » demande désormais
confirmation (`confirm('Se déconnecter ?')`) avant de naviguer vers
`/logout` — annulable, sans action si refusée. Même pattern déjà en
place pour le bouton « Quitter » (fonction `quitter()`,
`static/js/*.js`). Aucun changement d'apparence, de disposition ni de
media query : uniquement l'`onclick` du bouton, identique sur desktop
et mobile.

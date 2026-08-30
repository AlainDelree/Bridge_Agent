## #501 — finaliser_projet_ccw.ps1 : clarification du prompt de confirmation du token

Le message `Read-Host 'Appuie sur Entrée une fois le token créé et copié'` prêtait à
confusion : il pouvait être lu comme une demande de coller le token à cet endroit,
alors qu'il ne fait qu'attendre une touche Entrée pour continuer — le vrai collage
du token a lieu juste après, dans `mettre_a_jour_tokens_ccw.ps1` (« Collez la valeur
de GH_TOKEN »). Un utilisateur a déjà collé son token par erreur à cette invite.

Reformulé en : `'Ne colle RIEN ici : une fois le token créé et copié, appuie juste
sur Entrée pour continuer (le collage se fera à l'étape suivante)'`.

Le script personnel `creer_projet_ccw_complet.ps1` (hors dépôt officiel) n'est pas
accessible depuis ce worktree — la même formulation cohérente y est recommandée
manuellement si un message similaire y existe.

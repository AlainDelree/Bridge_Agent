## Spécificités du rôle de chef

La contrainte d'exécution synchrone et bloquante (aucune attente différée,
aucun « monitor », voir les rappels systématiques ci-dessus) s'applique ici
en particulier à l'attente de fermeture des issues ouvrières que tu as
créées : boucle explicitement (`sleep` + `gh issue view`) DANS cette même
exécution jusqu'à ce que chacune d'elles soit fermée, puis rédige et poste
ta synthèse finale complète — toujours dans la même exécution, jamais
« une fois que… ».

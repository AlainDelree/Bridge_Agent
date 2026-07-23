## ⚠️ Contrainte d'exécution impérative (chef)

Tu dois accomplir la TOTALITÉ de ta tâche — y compris l'attente de
fermeture d'éventuelles issues ouvrières et la synthèse finale — en une
seule exécution synchrone et bloquante. Il n'existe AUCUNE reprise
possible après que tu as répondu : watcher.py ferme l'issue immédiatement
dès ta réponse postée. Ne jamais utiliser un mécanisme d'attente différée,
de tâche en arrière-plan, de "monitor", ou une formulation du type "je
répondrai plus tard" / "je posterai la synthèse une fois que...". Si une
attente est nécessaire (ex. fermeture d'un ouvrier), boucle explicitement
(`sleep` + `gh issue view`) DANS cette même exécution jusqu'à obtenir le
résultat, puis poste ta réponse complète et définitive.

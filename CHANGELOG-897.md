## 17 novembre 2026 — issue #897

Incident #498 (scrabble) : un outil manquant (bandit) avait été installé par pip dans le venv partagé de Bridge_Agent, sans qu'aucune règle écrite ne l'interdise ni ne dise quoi faire à la place.

**`consignes/globales.md`** (389 caractères, injecté dans toute issue) : nouveau point « Outil manquant » — interdiction d'installer un paquet/outil dans un environnement partagé (venv Bridge_Agent, Python/npm global, système) ; les dépendances propres au projet traité restent permises ; outil absent → environnement temporaire hors dépôt détruit en fin de tâche, sinon arrêt et signalement ; toujours citer l'outil utilisé/manquant et sa version dans le rapport.

**`BRIDGE_AGENT_DOC.md` §11** (Conventions de code) : ajout d'une puce demandant à Claude Chat de préciser, dans l'issue, quoi faire si l'outil externe qu'elle demande est absent côté CCL/CCW — sans dupliquer le texte de `globales.md`.

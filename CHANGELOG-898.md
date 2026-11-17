## 17 novembre 2026 — issue #898

La procédure de restructuration du contexte d'un projet (CONTEXTE.md trop volumineux, découpage en fichiers `docs/contexte/<domaine>.md`) n'existait que dans la mémoire d'une conversation Claude Chat, perdue au fil des nouvelles conversations.

**`BRIDGE_AGENT_DOC.md` §12.3** (nouvelle sous-section, 30 lignes, juste après §12.2) : procédure à suivre par Claude Chat quand `CONTEXTE.md` d'un projet dépasse 4000 caractères ou qu'Alain le demande — mesurer avec `wc -m` (viser 3700 car.), rédiger une ou deux issues (étude puis implémentation si le contexte dépasse ~50 000 caractères), demander un inventaire puis le tri du contenu (règle vivante → fichier de domaine, récit/historique → vérifié contre un changelog puis supprimé ou listé pour décision, pas d'archive), interdire les valeurs sensibles, exiger un rapport détaillé. Renvoie à §12.2 et à `consignes/globales.md` pour les règles permanentes déjà écrites, sans les recopier.

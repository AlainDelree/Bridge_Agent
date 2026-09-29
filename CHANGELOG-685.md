## #685 — §11/§20 : exiger de demander à Alain avant d'utiliser le formulaire web comme repli quand aucun outil fichier n'est disponible

Cas constaté (dont un le 28/09/2026, projet Rummikub) : une conversation
Claude Chat sans outil fichier (`bash`/`create_file`) présentait le texte
d'une issue en clair pour qu'Alain le copie-colle dans `new_issue.py`, en
violation apparente de §11. Cause : §20 documente ce formulaire comme un
repli légitime, mais §11 et §20 ne précisaient pas explicitement qui doit
initier ce choix — une conversation sans outil fichier pouvait donc, de
bonne foi, s'appuyer sur §20 pour justifier le copier-coller.

Aucune suppression de la mention du formulaire web dans la doc (option
écartée : masquerait un usage réel et actif du système pour toute autre
conversation, créant d'autres angles morts).

- **§11** (`BRIDGE_AGENT_DOC.md`) : ajout — si aucun outil fichier n'est
  disponible dans la conversation en cours, Claude Chat le signale
  explicitement à Alain et demande la marche à suivre, plutôt que de
  basculer silencieusement vers le formulaire web de sa propre initiative.
- **§20** : précision symétrique — le formulaire reste un repli légitime,
  mais c'est à Alain de décider de l'utiliser, jamais à Claude Chat d'y
  basculer lui-même en l'invoquant comme justification.

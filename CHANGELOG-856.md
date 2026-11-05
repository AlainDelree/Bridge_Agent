## 5 novembre 2026 — issue #856

Correction d'un faux positif confirmé (code + tests) : l'avertissement
« Succès sans commit au-delà de la sauvegarde » (#764) et le garde-fou
voisin « verdict illisible avec commits » (#777) supposaient tous deux que
le PREMIER commit créé depuis le HEAD d'avant traitement est forcément
celui de sauvegarde, repéré par **position**. Exact pour un projet à
sauvegarde standard (le watcher fait lui-même ce commit, #846/#847), faux
pour un projet à `CMD_BACKUP` personnalisée (ex. alchess, gestionnaire de
sauvegarde hors git) : le watcher ne committe rien, et l'hypothèse prenait
alors l'unique commit de correctif pour une sauvegarde — faux positif
constaté sur 6 rapports sur 8 côté alchess (issues #255-#262, seule la
#257 légitime). Cause confirmée en lisant `watcher.py` ; non confirmée
contre l'historique git réel d'alchess, hors périmètre de ce worktree
(`/home/alain/NicLink`).

`_avertissement_succes_sans_commit` et `_commits_au_dela_sauvegarde`
excluent désormais ce commit par son **hash exact**
(`commit_sauvegarde_watcher`, déjà calculé par `_demarrer_traitement` pour
#846/#847), jamais plus par position — `None` (sauvegarde personnalisée ou
tentative de commit watcher en échec) signifie qu'aucun commit n'est à
exclure. Message de « succès sans commit » reformulé en ton neutre, sans
symbole d'alerte : dit que la tâche n'a produit aucun commit, que c'est
normal si rien n'était à modifier, et qu'il faut sinon relire le rapport.

Deuxième anomalie de même origine : le gabarit de rapport (`ligne_commits`
dans `lancer_claude`) demandait toujours un « [hash backup] » même pour un
projet sans commit de sauvegarde git — l'agent y plaçait alors le dernier
commit déjà présent avant la tâche, ce qui polluait la section « Fichiers
modifiés » (calculée côté web à partir des hash cités) avec les fichiers
d'un commit étranger à la tâche. Nouvelle forme pour `CMD_BACKUP`
personnalisée : un seul placeholder `[hash fix]`, consigne explicite de ne
citer que les commits réellement créés par la tâche. `consignes/
globales.md` (injecté dans tout prompt CCL) avait le même défaut — rappel
toujours valable du hash de sauvegarde watcher même quand ce projet n'en a
aucun — corrigé par une exception dédiée.

Côté interface web, `hashesDeCommit()`/`etatCommitsDeclares()`
(`static/js/app.js`) reconnaissaient déjà cette nouvelle forme sans
modification (extraction par motif hexadécimal générique, pas par libellé
« (backup)/(fix) ») — vérifié par deux nouveaux cas dans
`static/js/tests/hashes_commit.test.js` (gabarit à 3 formes désormais,
contre 2 avant cette issue).

Tests : `tests/test_sauvegarde_personnalisee_sans_commit_856.py` (nouveau,
10 scénarios — matrice 1/plusieurs/aucun commit × avec/sans commit de
sauvegarde watcher connu, plus le gabarit de prompt standard vs
personnalisé) ; `tests/test_ligne_verdict_764.py` et `tests/test_arret_
verdict_illisible_commits_777.py` adaptés à la nouvelle signature (hash
explicite en paramètre) sans changement de comportement pour les projets à
sauvegarde standard (aucun faux négatif nouveau). Doc : nouvelle puce au
§5 de `BRIDGE_AGENT_DOC.md` décrivant cet avertissement et son
déclenchement exact, absente avant cette issue.

py_compile : OK

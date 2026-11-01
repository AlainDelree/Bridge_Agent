## 1 novembre 2026 — issue #840

Renforce la puce « commit de sauvegarde » de `consignes/globales.md` et y
ajoute la méthode de rattrapage. La formulation précédente disait
seulement de faire le commit AVANT toute modification ; des agents s'y
prenaient en pratique après avoir déjà modifié des fichiers (constaté dans
les issues #830 et #838), rendant le commit inutile comme point de retour.

La nouvelle puce (lignes 5-12) précise : (a) le commit de sauvegarde est le
tout premier geste, avant toute modification et avant toute autre commande
qui écrit des fichiers ; (b) la forme à utiliser (`git commit
--allow-empty` si rien à capturer, sinon `git add -A` puis commit, en
renvoyant au garde-fou backup/reset existant) ; (c) la méthode de
rattrapage si des fichiers ont déjà été modifiés sans le commit préalable
(`git stash push -u`, commit, `git stash pop`, à signaler dans le rapport) ;
(d) le cas de modifications préexistantes non attribuables à l'agent, à
signaler dans le rapport plutôt qu'à tenter de les séparer.

Seule cette puce change ; aucune autre puce du fichier n'est touchée, ni
leur ordre. Fichier : 101 → 106 lignes (8 lignes ajoutées, 3 retirées).

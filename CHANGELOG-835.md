## 1 novembre 2026 — issue #835

Précharge du rapport : la préparation à l'avance (issue #832) se limitait à
tort aux « N premières issues non cochées » de TOUS les projets connus,
affichés ou non, sans ordre ni borne — `candidatsPrechargement`
(`static/js/resultats_coches.js`) ne retient désormais que les issues des
projets dont la pastille est sélectionnée, dans la fenêtre « par projet : N »
(même périmètre que les pastilles), triées de la plus ancienne à la plus
récente, avec une borne totale de préparations en attente ou prêtes
(`BORNE_TOTALE_PRECHARGEMENT = 6`, constante exportée). La file d'exécution
devient un tableau explicite (`filePrechargement`) : une entrée dont le
projet est désélectionné pendant qu'elle attend son tour est abandonnée sans
être préparée ; les préparations déjà prêtes sont conservées. Un repère
discret « prêt à copier » (pastille à contour vert + info-bulle) apparaît
désormais à côté de la case d'une issue dont le texte copié est préparé et
valide, et disparaît à la coche, à la péremption ou si le projet est
désélectionné — mis à jour à la fin de chaque préparation et au plus toutes
les 30s.

Côté serveur, un nouvel échantillonneur continu (`mesure_charge_interface.py`
+ `app/charge_interface.py`) écrit une ligne JSON par minute dans
`logs/charge_interface.log` (rotation par taille, réutilise
`JournalRotatifDate` de `watcher.py`) : secondes de processeur du serveur et
de ses fils (`os.times()`), requêtes de la minute, durée totale/max, route la
plus lente (gabarit Flask, jamais l'URL résolue — aucun numéro d'issue ni
titre dans ces lignes). Crochets `before_request`/`after_request` légers,
compteurs protégés par un verrou. La page envoie, à la fin de chaque série de
préparations, un résumé court à la nouvelle route `POST /mesure-precharge`
(champs numériques + mode stricts, corps limité à 1 Ko, mêmes règles de
connexion que le reste de l'interface). `scripts/rapport_charge_interface.py`
lit ce journal et ses archives et affiche, par jour, les agrégats (CPU
moyen/pic/95e centile, requêtes, route la plus lente, séries de précharge) —
lecture seule, `--jours N` (défaut 7) limité aux journées les plus récentes
présentes dans le journal.

Aucun frein automatique de la précharge n'est ajouté (décision à prendre sur
les mesures) ; le processeur de Firefox n'est pas mesuré ; le chemin de
copie, les messages du toast et le comportement de `--lan` restent inchangés.

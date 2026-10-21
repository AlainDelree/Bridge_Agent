## 21 octobre 2026 — issue #784

Diagnostic de l'issue #783 confirmé : `hashesDeCommit()` (`static/js/app.js`)
cherchait une ligne commençant par « Commits » immédiatement suivie de
« : », alors que le gabarit de réponse (`watcher.py::ligne_commits`) écrit
depuis le 30 août le chemin du dossier de travail entre les deux
(« Commits (dans {cwd_effectif}) : … »). La reconnaissance échouait donc
silencieusement pour toute issue, en mode écriture comme en lecture seule :
le bouton de copie du diff se comportait comme s'il n'y avait « rien à
copier », sans erreur visible, pendant que le bouton de copie globale
continuait de fonctionner en omettant simplement la partie diff. Le défaut a
survécu à une réécriture ultérieure de cette même ligne (#767), faute de
tout lien entre le gabarit et la reconnaissance.

- **`static/js/app.js` — `hashesDeCommit()` : motif élargi** pour tolérer ce
  qui s'intercale entre « Commits » et « : » (`/^\s*commits?\b[^:]*:/i` au
  lieu de `/^\s*commits?\s*:/i`), chemin de travail compris. La forme
  lecture seule (« Commits (dans …) : aucun (lecture seule) », sans aucun
  hash) continue de donner une liste vide — inchangé, vérifié par test.
  L'onglet de détail d'une issue, qui appelle la même fonction, bénéficie
  de la correction sans modification propre.
- **Test ajouté — `static/js/tests/hashes_commit.test.js`** : au lieu de
  recopier à la main une ligne d'exemple, ce test LIT le texte réel de la
  f-string `ligne_commits` dans `watcher.py` et construit ses lignes de test
  à partir de ce texte (en simulant le remplacement des placeholders `[hash
  backup]`/`[hash fix]` par l'agent, comme en conditions réelles). `app.js`
  n'étant pas un module ES, il est chargé dans un bac à sable `vm` minimal
  (stubs `document`/`window`/`fetch`/…) pour appeler la VRAIE fonction, pas
  une copie. Conséquence recherchée : si le gabarit change de forme à
  l'avenir, soit l'extraction ne trouve plus exactement 2 formes (échec
  explicite), soit la ligne produite change et la reconnaissance ne la
  retrouve plus — dans les deux cas ce test casse, pas le bouton en
  silence. Un commentaire croisé a été déposé aux deux endroits
  (`watcher.py` au-dessus de `ligne_commits`, `app.js` au-dessus de
  `hashesDeCommit`) pour que le lien entre gabarit et reconnaissance soit
  visible à la lecture, pas seulement dans ce test. Suite complète
  (`node --test static/js/tests/`) : 308/308 au vert après correctif ;
  vérifié que la régression originale (ancien motif) fait bien échouer le
  nouveau test avant d'être écartée.
- **Fragilité signalée, non traitée** : extraire des numéros de commit d'un
  texte libre rédigé par un agent restera fragile quel que soit le motif —
  toute reformulation du gabarit (même sans intention de casser la
  reconnaissance) peut la faire échouer à nouveau. Une source plus sûre
  existe déjà côté GitHub : l'API expose les commits d'une PR/issue
  indépendamment du texte du commentaire (ou, plus simple ici puisqu'il n'y
  a pas de PR, un champ structuré distinct du corps en prose — ex. une
  ligne JSON dédiée ou un commentaire caché — que `watcher.py` pourrait
  poser en plus du texte lisible). Décision volontairement laissée de côté :
  hors périmètre de cette tâche.

Fichiers touchés : `static/js/app.js`, `static/js/tests/hashes_commit.test.js`
(nouveau), `watcher.py` (commentaire seul, gabarit inchangé).

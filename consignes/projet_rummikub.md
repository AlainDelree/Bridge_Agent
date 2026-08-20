## Spécificités du projet Rummikub

- **Build CCW — mise à jour du clone (issue #406) :** l'étape de mise à
  jour du clone `C:\CCW_Share\CCW\rummikub` ne doit **jamais** utiliser
  `git pull --ff-only` : ce clone accumule entre chaque build des commits
  locaux non poussés (`version.json`, backup), donc le fast-forward échoue
  systématiquement. Utiliser à la place `fetch` + `reset --hard`, qui
  aligne proprement le clone sur `origin/master` sans merge ni conflit,
  quel que soit l'état local :

  ```
  git -C C:\CCW_Share\CCW\rummikub fetch origin
  git -C C:\CCW_Share\CCW\rummikub reset --hard origin/master
  ```

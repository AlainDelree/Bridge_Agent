## Règles impératives du projet AlChess (injectées à chaque issue)

- **Binaires tiers** (`engines/`, `.exe`, `.dll`, `lc0`) : lecture seule (chaînes, en-têtes, ressources de version). Ne jamais les exécuter, ni directement ni sous Wine : cela crée un `~/.wine` inutile et lance des programmes sur le poste d'Alain.
- **Serveur de test ou de vérification** : ne le démarrer que par `ALCHESS_SKIP_BOARD=1 ALCHESS_NO_BROWSER=1 python -m nicsoft.web`. Sans ces variables il ouvre un onglet dans le navigateur d'Alain, sollicite son échiquier et arrête le service ModemManager. Arrêter ensuite le serveur par son PID exact.
- **Suppressions de sécurité** : `# noqa` / `# nosec` seulement pour un faux positif jugé (urlopen sur adresse constante, subprocess à arguments fixes, aléa de jeu), après avoir cherché une correction ; une ligne de raison (au moins deux mots) juste au-dessus ou après, puis le code précis sur la ligne, jamais seul. Jamais en masse. Ne pas toucher `.audit.json` sans ordre explicite d'Alain.
- **Échiquier USB** : un seul accès ouvert à la fois (la nouvelle connexion ferme l'ancienne) ; chaque mode ferme l'échiquier à la fin de sa session ; les tests de connexion utilisent un faux module USB à ouverture exclusive.
- **CONTEXTE.md** : si tu le mets à jour, écris l'état réel, pas l'historique (l'historique va dans le `CHANGELOG-<N>.md` de ta tâche), et garde l'essentiel dans ses 4000 premiers caractères.
- **Parties Lichess** : aucun moteur d'échecs (Stockfish, Maia, Rodent, analyse), aucun livre d'ouvertures, explorateur, exercice ni indication de coup ne doit tourner ni être accessible pendant une partie en ligne (règle de fair-play de Lichess). Le jeton Lichess reste côté serveur, jamais envoyé au navigateur, jamais écrit dans un journal. Tout texte venu de Lichess (pseudos, messages) est inséré par `esc()`.
- **Tests** : aucun test automatique ne doit écrire dans le dossier réel de l'utilisateur (parties, configuration, journaux, données). Tout passe par un dossier temporaire ; un test de garde le vérifie.

## Lichess : jamais de partie réelle pendant le développement
Ne jamais ouvrir de recherche d'adversaire, de défi ni de partie sur le vrai Lichess, et ne jamais lire ni utiliser le vrai jeton d'Alain, ni dans les tests ni dans les essais : faux serveur local uniquement. Le réseau ne sert qu'à lire la documentation publique.

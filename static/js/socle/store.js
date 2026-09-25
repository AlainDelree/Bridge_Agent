// store.js — source de vérité unique de l'interface (issue #625, étape 1).
//
// RESPONSABILITÉ
//   Détenir l'état applicatif partagé, avec trois opérations et rien d'autre :
//   lecture (get), écriture (set/maj) et abonnement aux changements (abonner /
//   abonnerCle). Aucune brique ne détient d'état applicatif en double : quand
//   une fonctionnalité est sortie de l'ancien app.js (étapes suivantes), son
//   état vient vivre ICI, indexé de façon stable.
//
// CE QU'IL EXPOSE
//   - creerStore(etatInitial)  : fabrique générique, testable, sans DOM.
//   - store                    : l'instance unique de l'application, dont les
//                                tranches (slices) couvrent : issues indexées
//                                par projet+numéro, sélection courante, filtres,
//                                projets, watchers, état issues_inbox, son
//                                global, rate-limit, onglet actif.
//   - cleIssue(projet, numero) : clé canonique d'une issue ("projet#numero").
//
// NON-BUT À CETTE ÉTAPE
//   Le store est créé et testé mais NE PILOTE encore RIEN : l'ancien app.js
//   reste la seule source de vérité vivante de l'écran. Voir pont.js et
//   ARCHITECTURE.md (§ Refonte web) pour la procédure de migration.

/** Clé canonique d'une issue dans la tranche `issues`. */
export function cleIssue(projet, numero) {
  return `${projet}#${numero}`;
}

/**
 * Fabrique un petit store réactif générique.
 *
 * @param {object} etatInitial  État de départ (copié superficiellement).
 * @returns {{
 *   get: (cle?: string) => any,
 *   set: (cleOuObjet: string|object, valeur?: any) => void,
 *   maj: (cle: string, transformer: (ancienne:any)=>any) => void,
 *   abonner: (cb:(etat:object, cles:string[])=>void) => (()=>void),
 *   abonnerCle: (cle:string, cb:(valeur:any, etat:object)=>void) => (()=>void),
 * }}
 */
export function creerStore(etatInitial = {}) {
  let etat = { ...etatInitial };
  const abonnesGlobaux = new Set();      // notifiés à chaque changement
  const abonnesParCle = new Map();       // cle -> Set<cb>

  function get(cle) {
    return cle === undefined ? etat : etat[cle];
  }

  // set(cle, valeur) écrit une tranche ; set({a, b}) fusionne plusieurs tranches.
  function set(cleOuObjet, valeur) {
    let cles;
    if (cleOuObjet !== null && typeof cleOuObjet === 'object') {
      etat = { ...etat, ...cleOuObjet };
      cles = Object.keys(cleOuObjet);
    } else {
      etat = { ...etat, [cleOuObjet]: valeur };
      cles = [cleOuObjet];
    }
    notifier(cles);
  }

  // Mise à jour immuable d'une tranche à partir de sa valeur précédente.
  function maj(cle, transformer) {
    set(cle, transformer(etat[cle]));
  }

  function abonner(cb) {
    abonnesGlobaux.add(cb);
    return () => abonnesGlobaux.delete(cb);
  }

  function abonnerCle(cle, cb) {
    let s = abonnesParCle.get(cle);
    if (!s) { s = new Set(); abonnesParCle.set(cle, s); }
    s.add(cb);
    return () => s.delete(cb);
  }

  function notifier(cles) {
    // Copie défensive : un abonné peut se désabonner pendant la notification.
    for (const cb of [...abonnesGlobaux]) cb(etat, cles);
    for (const cle of cles) {
      const s = abonnesParCle.get(cle);
      if (s) for (const cb of [...s]) cb(etat[cle], etat);
    }
  }

  return { get, set, maj, abonner, abonnerCle };
}

// ─── Instance unique de l'application ───────────────────────────────────────
// Les tranches reprennent 1:1 l'état éparpillé aujourd'hui dans app.js, mais
// nommé et centralisé. `issues` est un dictionnaire indexé par cleIssue() (et
// non un tableau parcouru linéairement comme listeIssuesResultats aujourd'hui).

const socle = creerStore({
  issues: {},            // { "projet#numero": {…issueGitHub, projet} }
  timing: {},            // { "projet#numero": {timeout, max_essais, backoff, debut, sans_limite, estimation} } — décompte TIMEOUT + estimation (issue #627)
  selection: { projet: null, numero: null },
  filtres: { projetsActifs: [], ouvriers: false },
  projets: [],           // [{nom, depot, couleur, …}]
  watchers: {},          // { nomProjet: {pid, actif, …} }
  issuesInbox: { alarme: false, rejetes: [], historique: '' },
  son: 'plat',           // 'plat' | 'cloche' (interrupteur global du bip)
  rateLimit: null,       // { restant, limite, pourcent, etat } | null
  ongletActif: 'resultats', // nom de l'onglet actif (voir static/js/onglets.js)
});

// Aides spécifiques aux issues, construites sur la tranche `issues` indexée.
// Elles garantissent l'indexation par projet+numéro exigée par l'issue #625.
const aidesIssues = {
  lireIssue(projet, numero) {
    return socle.get('issues')[cleIssue(projet, numero)] || null;
  },
  ecrireIssue(issue) {
    if (!issue || issue.projet == null || issue.number == null) {
      throw new Error('ecrireIssue : issue.projet et issue.number sont requis');
    }
    socle.maj('issues', (courant) => ({
      ...courant,
      [cleIssue(issue.projet, issue.number)]: issue,
    }));
  },
  remplacerIssues(liste) {
    const index = {};
    for (const it of liste || []) index[cleIssue(it.projet, it.number)] = it;
    socle.set('issues', index);
  },
  listerIssues() {
    return Object.values(socle.get('issues'));
  },
};

export const store = Object.assign(socle, aidesIssues);

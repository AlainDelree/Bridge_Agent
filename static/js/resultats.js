// resultats.js — moteur de DONNÉES, d'ÉVÉNEMENTS et de BADGES de l'onglet
// Résultats (refonte web, étape 3, issue #627).
//
// RESPONSABILITÉ (ce que ce module a sorti de app.js)
//   - Le CHARGEMENT de la liste des issues (initial unique + ↻ explicite) et
//     des données de temps (décompte TIMEOUT + estimation), avec le STORE pour
//     source de vérité unique — plus aucun cache de liste en localStorage.
//   - Le CANAL /stream (via la brique sse), avec un traitement TOUJOURS CIBLÉ
//     sur le projet+issue concernés (jamais un rechargement de tous les
//     projets) : debut_issue, fin_issue, creation_issue (+ le fetch unique
//     post-dépassement de #334, réservé au décompte tombé à zéro).
//   - Le calcul et l'application des badges d'estimation et de décompte TIMEOUT.
//
// SOURCE DE VÉRITÉ
//   store.issues (dictionnaire indexé par cleIssue) et store.timing. app.js n'en
//   détient plus qu'un MIROIR (listeIssuesResultats / timingIssues), poussé par
//   ce module pour les fonctionnalités qui restent temporairement dans l'ancien
//   code (rendu DOM d'une ligne, filtres, panneau latéral, recherche…). Voir le
//   rapport de l'issue #627 pour la liste de ce qui reste dans app.js et pourquoi.
//
// RÈGLE ANTI-DOUBLE-CONNEXION
//   Ce module ouvre l'UNIQUE connexion /stream (sse.stream.connecter()). L'ancien
//   demarrerStreamFinIssue() d'app.js a été retiré dans le même mouvement. Le
//   canal /events (cycle de vie serveur) reste géré par app.js.

import { store, cleIssue } from './socle/store.js';
import { api } from './socle/api.js';
import { toasts } from './socle/toasts.js';
import { sse } from './socle/sse.js';
import { appelerAncien } from './socle/pont.js';

// ─────────────────────────────────────────────────────────────────────────────
// 1. LOGIQUE PURE (testée sous Node — voir static/js/tests/resultats.test.js)
//    Aucune dépendance au DOM ni au réseau : `maintenant` est passé en argument
//    (au lieu de Date.now()) pour rendre les calculs de badges déterministes.
// ─────────────────────────────────────────────────────────────────────────────

/** Formate une durée en secondes → "45s" / "3min 20s" (compact, lisible). */
export function formaterDuree(s) {
  s = Math.max(0, Math.floor(s));
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60), r = s % 60;
  return m + 'min' + (r ? ' ' + r + 's' : '');
}

// État visuel du badge de décompte TIMEOUT (issues #91/#106/#334). Reproduit à
// l'identique l'ancien formaterBadgeTempsRestant d'app.js, mais en renvoyant un
// descriptif { classe, texte, titre, budgetEpuise, masque } au lieu de muter le
// DOM. `opts.verifie` = le fetch unique post-dépassement a déjà confirmé l'issue
// encore ouverte (Set issuesDepassementVerifie). `budgetEpuise` signale la seule
// branche qui programme le fetch unique de #334.
export function calculerBadgeTempsRestant(t, maintenant, opts = {}) {
  if (!t) return { masque: true };
  if (!t.debut) {
    return { classe: 'ligne-tempsrestant tr-attente', texte: '⏳ en file',
             titre: 'En attente de prise en charge par le watcher' };
  }
  if (t.sans_limite) {
    return { classe: 'ligne-tempsrestant tr-illimite', texte: '⏳ en cours (pas de limite)',
             titre: 'Priorité haute/critique : réessais illimités, pas de deadline' };
  }
  const essais  = Math.max(1, t.max_essais || 1);
  const backoff = t.backoff || 0;
  const cycle   = t.timeout + backoff;
  const budget  = t.timeout * essais + backoff * (essais - 1);
  const ecoule  = (maintenant - new Date(t.debut).getTime()) / 1000;
  const restant = Math.round(budget - ecoule);
  const tentative = Math.min(essais, Math.floor(ecoule / cycle) + 1);

  if (restant > 0 && tentative <= 1) {
    return { classe: 'ligne-tempsrestant ' + (restant <= 30 ? 'tr-bientot' : 'tr-ok'),
             texte: '⏳ ' + formaterDuree(restant),
             titre: 'Temps restant estimé sur le budget total (' + essais
                  + ' tentative(s) × ' + t.timeout + 's' + (backoff ? ' + backoffs' : '')
                  + ') avant dépassement réel.' };
  }
  if (restant > 0) {
    return { classe: 'ligne-tempsrestant tr-retry',
             texte: '🔄 tentative ' + tentative + '/' + essais + ' — ' + formaterDuree(restant),
             titre: 'Le 1er cycle TIMEOUT (' + t.timeout + 's) a été dépassé, mais le '
                  + 'watcher dispose de ' + essais + ' tentatives. Reste ~'
                  + formaterDuree(restant) + ' sur le budget total ; pas encore un échec.' };
  }
  if (opts.verifie) {
    return { classe: 'ligne-tempsrestant tr-depasse',
             texte: '⌛ dépassement — rafraîchir ↻',
             titre: 'Budget total épuisé (' + essais + ' tentatives × ' + t.timeout + 's'
                  + (backoff ? ' + backoffs' : '') + ') ; la vérification automatique 15s '
                  + "après le dépassement montre l'issue toujours ouverte. Cliquez sur ↻ "
                  + 'pour revérifier — aucune autre vérification automatique ne sera programmée.' };
  }
  return { classe: 'ligne-tempsrestant tr-depasse',
           texte: '⌛ 0s — budget épuisé',
           titre: 'Budget total épuisé (' + essais + ' tentatives × ' + t.timeout + 's'
                + (backoff ? ' + backoffs' : '') + ') ; intervention humaine probable '
                + '(label needs-human). Vérification automatique programmée dans 15s ; '
                + 'en cas de doute, ↻ revérifie immédiatement.',
           budgetEpuise: true };
}

// État visuel du badge d'estimation prédictive (issue #108/#112). Reproduit à
// l'identique l'ancien formaterBadgeEstimation d'app.js, en renvoyant un
// descriptif { classe, texte, titre, masque } au lieu de muter le DOM.
export function calculerBadgeEstimation(t, maintenant) {
  const est = t && t.estimation;
  if (!est) return { masque: true };
  if (est.fiabilite === 'aucune' || est.mediane == null) {
    return { classe: 'ligne-estimation est-aucune', texte: '◦ pas encore de données',
             titre: 'Aucune issue fermée pour cette catégorie (projet + type + mode). '
                  + "L'estimation apparaîtra dès qu'au moins une issue similaire aura été "
                  + 'traitée. Le décompte à droite reste affiché normalement.' };
  }
  const cls = est.fiabilite === 'sur'     ? 'est-sur'
            : est.fiabilite === 'correct' ? 'est-correct'
            :                               'est-incertain';
  const libFiab = est.fiabilite === 'sur'     ? 'fiable'
                : est.fiabilite === 'correct' ? 'correcte'
                :                               'incertaine (peu de données)';
  const rappel = ' À ne pas confondre avec le décompte à droite, qui est le temps '
               + 'restant réel sur le TIMEOUT configuré (seule vraie alerte de blocage).';
  if (!t.debut) {
    return { classe: 'ligne-estimation ' + cls, texte: '≈ ' + formaterDuree(est.mediane),
             titre: 'Durée médiane observée sur ' + est.n + ' issue(s) fermée(s) du même '
                  + 'projet + type + mode — estimation ' + libFiab + '. Le décompte estimé '
                  + 'démarrera dès la prise en charge par le watcher.' + rappel };
  }
  const ecoule  = (maintenant - new Date(t.debut).getTime()) / 1000;
  const restant = Math.round(est.mediane - ecoule);
  if (restant > 0) {
    return { classe: 'ligne-estimation ' + cls, texte: '≈ ' + formaterDuree(restant),
             titre: 'Temps restant ESTIMÉ avant la durée médiane (' + formaterDuree(est.mediane)
                  + ' sur ' + est.n + ' issue(s) similaires, estimation ' + libFiab
                  + '). Simple repère prédictif, pas une limite dure.' + rappel };
  }
  return { classe: 'ligne-estimation est-depasse', texte: '≈ estimation dépassée',
           titre: 'La durée médiane estimée (' + formaterDuree(est.mediane) + ') est dépassée de '
                + formaterDuree(-restant) + ", mais ce n'est qu'une estimation indicative, pas "
                + "une limite dure : l'issue peut légitimement durer plus longtemps." + rappel };
}

// Décide, à partir de l'état courant et d'un événement /stream, l'action CIBLÉE
// à mener — cœur du correctif de l'issue #627 : `debut_issue` recharge le
// timing et ne passe JAMAIS par la vérification post-dépassement (#334), quelle
// que soit la présence antérieure de l'issue.
export function planifierEvenementSse(etat, ev) {
  const cle = cleIssue(ev.projet, ev.numero);
  const connue = !!(etat && etat.issues && etat.issues[cle]);
  if (ev.type === 'creation_issue') return { action: 'creer', cle, connue };
  if (ev.type === 'debut_issue')    return { action: 'debut', cle, connue };
  if (ev.type === 'fin_issue')      return { action: 'fin',   cle, connue };
  return { action: 'ignorer', cle, connue };
}

// Fusionne un chargement de liste en CONSERVANT les issues des projets non
// refetchés ET des projets dont le fetch a ÉCHOUÉ (correctif anomalie #3 :
// un projet en échec ne disparaît plus en silence). `chargements` =
// [{projet, succes, issues}]. Renvoie un tableau trié par date décroissante.
export function fusionnerChargement(anciennes, nomsFetch, chargements) {
  const fetchSet = new Set(nomsFetch);
  const echecs = new Set(chargements.filter(c => !c.succes).map(c => c.projet));
  const conservees = (anciennes || []).filter(
    it => !fetchSet.has(it.projet) || echecs.has(it.projet));
  const nouvelles = chargements.filter(c => c.succes).flatMap(
    c => (c.issues || []).map(it => Object.assign({}, it, { projet: c.projet })));
  return conservees.concat(nouvelles)
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. ORCHESTRATION NAVIGATEUR (DOM + réseau + store)
//    Rien de ce qui suit ne s'exécute à l'import ; tout part d'initialiser().
// ─────────────────────────────────────────────────────────────────────────────

const DELAI_FETCH_DEPASSEMENT_MS = 15000;   // marge laissée au watcher (issue #334)

let initialFait = false;                    // le chargement initial (unique) a-t-il eu lieu ?
let ongletActif = false;
let intervalTick = null;                    // recalcul 1 s des badges (client seul, aucun réseau)
const fetchDepassementProgramme = new Set();// clés dont le fetch unique #334 est déjà programmé
const depassementVerifie = new Set();       // clés confirmées encore ouvertes après le fetch #334

function maintenant() { return Date.now(); }
function nowIso() { return new Date().toISOString(); }

// Noms de projets disponibles, lus depuis le sélecteur global (peuplé côté serveur).
function nomsProjets() {
  const sel = document.getElementById('projet');
  if (!sel) return [];
  return [...sel.options].map(o => o.value).filter(Boolean);
}

// Limite « par projet » (issue #271) : lue via le pont (l'ancien code garde le
// champ de saisie et sa persistance) ; repli sur 5 si indisponible.
function limiteParProjet() {
  const v = appelerAncien('limiteIssuesProjet');
  return Number.isFinite(v) ? v : 5;
}

function timingCourant() { return store.get('timing') || {}; }
function listeCourante() { return store.listerIssues(); }
function trier(liste) {
  return liste.slice().sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
}

// Pousse l'état du store vers le miroir d'app.js (listeIssuesResultats /
// timingIssues), consommé par les fonctionnalités restées dans l'ancien code
// (panneau latéral, pastilles, recherche…).
function synchroniserMiroir() {
  appelerAncien('__resultatsMiroirListe', trier(listeCourante()));
  appelerAncien('__resultatsSetTiming', timingCourant());
}

// Rendu COMPLET de la liste (chargement initial, ↻, apparition d'une ligne) :
// délègue le rendu DOM à l'ancien code (appliquerListeIssues), qui reste seul
// responsable du markup d'une ligne (case à cocher, badges ✅/Diff/All, etc.).
function rendreListeComplete() {
  const liste = trier(listeCourante());
  appelerAncien('__resultatsSetTiming', timingCourant());
  appelerAncien('appliquerListeIssues', liste, nomsProjets());  // → rendreListeIssues → majBadges()
}

// Applique tous les badges d'estimation + décompte aux lignes présentes dans le
// DOM (recalcul pur, aucun appel réseau). Appelée chaque seconde et après chaque
// rendu. Programme, le cas échéant, le fetch unique post-dépassement (#334).
export function majBadges() {
  synchroniserMiroir();
  const t0 = maintenant();
  const timing = timingCourant();
  document.querySelectorAll('#liste-issues .ligne-issue').forEach((ligne) => {
    const cle = cleIssue(ligne.dataset.projet, ligne.dataset.numero);
    const t = timing[cle];
    const badgeEst = ligne.querySelector('.ligne-estimation');
    if (badgeEst) appliquerBadge(badgeEst, calculerBadgeEstimation(t, t0), 'ligne-estimation');
    const badge = ligne.querySelector('.ligne-tempsrestant');
    if (!badge) return;
    const etat = calculerBadgeTempsRestant(t, t0, { verifie: depassementVerifie.has(cle) });
    appliquerBadge(badge, etat, 'ligne-tempsrestant');
    if (etat.budgetEpuise) programmerFetchDepassement(ligne.dataset.projet, ligne.dataset.numero);
  });
}

function appliquerBadge(badge, etat, classeBase) {
  if (!etat || etat.masque) {
    badge.className = classeBase;
    badge.style.display = 'none';
    badge.textContent = '';
    return;
  }
  badge.style.display = '';
  badge.className = etat.classe;
  badge.textContent = etat.texte;
  badge.title = etat.titre;
}

// ─── Chargement de la liste (initial / ↻ / rafraîchissement action) ──────────
async function chargerListe(nomsAFetcher) {
  const noms = nomsProjets();
  if (!noms.length) { appelerAncien('__resultatsListeVide'); return; }
  const nomsFetch = Array.isArray(nomsAFetcher)
    ? nomsAFetcher.filter(n => noms.includes(n))
    : noms;
  const lim = limiteParProjet();
  appelerAncien('majIndicateurListe', true);
  const chargements = await Promise.all(nomsFetch.map(async (nom) => {
    try {
      const liste = await api.get(
        '/issues-liste/' + encodeURIComponent(nom) + '?limite=' + encodeURIComponent(lim),
        { silencieux: true });
      if (!Array.isArray(liste)) return { projet: nom, succes: false, issues: [] };
      return { projet: nom, succes: true, issues: liste };
    } catch (e) {
      return { projet: nom, succes: false, issues: [] };
    }
  }));
  appelerAncien('majIndicateurListe', false);
  const echecs = chargements.filter(c => !c.succes).map(c => c.projet);
  if (echecs.length) {
    toasts.erreur('Résultats — échec de chargement : ' + echecs.join(', ')
                + ' (données précédentes conservées).');
  }
  const fusionnee = fusionnerChargement(listeCourante(), nomsFetch, chargements);
  store.remplacerIssues(fusionnee);
  rendreListeComplete();
}

// ─── Données de temps (décompte + estimation) ────────────────────────────────
// Met à jour le timing d'UN projet à partir de sa liste /issues-en-attente :
// purge les entrées de ce projet puis réinjecte les issues ouvertes. Renvoie la
// liste brute reçue (ou null en cas d'échec — badges conservés).
async function chargerTimingProjet(nom) {
  let liste;
  try {
    liste = await api.get('/issues-en-attente/' + encodeURIComponent(nom), { silencieux: true });
  } catch (e) { return null; }
  if (!Array.isArray(liste)) return null;
  const timing = Object.assign({}, timingCourant());
  for (const cle of Object.keys(timing)) {
    if (cle.startsWith(nom + '#')) delete timing[cle];
  }
  for (const it of liste) {
    timing[cleIssue(nom, it.number)] = {
      timeout: it.timeout, max_essais: it.max_essais, backoff: it.backoff,
      debut: it.debut, sans_limite: it.sans_limite, estimation: it.estimation,
    };
  }
  store.set('timing', timing);
  return liste;
}

async function chargerTimingTous() {
  const noms = nomsProjets();
  const echecs = [];
  await Promise.all(noms.map(async (nom) => {
    const liste = await chargerTimingProjet(nom);
    if (liste === null) echecs.push(nom);
  }));
  if (echecs.length) {
    toasts.avertissement('Résultats — décompte non rechargé : ' + echecs.join(', ')
                       + ' (badges précédents conservés).');
  }
  majBadges();
}

// ─── Fetch unique au dépassement du TIMEOUT (issue #334) ─────────────────────
function programmerFetchDepassement(projet, numero) {
  const cle = cleIssue(projet, numero);
  if (fetchDepassementProgramme.has(cle)) return;
  fetchDepassementProgramme.add(cle);
  setTimeout(() => verifierApresDepassement(projet, numero), DELAI_FETCH_DEPASSEMENT_MS);
}

// Exécuté 15 s après le dépassement. Issue fermée/needs-human → ligne mise à
// jour (badge terminal, arrêt du décompte) ; encore ouverte → badge « ↻ » et
// AUCUN autre fetch automatique. RÉSERVÉ au décompte tombé à zéro — jamais
// appelé par debut_issue (correctif #627).
async function verifierApresDepassement(projet, numero) {
  const cle = cleIssue(projet, numero);
  let it;
  try {
    it = await api.get('/issue/' + encodeURIComponent(projet) + '/' + encodeURIComponent(numero),
                       { silencieux: true });
  } catch (e) { return; }
  if (!it || it.erreur) return;
  const nomsLabels = (it.labels || []).map(l => ((l && l.name) || l || '').toLowerCase());
  if ((it.state || '').toUpperCase() === 'CLOSED' || nomsLabels.includes('needs-human')) {
    ecrireChampsIssue(projet, numero, it);
    supprimerTiming(cle);
    majLigneConnue(projet, numero);
  } else {
    depassementVerifie.add(cle);
    majBadges();
  }
}

function ecrireChampsIssue(projet, numero, it) {
  const cle = cleIssue(projet, numero);
  const ancienne = store.get('issues')[cle] || {};
  store.ecrireIssue(Object.assign({}, ancienne, {
    number: it.number, title: it.title, state: it.state,
    labels: it.labels, createdAt: it.createdAt || ancienne.createdAt, projet,
  }));
}

function supprimerTiming(cle) {
  const timing = Object.assign({}, timingCourant());
  delete timing[cle];
  store.set('timing', timing);
}

// Met à jour la SEULE ligne DOM d'une issue déjà présente (préserve la sélection)
// en déléguant à remplacerLigneIssue d'app.js via le pont.
function majLigneConnue(projet, numero) {
  synchroniserMiroir();
  appelerAncien('__resultatsRemplacerLigne', projet, numero);
}

// ─── Traitement des événements /stream (toujours CIBLÉ) ──────────────────────
function traiterNotif(notif) {
  if (!notif || !notif.projet || notif.numero == null) return;
  const plan = planifierEvenementSse(store.get(), notif);
  if (plan.action === 'debut')       surDebutIssue(notif.projet, notif.numero);
  else if (plan.action === 'fin')    surFinIssue(notif.projet, notif.numero);
  else if (plan.action === 'creer')  surCreationIssue(notif.projet, notif.numero, notif.titre);
  // Le panneau latéral (issue #375) s'abonne lui-même à 'derniereNotifIssue'
  // (voir panneau_lateral.js) — plus de communication de module à module par
  // le pont ici (issue #632).
}

// debut_issue : recharge le timing CIBLÉ de cette issue (le décompte démarre) et
// l'ajoute à la liste si absente. Ne passe JAMAIS par la vérification
// post-dépassement (correctif anomalie #2).
async function surDebutIssue(projet, numero) {
  const cle = cleIssue(projet, numero);
  const connueAvant = !!store.get('issues')[cle];
  const liste = await chargerTimingProjet(projet);
  if (!connueAvant) {
    const info = Array.isArray(liste)
      ? liste.find(it => String(it.number) === String(numero)) : null;
    if (info) {
      store.ecrireIssue({ projet, number: info.number, title: info.title,
                          state: 'OPEN', labels: info.labels || [], createdAt: nowIso() });
    }
  }
  if (!connueAvant && store.get('issues')[cle]) rendreListeComplete();
  else majBadges();
}

// fin_issue : met à jour la ligne (état final, arrêt du décompte). Un seul fetch
// détail CIBLÉ sur l'issue concernée.
async function surFinIssue(projet, numero) {
  const cle = cleIssue(projet, numero);
  const connueAvant = !!store.get('issues')[cle];
  let it;
  try {
    it = await api.get('/issue/' + encodeURIComponent(projet) + '/' + encodeURIComponent(numero),
                       { silencieux: true });
  } catch (e) {
    toasts.erreur('Résultats — mise à jour impossible pour ' + projet + ' #' + numero + '.');
    return;
  }
  if (!it || it.erreur) return;
  ecrireChampsIssue(projet, numero, it);
  supprimerTiming(cle);
  if (connueAvant) majLigneConnue(projet, numero);
  else rendreListeComplete();
}

// creation_issue (contrat #9a : projet, numero, titre, fichier?) : fait
// apparaître la ligne avec « en file », puis l'enrichit (labels + estimation)
// via un fetch CIBLÉ sur le projet. Codé même si l'événement n'est pas encore
// émis.
async function surCreationIssue(projet, numero, titre) {
  const cle = cleIssue(projet, numero);
  if (!store.get('issues')[cle]) {
    store.ecrireIssue({ projet, number: Number(numero), title: titre || ('#' + numero),
                        state: 'OPEN', labels: [], createdAt: nowIso() });
  }
  const timing = Object.assign({}, timingCourant());
  if (!timing[cle]) {
    // Placeholder « en file » (debut null) → badge « ⏳ en file » immédiat.
    timing[cle] = { timeout: null, max_essais: null, backoff: 0,
                    debut: null, sans_limite: false, estimation: null };
  }
  store.set('timing', timing);
  rendreListeComplete();
  await chargerTimingProjet(projet);   // enrichit labels/estimation/timeout réels
  rendreListeComplete();
}

// ─── Cycle de vie de l'onglet (aucun rechargement réseau à l'activation) ─────
function demarrerTick() {
  majBadges();
  arreterTick();
  intervalTick = setInterval(majBadges, 1000);
}
function arreterTick() {
  if (intervalTick) { clearInterval(intervalTick); intervalTick = null; }
}

function onActiverOnglet() {
  ongletActif = true;
  if (!initialFait) {
    initialFait = true;
    chargerInitial();                  // UNIQUE chargement réseau
  } else {
    rendreListeComplete();             // simple rendu depuis le store, AUCUN réseau
  }
  demarrerTick();
}

function onDesactiverOnglet() {
  ongletActif = false;
  arreterTick();
}

async function chargerInitial() {
  await chargerListe();
  await chargerTimingTous();
}

// ↻ explicite : recharge liste + décompte (seul geste réseau hors initial/SSE).
async function rafraichir(nomsAFetcher) {
  await chargerListe(nomsAFetcher);
  await chargerTimingTous();
}

// ─── Amorçage (appelé une fois par index.js) ─────────────────────────────────
function initialiser() {
  // Abonnement aux notifications /stream (déposées dans le store par sse.js).
  store.abonnerCle('derniereNotifIssue', (notif) => traiterNotif(notif));
  // Activation/désactivation de l'onglet Résultats : abonnement direct au
  // store (issue #632), plus d'appel via le pont depuis onglets.js — cet
  // abonnement doit être posé AVANT que index.js n'active l'onglet par défaut
  // (voir onglets.js#activerOngletParDefaut) pour recevoir la notification
  // initiale, store.set() notifiant toujours ses abonnés même à valeur
  // inchangée.
  store.abonnerCle('ongletActif', (nom) => {
    if (nom === 'resultats') onActiverOnglet(); else onDesactiverOnglet();
  });
  // UNIQUE connexion /stream (permanente, comme l'ancien code depuis #515).
  sse.stream.connecter();
}

// Objet publié sous window.Bridge.resultats (via installerPont dans index.js) :
// rafraichir/chargerListe/majBadges sont l'API consommée par l'ancien app.js
// pendant la transition ; onActiverOnglet/onDesactiverOnglet ne sont plus
// appelées que par l'abonnement à store.ongletActif ci-dessus (issue #632),
// exposées ici surtout pour rester testables directement (voir
// static/js/tests/resultats.test.js).
export const resultats = {
  initialiser,
  onActiverOnglet,
  onDesactiverOnglet,
  rafraichir,
  chargerListe,
  majBadges,
};

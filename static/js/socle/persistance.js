// persistance.js — accès au localStorage (issue #625, étape 1 ; migration
// terminée à l'issue #644).
//
// RESPONSABILITÉ
//   LE seul point d'accès au localStorage, RESTREINT aux préférences d'interface
//   locales (filtres, largeur de colonne, dernier projet, cases cochées…). Rien
//   qui soit une source de vérité serveur : les données métier vivent dans le
//   store et sont rechargées via api. Toute lecture/écriture est protégée par
//   try/catch (mode privé, quota) et par une garde d'existence de localStorage
//   (import sûr sous Node — le backend est résolu à l'appel, pas à l'import).
//
// CE QU'IL EXPOSE
//   - lire(cle, defaut)          / ecrire(cle, valeur)   : valeurs JSON.
//   - lireTexte(cle, defaut)     / ecrireTexte(cle, val) : valeurs brutes
//                                  (compat clés historiques stockées en texte).
//   - supprimer(cle)
//   - supprimerParPrefixe(prefixe)
//   - toutesLesEntrees() : { cle, valeur brute }[] — scan à préfixe variable
//     (ex. migration des clés historiques `resultat-coche:*`).
//   - cleCacheDetail(nom, numero) : construit la clé de cache détail d'une issue.
//   - clesCacheDetailPourProjets(cles, noms) / clesCacheDetailHorsProjets(cles,
//     nomsActifs) : sélection PURE des clés de cache détail à purger
//     (testables sans DOM/localStorage).
//   - purgerCacheDetailProjets(noms) / purgerCacheDetailHorsProjets(nomsActifs) :
//     purge réelle correspondante.
//   - purgerProjet(nom) : purge toutes les clés propres à un projet supprimé
//     (cache détail + son entrée dans le filtre de l'onglet Résultats).
//   - CLES : les clés localStorage de l'interface (issue #644 : app.js n'y
//     accède plus qu'à travers ce module, via window.Bridge.persistance).
//
// Depuis l'issue #644, app.js (script classique, pas de `import`) passe par
// window.Bridge.persistance (voir socle/pont.js) pour tout accès au
// localStorage — plus aucun accès direct ailleurs.

function backend() {
  try {
    return (typeof localStorage !== 'undefined') ? localStorage : null;
  } catch {
    return null;   // accès localStorage peut lever (cookies bloqués)
  }
}

export function lire(cle, defaut = null) {
  const s = backend();
  if (!s) return defaut;
  try {
    const brut = s.getItem(cle);
    return brut == null ? defaut : JSON.parse(brut);
  } catch {
    return defaut;
  }
}

export function ecrire(cle, valeur) {
  const s = backend();
  if (!s) return;
  try { s.setItem(cle, JSON.stringify(valeur)); } catch { /* quota / privé */ }
}

export function lireTexte(cle, defaut = null) {
  const s = backend();
  if (!s) return defaut;
  try {
    const brut = s.getItem(cle);
    return brut == null ? defaut : brut;
  } catch {
    return defaut;
  }
}

export function ecrireTexte(cle, valeur) {
  const s = backend();
  if (!s) return;
  try { s.setItem(cle, String(valeur)); } catch { /* quota / privé */ }
}

export function supprimer(cle) {
  const s = backend();
  if (!s) return;
  try { s.removeItem(cle); } catch { /* ignoré */ }
}

export function supprimerParPrefixe(prefixe) {
  const s = backend();
  if (!s) return;
  try {
    const aSupprimer = [];
    for (let i = 0; i < s.length; i++) {
      const cle = s.key(i);
      if (cle && cle.startsWith(prefixe)) aSupprimer.push(cle);
    }
    for (const cle of aSupprimer) s.removeItem(cle);
  } catch { /* ignoré */ }
}

// Clés localStorage de l'interface — SOURCE UNIQUE (issue #644). app.js ne
// définit plus ses propres constantes dupliquées : il lit celles-ci via
// window.Bridge.persistance.CLES.
export const CLES = {
  projetActif: 'bridge_projet_actif',        // texte
  cacheIssues: 'bridge_cache_issues',        // JSON
  limiteIssues: 'bridge_limite_issues_projet',
  filtresResultats: 'bridge_filtres_resultats', // JSON
  filtreOuvriers: 'bridge_filtre_ouvriers',
  largeurTitre: 'bridge_largeur_titre',  // obsolète (issue #633) : purgée au chargement, voir resultats.js#initialiser
  notifPc: 'bridge_notif_pc',
  prefixeCacheDetail: 'bridge_cache_detail_',   // + nom + '_' + numero
  prefixeCocheResultat: 'resultat-coche:',      // + projet + ':' + numero
};

// Construit la clé de cache détail d'une issue précise.
export function cleCacheDetail(nom, numero) {
  return CLES.prefixeCacheDetail + nom + '_' + numero;
}

// Liste toutes les clés/valeurs brutes du localStorage — pour les scans à
// préfixe variable (ex. resultats_coches.js, migration des clés historiques
// `resultat-coche:*`). Valeurs en texte brut (pas de JSON.parse) : à
// l'appelant de les interpréter.
export function toutesLesEntrees() {
  const s = backend();
  if (!s) return [];
  const entrees = [];
  for (let i = 0; i < s.length; i++) {
    const cle = s.key(i);
    if (cle) entrees.push({ cle, valeur: s.getItem(cle) });
  }
  return entrees;
}

function toutesLesCles() {
  return toutesLesEntrees().map(e => e.cle);
}

// ─── Sélection PURE des clés de cache détail à purger (issue #644) ─────────
// Aucun accès localStorage ici : reçoivent la liste des clés en argument,
// testables sans DOM/backend (voir tests/persistance.test.js).

// Clés de cache détail appartenant à l'un des projets donnés.
export function clesCacheDetailPourProjets(cles, noms) {
  return cles.filter(cle =>
    (noms || []).some(nom => cle.startsWith(CLES.prefixeCacheDetail + nom + '_')));
}

// Clés de cache détail n'appartenant à AUCUN des projets actifs — celles à
// purger quand un projet sort du filtre plutôt que de s'accumuler
// indéfiniment (issue #644).
export function clesCacheDetailHorsProjets(cles, nomsActifs) {
  return cles.filter(cle =>
    cle.startsWith(CLES.prefixeCacheDetail)
    && !(nomsActifs || []).some(nom => cle.startsWith(CLES.prefixeCacheDetail + nom + '_')));
}

// Purge le cache détail des projets donnés, ou TOUT le cache détail si `noms`
// est absent (rechargement complet, ex. ↻ sans filtre restreint).
export function purgerCacheDetailProjets(noms) {
  if (!noms) { supprimerParPrefixe(CLES.prefixeCacheDetail); return; }
  clesCacheDetailPourProjets(toutesLesCles(), noms).forEach(cle => supprimer(cle));
}

// Purge le cache détail des projets qui ne sont plus dans le filtre actif
// (issue #644 : évite l'accumulation indéfinie d'un projet consulté puis
// retiré du filtre). À appeler à chaque ↻ ou changement de filtre.
export function purgerCacheDetailHorsProjets(nomsActifs) {
  clesCacheDetailHorsProjets(toutesLesCles(), nomsActifs).forEach(cle => supprimer(cle));
}

// Purge toutes les clés propres à un projet supprimé : son cache détail, et
// son entrée dans le filtre de l'onglet Résultats (issue #644, fuite
// confirmée — soumettreSupprimerProjet ne purgeait rien côté navigateur).
export function purgerProjet(nom) {
  supprimerParPrefixe(CLES.prefixeCacheDetail + nom + '_');
  const filtres = lire(CLES.filtresResultats, null);
  if (filtres && typeof filtres === 'object' && Object.prototype.hasOwnProperty.call(filtres, nom)) {
    delete filtres[nom];
    ecrire(CLES.filtresResultats, filtres);
  }
}

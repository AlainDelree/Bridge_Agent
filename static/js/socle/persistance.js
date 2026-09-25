// persistance.js — accès au localStorage (issue #625, étape 1).
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
//   - CLES : rappel des clés historiques d'app.js (pour la migration).
//
// Les clés historiques restent lues/écrites par l'ancien app.js à l'étape 1 ;
// ce module ne les remplace pas encore, il documente et outille la migration.

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

// Rappel documentaire des clés d'interface historiques (cf. app.js). Utile aux
// étapes suivantes pour migrer sans casser la compatibilité ascendante.
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

let sourceSSE = null;

let intervalWatchers = null;

// Dernier projet ayant reçu une issue dans CETTE session (onglet ouvert). Sert
// à déclencher un second avertissement dans envoyerIssue() si l'utilisateur
// change de projet juste avant l'envoi. Réinitialisé à chaque rechargement.
let sessionDernierEnvoi = null;

// Couleur d'accent STABLE dérivée du nom du projet (hash simple sur les
// charCodes → teinte HSL). Même nom ⇒ même couleur à chaque session.
function couleurProjet(nom) {
  let h = 0;
  for (let i = 0; i < nom.length; i++) {
    h = (h * 31 + nom.charCodeAt(i)) % 360;
  }
  return 'hsl(' + ((h + 360) % 360) + ', 60%, 34%)';
}

// Applique l'accent visuel du projet : bordure gauche du select et du bandeau,
// et libellé « Projet actif : … » en grand, tous de la même couleur.
function appliquerAccentProjet(nom) {
  const couleur = couleurProjet(nom);
  const select  = document.getElementById('projet');
  const bandeau = document.querySelector('.bandeau-projet');
  const label   = document.getElementById('projet-actif-label');
  if (select)  select.style.borderLeftColor  = couleur;
  if (bandeau) bandeau.style.borderLeftColor  = couleur;
  if (label) {
    label.textContent = 'Projet actif : ' + nom;
    label.style.color = couleur;
  }
}

function basculerOnglet(nom) {
  const noms = ['creation', 'resultats', 'journal', 'config', 'watchers'];
  document.querySelectorAll('.onglet').forEach((o, i) =>
    o.classList.toggle('actif', noms[i] === nom));
  noms.forEach(n =>
    document.getElementById('panneau-' + n).classList.toggle('actif', n === nom));
  if (nom === 'journal')  demarrerJournal();
  if (nom === 'resultats') chargerListeIssues();
  if (nom === 'watchers') {
    chargerWatchers();
    intervalWatchers = setInterval(chargerWatchers, 5000);
  } else {
    clearInterval(intervalWatchers);
  }
  if (nom === 'config') chargerConfig();
}

function onProjetChange() {
  const nom = document.getElementById('projet').value;
  // Mémorise le projet choisi pour le restaurer à la prochaine ouverture.
  try { localStorage.setItem('bridge_projet_actif', nom); } catch(e) {}
  appliquerAccentProjet(nom);
  verifierStatut();
  mettreAJourInfoProjet();
  // L'onglet Résultats est indépendant du sélecteur global (il agrège tous
  // les projets) : on ne le recharge donc PAS ici.
  // Si l'onglet Configuration est actif, recharger sa config pour le
  // nouveau projet (l'onglet lit désormais le sélecteur global #projet).
  if (document.getElementById('panneau-config').classList.contains('actif')) {
    chargerConfig();
  }
}

async function mettreAJourInfoProjet() {
  const nom = document.getElementById('projet').value;
  try {
    const rep = await fetch('/config/' + encodeURIComponent(nom));
    const cfg = await rep.json();
    const depEl = document.getElementById('info-depot');
    const repEl = document.getElementById('info-rep-travail');
    const perEl = document.getElementById('info-perimetre');
    depEl.textContent = '📦 ' + cfg.depot;
    repEl.textContent = ' · 📁 ' + cfg.rep_travail;
    if (cfg.perimetre) {
      perEl.textContent = ' · 🔒 ' + cfg.perimetre;
    } else {
      perEl.textContent = '';
    }
    // Le timeout par défaut suit la valeur TIMEOUT_CLAUDE du projet sélectionné.
    document.getElementById('timeout').value = cfg.timeout_claude || 300;
    // Le libellé du bouton d'envoi affiche le projet cible pour éviter les
    // envois sur le mauvais projet.
    document.getElementById('btn-envoyer').textContent = 'Envoyer sur ' + cfg.nom;
  } catch(e) {}
}

async function chargerConfig() {
  const nom = document.getElementById('projet').value;
  try {
    const rep = await fetch('/config/' + encodeURIComponent(nom));
    const cfg = await rep.json();

    document.getElementById('config-readonly').innerHTML =
      `NOM = ${cfg.nom}<br>DEPOT = ${cfg.depot}<br>` +
      `REP_TRAVAIL = ${cfg.rep_travail}<br>` +
      (cfg.perimetre  ? `PERIMETRE = ${cfg.perimetre}<br>` : '') +
      (cfg.cmd_backup ? `CMD_BACKUP = ${cfg.cmd_backup}` : '');

    document.getElementById('conf-TOPIC_NTFY').value        = cfg.topic_ntfy        || '';
    document.getElementById('conf-LABEL').value             = cfg.label             || 'for-linux';
    document.getElementById('conf-INTERVALLE').value        = cfg.intervalle        || 10;
    document.getElementById('conf-MAX_ESSAIS').value        = cfg.max_essais        || 3;
    document.getElementById('conf-TIMEOUT_CLAUDE').value    = cfg.timeout_claude    || 300;
    document.getElementById('conf-SCRIPT_BIP').value        = cfg.script_bip        || '';
    document.getElementById('conf-FICHIER_CONTEXTE').value  = cfg.fichier_contexte  || '';
    document.getElementById('conf-MODELE_CCL').value        = cfg.modele_ccl        || '';
    document.getElementById('conf-LOG_TAILLE_MAX_MO').value = cfg.log_taille_max_mo || 1;
    document.getElementById('conf-LOG_ARCHIVES').value      = cfg.log_archives      || 5;
    document.getElementById('msg-config').style.display = 'none';
  } catch(e) {
    const msg = document.getElementById('msg-config');
    msg.textContent = 'Erreur de chargement : ' + e.message;
    msg.className = 'message erreur'; msg.style.display = 'block';
  }
}

async function sauvegarderConfig(relancer) {
  const nom = document.getElementById('projet').value;
  const data = {
    TOPIC_NTFY:        document.getElementById('conf-TOPIC_NTFY').value,
    LABEL:             document.getElementById('conf-LABEL').value,
    INTERVALLE:        document.getElementById('conf-INTERVALLE').value,
    MAX_ESSAIS:        document.getElementById('conf-MAX_ESSAIS').value,
    TIMEOUT_CLAUDE:    document.getElementById('conf-TIMEOUT_CLAUDE').value,
    SCRIPT_BIP:        document.getElementById('conf-SCRIPT_BIP').value,
    FICHIER_CONTEXTE:  document.getElementById('conf-FICHIER_CONTEXTE').value,
    MODELE_CCL:        document.getElementById('conf-MODELE_CCL').value,
    LOG_TAILLE_MAX_MO: document.getElementById('conf-LOG_TAILLE_MAX_MO').value,
    LOG_ARCHIVES:      document.getElementById('conf-LOG_ARCHIVES').value,
  };
  const rep  = await fetch('/config/' + encodeURIComponent(nom), {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const json = await rep.json();
  const msg  = document.getElementById('msg-config');
  msg.textContent = json.message;
  msg.className   = 'message ' + (json.succes ? 'succes' : 'erreur');
  msg.style.display = 'block';
  if (json.succes && relancer) {
    await fetch('/lancer-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: nom, relancer: true})
    });
    msg.textContent += ' Watcher relancé.';
  }
}

function demarrerJournal() {
  if (sourceSSE) { sourceSSE.close(); sourceSSE = null; }
  const nom = document.getElementById('projet').value;
  document.getElementById('label-journal').textContent = 'logs/watcher-' + nom + '.log';
  document.getElementById('terminal').innerHTML = '';
  sourceSSE = new EventSource('/journal/' + encodeURIComponent(nom));
  sourceSSE.onmessage = function(e) {
    const term = document.getElementById('terminal');
    const div = document.createElement('div');
    const t = e.data;
    if (t.includes('[WARNING]') || t.includes('⚠'))  div.className = 'log-warn';
    else if (t.includes('[ERROR]'))                    div.className = 'log-err';
    else if (t.includes('✓') || t.includes('succès')) div.className = 'log-ok';
    else                                               div.className = 'log-info';
    div.textContent = t;
    // Les lignes les plus récentes s'affichent en haut
    term.insertBefore(div, term.firstChild);
    term.scrollTop = 0;
  };
  sourceSSE.onerror = function() {
    const term = document.getElementById('terminal');
    const div = document.createElement('div');
    div.className = 'log-warn';
    div.textContent = '— connexion perdue, tentative de reconnexion…';
    term.insertBefore(div, term.firstChild);
    term.scrollTop = 0;
  };
}

function viderTerminal() {
  document.getElementById('terminal').innerHTML = '';
}

// ─── Onglet Résultats : visualisation des issues ──────────────────────────

// Préfixe visuel d'une issue selon ses labels.
// needs-human prime sur tout ; sinon mode_write (✏️) puis done (✅) se cumulent ;
// à défaut, ○.
function prefixeIssue(labels) {
  const noms = (labels || []).map(l => ((l && l.name) || l || '').toLowerCase());
  if (noms.includes('needs-human')) return '⚠️';
  let p = '';
  if (noms.includes('mode_write')) p += '✏️';
  if (noms.includes('done'))       p += '✅';
  return p || '○';
}

// Badge coloré pour un label dans le panneau de détail.
function badgeLabel(nom) {
  const map = {
    'done':        {cls: 'succes',   txt: '✅ succès'},
    'needs-human': {cls: 'echec',    txt: '⚠️ échec'},
    'mode_write':  {cls: 'ecriture', txt: '✏️ écriture'},
    'bridge':      {cls: 'gris',     txt: 'bridge'},
    'for-linux':   {cls: 'gris',     txt: 'for-linux'},
  };
  const b = map[nom] || {cls: 'gris', txt: nom};
  return '<span class="badge-label ' + b.cls + '">' + escapeHtml(b.txt) + '</span>';
}

// ─── Onglet Résultats : vue consolidée multi-projets ──────────────────────
// L'onglet Résultats est INDÉPENDANT du sélecteur global : il agrège les
// issues de TOUS les projets, quel que soit le projet actif en haut.

// Couleur fixe par projet pour l'onglet Résultats (pastilles, badges, boutons
// de filtre). Valeurs stables imposées ; gris par défaut pour les autres.
function couleurProjetResultats(nom) {
  const map = {
    'bridge_agent': '#185FA5',  // bleu
    'alchess':      '#3B6D11',  // vert
    'ff_galerie':   '#BA7517',  // orange
  };
  return map[nom] || '#5F5E5A';  // gris
}

// Liste des noms de projets disponibles (lue depuis le sélecteur global, qui
// est peuplé côté serveur par lister_projets()).
function nomsProjetsDisponibles() {
  return [...document.getElementById('projet').options]
    .map(o => o.value).filter(Boolean);
}

// État de l'onglet Résultats : liste fusionnée des issues (chacune porte son
// projet source) + ensemble des projets actuellement affichés (filtre).
let listeIssuesResultats = [];
let projetsFiltresActifs = new Set();

// Clé localStorage du cache de la liste d'issues (issue #52). Affichage
// instantané depuis le cache, rafraîchi ensuite par un fetch d'arrière-plan.
const CLE_CACHE_ISSUES = 'bridge_cache_issues';

// Affiche/masque l'indicateur discret « Mise à jour… » sous la liste.
function majIndicateurListe(actif) {
  const el = document.getElementById('maj-indicateur');
  if (el) el.style.display = actif ? '' : 'none';
}

// Applique une liste d'issues à l'UI : filtres + boutons + rendu.
function appliquerListeIssues(liste, noms) {
  listeIssuesResultats = liste;
  projetsFiltresActifs = restaurerFiltresProjets(noms);
  construireBoutonsFiltre(noms);
  rendreListeIssues(true);
}

async function chargerListeIssues() {
  const zone = document.getElementById('liste-issues');
  const noms = nomsProjetsDisponibles();
  if (!noms.length) {
    zone.innerHTML = '<div class="issue-vide">Aucun projet</div>';
    return;
  }

  // 1) Affichage immédiat depuis le cache localStorage, s'il existe.
  let cache = null;
  try { cache = JSON.parse(localStorage.getItem(CLE_CACHE_ISSUES) || 'null'); } catch(e) {}
  const cacheAffiche = Array.isArray(cache) && cache.length > 0;
  if (cacheAffiche) {
    appliquerListeIssues(cache, noms);
  } else {
    zone.innerHTML = '<div class="issue-vide">Chargement…</div>';
  }

  // 2) Fetch d'arrière-plan des 5 dernières issues de chaque projet.
  majIndicateurListe(true);
  try {
    const listes = await Promise.all(noms.map(async nom => {
      try {
        const rep = await fetch('/issues-liste/' + encodeURIComponent(nom));
        const liste = await rep.json();
        if (!Array.isArray(liste)) return [];
        // Les 5 plus récentes (date de création décroissante) de ce projet.
        return liste
          .slice()
          .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
          .slice(0, 5)
          .map(it => Object.assign({}, it, {projet: nom}));
      } catch(e) {
        return [];
      }
    }));
    // Fusion + tri global par date de création décroissante (plus récentes en premier).
    const nouvelle = listes.flat().sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));

    // Ne re-render que si la liste a réellement changé : évite de perdre la
    // sélection courante quand le cache était déjà à jour.
    const inchangee = cacheAffiche && JSON.stringify(nouvelle) === JSON.stringify(cache);
    if (!inchangee) {
      appliquerListeIssues(nouvelle, noms);
    } else {
      listeIssuesResultats = nouvelle;
    }
    try { localStorage.setItem(CLE_CACHE_ISSUES, JSON.stringify(nouvelle)); } catch(e) {}
  } catch(e) {
    if (!cacheAffiche) zone.innerHTML = '<div class="issue-vide">Erreur de chargement</div>';
  } finally {
    majIndicateurListe(false);
  }
}

// Clé localStorage mémorisant l'état des boutons de filtre projet.
const CLE_FILTRES_RESULTATS = 'bridge_filtres_resultats';

// Lit l'état des filtres depuis localStorage → Set des projets actifs.
// Clé absente/illisible → tous actifs (comportement par défaut). Un projet
// n'est inactif que s'il est explicitement marqué false ; un projet apparu
// depuis la dernière sauvegarde (absent de l'objet) est donc actif.
function restaurerFiltresProjets(noms) {
  let brut = null;
  try { brut = localStorage.getItem(CLE_FILTRES_RESULTATS); } catch(e) {}
  if (!brut) return new Set(noms);
  let etat;
  try { etat = JSON.parse(brut); } catch(e) { return new Set(noms); }
  if (!etat || typeof etat !== 'object') return new Set(noms);
  return new Set(noms.filter(nom => etat[nom] !== false));
}

// Écrit l'état courant des filtres dans localStorage.
function sauvegarderFiltresProjets(noms) {
  const etat = {};
  for (const nom of noms) etat[nom] = projetsFiltresActifs.has(nom);
  try {
    localStorage.setItem(CLE_FILTRES_RESULTATS, JSON.stringify(etat));
  } catch(e) {}
}

// (Re)construit la ligne de boutons toggle — un par projet + « Tous ».
function construireBoutonsFiltre(noms) {
  const zone = document.getElementById('filtres-projets');
  zone.innerHTML = '';
  for (const nom of noms) {
    const btn = document.createElement('span');
    btn.className = 'filtre-projet';
    btn.dataset.projet = nom;
    // La couleur du projet est stockée en attribut data ; appliqueCouleurBouton
    // la reporte en texte + bordure quand le bouton est actif (indicateur
    // visible de projet, cohérent avec la pastille et le badge de détail).
    btn.dataset.couleur = couleurProjetResultats(nom);
    btn.onclick = () => basculerFiltreProjet(nom);
    btn.innerHTML = '<span class="pastille" style="background:'
      + couleurProjetResultats(nom) + '"></span>' + escapeHtml(nom);
    zone.appendChild(btn);
  }
  majClassesBoutonsFiltre();
  const tous = document.createElement('span');
  tous.className = 'filtre-projet tous';
  tous.textContent = 'Tous';
  tous.onclick = reactiverTousLesFiltres;
  zone.appendChild(tous);
  // Bouton rafraîchir déplacé ici, juste après « Tous » (issue #57). Recréé à
  // chaque reconstruction de la ligne car zone.innerHTML est vidé au début.
  const rafr = document.createElement('button');
  rafr.id = 'btn-rafraichir';
  rafr.className = 'btn-rafraichir';
  rafr.title = 'Rafraîchir depuis GitHub';
  rafr.textContent = '↻';
  rafr.onclick = rafraichirResultats;
  zone.appendChild(rafr);
}

// Active/désactive un projet dans le filtre puis masque/affiche les lignes
// correspondantes (display:none). Si la ligne sélectionnée devient masquée, on
// bascule sur la première ligne encore visible.
function basculerFiltreProjet(nom) {
  if (projetsFiltresActifs.has(nom)) projetsFiltresActifs.delete(nom);
  else projetsFiltresActifs.add(nom);
  sauvegarderFiltresProjets(nomsProjetsDisponibles());
  majClassesBoutonsFiltre();
  appliquerFiltresListe();
  const sel = document.querySelector('#liste-issues .ligne-issue.selectionnee');
  if (!sel || sel.style.display === 'none') selectionnerPremiereVisible();
}

// Remet tous les projets à l'état actif ET efface la mémoire localStorage
// (retour au comportement par défaut : tous actifs au prochain chargement).
function reactiverTousLesFiltres() {
  projetsFiltresActifs = new Set(nomsProjetsDisponibles());
  try { localStorage.removeItem(CLE_FILTRES_RESULTATS); } catch(e) {}
  majClassesBoutonsFiltre();
  appliquerFiltresListe();
  const sel = document.querySelector('#liste-issues .ligne-issue.selectionnee');
  if (!sel || sel.style.display === 'none') selectionnerPremiereVisible();
}

function majClassesBoutonsFiltre() {
  document.querySelectorAll('#filtres-projets .filtre-projet[data-projet]')
    .forEach(btn => {
      const actif = projetsFiltresActifs.has(btn.dataset.projet);
      btn.classList.toggle('inactif', !actif);
      // Actif : texte + bordure à la couleur du projet (bien visible).
      // Inactif : on efface le style inline pour laisser la classe .inactif
      // (grisé) reprendre la main.
      btn.style.color       = actif ? btn.dataset.couleur : '';
      btn.style.borderColor = actif ? btn.dataset.couleur : '';
    });
}

// Convertit une couleur hexadécimale #RRGGBB en rgba() avec l'alpha demandé.
// Sert aux fonds translucides (survol/sélection) propres à chaque projet.
function avecOpacite(hex, alpha) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  if (!m) return hex;
  const n = parseInt(m[1], 16);
  return 'rgba(' + ((n >> 16) & 255) + ',' + ((n >> 8) & 255) + ','
       + (n & 255) + ',' + alpha + ')';
}

// (Re)construit la liste HTML cliquable à partir de listeIssuesResultats. TOUTES
// les issues sont rendues comme lignes ; le filtre projet ne fait que masquer
// (display:none) les lignes des projets inactifs. Chaque ligne est coloriée à la
// couleur de son projet et déclenche afficherIssue() au clic. Si reset=true, on
// sélectionne et affiche la première issue visible.
function rendreListeIssues(reset) {
  const zone = document.getElementById('liste-issues');
  zone.innerHTML = '';
  if (!listeIssuesResultats.length) {
    zone.innerHTML = '<div class="issue-vide">Aucune issue à afficher</div>';
    document.getElementById('zone-issue').innerHTML =
      '<div class="issue-vide">Aucune issue à afficher</div>';
    return;
  }
  for (const it of listeIssuesResultats) {
    const etat = (it.state || '').toUpperCase() === 'CLOSED' ? 'fermé' : 'ouvert';
    const couleur = couleurProjetResultats(it.projet);
    const numero = String(it.number);
    // Date de création formatée en heure locale du navigateur (issue #58) :
    // "DD/MM/YYYY HH:MM:SS" jusqu'à la seconde via toLocaleString('fr-FR').
    const dateCreation = it.createdAt
      ? new Date(it.createdAt).toLocaleString('fr-FR', {
          day: '2-digit', month: '2-digit', year: 'numeric',
          hour: '2-digit', minute: '2-digit', second: '2-digit'
        })
      : '';
    const ligne = document.createElement('div');
    ligne.className = 'ligne-issue';
    ligne.dataset.projet = it.projet;
    ligne.dataset.numero = numero;
    // Couleur du texte = couleur du projet ; fonds translucides propres au projet
    // portés par des variables CSS, exploitées par .ligne-issue:hover/.selectionnee.
    ligne.style.color = couleur;
    ligne.style.setProperty('--bg-hover', avecOpacite(couleur, 0.10));
    ligne.style.setProperty('--bg-sel',   avecOpacite(couleur, 0.20));
    // Clic simple : sélectionne et affiche l'issue. Ctrl+clic : idem, puis
    // défile automatiquement jusqu'au bloc résultat CCL (dans cette UI, le
    // résultat est rendu EN PREMIER via .commentaire.resultat ; on le vise
    // donc explicitement, avec repli sur .commentaire:last-child).
    ligne.onclick = async (event) => {
      event.preventDefault();
      await afficherIssue(it.projet, numero);
      if (event.ctrlKey) {
        setTimeout(() => {
          const cible = document.querySelector('#zone-issue .commentaire.resultat')
                     || document.querySelector('#zone-issue .commentaire:last-child');
          if (cible) cible.scrollIntoView({behavior: 'smooth', block: 'start'});
        }, 100);
      }
    };
    // Gauche : badges emoji (✅ ✏️ ⚠️ ○) + pastille ● colorée du projet.
    // Centre : #N — titre [état].
    // Le badge ✅ des issues FERMÉES portant le label « done » (les seules qui
    // ont une réponse CCL) devient cliquable : un clic copie directement la
    // réponse CCL sans ouvrir le détail (issue #62).
    let badgesHtml = prefixeIssue(it.labels);
    const nomsLabelsLigne = (it.labels || [])
      .map(l => ((l && l.name) || l || '').toLowerCase());
    if (etat === 'fermé' && nomsLabelsLigne.includes('done')
        && badgesHtml.includes('✅')) {
      badgesHtml = badgesHtml.replace('✅',
        '<span class="badge-copie-ccl" title="Copier la réponse CCL"'
        + ' onclick="copierReponseDepuisBadge(event, \''
        + escapeHtml(it.projet) + '\', ' + Number(numero) + ')">✅</span>');
    }
    ligne.innerHTML =
      '<span class="ligne-date" style="font-size:11px;color:#999;'
      + 'min-width:140px;font-family:monospace">' + escapeHtml(dateCreation) + '</span>'
      + '<span class="ligne-gauche">'
      + '<span class="ligne-badges">' + badgesHtml + '</span>'
      + '<span class="pastille-ligne" style="background:' + couleur + '"></span>'
      + '</span>'
      + '<span class="ligne-texte">#' + escapeHtml(numero) + ' — '
      + escapeHtml(it.title) + ' [' + etat + ']</span>';
    zone.appendChild(ligne);
  }
  appliquerFiltresListe();
  if (reset) selectionnerPremiereVisible();
}

// Masque/affiche les lignes selon les projets actifs (filtre = display:none).
function appliquerFiltresListe() {
  document.querySelectorAll('#liste-issues .ligne-issue').forEach(ligne => {
    ligne.style.display = projetsFiltresActifs.has(ligne.dataset.projet) ? '' : 'none';
  });
}

// Sélectionne et affiche la première ligne encore visible (ou vide le détail).
function selectionnerPremiereVisible() {
  const premiere = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(ligne => ligne.style.display !== 'none');
  if (premiere) {
    afficherIssue(premiere.dataset.projet, premiere.dataset.numero);
  } else {
    document.getElementById('zone-issue').innerHTML =
      '<div class="issue-vide">Aucune issue à afficher</div>';
  }
}

function escapeHtml(t) {
  const d = document.createElement('div');
  d.textContent = t == null ? '' : t;
  return d.innerHTML;
}

// Rendu HTML restreint pour la réponse CCL (issue #61). On échappe TOUT le
// corps (aucune balise brute ne survit), puis on ré-autorise uniquement une
// liste blanche de balises sûres SANS attribut. Toute autre balise — ou une
// balise autorisée mais porteuse d'attributs, ex. <details open> ou
// <a href> — ne matche pas et reste échappée : elle s'affiche telle quelle
// plutôt que d'être interprétée. Pas d'injection possible via attributs.
function rendreHtmlRestreint(t) {
  // Échappement déterministe (& d'abord) — ne dépend pas de la sérialisation
  // du navigateur, contrairement à escapeHtml().
  let s = (t == null ? '' : String(t))
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const balises = ['details','summary','p','br','strong','em','code','pre',
                   'ul','ol','li','h1','h2','h3','h4','h5','h6'];
  balises.forEach(function(b) {
    s = s.split('&lt;' + b + '&gt;').join('<' + b + '>');   // ouvrante <tag>
    s = s.split('&lt;/' + b + '&gt;').join('</' + b + '>'); // fermante </tag>
  });
  // <br> auto-fermant toléré sous ses deux formes courantes.
  s = s.split('&lt;br/&gt;').join('<br/>').split('&lt;br /&gt;').join('<br/>');
  return s;
}

// Cache localStorage du détail d'une issue (issue #52). Clé par projet+numéro,
// avec un TTL court : le détail (commentaires, état) évolue vite, on n'affiche
// donc le cache que s'il a moins de TTL_DETAIL_MS.
const CLE_CACHE_DETAIL = 'bridge_cache_detail_';

// Issue actuellement affichée dans #zone-issue (null si aucune). Permet au
// bouton rafraîchir (issue #56) de la recharger depuis GitHub.
let projetCourant = null;
let numeroCourant = null;
const TTL_DETAIL_MS = 60000;
// Jeton anti-course : chaque appel à afficherIssue l'incrémente ; un fetch qui
// revient alors qu'une autre issue a été demandée entre-temps est ignoré.
let afficherIssueSeq = 0;

// Construit le HTML de détail d'une issue à partir de sa donnée brute (`it`).
// Fonction pure : même sortie depuis le cache et depuis le fetch frais.
function construireHtmlIssue(it, nom) {
  const ferme = (it.state || '').toUpperCase() === 'CLOSED';
  let html = '';
  html += '<div class="issue-titre">#' + escapeHtml(it.number) + ' — ' + escapeHtml(it.title) + '</div>';

  // Badge coloré du projet source (couleur cohérente avec les filtres).
  html += '<div><span class="badge-projet" style="background:'
        + couleurProjetResultats(nom) + '">'
        + '<span class="pastille"></span>' + escapeHtml(nom) + '</span></div>';

  html += '<div class="issue-badges">';
  html += '<span class="badge-etat ' + (ferme ? 'ferme' : 'ouvert') + '">'
        + (ferme ? 'fermé' : 'ouvert') + '</span>';
  for (const lab of (it.labels || [])) {
    html += badgeLabel(lab.name || lab);
  }
  html += '</div>';

  // Bouton « Annuler cette issue » : uniquement si l'issue est ouverte, porte
  // le label for-linux (donc destinée au watcher), n'est pas déjà en échec
  // (needs-human) et n'a encore aucun commentaire. Un commentaire signifie que
  // le watcher a capté l'issue et posté son ACK : CCL tourne déjà, l'annulation
  // serait sans effet — on masque le bouton pour ne pas induire en erreur.
  const nomsLabels = (it.labels || []).map(l => ((l.name || l) || '').toLowerCase());
  const comments = it.comments || [];
  const annulable = !ferme
    && nomsLabels.includes('for-linux')
    && !nomsLabels.includes('needs-human')
    && comments.length === 0;
  if (annulable) {
    html += '<div class="bloc-annuler">'
          + '<button class="danger" onclick="annulerIssue(\'' + nom + '\', '
          + Number(it.number) + ')">'
          + 'Annuler cette issue</button></div>';
  } else if (!ferme
    && nomsLabels.includes('for-linux')
    && !nomsLabels.includes('needs-human')
    && comments.length > 0) {
    html += '<div class="bloc-annuler">'
          + '<span class="traitement-encours">'
          + '⏳ En cours de traitement — annulation impossible</span></div>';
  }

  // Issue en échec définitif (label needs-human) et toujours ouverte :
  // l'intervention humaine ayant été effectuée, on propose de la clore
  // directement, sans passer par GitHub (issue #80). Bouton rouge plein à côté
  // du rappel « intervention humaine requise ».
  if (!ferme && nomsLabels.includes('needs-human')) {
    html += '<div class="bloc-annuler">'
          + '<span class="traitement-encours">'
          + '⚠️ Échec — intervention humaine requise</span> '
          + '<button class="danger-plein" onclick="fermerIssue(\'' + nom + '\', '
          + Number(it.number) + ')">'
          + 'Fermer définitivement</button></div>';
  }

  html += '<div class="issue-body">' + escapeHtml(it.body || '(pas de description)') + '</div>';

  const comms = it.comments || [];
  html += '<div class="issue-sep">Commentaires (' + comms.length + ')</div>';
  if (!comms.length) {
    html += '<div class="issue-vide">Aucun commentaire</div>';
  } else {
    // La réponse de CCL (dernier commentaire) est affichée en premier ;
    // les autres commentaires suivent dans l'ordre chronologique.
    const dernier = comms.length - 1;
    const ordre = [dernier, ...comms.map((_, i) => i).filter(i => i !== dernier)];
    ordre.forEach(i => {
      const c = comms[i];
      const auteur = (c.author && c.author.login) ? c.author.login : (c.author || 'inconnu');
      if (i === dernier) {
        // Réponse de CCL : on sépare le résumé court (texte AVANT <details>)
        // du bloc détails verbeux. Le bouton « Copier » est ancré au bloc
        // résumé et ne copie que ce résumé — pas les détails (issue #59).
        const corpsBrut = c.body || '';
        const idxDetails = corpsBrut.indexOf('<details>');
        const resume = (idxDetails >= 0 ? corpsBrut.slice(0, idxDetails) : corpsBrut)
                       .replace(/\s+$/, '');
        const details = idxDetails >= 0 ? corpsBrut.slice(idxDetails) : '';
        html += '<div class="commentaire resultat">'
              + '<div class="commentaire-auteur">' + escapeHtml(auteur) + ' — résultat CCL</div>'
              + '<div class="commentaire-resume">'
              // « Copier résumé » : le texte avant <details> uniquement (issue #59).
              // « Copier tout » : résumé + détails en markdown brut (issue #77).
              + '<button class="btn-copier" onclick="copierReponse(this)">Copier résumé</button>'
              + '<button class="btn-copier" onclick="copierTout(this)">Copier tout</button>'
              // Le bloc <details> brut (markdown non rendu) est conservé caché ici
              // pour que « Copier tout » puisse reconstruire le texte exact à coller
              // dans Claude Chat, indépendamment du rendu HTML de l'accordéon.
              + (details
                  ? '<div class="commentaire-details-brut" style="display:none">'
                    + escapeHtml(details) + '</div>'
                  : '')
              + '<div class="commentaire-corps">' + escapeHtml(resume) + '</div>'
              + '</div>';
        if (details) {
          // Le corps contient un bloc <details> : on le rend en HTML restreint
          // (liste blanche de balises sûres) pour un accordéon dépliable et
          // interactif au lieu de markdown brut échappé (issue #61).
          html += '<div class="commentaire-details commentaire-html">'
                + rendreHtmlRestreint(details) + '</div>';
        }
        html += '</div>';
      } else {
        // Autres commentaires (ACK, etc.) : rendu texte échappé (sécurité) +
        // bouton « Copier » discret en haut à droite, ancré au bloc (issue #61).
        html += '<div class="commentaire commentaire-copiable">'
              + '<button class="btn-copier" onclick="copierReponse(this)">Copier</button>'
              + '<div class="commentaire-auteur">' + escapeHtml(auteur) + '</div>'
              + '<div class="commentaire-corps">' + escapeHtml(c.body || '') + '</div>'
              + '</div>';
      }
    });
  }
  return html;
}

async function afficherIssue(nom, numero) {
  numero = numero == null ? '' : String(numero);
  const seq = ++afficherIssueSeq;
  // Met en évidence la ligne sélectionnée (fond coloré persistant) et retire la
  // sélection des autres lignes.
  document.querySelectorAll('#liste-issues .ligne-issue.selectionnee')
    .forEach(ligne => ligne.classList.remove('selectionnee'));
  const ligneSel = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(ligne => ligne.dataset.projet === nom && ligne.dataset.numero === numero);
  if (ligneSel) ligneSel.classList.add('selectionnee');
  const zone = document.getElementById('zone-issue');
  if (!numero || !nom) {
    projetCourant = null;
    numeroCourant = null;
    zone.innerHTML = '<div class="issue-vide">Aucune issue à afficher</div>';
    return;
  }
  // Mémorise l'issue affichée pour le bouton rafraîchir (issue #56).
  projetCourant = nom;
  numeroCourant = numero;

  // 1) Cache frais (< TTL) : affichage immédiat. Passé le TTL, on force le fetch
  //    pour ne montrer que du frais (état/commentaires évoluent vite).
  const cleCache = CLE_CACHE_DETAIL + nom + '_' + numero;
  let htmlAffiche = null;
  try {
    const obj = JSON.parse(localStorage.getItem(cleCache) || 'null');
    if (obj && obj.it && (Date.now() - obj.ts) < TTL_DETAIL_MS) {
      htmlAffiche = construireHtmlIssue(obj.it, nom);
      zone.innerHTML = htmlAffiche;
    }
  } catch(e) {}
  if (htmlAffiche === null) {
    zone.innerHTML = '<div class="issue-vide">Chargement de l\'issue #' + escapeHtml(numero) + '…</div>';
  }

  // 2) Fetch d'arrière-plan ; met à jour l'affichage et le cache si différent.
  try {
    const rep = await fetch('/issue/' + encodeURIComponent(nom) + '/' + encodeURIComponent(numero));
    const it = await rep.json();
    // Une autre issue a été demandée entre-temps : on n'écrase pas son affichage.
    if (seq !== afficherIssueSeq) return;
    if (it.erreur) {
      if (htmlAffiche === null) {
        zone.innerHTML = '<div class="issue-vide">Erreur : ' + escapeHtml(it.erreur) + '</div>';
      }
      return;
    }
    try { localStorage.setItem(cleCache, JSON.stringify({ts: Date.now(), it: it})); } catch(e) {}
    const htmlFrais = construireHtmlIssue(it, nom);
    if (htmlFrais !== htmlAffiche) {
      zone.innerHTML = htmlFrais;
    }
  } catch(e) {
    if (seq === afficherIssueSeq && htmlAffiche === null) {
      zone.innerHTML = '<div class="issue-vide">Erreur réseau : ' + escapeHtml(e.message) + '</div>';
    }
  }
}

// Bouton rafraîchir (issue #56) : vide le cache localStorage (liste + tous les
// détails) puis recharge tout depuis GitHub. Contourne le TTL du cache détail,
// qui peut montrer une issue « ouverte » alors que le watcher l'a fermée.
async function rafraichirResultats() {
  // Mémorise l'issue affichée AVANT le rechargement : chargerListeIssues()
  // réécrit projetCourant/numeroCourant en auto-sélectionnant la première ligne.
  const projet = projetCourant;
  const numero = numeroCourant;
  // 1) Cache de la liste.
  try { localStorage.removeItem(CLE_CACHE_ISSUES); } catch(e) {}
  // 2) Toutes les clés de cache détail « bridge_cache_detail_* ».
  try {
    const aSupprimer = [];
    for (let i = 0; i < localStorage.length; i++) {
      const cle = localStorage.key(i);
      if (cle && cle.indexOf(CLE_CACHE_DETAIL) === 0) aSupprimer.push(cle);
    }
    aSupprimer.forEach(cle => localStorage.removeItem(cle));
  } catch(e) {}
  // 3) Recharge la liste depuis GitHub.
  await chargerListeIssues();
  // 4) Recharge l'issue qui était affichée, si elle l'était.
  if (projet && numero) {
    await afficherIssue(projet, numero);
  }
}

// Copie le texte de la réponse CCL (dernier commentaire) dans le presse-papier.
// Feedback visuel « ✓ Copié ! » pendant 2 s. Fallback silencieux (sélection du
// texte + warning console) si navigator.clipboard est indisponible (non-HTTPS).
async function copierReponse(btn) {
  // Le bouton vit dans le bloc résumé : on copie le texte de CE bloc
  // uniquement (résumé court), jamais le bloc détails verbeux (issue #59).
  const bloc = btn.closest('.commentaire-resume') || btn.closest('.commentaire');
  const corps = bloc ? bloc.querySelector('.commentaire-corps') : null;
  if (!corps) return;
  // Libellé d'origine : « Copier résumé » (CCL, issue #77) ou « Copier » (autres
  // commentaires, issue #61) — on le restaure après le retour visuel.
  const libelle = btn.textContent;
  const texte = corps.textContent || '';
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
      btn.disabled = true;
      btn.textContent = '✓ Copié !';
      setTimeout(function() {
        btn.textContent = libelle;
        btn.disabled = false;
      }, 2000);
      return;
    } catch(e) {
      console.warn('copierReponse : échec navigator.clipboard, fallback sélection.', e);
    }
  } else {
    console.warn('copierReponse : navigator.clipboard indisponible (contexte non-HTTPS), fallback sélection.');
  }
  // Fallback : on sélectionne le texte du bloc pour permettre un Ctrl+C manuel.
  const sel = window.getSelection();
  if (sel) {
    const range = document.createRange();
    range.selectNodeContents(corps);
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

// Reconstruit la réponse CCL COMPLÈTE en markdown brut (issue #77) : le résumé,
// une ligne vide, puis le contenu du bloc <details> débarrassé de ses seules
// balises structurantes (<details>, <summary>, </summary>, </details>). Le texte
// interne (dont le libellé du <summary>) est conservé tel quel — résultat lisible
// et collable directement dans Claude Chat. Si les détails sont vides, on ne
// renvoie que le résumé (pas de ligne vide superflue).
function texteReponseComplete(resume, detailsBrut) {
  const contenu = (detailsBrut || '')
    .split('<details>').join('')
    .split('</details>').join('')
    .split('<summary>').join('')
    .split('</summary>').join('')
    .replace(/^\s+|\s+$/g, '');
  const r = (resume || '').replace(/\s+$/, '');
  return contenu ? (r + '\n\n' + contenu) : r;
}

// « Copier tout » (issue #77) : copie la réponse CCL complète (résumé + détails)
// en markdown brut, via texteReponseComplete(). Même feedback visuel que
// « Copier résumé » — « ✓ Copié ! » pendant 1,5 s puis retour au libellé. Le
// résumé est lu dans .commentaire-corps, les détails bruts dans le bloc caché
// .commentaire-details-brut. Fallback silencieux (sélection du résumé) si
// navigator.clipboard est indisponible (contexte non-HTTPS).
async function copierTout(btn) {
  const bloc = btn.closest('.commentaire-resume') || btn.closest('.commentaire');
  if (!bloc) return;
  const corps  = bloc.querySelector('.commentaire-corps');
  const brutEl = bloc.querySelector('.commentaire-details-brut');
  const resume = corps  ? (corps.textContent  || '') : '';
  const details = brutEl ? (brutEl.textContent || '') : '';
  const texte  = texteReponseComplete(resume, details);
  const libelle = btn.textContent;
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
      btn.disabled = true;
      btn.textContent = '✓ Copié !';
      setTimeout(function() {
        btn.textContent = libelle;
        btn.disabled = false;
      }, 1500);
      return;
    } catch(e) {
      console.warn('copierTout : échec navigator.clipboard, fallback sélection.', e);
    }
  } else {
    console.warn('copierTout : navigator.clipboard indisponible (contexte non-HTTPS), fallback sélection.');
  }
  // Fallback : à défaut de presse-papier, on sélectionne au moins le résumé
  // affiché (le texte complet reconstruit ne peut pas être injecté dans le DOM).
  const sel = window.getSelection();
  if (sel && corps) {
    const range = document.createRange();
    range.selectNodeContents(corps);
    sel.removeAllRanges();
    sel.addRange(range);
  }
}

// Extrait le RÉSUMÉ de la réponse CCL (dernier commentaire) d'une donnée issue
// brute : texte AVANT le bloc <details>, whitespace de fin retiré. Cohérent
// avec ce que copie le bouton « Copier la réponse » du détail (issue #59).
function resumeReponseCcl(it) {
  const comms = (it && it.comments) || [];
  if (!comms.length) return '';
  const corpsBrut = comms[comms.length - 1].body || '';
  const idxDetails = corpsBrut.indexOf('<details>');
  return (idxDetails >= 0 ? corpsBrut.slice(0, idxDetails) : corpsBrut)
         .replace(/\s+$/, '');
}

// Clic sur le badge ✅ d'une issue fermée+done (issue #62) : copie la réponse
// CCL directement depuis la liste, sans ouvrir le détail. Utilise le cache
// bridge_cache_detail_<projet>_<numero> s'il est frais (< TTL), sinon fetch le
// détail (et met le cache à jour). Feedback visuel bref sur le badge lui-même,
// sans modifier la ligne. stopPropagation() empêche la sélection de la ligne.
async function copierReponseDepuisBadge(event, nom, numero) {
  event.stopPropagation();
  const badge = event.currentTarget;   // capturé avant tout await (nullé ensuite)
  numero = String(numero);
  const cleCache = CLE_CACHE_DETAIL + nom + '_' + numero;
  let texte = null;

  // 1) Cache frais (< TTL) : on évite le fetch.
  try {
    const obj = JSON.parse(localStorage.getItem(cleCache) || 'null');
    if (obj && obj.it && (Date.now() - obj.ts) < TTL_DETAIL_MS) {
      texte = resumeReponseCcl(obj.it);
    }
  } catch(e) {}

  // 2) Pas de cache exploitable : fetch le détail et rafraîchit le cache.
  if (texte === null) {
    try {
      const rep = await fetch('/issue/' + encodeURIComponent(nom)
                              + '/' + encodeURIComponent(numero));
      const it = await rep.json();
      if (!it.erreur) {
        try { localStorage.setItem(cleCache, JSON.stringify({ts: Date.now(), it: it})); } catch(e) {}
        texte = resumeReponseCcl(it);
      }
    } catch(e) {
      console.warn('copierReponseDepuisBadge : échec fetch du détail.', e);
    }
  }
  if (texte === null) texte = '';

  // Copie dans le presse-papier (fallback silencieux si indisponible / non-HTTPS).
  if (navigator.clipboard && navigator.clipboard.writeText) {
    try {
      await navigator.clipboard.writeText(texte);
    } catch(e) {
      console.warn('copierReponseDepuisBadge : échec navigator.clipboard.', e);
    }
  } else {
    console.warn('copierReponseDepuisBadge : navigator.clipboard indisponible (non-HTTPS).');
  }

  // Feedback visuel : ✅ → ✓ pendant 1,5 s, puis retour à ✅ (ligne inchangée).
  if (badge) {
    badge.textContent = '✓';
    setTimeout(function() { badge.textContent = '✅'; }, 1500);
  }
}

// Ferme une issue en attente sur GitHub (pas encore traitée par le watcher),
// puis rafraîchit l'affichage et la combobox.
async function annulerIssue(nom, numero) {
  if (!confirm("Annuler (fermer) l'issue #" + numero + " sur GitHub ?")) return;
  try {
    const rep = await fetch('/annuler-issue/' + encodeURIComponent(nom)
                            + '/' + encodeURIComponent(numero), {method: 'POST'});
    const json = await rep.json();
    if (!json.succes) {
      alert('Erreur : ' + (json.message || 'échec de l\'annulation.'));
      return;
    }
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
    return;
  }
  // Recharge la liste (l'issue devient fermée) puis réaffiche la même issue si
  // sa ligne existe encore et reste visible (projet non filtré).
  const numStr = String(numero);
  await chargerListeIssues();
  const ligne = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(l => l.dataset.projet === nom && l.dataset.numero === numStr);
  if (ligne && ligne.style.display !== 'none') {
    await afficherIssue(nom, numStr);
  }
}

// Ferme définitivement une issue en échec (label needs-human) après
// intervention humaine, puis rafraîchit l'affichage et la combobox (issue #80).
// L'action est irréversible → double confirmation via confirm().
async function fermerIssue(nom, numero) {
  if (!confirm("Fermer définitivement l'issue #" + numero
               + " ? Cette action est irréversible.")) return;
  try {
    const rep = await fetch('/fermer-issue/' + encodeURIComponent(nom)
                            + '/' + encodeURIComponent(numero), {method: 'POST'});
    const json = await rep.json();
    if (!json.succes) {
      alert('Erreur : ' + (json.message || 'échec de la fermeture.'));
      return;
    }
  } catch(e) {
    alert('Erreur réseau : ' + e.message);
    return;
  }
  // Recharge la liste (l'issue devient fermée) puis réaffiche la même issue si
  // sa ligne existe encore et reste visible (projet non filtré).
  const numStr = String(numero);
  await chargerListeIssues();
  const ligne = [...document.querySelectorAll('#liste-issues .ligne-issue')]
    .find(l => l.dataset.projet === nom && l.dataset.numero === numStr);
  if (ligne && ligne.style.display !== 'none') {
    await afficherIssue(nom, numStr);
  }
}

function collecterFormulaire() {
  const notifs = [...document.querySelectorAll('input[name=notifs]:checked')].map(c => c.value);
  return {
    projet:          document.getElementById('projet').value,
    titre:           document.getElementById('titre').value.trim(),
    priorite:        document.getElementById('priorite').value,
    timeout:         document.getElementById('timeout').value,
    mode:            document.querySelector('input[name=mode]:checked').value,
    notifs:          notifs,
    corps:           document.getElementById('corps').value.trim(),
    modele_ponctuel: document.getElementById('modele-ponctuel').value,
  };
}

function afficherMessage(texte, type) {
  const el = document.getElementById('message');
  el.textContent = texte;
  el.className = 'message ' + type;
  el.style.display = 'block';
}

function cacherRetours() {
  document.getElementById('message').style.display = 'none';
  document.getElementById('zone-apercu').style.display = 'none';
}

async function afficherApercu() {
  cacherRetours();
  const data = collecterFormulaire();
  if (!data.titre) { afficherMessage('Le titre est obligatoire.', 'erreur'); return; }
  const rep = await fetch('/apercu', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data)
  });
  const json = await rep.json();
  const zone = document.getElementById('zone-apercu');
  zone.textContent = json.commande;
  zone.style.display = 'block';
}

// Affiche le modal de confirmation et résout true (envoyer) / false (annuler).
function afficherModalConfirmation(issues) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    document.getElementById('modal-titre').textContent =
      '⚠️ ' + issues.length + ' issue(s) en attente sur ce projet :';
    document.getElementById('modal-liste').innerHTML = issues.map(it =>
      '#' + escapeHtml(String(it.number)) + ' — ' + escapeHtml(it.title || '(sans titre)')
    ).join('<br>');
    const btnOui = document.getElementById('modal-oui');
    const btnNon = document.getElementById('modal-non');
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

// Modal de confirmation générique (titre + libellés de boutons personnalisés,
// sans liste). Réutilise le même overlay ; restaure les libellés d'origine à la
// fermeture. Résout true (bouton de gauche/oui) ou false (annuler).
function afficherModalGenerique(titre, texteOui, texteNon) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    const liste   = document.getElementById('modal-liste');
    const btnOui  = document.getElementById('modal-oui');
    const btnNon  = document.getElementById('modal-non');
    const ouiAvant = btnOui.textContent;
    const nonAvant = btnNon.textContent;
    document.getElementById('modal-titre').textContent = titre;
    liste.style.display = 'none';
    btnOui.textContent  = texteOui;
    btnNon.textContent  = texteNon;
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      btnOui.textContent = ouiAvant;
      btnNon.textContent = nonAvant;
      liste.style.display = '';
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

// Détecte une incohérence entre le projet sélectionné et le champ PROJET de
// l'en-tête bridge. Fiable : on ne fait plus d'analyse textuelle (source de
// faux positifs) — on lit le champ « | PROJET | … | » que new_issue.py insère
// dans l'en-tête, et que Claude Chat reproduit dans le corps qu'il fournit.
// Retourne {projetIssue, projetSelectionne} si les deux diffèrent, sinon null
// (champ absent → pas de vérification ; identique → pas de modale).
function detecterIncoherenceProjet(data) {
  const corps = data.corps || '';
  // Ligne du tableau markdown : « | PROJET | valeur | ». La valeur est la
  // 3e cellule, capturée entre le 2e et le 3e séparateur « | ».
  const m = corps.match(/^\s*\|\s*PROJET\s*\|([^|]*)\|/im);
  if (!m) return null;                                  // champ absent : pas de vérif
  const projetIssue = m[1].trim();
  if (!projetIssue) return null;                        // valeur vide : pas de vérif
  const projetSelectionne = (data.projet || '').trim();
  if (projetIssue.toLowerCase() === projetSelectionne.toLowerCase()) {
    return null;                                        // identique : pas de modale
  }
  return {projetIssue, projetSelectionne};
}

// Modal d'alerte d'incohérence projet ⇄ corps. Réutilise l'overlay des issues
// en attente pour un rendu cohérent ; restaure libellés et liste à la
// fermeture. Résout true (envoyer quand même) / false (annuler).
function afficherModalIncoherence(projetIssue, projetSelectionne) {
  return new Promise(resolve => {
    const overlay = document.getElementById('modal-confirmation');
    const liste   = document.getElementById('modal-liste');
    const btnOui  = document.getElementById('modal-oui');
    const btnNon  = document.getElementById('modal-non');
    const ouiAvant = btnOui.textContent;
    const nonAvant = btnNon.textContent;
    document.getElementById('modal-titre').textContent = '⚠️ Incohérence détectée';
    liste.style.display = '';
    liste.innerHTML =
      'L\'en-tête de l\'issue indique le projet « <b>' + escapeHtml(projetIssue) + '</b> » '
      + 'mais tu envoies sur <b>' + escapeHtml(projetSelectionne) + '</b>.'
      + '<br><br>Envoyer quand même sur <b>' + escapeHtml(projetSelectionne) + '</b> ?';
    btnOui.textContent = 'Envoyer quand même';
    btnNon.textContent = 'Annuler';
    function fermer(reponse) {
      overlay.classList.remove('actif');
      btnOui.onclick = null; btnNon.onclick = null;
      btnOui.textContent = ouiAvant;
      btnNon.textContent = nonAvant;
      resolve(reponse);
    }
    btnOui.onclick = () => fermer(true);
    btnNon.onclick = () => fermer(false);
    overlay.classList.add('actif');
  });
}

async function envoyerIssue() {
  cacherRetours();
  const data = collecterFormulaire();
  if (!data.titre) { afficherMessage('Le titre est obligatoire.', 'erreur'); return; }

  // Avertit si des issues for-linux sont déjà en attente sur ce projet, pour
  // éviter les conflits quand plusieurs issues mode_write s'enchaînent.
  try {
    const repAttente = await fetch('/issues-en-attente/' + encodeURIComponent(data.projet));
    const enAttente  = await repAttente.json();
    if (Array.isArray(enAttente) && enAttente.length) {
      const confirmer = await afficherModalConfirmation(enAttente);
      if (!confirmer) return;   // l'utilisateur a annulé l'envoi
    }
  } catch(e) {
    // La vérification a échoué (réseau, gh…) : on n'empêche pas l'envoi.
  }

  // Second garde-fou : si on a déjà envoyé une issue dans cette session sur un
  // AUTRE projet, on confirme explicitement la cible avant d'envoyer.
  if (sessionDernierEnvoi && sessionDernierEnvoi !== data.projet) {
    const ok = await afficherModalGenerique(
      'Attention : tu envoies sur ' + data.projet
        + ' (dernier envoi : ' + sessionDernierEnvoi + '). Confirmer ?',
      'Oui, envoyer sur ' + data.projet,
      'Annuler');
    if (!ok) return;
  }

  // Garde-fou ciblé : alerte seulement si le champ PROJET de l'en-tête diffère
  // du projet sélectionné (issue partie sur le mauvais dépôt).
  try {
    const incoherence = detecterIncoherenceProjet(data);
    if (incoherence) {
      const ok = await afficherModalIncoherence(
        incoherence.projetIssue, incoherence.projetSelectionne);
      if (!ok) return;   // l'utilisateur a annulé l'envoi
    }
  } catch(e) {
    // La détection a échoué : on n'empêche pas l'envoi.
  }

  const btn = document.getElementById('btn-envoyer');
  btn.disabled = true; btn.textContent = 'Envoi…';
  try {
    const rep = await fetch('/envoyer', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
    const json = await rep.json();
    if (json.succes) {
      afficherMessage('✓ Issue créée : ' + json.url, 'succes');
      sessionDernierEnvoi = data.projet;   // mémorise la cible du dernier envoi
      viderFormulaire(false);
    } else {
      afficherMessage('Erreur : ' + json.erreur, 'erreur');
    }
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
  // Restaure le libellé avec le projet cible plutôt qu'un texte générique.
  btn.disabled = false;
  btn.textContent = 'Envoyer sur ' + document.getElementById('projet').value;
}

async function chargerWatchers() {
  const rep  = await fetch('/watchers');
  const liste = await rep.json();
  const tbody = document.getElementById('corps-watchers');
  tbody.innerHTML = '';
  for (const w of liste) {
    const tr = document.createElement('tr');
    tr.style.borderBottom = '1px solid #f0efe9';
    tr.innerHTML = `
      <td style="padding:10px 0;text-align:center">
        <input type="checkbox" class="cb-watcher" value="${w.nom}"
               onchange="mettreAJourCompte()">
      </td>
      <td style="padding:10px 4px">
        <span style="width:8px;height:8px;border-radius:50%;
              background:${w.actif ? '#5cb85c' : '#d9534f'};
              display:inline-block"></span>
      </td>
      <td style="padding:10px 12px;font-size:13px">${w.nom}</td>
      <td style="padding:10px 12px;font-size:13px;color:#888">${w.depot}</td>
      <td style="padding:10px 0;font-size:12px;color:#aaa">
        ${w.actif ? 'pid ' + w.pid : '—'}
      </td>`;
    tbody.appendChild(tr);
  }
  mettreAJourCompte();
  document.getElementById('cb-tous').checked = false;
}

function selectionnerTous(cb) {
  document.querySelectorAll('.cb-watcher').forEach(c => c.checked = cb.checked);
  mettreAJourCompte();
}

function mettreAJourCompte() {
  const n = document.querySelectorAll('.cb-watcher:checked').length;
  document.getElementById('compte-selection').textContent =
    n === 0 ? 'Aucun sélectionné' : `${n} sélectionné(s)`;
}

async function actionWatchers(action) {
  const selectionnes = [...document.querySelectorAll('.cb-watcher:checked')].map(c => c.value);
  if (!selectionnes.length) {
    const msg = document.getElementById('msg-watchers');
    msg.textContent = 'Sélectionne au moins un projet.';
    msg.className = 'message erreur'; msg.style.display = 'block';
    setTimeout(() => msg.style.display = 'none', 3000);
    return;
  }
  document.getElementById('msg-watchers').style.display = 'none';

  const route   = action === 'arreter' ? '/arreter-watcher' : '/lancer-watcher';
  const payload = action === 'lancer'
    ? (nom) => ({projet: nom, relancer: false})
    : (nom) => ({projet: nom, relancer: action === 'relancer'});

  for (const nom of selectionnes) {
    await fetch(route, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload(nom))
    });
  }
  await chargerWatchers();
  await verifierStatut();
}

function mettreAJourBoutonEnvoi() {
  const ecriture = document.querySelector('input[name=mode]:checked').value === 'ecriture';
  const btn = document.getElementById('btn-envoyer');
  btn.style.background    = ecriture ? '#a32d2d' : '#1a1a18';
  btn.style.borderColor   = ecriture ? '#a32d2d' : '#1a1a18';
}

// Détection de « #Titre: … » en première ligne du corps.
// Permet de coller titre + corps en un seul copier-coller dans le champ #corps :
// si la première ligne commence par « #Titre: » (insensible à la casse, espaces
// tolérés après « : »), on déplace ce qui suit dans #titre et on retire cette
// ligne du corps. Le champ #titre reste éditable normalement ; taper directement
// dedans ne déclenche aucun comportement automatique (l'écouteur est sur #corps).
function detecterTitreDansCorps() {
  const corpsEl = document.getElementById('corps');
  const valeur  = corpsEl.value;
  const finLigne      = valeur.indexOf('\n');
  const premiereLigne = finLigne === -1 ? valeur : valeur.slice(0, finLigne);
  const m = premiereLigne.match(/^#titre:\s*(.*)$/i);
  if (!m) return;

  // Mémorise le mode courant : la détection ne touche pas au mode, mais on
  // n'appelle mettreAJourBoutonEnvoi() que s'il a effectivement changé.
  const modeAvant = document.querySelector('input[name=mode]:checked').value;

  document.getElementById('titre').value = m[1].trim();
  // Supprime la première ligne (et son saut de ligne) du corps.
  corpsEl.value = finLigne === -1 ? '' : valeur.slice(finLigne + 1);

  const modeApres = document.querySelector('input[name=mode]:checked').value;
  if (modeApres !== modeAvant) mettreAJourBoutonEnvoi();
}
document.getElementById('corps').addEventListener('input', detecterTitreDansCorps);

async function verifierStatut() {
  const nom = document.getElementById('projet').value;
  try {
    const rep  = await fetch('/statut/' + encodeURIComponent(nom));
    const json = await rep.json();
    const dot  = document.getElementById('dot-statut');
    const txt  = document.getElementById('texte-statut');
    const btn  = document.getElementById('btn-watcher');
    if (json.actif) {
      dot.style.background = '#5cb85c';
      txt.style.color      = '#155724';
      txt.textContent      = 'Watcher actif (pid ' + json.pid + ')';
      btn.textContent      = 'Relancer le watcher';
    } else {
      dot.style.background = '#d9534f';
      txt.style.color      = '#888';
      txt.textContent      = 'Watcher inactif';
      btn.textContent      = 'Lancer le watcher';
    }
  } catch(e) { /* réseau indisponible — on ignore */ }
}

async function lancerWatcher() {
  const btn = document.getElementById('btn-watcher');
  btn.disabled = true; btn.textContent = 'Démarrage…';
  try {
    const rep  = await fetch('/lancer-watcher', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({projet: document.getElementById('projet').value})
    });
    const json = await rep.json();
    if (!json.succes) afficherMessage('Erreur watcher : ' + json.erreur, 'erreur');
  } catch(e) {
    afficherMessage('Erreur réseau : ' + e.message, 'erreur');
  }
  btn.disabled = false;
  await verifierStatut();
}

// Au chargement : restaure le dernier projet mémorisé (localStorage) s'il
// correspond encore à une option existante, puis initialise l'accent visuel, le
// statut et les infos via onProjetChange(). Sonde ensuite toutes les 5 s.
(function restaurerProjet() {
  const select = document.getElementById('projet');
  let dernier = null;
  try { dernier = localStorage.getItem('bridge_projet_actif'); } catch(e) {}
  if (dernier && [...select.options].some(o => o.value === dernier)) {
    select.value = dernier;
  }
  onProjetChange();
})();
setInterval(verifierStatut, 5000);

// ─── Cycle de vie : onglet ↔ serveur ──────────────────────────────────────
// Deux liens : (1) heartbeat navigateur → serveur, qui laisse le serveur se
// couper tout seul quand l'onglet est fermé ; (2) canal SSE serveur → onglet,
// qui affiche un overlay quand le serveur s'arrête (Ctrl+C ou coupure brutale).
let sourceEvents     = null;
let timerErreurArret = null;

function afficherOverlayArret() {
  const ov = document.getElementById('overlay-arret');
  if (ov) ov.classList.add('actif');
}

// Heartbeat périodique : signale au serveur que l'onglet est toujours ouvert.
function envoyerHeartbeat() {
  fetch('/heartbeat', {method: 'POST'}).catch(() => {});
}

// Avant tout déchargement (F5, Ctrl+R, navigation, fermeture), on pose un
// drapeau : au chargement suivant, sa présence révèle un simple rechargement.
window.addEventListener('beforeunload', function() {
  try { sessionStorage.setItem('_refresh', '1'); } catch(e) {}
});

function demarrerCycleVie() {
  // Distinction refresh / fermeture : si le drapeau est présent, c'était un
  // rechargement — on le retire et on reprend normalement. S'il est absent,
  // c'était une vraie fermeture (mais alors le serveur est déjà coupé : le
  // heartbeat interrompu l'a fait s'arrêter, donc ce code ne s'exécute pas).
  try {
    if (sessionStorage.getItem('_refresh')) sessionStorage.removeItem('_refresh');
  } catch(e) {}

  envoyerHeartbeat();
  setInterval(envoyerHeartbeat, 5000);

  // Canal serveur → onglet.
  sourceEvents = new EventSource('/events');

  // Arrêt propre du serveur (Ctrl+C) : event « shutdown » explicite.
  sourceEvents.addEventListener('shutdown', function() {
    if (timerErreurArret) { clearTimeout(timerErreurArret); timerErreurArret = null; }
    sourceEvents.close();
    afficherOverlayArret();
  });

  // Connexion (r)établie : annule une éventuelle alerte en attente.
  sourceEvents.onopen = function() {
    if (timerErreurArret) { clearTimeout(timerErreurArret); timerErreurArret = null; }
  };

  // Coupure brutale (serveur tué sans signal) : la connexion SSE tombe en
  // erreur. Délai de 3 s avant l'overlay pour ne pas réagir à un micro-freeze ;
  // si la connexion se rétablit entre-temps, onopen annule le timer.
  sourceEvents.onerror = function() {
    if (timerErreurArret) return;
    timerErreurArret = setTimeout(function() {
      timerErreurArret = null;
      afficherOverlayArret();
    }, 3000);
  };
}
demarrerCycleVie();

// Arrêt volontaire depuis l'onglet : window.close() est autorisé par le
// navigateur car déclenché par une action utilisateur (contrairement à Ctrl+C
// côté serveur, qui ne peut que déclencher l'overlay via /events). On prévient
// le serveur (/quitter pose arret_demande puis os._exit après 2 s) et on ferme.
async function quitter() {
  if (!confirm('Arrêter new_issue.py et fermer l\'onglet ?')) return;
  await fetch('/quitter', {method: 'POST'});
  window.close();
}

function viderFormulaire(cacherMsg=true) {
  if (cacherMsg) cacherRetours();
  document.getElementById('titre').value = '';
  document.getElementById('corps').value = '';
  document.getElementById('priorite').value = 'normale';
  // Réinitialise le timeout sur la valeur TIMEOUT_CLAUDE du projet courant.
  mettreAJourInfoProjet();
  document.querySelector('input[name=mode][value=lecture]').checked = true;
  mettreAJourBoutonEnvoi();
  document.querySelectorAll('input[name=notifs]').forEach(c => c.checked = false);
  document.getElementById('modele-ponctuel').value = '';
}

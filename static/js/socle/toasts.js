// toasts.js — canal unique de notification non bloquant (issue #625, étape 1).
//
// RESPONSABILITÉ
//   Une seule façon de parler à l'utilisateur :
//   - toasts.info / succes / erreur / avertissement : message éphémère qui
//     s'efface tout seul. JAMAIS de boîte à fermer avec « OK » (fini les
//     alert()). C'est le remplaçant de alert(...) et de afficherToast(...).
//   - toasts.confirmer(...) : LA seule modale, réservée aux confirmations
//     d'actions destructives (remplaçant de confirm(...)). Renvoie une Promise
//     qui se résout à true (confirmé) ou false (annulé).
//
// CE QU'IL EXPOSE
//   export const toasts = { info, succes, erreur, avertissement, confirmer }
//
// AUTONOMIE VISUELLE
//   Les styles sont injectés une seule fois, à la première utilisation, sous des
//   classes préfixées `socle-` : aucune dépendance à style.css, et rien ne
//   s'affiche tant qu'une fonction n'est pas appelée (le socle est inerte à
//   l'étape 1). L'accès au DOM est paresseux → l'import reste sûr sous Node.

const DUREE_DEFAUT_MS = 4000;
let stylesInjectes = false;

function doc() {
  if (typeof document === 'undefined') return null;
  return document;
}

function injecterStyles() {
  if (stylesInjectes) return;
  const d = doc();
  if (!d) return;
  stylesInjectes = true;
  const style = d.createElement('style');
  style.id = 'socle-toasts-styles';
  style.textContent = `
.socle-toasts{position:fixed;top:16px;left:50%;transform:translateX(-50%);
  z-index:3000;display:flex;flex-direction:column;gap:8px;align-items:center;
  pointer-events:none}
.socle-toast{pointer-events:auto;min-width:220px;max-width:80vw;padding:10px 16px;
  border-radius:8px;font-size:13px;font-weight:500;color:#fff;
  box-shadow:0 4px 16px rgba(0,0,0,.22);opacity:0;transform:translateY(-8px);
  transition:opacity .18s,transform .18s}
.socle-toast.visible{opacity:1;transform:translateY(0)}
.socle-toast.info{background:#334}
.socle-toast.succes{background:#22803a}
.socle-toast.avertissement{background:#8a6d00}
.socle-toast.erreur{background:#a32d2d}
.socle-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.45);
  z-index:3100;display:flex;justify-content:center;align-items:flex-start;
  padding:70px 16px}
.socle-modal-carte{background:#fff;border-radius:12px;max-width:460px;width:100%;
  padding:22px 24px;box-shadow:0 10px 40px rgba(0,0,0,.28)}
.socle-modal-titre{font-size:15px;font-weight:600;line-height:1.4;margin-bottom:12px}
.socle-modal-message{font-size:13px;line-height:1.5;margin-bottom:18px;color:#333;
  white-space:pre-wrap}
.socle-modal-boutons{display:flex;justify-content:flex-end;gap:10px}
.socle-modal-boutons button{padding:7px 16px;border:1px solid #ccc;border-radius:6px;
  font-size:13px;cursor:pointer;background:#fff;color:#1a1a18}
.socle-modal-boutons button.danger{background:#a32d2d;color:#fff;border-color:#a32d2d}
`;
  d.head.appendChild(style);
}

function afficher(texte, type) {
  const d = doc();
  if (!d) { return; }
  injecterStyles();
  let conteneur = d.querySelector('.socle-toasts');
  if (!conteneur) {
    conteneur = d.createElement('div');
    conteneur.className = 'socle-toasts';
    d.body.appendChild(conteneur);
  }
  const toast = d.createElement('div');
  toast.className = `socle-toast ${type}`;
  toast.textContent = texte;
  conteneur.appendChild(toast);
  // Forcer un reflow puis lancer la transition d'apparition.
  requestAnimationFrame(() => toast.classList.add('visible'));
  const partir = () => {
    toast.classList.remove('visible');
    setTimeout(() => toast.remove(), 200);
  };
  setTimeout(partir, DUREE_DEFAUT_MS);
  toast.addEventListener('click', partir);
  return toast;
}

/**
 * LA modale de confirmation destructive (unique). Renvoie une Promise<boolean>.
 * @param {string} message
 * @param {{titre?:string, texteConfirmer?:string, texteAnnuler?:string}} [opts]
 */
function confirmer(message, opts = {}) {
  const {
    titre = 'Confirmer',
    texteConfirmer = 'Confirmer',
    texteAnnuler = 'Annuler',
  } = opts;
  const d = doc();
  if (!d) return Promise.resolve(false);
  injecterStyles();
  return new Promise((resoudre) => {
    const overlay = d.createElement('div');
    overlay.className = 'socle-modal-overlay';
    overlay.innerHTML =
      '<div class="socle-modal-carte" role="dialog" aria-modal="true">' +
      '<div class="socle-modal-titre"></div>' +
      '<div class="socle-modal-message"></div>' +
      '<div class="socle-modal-boutons">' +
      '<button data-role="annuler"></button>' +
      '<button class="danger" data-role="confirmer"></button>' +
      '</div></div>';
    overlay.querySelector('.socle-modal-titre').textContent = titre;
    overlay.querySelector('.socle-modal-message').textContent = message;
    const btnAnnuler = overlay.querySelector('[data-role="annuler"]');
    const btnConfirmer = overlay.querySelector('[data-role="confirmer"]');
    btnAnnuler.textContent = texteAnnuler;
    btnConfirmer.textContent = texteConfirmer;
    const fermer = (valeur) => { overlay.remove(); resoudre(valeur); };
    btnAnnuler.addEventListener('click', () => fermer(false));
    btnConfirmer.addEventListener('click', () => fermer(true));
    overlay.addEventListener('click', (e) => { if (e.target === overlay) fermer(false); });
    d.body.appendChild(overlay);
    btnConfirmer.focus();
  });
}

export const toasts = {
  info: (texte) => afficher(texte, 'info'),
  succes: (texte) => afficher(texte, 'succes'),
  erreur: (texte) => afficher(texte, 'erreur'),
  avertissement: (texte) => afficher(texte, 'avertissement'),
  confirmer,
};

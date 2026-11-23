// Tests de static/js/socle/sse.js (issue #937) : le battement serveur du
// canal /stream (app/fin_issue.py, DELAI_PING) est un événement SSE NOMMÉ
// ('battement') reçu par un gestionnaire côté client — AVANT ce correctif,
// c'était un commentaire du protocole SSE (': ping'), qu'EventSource
// n'expose jamais à un gestionnaire JavaScript (le symptôme de l'issue #937
// : un flux sain jugé silencieux). EventSource n'existe pas sous Node : un
// faux constructeur minimal (FakeEventSource ci-dessous) tient lieu de
// navigateur, comme le fait déjà l'en-tête de sse.js (connecter() est le
// SEUL endroit qui instancie `new EventSource`).
import { test } from 'node:test';
import assert from 'node:assert/strict';

class FakeEventSource {
  constructor(url) {
    this.url = url;
    this.listeners = {};
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    FakeEventSource.derniereInstance = this;
  }
  addEventListener(nom, fn) {
    (this.listeners[nom] ??= []).push(fn);
  }
  // Simule la réception d'un événement nommé réel (ex. 'battement',
  // 'debut_issue') — jamais une ligne de commentaire SSE, qu'EventSource
  // n'expose à aucun gestionnaire.
  emettre(nom, data) {
    for (const fn of (this.listeners[nom] || [])) fn({ type: nom, data });
  }
  close() {}
}
globalThis.EventSource = FakeEventSource;

const { creerCanalSse, sse } = await import('../socle/sse.js');

test('creerCanalSse : aucune activité avant connexion (depuisDerniereActiviteMs → null)', () => {
  const canal = creerCanalSse('/stream', {});
  assert.equal(canal.depuisDerniereActiviteMs(), null);
});

test('creerCanalSse : onOuvert (connexion) réarme l\'horodatage d\'activité', () => {
  const canal = creerCanalSse('/stream', {});
  canal.connecter();
  const source = FakeEventSource.derniereInstance;
  assert.equal(canal.depuisDerniereActiviteMs(), null);   // pas encore onopen
  source.onopen({});
  // Juste après onopen, l'ancienneté mesurée au moment présent est quasi
  // nulle (comparaison robuste, sans dépendre de l'horloge exacte).
  assert.ok(canal.depuisDerniereActiviteMs() < 50);
});

test('creerCanalSse : un événement NOMMÉ (ex. battement) réarme l\'horodatage d\'activité comme un événement métier', () => {
  let recu = null;
  const canal = creerCanalSse('/stream', { battement: (e) => { recu = e; } });
  canal.connecter();
  const source = FakeEventSource.derniereInstance;
  source.onopen({});
  source.emettre('battement', '{}');
  assert.ok(recu !== null, 'le gestionnaire "battement" doit être invoqué');
  assert.ok(canal.depuisDerniereActiviteMs() < 50);
});

test('creerCanalSse : addEventListener posé pour chaque événement nommé, onmessage pour la clé "message"', () => {
  const canal = creerCanalSse('/stream', { message: () => {}, autre_evenement: () => {} });
  canal.connecter();
  const source = FakeEventSource.derniereInstance;
  assert.equal(typeof source.onmessage, 'function');
  assert.ok(Array.isArray(source.listeners.autre_evenement) && source.listeners.autre_evenement.length === 1);
  assert.equal(source.listeners.message, undefined);   // 'message' passe par onmessage, jamais addEventListener
});

// ─── sse.stream : le canal /stream préconfiguré écoute bien 'battement' ─────
test('sse.stream : le canal préconfiguré écoute l\'événement nommé "battement" (issue #937)', () => {
  sse.stream.fermer();
  sse.stream.connecter();
  const source = FakeEventSource.derniereInstance;
  assert.ok(Array.isArray(source.listeners.battement) && source.listeners.battement.length === 1,
    'sse.stream doit poser un gestionnaire pour l\'événement SSE nommé "battement"');
  sse.stream.fermer();
});

test('sse.stream : recevoir "battement" réarme l\'ancienneté du flux SANS passer par un événement métier', () => {
  sse.stream.fermer();
  sse.stream.connecter();
  const source = FakeEventSource.derniereInstance;
  source.onopen({});
  source.emettre('battement', '{}');
  assert.ok(sse.stream.depuisDerniereActiviteMs() < 50);
  sse.stream.fermer();
});

// Tests de api.js — délai maximum par requête (issue #917 point 7) : AUCUNE
// requête de l'interface ne doit plus rester bloquée indéfiniment. Mock de
// `fetch` global (Node 18+, pas de dépendance de test supplémentaire) —
// lancement (depuis la racine) :
//   node --test static/js/socle/tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';

import { api, ErreurApi, TIMEOUT_DEFAUT_MS } from '../api.js';

function restaurerFetch(original) {
  globalThis.fetch = original;
}

test('api.requete : délai dépassé → ErreurApi avec timeout:true, message explicite', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (url, options) => new Promise((resolve, reject) => {
    // Ne résout jamais tout seul — seul l'abandon (signal) doit trancher.
    if (options && options.signal) {
      options.signal.addEventListener('abort', () => {
        const e = new Error('The operation was aborted');
        e.name = 'AbortError';
        reject(e);
      });
    }
  });
  try {
    await assert.rejects(
      () => api.get('/lent', { silencieux: true, timeoutMs: 20 }),
      (err) => {
        assert.ok(err instanceof ErreurApi);
        assert.equal(err.timeout, true);
        assert.match(err.message, /Délai dépassé/);
        return true;
      });
  } finally {
    restaurerFetch(original);
  }
});

test('api.requete : timeoutMs:0 désactive le délai (aucun signal transmis à fetch)', async () => {
  const original = globalThis.fetch;
  let signalRecu;
  globalThis.fetch = async (url, options) => {
    signalRecu = options && options.signal;
    return { ok: true, text: async () => '{"ok":true}' };
  };
  try {
    const rep = await api.get('/sans-delai', { silencieux: true, timeoutMs: 0 });
    assert.deepEqual(rep, { ok: true });
    assert.equal(signalRecu, undefined);
  } finally {
    restaurerFetch(original);
  }
});

test('api.requete : succès normal toujours inchangé avec le délai par défaut', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: true, text: async () => '{"valeur":42}' });
  try {
    const rep = await api.get('/ok', { silencieux: true });
    assert.deepEqual(rep, { valeur: 42 });
  } finally {
    restaurerFetch(original);
  }
});

test('api.requete : coupure réseau normale (sans abandon) reste timeout:false', async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new Error('ECONNREFUSED'); };
  try {
    await assert.rejects(
      () => api.get('/coupe', { silencieux: true }),
      (err) => {
        assert.ok(err instanceof ErreurApi);
        assert.equal(err.timeout, false);
        assert.match(err.message, /injoignable/);
        return true;
      });
  } finally {
    restaurerFetch(original);
  }
});

test('TIMEOUT_DEFAUT_MS : de l\'ordre de 30s', () => {
  assert.equal(TIMEOUT_DEFAUT_MS, 30000);
});

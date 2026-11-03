// Run with: node --test scripts/testes/security_frontend.test.cjs
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../..');

function worker() {
  const handlers = {}, writes = [], removed = [];
  let online = true;
  const fallback = new Response('offline público');
  const cache = {
    async match(key) { return key === '/offline/' ? fallback : undefined; },
    async put(key) { writes.push(typeof key === 'string' ? key : key.url); },
  };
  const context = {
    URL, Response,
    self: {
      location: {origin: 'https://test.local'},
      addEventListener: (name, handler) => handlers[name] = handler,
      skipWaiting: async () => {},
      clients: {claim: async () => {}},
    },
    caches: {
      open: async () => cache,
      keys: async () => ['santuario-v8', 'santuario-quiz-v1', 'santuario-v9', 'another-app'],
      delete: async key => removed.push(key),
    },
    fetch: async () => {
      if (!online) throw new Error('offline');
      return new Response('private content');
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'quiz/static/quiz/sw.js'), 'utf8'), context);
  return {handlers, writes, removed, offline: () => online = false};
}

test('upgrade removes old authenticated caches and preserves unrelated caches', async () => {
  const w = worker();
  let completion;
  w.handlers.activate({waitUntil: value => completion = value});
  await completion;
  assert.deepEqual(w.removed.sort(), ['santuario-quiz-v1', 'santuario-v8']);
});

test('private navigation is never cached; offline only returns public fallback', async () => {
  const w = worker();
  for (const url of ['/perfil/', '/dashboard/', '/admin-painel/', '/quiz/']) {
    let response;
    const event = {request: {url: 'https://test.local' + url, method: 'GET', mode: 'navigate'},
                   respondWith: value => response = value};
    w.handlers.fetch(event);
    assert.equal(await (await response).text(), 'private content');
    assert.equal(w.writes.length, 0);
  }
  w.offline();
  let response;
  w.handlers.fetch({request: {url: 'https://test.local/perfil/', method: 'GET', mode: 'navigate'},
                    respondWith: value => response = value});
  assert.equal(await (await response).text(), 'offline público');
});

test('media and APIs bypass cache even when URLs have image extensions', () => {
  const w = worker();
  for (const url of ['/media/perfil/avatar.jpg', '/api/private.png']) {
    let intercepted = false;
    w.handlers.fetch({request: {url: 'https://test.local' + url, method: 'GET', mode: 'cors'},
                      respondWith: () => intercepted = true});
    assert.equal(intercepted, false);
  }
});

test('public static assets can be cached', async () => {
  const w = worker();
  let response;
  w.handlers.fetch({request: {url: 'https://test.local/static/app.js', method: 'GET', mode: 'cors'},
                    respondWith: value => response = value});
  await response;
  assert.deepEqual(w.writes, ['https://test.local/static/app.js']);
});

test('changed game scripts have valid JavaScript syntax', () => {
  for (const name of ['modo_desafio', 'duelo_jogar', 'coletivo_jogar']) {
    const html = fs.readFileSync(path.join(root, `quiz/templates/quiz/${name}.html`), 'utf8');
    const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
    assert.ok(scripts.length);
    for (const [, script] of scripts) {
      // Template numeric/boolean values and URL tags are tested by Django separately.
      new vm.Script(script.replace(/{{[\s\S]*?}}/g, '1').replace(/{%[\s\S]*?%}/g, '/test/'));
    }
  }
});

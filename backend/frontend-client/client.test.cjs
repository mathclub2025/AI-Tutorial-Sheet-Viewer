// Run after compiling mathclubClient.ts to .client-test (see README).
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { MathClubClient, MathClubAPIError } = require('../.client-test/mathclubClient.js');

test('sends filters, honors same-origin credentials and encodes identifiers', async () => {
  const calls = [];
  global.fetch = async (url, init) => {
    calls.push([url, init]);
    return new Response(JSON.stringify({ items: [], total: 0, request_id: 'trace-1', captured: false }));
  };
  const client = new MathClubClient('https://mathclub.test/');
  await client.search('differentiate', { topic: 'Differentiation' }, 3);
  assert.equal(calls[0][0], 'https://mathclub.test/api/v1/search');
  assert.equal(calls[0][1].credentials, 'same-origin');
  assert.equal(JSON.parse(calls[0][1].body).limit, 3);
  await client.getQuestion('unsafe/id');
  assert.ok(calls[1][0].endsWith('/unsafe%2Fid'));
});

test('preserves structured errors, trace and retry delay', async () => {
  global.fetch = async () => new Response(JSON.stringify({ error: 'RATE_LIMITED', message: 'Too many requests', details: [] }),
    { status: 429, headers: { 'X-Request-ID': 'trace-1234', 'Retry-After': '12' } });
  await assert.rejects(new MathClubClient('').catalog(), error => {
    assert.ok(error instanceof MathClubAPIError);
    assert.equal(error.code, 'RATE_LIMITED');
    assert.equal(error.requestId, 'trace-1234');
    assert.equal(error.retryAfter, 12);
    return true;
  });
});

test('invalid success JSON is an error', async () => {
  global.fetch = async () => new Response('not json');
  await assert.rejects(new MathClubClient('').catalog(), error => error.code === 'INVALID_RESPONSE');
});

test('network error has stable code', async () => {
  global.fetch = async () => { throw new TypeError('network'); };
  await assert.rejects(new MathClubClient('').catalog(), error => error.code === 'NETWORK_ERROR');
});

test('timeout cancels the fetch', async () => {
  global.fetch = (_, init) => new Promise((_, reject) => {
    init.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  await assert.rejects(new MathClubClient('', () => ({}), { timeoutMs: 5 }).catalog(), error => error.code === 'TIMEOUT');
});

test('caller cancellation is distinct from timeout', async () => {
  const controller = new AbortController();
  global.fetch = (_, init) => new Promise((_, reject) => {
    init.signal.addEventListener('abort', () => reject(new Error('aborted')), { once: true });
  });
  const promise = new MathClubClient('').catalog({ signal: controller.signal });
  controller.abort();
  await assert.rejects(promise, error => error.code === 'CANCELLED');
});

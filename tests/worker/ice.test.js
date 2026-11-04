import { test } from 'node:test';
import assert from 'node:assert/strict';
import { normalizeIceServers, isSameOrigin } from '../../src/ice.js';

test('ポート53の URL を落とし、認証情報は残す', () => {
  const out = normalizeIceServers({
    iceServers: [
      { urls: ['stun:stun.cloudflare.com:3478', 'stun:stun.cloudflare.com:53'] },
      {
        urls: ['turn:turn.cloudflare.com:3478?transport=udp', 'turn:turn.cloudflare.com:53?transport=udp', 'turns:turn.cloudflare.com:443?transport=tcp'],
        username: 'u', credential: 'c',
      },
    ],
  });
  assert.deepEqual(out, [
    { urls: ['stun:stun.cloudflare.com:3478'] },
    { urls: ['turn:turn.cloudflare.com:3478?transport=udp', 'turns:turn.cloudflare.com:443?transport=tcp'], username: 'u', credential: 'c' },
  ]);
});

test('古い形（1件の物）でも読める・空なら空', () => {
  assert.equal(normalizeIceServers({ iceServers: { urls: 'turn:x:3478', username: 'u', credential: 'c' } }).length, 1);
  assert.deepEqual(normalizeIceServers({}), []);
  assert.deepEqual(normalizeIceServers({ iceServers: [{ urls: ['stun:x:53'] }] }), []);
});

const req = (h) => new Request('https://room.example/api/ice', { headers: h });

test('同じサイトのページからの要求だけ通す', () => {
  assert.equal(isSameOrigin(req({ 'Sec-Fetch-Site': 'same-origin' })), true);
  assert.equal(isSameOrigin(req({ 'Sec-Fetch-Site': 'cross-site' })), false);
  assert.equal(isSameOrigin(req({ Origin: 'https://room.example' })), true);
  assert.equal(isSameOrigin(req({ Origin: 'https://evil.example' })), false);
  assert.equal(isSameOrigin(req({})), false);
});

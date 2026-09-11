import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseLyrics, activeLine, lyricEndpoint, lyricIdentityTitle, lyricRetryAfter, lyricRetryCountdown } from '../backend/static/lyrics-data.js';

test('LRC supports multiple timestamps, metadata offset, blank instrumental lines and translations', () => {
  const { lines, timed } = parseLyrics('[ar:Example]\n[offset:500]\n[00:03.00][00:08.00]Original\n[00:03.00]Translation\n[00:05.00]\n[00:00.00]Intro');
  assert.equal(timed, true);
  assert.deepEqual(lines.map(line => line.time), [0, 2.5, 4.5, 7.5]);
  assert.equal(lines[1].text, 'Original\nTranslation');
  assert.equal(lines[2].text, '');
  assert.equal(activeLine(lines, 0), 0);
  assert.equal(activeLine(lines, 2.4), 0);
  assert.equal(activeLine(lines, 3), 1);
  assert.equal(activeLine(lines, -1), -1);
});

test('plain text is not assigned synthetic playback timestamps', () => {
  assert.deepEqual(parseLyrics('[ar:Example]\nFirst line\nSecond line'), { timed: false, lines: [{ time: null, text: 'First line' }, { time: null, text: 'Second line' }] });
  assert.equal(parseLyrics(null).lines.length, 0);
  assert.equal(parseLyrics('[ar:Example]').lines.length, 0);
});

test('lyric URL preserves raw joox plus signs, accepts local proxy and rejects external paths', () => {
  const origin = 'https://audio.deline.top';
  assert.equal(lyricEndpoint('/music/s/joox/Ab%252Bcd%253D%253D.mp3', origin), '/music/lyrics/joox/Ab%2Bcd%3D%3D.json');
  assert.equal(lyricEndpoint('/s/netease/123.mp3', origin), '/lyrics/netease/123.json');
  assert.equal(lyricEndpoint('https://other.example/s/netease/123.mp3', origin), null);
  assert.equal(lyricEndpoint('/voice/speech.mp3', origin), null);
  assert.equal(lyricEndpoint('/music/s/joox/%QQ.mp3', origin), null);
  assert.equal(lyricEndpoint('/music/s/kuwo/song-hash.mp3?stream=1', origin, { source: 'kuwo', id: 'song-hash', lyric_id: 'separate-lyric-id' }), '/music/lyrics/kuwo/separate-lyric-id.json');
  assert.equal(lyricEndpoint('/music/s/tencent/123.mp3', origin, { source: 'tencent', lyric_id: 'abc+def==' }), '/music/lyrics/tencent/abc%2Bdef%3D%3D.json');
  assert.equal(lyricEndpoint('/music/s/id/123.mp3', origin), '/music/lyrics/netease/123.json');
  assert.equal(lyricEndpoint('https://other.example/music/s/tencent/123.mp3', origin, { source: 'tencent', lyric_id: '123' }), null);
});

test('lyric URL includes strict identity and removes only the exact artist display prefix', () => {
  const origin = 'https://audio.deline.top';
  assert.equal(lyricIdentityTitle('赵雷 - 南方姑娘', '赵雷'), '南方姑娘');
  assert.equal(lyricIdentityTitle('Blue - Live', 'Artist'), 'Blue - Live');
  assert.equal(
    lyricEndpoint('/music/s/netease/123.mp3', origin, { title: '赵雷 - 南方姑娘', artist: '赵雷' }),
    '/music/lyrics/netease/123.json?title=%E5%8D%97%E6%96%B9%E5%A7%91%E5%A8%98&artist=%E8%B5%B5%E9%9B%B7',
  );
  assert.equal(
    lyricEndpoint('/music/s/netease/123.mp3', origin, {
      title: '赵雷 - 南方姑娘', lyric_title: '南方姑娘', artist: '趙雷',
    }),
    '/music/lyrics/netease/123.json?title=%E5%8D%97%E6%96%B9%E5%A7%91%E5%A8%98&artist=%E8%B6%99%E9%9B%B7',
  );
});

test('lyric retry delay prefers structured retry_after and understands HTTP dates', () => {
  const response = { headers: { get: () => '45' } };
  assert.equal(lyricRetryAfter(response, { detail: { status: 'limited', retry_after: 137 } }), 137);
  assert.equal(lyricRetryAfter(response, {}), 45);
  assert.equal(lyricRetryAfter({ headers: { get: () => 'Thu, 01 Jan 2026 00:01:00 GMT' } }, {}, Date.UTC(2026, 0, 1)), 60);
  assert.equal(lyricRetryAfter({ headers: { get: () => null } }, {}), 300);
});

test('lyric retry countdown derives a live non-negative value from its deadline', () => {
  const now = Date.UTC(2026, 8, 12, 0, 0, 0);
  const deadline = now + 233000;
  assert.equal(lyricRetryCountdown(deadline, now), 233);
  assert.equal(lyricRetryCountdown(deadline, now + 1000), 232);
  assert.equal(lyricRetryCountdown(deadline, now + 232001), 1);
  assert.equal(lyricRetryCountdown(deadline, now + 233000), 0);
  assert.equal(lyricRetryCountdown(deadline, now + 240000), 0);
  assert.equal(lyricRetryCountdown('invalid', now), 0);
});

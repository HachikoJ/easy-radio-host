import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseLyrics, activeLine, lyricEndpoint } from '../backend/static/lyrics-data.js';

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
});

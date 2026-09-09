import { Lrc } from './vendor/lrc-kit/lrc.js';
import { parseLine, LineType } from './vendor/lrc-kit/line-parser.js';

export function parseLyrics(text) {
  if (typeof text !== 'string') return { lines: [], timed: false };
  text = text.slice(0, 100000);
  const parsed = Lrc.parse(text, { enhanced: false });
  const offset = Number(parsed.info.offset) || 0;
  const groups = new Map();
  for (const line of parsed.lyrics.slice(0, 1000)) {
    if (!Number.isFinite(line.timestamp)) continue;
    const time = Math.max(0, line.timestamp - offset / 1000);
    const content = line.content.trim().slice(0, 1000);
    if (groups.has(time)) groups.set(time, [groups.get(time), content].filter(Boolean).join('\n'));
    else groups.set(time, content);
  }
  if (groups.size && [...groups.values()].some(Boolean)) {
    return { timed: true, lines: [...groups].sort((a, b) => a[0] - b[0]).map(([time, text]) => ({ time, text })) };
  }
  return { timed: false, lines: text.split(/\r?\n/).filter(line => line.trim() && parseLine(line).type === LineType.INVALID).slice(0, 1000).map(text => ({ time: null, text: text.slice(0, 1000) })) };
}

export function activeLine(lines, time) {
  let low = 0, high = lines.length - 1, found = -1;
  while (low <= high) {
    const middle = Math.floor((low + high) / 2);
    if (lines[middle].time <= time) { found = middle; low = middle + 1; }
    else high = middle - 1;
  }
  return found;
}

export function lyricEndpoint(songUrl, origin) {
  try {
    const url = new URL(songUrl, origin);
    const match = url.pathname.match(/^(.*)\/s\/(joox|netease)\/([^/]+)\.mp3$/);
    if (!match || url.origin !== new URL(origin).origin) return null;
    // The playlist and song_url each quote the ID once before playback.
    const id = decodeURIComponent(decodeURIComponent(match[3]));
    return `${match[1]}/lyrics/${match[2]}/${encodeURIComponent(id)}.json`;
  } catch { return null; }
}

import { parseLyrics, activeLine, lyricEndpoint } from './lyrics-data.js';

export function createLyricsExperience({ audio, state, seek, demo }) {
  const get = id => document.getElementById(id);
  const panel = get('lyrics-panel'), viewport = get('lyrics-lines');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const focusMount = document.createElement('div'); focusMount.id = 'lyrics-focus';
  document.querySelector('.focus-copy').insertBefore(focusMount, document.querySelector('.up-next'));
  for (const target of document.querySelectorAll('.cover-wrap,.focus-art')) {
    const artwork = target.querySelector('img');
    const stage = document.createElement('div'); stage.className = 'record-stage';
    const disc = document.createElement('div'); disc.className = 'record-disc';
    target.insertBefore(stage, artwork); disc.append(artwork); stage.append(disc);
    const ring = document.createElement('div'); ring.className = 'record-rhythm'; ring.setAttribute('aria-hidden', 'true');
    for (let i = 0; i < 72; i++) {
      const spoke = document.createElement('span'), pulse = document.createElement('i');
      spoke.style.setProperty('--angle', `${i * 5}deg`);
      pulse.style.setProperty('--beat-delay', `${-i * .137}s`);
      pulse.style.setProperty('--beat-duration', `${.7 + (i % 7) * .11}s`);
      spoke.append(pulse); ring.append(spoke);
    }
    stage.append(ring);
  }
  let itemKey = null, controller = null, lines = [], timed = false, active = -2;
  let translations = [], offset = 0, ready = false, motion = true;
  let browseTimer = null;
  try { motion = localStorage.getItem('tingjian.motion.v1') !== 'off'; } catch { /* Optional preference. */ }
  get('motion-enabled').checked = motion;

  function motionState() {
    const song = state()?.kind === 'song';
    const moving = motion && !reduced.matches && !document.hidden && ready && !audio.paused && !audio.ended && !audio.seeking && song;
    document.body.classList.toggle('motion-playing', moving);
    document.body.classList.toggle('motion-disabled', !motion || reduced.matches);
    get('motion-status').textContent = !motion ? '动效已关闭' : reduced.matches ? '系统已减少动态效果' : !song ? state() ? '主持人口播中' : '等待播放' : audio.error ? '音频暂不可用' : audio.paused ? '已暂停' : !ready || audio.seeking ? '缓冲中' : '正在播放';
  }
  for (const event of ['playing', 'canplay']) audio.addEventListener(event, () => { ready = true; motionState(); });
  for (const event of ['waiting', 'loadstart', 'emptied', 'ended', 'error']) audio.addEventListener(event, () => { ready = false; motionState(); });
  for (const event of ['pause', 'seeking', 'seeked']) audio.addEventListener(event, motionState);
  document.addEventListener('visibilitychange', motionState);
  reduced.addEventListener('change', motionState);
  get('motion-enabled').addEventListener('change', () => {
    motion = get('motion-enabled').checked;
    try { localStorage.setItem('tingjian.motion.v1', motion ? 'on' : 'off'); } catch { /* Optional preference. */ }
    motionState();
  });

  function center(force = false) {
    if (browseTimer || !get('lyrics-follow').checked || active < 0 || !viewport.children[active]) return;
    const line = viewport.children[active];
    viewport.scrollTo({ top: line.offsetTop - viewport.clientHeight / 2 + line.offsetHeight / 2, behavior: force || reduced.matches ? 'instant' : 'smooth' });
  }
  function update(force = false) {
    if (!timed) return;
    const next = activeLine(lines, audio.currentTime - offset);
    if (next === active && !force) return;
    active = next;
    [...viewport.children].forEach((line, i) => {
      line.classList.toggle('current-line', i === active);
      if (i === active) line.setAttribute('aria-current', 'true'); else line.removeAttribute('aria-current');
    });
    preview(active >= 0 ? lines[active].text || '间奏' : '前奏 · 歌词即将开始');
    center(force);
  }
  function draw() {
    viewport.replaceChildren(...lines.map((line, i) => {
      const node = document.createElement(timed ? 'button' : 'p');
      node.className = 'lyric-line';
      if (timed) {
        node.type = 'button';
        node.addEventListener('click', () => { if (!Number.isFinite(audio.duration) || audio.duration <= 0) return; resumeFollow(); get('lyrics-follow').checked = true; seek(Math.max(0, line.time + offset)); update(true); });
      }
      const original = document.createElement('span'); original.textContent = line.text || '· · ·'; node.append(original);
      if (timed && get('lyrics-translation').checked) {
        const translation = translations.find(entry => Math.abs(entry.time - line.time) < .3 && entry.text && entry.text !== line.text);
        if (translation) { const text = document.createElement('small'); text.textContent = translation.text; node.append(text); }
      }
      node.dataset.line = i;
      return node;
    }));
    active = -2; update(true);
  }
  function preview(text) {
    get('player-lyric-text').textContent = text;
    get('player-lyric').setAttribute('aria-label', `查看歌词：${text}`);
  }
  function status(text) {
    get('lyrics-status').textContent = text;
    get('lyrics-panel').dataset.state = lines.length ? timed ? 'synced' : 'plain' : 'empty';
    preview(text);
  }
  async function load(item) {
    controller?.abort();
    clearTimeout(browseTimer); browseTimer = null;
    const request = new AbortController(); controller = request;
    lines = []; translations = []; timed = false; active = -2; offset = 0;
    viewport.replaceChildren(); viewport.scrollTop = 0;
    get('lyrics-offset').value = '0'; get('lyrics-follow').checked = true;
    get('lyrics-retry').hidden = true; get('translation-control').hidden = true;
    get('lyrics-timing').hidden = true;
    get('lyrics-source').textContent = '';
    get('player-lyric').disabled = item?.kind !== 'song';
    if (item?.kind !== 'song') { status(item ? '主持人口播中' : '选择歌曲后显示歌词'); return; }
    status('正在获取歌词…');
    panel.dataset.state = 'loading';
    const timeout = setTimeout(() => request.abort(), 18000);
    try {
      let data;
      if (demo) {
        data = { lyric: '[00:00.00]听间 · 原创器乐试听\n[00:03.00]窗边的光，慢慢落下\n[00:07.00]让旋律留住这一刻\n[00:11.00]微风经过，音乐继续', source: '原创演示文案' };
      } else {
        const endpoint = lyricEndpoint(item.url, location.origin);
        if (!endpoint) { status('此音源暂不支持歌词'); return; }
        const response = await fetch(endpoint, { signal: request.signal });
        if (!response.ok) throw new Error();
        data = await response.json();
      }
      if (request.signal.aborted || controller !== request) return;
      ({ lines, timed } = parseLyrics(data.lyric));
      const translated = parseLyrics(data.translation);
      translations = translated.timed ? translated.lines : [];
      get('translation-control').hidden = !translations.length || !timed;
      get('lyrics-timing').hidden = !timed;
      get('lyrics-source').textContent = demo ? '原创演示文案 · 非歌曲原词' : lines.length ? '歌词来源：GD 音乐 API · 版权归原权利人' : '';
      status(!lines.length ? '该音源未返回歌词' : timed ? `同步歌词 · ${lines.length} 行` : '纯文本歌词 · 无时间戳');
      get('lyrics-retry').hidden = lines.length > 0;
      draw();
      if (!timed && lines.length) preview(lines[0].text);
    } catch {
      if (controller !== request) return;
      status(request.signal.aborted ? '歌词请求超时，请重试' : '歌词请求失败，请重试');
      panel.dataset.state = 'error'; get('lyrics-retry').hidden = false;
    } finally { clearTimeout(timeout); }
  }
  function place() {
    const target = get(document.body.classList.contains('focus-mode') ? 'lyrics-focus' : 'lyrics-home');
    if (panel.parentElement !== target) { target.append(panel); center(true); }
  }
  function render() {
    const item = state(), key = item?.kind === 'song' ? `${item.url}|${item.title}` : item?.kind || '';
    place(); motionState();
    if (key !== itemKey) { itemKey = key; load(item); }
  }
  function resumeFollow() { clearTimeout(browseTimer); browseTimer = null; center(true); }
  const manualScroll = () => {
    if (!timed || !get('lyrics-follow').checked) return;
    clearTimeout(browseTimer);
    browseTimer = setTimeout(resumeFollow, 3000);
  };
  viewport.addEventListener('wheel', manualScroll, { passive: true });
  viewport.addEventListener('touchmove', manualScroll, { passive: true });
  viewport.addEventListener('pointerdown', event => { if (event.target === viewport) manualScroll(); });
  viewport.addEventListener('keydown', event => { if (['ArrowDown', 'ArrowUp', 'PageDown', 'PageUp', 'Home', 'End'].includes(event.key)) manualScroll(); });
  get('lyrics-follow').addEventListener('change', resumeFollow);
  get('lyrics-offset').addEventListener('input', () => { offset = Math.max(-10, Math.min(10, Number(get('lyrics-offset').value) || 0)); update(true); });
  get('lyrics-offset').addEventListener('change', () => { get('lyrics-offset').value = String(offset); });
  get('lyrics-translation').addEventListener('change', draw);
  get('lyrics-retry').addEventListener('click', () => load(state()));
  audio.addEventListener('timeupdate', () => update());
  audio.addEventListener('seeked', () => update(true));
  window.addEventListener('tingjian:layout', place);
  window.addEventListener('resize', () => center(true));
  render();
  return { render };
}

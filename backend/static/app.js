import { createLyricsExperience } from './lyrics.js';
import { createRecommendationExperience } from './recommendations.js';

const $ = id => document.getElementById(id);
const audio = $('audio');
const demo = new URLSearchParams(location.search).get('demo') === '1';
const themes = [
  { name: '午后咖啡', slogan: '忙里偷闲的一杯歌', detail: '轻松 · 慢一点', image: 'coffee' },
  { name: '城市漫游', slogan: '陪你在路上', detail: '流行 · 在路上', image: 'city' },
  { name: '深夜安眠', slogan: '让世界慢下来', detail: '安静 · 好好休息', image: 'night' },
  { name: '怀旧金曲', slogan: '把旧时光唱给你听', detail: '经典 · 旧时光', image: 'stage' },
  { name: '元气早班', slogan: '把好心情叫醒', detail: '轻快 · 新的一天', image: 'forest' },
  { name: '心情小站', slogan: '此刻的你最想听什么', detail: '随心 · 放空一下', image: 'lake' }
];
let selected = themes[0], activeTheme = themes[0];
let queue = [], index = -1, interrupt = null, recent = [];
let playing = false, mode = 'none', textPosition = 0, textDuration = 0;
let timer = null, lastTick = 0, nextSeek = 0, mediaGeneration = 0;
let mediaRetryUsed = false, mediaRetryTimer = null, failedGeneration = -1;
let generation = null, chatRequest = null, retryAction = null;
let programmeVersion = 0;
let muted = false, volume = .75;
let listening, lyrics, recommendations;
let lastRecentItem = null;

function icon(name) {
  const span = document.createElement('span');
  span.className = 'icon';
  span.style.setProperty('--icon', `url(assets/${name}.svg)`);
  span.setAttribute('aria-hidden', 'true');
  return span;
}
function setIcon(id, name) { $(id).style.setProperty('--icon', `url(assets/${name}.svg)`); }
function formatTime(value) {
  const seconds = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}
function current() { return interrupt ? interrupt.items[interrupt.index] : queue[index]; }
function position() { return mode === 'text' ? textPosition : audio.currentTime || 0; }
function notify(message, retry = null) {
  $('notice-text').textContent = message;
  $('notice').hidden = false;
  retryAction = retry;
  $('retry').hidden = !retry;
}
function clearNotice() { $('notice').hidden = true; retryAction = null; }
function normalizeItems(items) {
  if (!Array.isArray(items)) return [];
  return items.filter(item => item && ['song', 'talk', 'text'].includes(item.kind)).map(item => ({
    kind: item.kind,
    title: typeof item.title === 'string' && item.title.trim() ? item.title : item.kind === 'song' ? '未命名歌曲' : '小蓝的口播',
    text: typeof item.text === 'string' ? item.text : '',
    url: typeof item.url === 'string' ? item.url : '',
    recommendation: item.recommendation && typeof item.recommendation.reason === 'string' ? { reason: item.recommendation.reason.slice(0, 300) } : null
  })).filter(item => item.kind !== 'song' || item.url);
}
async function request(path, body, controller) {
  const timeout = setTimeout(() => controller.abort('timeout'), 90000);
  try {
    if (demo) {
      const { respond } = await import('./demo.js');
      return await respond(path, body, controller.signal);
    }
    const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: controller.signal });
    if (!response.ok) {
      const failure = await response.json().catch(() => null);
      throw new Error(response.status >= 500 ? '服务暂时不可用，请稍后重试。' : typeof failure?.detail === 'string' ? failure.detail : `请求未完成（${response.status}），请检查选歌设置。`);
    }
    const result = await response.json();
    if (!result || typeof result !== 'object') throw new Error('服务返回的节目格式不正确。');
    return result;
  } catch (error) {
    if (controller.signal.reason === 'timeout') throw new Error('等待服务响应超时，请重试。');
    if (error instanceof SyntaxError) throw new Error('未收到有效节目，请检查主应用是否已启动。');
    if (error instanceof TypeError) throw new Error('无法连接电台服务，请检查网络后重试。');
    throw error;
  } finally { clearTimeout(timeout); }
}
function renderThemes() {
  $('theme-list').replaceChildren(...themes.map(theme => {
    const button = document.createElement('button');
    button.className = `theme-card${theme === selected ? ' selected' : ''}`;
    button.setAttribute('aria-pressed', String(theme === selected));
    button.setAttribute('aria-label', `选择${theme.name}`);
    const image = document.createElement('img');
    image.src = `assets/${theme.image}.jpg`; image.alt = ''; image.width = 320; image.height = 160;
    const title = document.createElement('strong'); title.textContent = theme.name;
    const subtitle = document.createElement('small'); subtitle.textContent = theme.detail;
    button.append(image, title, subtitle);
    if (theme === selected) { const check = document.createElement('span'); check.className = 'theme-check'; check.append(icon('Check')); button.append(check); }
    button.addEventListener('click', () => selectTheme(theme));
    return button;
  }));
}
function selectTheme(theme) {
  selected = theme;
  $('cover').src = `assets/${theme.image}.jpg`;
  $('cover').alt = `${theme.name}主题封面`;
  $('show-theme').textContent = theme.name;
  $('show-slogan').textContent = theme.slogan;
  renderThemes(); renderPlayback();
}
function renderQueue() {
  const visible = interrupt ? [...interrupt.items.map((item, i) => ({ item, i, inserted: true })), ...queue.map((item, i) => ({ item, i, inserted: false }))] : queue.map((item, i) => ({ item, i, inserted: false }));
  $('queue-empty').hidden = visible.length > 0;
  $('queue-count').textContent = visible.length ? `${queue.filter(item => item.kind === 'song').length} 首歌曲 · ${visible.length} 个片段` : '尚未开播';
  $('queue').replaceChildren(...visible.map(({ item, i, inserted }) => {
    const isCurrent = inserted ? interrupt.index === i : !interrupt && index === i;
    const li = document.createElement('li'); li.className = `queue-item${isCurrent ? ' active' : ''}`;
    const button = document.createElement('button'); button.setAttribute('aria-label', `播放${item.title}`);
    if (isCurrent) button.setAttribute('aria-current', 'true');
    const number = document.createElement('span'); number.className = 'queue-number'; number.textContent = inserted ? '+' : String(i + 1).padStart(2, '0');
    const type = document.createElement('span'); type.className = 'queue-kind'; type.append(icon(item.kind === 'song' ? 'Music2' : 'Mic2'));
    const copy = document.createElement('span'); copy.className = 'queue-copy';
    const title = document.createElement('strong'); title.textContent = item.title;
    const subtitle = document.createElement('small'); subtitle.textContent = inserted ? '互动插播' : item.kind === 'song' ? item.recommendation?.reason || '歌曲' : '小蓝 · 主持人口播'; copy.append(title, subtitle);
    const tail = document.createElement('span'); tail.className = 'queue-tail'; tail.textContent = isCurrent ? playing ? '播放中' : '已暂停' : inserted ? '插播' : String(i + 1).padStart(2, '0');
    button.append(number, type, copy, tail);
    button.addEventListener('click', () => { if (inserted) { interrupt.index = i; } else { interrupt = null; index = i; } activate(); });
    li.append(button); return li;
  }));
}
function renderPlayback() {
  const item = current(), busy = Boolean(generation);
  $('generate').disabled = busy;
  document.querySelectorAll('.theme-card').forEach(button => { button.disabled = busy; });
  $('cancel-generate').hidden = !busy;
  $('listening').classList.toggle('loading', busy);
  $('generate-label').textContent = busy ? '正在编排…' : queue.length ? '生成新一期' : '开始收听';
  $('generate').querySelector('.icon').style.setProperty('--icon', `url(assets/${busy ? 'LoaderCircle' : queue.length ? 'RefreshCw' : 'Play'}.svg)`);
  $('play').disabled = busy && !item;
  const playLabel = item ? playing ? '暂停' : '继续播放' : '开始收听';
  $('play').setAttribute('aria-label', playLabel); $('play').dataset.tip = playLabel;
  setIcon('play-icon', playing ? 'Pause' : 'Play');
  $('previous').disabled = !queue.length && !interrupt;
  $('next').disabled = !item;
  $('stop').disabled = !item && !busy;
  $('track-title').textContent = item ? item.title : queue.length ? '本期已播完' : '还没有开始播放';
  $('track-kind').textContent = item ? `${interrupt ? '互动插播' : item.kind === 'song' ? '歌曲' : '主持人口播'} · ${activeTheme.name}` : `${selected.name} · 小蓝`;
  $('mini-cover').src = `assets/${(item ? activeTheme : selected).image}.jpg`;
  $('transcript').hidden = !item || item.kind === 'song' || !item.text;
  $('transcript-text').textContent = item && item.kind !== 'song' ? item.text : '';
  $('show-status').textContent = busy ? '小蓝正在准备节目' : item && selected !== activeTheme ? `待切换 · 正在收听${activeTheme.name}` : item ? playing ? interrupt ? '互动插播中' : '正在播放' : '已暂停' : queue.length ? '本期已播完' : '准备就绪';
  $('status-dot').classList.toggle('playing', playing);
  $('now-title').textContent = item?.title || selected.name;
  listening?.render();
  lyrics?.render();
  recommendations?.render();
  renderQueue(); renderProgress();
}
function renderProgress() {
  const total = mode === 'text' ? textDuration : Number.isFinite(audio.duration) ? audio.duration : 0;
  const elapsed = current() ? position() : 0;
  $('elapsed').textContent = formatTime(elapsed); $('duration').textContent = formatTime(current() ? total : 0);
  $('seek').disabled = !current() || mode === 'text' || !total;
  $('seek').value = total ? Math.min(1000, elapsed / total * 1000) : 0;
  $('seek').setAttribute('aria-valuetext', `${formatTime(elapsed)} / ${formatTime(total)}`);
  listening?.updatePosition(total, elapsed);
}
function resetMedia() {
  mediaGeneration++;
  clearTimeout(mediaRetryTimer); mediaRetryTimer = null;
  clearInterval(timer); timer = null; mode = 'none'; playing = false;
  audio.pause(); audio.removeAttribute('src'); audio.load();
}
function startText(item, offset, autoplay) {
  mode = 'text'; textDuration = Math.min(18, Math.max(6, item.text.length / 8)); textPosition = Math.min(offset, textDuration); playing = autoplay;
  lastTick = performance.now();
  timer = setInterval(() => { const now = performance.now(); if (playing) textPosition += (now - lastTick) / 1000; lastTick = now; renderProgress(); if (playing && textPosition >= textDuration) advance(); }, 100);
}
function activate(offset = 0, autoplay = true, recovering = false) {
  resetMedia();
  if (!recovering) mediaRetryUsed = false;
  const item = current();
  if (!item) { renderPlayback(); return; }
  if (item.kind === 'text' || (!item.url && item.kind === 'talk')) {
    startText(item, offset, autoplay);
  } else {
    let url;
    try { url = new URL(item.url, location.href); if (!['http:', 'https:', 'blob:'].includes(url.protocol)) throw new Error(); }
    catch { notify('歌曲地址无效，请切换其他片段。'); renderPlayback(); return; }
    if (recovering) { url.searchParams.set('refresh', '1'); url.searchParams.set('_retry', String(Date.now())); }
    mode = 'media'; nextSeek = offset; audio.src = url.href;
    audio.volume = volume; audio.muted = muted;
    if (autoplay) playMedia();
  }
  renderPlayback();
}
function playMedia() {
  const token = mediaGeneration;
  playing = true;
  audio.play().then(() => { if (token === mediaGeneration && mode === 'media') { playing = !audio.paused; renderPlayback(); } }).catch(error => {
    if (token !== mediaGeneration || error.name === 'AbortError') return;
    playing = false;
    if (error.name === 'NotAllowedError') notify('浏览器暂停了自动播放，点击播放继续。');
    else handleMediaError();
    renderPlayback();
  });
}
function pausePlayback() {
  if (mode === 'media') { mediaGeneration++; audio.pause(); }
  playing = false;
  renderPlayback();
}
function togglePlay() {
  clearNotice();
  if (!current()) { if (queue.length) { index = 0; activate(); } else generateShow(); return; }
  if (mode === 'text') { playing = !playing; lastTick = performance.now(); renderPlayback(); }
  else if (mode === 'media') { if (playing) pausePlayback(); else playMedia(); }
  else activate();
}
function advance() {
  if (!current()) return;
  if (interrupt) {
    interrupt.index++;
    if (interrupt.index < interrupt.items.length) { activate(); return; }
    const saved = interrupt; interrupt = null;
    index = saved.originalIndex;
    activate(saved.position, saved.wasPlaying);
    saved.after.forEach(action => action());
    return;
  }
  index++;
  if (index < queue.length) { activate(); return; }
  resetMedia(); renderPlayback();
  if ($('auto').checked) generateShow();
}
function previous() {
  if (interrupt && !queue.length) { interrupt.index = Math.max(0, interrupt.index - 1); activate(); return; }
  interrupt = null;
  if (!queue.length) return;
  index = Math.max(0, Math.min(queue.length - 1, index - 1)); activate();
}
function stop() {
  programmeVersion++;
  generation?.abort(); chatRequest?.abort();
  interrupt = null; queue = []; index = -1; resetMedia(); renderPlayback();
}
function insert(items, after) {
  if (!items.length) { after(); return; }
  if (interrupt) { interrupt.items.push(...items); interrupt.after.push(after); renderPlayback(); return; }
  interrupt = { items, index: 0, originalIndex: index, position: position(), wasPlaying: playing, after: [after] };
  activate();
}
function handleMediaError() {
  if (mode !== 'media' || !current() || failedGeneration === mediaGeneration) return;
  failedGeneration = mediaGeneration;
  const item = current();
  if (item.kind === 'talk' && item.text) {
    resetMedia(); startText(item, 0, true);
    notify('口播音频暂时不可用，正在显示文稿。');
  } else {
    const url = new URL(item.url, location.href);
    if (!mediaRetryUsed && url.origin === location.origin && /\/s\/(joox|netease|id)\/[^/]+\.mp3$/.test(url.pathname)) {
      const offset = position();
      mediaRetryUsed = true;
      resetMedia();
      notify('音源连接中断，正在重新获取可用地址…');
      mediaRetryTimer = setTimeout(() => activate(offset, true, true), 500);
      renderPlayback();
      return;
    }
    audio.pause(); playing = false;
    notify('此音源暂时不可用，已尝试重新连接。可重试或切换下一段。', () => activate(position(), true, true));
  }
  renderPlayback();
}
async function generateShow({ replace = false, seed = '' } = {}) {
  if (generation && !replace) return;
  generation?.abort();
  chatRequest?.abort();
  programmeVersion++;
  clearNotice();
  const controller = new AbortController(), theme = selected;
  generation = controller; renderPlayback();
  try {
    const data = await request('/api/show', { exclude: recent, theme: theme.name, recommendation: recommendations?.request(seed) }, controller);
    if (controller.signal.aborted) return;
    const items = normalizeItems(data.items);
    if (!items.length) throw new Error('这一期还没有可播放的内容，请重试。');
    programmeVersion++;
    chatRequest?.abort();
    interrupt = null; queue = items; index = 0;
    recommendations?.setSummary(data.meta?.recommendation);
    activeTheme = themes.find(item => item.name === data.meta?.theme) || theme;
    selectTheme(activeTheme); activate();
  } catch (error) {
    if (controller.signal.aborted && controller.signal.reason !== 'timeout') return;
    notify(error.message || '节目生成失败，请重试。', () => generateShow({ seed }));
  } finally { if (generation === controller) generation = null; renderPlayback(); }
}
function addMessage(speaker, text, user = false) {
  const entry = document.createElement('div'); entry.className = `chat-entry${user ? ' user' : ''}`;
  const name = document.createElement('span'); name.className = 'speaker'; name.textContent = speaker;
  const body = document.createElement('p'); body.textContent = text;
  entry.append(name, body); $('chat-log').append(entry);
  while ($('chat-log').children.length > 40) $('chat-log').firstChild.remove();
  $('chat-log').scrollTop = $('chat-log').scrollHeight;
  return name;
}
function applyActions(actions) {
  const theme = actions.find(action => action.type === 'play_theme');
  if (theme) { selectTheme(themes.find(item => item.name === theme.theme) || selected); generateShow({ replace: true }); return; }
  for (const action of actions) {
    if (action.type === 'pause') pausePlayback();
    if (action.type === 'resume' && !playing) togglePlay();
    if (action.type === 'next') advance();
    if (action.type === 'prev') previous();
    if (action.type === 'stop') stop();
  }
}
async function sendChat(event, requestedMessage) {
  event?.preventDefault();
  const message = requestedMessage || $('message').value.trim();
  if (!message || chatRequest) return;
  const controller = new AbortController(), version = programmeVersion; chatRequest = controller;
  $('send').disabled = true; $('chat-error').hidden = true; $('chat-status').textContent = '小蓝正在回应…';
  if (requestedMessage) $('library-status').textContent = '小蓝正在处理点播…';
  const label = addMessage('你', message, true);
  try {
    const data = await request('/api/intent', { message, exclude: recent, state: { playing, paused: !playing, current: current()?.title || '', theme: activeTheme.name, auto: $('auto').checked } }, controller);
    if (controller.signal.aborted || version !== programmeVersion) { label.textContent = '你 · 已取消'; return; }
    const items = normalizeItems(data.items), actions = Array.isArray(data.actions) ? data.actions.filter(action => action && typeof action.type === 'string') : [];
    if (!items.length && !actions.length) throw new Error('小蓝暂时没有回应，请再试一次。');
    if (!requestedMessage && $('message').value.trim() === message) $('message').value = '';
    $('message-count').textContent = `${$('message').value.length} / 1000`;
    for (const item of items) addMessage(item.kind === 'song' ? '点歌' : '小蓝', item.kind === 'song' ? item.title : item.text || item.title);
    for (const action of actions) if (action.type === 'set_auto') $('auto').checked = action.on === true;
    insert(items, () => { if (version === programmeVersion) applyActions(actions); });
  } catch (error) {
    label.textContent = controller.signal.aborted && controller.signal.reason !== 'timeout' ? '你 · 已取消' : '你 · 未发送';
    if (controller.signal.aborted && controller.signal.reason !== 'timeout') return;
    $('chat-error').textContent = error.message || '消息发送失败，请重试。'; $('chat-error').hidden = false;
    if (requestedMessage || document.body.classList.contains('focus-mode')) notify(error.message || '点播失败，请重试。');
  } finally { if (chatRequest === controller) chatRequest = null; $('send').disabled = false; $('chat-status').textContent = ''; if (requestedMessage) $('library-status').textContent = ''; }
}

$('today').textContent = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date());
$('demo-badge').hidden = !demo;
$('generate').addEventListener('click', generateShow);
$('cancel-generate').addEventListener('click', () => generation?.abort());
$('play').addEventListener('click', togglePlay);
$('previous').addEventListener('click', previous);
$('next').addEventListener('click', advance);
$('stop').addEventListener('click', stop);
function showLyrics() {
  listening?.setFocus(true);
  $('lyrics-panel').scrollIntoView({ block: 'center', behavior: 'auto' });
  $('lyrics-lines').focus({ preventScroll: true });
  $('lyrics-follow').checked = true;
  $('lyrics-follow').dispatchEvent(new Event('change'));
}
$('lyrics-toggle').addEventListener('click', showLyrics);
$('player-lyric').addEventListener('click', showLyrics);
$('retry').addEventListener('click', () => { const action = retryAction; clearNotice(); action?.(); });
$('dismiss-notice').addEventListener('click', clearNotice);
$('auto').addEventListener('change', () => { if ($('auto').checked && !current() && !generation) generateShow(); });
$('chat-form').addEventListener('submit', sendChat);
$('message').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendChat(); } });
$('message').addEventListener('input', () => { $('message-count').textContent = `${$('message').value.length} / 1000`; });
$('volume').addEventListener('input', event => { volume = Number(event.target.value) / 100; muted = volume === 0; updateVolume(); });
$('mute').addEventListener('click', () => { muted = !muted; if (!muted && !volume) volume = .75; updateVolume(); });
function updateVolume() {
  audio.volume = volume; audio.muted = muted;
  $('volume').value = muted ? 0 : volume * 100;
  $('volume-value').textContent = `${Math.round(muted ? 0 : volume * 100)}%`;
  const label = muted ? '取消静音' : '静音'; $('mute').setAttribute('aria-label', label); $('mute').dataset.tip = label;
  setIcon('volume-icon', muted ? 'VolumeX' : 'Volume2');
}
$('seek').addEventListener('input', event => { if (mode === 'media' && Number.isFinite(audio.duration)) { audio.currentTime = audio.duration * Number(event.target.value) / 1000; renderProgress(); } });
audio.addEventListener('loadedmetadata', () => { if (mode !== 'media') return; if (nextSeek && Number.isFinite(audio.duration)) audio.currentTime = Math.min(nextSeek, Math.max(0, audio.duration - .1)); nextSeek = 0; renderProgress(); });
audio.addEventListener('timeupdate', renderProgress);
audio.addEventListener('ended', () => { if (mode === 'media') advance(); });
audio.addEventListener('error', handleMediaError);
audio.addEventListener('pause', () => { if (mode === 'media' && audio.paused) { playing = false; renderPlayback(); } });
audio.addEventListener('playing', () => {
  if (mode !== 'media' || audio.paused) return;
  playing = true;
  if (mediaRetryUsed && $('notice-text').textContent === '音源连接中断，正在重新获取可用地址…') clearNotice();
  const item = current();
  if (item?.kind === 'song' && item !== lastRecentItem) {
    recent = [...recent.filter(title => title !== item.title), item.title].slice(-30);
    lastRecentItem = item;
  }
  listening?.recordPlay(); renderPlayback();
});
document.querySelectorAll('.nav-link').forEach(link => link.addEventListener('click', () => { document.querySelectorAll('.nav-link').forEach(item => item.classList.toggle('active', item === link)); }));
listening = createListeningExperience({
  demo, icon,
  state: () => ({ item: current(), theme: current() ? activeTheme : selected, playing, mode, busy: Boolean(chatRequest), next: interrupt ? interrupt.items[interrupt.index + 1] || queue[interrupt.originalIndex] : queue[index + 1] }),
  play: () => { if (!playing) togglePlay(); }, pause: pausePlayback, next: advance, previous, stop,
  seek: seconds => { if (mode === 'media' && Number.isFinite(audio.duration)) { audio.currentTime = Math.max(0, Math.min(audio.duration, seconds)); renderProgress(); } },
  replay: title => { if (chatRequest) { notify('小蓝正在回应，请稍后再点播。'); return; } sendChat(undefined, `请播放《${title}》`); },
  notify
});
lyrics = createLyricsExperience({ audio, state: current, demo,
  seek: seconds => { if (mode === 'media' && Number.isFinite(audio.duration)) { audio.currentTime = Math.max(0, Math.min(audio.duration, seconds)); renderProgress(); } }
});
recommendations = createRecommendationExperience({ demo, icon, notify,
  state: () => ({ item: current(), busy: Boolean(generation) }),
  signals: () => listening.recommendationSignals(),
  related: seed => generateShow({ seed })
});
updateVolume(); renderThemes(); renderPlayback();

import { createLyricsExperience } from './lyrics.js?v=20260909-3';
import { createRecommendationExperience } from './recommendations.js?v=20260909-3';
import { createQuietLayout } from './layout.js?v=20260911-1';
const { themes, scheduledTheme } = globalThis.TingjianThemeSchedule;

const $ = id => document.getElementById(id);
const audio = $('audio');
const demo = new URLSearchParams(location.search).get('demo') === '1';
let selected = themes.find(theme => theme.name === document.documentElement.dataset.scheduledTheme) || scheduledTheme(themes);
let activeTheme = selected;
let followSystemTime = true;
let queue = [], index = -1, interrupt = null, recent = [];
let playing = false, mode = 'none', textPosition = 0, textDuration = 0;
let timer = null, lastTick = 0, nextSeek = 0, mediaGeneration = 0;
let mediaRetryUsed = false, mediaRetryTimer = null, failedGeneration = -1;
let recoveryRequest = null, recoveryState = null, consecutiveUnavailable = 0;
let continuationTimer = null, continuityVersion = 0, availabilityRequest = null;
let announcementAudio = null, finishAnnouncement = null, pausedOffset = 0;
let cooldownAudio = null, cooldownRequest = null, finishCooldown = null;
let cooldownItems = [], cooldownIndex = 0;
let quotaUntil = 0, continuationFailure = null, pausedWaiting = false;
let generation = null, chatRequest = null, retryAction = null;
let programmeVersion = 0;
let muted = false, volume = .75;
let relayUrl = '', playbackSession = false, autoplayBlocked = false;
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
function relaySource() {
  if (!relayUrl) {
    // 0.25 秒全零采样 WAV：点击开始时让主音频元素真的播起来一次，
    // 之后在同一个元素上换源续播，后台标签页也不需要新的用户手势。
    const rate = 8000, frames = rate / 4, bytes = new Uint8Array(44 + frames);
    const view = new DataView(bytes.buffer);
    const tag = (offset, text) => [...text].forEach((character, index) => view.setUint8(offset + index, character.charCodeAt(0)));
    tag(0, 'RIFF'); view.setUint32(4, 36 + frames, true); tag(8, 'WAVE'); tag(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, rate, true); view.setUint32(28, rate, true); view.setUint16(32, 1, true); view.setUint16(34, 8, true);
    tag(36, 'data'); view.setUint32(40, frames, true); bytes.fill(128, 44);
    relayUrl = URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }));
  }
  return relayUrl;
}
function stopRelay() { audio.loop = false; }
function releaseAudio() { stopRelay(); audio.pause(); audio.removeAttribute('src'); audio.load(); }
function endPlaybackSession() { playbackSession = false; autoplayBlocked = false; stopRelay(); }
function armRelay() {
  if (!playbackSession) return;
  const relay = relaySource();
  audio.loop = true;
  if (audio.getAttribute('src') !== relay) audio.src = relay;
  if (!audio.paused) return;
  try {
    const pending = audio.play();
    pending?.catch(() => {});
  } catch { /* Older browsers may reject the silent relay synchronously. */ }
}
function primePlayback() {
  playbackSession = true;
  if (mode === 'media' && audio.getAttribute('src')) return;
  armRelay();
}
function normalizeItems(items) {
  if (!Array.isArray(items)) return [];
  return items.filter(item => item && ['song', 'talk', 'text'].includes(item.kind)).map(item => ({
    kind: item.kind,
    title: typeof item.title === 'string' && item.title.trim() ? item.title : item.kind === 'song' ? '未命名歌曲' : '小蓝的口播',
    text: typeof item.text === 'string' ? item.text : '',
    url: typeof item.url === 'string' ? item.url : '',
    source: typeof item.source === 'string' ? item.source : '',
    id: item.id == null ? '' : String(item.id),
    artist: typeof item.artist === 'string' ? item.artist : '',
    lyric_id: item.lyric_id == null ? '' : String(item.lyric_id),
    lyric_title: typeof item.lyric_title === 'string' ? item.lyric_title : '',
    requested: item.requested === true,
    recommendation: item.recommendation && typeof item.recommendation.reason === 'string' ? { reason: item.recommendation.reason.slice(0, 300) } : null
  })).filter(item => item.kind !== 'song' || item.url);
}
async function request(path, body, controller) {
  const timeout = setTimeout(() => controller.abort('timeout'), path === '/api/playback/resolve' ? 60000 : 240000);
  try {
    if (demo) {
      const { respond } = await import('./demo.js?v=20260909-3');
      return await respond(path, body, controller.signal);
    }
    const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: controller.signal });
    if (!response.ok) {
      const failure = await response.json().catch(() => null);
      const detail = failure?.detail;
      const error = new Error(typeof detail?.notice === 'string' ? detail.notice : typeof detail === 'string' ? detail : '服务暂时不可用，将自动继续收听。');
      error.status = detail?.status || (response.status === 429 ? 'limited' : 'temporary');
      error.retry_after = detail?.retry_after;
      throw error;
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
    button.addEventListener('click', () => selectTheme(theme, true));
    return button;
  }));
}
function selectTheme(theme, manual = false) {
  if (manual) followSystemTime = false;
  selected = theme;
  $('cover').src = `assets/${theme.image}.jpg`;
  $('cover').alt = `${theme.name}主题封面`;
  $('show-theme').textContent = theme.name;
  $('show-slogan').textContent = theme.slogan;
  renderThemes(); renderPlayback();
}
function syncThemeWithSystemTime() {
  if (!followSystemTime) return;
  const next = scheduledTheme(themes);
  if (next !== selected) selectTheme(next);
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
    const subtitle = document.createElement('small'); subtitle.textContent = item.unavailable ? '音源暂不可用 · 点击重新检索' : inserted ? '互动插播' : item.kind === 'song' ? item.recommendation?.reason || '歌曲' : '小蓝 · 主持人口播'; copy.append(title, subtitle);
    const tail = document.createElement('span'); tail.className = 'queue-tail'; tail.textContent = isCurrent ? playing ? '播放中' : '已暂停' : inserted ? '插播' : String(i + 1).padStart(2, '0');
    button.append(number, type, copy, tail);
    button.addEventListener('click', () => { if (inserted) { interrupt.index = i; } else { interrupt = null; index = i; } activate(); });
    li.append(button); return li;
  }));
}
function renderPlayback() {
  const item = current(), busy = Boolean(generation);
  document.body.classList.toggle('has-programme', queue.length > 0 || Boolean(item));
  document.body.classList.toggle('has-song', item?.kind === 'song');
  document.body.classList.toggle('has-current', Boolean(item));
  document.body.classList.toggle('preparing-programme', busy);
  document.body.dataset.playbackState = busy && !item ? 'preparing' : mode === 'waiting' || pausedWaiting ? 'waiting' : ['recovering', 'announcement', 'cooldown'].includes(mode) ? 'recovering' : item && playing ? 'playing' : item ? 'paused' : queue.length ? 'complete' : 'idle';
  $('generate').disabled = busy;
  document.querySelectorAll('.theme-card').forEach(button => { button.disabled = busy; });
  $('cancel-generate').hidden = !busy;
  $('listening').classList.toggle('loading', busy);
  $('generate-label').textContent = busy ? '正在编排…' : queue.length || item ? '生成新一期' : '开始收听';
  $('generate').dataset.tip = $('generate-label').textContent;
  $('generate').setAttribute('aria-label', $('generate-label').textContent);
  $('generate').querySelector('.icon').style.setProperty('--icon', `url(assets/${busy ? 'LoaderCircle' : queue.length || item ? 'RefreshCw' : 'Play'}.svg)`);
  $('play').disabled = busy && !item;
  const playLabel = playing ? '暂停' : item || pausedWaiting ? '继续播放' : '开始收听';
  $('play').setAttribute('aria-label', playLabel); $('play').dataset.tip = playLabel;
  setIcon('play-icon', playing ? 'Pause' : 'Play');
  $('previous').disabled = !queue.length && !interrupt;
  $('next').disabled = !item;
  $('stop').disabled = !item && !busy && !playing && !pausedWaiting;
  $('track-title').textContent = item ? item.title : queue.length ? '本期已播完' : '还没有开始播放';
  $('track-kind').textContent = item ? item.kind === 'song' ? `${item.artist || '在线音乐'} · ${activeTheme.name}` : `小蓝 · ${activeTheme.name}` : queue.length ? `小蓝 · 本期已播完` : '小蓝 · 等待开播';
  $('mini-cover').src = `assets/${(item ? activeTheme : selected).image}.jpg`;
  $('transcript').hidden = !item || item.kind === 'song' || !item.text;
  $('transcript-text').textContent = item && item.kind !== 'song' ? item.text : '';
  $('show-status').textContent = busy ? '小蓝正在准备节目' : mode === 'cooldown' ? '小蓝陪你聊一会儿' : mode === 'waiting' ? '等待自动续播' : mode === 'announcement' ? '小蓝正在提醒' : item && selected !== activeTheme ? `待切换 · 正在收听${activeTheme.name}` : item ? playing ? interrupt ? '互动插播中' : '正在播放' : '已暂停' : pausedWaiting ? '已暂停自动续播' : queue.length ? '本期已播完' : '准备就绪';
  $('show-theme').textContent = (item ? activeTheme : selected).detail;
  $('status-dot').classList.toggle('playing', playing);
  $('now-title').textContent = item?.title || selected.name;
  $('now-title').title = $('now-title').textContent;
  listening?.render();
  lyrics?.render();
  recommendations?.render();
  renderQueue(); renderProgress();
}
function renderProgress() {
  const active = mode === 'text' || mode === 'media';
  const total = mode === 'text' ? textDuration : mode === 'media' && Number.isFinite(audio.duration) ? audio.duration : 0;
  const elapsed = current() && active ? position() : 0;
  $('elapsed').textContent = formatTime(elapsed); $('duration').textContent = formatTime(current() ? total : 0);
  $('seek').disabled = !current() || mode !== 'media' || !total;
  $('seek').value = total ? Math.min(1000, elapsed / total * 1000) : 0;
  $('seek').setAttribute('aria-valuetext', `${formatTime(elapsed)} / ${formatTime(total)}`);
  listening?.updatePosition(total, elapsed);
}
function cancelRecovery() {
  if (recoveryState && retryAction) clearNotice();
  recoveryRequest?.abort(); recoveryRequest = null; recoveryState = null;
  if (['音源连接中断，正在重新获取可用地址…', '正在检索其他渠道的匹配音源…', '已找到其他渠道音源，正在连接…'].includes($('notice-text').textContent)) clearNotice();
  clearTimeout(mediaRetryTimer); mediaRetryTimer = null;
}
function cancelContinuation() {
  continuityVersion++;
  clearTimeout(continuationTimer); continuationTimer = null;
  availabilityRequest?.abort(); availabilityRequest = null;
  cooldownRequest?.abort(); cooldownRequest = null;
  finishAnnouncement?.(false);
  finishCooldown?.(false);
  cooldownItems = []; cooldownIndex = 0;
}
function failureReason(status) {
  return ['unavailable', 'limited'].includes(status) ? status : 'temporary';
}
function rememberFailure(status, retryAfter) {
  status = failureReason(status);
  if (status === 'limited') quotaUntil = Math.max(quotaUntil, Date.now() + Math.max(1, Number(retryAfter) || 300) * 1000);
  continuationFailure = { status, retry_after: retryAfter };
  return status;
}
function announce(reason, message) {
  const token = continuityVersion;
  return new Promise(resolve => {
    let settled = false, fallbackStarted = false, timeout;
    const clip = new Audio(`/api/playback/announcement/${reason}.mp3`);
    announcementAudio = clip;
    clip.volume = volume; clip.muted = muted;
    const finish = completed => {
      if (settled) return;
      settled = true; clearTimeout(timeout);
      clip.onended = null; clip.onerror = null;
      clip.pause(); clip.removeAttribute('src'); clip.load();
      window.speechSynthesis?.cancel();
      if (announcementAudio === clip) announcementAudio = null;
      if (finishAnnouncement === finish) finishAnnouncement = null;
      resolve(completed && token === continuityVersion);
    };
    finishAnnouncement = finish;
    const fallback = () => {
      if (settled || fallbackStarted) return;
      fallbackStarted = true;
      clip.pause(); clip.removeAttribute('src'); clip.load();
      clearTimeout(timeout);
      timeout = setTimeout(() => finish(true), 20000);
      if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) { finish(true); return; }
      const speech = new SpeechSynthesisUtterance(message);
      speech.lang = 'zh-CN'; speech.volume = muted ? 0 : volume;
      speech.onend = () => finish(true); speech.onerror = () => finish(true);
      window.speechSynthesis.speak(speech);
    };
    clip.onended = () => finish(true); clip.onerror = fallback;
    timeout = setTimeout(fallback, 15000);
    clip.play().catch(fallback);
  });
}
async function failureAndContinue(status, notice, retryAfter) {
  status = rememberFailure(status, retryAfter);
  resetMedia();
  const token = continuityVersion;
  const message = notice || (status === 'limited' ? '音源服务暂时限流，将尝试下一首可用推荐。' : status === 'unavailable' ? '未找到可用的匹配音源，将继续下一首推荐。' : '音源服务暂时连接失败，将继续下一首推荐。');
  notify(message); addMessage('小蓝', message);
  mode = 'announcement'; playing = true; renderPlayback();
  if (await announce(status, message) && token === continuityVersion) {
    if (current()) advance(true, true);
    else scheduleRecommendation();
  }
}

function shuffleCooldownItems(items, previousId = '') {
  const shuffled = [...items];
  for (let i = shuffled.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [shuffled[i], shuffled[j]] = [shuffled[j], shuffled[i]];
  }
  if (shuffled.length > 1 && shuffled[0].id === previousId) [shuffled[0], shuffled[1]] = [shuffled[1], shuffled[0]];
  return shuffled;
}

function orderCooldownItems(items, previousId = '') {
  const hour = new Date().getHours();
  const localPeriod = hour >= 5 && hour < 12 ? 'morning' : hour >= 18 || hour < 5 ? 'evening' : '';
  const ordered = shuffleCooldownItems(items.filter(item => item.period === 'any'), previousId);
  const seasonal = localPeriod ? shuffleCooldownItems(items.filter(item => item.period === localPeriod), previousId) : [];
  for (const item of seasonal) ordered.splice(Math.floor(Math.random() * (Math.min(ordered.length, 2) + 1)), 0, item);
  if (ordered.length > 1 && ordered[0].id === previousId) [ordered[0], ordered[1]] = [ordered[1], ordered[0]];
  return ordered;
}

function playCooldownItem(item, token) {
  return new Promise(resolve => {
    let settled = false, fallbackStarted = false, timeout;
    const clip = new Audio(item.url);
    cooldownAudio = clip;
    clip.volume = volume; clip.muted = muted;
    const finish = completed => {
      if (settled) return;
      settled = true; clearTimeout(timeout);
      clip.onended = null; clip.onerror = null;
      clip.pause(); clip.removeAttribute('src'); clip.load();
      window.speechSynthesis?.cancel();
      if (cooldownAudio === clip) cooldownAudio = null;
      if (finishCooldown === finish) finishCooldown = null;
      resolve(completed && token === continuityVersion);
    };
    finishCooldown = finish;
    const fallback = () => {
      if (settled || fallbackStarted) return;
      fallbackStarted = true;
      clip.pause(); clip.removeAttribute('src'); clip.load();
      clearTimeout(timeout);
      timeout = setTimeout(() => finish(true), 45000);
      if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) { finish(true); return; }
      const speech = new SpeechSynthesisUtterance(item.text);
      speech.lang = 'zh-CN'; speech.volume = muted ? 0 : volume;
      speech.onend = () => finish(true); speech.onerror = () => finish(true);
      window.speechSynthesis.speak(speech);
    };
    clip.onended = () => finish(true); clip.onerror = fallback;
    timeout = setTimeout(fallback, 90000);
    clip.play().catch(fallback);
  });
}

async function playCooldownContent(token) {
  const controller = new AbortController(); cooldownRequest = controller;
  const timeout = setTimeout(() => controller.abort('timeout'), 10000);
  try {
    const response = await fetch('/api/playback/cooldown/content.json', { signal: controller.signal });
    if (!response.ok) throw new Error('cooldown manifest');
    const data = await response.json();
    if (token !== continuityVersion) return;
    const validItems = Array.isArray(data.items) ? data.items.flatMap(item => {
      if (!item || typeof item.id !== 'string' || typeof item.title !== 'string' || typeof item.url !== 'string' || typeof item.text !== 'string' || !['any', 'morning', 'evening'].includes(item.period)) return [];
      try {
        const url = new URL(item.url, location.href);
        if (url.origin !== location.origin || !url.pathname.startsWith('/api/playback/cooldown/') || !url.pathname.endsWith('.mp3')) return [];
        return [{ ...item, url: url.href }];
      } catch { return []; }
    }) : [];
    cooldownItems = orderCooldownItems(validItems);
    if (!cooldownItems.length) throw new Error('empty cooldown manifest');
    cooldownIndex = 0;
    while (token === continuityVersion && quotaUntil - Date.now() >= 6000) {
      if (cooldownIndex >= cooldownItems.length) {
        cooldownItems = orderCooldownItems(cooldownItems, cooldownItems.at(-1)?.id || '');
        cooldownIndex = 0;
      }
      mode = 'cooldown'; playing = true;
      const item = cooldownItems[cooldownIndex];
      cooldownIndex++; notify(`${item.title} · 音乐将在额度恢复后自动继续。`); renderPlayback();
      if (!await playCooldownItem(item, token)) return;
    }
  } catch {
    if (token !== continuityVersion || controller.signal.aborted && controller.signal.reason !== 'timeout') return;
    mode = 'waiting'; playing = true; renderPlayback();
    await announce('waiting', '音源请求额度正在恢复，我们稍微聊一会儿，音乐随后继续。');
  } finally {
    clearTimeout(timeout);
    if (cooldownRequest === controller) cooldownRequest = null;
  }
}

async function scheduleRecommendation(delay = null) {
  cancelContinuation();
  const token = continuityVersion;
  const status = continuationFailure?.status || 'temporary';
  const remaining = Math.max(0, quotaUntil - Date.now());
  const wait = Math.max(remaining, delay ?? (status === 'unavailable' ? 30000 : status === 'temporary' ? 15000 : 0));
  mode = 'waiting'; playing = true;
  notify(remaining > 0 ? `音源请求额度暂未恢复，约 ${Math.ceil(wait / 1000)} 秒后自动继续。` : `正在等待音源恢复，约 ${Math.max(1, Math.ceil(wait / 1000))} 秒后自动推荐下一首。`);
  renderPlayback();
  if (remaining > 0) playCooldownContent(token);
  continuationTimer = setTimeout(async () => {
    if (token !== continuityVersion) return;
    finishCooldown?.(false);
    finishAnnouncement?.(false);
    cooldownRequest?.abort(); cooldownRequest = null;
    const controller = new AbortController(); availabilityRequest = controller;
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch('/api/playback/availability', { signal: controller.signal });
      if (!response.ok) throw new Error('availability');
      const data = await response.json();
      if (token !== continuityVersion) return;
      if (data.status === 'limited') {
        rememberFailure('limited', data.retry_after);
        notify('音源请求额度暂未恢复，将在允许访问后自动继续。');
        scheduleRecommendation();
      } else if (data.status === 'ready') generateShow();
      else {
        rememberFailure('temporary', data.retry_after);
        scheduleRecommendation(Math.max(15000, (Number(data.retry_after) || 0) * 1000));
      }
    } catch {
      if (token === continuityVersion) scheduleRecommendation(15000);
    } finally {
      clearTimeout(timeout);
      if (availabilityRequest === controller) availabilityRequest = null;
    }
  }, Math.max(1000, wait));
}
function resetMedia(preserveRecovery = false) {
  if (!preserveRecovery) { cancelRecovery(); cancelContinuation(); }
  mediaGeneration++;
  clearTimeout(mediaRetryTimer); mediaRetryTimer = null;
  clearInterval(timer); timer = null; mode = 'none'; playing = false;
  autoplayBlocked = false;
  if (playbackSession) armRelay();
  else releaseAudio();
}
function startText(item, offset, autoplay) {
  mode = 'text'; textDuration = Math.min(18, Math.max(6, item.text.length / 8)); textPosition = Math.min(offset, textDuration); playing = autoplay;
  lastTick = performance.now();
  timer = setInterval(() => { const now = performance.now(); if (playing) textPosition += (now - lastTick) / 1000; lastTick = now; renderProgress(); if (playing && textPosition >= textDuration) advance(); }, 100);
}
function activate(offset = 0, autoplay = true, recovering = false, refresh = false) {
  // 恢复到暂停状态时不需要静音接力，避免后台无声空转。
  if (!autoplay) endPlaybackSession();
  resetMedia(recovering);
  pausedOffset = offset; pausedWaiting = false;
  lyrics?.resume();
  if (!recovering) mediaRetryUsed = false;
  const item = current();
  if (!item) { renderPlayback(); return; }
  if (item.kind === 'text' || (!item.url && item.kind === 'talk')) {
    startText(item, offset, autoplay);
  } else {
    let url;
    try { url = new URL(item.url, location.href); if (!['http:', 'https:', 'blob:'].includes(url.protocol)) throw new Error(); }
    catch { failureAndContinue('temporary', '这段音频地址无效，将继续下一首推荐。'); return; }
    if (item.kind === 'song' && url.origin === location.origin && /\/s\/[^/]+\/[^/]+\.mp3$/.test(url.pathname)) url.searchParams.set('stream', '1');
    if (item.kind === 'song' && (audio.captureStream || audio.mozCaptureStream)) audio.crossOrigin = 'anonymous';
    else audio.removeAttribute('crossorigin');
    if (refresh) { url.searchParams.set('refresh', '1'); url.searchParams.set('_retry', String(Date.now())); }
    mode = 'media'; nextSeek = offset; stopRelay(); audio.src = url.href;
    updateVolume();
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
    if (error.name === 'NotAllowedError') {
      autoplayBlocked = true;
      notify('浏览器拦截了自动播放，回到本页会自动重试。');
    }
    else handleMediaError();
    renderPlayback();
  });
}
function pausePlayback() {
  if (mode === 'media' || mode === 'text') pausedOffset = position();
  pausedWaiting = !current() && ['waiting', 'announcement', 'cooldown'].includes(mode);
  programmeVersion++;
  generation?.abort(); generation = null;
  chatRequest?.abort(); chatRequest = null;
  endPlaybackSession();
  resetMedia();
  lyrics?.suspend();
  updateChatComposer();
  renderPlayback();
}
function togglePlay() {
  clearNotice();
  if (playing) { pausePlayback(); return; }
  if (pausedWaiting) { pausedWaiting = false; scheduleRecommendation(); return; }
  if (quotaUntil > Date.now() && !current()) { scheduleRecommendation(0); return; }
  if (!current()) { if (queue.length) { index = 0; activate(); } else generateShow(); return; }
  if (mode === 'text') { playing = !playing; lastTick = performance.now(); renderPlayback(); }
  else if (mode === 'media') { if (playing) pausePlayback(); else playMedia(); }
  else activate(pausedOffset);
}
function advance(allowAuto = true, recovering = false) {
  if (!current()) { if (recovering) scheduleRecommendation(); return; }
  if (interrupt) {
    interrupt.index++;
    if (interrupt.index < interrupt.items.length) { activate(); return; }
    const saved = interrupt; interrupt = null;
    index = saved.originalIndex;
    activate(saved.position, saved.wasPlaying);
    saved.after.forEach(action => action());
    if (recovering && !current()) scheduleRecommendation();
    return;
  }
  index++;
  if (index < queue.length) { activate(); return; }
  const continues = recovering || ($('auto').checked && allowAuto);
  if (!continues) endPlaybackSession();
  resetMedia(); renderPlayback();
  if (recovering) scheduleRecommendation();
  else if (continues) {
    if (quotaUntil > Date.now()) scheduleRecommendation(0);
    else generateShow();
  }
}
function previous() {
  if (interrupt && !queue.length) { interrupt.index = Math.max(0, interrupt.index - 1); activate(); return; }
  interrupt = null;
  if (!queue.length) return;
  index = Math.max(0, Math.min(queue.length - 1, index - 1)); activate();
}
function stop() {
  programmeVersion++;
  generation?.abort(); generation = null; chatRequest?.abort(); chatRequest = null;
  interrupt = null; queue = []; index = -1; pausedWaiting = false; pausedOffset = 0;
  endPlaybackSession(); resetMedia(); renderPlayback();
  lyrics?.suspend(); updateChatComposer();
}
function insert(items, after) {
  if (!items.length) {
    after();
    // 纯文字回复不会接上播放：结束静音接力，避免音频元素在后台无声空转。
    if (playbackSession && mode === 'none' && !current() && !generation) { endPlaybackSession(); releaseAudio(); renderPlayback(); }
    return;
  }
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
  } else if (item.kind !== 'song') {
    failureAndContinue('temporary', '这段口播暂时无法播放，将继续下一首推荐。');
  } else {
    const url = new URL(item.url, location.href);
    if (!recoveryState || recoveryState.item !== item) recoveryState = { item, exclude: [], offset: position() };
    else recoveryState.offset = Math.max(recoveryState.offset, position());
    if (!mediaRetryUsed && url.origin === location.origin && /\/s\/[^/]+\/[^/]+\.mp3$/.test(url.pathname)) {
      const offset = position();
      mediaRetryUsed = true;
      resetMedia(true);
      mode = 'recovering'; playing = true;
      notify('音源连接中断，正在重新获取可用地址…');
      mediaRetryTimer = setTimeout(() => activate(offset, true, true, true), 500);
      renderPlayback();
      return;
    }
    recoverSong();
  }
  renderPlayback();
}
function songIdentity(item) {
  if (item.source && item.id) return { source: item.source === 'id' ? 'netease' : item.source, id: item.id };
  try {
    const match = new URL(item.url, location.href).pathname.match(/\/s\/([^/]+)\/([^/]+)\.mp3$/);
    if (match) return { source: match[1] === 'id' ? 'netease' : match[1], id: decodeURIComponent(decodeURIComponent(match[2])) };
  } catch { /* A malformed address still permits recovery by song title. */ }
  return null;
}
async function recoverSong() {
  const item = current();
  if (item?.kind !== 'song' || recoveryRequest) return;
  const state = recoveryState?.item === item ? recoveryState : { item, exclude: [], offset: position() };
  recoveryState = state;
  const identity = songIdentity(item);
  if (identity && !state.exclude.some(candidate => candidate.source === identity.source && candidate.id === identity.id)) state.exclude.push(identity);
  resetMedia(true);
  const token = mediaGeneration, controller = new AbortController(); recoveryRequest = controller;
  mode = 'recovering'; playing = true;
  notify('正在检索其他渠道的匹配音源…'); renderPlayback();
  try {
    const data = await request('/api/playback/resolve', { title: item.title, artist: item.artist, ...identity, exclude: state.exclude }, controller);
    if (controller.signal.aborted || token !== mediaGeneration || current() !== item) return;
    if (data.status === 'available') {
      const replacement = normalizeItems([data.item])[0], replacementId = replacement && songIdentity(replacement);
      if (!replacement || replacement.kind !== 'song' || replacement.url === item.url || (replacementId && state.exclude.some(candidate => candidate.source === replacementId.source && candidate.id === replacementId.id))) {
        await failureAndContinue('temporary', '音源检索暂未完成，将继续下一首推荐。'); return;
      }
      Object.assign(item, replacement, { requested: item.requested || replacement.requested, recommendation: replacement.recommendation || item.recommendation, unavailable: false });
      mediaRetryUsed = true;
      notify('已找到其他渠道音源，正在连接…');
      activate(state.offset, true, true);
    } else if (data.status === 'unavailable') {
      item.unavailable = true; consecutiveUnavailable++;
      await failureAndContinue('unavailable', `《${item.title}》未找到可用的匹配音源，将继续下一首推荐。`);
    } else {
      await failureAndContinue(data.status, data.notice, data.retry_after);
    }
  } catch (error) {
    if (token !== mediaGeneration || current() !== item || (controller.signal.aborted && controller.signal.reason !== 'timeout')) return;
    await failureAndContinue(error.status || 'temporary', error.message, error.retry_after);
  } finally { if (recoveryRequest === controller) recoveryRequest = null; renderPlayback(); }
}
async function generateShow({ replace = false, seed = '' } = {}) {
  if (generation && !replace) return;
  if (quotaUntil > Date.now()) {
    if (current()) await failureAndContinue('limited', '音源请求额度暂未恢复，将尝试下一首可用推荐。', Math.ceil((quotaUntil - Date.now()) / 1000));
    else scheduleRecommendation(0);
    return;
  }
  generation?.abort();
  chatRequest?.abort();
  cancelRecovery(); cancelContinuation();
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
    if (typeof data.notice === 'string' && data.notice) notify(data.notice);
  } catch (error) {
    if (controller.signal.aborted && controller.signal.reason !== 'timeout') return;
    // Release the generation guard before the automatic continuation is armed.
    if (generation === controller) generation = null;
    await failureAndContinue(error.status || 'temporary', error.message || '节目暂未生成，将自动继续推荐。', error.retry_after);
  } finally { if (generation === controller) generation = null; renderPlayback(); }
}
function addMessage(speaker, text, user = false) {
  const entry = document.createElement('div'); entry.className = `chat-entry${user ? ' user' : speaker === '点歌' ? ' song' : ''}`;
  const name = document.createElement('span'); name.className = 'speaker'; name.textContent = speaker;
  if (!user) name.prepend(icon(speaker === '点歌' ? 'Music2' : 'Mic2'));
  const body = document.createElement('p'); body.textContent = text;
  entry.append(name, body); $('chat-log').append(entry);
  while ($('chat-log').querySelectorAll('.chat-entry').length > 40) $('chat-log').querySelector('.chat-entry').remove();
  $('chat-log').scrollTop = $('chat-log').scrollHeight;
  return name;
}
function updateChatComposer() {
  const input = $('message'), busy = Boolean(chatRequest);
  $('message-count').textContent = `${input.value.length} / 1000`;
  $('send').disabled = busy || !input.value.trim();
  $('chat-form').setAttribute('aria-busy', String(busy));
  const label = busy ? '正在发送' : '发送给小蓝';
  $('send').setAttribute('aria-label', label); $('send').dataset.tip = label;
  setIcon('send-icon', busy ? 'LoaderCircle' : 'Send');
  if (input.clientWidth) {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, parseFloat(getComputedStyle(input).maxHeight))}px`;
  }
}
function applyActions(actions) {
  const theme = actions.find(action => action.type === 'play_theme');
  if (theme) { selectTheme(themes.find(item => item.name === theme.theme) || selected, true); generateShow({ replace: true }); return; }
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
  $('chat-error').hidden = true; $('chat-status').textContent = '小蓝正在回应…';
  updateChatComposer();
  if (requestedMessage) $('library-status').textContent = '小蓝正在处理点播…';
  const label = addMessage('你', message, true);
  try {
    const data = await request('/api/intent', { message, exclude: recent, state: { playing, paused: !playing, current: current()?.title || '', theme: activeTheme.name, auto: $('auto').checked } }, controller);
    if (controller.signal.aborted || version !== programmeVersion) { label.textContent = '你 · 已取消'; return; }
    const items = normalizeItems(data.items), actions = Array.isArray(data.actions) ? data.actions.filter(action => action && typeof action.type === 'string') : [];
    const notice = typeof data.notice === 'string' ? data.notice.trim() : '';
    if (!items.length && !actions.length && !notice) throw new Error('小蓝暂时没有回应，请再试一次。');
    if (!requestedMessage && $('message').value.trim() === message) $('message').value = '';
    updateChatComposer();
    for (const item of items) addMessage(item.kind === 'song' ? '点歌' : '小蓝', item.kind === 'song' ? item.title : item.text || item.title);
    if (notice) {
      if (!['unavailable', 'limited', 'temporary'].includes(data.availability) && !items.some(item => item.kind !== 'song' && item.text === notice)) addMessage('小蓝', notice);
      notify(notice);
    }
    for (const action of actions) if (action.type === 'set_auto') $('auto').checked = action.on === true;
    if (['unavailable', 'limited', 'temporary'].includes(data.availability)) {
      await failureAndContinue(data.availability, notice, data.retry_after);
    } else insert(items, () => { if (version === programmeVersion) applyActions(actions); });
  } catch (error) {
    label.textContent = controller.signal.aborted && controller.signal.reason !== 'timeout' ? '你 · 已取消' : '你 · 未发送';
    if (controller.signal.aborted && controller.signal.reason !== 'timeout') return;
    $('chat-error').textContent = error.message || '消息发送失败，请重试。'; $('chat-error').hidden = false;
    await failureAndContinue(error.status || 'temporary', error.message || '点播服务暂时连接失败，将继续下一首推荐。', error.retry_after);
  } finally { if (chatRequest === controller) chatRequest = null; updateChatComposer(); $('chat-status').textContent = ''; if (requestedMessage) $('library-status').textContent = ''; }
}

$('today').textContent = new Intl.DateTimeFormat('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' }).format(new Date());
$('demo-badge').hidden = !demo;
$('generate').addEventListener('click', () => { primePlayback(); generateShow(); });
$('cancel-generate').addEventListener('click', pausePlayback);
$('play').addEventListener('click', () => { if (!playing && !audio.getAttribute('src')) primePlayback(); togglePlay(); });
$('previous').addEventListener('click', previous);
$('next').addEventListener('click', advance);
$('stop').addEventListener('click', stop);
function showLyrics() {
  window.dispatchEvent(new Event('tingjian:show-lyrics'));
  $('lyrics-lines').focus({ preventScroll: true });
  $('lyrics-follow').checked = true;
  $('lyrics-follow').dispatchEvent(new Event('change'));
}
$('lyrics-toggle').addEventListener('click', showLyrics);
$('player-lyric').addEventListener('click', showLyrics);
$('retry').addEventListener('click', () => { const action = retryAction; clearNotice(); primePlayback(); action?.(); });
$('dismiss-notice').addEventListener('click', clearNotice);
$('auto').addEventListener('change', () => { if ($('auto').checked) primePlayback(); if ($('auto').checked && !current() && !generation) generateShow(); });
$('chat-form').addEventListener('submit', event => { primePlayback(); sendChat(event); });
$('message').addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendChat(); } });
$('message').addEventListener('input', updateChatComposer);
new ResizeObserver(updateChatComposer).observe($('message').parentElement);
$('volume').addEventListener('input', event => { volume = Number(event.target.value) / 100; muted = volume === 0; updateVolume(); });
$('mute').addEventListener('click', () => { muted = !muted; if (!muted && !volume) volume = .75; updateVolume(); });
function updateVolume() {
  // Narration is mastered to -14 LUFS; trim the louder online music sources.
  audio.volume = volume * (current()?.kind === 'song' ? .85 : 1); audio.muted = muted;
  if (announcementAudio) { announcementAudio.volume = volume; announcementAudio.muted = muted; }
  if (cooldownAudio) { cooldownAudio.volume = volume; cooldownAudio.muted = muted; }
  $('volume').value = muted ? 0 : volume * 100;
  $('volume-value').textContent = `${Math.round(muted ? 0 : volume * 100)}%`;
  const label = muted ? '取消静音' : '静音'; $('mute').setAttribute('aria-label', label); $('mute').dataset.tip = label;
  setIcon('volume-icon', muted ? 'VolumeX' : 'Volume2');
}
function adjustVolume(delta) {
  if (muted && delta > 0) muted = false;
  else if (!muted) volume = Math.max(0, Math.min(1, volume + delta));
  muted = volume === 0;
  updateVolume();
}
$('seek').addEventListener('input', event => { if (mode === 'media' && Number.isFinite(audio.duration)) { audio.currentTime = audio.duration * Number(event.target.value) / 1000; renderProgress(); } });
audio.addEventListener('loadedmetadata', () => { if (mode !== 'media') return; if (nextSeek && Number.isFinite(audio.duration)) audio.currentTime = Math.min(nextSeek, Math.max(0, audio.duration - .1)); nextSeek = 0; renderProgress(); });
audio.addEventListener('timeupdate', renderProgress);
audio.addEventListener('ended', () => { if (mode === 'media') advance(); });
audio.addEventListener('error', handleMediaError);
audio.addEventListener('pause', () => { if (mode === 'media' && audio.paused) { playing = false; renderPlayback(); } });
audio.addEventListener('playing', () => {
  if (mode !== 'media' || audio.paused) return;
  playing = true; autoplayBlocked = false;
  const notice = $('notice-text').textContent;
  if (notice === '浏览器拦截了自动播放，回到本页会自动重试。' || mediaRetryUsed && ['音源连接中断，正在重新获取可用地址…', '已找到其他渠道音源，正在连接…'].includes(notice)) clearNotice();
  const item = current();
  if (item?.kind === 'song') { consecutiveUnavailable = 0; item.unavailable = false; }
  if (item?.kind === 'song' && item !== lastRecentItem) {
    recent = [...recent.filter(title => title !== item.title), item.title].slice(-30);
    lastRecentItem = item;
  }
  listening?.recordPlay(); renderPlayback();
});
window.addEventListener('pagehide', pausePlayback);
document.querySelectorAll('.nav-link').forEach(link => link.addEventListener('click', () => { document.querySelectorAll('.nav-link').forEach(item => item.classList.toggle('active', item === link)); }));
listening = createListeningExperience({
  demo, icon,
  state: () => ({ item: current(), theme: current() ? activeTheme : selected, playing, mode, busy: Boolean(chatRequest), next: interrupt ? interrupt.items[interrupt.index + 1] || queue[interrupt.originalIndex] : queue[index + 1] }),
  play: () => { if (!playing) togglePlay(); }, pause: pausePlayback, next: advance, previous, stop,
  seek: seconds => { if (mode === 'media' && Number.isFinite(audio.duration)) { audio.currentTime = Math.max(0, Math.min(audio.duration, seconds)); renderProgress(); } },
  replay: title => { if (chatRequest) { notify('小蓝正在回应，请稍后再点播。'); return; } sendChat(undefined, `请播放《${title}》`); },
  notify, adjustVolume
});
lyrics = createLyricsExperience({ audio, state: current, demo,
  seek: seconds => { if (mode === 'media' && Number.isFinite(audio.duration)) { audio.currentTime = Math.max(0, Math.min(audio.duration, seconds)); renderProgress(); } }
});
recommendations = createRecommendationExperience({ demo, icon, notify,
  state: () => ({ item: current(), busy: Boolean(generation) }),
  signals: () => listening.recommendationSignals(),
  related: seed => generateShow({ seed })
});
createQuietLayout({ icon });
updateVolume(); selectTheme(selected);
setInterval(syncThemeWithSystemTime, 60000);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) return;
  syncThemeWithSystemTime();
  // 浏览器若在后台拒绝了真正的音源，回到本页时自动续播，不需要再次点击。
  if (autoplayBlocked && mode === 'media' && current()) { autoplayBlocked = false; playMedia(); }
});

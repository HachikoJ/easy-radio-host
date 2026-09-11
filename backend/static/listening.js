// Independently implemented for Tingjian; interaction references are listed in credits.html.
function createListeningExperience(actions) {
  const get = id => document.getElementById(id);
  const storageKey = actions.demo ? 'tingjian.demo.library.v1' : 'tingjian.library.v1';
  let storageAvailable = true, library = { favorites: [], history: [] };
  let lastRecordedItem = null, metadataKey = '';
  const validEntry = entry => entry && typeof entry.title === 'string' && entry.title.trim() && entry.title.length <= 500 && typeof entry.theme === 'string' && entry.theme.length <= 100 && Number.isFinite(entry.at) && Number.isFinite(new Date(entry.at).getTime());
  const cleanEntries = (entries, limit) => Array.isArray(entries) ? entries.filter(validEntry).slice(0, limit).map(({ title, theme, at }) => ({ title, theme, at })) : [];
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey) || 'null');
    if (stored) library = { favorites: cleanEntries(stored.favorites, 100), history: cleanEntries(stored.history, 50) };
  } catch { storageAvailable = false; }

  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify(library)); storageAvailable = true; }
    catch { storageAvailable = false; }
    get('library-status').textContent = storageAvailable ? '' : '浏览器无法保存记录，本次记录仅在当前页面保留。';
  }
  function isFavorite(item) { return item?.kind === 'song' && library.favorites.some(entry => entry.title === item.title.slice(0, 500)); }
  function toggleFavorite() {
    const { item, theme } = actions.state();
    if (item?.kind !== 'song') return;
    if (isFavorite(item)) library.favorites = library.favorites.filter(entry => entry.title !== item.title.slice(0, 500));
    else {
      if (library.favorites.length >= 100) { actions.notify('此浏览器已收藏 100 首歌曲，请先取消部分收藏。'); return; }
      library.favorites.unshift({ title: item.title.slice(0, 500), theme: theme.name, at: Date.now() });
    }
    persist(); renderLibrary(); render();
  }
  function renderLibrary() {
    for (const [type, entries] of Object.entries(library)) {
      get(`${type}-empty`).hidden = entries.length > 0;
      get(`${type}-list`).replaceChildren(...entries.map(entry => {
        const li = document.createElement('li');
        const button = document.createElement('button'); button.type = 'button';
        button.setAttribute('aria-label', `点播${entry.title}`);
        const copy = document.createElement('span'); copy.className = 'library-copy';
        const title = document.createElement('strong'); title.textContent = entry.title;
        const meta = document.createElement('small');
        meta.textContent = `${entry.theme} · ${new Intl.DateTimeFormat('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(entry.at)}`;
        copy.append(title, meta); button.append(actions.icon('Music2'), copy, actions.icon('Play'));
        button.addEventListener('click', () => actions.replay(entry.title));
        li.append(button);
        if (type === 'favorites') {
          const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'icon-button favorite-remove';
          remove.setAttribute('aria-label', `取消收藏${entry.title}`); remove.dataset.tip = '取消收藏'; remove.append(actions.icon('Heart'));
          remove.addEventListener('click', () => {
            const oldIndex = library.favorites.indexOf(entry);
            library.favorites = library.favorites.filter(saved => saved.title !== entry.title);
            persist(); renderLibrary(); render();
            const remaining = get('favorites-list').querySelectorAll('.favorite-remove');
            (remaining[Math.min(oldIndex, remaining.length - 1)] || get('tab-favorites')).focus();
          });
          li.append(remove);
        }
        return li;
      }));
    }
    if (!storageAvailable) get('library-status').textContent = '浏览器无法读取收听记录，本次记录仅在当前页面保留。';
  }
  function recordPlay() {
    const { item, theme, mode } = actions.state();
    if (mode !== 'media' || item?.kind !== 'song' || item === lastRecordedItem) return;
    lastRecordedItem = item;
    const entry = { title: item.title.slice(0, 500), theme: theme.name, at: Date.now() };
    library.history = [entry, ...library.history.filter(old => old.title !== entry.title)].slice(0, 50);
    persist(); renderLibrary();
  }

  const tabs = ['queue', 'favorites', 'history'];
  function selectTab(name, focus = false) {
    for (const tab of tabs) {
      get(`tab-${tab}`).setAttribute('aria-selected', String(tab === name));
      get(`tab-${tab}`).tabIndex = tab === name ? 0 : -1;
      get(`panel-${tab}`).hidden = tab !== name;
    }
    if (focus) get(`tab-${name}`).focus();
  }
  for (const [i, tab] of tabs.entries()) {
    get(`tab-${tab}`).addEventListener('click', () => selectTab(tab));
    get(`tab-${tab}`).addEventListener('keydown', event => {
      const target = event.key === 'ArrowRight' ? (i + 1) % 3 : event.key === 'ArrowLeft' ? (i + 2) % 3 : event.key === 'Home' ? 0 : event.key === 'End' ? 2 : -1;
      if (target !== -1) { event.preventDefault(); selectTab(tabs[target], true); }
    });
  }
  document.querySelector('a[href="#queue-section"]').addEventListener('click', () => selectTab('queue'));
  get('favorite').addEventListener('click', toggleFavorite);

  function setAppearance(appearance) {
    document.documentElement.dataset.appearance = appearance;
    const label = appearance === 'dark' ? '切换浅色模式' : '切换深色模式';
    get('appearance').setAttribute('aria-label', label); get('appearance').dataset.tip = label;
    get('appearance').setAttribute('aria-pressed', String(appearance === 'dark'));
    get('appearance-icon').style.setProperty('--icon', `url(assets/${appearance === 'dark' ? 'Sun' : 'Moon'}.svg)`);
    document.querySelector('meta[name="theme-color"]').content = appearance === 'dark' ? '#17191c' : '#f6f7f9';
  }
  let storedAppearance = null;
  try {
    const saved = localStorage.getItem('tingjian.appearance.v1');
    if (saved === 'light' || saved === 'dark') storedAppearance = saved;
  } catch { /* Storage is optional. */ }
  let appearance = storedAppearance || 'dark';
  setAppearance(appearance);
  get('appearance').addEventListener('click', () => {
    appearance = appearance === 'dark' ? 'light' : 'dark'; storedAppearance = appearance; setAppearance(appearance);
    try { localStorage.setItem('tingjian.appearance.v1', appearance); } catch { actions.notify('当前浏览器无法记住配色，下次打开将恢复默认深色模式。'); }
  });
  function seekBy(delta) { actions.seek((document.getElementById('audio').currentTime || 0) + delta); }
  document.addEventListener('keydown', event => {
    if (event.defaultPrevented) return;
    if (event.isComposing || event.repeat || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.target.closest('input,textarea,button,a,select,[contenteditable="true"],[role="tab"]')) return;
    if (event.code === 'Space') { event.preventDefault(); actions.state().playing ? actions.pause() : actions.play(); }
    if (event.key === 'ArrowLeft') { event.preventDefault(); seekBy(-5); }
    if (event.key === 'ArrowRight') { event.preventDefault(); seekBy(5); }
    if (event.key === 'ArrowUp') { event.preventDefault(); actions.adjustVolume(.05); }
    if (event.key === 'ArrowDown') { event.preventDefault(); actions.adjustVolume(-.05); }
  });

  const session = navigator.mediaSession;
  if (session) {
    const handlers = { play: actions.play, pause: actions.pause, previoustrack: actions.previous, nexttrack: actions.next, stop: actions.stop, seekto: details => { if (Number.isFinite(details.seekTime)) actions.seek(details.seekTime); }, seekbackward: details => seekBy(-(details.seekOffset || 10)), seekforward: details => seekBy(details.seekOffset || 10) };
    for (const [action, handler] of Object.entries(handlers)) {
      try { session.setActionHandler(action, handler); } catch { /* Unsupported actions leave the visible controls available. */ }
    }
  }
  function updatePosition(duration, position) {
    if (!session?.setPositionState) return;
    try {
      if (actions.state().mode === 'media' && duration > 0 && Number.isFinite(duration)) session.setPositionState({ duration, playbackRate: 1, position: Math.max(0, Math.min(position, duration)) });
      else session.setPositionState();
    } catch { /* Position reporting varies by browser. */ }
  }
  function render() {
    const { item, theme, playing } = actions.state();
    const title = item?.title || theme.name;
    const artwork = `assets/${theme.image}.jpg`;
    const button = get('favorite'), saved = isFavorite(item);
    button.disabled = item?.kind !== 'song';
    button.setAttribute('aria-pressed', String(saved));
    const label = saved ? '取消收藏当前歌曲' : '收藏当前歌曲';
    button.setAttribute('aria-label', label); button.dataset.tip = label;
    get('focus-note').hidden = !item?.text || item.kind === 'song';
    get('focus-text').textContent = item?.kind === 'song' ? '' : item?.text || '';
    if (session) {
      const key = item ? `${title}|${artwork}` : '';
      try {
        if (key !== metadataKey) {
          session.metadata = item && typeof MediaMetadata === 'function' ? new MediaMetadata({ title, artist: item.kind === 'song' ? theme.name : '小蓝', album: actions.demo ? '听间 · 演示节目' : '听间', artwork: [{ src: new URL(artwork, location.href).href, type: 'image/jpeg' }] }) : null;
          metadataKey = key;
        }
        session.playbackState = item ? playing ? 'playing' : 'paused' : 'none';
      } catch { /* MediaSession is progressive enhancement. */ }
    }
  }
  renderLibrary();
  return { render, recordPlay, updatePosition,
    recommendationSignals: () => ({ favorites: library.favorites.map(entry => entry.title), history: library.history.map(entry => entry.title).reverse() })
  };
}

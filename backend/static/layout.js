export function createQuietLayout({ icon }) {
  const get = id => document.getElementById(id);
  const header = document.querySelector('.page-header');
  const nav = document.querySelector('.sidebar nav');
  header.prepend(document.querySelector('.sidebar .brand'), nav);
  const viewActions = document.querySelector('.view-actions');
  for (const [id, label, symbol] of [
    ['credits-link', '开源致谢', 'BookOpen'],
    ['author-link', '联系作者 · GitHub', 'Github']
  ]) {
    const link = get(id);
    link.className = 'icon-button header-resource'; link.dataset.tip = label;
    link.setAttribute('aria-label', `${label}（新标签页）`);
    link.replaceChildren(icon(symbol)); viewActions.append(link);
  }
  get('lyrics-home').classList.add('lyric-column');
  get('listening').append(get('lyrics-home'));

  const recordColumn = document.createElement('div'); recordColumn.className = 'record-column';
  const trackHeading = document.createElement('div'); trackHeading.className = 'track-heading';
  recordColumn.append(document.querySelector('.cover-wrap'), document.querySelector('.show-summary'));
  trackHeading.append(recordColumn.querySelector('#now-title'));
  get('listening').prepend(trackHeading, recordColumn);
  document.querySelector('.show-actions').append(document.querySelector('.now-heading .song-actions'));
  const controls = document.createElement('div'); controls.className = 'listening-tools';
  const follow = get('lyrics-follow').closest('label');
  const motion = get('motion-enabled').closest('label');
  follow.lastChild.textContent = '跟随'; motion.lastChild.textContent = '动效';
  follow.title = '歌词跟随播放'; motion.title = '播放动效';
  controls.append(follow, motion);
  const settings = get('recommendation-settings');
  const summary = settings.querySelector('summary');
  summary.setAttribute('aria-label', '收听设置'); summary.dataset.tip = '收听设置';
  summary.querySelector('.icon').style.setProperty('--icon', 'url(assets/SlidersHorizontal.svg)');
  const options = settings.querySelector('.recommendation-options');
  const playbackTitle = document.createElement('h3'); playbackTitle.textContent = '播放';
  const preferencesTitle = document.createElement('h3'); preferencesTitle.textContent = '选歌偏好';
  options.prepend(playbackTitle, get('auto').closest('label'), get('lyrics-timing'), preferencesTitle);
  options.append(get('recommendation-summary'));
  controls.append(settings); trackHeading.append(controls);
  const viewport = get('lyrics-lines');
  new ResizeObserver(() => {
    viewport.style.setProperty('--lyrics-height', `${viewport.clientHeight}px`);
  }).observe(viewport);
  const sizeRecord = new ResizeObserver(() => {
    recordColumn.style.setProperty('--record-room', `${Math.max(0, recordColumn.clientHeight - document.querySelector('.show-summary').offsetHeight)}px`);
  });
  sizeRecord.observe(recordColumn);
  sizeRecord.observe(document.querySelector('.show-summary'));
  const sizeSettings = () => {
    if (!settings.open) return;
    const bottom = Math.min(innerHeight, document.querySelector('.player-bar').getBoundingClientRect().top);
    options.style.setProperty('--settings-room', `${Math.max(80, bottom - summary.getBoundingClientRect().bottom - 12)}px`);
  };
  settings.addEventListener('toggle', sizeSettings);
  window.addEventListener('resize', sizeSettings);
  window.addEventListener('scroll', sizeSettings, { passive: true });

  const drawer = document.createElement('dialog'); drawer.className = 'utility-drawer'; drawer.id = 'utility-drawer';
  drawer.tabIndex = -1;
  drawer.setAttribute('aria-modal', 'false'); drawer.setAttribute('aria-labelledby', 'drawer-title');
  const drawerHeader = document.createElement('div'); drawerHeader.className = 'drawer-heading';
  const title = document.createElement('h2'); title.id = 'drawer-title';
  const close = document.createElement('button'); close.className = 'icon-button'; close.type = 'button';
  close.setAttribute('aria-label', '关闭面板'); close.dataset.tip = '关闭面板'; close.append(icon('X'));
  const content = document.createElement('div'); content.className = 'drawer-content';
  drawerHeader.append(title, close); drawer.append(drawerHeader, content);
  const sections = new Map([
    ['themes', { title: '主题电台', node: get('themes') }],
    ['queue-section', { title: '我的音乐', node: get('queue-section') }],
    ['conversation', { title: '点歌互动', node: get('conversation') }]
  ]);
  for (const { node } of sections.values()) { node.hidden = true; content.append(node); }
  const shade = document.createElement('div'); shade.className = 'drawer-shade'; shade.hidden = true; shade.setAttribute('aria-hidden', 'true');
  document.body.append(shade, drawer);
  let opener = null, activePanel = null;
  const navLinks = [...nav.querySelectorAll('a')];
  for (const link of navLinks) {
    link.setAttribute('aria-controls', link.hash === '#listening' ? 'listening' : drawer.id);
    if (link.hash !== '#listening') link.setAttribute('aria-expanded', 'false');
  }
  const updateNavigation = id => {
    for (const link of navLinks) {
      const active = link.hash === `#${id}`;
      link.classList.toggle('active', active);
      if (link.hash !== '#listening') link.setAttribute('aria-expanded', String(active));
      if (active) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
    }
  };
  const fitChatViewport = () => {
    drawer.classList.remove('compact-chat');
    drawer.style.removeProperty('--chat-top');
    if (activePanel !== 'conversation') return;
    const viewport = window.visualViewport;
    const visibleBottom = viewport ? viewport.offsetTop + viewport.height : innerHeight;
    const playerTop = document.querySelector('.player-bar').getBoundingClientRect().top;
    const bottom = Math.min(visibleBottom, playerTop) - 8;
    drawer.style.setProperty('--chat-bottom', `${Math.max(8, innerHeight - bottom)}px`);
    const room = bottom - drawer.getBoundingClientRect().top;
    if (room < 240) drawer.style.setProperty('--chat-top', `${(viewport?.offsetTop || 0) + 8}px`);
    drawer.classList.toggle('compact-chat', room < 360);
  };
  window.visualViewport?.addEventListener('resize', fitChatViewport);
  window.visualViewport?.addEventListener('scroll', fitChatViewport);
  window.addEventListener('resize', fitChatViewport);
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  function closeDrawer(restore = true) {
    if (!drawer.open) return;
    drawer.close(); shade.hidden = true; document.body.classList.remove('drawer-open'); activePanel = null;
    get('listening').inert = false;
    updateNavigation('listening');
    if (restore) opener?.focus({ preventScroll: true });
  }
  function openDrawer(id, trigger, focusOnOpen = true) {
    const selected = sections.get(id);
    if (!selected) { closeDrawer(false); return; }
    if (drawer.open && activePanel === id) { closeDrawer(); return; }
    settings.open = false;
    opener = trigger; activePanel = id;
    drawer.dataset.panel = id;
    for (const { node } of sections.values()) node.hidden = node !== selected.node;
    title.textContent = selected.title;
    if (!drawer.open) drawer.show();
    fitChatViewport();
    shade.hidden = false; document.body.classList.add('drawer-open');
    get('listening').inert = true;
    updateNavigation(id);
    if (!reduced.matches) content.animate([{ opacity: .2, transform: 'translateX(14px)' }, { opacity: 1, transform: 'none' }], { duration: 220, easing: 'ease-out' });
    if (id === 'conversation') get('message').focus({ preventScroll: true });
    else if (focusOnOpen) close.focus({ preventScroll: true });
    else drawer.focus({ preventScroll: true });
  }
  navLinks.forEach(link => link.addEventListener('click', event => {
    event.preventDefault(); openDrawer(link.hash.slice(1), link, event.detail === 0);
  }));
  document.querySelector('.brand').addEventListener('click', event => { event.preventDefault(); closeDrawer(false); });
  close.addEventListener('click', () => closeDrawer());
  shade.addEventListener('click', () => closeDrawer());
  get('theme-list').addEventListener('click', event => {
    if (!event.target.closest('.theme-card')) return;
    closeDrawer(false);
    get('generate').focus({ preventScroll: true });
  });
  get('queue').addEventListener('click', event => { if (event.target.closest('button')) closeDrawer(); });
  for (const id of ['favorites-list', 'history-list']) get(id).addEventListener('click', event => {
    if (event.target.closest('button') && !event.target.closest('.favorite-remove')) closeDrawer();
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Tab' && drawer.open) {
      const focusable = [...drawer.querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),textarea:not(:disabled),select:not(:disabled),summary,[tabindex]:not([tabindex="-1"])')].filter(node => !node.hidden && node.getClientRects().length);
      if (!focusable.length) { event.preventDefault(); drawer.focus(); return; }
      const first = focusable[0], last = focusable.at(-1);
      if (!drawer.contains(document.activeElement)) { event.preventDefault(); (event.shiftKey ? last : first).focus(); }
      else if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      return;
    }
    if (event.key !== 'Escape') return;
    if (settings.open) { settings.open = false; summary.focus(); }
    else if (drawer.open) closeDrawer();
    else return;
    event.preventDefault(); event.stopImmediatePropagation();
  }, true);
  document.addEventListener('pointerdown', event => { if (settings.open && !settings.contains(event.target)) settings.open = false; });
  window.addEventListener('tingjian:show-lyrics', () => closeDrawer(false));
  window.addEventListener('tingjian:layout', () => { settings.open = false; closeDrawer(false); });

  const updateBackdrop = () => {
    const image = get('cover');
    get('lyrics-panel').style.setProperty('--lyric-image', `url("${image.src}")`);
  };
  new MutationObserver(updateBackdrop).observe(get('cover'), { attributes: true, attributeFilter: ['src'] });
  window.addEventListener('tingjian:layout', updateBackdrop);
  document.body.classList.add('quiet-ui');
  updateBackdrop();
  window.dispatchEvent(new Event('tingjian:layout'));
}

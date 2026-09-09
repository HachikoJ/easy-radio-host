export function createQuietLayout({ icon, setFocus }) {
  const get = id => document.getElementById(id);
  const header = document.querySelector('.page-header');
  const nav = document.querySelector('.sidebar nav');
  header.prepend(document.querySelector('.sidebar .brand'), nav);
  get('lyrics-home').classList.add('lyric-column');
  get('listening').append(get('lyrics-home'));

  const heading = document.querySelector('.lyrics-heading');
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
  controls.append(settings); heading.append(controls);
  const sizeSettings = () => {
    if (!settings.open) return;
    const bottom = Math.min(innerHeight, document.querySelector('.player-bar').getBoundingClientRect().top);
    options.style.setProperty('--settings-room', `${Math.max(80, bottom - summary.getBoundingClientRect().bottom - 12)}px`);
  };
  settings.addEventListener('toggle', sizeSettings);
  window.addEventListener('resize', sizeSettings);
  window.addEventListener('scroll', sizeSettings, { passive: true });

  const drawer = document.createElement('dialog'); drawer.className = 'utility-drawer';
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
  const shade = document.createElement('div'); shade.className = 'drawer-shade'; shade.hidden = true;
  document.body.append(shade, drawer);
  let opener = null, activePanel = null;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  function closeDrawer(restore = true) {
    if (!drawer.open) return;
    drawer.close(); shade.hidden = true; activePanel = null;
    for (const node of document.querySelectorAll('.listening,.focus-stage,.page-footer')) node.inert = false;
    nav.querySelectorAll('a').forEach(link => link.classList.toggle('active', link.hash === '#listening'));
    if (restore) opener?.focus({ preventScroll: true });
  }
  function openDrawer(id, trigger) {
    const selected = sections.get(id);
    if (!selected) { closeDrawer(false); setFocus(false); return; }
    if (drawer.open && activePanel === id) { closeDrawer(); return; }
    settings.open = false;
    opener = trigger; activePanel = id;
    for (const { node } of sections.values()) node.hidden = node !== selected.node;
    title.textContent = selected.title;
    if (!drawer.open) drawer.show();
    shade.hidden = false;
    for (const node of document.querySelectorAll('.listening,.focus-stage,.page-footer')) node.inert = true;
    nav.querySelectorAll('a').forEach(link => link.classList.toggle('active', link.hash === `#${id}`));
    if (!reduced.matches) content.animate([{ opacity: .2, transform: 'translateX(14px)' }, { opacity: 1, transform: 'none' }], { duration: 220, easing: 'ease-out' });
    (id === 'conversation' ? get('message') : close).focus({ preventScroll: true });
  }
  nav.querySelectorAll('a').forEach(link => link.addEventListener('click', event => {
    event.preventDefault(); openDrawer(link.hash.slice(1), link);
  }));
  document.querySelector('.brand').addEventListener('click', event => { event.preventDefault(); closeDrawer(false); setFocus(false); });
  close.addEventListener('click', () => closeDrawer());
  shade.addEventListener('click', () => closeDrawer());
  get('theme-list').addEventListener('click', async event => {
    if (!event.target.closest('.theme-card')) return;
    closeDrawer(false);
    await setFocus(false);
    get('generate').focus({ preventScroll: true });
  });
  get('queue').addEventListener('click', event => { if (event.target.closest('button')) closeDrawer(); });
  for (const id of ['favorites-list', 'history-list']) get(id).addEventListener('click', event => {
    if (event.target.closest('button') && !event.target.closest('.favorite-remove')) closeDrawer();
  });
  document.addEventListener('keydown', event => {
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
    const image = get(document.body.classList.contains('focus-mode') ? 'focus-cover' : 'cover');
    get('lyrics-panel').style.setProperty('--lyric-image', `url("${image.src}")`);
  };
  for (const id of ['cover', 'focus-cover']) new MutationObserver(updateBackdrop).observe(get(id), { attributes: true, attributeFilter: ['src'] });
  window.addEventListener('tingjian:layout', updateBackdrop);
  document.body.classList.add('quiet-ui');
  updateBackdrop();
  window.dispatchEvent(new Event('tingjian:layout'));
}

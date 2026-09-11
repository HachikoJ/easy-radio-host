(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.TingjianThemeSchedule = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  const SCHEDULE = [
    { start: 5, end: 9, name: '元气早班' },
    { start: 9, end: 12, name: '城市漫游' },
    { start: 12, end: 18, name: '午后咖啡' },
    { start: 18, end: 20, name: '怀旧金曲' },
    { start: 20, end: 22, name: '心情小站' },
    { start: 22, end: 5, name: '深夜安眠' }
  ];

  const themes = [
    { name: '午后咖啡', slogan: '忙里偷闲的一杯歌', detail: '轻松 · 慢一点', image: 'coffee' },
    { name: '城市漫游', slogan: '陪你在路上', detail: '流行 · 在路上', image: 'city' },
    { name: '深夜安眠', slogan: '让世界慢下来', detail: '安静 · 好好休息', image: 'night' },
    { name: '怀旧金曲', slogan: '把旧时光唱给你听', detail: '经典 · 旧时光', image: 'stage' },
    { name: '元气早班', slogan: '把好心情叫醒', detail: '轻快 · 新的一天', image: 'forest' },
    { name: '心情小站', slogan: '此刻的你最想听什么', detail: '随心 · 放空一下', image: 'lake' }
  ];

  function themeNameForHour(hour) {
    const normalized = ((Number(hour) % 24) + 24) % 24;
    return SCHEDULE.find(({ start, end }) => (
      start < end
        ? normalized >= start && normalized < end
        : normalized >= start || normalized < end
    )).name;
  }

  function scheduledTheme(availableThemes, now = new Date()) {
    const name = themeNameForHour(now.getHours());
    return availableThemes.find(theme => theme.name === name) || availableThemes[0];
  }

  function applyScheduledTheme(targetDocument = document, now = new Date()) {
    const theme = scheduledTheme(themes, now);
    const set = (id, property, value) => {
      const node = targetDocument.getElementById(id);
      if (node) node[property] = value;
    };
    set('cover', 'src', `assets/${theme.image}.jpg`);
    set('cover', 'alt', `${theme.name}主题封面`);
    set('show-theme', 'textContent', theme.detail);
    set('show-slogan', 'textContent', theme.slogan);
    set('now-title', 'textContent', theme.name);
    set('now-title', 'title', theme.name);
    set('mini-cover', 'src', `assets/${theme.image}.jpg`);
    targetDocument.documentElement.dataset.scheduledTheme = theme.name;
    // 启动遮罩由 layout.js 在真实布局提交后统一解除，避免旧版结构先被绘制。
    return theme;
  }

  const api = { themes, themeNameForHour, scheduledTheme, applyScheduledTheme };
  if (typeof document !== 'undefined') applyScheduledTheme(document);
  return api;
});

const SCHEDULE = [
  { start: 5, end: 9, name: '元气早班' },
  { start: 9, end: 12, name: '城市漫游' },
  { start: 12, end: 18, name: '午后咖啡' },
  { start: 18, end: 20, name: '怀旧金曲' },
  { start: 20, end: 22, name: '心情小站' },
  { start: 22, end: 5, name: '深夜安眠' }
];

export function themeNameForHour(hour) {
  const normalized = ((Number(hour) % 24) + 24) % 24;
  return SCHEDULE.find(({ start, end }) => (
    start < end
      ? normalized >= start && normalized < end
      : normalized >= start || normalized < end
  )).name;
}

export function scheduledTheme(themes, now = new Date()) {
  const name = themeNameForHour(now.getHours());
  return themes.find(theme => theme.name === name) || themes[0];
}

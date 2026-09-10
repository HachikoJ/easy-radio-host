import assert from 'node:assert/strict';
import { test } from 'node:test';
import { scheduledTheme, themeNameForHour } from '../backend/static/theme-schedule.js';

const themes = [
  { name: '午后咖啡' },
  { name: '城市漫游' },
  { name: '深夜安眠' },
  { name: '怀旧金曲' },
  { name: '元气早班' },
  { name: '心情小站' }
];

test('maps each system hour to the intended programme theme', () => {
  const cases = new Map([
    [4, '深夜安眠'],
    [5, '元气早班'],
    [8, '元气早班'],
    [9, '城市漫游'],
    [11, '城市漫游'],
    [12, '午后咖啡'],
    [17, '午后咖啡'],
    [18, '怀旧金曲'],
    [19, '怀旧金曲'],
    [20, '心情小站'],
    [21, '心情小站'],
    [22, '深夜安眠'],
    [23, '深夜安眠']
  ]);
  for (const [hour, expected] of cases) {
    assert.equal(themeNameForHour(hour), expected, `${hour}:00`);
  }
});

test('falls back to the first available theme when a scheduled theme is absent', () => {
  const now = new Date(2026, 8, 10, 22, 0);
  assert.equal(scheduledTheme([{ name: '午后咖啡' }], now).name, '午后咖啡');
});

test('returns the complete scheduled theme object for the current time', () => {
  const now = new Date(2026, 8, 10, 14, 0);
  assert.equal(scheduledTheme(themes, now).name, '午后咖啡');
});

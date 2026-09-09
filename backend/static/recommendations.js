// Recommendation preferences stay in this browser until explicitly enabled.
export function createRecommendationExperience(actions) {
  const get = id => document.getElementById(id);
  const storageKey = actions.demo ? 'tingjian.demo.recommendation.v1' : 'tingjian.recommendation.v1';
  let enabled = false, disliked = [], available = true, summary = null;
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || 'null');
    enabled = saved?.enabled === true;
    disliked = Array.isArray(saved?.disliked) ? [...new Set(saved.disliked.filter(title => typeof title === 'string' && title.trim() && title.length <= 500))].slice(0, 100) : [];
  } catch { available = false; }
  function persist() {
    try { localStorage.setItem(storageKey, JSON.stringify({ enabled, disliked })); available = true; }
    catch { available = false; }
  }
  function renderList() {
    get('disliked-count').textContent = String(disliked.length);
    get('disliked-empty').hidden = disliked.length > 0;
    get('disliked-list').replaceChildren(...disliked.map(title => {
      const li = document.createElement('li'), copy = document.createElement('span'), undo = document.createElement('button');
      copy.textContent = title;
      undo.type = 'button'; undo.className = 'icon-button'; undo.setAttribute('aria-label', `恢复推荐${title}`); undo.dataset.tip = '恢复推荐'; undo.append(actions.icon('RefreshCw'));
      undo.addEventListener('click', () => {
        const index = disliked.indexOf(title);
        disliked = disliked.filter(value => value !== title); persist(); renderList(); render();
        const remaining = get('disliked-list').querySelectorAll('button');
        (remaining[Math.min(index, remaining.length - 1)] || get('disliked-summary')).focus();
        actions.notify(`已恢复推荐：${title}`);
      });
      li.append(copy, undo); return li;
    }));
  }
  function render() {
    const { item, busy } = actions.state(), song = item?.kind === 'song';
    get('personalize').checked = enabled;
    get('recommendation-state').textContent = enabled ? '偏好选歌已开启' : '主题选歌';
    get('recommendation-storage').textContent = available ? '' : '浏览器无法保存偏好，本次设置仅在当前页面保留。';
    const isDisliked = song && disliked.includes(item.title);
    const related = get('related'), dislike = get('dislike');
    related.disabled = !song || busy;
    dislike.disabled = !song || busy;
    const label = isDisliked ? '恢复推荐这首' : '少推荐这首';
    dislike.setAttribute('aria-label', label); dislike.dataset.tip = label; dislike.setAttribute('aria-pressed', String(Boolean(isDisliked)));
    const reason = get('recommendation-reason');
    reason.textContent = song ? item.recommendation?.reason || '' : '';
    reason.hidden = !reason.textContent;
    const notices = [];
    if (summary?.recent_relaxed) notices.push('近期可选歌曲不足，已优先回补较早听过的歌曲');
    if (summary?.artist_limit_relaxed) notices.push('可选歌手较少，本期包含同歌手曲目');
    const notice = typeof summary?.notice === 'string' ? summary.notice.slice(0, 500) : notices.join('；');
    get('recommendation-summary').textContent = notice;
    get('recommendation-summary').hidden = !notice;
  }
  function toggleDislike() {
    const { item } = actions.state();
    if (item?.kind !== 'song') return;
    if (!enabled) {
      get('recommendation-settings').open = true;
      get('personalize').focus();
      actions.notify('请先开启“按我的偏好选歌”，再设置少推荐歌曲。');
      return;
    }
    const title = item.title.slice(0, 500);
    if (disliked.includes(title)) {
      disliked = disliked.filter(value => value !== title);
      actions.notify(`已恢复推荐：${title}`);
    } else {
      if (disliked.length >= 100) { actions.notify('少推荐列表已满，请先恢复部分歌曲。'); return; }
      disliked = [...disliked, title];
      actions.notify(`已设为少推荐：${title}。从下一期生效，仍可主动点播。`);
    }
    persist(); renderList(); render();
  }
  get('personalize').addEventListener('change', event => {
    enabled = event.target.checked; persist(); render();
    actions.notify(enabled ? '偏好选歌已开启，从下一期生效。' : '偏好选歌已关闭，后续节目不发送本地偏好记录。');
  });
  get('dislike').addEventListener('click', toggleDislike);
  get('related').addEventListener('click', () => {
    const { item } = actions.state();
    if (item?.kind === 'song') actions.related(item.title);
  });
  renderList(); render();
  return {
    render,
    setSummary: value => { summary = value; render(); },
    request: (seed = '') => enabled ? { personalize: true, ...actions.signals(), disliked: [...disliked], seed } : { personalize: false, seed }
  };
}

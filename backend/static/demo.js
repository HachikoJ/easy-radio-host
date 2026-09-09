// Local fixtures are loaded only with ?demo=1; production requests use the existing API.
function wait(signal) {
  return new Promise((resolve, reject) => {
    const abort = () => { clearTimeout(timer); reject(new DOMException('Aborted', 'AbortError')); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', abort); resolve(); }, 700);
    if (signal.aborted) abort(); else signal.addEventListener('abort', abort, { once: true });
  });
}
export async function respond(path, body, signal) {
  await wait(signal);
  if (path === '/api/show') {
    const candidates = ['窗边 / 原创试听', '微风 / 原创试听'];
    const available = candidates.filter(title => title !== body.recommendation?.seed && !(body.recommendation?.personalize && body.recommendation.disliked?.includes(title)));
    if (!available.length) throw new Error('没有符合偏好的演示歌曲，请恢复少推荐列表中的歌曲。');
    return {
    meta: { theme: body.theme, slogan: '一段留给自己的声音', time: '演示节目', recommendation: {} },
    items: [
      { kind: 'text', title: '把这一刻留给自己', text: '我是小蓝。先把手里的事放一放，听一段轻轻的旋律。这是听间的演示节目，接下来是一段本地合成的原创试听。' },
      { kind: 'song', title: '窗边 / 原创试听', url: 'assets/demo-chimes.wav', recommendation: { sources: ['demo'], reason: '原创试听 · 主题选歌示例' } },
      { kind: 'text', title: '小蓝的片刻絮语', text: '有时候，音乐不必填满所有安静。下一段，继续把节奏放慢一些。' },
      { kind: 'song', title: '微风 / 原创试听', url: 'assets/demo-chimes.wav', recommendation: { sources: ['demo'], reason: '原创试听 · 探索选歌示例' } },
      { kind: 'text', title: '待会儿再见', text: '这一小段节目就到这里。愿下一刻，也有你喜欢的声音。' }
    ].filter(item => item.kind !== 'song' || available.includes(item.title))
  };
  }
  const replayTitle = body.message.match(/^请播放《(窗边 \/ 原创试听|微风 \/ 原创试听)》$/)?.[1];
  if (replayTitle) return { items: [{ kind: 'song', title: replayTitle, url: 'assets/demo-chimes.wav' }], actions: [] };
  const control = /暂停/.test(body.message) ? 'pause' : /继续/.test(body.message) ? 'resume' : /下一/.test(body.message) ? 'next' : /上一/.test(body.message) ? 'prev' : /停止/.test(body.message) ? 'stop' : '';
  return {
    items: [{ kind: 'text', title: '小蓝的回应', text: control ? '好的，收到。' : '收到。这是本地演示回应，真实点歌和聊天会交给电台服务处理。' }],
    actions: control ? [{ type: control }] : []
  };
}

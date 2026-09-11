async (page) => {
  const check = (ok, message) => { if (!ok) throw new Error(message); };
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    window.playEvents = [];
    window.mainAudioLoads = 0;
    window.holdAnnouncement = false;
    window.holdCooldown = false;
    window.abortedRequests = [];
    window.autoplayUnlocked = false;
    window.__testHidden = false;
    window.forceBackgroundReject = false;
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => window.__testHidden });
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => window.__testHidden ? 'hidden' : 'visible' });
    window.setTestHidden = value => { window.__testHidden = value; document.dispatchEvent(new Event('visibilitychange')); };
    let transientPlaybackGesture = false;
    document.addEventListener('click', () => {
      transientPlaybackGesture = true;
      setTimeout(() => { transientPlaybackGesture = false; }, 0);
    }, { capture: true });
    const originalFetch = window.fetch;
    window.fetch = (url, options = {}) => {
      options.signal?.addEventListener('abort', () => window.abortedRequests.push(String(url)), { once: true });
      return originalFetch(url, options);
    };
    const proto = HTMLMediaElement.prototype;
    Object.defineProperty(proto, 'paused', { get() { return this._paused !== false; } });
    Object.defineProperty(proto, 'currentTime', { get() { return this._time || 0; }, set(value) { this._time = value; } });
    Object.defineProperty(proto, 'duration', { get() { return 180; } });
    proto.pause = function () { this._paused = true; this.dispatchEvent(new Event('pause')); };
    // 媒体重新加载会结束浏览器的播放授权；仅切换地址不会。
    proto.load = function () { this._time = 0; this._userUnlocked = false; if (this.id === 'audio') window.mainAudioLoads++; };
    // 真实浏览器在设置新 src 后会回到 paused，等待下一次 play()。
    const src = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
    Object.defineProperty(proto, 'src', {
      get() { return src.get.call(this); },
      set(value) { src.set.call(this, value); this._paused = true; }
    });
    proto.play = function () {
      const url = this.src;
      // 模拟：即使元素已解锁，浏览器在后台仍可能拒绝这一次播放；回到前台重试必须成功。
      if (window.forceBackgroundReject && document.hidden && !url.startsWith('blob:')) {
        window.forceBackgroundReject = false;
        return Promise.reject(new DOMException('User gesture required', 'NotAllowedError'));
      }
      // 真实的浏览器策略：用户手势能激活一次播放；页面进入后台后，
      // 已经由手势解锁且没有重新加载的媒体元素仍可继续播放。
      if (!this._userUnlocked && !transientPlaybackGesture && (document.hidden || !window.autoplayUnlocked)) {
        return Promise.reject(new DOMException('User gesture required', 'NotAllowedError'));
      }
      if (!this._userUnlocked) { this._userUnlocked = true; window.autoplayUnlocked = true; }
      window.playEvents.push({ url, time: Date.now(), hidden: document.hidden });
      this._paused = false;
      if (url.includes('/bad.mp3')) {
        queueMicrotask(() => this.dispatchEvent(new Event('error')));
        return Promise.reject(new DOMException('Unavailable test audio', 'NotSupportedError'));
      }
      queueMicrotask(() => {
        this.dispatchEvent(new Event('loadedmetadata'));
        this.dispatchEvent(new Event('playing'));
      });
      if ((url.includes('/announcement/') && !window.holdAnnouncement) || (url.includes('/cooldown/') && !window.holdCooldown)) {
        setTimeout(() => { if (this.src === url && !this.paused) this.dispatchEvent(new Event('ended')); }, 250);
      }
      return Promise.resolve();
    };
  });
  let resolveStatus = 'limited', intentStatus = 'unavailable', availabilityStatus = 'ready', showFailure = null, showRetryAfter = 2, songIds = ['bad', 'good'];
  let showDelay = 0, intentDelay = 0, cooldownManifestFailure = false;
  let showCalls = 0, resolveCalls = 0, availabilityCalls = 0, cooldownManifestCalls = 0;
  const song = id => ({ kind: 'song', title: id === 'bad' ? '指定歌曲 / 原唱' : `推荐歌曲 ${id}`, artist: '原唱', source: 'netease', id, url: `/music/s/netease/${id}.mp3` });
  await page.route('**/api/show', async route => {
    showCalls++;
    if (showDelay) await page.waitForTimeout(showDelay);
    return route.fulfill(showFailure ? { status: 429, json: { detail: { status: showFailure, notice: '本轮音源访问额度已用完，将自动继续。', retry_after: showRetryAfter } } } : { json: { items: songIds.map(song) } }).catch(() => {});
  });
  await page.route('**/api/playback/resolve', route => {
    resolveCalls++;
    return route.fulfill({ json: { status: resolveStatus, retry_after: 2 } });
  });
  await page.route('**/api/playback/availability', route => {
    availabilityCalls++;
    return route.fulfill({ json: { status: availabilityStatus, remaining: 20, retry_after: 0 } });
  });
  await page.route('**/api/playback/cooldown/**', route => {
    if (route.request().url().endsWith('/content.json')) {
      cooldownManifestCalls++;
      if (cooldownManifestFailure) return route.fulfill({ status: 503, body: '' });
      return route.fulfill({ json: { version: 'v1-test', items: [
        { id: 'evening', title: '晚间话题', period: 'evening', text: '晚间内容', url: '/api/playback/cooldown/v1-test/evening.mp3' },
        { id: 'mood1', title: '心情话题', period: 'any', text: '心情内容', url: '/api/playback/cooldown/v1-test/mood1.mp3' },
        { id: 'morning', title: '早间话题', period: 'morning', text: '早间内容', url: '/api/playback/cooldown/v1-test/morning.mp3' },
        { id: 'weather1', title: '天气话题', period: 'any', text: '条件式天气内容', url: '/api/playback/cooldown/v1-test/weather1.mp3' },
        { id: 'external', title: '不可信内容', period: 'any', text: '不应播放', url: 'https://invalid.example/foreign.mp3' }
      ] } });
    }
    return route.fulfill({ contentType: 'audio/wav', body: fixture });
  });
  await page.route('**/api/intent', async route => {
    if (intentDelay) await page.waitForTimeout(intentDelay);
    return route.fulfill({ json: intentStatus === 'available' ? { items: [song('bad')], actions: [] } : { availability: intentStatus, retry_after: 2, notice: intentStatus === 'unavailable' ? '《用户指定歌曲》未找到相关音源，将继续下一首推荐。' : '音源服务暂时限流，将继续下一首推荐。', items: [], actions: [{ type: 'next' }] } }).catch(() => {});
  });
  const fixture = await (await page.request.get('http://127.0.0.1:8131/assets/demo-chimes.wav')).body();
  await page.route('**/music/s/**', route => route.fulfill({ contentType: 'audio/wav', body: fixture }));
  await page.route('**/api/playback/announcement/**', route => route.fulfill({ contentType: 'audio/wav', body: fixture }));
  await page.route('**/music/lyrics/**', route => route.fulfill({ json: { lyric: '[00:00.00]验证歌词' } }));
  const reset = async () => { await page.goto('http://127.0.0.1:8131/'); await page.evaluate(() => { document.querySelector('#auto').checked = false; }); };
  await reset();
  await page.locator('#generate').click();
  check(await page.waitForFunction(() => window.autoplayUnlocked), 'start click primes browser playback permission');
  await page.waitForFunction(() => window.playEvents.some(event => event.url.includes('/announcement/limited.mp3')));
  check((await page.locator('audio').getAttribute('src') || '').startsWith('blob:'), 'failed audio is replaced by the inaudible relay during announcement');
  check((await page.locator('#track-title').textContent()).includes('指定歌曲'), 'reason announcement precedes next track');
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/good.mp3'));
  check(resolveCalls === 1, 'duplicate media errors merge into a single recovery');
  check(await page.evaluate(() => {
    const announcement = window.playEvents.find(event => event.url.includes('/announcement/limited.mp3'));
    return window.playEvents.find(event => event.url.includes('/good.mp3')).time - announcement.time >= 200;
  }), 'limited announcement finishes before next song, even with auto disabled');

  await page.locator('audio').evaluate(audio => { audio.currentTime = 42; });
  await page.locator('#play').click();
  check(!(await page.locator('audio').getAttribute('src')), 'pause releases the audio stream');
  await page.locator('#play').click();
  await page.waitForFunction(() => document.querySelector('audio').currentTime === 42);

  for (const status of ['unavailable', 'temporary']) {
    resolveStatus = status; await reset(); await page.locator('#generate').click();
    await page.waitForFunction(reason => window.playEvents.some(event => event.url.includes(`/announcement/${reason}.mp3`)), status);
    await page.waitForFunction(() => document.querySelector('audio').src.includes('/good.mp3'));
  }

  resolveStatus = 'limited'; await reset(); await page.evaluate(() => { window.holdAnnouncement = true; });
  await page.locator('#generate').click();
  await page.waitForFunction(() => document.querySelector('#show-status').textContent === '小蓝正在提醒');
  await page.locator('#play').click();
  await page.waitForTimeout(500);
  check(!(await page.locator('audio').getAttribute('src')), 'pause cancels announcement and prevents late next');
  check(!await page.evaluate(() => window.playEvents.some(event => event.url.includes('/good.mp3'))), 'cancelled announcement does not resume playback');

  songIds = ['first', 'second']; await reset(); await page.locator('#generate').click();
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/first.mp3'));
  await page.locator('a[href="#conversation"]').click();
  await page.locator('#message').fill('请播放用户指定歌曲'); await page.locator('#send').click();
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/second.mp3'));
  check((await page.locator('#chat-log').textContent()).includes('《用户指定歌曲》未找到相关音源'), 'explicit requested-song failure persists as text');
  check(await page.evaluate(() => window.playEvents.some(event => event.url.includes('/announcement/unavailable.mp3'))), 'explicit missing request has audible reason');

  showFailure = 'limited'; showRetryAfter = 8; await reset(); await page.locator('#generate').click();
  await page.waitForFunction(() => ['等待自动续播', '小蓝陪你聊一会儿'].includes(document.querySelector('#show-status').textContent));
  await page.waitForFunction(() => window.playEvents.some(event => event.url.includes('/api/playback/cooldown/')));
  const localHour = await page.evaluate(() => new Date().getHours());
  check((await page.locator('#queue').textContent() || '').includes('心情话题') === false, 'cooldown content stays outside the programme queue');
  const blockedShowCalls = showCalls, beforeAvailability = availabilityCalls;
  await page.waitForTimeout(500);
  check(showCalls === blockedShowCalls && availabilityCalls === beforeAvailability, 'quota window does not generate or poll early');
  showFailure = null;
  const eligibleCount = localHour >= 5 && localHour < 12 || localHour >= 18 || localHour < 5 ? 3 : 2;
  await page.waitForFunction(count => window.playEvents.filter(event => event.url.includes('/api/playback/cooldown/')).length >= count + 1, eligibleCount);
  const cooldownIds = await page.evaluate(() => window.playEvents.filter(event => event.url.includes('/api/playback/cooldown/')).map(event => new URL(event.url).pathname.split('/').pop().replace('.mp3', '')));
  check(new Set(cooldownIds.slice(0, eligibleCount)).size === eligibleCount, 'cooldown does not repeat within a shuffled round');
  check(cooldownIds[eligibleCount - 1] !== cooldownIds[eligibleCount], 'cooldown does not repeat across a round boundary');
  check(!cooldownIds.includes('external'), 'cooldown rejects off-origin manifest audio');
  check(!(localHour >= 5 && localHour < 12) || !cooldownIds.includes('evening'), 'morning cooldown excludes evening-only content');
  check(!(localHour >= 18 || localHour < 5) || !cooldownIds.includes('morning'), 'evening cooldown excludes morning-only content');
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/first.mp3'), null, { timeout: 12000 });
  check(availabilityCalls === beforeAvailability + 1 && showCalls === blockedShowCalls + 1, 'quota recovery checks availability once then auto-recommends');

  showRetryAfter = 2; showFailure = 'limited'; await reset(); await page.locator('#generate').click();
  await page.waitForFunction(() => ['等待自动续播', '小蓝陪你聊一会儿'].includes(document.querySelector('#show-status').textContent));
  const pausedShowCalls = showCalls, pausedAvailabilityCalls = availabilityCalls;
  await page.locator('#play').click();
  await page.waitForTimeout(2600);
  check(showCalls === pausedShowCalls && availabilityCalls === pausedAvailabilityCalls, 'pause cancels automatic quota resume');
  showFailure = null; await page.locator('#play').click();
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/first.mp3'), null, { timeout: 6000 });
  await page.evaluate(() => window.dispatchEvent(new Event('pagehide')));
  check(!(await page.locator('audio').getAttribute('src')), 'pagehide releases active audio');

  for (const status of ['unavailable', 'available']) {
    intentStatus = status; resolveStatus = 'unavailable'; await reset();
    await page.locator('a[href="#conversation"]').click();
    await page.locator('#message').fill('请播放用户指定歌曲'); await page.locator('#send').click();
    await page.waitForFunction(() => ['等待自动续播', '小蓝陪你聊一会儿'].includes(document.querySelector('#show-status').textContent));
    check((await page.locator('#notice-text').textContent()).includes('自动推荐下一首'), `${status} request with no original queue schedules recommendation`);
    await page.keyboard.press('Escape'); await page.locator('#stop').click();
  }

  availabilityStatus = 'temporary'; showFailure = 'limited'; await reset(); await page.locator('#generate').click();
  const beforeTemporaryCheck = availabilityCalls;
  await page.waitForFunction(() => ['等待自动续播', '小蓝陪你聊一会儿'].includes(document.querySelector('#show-status').textContent));
  const beforeTemporaryShow = showCalls;
  await page.waitForTimeout(3500);
  check(availabilityCalls === beforeTemporaryCheck + 1 && showCalls === beforeTemporaryShow, 'temporary availability does not trigger expensive generation');
  await page.locator('#stop').click();

  availabilityStatus = 'ready'; cooldownManifestFailure = true; showFailure = 'limited';
  const beforeManifestFailureAvailability = availabilityCalls;
  await reset(); await page.locator('#generate').click();
  await page.waitForFunction(() => window.playEvents.filter(event => event.url.includes('/announcement/waiting.mp3')).length > 0);
  showFailure = null;
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/first.mp3'), null, { timeout: 6000 });
  check(availabilityCalls === beforeManifestFailureAvailability + 1, 'manifest failure still checks availability exactly once at expiry');
  cooldownManifestFailure = false;

  availabilityStatus = 'ready'; showFailure = null; showDelay = 800;
  await reset(); await page.locator('#generate').click();
  await page.locator('#cancel-generate').click(); await page.waitForTimeout(1000);
  check(await page.evaluate(() => window.abortedRequests.includes('/api/show')), 'cancel generation aborts its request');
  check(!(await page.locator('audio').getAttribute('src')), 'late show response does not resume playback');
  showDelay = 0; intentDelay = 800;
  await page.locator('#generate').click();
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/first.mp3'));
  await page.locator('a[href="#conversation"]').click();
  await page.locator('#message').fill('请播放用户指定歌曲'); await page.locator('#send').click();
  await page.keyboard.press('Escape'); await page.locator('#play').click(); await page.waitForTimeout(1000);
  check(await page.evaluate(() => window.abortedRequests.includes('/api/intent')), 'pause aborts pending point request');
  check(!(await page.locator('audio').getAttribute('src')), 'late intent response does not insert playback after pause');

  intentDelay = 0; resolveStatus = 'limited'; songIds = ['bad', 'good', 'third'];
  await reset(); await page.locator('#generate').click();
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/good.mp3'));
  const beforeManualQuotaShow = showCalls;
  await page.locator('#generate').click();
  check((await page.locator('audio').getAttribute('src') || '').startsWith('blob:'), 'known quota announcement replaces current song with the inaudible relay');
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/third.mp3'));
  check(showCalls === beforeManualQuotaShow, 'manual generation during known quota continues cached queue without calling show');
  await page.locator('#stop').click();

  showFailure = 'limited'; showRetryAfter = 640; await reset(); await page.locator('#generate').click();
  await page.waitForFunction(() => window.playEvents.some(event => event.url.includes('/api/playback/cooldown/')));
  const beforeLongCooldownAvailability = availabilityCalls;
  await page.waitForTimeout(900);
  check(availabilityCalls === beforeLongCooldownAvailability, '640-second cooldown never probes availability early');
  await page.locator('#stop').click();

  // 用户点击开始后切到后台：节目加载完成必须自动续播，不能再要一次点击。
  showDelay = 900; showFailure = null; resolveStatus = 'unavailable'; availabilityStatus = 'ready';
  songIds = ['background'];
  await reset();
  await page.locator('#generate').click();
  await page.evaluate(() => window.setTestHidden(true));
  check(await page.waitForFunction(() => {
    const audio = document.querySelector('audio');
    return audio.src.startsWith('blob:') && !audio.paused;
  }), 'silent relay keeps the playback session alive while the show is generated in the background');
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/background.mp3') && !document.querySelector('audio').paused, null, { timeout: 6000 });
  const backgroundPlay = await page.evaluate(() => window.playEvents.find(event => event.url.includes('/background.mp3')));
  check(backgroundPlay?.hidden === true, 'real audio starts while the tab stays in the background');
  check(await page.evaluate(() => window.mainAudioLoads === 0), 'background handoff never unloads the unlocked audio element');
  await page.evaluate(() => window.setTestHidden(false));

  // 后台播放仍被拒绝时，回到本页要自动重试并清除提示，不能要求再点一次。
  showDelay = 600; showFailure = null; resolveStatus = 'unavailable'; songIds = ['retry'];
  await reset();
  await page.locator('#generate').click();
  await page.evaluate(() => { window.forceBackgroundReject = true; window.setTestHidden(true); });
  await page.waitForFunction(() => document.querySelector('audio').src.includes('/retry.mp3'));
  await page.waitForFunction(() => document.querySelector('#notice-text').textContent.includes('回到本页会自动重试'));
  check(await page.evaluate(() => document.querySelector('audio').paused), 'background rejection leaves audio paused without another gesture');
  await page.evaluate(() => window.setTestHidden(false));
  await page.waitForFunction(() => {
    const audio = document.querySelector('audio');
    return audio.src.includes('/retry.mp3') && !audio.paused;
  }, null, { timeout: 6000 });
  check(await page.evaluate(() => document.querySelector('#notice').hidden), 'returning to the page clears the autoplay-blocked notice');

  check(errors.length === 0, `page errors: ${errors.join(', ')}`);
  return { audibleReasons: ['limited', 'unavailable', 'temporary'], announcementBeforeNext: true, missingRequestNotice: true, pauseUnloadAndResumePosition: true, cancelledAnnouncement: true, quotaResume: true, noEarlyQuotaRequests: true, pauseCancelsWait: true, pagehideRelease: true, emptyQueueRequestRecovery: true, temporaryAvailabilityBackoff: true, abortPendingGenerationAndIntent: true, cooldownLocalPeriod: true, cooldownManifestFallback: true, backgroundAutoplay: true, backgroundVisibleRetry: true, showCalls, resolveCalls, availabilityCalls, cooldownManifestCalls, errors };
}

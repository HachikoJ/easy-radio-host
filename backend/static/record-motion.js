export function createRecordMotion(stages, audio) {
  const surfaces = stages.map(stage => {
    const canvas = document.createElement('canvas');
    canvas.className = 'record-ripple';
    canvas.setAttribute('aria-hidden', 'true');
    stage.append(canvas);
    return { canvas, context: canvas.getContext('2d'), size: 0, stage, renderer: null };
  });
  let moving = false, frame = null, lastFrame = 0, phase = 0;
  let audioContext = null, source = null, stream = null, analyser = null;
  let frequencies = null, samples = null, energy = 0, bass = 0;
  const bands = new Float32Array(64);
  const ripples = [0, 0, 0, 0];

  function releaseAnalysis() {
    source?.disconnect(); source = null; analyser = null;
    stream?.getTracks().forEach(track => track.stop()); stream = null;
    energy = 0; bass = 0; ripples.fill(0); bands.fill(0);
    surfaces.forEach(({ canvas }) => { canvas.dataset.rhythm = 'ambient'; });
  }
  function analysePlayback() {
    const capture = audio.captureStream || audio.mozCaptureStream;
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!capture || !Context || analyser) return;
    try {
      stream = capture.call(audio);
      if (!stream.getAudioTracks().some(track => track.readyState === 'live' && !track.muted)) { releaseAnalysis(); return; }
      audioContext ||= new Context();
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 1024; analyser.smoothingTimeConstant = .75;
      frequencies = new Uint8Array(analyser.frequencyBinCount);
      samples = new Float32Array(analyser.fftSize);
      source = audioContext.createMediaStreamSource(stream);
      // Analysis is a side branch; the native audio element remains the only output.
      source.connect(analyser);
      audioContext.resume().catch(() => {});
    } catch { releaseAnalysis(); }
  }
  function measure() {
    const available = analyser && audioContext.state === 'running' && stream.getAudioTracks().some(track => !track.muted && track.readyState === 'live');
    surfaces.forEach(({ canvas }) => { canvas.dataset.rhythm = available ? 'audio' : 'ambient'; });
    if (!available) {
      for (let i = 0; i < bands.length; i++) bands[i] = .16 + .14 * Math.sin(i * .3 + phase * 1.7) ** 2;
      energy = .22; bass = .18;
      return false;
    }
    analyser.getByteFrequencyData(frequencies);
    analyser.getFloatTimeDomainData(samples);
    for (let i = 0; i < bands.length; i++) {
      const mirrored = i < 32 ? i : 63 - i;
      const bin = Math.round(Math.exp(Math.log(200) * mirrored / 31));
      bands[i] += (frequencies[bin] / 255 - bands[i]) * .35;
    }
    const lowBins = Math.max(2, Math.round(250 * analyser.fftSize / audioContext.sampleRate));
    let low = 0, power = 0;
    for (let i = 1; i <= lowBins; i++) low += frequencies[i] / 255;
    for (const sample of samples) power += sample * sample;
    energy += (Math.min(1, Math.sqrt(power / samples.length) * 4) - energy) * .25;
    const nextBass = low / lowBins;
    bass += (nextBass - bass) * (nextBass > bass ? .4 : .12);
    for (let i = ripples.length - 1; i > 0; i--) ripples[i] += (ripples[i - 1] - ripples[i]) * .22;
    ripples[0] = Math.min(1, energy * .6 + bass * .65);
    return true;
  }
  audio.addEventListener('loadstart', releaseAnalysis);
  audio.addEventListener('playing', () => { if (moving) analysePlayback(); });
  const resume = () => { if (moving) audioContext?.resume().catch(() => {}); };
  document.addEventListener('pointerdown', resume, { passive: true });
  document.addEventListener('keydown', resume);

  function draw(surface) {
    const { canvas, context, size } = surface;
    if (!size || !canvas.getClientRects().length) return;
    if (surface.renderer) {
      surface.renderer.render({ phase, energy, bass, bands, moving });
      return;
    }
    if (!context) return;
    const dark = document.documentElement.dataset.appearance === 'dark';
    context.clearRect(0, 0, size, size);
    const center = size / 2;
    // Closed, overlapping ribbons keep the contour fluid at every angle.
    for (let layer = 3; layer >= 0; layer--) {
      const points = [];
      const rhythmic = canvas.dataset.rhythm === 'audio';
      const swell = rhythmic ? ripples[layer] : .5 + .5 * Math.sin(phase * 2.1 - layer * .75);
      for (let i = 0; i < 160; i++) {
        const angle = i / 160 * Math.PI * 2;
        const wave = Math.sin(angle * 3 + phase * 1.15 - layer * .5) * .012
          + Math.sin(angle * 5 - phase * 1.6 + layer * .65) * .008
          + Math.sin(angle * 8 + phase * .8 - layer * .35) * .003;
        const radius = size * (.376 + layer * .023 + swell * .02 + wave * (.7 + swell * .5));
        points.push([center + Math.cos(angle) * radius, center + Math.sin(angle) * radius]);
      }
      context.beginPath();
      const last = points[points.length - 1], first = points[0];
      context.moveTo((last[0] + first[0]) / 2, (last[1] + first[1]) / 2);
      points.forEach((point, i) => {
        const next = points[(i + 1) % points.length];
        context.quadraticCurveTo(point[0], point[1], (point[0] + next[0]) / 2, (point[1] + next[1]) / 2);
      });
      context.closePath();
      const color = layer % 3 === 1 ? '196,119,145' : dark ? '97,196,201' : '64,151,160';
      context.fillStyle = `rgba(${color},${(dark ? .11 : .09) + swell * .045})`;
      context.fill();
      context.strokeStyle = `rgba(${color},${(dark ? .27 : .2) + swell * .12})`;
      context.lineWidth = Math.max(.7, size * .002);
      context.stroke();
    }
  }

  function paint() { surfaces.forEach(draw); }
  function tick(timestamp) {
    frame = null;
    if (!moving) return;
    if (timestamp - lastFrame >= 1000 / 30) {
      lastFrame = timestamp;
      phase = audio.currentTime;
      measure();
      paint();
    }
    frame = requestAnimationFrame(tick);
  }
  const observer = new ResizeObserver(entries => {
    for (const entry of entries) {
      const surface = surfaces.find(item => item.canvas === entry.target);
      const size = entry.contentRect.width;
      if (!size) continue;
      surface.size = size;
      const ratio = Math.min(devicePixelRatio || 1, 2);
      if (surface.renderer) surface.renderer.resize(size, ratio);
      else {
        surface.canvas.width = Math.round(size * ratio);
        surface.canvas.height = Math.round(size * ratio);
        surface.context.setTransform(ratio, 0, 0, ratio, 0, 0);
      }
      draw(surface);
    }
  });
  surfaces.forEach(({ canvas }) => observer.observe(canvas));
  new MutationObserver(paint).observe(document.documentElement, { attributes: true, attributeFilter: ['data-appearance'] });
  const revealed = new WeakSet();
  const reveal = (surface, webgl = false) => {
    if (revealed.has(surface)) return;
    revealed.add(surface);
    if (webgl) surface.stage.classList.add('record-webgl');
    surface.stage.classList.remove('record-booting');
    window.dispatchEvent(new Event('tingjian:record-ready'));
  };
  // Three.js 首次绘制前保持隐藏；若加载失败则只显示一次普通唱片，之后不再替换。
  import('./record-scene.js?v=20260911-6').then(({ createRecordScene }) => {
    for (const surface of surfaces) {
      const canvas = surface.canvas.cloneNode(false);
      try {
        const renderer = createRecordScene(canvas, surface.stage.querySelector('img'), () => reveal(surface, true));
        observer.unobserve(surface.canvas);
        surface.canvas.replaceWith(canvas);
        surface.canvas = canvas; surface.context = null; surface.renderer = renderer;
        observer.observe(canvas);
        if (surface.size) { renderer.resize(surface.size, Math.min(devicePixelRatio || 1, 2)); draw(surface); }
      } catch { reveal(surface); } /* Keep the canvas fallback when WebGL is unavailable. */
    }
  }).catch(() => surfaces.forEach(surface => reveal(surface)));

  return {
    setPlaying(value) {
      if (moving === value) return;
      moving = value;
      if (moving) {
        analysePlayback();
        audioContext?.resume().catch(() => {});
        frame = requestAnimationFrame(tick);
      } else {
        cancelAnimationFrame(frame); frame = null;
        releaseAnalysis();
        audioContext?.suspend().catch(() => {});
      }
    }
  };
}

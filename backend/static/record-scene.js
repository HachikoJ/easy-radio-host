import * as THREE from './vendor/three/three.module.min.js';

const TAU = Math.PI * 2;
const SEGMENTS = 192;
const EMPTY_BANDS = new Float32Array(64);

function ribbonGeometry() {
  const geometry = new THREE.BufferGeometry();
  const count = (SEGMENTS + 1) * 2;
  geometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(count * 3), 3).setUsage(THREE.DynamicDrawUsage));
  geometry.setAttribute('color', new THREE.BufferAttribute(new Float32Array(count * 3), 3));
  geometry.setAttribute('uv', new THREE.BufferAttribute(new Float32Array(count * 2), 2));
  const indices = [];
  const color = new THREE.Color();
  for (let i = 0; i <= SEGMENTS; i++) {
    const progress = i / SEGMENTS;
    color.setHSL((progress + .49) % 1, .98, .58);
    for (let edge = 0; edge < 2; edge++) {
      geometry.attributes.color.setXYZ(i * 2 + edge, color.r, color.g, color.b);
      geometry.attributes.uv.setXY(i * 2 + edge, progress, edge);
    }
    if (i < SEGMENTS) {
      const j = i * 2;
      indices.push(j, j + 1, j + 2, j + 1, j + 3, j + 2);
    }
  }
  geometry.setIndex(indices);
  return geometry;
}

const vertexShader = `
  varying vec3 tint;
  varying vec2 ribbon;
  void main() {
    tint = color;
    ribbon = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

function ribbonMaterial(glow, opacity) {
  return new THREE.ShaderMaterial({
    vertexColors: true,
    transparent: true,
    side: THREE.DoubleSide,
    depthWrite: false,
    blending: glow ? THREE.AdditiveBlending : THREE.NormalBlending,
    uniforms: { opacity: { value: opacity } },
    vertexShader,
    fragmentShader: `
      uniform float opacity;
      varying vec3 tint;
      varying vec2 ribbon;
      void main() {
        float coverage = ${glow
          ? 'pow(max(0.0, 1.0 - abs(ribbon.y * 2.0 - 1.0)), 2.4)'
          : '(0.12 + 0.52 * pow(ribbon.y, 1.4) + 0.30 * pow(1.0 - ribbon.y, 7.0))'};
        gl_FragColor = vec4(tint * ${glow ? '1.3' : '1.05'}, coverage * opacity);
      }
    `
  });
}

export function createRecordScene(canvas, artworkImage) {
  const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true, preserveDrawingBuffer: true, powerPreference: 'low-power' });
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, 1, .1, 30);
  camera.position.set(0, 4.8, 4.7);
  camera.lookAt(0, .1, 0);
  camera.zoom = 1.23;
  camera.updateProjectionMatrix();
  const disposable = [];
  let disposed = false;
  let initialized = false;
  let lastState = { phase: 0, energy: 0, bass: 0, bands: EMPTY_BANDS, moving: false };

  function mesh(geometry, material, parent = scene) {
    const object = new THREE.Mesh(geometry, material);
    disposable.push(geometry, material);
    parent.add(object);
    return object;
  }
  function flatRing(inner, outer, color, y, opacity = 1) {
    const ring = mesh(new THREE.RingGeometry(inner, outer, 128), new THREE.MeshBasicMaterial({ color, transparent: opacity < 1, opacity, side: THREE.DoubleSide, depthWrite: opacity === 1 }));
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = y;
    return ring;
  }

  // A physical dark platter preserves the luminous ribbons on light and dark pages.
  mesh(new THREE.CylinderGeometry(1.48, 1.44, .075, 128), new THREE.MeshBasicMaterial({ color: 0x070b17 })).position.y = -.07;
  flatRing(.90, 1.46, 0x131a31, -.025);
  flatRing(1.43, 1.445, 0x36bce0, -.018, .7);
  flatRing(.9, .915, 0x5dc6d8, .005, .7);
  const record = new THREE.Group();
  scene.add(record);
  record.position.y = .018;
  const vinyl = mesh(new THREE.CircleGeometry(.895, 128), new THREE.MeshBasicMaterial({ color: 0x0a0d14, side: THREE.DoubleSide }), record);
  vinyl.rotation.x = -Math.PI / 2;
  for (let i = 0; i < 9; i++) flatRing(.758 + i * .015, .7595 + i * .015, i % 2 ? 0x2b3242 : 0x52596b, .022, .48);
  const artworkMaterial = new THREE.MeshBasicMaterial({ color: 0xffffff, side: THREE.DoubleSide });
  const artwork = mesh(new THREE.CircleGeometry(.735, 128), artworkMaterial, record);
  artwork.rotation.x = -Math.PI / 2;
  artwork.position.y = .008;
  flatRing(.049, .073, 0xb4bed0, .032);
  const spindle = mesh(new THREE.CircleGeometry(.048, 32), new THREE.MeshBasicMaterial({ color: 0x060913, side: THREE.DoubleSide }));
  spindle.rotation.x = -Math.PI / 2;
  spindle.position.y = .034;

  let textureRequest = 0;
  function updateArtwork() {
    const url = artworkImage?.currentSrc || artworkImage?.src;
    if (!url) return;
    const request = ++textureRequest;
    new THREE.TextureLoader().load(url, texture => {
      if (disposed || request !== textureRequest) { texture.dispose(); return; }
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = Math.min(4, renderer.capabilities.getMaxAnisotropy());
      const image = texture.image;
      if (image.width > image.height) { texture.repeat.x = image.height / image.width; texture.offset.x = (1 - texture.repeat.x) / 2; }
      else { texture.repeat.y = image.width / image.height; texture.offset.y = (1 - texture.repeat.y) / 2; }
      artworkMaterial.map?.dispose();
      artworkMaterial.map = texture;
      artworkMaterial.needsUpdate = true;
      renderer.render(scene, camera);
    }, undefined, () => {});
  }
  const artworkObserver = new MutationObserver(updateArtwork);
  if (artworkImage) {
    artworkObserver.observe(artworkImage, { attributes: true, attributeFilter: ['src', 'srcset'] });
    artworkImage.addEventListener('load', updateArtwork);
  }
  updateArtwork();

  const layers = Array.from({ length: 4 }, (_, layer) => {
    const curtain = mesh(ribbonGeometry(), ribbonMaterial(false, .65 - layer * .055));
    const halo = mesh(ribbonGeometry(), ribbonMaterial(true, .56));
    const crest = mesh(ribbonGeometry(), ribbonMaterial(true, .95));
    for (const surface of [curtain, halo, crest]) {
      surface.frustumCulled = false;
      surface.renderOrder = layer + 2;
    }
    return { curtain, halo, crest, delayed: new Float32Array(SEGMENTS + 1) };
  });

  const ticksGeometry = new THREE.BufferGeometry();
  const ticks = new Float32Array(96 * 2 * 3);
  const tickColors = new Float32Array(ticks.length);
  const tickColor = new THREE.Color();
  for (let i = 0; i < 96; i++) {
    tickColor.setHSL((i / 96 + .49) % 1, .95, .67);
    for (let end = 0; end < 2; end++) tickColor.toArray(tickColors, i * 6 + end * 3);
  }
  ticksGeometry.setAttribute('position', new THREE.BufferAttribute(ticks, 3).setUsage(THREE.DynamicDrawUsage));
  ticksGeometry.setAttribute('color', new THREE.BufferAttribute(tickColors, 3));
  const ticksMaterial = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: .82 });
  const tickLines = new THREE.LineSegments(ticksGeometry, ticksMaterial);
  tickLines.frustumCulled = false;
  scene.add(tickLines);
  disposable.push(ticksGeometry, ticksMaterial);

  function bandAt(bands, angle) {
    const index = ((angle % TAU + TAU) % TAU) / TAU * bands.length;
    const floor = Math.floor(index), mix = index - floor;
    const sample = offset => bands[((offset % bands.length) + bands.length) % bands.length] || 0;
    const smooth = offset => (sample(offset - 1) + sample(offset) * 2 + sample(offset + 1)) * .25;
    const a = smooth(floor - 1), b = smooth(floor), c = smooth(floor + 1), d = smooth(floor + 2);
    // Periodic Catmull-Rom keeps the curtain smooth across FFT bins and the seam.
    const value = .5 * ((2 * b) + (-a + c) * mix + (2 * a - 5 * b + 4 * c - d) * mix ** 2 + (-a + 3 * b - 3 * c + d) * mix ** 3);
    return Math.max(0, Math.min(1, value));
  }

  function render(state = lastState) {
    if (disposed) return;
    const advance = !initialized || state.phase !== lastState.phase;
    initialized = true;
    lastState = state;
    const { phase = 0, energy = 0, bass = 0, bands = EMPTY_BANDS } = state;
    record.rotation.y = phase * -.23;
    for (let layer = 0; layer < layers.length; layer++) {
      const { curtain, halo, crest, delayed } = layers[layer];
      const positions = curtain.geometry.attributes.position;
      const haloPositions = halo.geometry.attributes.position;
      const crestPositions = crest.geometry.attributes.position;
      for (let i = 0; i <= SEGMENTS; i++) {
        const angle = i / SEGMENTS * TAU;
        const frequency = bandAt(bands, angle + layer * .2);
        const neighboring = (bandAt(bands, angle - .1 + layer * .2) + bandAt(bands, angle + .1 + layer * .2)) * .5;
        const target = frequency * .65 + neighboring * .35;
        if (advance) delayed[i] += (target - delayed[i]) * (.34 - layer * .055);
        const drift = .5 + .5 * Math.sin(angle * 3 + phase * 1.65 - layer * .9);
        const detail = .5 + .5 * Math.sin(angle * 7 - phase * 2.05 + layer);
        const amplitude = .025 + energy * .15 + bass * .12;
        const height = .055 + (drift * .68 + detail * .32) * amplitude + delayed[i] * (.37 + layer * .05);
        const radius = .98 + layer * .105 + Math.sin(angle * 4 + phase - layer) * (.009 + bass * .022);
        const cosine = Math.cos(angle), sine = Math.sin(angle);
        positions.setXYZ(i * 2, cosine * radius, -.012 + layer * .005, sine * radius);
        positions.setXYZ(i * 2 + 1, cosine * (radius + .035), height, sine * (radius + .035));
        haloPositions.setXYZ(i * 2, cosine * (radius + .035), height - .063, sine * (radius + .035));
        haloPositions.setXYZ(i * 2 + 1, cosine * (radius + .035), height + .063, sine * (radius + .035));
        crestPositions.setXYZ(i * 2, cosine * (radius + .035), height - .009, sine * (radius + .035));
        crestPositions.setXYZ(i * 2 + 1, cosine * (radius + .035), height + .009, sine * (radius + .035));
      }
      positions.needsUpdate = true;
      haloPositions.needsUpdate = true;
      crestPositions.needsUpdate = true;
    }
    for (let i = 0; i < 96; i++) {
      const angle = i / 96 * TAU;
      const level = bandAt(bands, angle);
      const length = .02 + level * .055 + (i % 4 === 0 ? .018 : 0);
      const cosine = Math.cos(angle), sine = Math.sin(angle);
      ticksGeometry.attributes.position.setXYZ(i * 2, cosine * 1.36, -.008, sine * 1.36);
      ticksGeometry.attributes.position.setXYZ(i * 2 + 1, cosine * (1.36 + length), -.008 + level * .055, sine * (1.36 + length));
    }
    ticksGeometry.attributes.position.needsUpdate = true;
    renderer.render(scene, camera);
  }

  function restoreContext() {
    if (!disposed) renderer.render(scene, camera);
  }
  canvas.addEventListener('webglcontextrestored', restoreContext);

  return {
    render,
    resize(size, ratio = 1) {
      if (disposed || !size) return;
      renderer.setPixelRatio(Math.min(ratio, 2));
      renderer.setSize(size, size, false);
      render(lastState);
    },
    dispose() {
      disposed = true;
      canvas.removeEventListener('webglcontextrestored', restoreContext);
      artworkObserver.disconnect();
      artworkImage?.removeEventListener('load', updateArtwork);
      artworkMaterial.map?.dispose();
      disposable.forEach(resource => resource.dispose());
      renderer.dispose();
    }
  };
}

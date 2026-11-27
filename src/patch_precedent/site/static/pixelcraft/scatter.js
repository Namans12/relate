// Brush radius and tile size are measured in source-image pixels.
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');

export async function preparePanel(panel, poster, { grain, hold, hoverDrift, signal }) {
  const brush = hold ? 82 : 100;
  const impulseScale = hold ? .72 : 1;
  const closeupTravelLimit = 52;
  const image = panel.querySelector('img');
  try {
    await image.decode();
  } catch (error) {
    if (signal.aborted) return;
    throw error;
  }
  if (signal.aborted) return;
  panel.style.setProperty('--source-width', image.naturalWidth);
  panel.style.setProperty('--source-height', image.naturalHeight);
  const canvas = panel.querySelector('canvas');
  const context = canvas.getContext('2d');
  if (!context) return;

  const live = new Map();
  const columns = Math.ceil(image.naturalWidth / grain);
  let crop, scale, frame = 0, lastTime = 0, previous = null;
  let keyboardPoint, hoverPoint, lastPointerMotion = 0;

  function reset() {
    cancelAnimationFrame(frame);
    frame = 0;
    lastTime = 0;
    previous = null;
    hoverPoint = null;
    live.clear();
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
  }

  function resize() {
    reset();
    const bounds = panel.getBoundingClientRect();
    const css = getComputedStyle(panel);
    const value = key => Number(css.getPropertyValue('--' + key));
    crop = { x: value('left'), y: value('top'), w: value('width'), h: value('height') };
    scale = bounds.width / crop.w;
    const density = Math.min(devicePixelRatio || 1, 2);
    canvas.width = Math.round(bounds.width * density);
    canvas.height = Math.round(bounds.height * density);
    keyboardPoint = { x: crop.x + crop.w * .65, y: crop.y + crop.h * .45 };
  }

  function seed(id) {
    const hash = Math.sin(id * 127.1 + 311.7) * 43758.5453;
    return hash - Math.floor(hash);
  }

  function hoverNoise(tick, channel) {
    const step = Math.floor(tick);
    const t = tick - step;
    const blend = t * t * (3 - 2 * t);
    const start = seed(channel + step);
    const end = seed(channel + step + 1);
    return 2 * (start + (end - start) * blend) - 1;
  }

  function disturb(x, y, driftX, driftY) {
    const left = Math.max(0, Math.floor((x - brush) / grain));
    const top = Math.max(0, Math.floor((y - brush) / grain));
    const right = Math.min(columns - 1, Math.floor((x + brush) / grain));
    const bottom = Math.min(Math.floor((image.naturalHeight - grain) / grain), Math.floor((y + brush) / grain));

    for (let row = top; row <= bottom; row++) {
      for (let col = left; col <= right; col++) {
        const ox = col * grain, oy = row * grain;
        const dx = ox + grain / 2 - x, dy = oy + grain / 2 - y;
        const distance = Math.hypot(dx, dy);
        if (distance >= brush) continue;
        const id = row * columns + col;
        let chip = live.get(id);
        if (!chip) {
          chip = { ox, oy, dx: 0, dy: 0, vx: 0, vy: 0, noise: seed(id), angle: seed(id + 17) * Math.PI * 2 };
          live.set(id, chip);
        }
        const force = (1 - distance / brush) ** 1.3 * (210 + chip.noise * 430) * impulseScale;
        const divisor = Math.max(1, distance);
        chip.vx = chip.vx * .45 + force * (dx / divisor + Math.cos(chip.angle) * .95) + driftX * force * .2;
        chip.vy = chip.vy * .45 + force * (dy / divisor + Math.sin(chip.angle) * .95) + driftY * force * .2;
      }
    }
  }

  const holeColor = getComputedStyle(canvas).getPropertyValue('--pixelcraft-bg').trim() || '#f4f1e8';
  function animate(time) {
    const dt = Math.min((time - (lastTime || time - 16.67)) / 1000, .033);
    lastTime = time;
    const sx = canvas.width / crop.w, sy = canvas.height / crop.h;
    context.setTransform(1, 0, 0, 1, 0, 0);
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.setTransform(sx, 0, 0, sy, -crop.x * sx, -crop.y * sy);
    const drag = Math.exp(-7.6 * dt);
    context.fillStyle = holeColor;
    context.beginPath();
    for (const [id, p] of live) {
      // In the close-up, keep a small opening around a resting pointer.
      let targetX = 0, targetY = 0;
      if (hoverPoint) {
        const dx = p.ox + grain / 2 - hoverPoint.x;
        const dy = p.oy + grain / 2 - hoverPoint.y;
        const distance = Math.hypot(dx, dy);
        const push = Math.max(0, 1 - distance / brush) ** 2 * brush * .38;
        targetX = push * (dx / Math.max(1, distance) + .65 * Math.cos(p.angle));
        targetY = push * (dy / Math.max(1, distance) + .65 * Math.sin(p.angle));
      }
      p.vx = (p.vx + 54 * (targetX - p.dx) * dt) * drag;
      p.vy = (p.vy + 54 * (targetY - p.dy) * dt) * drag;
      p.dx += p.vx * dt;
      p.dy += p.vy * dt;
      if (Math.abs(p.dx) + Math.abs(p.dy) < .4 && Math.abs(p.vx) + Math.abs(p.vy) < 3) {
        live.delete(id);
        continue;
      }
      context.rect(p.ox, p.oy, grain + .1, grain + .1);
    }
    context.fill();
    // Blend in only after the pointer pauses. Drift is visual and never feeds the spring.
    const stillTime = time - lastPointerMotion;
    const driftMix = hoverDrift && hoverPoint ? Math.min(1, Math.max(0, (stillTime - 110) / 220)) : 0;
    const seconds = time / 1000;
    for (const p of live.values()) {
      let offsetX = p.dx, offsetY = p.dy;
      if (driftMix > 0) {
        const distance = Math.hypot(p.ox + grain / 2 - hoverPoint.x, p.oy + grain / 2 - hoverPoint.y);
        const amplitude = Math.min(grain * 1.5, 10) * driftMix * Math.max(0, 1 - distance / brush);
        const phase = seconds * (5 + 5 * p.noise) + p.angle;
        const tick = seconds * (7 + 4 * p.noise) + p.angle;
        const channel = p.noise * 8192;
        offsetX += amplitude * (.65 * Math.sin(phase) + .35 * hoverNoise(tick, channel));
        offsetY += amplitude * (.65 * Math.cos(phase * 1.23) + .35 * hoverNoise(tick + .37, channel + 293.7));
      }
      // Ease strong impulses toward a radial limit without clipping their direction.
      const travelScale = hold ? closeupTravelLimit / Math.hypot(closeupTravelLimit, offsetX, offsetY) : 1;
      const dx = offsetX * travelScale, dy = offsetY * travelScale;
      const inset = Math.min(.5, (Math.abs(dx) + Math.abs(dy)) * .012);
      context.drawImage(image, p.ox, p.oy, grain, grain,
        p.ox + dx + inset, p.oy + dy + inset, grain - 2 * inset, grain - 2 * inset);
    }
    if (live.size) frame = requestAnimationFrame(animate);
    else reset();
  }

  function scatter(point) {
    if (reducedMotion.matches || !scale) return;
    const dx = previous ? point.x - previous.x : 0;
    const dy = previous ? point.y - previous.y : 0;
    const length = Math.hypot(dx, dy);
    const steps = Math.max(1, Math.min(10, Math.ceil(length / (brush * .4))));
    for (let step = 1; step <= steps; step++) {
      const t = 1 - step / steps;
      disturb(point.x - dx * t, point.y - dy * t, dx / Math.max(1, length), dy / Math.max(1, length));
    }
    previous = point;
    if (!frame) frame = requestAnimationFrame(animate);
  }

  function pointer(event) {
    if (!event.isPrimary || !scale) return;
    const bounds = panel.getBoundingClientRect();
    const point = { x: crop.x + (event.clientX - bounds.left) / scale, y: crop.y + (event.clientY - bounds.top) / scale };
    if (hoverDrift && (!hoverPoint || point.x !== hoverPoint.x || point.y !== hoverPoint.y)) {
      lastPointerMotion = performance.now();
    }
    if (hold && !reducedMotion.matches) hoverPoint = point;
    scatter(point);
  }

  panel.addEventListener('pointermove', pointer, { signal });
  panel.addEventListener('pointerdown', pointer, { signal });
  for (const event of ['pointerleave', 'pointercancel', 'pointerup']) {
    panel.addEventListener(event, input => {
      previous = null;
      if (hoverDrift && event === 'pointerup' && input.pointerType === 'mouse') return;
      hoverPoint = null;
    }, { signal });
  }
  poster.addEventListener('keydown', event => {
    if (!scale || reducedMotion.matches || event.altKey || event.metaKey || event.ctrlKey) return;
    const directions = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1], ' ': [0, 0] };
    const direction = directions[event.key];
    if (!direction) return;
    event.preventDefault();
    keyboardPoint.x = Math.max(crop.x, Math.min(crop.x + crop.w, keyboardPoint.x + direction[0] * 40));
    keyboardPoint.y = Math.max(crop.y, Math.min(crop.y + crop.h, keyboardPoint.y + direction[1] * 40));
    hoverPoint = null;
    scatter(keyboardPoint);
    previous = null;
  }, { signal });
  reducedMotion.addEventListener('change', reset, { signal });
  document.addEventListener('visibilitychange', () => { if (document.hidden) reset(); }, { signal });
  resize();
  const observer = new ResizeObserver(resize);
  observer.observe(panel);
  signal.addEventListener('abort', () => {
    observer.disconnect();
    reset();
  }, { once: true });
}

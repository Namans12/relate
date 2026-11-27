// Draws the "C" lockup (mark + title, failing-test line ending as the final dot).
// Adapted from Gemini's splash-c.html; only the title typography is parameterised.
const INK = '#1B1F2A', PAPER = '#FAF7F2', DEEP = '#B4472A', BRIGHT = '#E36B47';

function advances(ctx, text, track) {
  const out = [];
  for (let i = 0; i < text.length; i++) {
    const adv = i === 0 ? ctx.measureText(text[0]).width
      : ctx.measureText(text.slice(0, i + 1)).width - ctx.measureText(text.slice(0, i)).width;
    out.push(adv + (i < text.length - 1 ? track : 0));
  }
  return out;
}
const widthOf = (ctx, t, k) => advances(ctx, t, k).reduce((a, b) => a + b, 0);
function drawTracked(ctx, text, x, y, track) {
  const adv = advances(ctx, text, track); let cx = x;
  for (let i = 0; i < text.length; i++) { ctx.fillText(text[i], cx, y); cx += adv[i]; }
}

// Mark geometry shared by both lockups. Sizes are tuned for a 460px tile.
function markGeometry(mx, my, ms) {
  const P = (x, y) => [mx + x * ms, my + y * ms];
  return { mx, my, ms, a: P(0.26, 0.28), d: P(0.51, 0.53), c1: P(0.76, 0.28), c3: P(0.26, 0.77), ringR: 66, ringStroke: 24 };
}

// Tile and the three spokes from the ring to the page and the two check nodes.
function markBase(g, m) {
  g.fillStyle = INK; g.beginPath(); g.roundRect(m.mx, m.my, m.ms, m.ms, 100); g.fill();
  const [dx, dy] = m.d, outer = m.ringR + m.ringStroke / 2;
  g.lineWidth = 14; g.lineCap = 'round'; g.strokeStyle = PAPER;
  for (const [nx, ny] of [m.a, m.c1, m.c3]) {
    const a = Math.atan2(ny - dy, nx - dx);
    g.beginPath(); g.moveTo(dx + Math.cos(a) * outer, dy + Math.sin(a) * outer); g.lineTo(nx, ny); g.stroke();
  }
  return outer;
}

// Page node, ring and check nodes, drawn over the spokes.
function markTop(g, m) {
  const [ax, ay] = m.a, [dx, dy] = m.d;
  const pw = 80, ph = 94;
  g.fillStyle = PAPER; g.beginPath(); g.roundRect(ax - pw / 2, ay - ph / 2, pw, ph, 13); g.fill();
  g.fillStyle = INK; g.beginPath(); g.roundRect(ax - 22, ay - 16, 32, 9, 4); g.roundRect(ax - 22, ay + 4, 44, 9, 4); g.fill();
  g.fillStyle = INK; g.beginPath(); g.arc(dx, dy, m.ringR, 0, Math.PI * 2); g.fill();
  g.lineWidth = m.ringStroke; g.strokeStyle = BRIGHT; g.beginPath(); g.arc(dx, dy, m.ringR, 0, Math.PI * 2); g.stroke();
  g.fillStyle = PAPER; for (const [nx, ny] of [m.c1, m.c3]) { g.beginPath(); g.arc(nx, ny, 28, 0, Math.PI * 2); g.fill(); }
}

function loadType(type) {
  const t = Object.assign({ family: 'Fraunces', w1: 600, w2: 700, s1: 122, s2: 210, k1: -2.4, k2: -5.4, cap: 0.70, varSettings: '' }, type);
  return Promise.all([document.fonts.load(`${t.w1} ${t.s1}px "${t.family}"`), document.fonts.load(`${t.w2} ${t.s2}px "${t.family}"`)]).then(() => t);
}

export async function drawC(type) {
  const t = await loadType(type);
  const W = 2160, H = 760, c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.fillStyle = PAPER; g.fillRect(0, 0, W, H);

  const ms = 460, gap = 92;
  const f1 = `${t.w1} ${t.s1}px "${t.family}"`, f2 = `${t.w2} ${t.s2}px "${t.family}"`;
  g.textBaseline = 'alphabetic';
  g.font = f2; const w2 = widthOf(g, 'Precedent', t.k2);
  const dotR = 21, dotGap = Math.round(t.s2 * 0.2);
  const lockupW = ms + gap + w2 + dotGap + dotR;
  const mx = (W - lockupW) / 2, my = (H - ms) / 2, tx = mx + ms + gap;

  const m = markGeometry(mx, my, ms);
  const ringOuterR = markBase(g, m);
  const [dx, dy] = m.d;
  // title baselines: line 2 baseline sits at 78% of the mark; line 1 above it by line-1 cap + leading
  const baseY2 = my + ms * 0.78;
  const baseY1 = baseY2 - t.s2 * t.cap - t.s1 * 0.42;
  const dotX = tx + w2 + dotGap, dotY = baseY2 - dotR + 2, conduitY = my + ms * 0.9;
  const ea = Math.PI / 4, sx = dx + Math.cos(ea) * ringOuterR, sy = dy + Math.sin(ea) * ringOuterR;
  const cornerX = sx + (conduitY - sy), tileRight = mx + ms;
  g.lineWidth = 10; g.lineCap = 'butt'; g.strokeStyle = BRIGHT;
  g.beginPath(); g.moveTo(sx, sy); g.arcTo(cornerX, conduitY, tileRight, conduitY, 24); g.lineTo(tileRight, conduitY); g.stroke();
  g.strokeStyle = DEEP;
  g.beginPath(); g.moveTo(tileRight, conduitY); g.arcTo(dotX, conduitY, dotX, dotY, 28); g.lineTo(dotX, dotY); g.stroke();
  markTop(g, m);
  g.fillStyle = INK;
  g.font = f1; drawTracked(g, 'Patch', tx + 4, baseY1, t.k1);
  g.font = f2; drawTracked(g, 'Precedent', tx, baseY2, t.k2);
  g.fillStyle = BRIGHT; g.beginPath(); g.arc(dotX, dotY, dotR, 0, Math.PI * 2); g.fill();
  return c;
}

// Narrow-screen lockup: the mark above a centred two-line title, no conduit.
export async function drawCStacked(type) {
  const t = await loadType(type);
  const W = 1300, ms = 460, top = 70, gapMark = 76, bottom = 90;
  const f1 = `${t.w1} ${t.s1}px "${t.family}"`, f2 = `${t.w2} ${t.s2}px "${t.family}"`;
  const probe = document.createElement('canvas').getContext('2d');
  probe.font = f1; const w1 = widthOf(probe, 'Patch', t.k1);
  probe.font = f2; const w2 = widthOf(probe, 'Precedent', t.k2);
  const dotR = 21, dotGap = 16;
  const baseY1 = top + ms + gapMark + t.s1 * t.cap;
  const baseY2 = baseY1 + t.s1 * 0.42 + t.s2 * t.cap;
  const H = Math.round(baseY2 + bottom);
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.fillStyle = PAPER; g.fillRect(0, 0, W, H);
  g.textBaseline = 'alphabetic';
  const m = markGeometry((W - ms) / 2, top, ms);
  markBase(g, m); markTop(g, m);
  g.fillStyle = INK;
  g.font = f1; drawTracked(g, 'Patch', (W - w1) / 2, baseY1, t.k1);
  const x2 = (W - (w2 + dotGap + dotR * 2)) / 2;
  g.font = f2; drawTracked(g, 'Precedent', x2, baseY2, t.k2);
  g.fillStyle = BRIGHT; g.beginPath(); g.arc(x2 + w2 + dotGap + dotR, baseY2 - dotR + 2, dotR, 0, Math.PI * 2); g.fill();
  return c;
}

export const FONTS = {
  fraunces: { label: 'Fraunces (current)', family: 'Fraunces', w1: 600, w2: 700, s1: 122, s2: 210, k1: -2.4, k2: -5.4, cap: 0.70 },
  instrument: { label: 'Instrument Serif', family: 'Instrument Serif', w1: 400, w2: 400, s1: 140, s2: 250, k1: -1.5, k2: -4, cap: 0.66 },
  playfair: { label: 'Playfair Display', family: 'Playfair Display', w1: 600, w2: 800, s1: 120, s2: 205, k1: -1.5, k2: -4.5, cap: 0.71 },
  dmserif: { label: 'DM Serif Display', family: 'DM Serif Display', w1: 400, w2: 400, s1: 124, s2: 214, k1: -1, k2: -4, cap: 0.70 },
};

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

export async function drawC(type) {
  const t = Object.assign({ family: 'Fraunces', w1: 600, w2: 700, s1: 122, s2: 210, k1: -2.4, k2: -5.4, cap: 0.70, varSettings: '' }, type);
  await Promise.all([document.fonts.load(`${t.w1} ${t.s1}px "${t.family}"`), document.fonts.load(`${t.w2} ${t.s2}px "${t.family}"`)]);
  const W = 2160, H = 760, c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.fillStyle = PAPER; g.fillRect(0, 0, W, H);

  const ms = 460, mr = 100, gap = 92;
  const f1 = `${t.w1} ${t.s1}px "${t.family}"`, f2 = `${t.w2} ${t.s2}px "${t.family}"`;
  g.textBaseline = 'alphabetic';
  g.font = f2; const w2 = widthOf(g, 'Precedent', t.k2);
  const dotR = 21, dotGap = Math.round(t.s2 * 0.2);
  const lockupW = ms + gap + w2 + dotGap + dotR;
  const mx = (W - lockupW) / 2, my = (H - ms) / 2, tx = mx + ms + gap;

  g.fillStyle = INK; g.beginPath(); g.roundRect(mx, my, ms, ms, mr); g.fill();
  const P = (x, y) => [mx + x * ms, my + y * ms];
  const [ax, ay] = P(0.26, 0.28), [dx, dy] = P(0.51, 0.53), [c1x, c1y] = P(0.76, 0.28), [c3x, c3y] = P(0.26, 0.77);
  const ringR = 66, ringStroke = 24, ringOuterR = ringR + ringStroke / 2;
  g.lineWidth = 14; g.lineCap = 'round'; g.strokeStyle = PAPER;
  for (const [nx, ny] of [[ax, ay], [c1x, c1y], [c3x, c3y]]) {
    const a = Math.atan2(ny - dy, nx - dx);
    g.beginPath(); g.moveTo(dx + Math.cos(a) * ringOuterR, dy + Math.sin(a) * ringOuterR); g.lineTo(nx, ny); g.stroke();
  }
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
  const pw = 80, ph = 94;
  g.fillStyle = PAPER; g.beginPath(); g.roundRect(ax - pw / 2, ay - ph / 2, pw, ph, 13); g.fill();
  g.fillStyle = INK; g.beginPath(); g.roundRect(ax - 22, ay - 16, 32, 9, 4); g.roundRect(ax - 22, ay + 4, 44, 9, 4); g.fill();
  g.fillStyle = INK; g.beginPath(); g.arc(dx, dy, ringR, 0, Math.PI * 2); g.fill();
  g.lineWidth = ringStroke; g.strokeStyle = BRIGHT; g.beginPath(); g.arc(dx, dy, ringR, 0, Math.PI * 2); g.stroke();
  g.fillStyle = PAPER; for (const [nx, ny] of [[c1x, c1y], [c3x, c3y]]) { g.beginPath(); g.arc(nx, ny, 28, 0, Math.PI * 2); g.fill(); }
  g.fillStyle = INK;
  g.font = f1; drawTracked(g, 'Patch', tx + 4, baseY1, t.k1);
  g.font = f2; drawTracked(g, 'Precedent', tx, baseY2, t.k2);
  g.fillStyle = BRIGHT; g.beginPath(); g.arc(dotX, dotY, dotR, 0, Math.PI * 2); g.fill();
  return c;
}

export const FONTS = {
  fraunces: { label: 'Fraunces (current)', family: 'Fraunces', w1: 600, w2: 700, s1: 122, s2: 210, k1: -2.4, k2: -5.4, cap: 0.70 },
  instrument: { label: 'Instrument Serif', family: 'Instrument Serif', w1: 400, w2: 400, s1: 140, s2: 250, k1: -1.5, k2: -4, cap: 0.66 },
  playfair: { label: 'Playfair Display', family: 'Playfair Display', w1: 600, w2: 800, s1: 120, s2: 205, k1: -1.5, k2: -4.5, cap: 0.71 },
  dmserif: { label: 'DM Serif Display', family: 'DM Serif Display', w1: 400, w2: 400, s1: 124, s2: 214, k1: -1, k2: -4, cap: 0.70 },
};

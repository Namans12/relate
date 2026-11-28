// Intro page: the pixelcraft lockup, and the Enter, Escape and click routes to home.html.
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
// The inline 1.5 s fallback in intro.html may already have swapped #artslot for the still
// lockup, so always look the slot up again rather than holding the original node.
const currentSlot = () => document.getElementById('artslot');
const ready = () => requestAnimationFrame(() => document.body.classList.add('ready'));

function showStill() {
  const slot = currentSlot();
  if (!slot || slot.classList.contains('still')) return;
  const img = new Image();
  img.src = 'lockup.png';
  img.alt = 'Patch Precedent';
  img.id = 'artslot';
  img.className = 'still';
  slot.replaceWith(img);
}

try {
  // Offline, the web font never arrives; drawing with a fallback face would misrender the title.
  const fontOk = !reduce && (await document.fonts.load('800 100px "Playfair Display"')).length > 0
    && document.fonts.check('800 100px "Playfair Display"');
  if (reduce || !fontOk) {
    showStill();
  } else {
    await import('./pixelcraft/pixelcraft-banner.js');
    const { drawC, drawCStacked, FONTS } = await import('./c-art.js');
    const stacked = matchMedia('(max-width: 599px)').matches;
    const canvas = await (stacked ? drawCStacked : drawC)(FONTS.playfair);
    const art = document.createElement('pixelcraft-banner');
    // Until its image decodes, the banner's panel falls back to a 1:1 shape, which pushes
    // the Enter button off short screens and then jumps it back up. These custom
    // properties inherit into the shadow root and give the panel its real shape at once.
    art.style.setProperty('--source-width', canvas.width);
    art.style.setProperty('--source-height', canvas.height);
    art.setAttribute('variant', 'hover-drift');
    art.setAttribute('block-size', stacked ? '6' : '8');
    art.setAttribute('alt', 'Patch Precedent');
    art.setAttribute('src', canvas.toDataURL('image/png'));
    // A late banner upgrades the fallback still in place.
    currentSlot().replaceWith(art);
  }
} catch (err) {
  console.error(err);
  showStill();
}
ready();

const btn = document.getElementById('enter');
let leaving = false;
const go = () => {
  if (leaving) return; leaving = true;
  document.body.classList.add('leaving');
  setTimeout(() => { location.href = 'home.html'; }, reduce ? 0 : 450);
};
btn.addEventListener('click', e => { e.preventDefault(); go(); });
// keyboard Enter shows the same slide and press as the mouse, then enters
// (a keyup without a keydown on this page, such as one that began elsewhere, does nothing)
let armed = false;
addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.repeat && !e.target.closest('a')) {
    e.preventDefault(); armed = true; btn.classList.add('kbd', 'kbd-down');
  }
  if (e.key === 'Escape') go();
});
addEventListener('keyup', e => {
  if (e.key === 'Enter' && armed && !e.target.closest('a')) {
    armed = false; btn.classList.remove('kbd-down'); setTimeout(go, reduce ? 0 : 220);
  }
});

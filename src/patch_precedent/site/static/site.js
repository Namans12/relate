// Reveal on scroll, copy buttons and the mobile menu. Everything works without it.
(() => {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;

  const items = document.querySelectorAll('.reveal');
  if (!('IntersectionObserver' in window) || reduce) {
    items.forEach(el => el.classList.add('in'));
  } else {
    const io = new IntersectionObserver(entries => {
      for (const e of entries) if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
    }, { rootMargin: '0px 0px -8% 0px' });
    items.forEach(el => io.observe(el));
  }

  const status = document.getElementById('sr-status');
  const legacyCopy = text => {
    const ta = document.createElement('textarea');
    ta.value = text; ta.setAttribute('readonly', ''); ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.append(ta); ta.select();
    let ok = false;
    try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
    ta.remove();
    return ok;
  };
  document.addEventListener('click', async e => {
    const btn = e.target.closest('[data-copy]');
    if (!btn) return;
    const box = btn.closest('.code') || btn.parentElement;
    const src = box.querySelector('[data-verbatim]');
    if (!src) return;
    const text = src.textContent.replace(/\n$/, '');
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (err) { ok = legacyCopy(text); }
    if (!ok) return;
    const label = btn.dataset.label || btn.textContent;
    btn.dataset.label = label;
    btn.textContent = 'Copied';
    if (status) status.textContent = 'Copied';
    clearTimeout(btn._t);
    btn._t = setTimeout(() => { btn.textContent = label; if (status) status.textContent = ''; }, 1500);
  });

  const menuBtn = document.querySelector('.menu-btn');
  const panel = document.getElementById('menu-panel');
  if (menuBtn && panel) {
    const set = open => {
      menuBtn.setAttribute('aria-expanded', String(open));
      menuBtn.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
      panel.hidden = !open;
    };
    menuBtn.addEventListener('click', () => set(panel.hidden));
    panel.addEventListener('click', e => { if (e.target.closest('a')) set(false); });
    addEventListener('keydown', e => { if (e.key === 'Escape' && !panel.hidden) { set(false); menuBtn.focus(); } });
    matchMedia('(min-width: 721px)').addEventListener('change', e => { if (e.matches) set(false); });
  }
})();

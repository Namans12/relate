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

  // carousel
  document.querySelectorAll('[data-carousel]').forEach(root => {
    const track = root.querySelector('[data-track]');
    const cards = [...track.querySelectorAll('[data-card]')];
    const prev = root.querySelector('[data-prev]');
    const next = root.querySelector('[data-next]');
    const dotsBox = root.querySelector('[data-dots]');
    const dots = cards.map((_, i) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.setAttribute('aria-label', 'Go to patch ' + (i + 1) + ' of ' + cards.length);
      b.addEventListener('click', () => go(i));
      dotsBox.append(b);
      return b;
    });
    const behavior = () => (reduce ? 'auto' : 'smooth');
    const go = i => {
      const c = cards[Math.max(0, Math.min(cards.length - 1, i))];
      track.scrollTo({ left: c.offsetLeft - cards[0].offsetLeft, behavior: behavior() });
    };
    const index = () => {
      const x = track.scrollLeft + cards[0].offsetLeft;
      let best = 0;
      cards.forEach((c, i) => { if (Math.abs(c.offsetLeft - x) < Math.abs(cards[best].offsetLeft - x)) best = i; });
      return best;
    };
    const sync = () => {
      const max = track.scrollWidth - track.clientWidth - 2;
      const i = track.scrollLeft >= max ? cards.length - 1 : index();
      dots.forEach((d, j) => d.setAttribute('aria-current', String(j === i)));
      prev.disabled = track.scrollLeft <= 2;
      next.disabled = track.scrollLeft >= max;
    };
    prev.addEventListener('click', () => go(index() - 1));
    next.addEventListener('click', () => go(index() + 1));
    track.addEventListener('keydown', e => {
      if (e.target !== track) return;
      if (e.key === 'ArrowRight') { e.preventDefault(); go(index() + 1); }
      if (e.key === 'ArrowLeft') { e.preventDefault(); go(index() - 1); }
    });
    track.addEventListener('scroll', () => requestAnimationFrame(sync), { passive: true });
    addEventListener('resize', sync);
    sync();
  });

  // tabs
  document.querySelectorAll('[data-tabs]').forEach(root => {
    const tabs = [...root.querySelectorAll('[role="tab"]')];
    const panels = tabs.map(t => document.getElementById(t.getAttribute('aria-controls')));
    const select = (i, focus) => {
      tabs.forEach((t, j) => {
        t.setAttribute('aria-selected', String(i === j));
        t.tabIndex = i === j ? 0 : -1;
        panels[j].hidden = i !== j;
      });
      if (focus) tabs[i].focus();
    };
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => select(i, false));
      t.addEventListener('keydown', e => {
        const n = tabs.length;
        const map = { ArrowRight: (i + 1) % n, ArrowLeft: (i + n - 1) % n, Home: 0, End: n - 1 };
        if (e.key in map) { e.preventDefault(); select(map[e.key], true); }
      });
    });
    select(0, false);
  });

  // recorded run replay
  document.querySelectorAll('[data-replay]').forEach(pre => {
    const lines = [...pre.querySelectorAll('.t-line')];
    const panel = pre.closest('.term');
    const play = panel.querySelector('[data-play]');
    const skip = panel.querySelector('[data-skip]');
    const TOTAL = 12;
    const last = lines.length ? Math.max(...lines.map(l => parseFloat(l.dataset.t) || 0)) : 0;
    const scale = last > 0 ? TOTAL / last : 0;
    let timers = [];
    let played = false;
    const stop = () => { timers.forEach(clearTimeout); timers = []; };
    const showAll = () => {
      stop();
      pre.classList.remove('replaying');
      lines.forEach(l => l.classList.remove('on'));
      pre.scrollTop = pre.scrollHeight;
      play.textContent = played ? 'Replay' : 'Play';
    };
    const start = () => {
      stop();
      played = true;
      if (reduce) { showAll(); return; }
      pre.classList.add('replaying');
      lines.forEach(l => l.classList.remove('on'));
      play.textContent = 'Replay';
      lines.forEach(l => {
        timers.push(setTimeout(() => {
          l.classList.add('on');
          pre.scrollTop = Math.max(0, l.offsetTop + l.offsetHeight + 20 - pre.clientHeight);
        }, (parseFloat(l.dataset.t) || 0) * scale * 1000));
      });
      timers.push(setTimeout(() => { pre.classList.remove('replaying'); lines.forEach(l => l.classList.remove('on')); pre.scrollTop = pre.scrollHeight; }, TOTAL * 1000 + 300));
    };
    play.addEventListener('click', start);
    skip.addEventListener('click', () => { played = true; showAll(); });

    let want = false;
    const io = 'IntersectionObserver' in window ? new IntersectionObserver(es => {
      for (const e of es) if (e.isIntersecting && want) { want = false; start(); }
    }, { threshold: 0.3 }) : null;
    const request = () => { if (played) return; want = true; if (io) { io.unobserve(panel); io.observe(panel); } else { want = false; start(); } };
    if (location.hash === '#demo') request();
    addEventListener('hashchange', () => { if (location.hash === '#demo') request(); });
    document.addEventListener('click', e => { if (e.target.closest('a[href$="#demo"]')) request(); });
  });
})();

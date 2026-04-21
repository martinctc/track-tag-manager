/* ── Sticky-nav border on scroll ─────────────────────────────────────── */
(() => {
  const nav = document.querySelector('.nav');
  if (!nav) return;
  const onScroll = () => nav.classList.toggle('scrolled', window.scrollY > 8);
  onScroll();
  window.addEventListener('scroll', onScroll, { passive: true });
})();

/* ── Hero waveform: generate bars and breathe with a gentle animation ── */
(() => {
  const wrap = document.getElementById('wave');
  if (!wrap) return;

  const N = 96;
  // Pseudo-random but stable amplitude profile (bell-ish)
  const heights = Array.from({ length: N }, (_, i) => {
    const t = i / (N - 1);
    const bell = Math.sin(t * Math.PI);                  // 0..1..0
    const noise = (Math.sin(i * 12.9898) * 43758.5453) % 1;
    const r = (noise + 1) % 1;                            // 0..1
    return 0.18 + bell * 0.65 + r * 0.18;                 // 0.18..~1.0
  });

  // Build DOM
  const frag = document.createDocumentFragment();
  heights.forEach(h => {
    const s = document.createElement('span');
    s.style.setProperty('--h', `${(h * 100).toFixed(1)}%`);
    frag.appendChild(s);
  });
  wrap.appendChild(frag);

  // Breathing animation — randomly nudge bars on a slow cadence
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const bars = Array.from(wrap.children);
  let raf, last = 0;
  const tick = (ts) => {
    if (ts - last > 220) {
      last = ts;
      // Update ~12 random bars per frame for a subtle living feel
      for (let k = 0; k < 12; k++) {
        const i = (Math.random() * bars.length) | 0;
        const base = heights[i];
        const jitter = (Math.random() - 0.5) * 0.18;
        const h = Math.max(0.08, Math.min(1.0, base + jitter));
        bars[i].style.setProperty('--h', `${(h * 100).toFixed(1)}%`);
      }
    }
    raf = requestAnimationFrame(tick);
  };
  raf = requestAnimationFrame(tick);

  // Pause when tab hidden to save battery
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) cancelAnimationFrame(raf);
    else raf = requestAnimationFrame(tick);
  });
})();

/* ── Reveal-on-scroll ────────────────────────────────────────────────── */
(() => {
  const targets = document.querySelectorAll(
    '.section .section-title, .section .section-sub, .feature, .strip-item, ' +
    '.vocab-block, .flow li, .format-table, .codeblock, .cta-row'
  );
  targets.forEach(el => el.classList.add('reveal'));

  if (!('IntersectionObserver' in window)) {
    targets.forEach(el => el.classList.add('in'));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        e.target.classList.add('in');
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });
  targets.forEach(el => io.observe(el));
})();

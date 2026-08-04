(() => {
  'use strict';
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (reduced) return;   // the CSS already lays the whole reel out flat

  /* How a thing arrives. t runs 0 (off) to 1 (settled). Having several of
     these, rather than one fade-up applied to everything, is the difference
     between six scenes and one scene shown six times. */
  const ANIM = {
    rise:  t => `translate3d(0,${((1 - t) * 46).toFixed(1)}px,0)`,
    drop:  t => `translate3d(0,${((1 - t) * -52).toFixed(1)}px,0)`,
    left:  t => `translate3d(${((1 - t) * -110).toFixed(1)}px,0,0)`,
    right: t => `translate3d(${((1 - t) * 110).toFixed(1)}px,0,0)`,
    pop:   t => `scale(${(0.84 + t * 0.16).toFixed(3)})`,
    // Swings in from the right and straightens as it lands.
    tilt:  t => `translate3d(${((1 - t) * 150).toFixed(1)}px,0,0) `
              + `rotate(${((1 - t) * 6).toFixed(2)}deg)`
  };

  const BAND = 260;   // px of overlap between one panel and the next

  const scenes = [...document.querySelectorAll('.scene')].map((el, i) => ({
    el,
    stage: el.querySelector('.stage'),
    i,
    items: [...el.querySelectorAll('[data-at]')].map(n => {
      const [a, b] = n.dataset.at.split(',').map(Number);
      return { n, a, b, fn: ANIM[n.dataset.anim] || ANIM.rise,
               wipe: n.hasAttribute('data-wipe') };
    }),
    crossers: [...el.querySelectorAll('.cross')].map(n => ({
      n, d: parseFloat(n.dataset.cross) || 1
    })),
    feeds: [...el.querySelectorAll('[data-feed]')].map(n => {
      const [a, b] = n.dataset.feed.split(',').map(Number);
      return { n, a, b };
    })
  }));

  const run = document.querySelector('.dial .run');
  const pct = document.getElementById('pct');
  const tin = document.querySelector('.resupply');
  const dock = document.querySelector('.dock');

  // The mouse perks up when you reach for the tin, and again when it opens on
  // its own at the end.
  let hovering = false;
  tin.addEventListener('pointerenter', () => { hovering = true; dock.classList.add('excited'); });
  tin.addEventListener('pointerleave', () => { hovering = false; frame(); });
  const chapterEl = document.getElementById('chapter');
  const CHAPTERS = ['00 · Title','01 · One story','02 · Five sections',
                    '03 · Talk back','04 · Sources','05 · Subscribe'];
  const CIRC = 2 * Math.PI * 27;

  const clamp = v => v < 0 ? 0 : v > 1 ? 1 : v;
  // Slow at both ends: things settle instead of arriving at full speed.
  const ease = t => t < .5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  let vh = innerHeight, queued = false;

  function frame() {
    queued = false;
    const y = window.scrollY || document.documentElement.scrollTop;

    const last = scenes.length - 1;

    for (const s of scenes) {
      const top = s.el.offsetTop;
      const h = s.el.offsetHeight;
      // With the panel fixed, the scene's whole height is its timeline.
      const p = clamp(h > 0 ? (y - top) / h : 0);

      // Fade in over BAND before this panel's scene starts; fade out over
      // BAND after it ends. The final panel never fades out.
      let vis;
      if (y < top) vis = clamp(1 - (top - y) / BAND);
      else if (y > top + h && s.i !== last) vis = clamp(1 - (y - top - h) / BAND);
      else vis = 1;

      s.stage.style.opacity = vis.toFixed(3);
      s.stage.style.visibility = vis > 0.01 ? 'visible' : 'hidden';
      s.stage.style.zIndex = String(10 + s.i);
      if (vis <= 0.01) continue;

      for (const it of s.items) {
        const t = ease(clamp((p - it.a) / (it.b - it.a)));
        it.n.style.opacity = t.toFixed(3);
        it.n.style.transform = it.fn(t);
        // A wipe reveals left to right instead of fading, which reads as
        // writing rather than appearing.
        if (it.wipe) it.n.style.clipPath = `inset(0 ${((1 - t) * 100).toFixed(1)}% 0 0)`;
      }

      // Shapes that keep moving for the whole scene, so something is always
      // in motion rather than everything arriving and then sitting still.
      for (const c of s.crossers) {
        c.n.style.transform =
          `translate3d(${((p - 0.5) * c.d * 60).toFixed(1)}vw,0,0) `
          + `rotate(${((p - 0.5) * c.d * 40).toFixed(1)}deg)`;
      }

      // The phone's feed is taller than its screen; scroll reads it.
      for (const f of s.feeds) {
        const t = ease(clamp((p - f.a) / (f.b - f.a)));
        const over = Math.max(0, f.n.scrollHeight - f.n.parentElement.clientHeight + 46);
        f.n.style.transform = `translate3d(0,${(-t * over).toFixed(1)}px,0)`;
      }
    }

    // How far through the whole reel.
    const total = document.body.scrollHeight - vh;
    const g = clamp(total > 0 ? y / total : 0);
    run.style.strokeDashoffset = (CIRC * (1 - g)).toFixed(1);
    pct.textContent = Math.round(g * 100);

    // She stays put. The cup swings gently under her: out one way, back
    // through the middle, out the other, and home by the end. sin() returns to
    // zero exactly where it started.
    const cupEl = document.querySelector('.cup');
    if (cupEl) cupEl.style.transform =
      `translateX(${(Math.sin(g * Math.PI * 2) * 9).toFixed(1)}px)`;

    // Near the end it opens by itself, so anyone who never hovered still finds
    // out the little tin was a tip jar.
    const open = g > 0.9;
    tin.classList.toggle('open', open);

    // Looking at you at the top, at the page through the middle, back at you
    // by the end.
    const eye = document.querySelector('.mouse .gaze');
    if (eye) eye.style.transform =
      (g > 0.28 && g < 0.72) ? 'translateX(-1px)' : 'translateX(0)';
    dock.classList.toggle('excited', open || hovering);

    // The window is fixed, so it can say what is currently passing through it.
    const ci = Math.min(CHAPTERS.length - 1, Math.floor(g * CHAPTERS.length));
    if (chapterEl.textContent !== CHAPTERS[ci]) chapterEl.textContent = CHAPTERS[ci];
  }

  function onScroll() {
    if (!queued) { queued = true; requestAnimationFrame(frame); }
  }

  function resize() { vh = innerHeight; frame(); }

  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', resize);
  if (document.fonts) document.fonts.ready.then(frame);
  frame();
})();

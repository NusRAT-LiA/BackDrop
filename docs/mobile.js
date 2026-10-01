/* Phone helpers: mark boxes that scroll sideways, fold figure captions under Details, and let Figure 2 open full size. */
(() => {
  const BOXES = '.mapbox,.tbox,.cscroll,.gwrap,.twrap';
  const phone = window.matchMedia('(max-width:640px)');
  const atEnd = el => el.scrollLeft + el.clientWidth >= el.scrollWidth - 4;
  function mark() {
    document.querySelectorAll(BOXES).forEach(el => {
      const over = phone.matches && el.scrollWidth > el.clientWidth + 4;
      el.classList.toggle('is-scroll', over);
      el.classList.toggle('at-end', over && atEnd(el));
      const next = el.nextElementSibling, has = next && next.classList.contains('swipe');
      if (over && !has) {
        const p = document.createElement('p');
        p.className = 'swipe';
        p.textContent = 'Swipe sideways to see the rest →';
        el.after(p);
      } else if (!over && has) next.remove();
    });
  }
  // on phones, charts keep at least 80% of their drawn size so their text stays readable; the box scrolls instead
  function widen() {
    document.querySelectorAll('.cscroll svg[viewBox], .mapbox svg[viewBox]').forEach(svg => {
      if (!('base' in svg.dataset)) svg.dataset.base = svg.style.minWidth || '';
      const vb = parseFloat(svg.getAttribute('viewBox').split(/[\s,]+/)[2]) || 0;
      const base = parseFloat(svg.dataset.base) || 0;
      svg.style.minWidth = phone.matches ? Math.max(base, Math.round(vb * 0.8)) + 'px' : svg.dataset.base;
    });
  }
  // Findings: captions, notes and the paper's-version buttons fold under one Details button per figure
  function details() {
    document.querySelectorAll('figure.item').forEach(item => {
      const heading = el => el.matches('p.note') && el.children.length === 1 && el.firstElementChild.tagName === 'B' && el.textContent.trim() === el.firstElementChild.textContent.trim();
      const fold = [...item.querySelectorAll('figcaption, .cap, .orig-t, p.note')].filter(el => !heading(el));
      fold.forEach(el => el.classList.add('fold'));
      if (fold.length && !item.querySelector(':scope > .dett')) {
        const b = document.createElement('button');
        b.type = 'button'; b.className = 'btn sm dett'; b.setAttribute('aria-expanded', 'false'); b.textContent = 'Details';
        item.appendChild(b);
      }
    });
  }
  function figures() {
    document.querySelectorAll('.card figure > img').forEach(img => {
      const a = document.createElement('a');
      a.href = img.getAttribute('src'); a.target = '_blank'; a.rel = 'noopener';
      img.before(a); a.appendChild(img);
      const p = document.createElement('p');
      p.className = 'swipe fighint';
      p.textContent = 'Tap the figure to open it full size.';
      a.after(p);
    });
  }
  let queued = false;
  const later = () => { if (!queued) { queued = true; requestAnimationFrame(() => { queued = false; details(); widen(); mark(); }); } };
  document.addEventListener('click', e => {
    const b = e.target.closest('.dett'); if (!b) return;
    const item = b.closest('figure.item'), open = !item.classList.contains('det');
    item.classList.toggle('det', open);
    b.setAttribute('aria-expanded', String(open));
    b.textContent = open ? 'Hide details' : 'Details';
  });
  document.addEventListener('scroll', e => {
    const el = e.target;
    if (el.classList && el.classList.contains('is-scroll')) el.classList.toggle('at-end', atEnd(el));
  }, true);
  window.addEventListener('load', () => { figures(); details(); widen(); mark(); });
  window.addEventListener('resize', later);
  phone.addEventListener('change', later);
  new MutationObserver(later).observe(document.body, {childList: true, subtree: true});
})();

/** Full-screen dark blur with a sharp cutout around the highlighted tour target. */

const ATM_ID = 'cv-tour-atmosphere';
const PAD = 12;

export function ensureTourAtmosphere(): HTMLElement {
  let el = document.getElementById(ATM_ID);
  if (!el) {
    el = document.createElement('div');
    el.id = ATM_ID;
    el.className = 'cv-tour-atmosphere';
    el.setAttribute('aria-hidden', 'true');
    document.body.appendChild(el);
  }
  document.documentElement.classList.add('cv-tour-active');
  return el;
}

export function updateTourAtmosphereCutout(element?: Element | null) {
  const el = ensureTourAtmosphere();
  if (!element || !(element instanceof HTMLElement)) {
    el.style.clipPath = 'none';
    return;
  }
  const r = element.getBoundingClientRect();
  const x = Math.max(0, r.left - PAD);
  const y = Math.max(0, r.top - PAD);
  const w = Math.min(window.innerWidth - x, r.width + PAD * 2);
  const h = Math.min(window.innerHeight - y, r.height + PAD * 2);
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  // Outer rect + inner hole (evenodd) so the spotlight stays sharp.
  el.style.clipPath = `path(evenodd, "M0,0 H${vw} V${vh} H0 Z M${x},${y} H${x + w} V${y + h} H${x} Z")`;
}

export function clearTourAtmosphere() {
  document.getElementById(ATM_ID)?.remove();
  document.documentElement.classList.remove('cv-tour-active');
}

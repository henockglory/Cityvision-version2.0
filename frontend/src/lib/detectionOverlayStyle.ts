/** Premium bbox palette by COCO class (border + soft fill). */
const CLASS_PALETTE: Record<string, { border: string; fill: string; label: string }> = {
  person: { border: '#fbbf24', fill: 'rgba(251, 191, 36, 0.12)', label: '#fef3c7' },
  car: { border: '#38bdf8', fill: 'rgba(56, 189, 248, 0.14)', label: '#e0f2fe' },
  truck: { border: '#60a5fa', fill: 'rgba(96, 165, 250, 0.14)', label: '#dbeafe' },
  bus: { border: '#818cf8', fill: 'rgba(129, 140, 248, 0.14)', label: '#e0e7ff' },
  motorcycle: { border: '#2dd4bf', fill: 'rgba(45, 212, 191, 0.14)', label: '#ccfbf1' },
  bicycle: { border: '#34d399', fill: 'rgba(52, 211, 153, 0.14)', label: '#d1fae5' },
};

const DEFAULT_PALETTE = { border: '#a78bfa', fill: 'rgba(167, 139, 250, 0.12)', label: '#ede9fe' };

export function paletteForClass(className: string) {
  return CLASS_PALETTE[className] ?? DEFAULT_PALETTE;
}

import { useEffect, useRef } from 'react';

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  alpha: number;
  hue: number;
}

export default function HologramBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId = 0;
    let particles: Particle[] = [];

    const resize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
      particles = Array.from({ length: 220 }, () => ({
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        size: Math.random() * 2.5 + 0.5,
        alpha: Math.random() * 0.55 + 0.12,
        hue: Math.random() > 0.5 ? 195 : 220,
      }));
    };

    const drawWeb = () => {
      const cx = canvas.width * 0.5;
      const cy = canvas.height * 0.42;
      const rings = 9;
      const spokes = 18;
      const maxR = Math.min(canvas.width, canvas.height) * 0.58;

      ctx.strokeStyle = 'rgba(0, 102, 255, 0.12)';
      ctx.lineWidth = 0.6;
      for (let r = 1; r <= rings; r++) {
        ctx.beginPath();
        ctx.arc(cx, cy, (r / rings) * maxR, 0, Math.PI * 2);
        ctx.stroke();
      }
      for (let s = 0; s < spokes; s++) {
        const angle = (s / spokes) * Math.PI * 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + Math.cos(angle) * maxR, cy + Math.sin(angle) * maxR);
        ctx.stroke();
      }

      ctx.strokeStyle = 'rgba(0, 212, 255, 0.06)';
      for (let r = 1; r <= rings; r++) {
        for (let s = 0; s < spokes; s++) {
          const a1 = (s / spokes) * Math.PI * 2;
          const a2 = ((s + 2) / spokes) * Math.PI * 2;
          const rad = (r / rings) * maxR;
          const rad2 = ((r + 1) / rings) * maxR;
          ctx.beginPath();
          ctx.moveTo(cx + Math.cos(a1) * rad, cy + Math.sin(a1) * rad);
          ctx.lineTo(cx + Math.cos(a2) * rad2, cy + Math.sin(a2) * rad2);
          ctx.stroke();
        }
      }

      const corners = [
        [canvas.width * 0.15, canvas.height * 0.2],
        [canvas.width * 0.85, canvas.height * 0.15],
        [canvas.width * 0.1, canvas.height * 0.85],
        [canvas.width * 0.9, canvas.height * 0.8],
      ];
      ctx.strokeStyle = 'rgba(0, 102, 255, 0.07)';
      for (const [x, y] of corners) {
        for (let s = 0; s < 8; s++) {
          const angle = (s / 8) * Math.PI * 2;
          ctx.beginPath();
          ctx.moveTo(x, y);
          ctx.lineTo(x + Math.cos(angle) * 120, y + Math.sin(angle) * 120);
          ctx.stroke();
        }
      }
    };

    const draw = () => {
      ctx.fillStyle = 'rgba(0, 0, 0, 0.15)';
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      drawWeb();

      for (const p of particles) {
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = canvas.width;
        if (p.x > canvas.width) p.x = 0;
        if (p.y < 0) p.y = canvas.height;
        if (p.y > canvas.height) p.y = 0;

        const gradient = ctx.createRadialGradient(p.x, p.y, 0, p.x, p.y, p.size * 4);
        gradient.addColorStop(0, `hsla(${p.hue}, 100%, 72%, ${p.alpha})`);
        gradient.addColorStop(0.5, `hsla(${p.hue}, 90%, 55%, ${p.alpha * 0.4})`);
        gradient.addColorStop(1, `hsla(${p.hue}, 100%, 50%, 0)`);
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.size * 2.5, 0, Math.PI * 2);
        ctx.fill();
      }

      animId = requestAnimationFrame(draw);
    };

    resize();
    draw();
    window.addEventListener('resize', resize);
    return () => {
      cancelAnimationFrame(animId);
      window.removeEventListener('resize', resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 pointer-events-none z-0"
      aria-hidden
    />
  );
}

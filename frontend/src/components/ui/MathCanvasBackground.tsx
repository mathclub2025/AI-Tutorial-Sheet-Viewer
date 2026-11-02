"use client";

import * as React from "react";

interface ChalkWatermark {
  symbol: string;
  x: number;
  y: number;
  vy: number;
  swayAmplitude: number;
  swayFrequency: number;
  swayOffset: number;
  angle: number;
  size: number;
}

const WATERMARK_SYMBOLS = ["∫", "∑", "∂", "π", "∞", "∇", "∆", "ℝ"];

export function MathCanvasBackground() {
  const canvasRef = React.useRef<HTMLCanvasElement | null>(null);

  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    // Mouse coordinates with smooth damping
    const mouse = {
      x: width / 2,
      y: height / 2,
      targetX: width / 2,
      targetY: height / 2,
      active: false,
    };

    const handleMouseMove = (e: MouseEvent) => {
      mouse.targetX = e.clientX;
      mouse.targetY = e.clientY;
      mouse.active = true;
    };

    const handleMouseLeave = () => {
      mouse.active = false;
      mouse.targetX = width / 2;
      mouse.targetY = height / 2;
    };

    window.addEventListener("mousemove", handleMouseMove, { passive: true });
    document.addEventListener("mouseleave", handleMouseLeave);

    // High DPI Retina scaling
    const handleResize = () => {
      if (!canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      ctx.resetTransform?.();
      ctx.scale(dpr, dpr);
    };

    handleResize();
    window.addEventListener("resize", handleResize);

    // 8-10 Large Elegant Mathematical Chalk Watermarks
    const watermarks: ChalkWatermark[] = WATERMARK_SYMBOLS.map((symbol, i) => ({
      symbol,
      x: ((i + 0.5) / WATERMARK_SYMBOLS.length) * width + (Math.random() - 0.5) * 80,
      y: Math.random() * height,
      vy: -0.15, // Drifting very slowly as requested
      swayAmplitude: Math.random() * 0.4 + 0.15,
      swayFrequency: 0.003,
      swayOffset: Math.random() * Math.PI * 2,
      angle: (Math.random() - 0.5) * 0.25,
      size: Math.floor(Math.random() * 16) + 36, // 36px to 52px
    }));

    // Animation phases
    let time = 0;

    const render = () => {
      time += 0.001; // Smooth slow evolution
      ctx.clearRect(0, 0, width, height);

      // Smooth mouse follow
      mouse.x += (mouse.targetX - mouse.x) * 0.02;
      mouse.y += (mouse.targetY - mouse.y) * 0.02;

      const mouseOffsetNormX = (mouse.x - width / 2) / (width / 2);
      const mouseOffsetNormY = (mouse.y - height / 2) / (height / 2);

      // -----------------------------------------------------------
      // 1. Faint Chalk Watermarks (Italic serif, drifting very slowly)
      // -----------------------------------------------------------
      ctx.fillStyle = "rgba(244, 240, 234, 0.06)";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";

      for (let i = 0; i < watermarks.length; i++) {
        const mark = watermarks[i];
        mark.y += mark.vy;
        mark.x += Math.sin(time * 2 + mark.swayOffset) * mark.swayAmplitude;

        // Wrap around smoothly when drifting above top
        if (mark.y < -60) {
          mark.y = height + 60;
          mark.x = Math.random() * width;
        }

        ctx.save();
        ctx.translate(mark.x, mark.y);
        ctx.rotate(mark.angle);
        ctx.font = `italic ${mark.size}px Georgia, "Times New Roman", serif`;
        ctx.fillText(mark.symbol, 0, 0);
        ctx.restore();
      }

      // -----------------------------------------------------------
      // 2. Continuous Parametric Harmonic / Lissajous Curves
      // -----------------------------------------------------------
      ctx.lineWidth = 1;

      // Curve 1: 3:2 Lissajous Harmonic Knot in subtle warm chalk
      // x(t) = A * sin(3t + δ1), y(t) = B * sin(2t + δ2)
      ctx.beginPath();
      ctx.strokeStyle = "rgba(226, 220, 205, 0.07)";
      const cx1 = width * 0.5 + mouseOffsetNormX * 18;
      const cy1 = height * 0.48 + mouseOffsetNormY * 14;
      const rx1 = Math.min(width * 0.42, 600);
      const ry1 = Math.min(height * 0.36, 360);
      const phase1 = time * 0.6;
      const phase2 = time * 0.4;
      const steps1 = 600;

      for (let i = 0; i <= steps1; i++) {
        const t = (i / steps1) * Math.PI * 2;
        const x = cx1 + rx1 * Math.sin(3 * t + phase1) * Math.cos(t * 0.25);
        const y = cy1 + ry1 * Math.sin(2 * t + phase2);
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

      // Curve 2: 5:4 Parametric Harmonic Ribbon in subtle academic gold
      ctx.beginPath();
      ctx.strokeStyle = "rgba(212, 175, 55, 0.05)";
      const cx2 = width * 0.52 - mouseOffsetNormX * 14;
      const cy2 = height * 0.52 - mouseOffsetNormY * 10;
      const rx2 = Math.min(width * 0.46, 680);
      const ry2 = Math.min(height * 0.38, 400);
      const phase3 = time * 0.45 + 1.2;
      const phase4 = time * 0.35 + 0.8;
      const steps2 = 700;

      for (let i = 0; i <= steps2; i++) {
        const t = (i / steps2) * Math.PI * 2;
        const x = cx2 + rx2 * Math.sin(5 * t + phase3) * Math.cos(t * 0.5);
        const y = cy2 + ry2 * Math.cos(4 * t + phase4);
        if (i === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

      // Curve 3: Continuous Fourier Wave Interference across the screen width
      ctx.beginPath();
      ctx.strokeStyle = "rgba(226, 220, 205, 0.06)";
      const baseWaveY = height * 0.54 + mouseOffsetNormY * 20;
      const wavePhase1 = time * 0.8;
      const wavePhase2 = time * 1.3;
      const wavePhase3 = time * 0.5;

      for (let x = 0; x <= width; x += 4) {
        const y =
          baseWaveY +
          Math.sin(x * 0.0024 + wavePhase1) * 55 +
          Math.sin(x * 0.0056 - wavePhase2) * 28 +
          Math.cos(x * 0.0011 + wavePhase3) * 38;

        if (x === 0) {
          ctx.moveTo(x, y);
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(animationFrameId);
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseleave", handleMouseLeave);
    };
  }, []);

  return (
    <div
      aria-hidden="true"
      className="fixed inset-0 -z-10 pointer-events-none overflow-hidden bg-[#0A0A0C] bg-[radial-gradient(ellipse_80%_60%_at_50%_0%,rgba(255,248,231,0.03),transparent_75%)]"
    >
      <canvas
        ref={canvasRef}
        className="absolute inset-0 block h-full w-full pointer-events-none"
      />
    </div>
  );
}

export default MathCanvasBackground;

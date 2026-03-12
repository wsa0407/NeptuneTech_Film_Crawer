/**
 * 交互式粒子星座背景 (Constellation Effect)
 * 全屏 Canvas：粒子缓慢漂浮，近距离自动连线；鼠标在非白卡区域时产生引力连线。
 * pointer-events: none，不干扰页面点击。
 */
(function () {
  const CONFIG = {
    particleCount: 100,
    connectRadius: 140,
    mouseRadius: 200,
    particleRadius: 1.2,
    lineOpacityMax: 0.55,
    mouseLineOpacityMax: 0.65,
    speed: 0.15,
    backgroundColor: "#0D1117",
  };

  let canvas, ctx, w, h;
  let particles = [];
  let mouse = { x: null, y: null };
  let animationId;

  function init() {
    canvas = document.getElementById("particle-canvas");
    if (!canvas) return;
    ctx = canvas.getContext("2d");
    resize();
    window.addEventListener("resize", resize);
    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseleave", onMouseLeave);
    loop();
  }

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    w = canvas.width = window.innerWidth * dpr;
    h = canvas.height = window.innerHeight * dpr;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    canvas.style.width = window.innerWidth + "px";
    canvas.style.height = window.innerHeight + "px";
    createParticles();
  }

  function createParticles() {
    const count = CONFIG.particleCount;
    const maxX = window.innerWidth;
    const maxY = window.innerHeight;
    particles = [];
    for (let i = 0; i < count; i++) {
      particles.push({
        x: Math.random() * maxX,
        y: Math.random() * maxY,
        vx: (Math.random() - 0.5) * CONFIG.speed,
        vy: (Math.random() - 0.5) * CONFIG.speed,
      });
    }
  }

  function isMouseOverBlockingElement(x, y) {
    const cards = document.querySelectorAll(".card");
    const header = document.querySelector(".header");
    const loginBox = document.querySelector(".login-box");
    const detail = document.querySelector(".detail");
    const rects = [];
    cards.forEach(function (el) {
      rects.push(el.getBoundingClientRect());
    });
    if (header) rects.push(header.getBoundingClientRect());
    if (loginBox) rects.push(loginBox.getBoundingClientRect());
    if (detail) rects.push(detail.getBoundingClientRect());
    for (let i = 0; i < rects.length; i++) {
      const r = rects[i];
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return true;
    }
    return false;
  }

  function onMouseMove(e) {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
  }

  function onMouseLeave() {
    mouse.x = null;
    mouse.y = null;
  }

  function dist(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function drawParticle(p) {
    const px = p.x;
    const py = p.y;
    ctx.beginPath();
    ctx.arc(px, py, CONFIG.particleRadius, 0, Math.PI * 2);
    ctx.fillStyle = "rgba(220, 235, 255, 0.65)";
    ctx.fill();
  }

  function drawLine(x1, y1, x2, y2, opacity) {
    ctx.setLineDash([2, 4]);
    ctx.beginPath();
    ctx.moveTo(x1, y1);
    ctx.lineTo(x2, y2);
    ctx.strokeStyle = "rgba(255, 255, 255, " + opacity + ")";
    ctx.lineWidth = 0.8;
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function loop() {
    const cw = window.innerWidth;
    const ch = window.innerHeight;

    ctx.fillStyle = CONFIG.backgroundColor;
    ctx.fillRect(0, 0, cw, ch);

    // 更新粒子位置（缓慢漂浮）
    particles.forEach(function (p) {
      p.x += p.vx;
      p.y += p.vy;
      if (p.x < 0 || p.x > cw) p.vx *= -1;
      if (p.y < 0 || p.y > ch) p.vy *= -1;
      p.x = Math.max(0, Math.min(cw, p.x));
      p.y = Math.max(0, Math.min(ch, p.y));
    });

    const mouseActive = mouse.x != null && mouse.y != null && !isMouseOverBlockingElement(mouse.x, mouse.y);

    // 粒子间连线（距离小于阈值时渐隐连线）
    for (let i = 0; i < particles.length; i++) {
      for (let j = i + 1; j < particles.length; j++) {
        const d = dist(particles[i], particles[j]);
        if (d < CONFIG.connectRadius) {
          const opacity = (1 - d / CONFIG.connectRadius) * CONFIG.lineOpacityMax;
          drawLine(particles[i].x, particles[i].y, particles[j].x, particles[j].y, opacity);
        }
      }
    }

    // 鼠标引力连线（仅在非白卡区域）
    if (mouseActive) {
      particles.forEach(function (p) {
        const d = Math.hypot(p.x - mouse.x, p.y - mouse.y);
        if (d < CONFIG.mouseRadius) {
          const opacity = (1 - d / CONFIG.mouseRadius) * CONFIG.mouseLineOpacityMax;
          drawLine(p.x, p.y, mouse.x, mouse.y, opacity);
        }
      });
    }

    // 绘制粒子点
    particles.forEach(drawParticle);

    animationId = requestAnimationFrame(loop);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

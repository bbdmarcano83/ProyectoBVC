// ── Reloj ─────────────────────────────────────────────────────────────────
(function () {
    const el = document.getElementById('reloj');
    if (!el) return;
    function tick() {
        el.textContent = new Date().toLocaleTimeString('es-VE', { hour12: false });
    }
    tick();
    setInterval(tick, 1000);
})();

// ── Skeleton loader → reemplaza con datos reales al cargar ────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Counter animation para stat cards
    document.querySelectorAll('.stat-value[data-target]').forEach(el => {
        const target = parseFloat(el.dataset.target);
        const decimals = el.dataset.decimals || 2;
        const suffix = el.dataset.suffix || '';
        let start = 0;
        const duration = 800;
        const step = timestamp => {
            if (!start) start = timestamp;
            const progress = Math.min((timestamp - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            el.textContent = (target * eased).toFixed(decimals) + suffix;
            if (progress < 1) requestAnimationFrame(step);
        };
        requestAnimationFrame(step);
    });
});

// ── Flash animación en números que cambian ────────────────────────────────
function flashNumber(el, isUp) {
    el.style.transition = 'color .1s';
    el.style.color = isUp ? 'var(--buy)' : 'var(--sell)';
    setTimeout(() => { el.style.color = ''; }, 600);
}

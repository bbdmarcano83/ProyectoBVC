(function () {
    const el = document.getElementById('reloj');
    if (!el) return;
    function tick() {
        const now = new Date();
        el.textContent = now.toLocaleTimeString('es-VE', { hour12: false });
    }
    tick();
    setInterval(tick, 1000);
})();
// A history snapshot must not resurrect a logged-out account's private screen.
// Ordinary navigation remains unchanged; only BFCache restoration reloads.
(() => {
    window.addEventListener("pagehide", () => {
        document.documentElement.style.visibility = "hidden";
    });
    window.addEventListener("pageshow", event => {
        if (event.persisted) {
            window.location.reload();
            return;
        }
        document.documentElement.style.visibility = "";
    });
})();

// A history snapshot must not resurrect a logged-out account's private screen.
// Ordinary navigation remains unchanged; only BFCache restoration reloads.
(() => {
    document.addEventListener("submit", event => {
        const form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        const action = new URL(form.action, location.href);
        if (action.origin !== location.origin || action.pathname !== "/logout") return;
        // Stop in-page writers before pagehide so they cannot recreate private
        // drafts while this tab is leaving an authenticated account.
        window.dispatchEvent(new CustomEvent("dai:session-ending"));
        try {
            for (const key of Object.keys(sessionStorage)) {
                if (key.startsWith("dai:voice-draft:") || key.startsWith("dai-social-v1:")) {
                    sessionStorage.removeItem(key);
                }
            }
        } catch {}
    }, true);
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


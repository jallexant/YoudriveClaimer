// Reads rendered cards only. No login automation, cookie access or remote API call.
(() => {
  let lastAccepted = "";
  let busy = false;
  const text = (root, selector) => root.querySelector(selector)?.textContent?.trim() || "";
  const digest = async value => Array.from(new Uint8Array(
    await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value))
  )).map(n => n.toString(16).padStart(2, "0")).join("");

  async function collect() {
    if (busy) return;
    busy = true;
    try {
      const page = location.pathname.endsWith("/trajets") ? "history" : "dashboard";
      const cards = Array.from(document.querySelectorAll("lib-journey-trip-card"));
      if (!cards.length || cards.length > (page === "history" ? 10 : 3)) return;
      const trips = [];
      for (const card of cards) {
        const times = Array.from(card.querySelectorAll(".trip-card__time"), el => el.textContent.trim());
        const meta = Array.from(card.querySelectorAll(".trip-card__meta-item p"), el => el.textContent.trim());
        const date = text(card, ".trip-card__date");
        const distance = meta.find(value => /\bkm\b/.test(value)) || "";
        const duration = meta.find(value => /^\d+:\d{2}$/.test(value)) || "";
        if (!date || times.length !== 2 || !distance || !duration) return;
        const addresses = Array.from(card.querySelectorAll(".trip-card__address"), el =>
          el.textContent.trim().replace(/\s+/g, " "));
        // Score excluded: a correction must update the same local row.
        const identity = await digest(JSON.stringify([date, ...times, distance, ...addresses]));
        trips.push({date, start: times[0], end: times[1], distance, duration,
          score: text(card, ".score-badge__value"), identity});
      }
      const payload = {source: "direct-assurance-visible-v1", page, trips};
      const fingerprint = JSON.stringify(payload);
      if (fingerprint === lastAccepted) return;
      const result = await chrome.runtime.sendMessage(payload);
      if (result?.ok) lastAccepted = fingerprint;
    } catch (_) {
      // No personal data in browser logs; retry when the local server is available.
    } finally {
      busy = false;
    }
  }
  new MutationObserver(collect).observe(document.documentElement, {subtree: true, childList: true});
  setInterval(collect, 30000);
  collect();
})();

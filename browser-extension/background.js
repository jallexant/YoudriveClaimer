importScripts("local-config.js");

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  const allowed = /^https:\/\/espace-personnel\.direct-assurance\.fr\/espace-personnel\/mypolicy\/tableau-de-bord-Youdrive(?:\/trajets)?(?:[?#].*)?$/;
  if (sender.id !== chrome.runtime.id || !allowed.test(sender.tab?.url || "") ||
      message?.source !== "direct-assurance-visible-v1") {
    return false;
  }
  fetch("http://127.0.0.1:8766/trips", {
    method: "POST",
    signal: AbortSignal.timeout(10000),
    redirect: "error",
    credentials: "omit",
    headers: {"Content-Type": "application/json", "Authorization": `Bearer ${LOCAL_TOKEN}`},
    body: JSON.stringify(message)
  }).then(async response => {
    const result = response.ok ? await response.json() : null;
    await chrome.action.setBadgeText({text: response.ok ? "OK" : "!", tabId: sender.tab.id});
    respond({ok: response.ok, count: result?.received});
  }).catch(() => {
    chrome.action.setBadgeText({text: "!", tabId: sender.tab.id});
    respond({ok: false});
  });
  return true;
});

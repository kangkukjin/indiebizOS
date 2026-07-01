chrome.action.onClicked.addListener((tab) => {
  if (tab.url && !tab.url.startsWith('chrome://') && !tab.url.startsWith('about:')) {
    const translateUrl = `https://translate.google.com/translate?sl=auto&tl=ko&u=${encodeURIComponent(tab.url)}`;
    // 현재 탭에서 즉시 번역 페이지로 전환합니다.
    chrome.tabs.update(tab.id, { url: translateUrl });
  }
});
/* ==========================================================================
   Zentrix site — подставляет актуальную версию и ссылки на релиз
   Если API недоступен (rate limit / нет сети) — остаются ссылки на /releases/latest
   ========================================================================== */
(() => {
  "use strict";

  const REPO = "w1kscc/Zentrix";
  const API = `https://api.github.com/repos/${REPO}/releases/latest`;
  const FALLBACK = `https://github.com/${REPO}/releases/latest`;

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  const fmt = (bytes) => {
    if (!bytes) return "";
    const mb = bytes / 1048576;
    return `${mb.toFixed(1)} MB`;
  };

  function setVersion(version) {
    $$("[data-version]").forEach((el) => {
      el.textContent = version;
    });
  }

  function setLinks(assets) {
    const exe = assets.find((a) => /setup\.exe$/i.test(a.name));
    const zip = assets.find((a) => /portable\.zip$/i.test(a.name));

    [["[data-dl-installer]", exe], ["[data-dl-portable]", zip]].forEach(([sel, asset]) => {
      $$(sel).forEach((el) => {
        if (asset) {
          el.href = asset.browser_download_url;
          const size = el.querySelector(".dl-size");
          if (size) size.textContent = fmt(asset.size);
        } else {
          el.href = FALLBACK;
        }
        el.classList.remove("skeleton");
      });
    });

    const list = $("#asset-list");
    if (!list) return;
    if (!assets.length) {
      list.innerHTML = '<div class="vrow"><span class="name">Релиз пока без файлов</span></div>';
      return;
    }
    list.innerHTML = assets
      .filter((a) => /\.(exe|zip)$/i.test(a.name))
      .map(
        (a) => `
        <div class="vrow">
          <div>
            <div class="name">${a.name}</div>
            <div class="sz">${fmt(a.size)}</div>
          </div>
          <a href="${a.browser_download_url}" rel="noopener">Скачать →</a>
        </div>`
      )
      .join("");
  }

  async function load() {
    try {
      const res = await fetch(API, { headers: { Accept: "application/vnd.github+json" } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const version = (data.tag_name || "").replace(/^v/i, "");
      if (version) setVersion(version);
      setLinks(data.assets || []);

      const published = $("#published");
      if (published && data.published_at) {
        const d = new Date(data.published_at);
        published.textContent = d.toLocaleDateString("ru-RU", {
          day: "numeric",
          month: "long",
          year: "numeric",
        });
      }
    } catch (err) {
      // тихий откат: остаются статические ссылки на /releases/latest
      $$("[data-dl-installer], [data-dl-portable]").forEach((el) => {
        el.href = FALLBACK;
        el.classList.remove("skeleton");
      });
      const list = $("#asset-list");
      if (list) {
        list.innerHTML = `
          <div class="vrow">
            <span class="name">Открыть все релизы на GitHub</span>
            <a href="${FALLBACK}" rel="noopener">Перейти →</a>
          </div>`;
      }
      console.warn("Zentrix: не удалось получить данные релиза", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", load);
  } else {
    load();
  }
})();

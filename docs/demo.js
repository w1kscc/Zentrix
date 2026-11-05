/* Интерактивное демо GUI Zentrix: переключение вкладок и живые элементы.
   Все IP и города на сайте скрыты — никаких реальных данных. */
(function () {
  "use strict";

  var demo = document.getElementById("appDemo");
  if (!demo) return;

  var running = true;

  // Переключение вкладок сайдбара
  var navButtons = demo.querySelectorAll(".app-nav button[data-page]");
  var pages = demo.querySelectorAll(".app-body .page");
  navButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var key = button.getAttribute("data-page");
      navButtons.forEach(function (other) { other.classList.toggle("on", other === button); });
      pages.forEach(function (page) {
        page.classList.toggle("on", page.getAttribute("data-page") === key);
      });
    });
  });

  // Тумблеры
  demo.querySelectorAll(".a-toggle").forEach(function (toggle) {
    toggle.addEventListener("click", function () { toggle.classList.toggle("on"); });
  });

  // Выбор темы
  var themeButtons = demo.querySelectorAll(".a-card .a-row .a-btn");
  themeButtons.forEach(function (button) {
    if (/^(Тёмная|Светлая|Как в Windows)$/.test(button.textContent.trim())) {
      button.addEventListener("click", function () {
        var row = button.parentElement;
        row.querySelectorAll(".a-btn").forEach(function (other) {
          if (/^(Тёмная|Светлая|Как в Windows)$/.test(other.textContent.trim())) {
            other.classList.toggle("on", other === button);
          }
        });
      });
    }
  });

  // Главный переключатель обхода: меняет бейдж, статус и заголовок окна
  var runButton = demo.querySelector("[data-run]");
  var runBadge = demo.querySelector("[data-run-badge]");
  var runStatus = demo.querySelector("[data-run-status]");
  var runPillText = demo.querySelector("[data-run-text]");
  var runPillDot = demo.querySelector("[data-run-dot]");
  var zapRun = demo.querySelector("[data-zap-run]");
  var zapBadge = demo.querySelector("[data-zap-badge]");

  function setRunning(value) {
    running = value;
    if (runButton) runButton.textContent = running ? "Остановить обход" : "Включить обход";
    if (zapRun) zapRun.textContent = running ? "Остановить" : "Подключить";
    if (runBadge) {
      runBadge.textContent = running ? "АКТИВНО" : "ВЫКЛЮЧЕНО";
      runBadge.classList.toggle("ok", running);
    }
    if (zapBadge) {
      zapBadge.textContent = running ? "РАБОТАЕТ" : "ВЫКЛЮЧЕН";
      zapBadge.classList.toggle("ok", running);
    }
    if (runStatus) {
      runStatus.textContent = running
        ? "Zapret работает · general (ALT8).bat · PID 12220"
        : "Zapret выключен · выбрана стратегия general (ALT8).bat";
    }
    if (runPillText) runPillText.textContent = running ? "Zapret активен" : "Обход выключен";
    if (runPillDot) runPillDot.classList.toggle("on", running);
  }

  if (runButton) runButton.addEventListener("click", function () { setRunning(!running); });
  if (zapRun) zapRun.addEventListener("click", function () { setRunning(!running); });

  // TG WS Proxy переключатель
  var tgRun = demo.querySelector("[data-tg-run]");
  var tgBadge = demo.querySelector("[data-tg-badge]");
  if (tgRun) {
    tgRun.addEventListener("click", function () {
      var on = tgBadge && tgBadge.textContent.trim() === "РАБОТАЕТ";
      if (tgBadge) {
        tgBadge.textContent = on ? "ВЫКЛЮЧЕН" : "РАБОТАЕТ";
        tgBadge.classList.toggle("ok", !on);
      }
      tgRun.textContent = on ? "Включить TG WS Proxy" : "Выключить TG WS Proxy";
    });
  }

  // «Выбрать лучший»: имитация замера
  var best = demo.querySelector("[data-best]");
  if (best) {
    best.addEventListener("click", function () {
      var original = best.textContent;
      best.textContent = "Проверяю стратегии…";
      best.style.pointerEvents = "none";
      setTimeout(function () {
        best.textContent = "Лучше всех: general (ALT8)";
        best.style.pointerEvents = "";
        setTimeout(function () { best.textContent = original; }, 2600);
      }, 1400);
    });
  }

  // «Поиск лучшей стратегии» на вкладке Zapret
  var zapSearch = demo.querySelector("[data-zap-search]");
  if (zapSearch) {
    zapSearch.addEventListener("click", function () {
      var original = zapSearch.textContent;
      zapSearch.textContent = "Проверяю 1/22…";
      zapSearch.style.pointerEvents = "none";
      setTimeout(function () {
        zapSearch.textContent = "Найдена: general (ALT8)";
        zapSearch.style.pointerEvents = "";
        setTimeout(function () { zapSearch.textContent = original; }, 2600);
      }, 1400);
    });
  }
})();

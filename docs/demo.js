/* Интерактивное демо GUI Zentrix: переключение вкладок без анимаций.
   Все IP и города на сайте скрыты — никаких реальных данных. */
(function () {
  "use strict";

  var demo = document.getElementById("appDemo");
  if (!demo) return;

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

  // Выбор стратегии (единичный выбор в списке)
  demo.querySelectorAll("[data-select-group]").forEach(function (group) {
    group.querySelectorAll(".a-item").forEach(function (item) {
      item.addEventListener("click", function () {
        group.querySelectorAll(".a-item").forEach(function (other) {
          other.classList.toggle("sel", other === item);
        });
      });
    });
  });

  // Чипы маршрута в шеринге (VPN / Zapret)
  demo.querySelectorAll("[data-route-group] .a-btn").forEach(function (chip) {
    chip.addEventListener("click", function () {
      chip.parentElement.querySelectorAll(".a-btn").forEach(function (other) {
        other.classList.toggle("on", other === chip);
      });
    });
  });

  // Переключатели-свитчи
  demo.querySelectorAll(".a-toggle").forEach(function (toggle) {
    toggle.addEventListener("click", function () { toggle.classList.toggle("on"); });
  });

  // Кнопки запуска: смена состояния (без анимации), в каждом разделе своя
  demo.querySelectorAll("[data-run]").forEach(function (runButton) {
    runButton.addEventListener("click", function () {
      var running = runButton.classList.toggle("danger");
      runButton.classList.toggle("primary", !running);
      runButton.textContent = running ? "Остановить" : "Запустить";
      var badge = demo.querySelector("[data-run-badge]");
      if (badge) {
        badge.textContent = running ? "РАБОТАЕТ" : "ВЫКЛЮЧЕН";
        badge.classList.toggle("ok", running);
        badge.classList.toggle("muted", !running);
      }
      var status = demo.querySelector("[data-run-status]");
      if (status) status.textContent = running ? "general (FAKE TLS AUTO) · PID 42**" : "Движок не запущен";
    });
  });
})();

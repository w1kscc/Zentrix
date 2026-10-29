"""Blocking-check page: probes, per-service rows, recommendations and export."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ... import constants, paths, winapi
from ...blocking_check import (
    STATUS_LABELS, BlockCheckRunner, ServiceResult, report_json, report_text,
)
from ...logger import get_logger
from .. import overlays, theme
from ..widgets import Badge, Divider, GlassCard, IconOrb, PrimaryButton, icon
from ..workers import run_task
from .base_page import Page, page_heading

log = get_logger("blockcheck-page")

KIND = {"ok": "ok", "blocked": "err", "unstable": "warn", "error": "warn", "pending": "muted"}


class ServiceRow(QWidget):
    def __init__(self, service: dict, palette_obj: theme.Palette, parent=None) -> None:
        super().__init__(parent)
        self.service = service
        self.result: ServiceResult | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        self.orb = IconOrb("globe", palette_obj, 34)
        layout.addWidget(self.orb, 0, Qt.AlignVCenter)

        text = QVBoxLayout()
        text.setSpacing(1)
        self.name_label = QLabel(service["name"])
        self.name_label.setObjectName("h2")
        text.addWidget(self.name_label)
        self.host_label = QLabel(f"{service['host']} · {service.get('note', '')}")
        self.host_label.setObjectName("tiny")
        text.addWidget(self.host_label)
        layout.addLayout(text, 2)

        self.badge = Badge("ОЖИДАНИЕ", "muted")
        layout.addWidget(self.badge, 0, Qt.AlignVCenter)

        self.latency = QLabel("—")
        self.latency.setObjectName("tiny")
        self.latency.setMinimumWidth(64)
        self.latency.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.latency, 0)

        self.reason = QLabel("Проверка не запускалась")
        self.reason.setObjectName("tiny")
        self.reason.setWordWrap(True)
        self.reason.setMinimumWidth(220)
        layout.addWidget(self.reason, 3)

        self.apply_button = QPushButton("Применить")
        self.apply_button.setProperty("variant", "chip")
        self.apply_button.setFixedHeight(30)
        self.apply_button.setCursor(Qt.PointingHandCursor)
        self.apply_button.hide()
        layout.addWidget(self.apply_button, 0)

    def set_pending(self) -> None:
        self.result = None
        self.badge.update_badge("ПРОВЕРКА…", "info")
        self.latency.setText("—")
        self.reason.setText("Подключение…")
        self.apply_button.hide()

    def set_result(self, result: ServiceResult) -> None:
        self.result = result
        self.badge.update_badge(STATUS_LABELS.get(result.status, result.status).upper(),
                                KIND.get(result.status, "muted"))
        self.latency.setText(f"{result.latency_ms} мс" if result.latency_ms else "—")
        detail = result.reason
        if result.detail:
            detail = f"{detail} · {result.detail}"
        self.reason.setText(detail)
        self.reason.setToolTip(result.detail or result.reason)
        actionable = result.status in {"blocked", "unstable"}
        self.apply_button.setVisible(actionable)
        self.apply_button.setToolTip(result.recommendation or "Открыть рекомендации")

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self.orb.set_palette(palette_obj)


class BlockCheckPage(Page):
    key = "blockcheck"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._runner: BlockCheckRunner | None = None
        self._results: dict[str, ServiceResult] = {}
        self._rows: dict[str, ServiceRow] = {}
        self._build()
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)
        header_layout.addWidget(
            page_heading("Проверка блокировок",
                         "DNS · TCP · TLS/SNI — найдите причину и подберите стратегию"), 1
        )
        self.run_button = PrimaryButton("Проверить всё", "target", p)
        self.run_button.clicked.connect(self._toggle_run)
        header_layout.addWidget(self.run_button, 0, Qt.AlignBottom)
        self.add(header)

        self.summary = QLabel("Проверка ещё не запускалась")
        self.summary.setObjectName("tiny")
        self.add(self.summary)

        self.progress_card = GlassCard("Ход проверки", "", "activity", p)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(constants.SERVICES))
        self.progress.setValue(0)
        self.progress_card.add(self.progress)
        self.progress_label = QLabel("Ожидание")
        self.progress_label.setObjectName("tiny")
        self.progress_card.add(self.progress_label)
        self.progress_card.hide()
        self.add(self.progress_card)

        self.recommend_card = GlassCard("Рекомендация", "Автоматический вывод по результатам",
                                        "alert", p)
        self.recommend_badge = Badge("НЕТ ДАННЫХ", "muted")
        self.recommend_card.add_header_widget(self.recommend_badge)
        self.recommend_label = QLabel("Запустите проверку, чтобы получить рекомендацию.")
        self.recommend_label.setObjectName("tiny")
        self.recommend_label.setWordWrap(True)
        self.recommend_card.add(self.recommend_label)
        self.recommend_button = QPushButton("Применить рекомендуемую стратегию")
        self.recommend_button.setProperty("variant", "primary")
        self.recommend_button.setFixedHeight(34)
        self.recommend_button.hide()
        self.recommend_card.add(self.recommend_button, 0)
        self.recommend_card.hide()
        self.add(self.recommend_card)

        services_card = GlassCard("Сервисы", "Проверка выполняется параллельно, не более 4 потоков",
                                  "globe", p)
        for index, service in enumerate(constants.SERVICES):
            row = ServiceRow(service, p)
            row.apply_button.clicked.connect(
                lambda _=False, r=row: self._apply(r.result) if r.result else None
            )
            self._rows[service["id"]] = row
            if index:
                services_card.add(Divider())
            services_card.add(row)
        self.add(services_card)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        self.copy_button = QPushButton("Копировать отчёт")
        self.copy_button.setIcon(icon("copy", p.accent, 18))
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy)
        tools.addWidget(self.copy_button)
        self.export_txt_button = QPushButton("Экспорт TXT")
        self.export_txt_button.setIcon(icon("download", p.accent, 18))
        self.export_txt_button.setEnabled(False)
        self.export_txt_button.clicked.connect(lambda: self._export("txt"))
        tools.addWidget(self.export_txt_button)
        self.export_json_button = QPushButton("Экспорт JSON")
        self.export_json_button.setIcon(icon("download", p.accent, 18))
        self.export_json_button.setEnabled(False)
        self.export_json_button.clicked.connect(lambda: self._export("json"))
        tools.addWidget(self.export_json_button)
        tools.addStretch(1)
        self.add_layout(tools)

        legend = GlassCard("Как это работает", "", "info", p)
        text = QLabel(
            "1. <b>DNS</b> — системный ответ сравнивается с DNS-over-HTTPS (Google). "
            "Расхождение означает подмену DNS.<br>"
            "2. <b>TCP</b> — устанавливается соединение с портом 443. RST или таймаут "
            "указывают на блокировку транспорта.<br>"
            "3. <b>TLS</b> — выполняется рукопожатие с настоящим SNI. Обрыв или таймаут "
            "на этом шаге — типичный признак DPI.<br><br>"
            "Кнопка «Применить» рядом с сервисом предлагает подходящую стратегию Zapret "
            "или смену DNS. Все изменения выполняются только после подтверждения."
        )
        text.setObjectName("tiny")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        legend.add(text)
        self.add(legend)
        self.finish()

    # ------------------------------------------------------------------- show
    def on_show(self) -> None:
        if self._results:
            self._update_summary()

    def on_theme(self) -> None:
        p = self.ctx.palette
        for row in self._rows.values():
            row.set_palette(p)
        self.copy_button.setIcon(icon("copy", p.accent, 18))
        self.export_txt_button.setIcon(icon("download", p.accent, 18))
        self.export_json_button.setIcon(icon("download", p.accent, 18))

    # -------------------------------------------------------------------- run
    def _toggle_run(self) -> None:
        if self._runner and self._runner.isRunning():
            self._runner.stop()
            self.run_button.setEnabled(False)
            self.progress_label.setText("Останавливаю проверку…")
            return
        self._start()

    def _start(self) -> None:
        self._results.clear()
        self.ctx.block_results = []
        for row in self._rows.values():
            row.set_pending()
        self.recommend_card.hide()
        self.progress_card.show()
        total = len(self._rows)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.progress_label.setText(f"Проверено 0 из {total}")
        self.summary.setText("Проверка выполняется…")
        self.run_button.setText("Остановить")
        self.run_button.setProperty("variant", "danger")
        self.run_button.style().unpolish(self.run_button)
        self.run_button.style().polish(self.run_button)
        self.run_button.setEnabled(True)
        self._set_export_enabled(False)
        self.ctx.sound.play("click")

        runner = BlockCheckRunner(parent=self)
        self._runner = runner
        runner.result_ready.connect(self._on_result)
        runner.progress.connect(self._on_progress)
        runner.finished_all.connect(self._on_finished)
        runner.failed.connect(self._on_failed)
        runner.finished.connect(runner.deleteLater)
        runner.start()

    def _on_result(self, result: ServiceResult) -> None:
        self._results[result.id] = result
        row = self._rows.get(result.id)
        if row:
            row.set_result(result)

    def _on_progress(self, index: int, total: int, name: str) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(index)
        self.progress_label.setText(f"Проверено {index} из {total} · {name}")

    def _on_finished(self, results: list) -> None:
        self._runner = None
        ordered = [result for result in results if isinstance(result, ServiceResult)]
        self.ctx.block_results = ordered
        if not ordered:
            ordered = list(self._results.values())
        for result in ordered:
            row = self._rows.get(result.id)
            if row:
                row.set_result(result)
        self.progress.setValue(self.progress.maximum())
        self.progress_label.setText(f"Готово · сервисов: {len(ordered)}")
        self.run_button.setText("Проверить всё")
        self.run_button.setProperty("variant", "primary")
        self.run_button.style().unpolish(self.run_button)
        self.run_button.style().polish(self.run_button)
        self.run_button.setEnabled(True)
        self._set_export_enabled(bool(ordered))
        self._update_summary()
        self._update_recommendation()
        self.ctx.sound.play("notify")
        home = self.ctx.pages.get("home")
        if home is not None:
            try:
                home._refresh_services()  # noqa: SLF001 - dashboard mirror
            except Exception:
                pass

    def _on_failed(self, message: str) -> None:
        self._runner = None
        self.run_button.setText("Проверить всё")
        self.run_button.setProperty("variant", "primary")
        self.run_button.style().unpolish(self.run_button)
        self.run_button.style().polish(self.run_button)
        self.run_button.setEnabled(True)
        self.progress_label.setText("Проверка прервана")
        self.ctx.notify(f"Проверка блокировок: {message}", "err", "error")

    # --------------------------------------------------------------- summary
    def _update_summary(self) -> None:
        results = list(self._results.values())
        if not results:
            self.summary.setText("Проверка ещё не запускалась")
            return
        blocked = sum(1 for item in results if item.status == "blocked")
        unstable = sum(1 for item in results if item.status == "unstable")
        ok = sum(1 for item in results if item.status == "ok")
        self.summary.setText(
            f"Проверено {len(results)} из {len(self._rows)} · доступно {ok} · "
            f"заблокировано {blocked} · нестабильно {unstable}"
        )

    def _update_recommendation(self) -> None:
        results = list(self._results.values())
        if not results:
            return
        blocked = [item for item in results if item.status in {"blocked", "unstable"}]
        if not blocked:
            self.recommend_badge.update_badge("ВСЁ ДОСТУПНО", "ok")
            self.recommend_label.setText(
                "Признаков блокировки не найдено. Если отдельные приложения всё равно "
                "не работают, проверьте их настройки прокси и брандмауэр Windows."
            )
            self.recommend_button.hide()
            self.recommend_card.show()
            return
        strategy = self._best_strategy(blocked)
        names = ", ".join(item.name for item in blocked[:5])
        self.recommend_badge.update_badge("НУЖЕН ОБХОД", "warn")
        self.recommend_label.setText(
            f"Обнаружены проблемы: {names}{'…' if len(blocked) > 5 else ''}.<br><br>"
            f"Рекомендуемая стратегия Zapret: <b>{strategy or 'general.bat'}</b>. "
            "Включите обход и повторите проверку — если проблема осталась, попробуйте "
            "другую стратегию или смените DNS."
        )
        self.recommend_button.setText(f"Включить {strategy or 'general.bat'}")
        self.recommend_button.show()
        try:
            self.recommend_button.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        self.recommend_button.clicked.connect(lambda: self._apply_strategy(strategy or "general.bat"))
        self.recommend_card.show()

    @staticmethod
    def _best_strategy(results: list[ServiceResult]) -> str:
        counts: dict[str, int] = {}
        for result in results:
            if result.strategy:
                counts[result.strategy] = counts.get(result.strategy, 0) + 1
        if not counts:
            return "general.bat"
        return max(counts.items(), key=lambda item: item[1])[0]

    # ------------------------------------------------------------------ apply
    def _apply(self, result: ServiceResult | None) -> None:
        if result is None:
            return
        dns_needed = "DNS" in result.reason.upper() or "DNS" in result.recommendation.upper()
        strategy = result.strategy or "general.bat"
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        title = QLabel(
            f"<b>{result.name}</b> · {STATUS_LABELS.get(result.status, result.status)}<br><br>"
            f"Причина: {result.reason}<br>"
            f"Детали: {result.detail or '—'}<br>"
            f"Задержка: {result.latency_ms} мс<br><br>"
            f"<b>Рекомендация:</b> {result.recommendation or '—'}"
        )
        title.setWordWrap(True)
        title.setTextFormat(Qt.RichText)
        title.setObjectName("tiny")
        layout.addWidget(title)

        actions: list[tuple] = [("Закрыть", "ghost", self.ctx.overlay.close_panel)]
        if dns_needed:
            actions.append((
                "Сменить DNS на 1.1.1.1", "chip",
                lambda: self._confirm_dns(result),
            ))
        if result.status in {"blocked", "unstable"}:
            actions.append((
                f"Применить {strategy}", "primary",
                lambda: self._apply_strategy(strategy),
            ))
        overlays.panel_with_actions(
            self.ctx.overlay, f"{result.name} · рекомендации", content, actions
        )

    def _apply_strategy(self, filename: str) -> None:
        self.ctx.overlay.close_panel()
        engine = self.ctx.zapret
        strategies = engine.strategies()
        if not strategies:
            overlays.info(
                self.ctx.overlay, "Стратегии не найдены",
                "Укажите папку <b>zapret-discord-youtube</b> в настройках движка "
                "или установите Zapret на вкладке «Обновления».",
            )
            return
        match = next((item for item in strategies if item.filename.lower() == filename.lower()), None)
        if match is None:
            match = next(
                (item for item in strategies if item.filename.lower() == "general.bat"),
                strategies[0],
            )
        self.ctx.settings.set("zapret.strategy", match.filename)
        self.ctx.notify(f"Выбрана стратегия {match.name}", "ok")
        if engine.status == "running":
            overlays.confirm(
                self.ctx.overlay, "Перезапустить Zapret?",
                f"Текущая стратегия будет заменена на <b>{match.name}</b>.<br>"
                "winws будет перезапущен без потери соединений в Zentrix.",
                "Перезапустить",
                lambda: run_task(self, engine.restart, on_done=lambda _: self._after_apply(),
                                 on_error=lambda msg: self.ctx.notify(msg, "err", "error")),
            )
            return
        if not self.ctx.admin():
            self._admin_help()
            return
        if not engine.is_available():
            overlays.info(self.ctx.overlay, "winws.exe не найден",
                          "Проверьте папку движка в настройках.")
            return
        overlays.confirm(
            self.ctx.overlay, "Включить обход?",
            f"Zapret будет запущен со стратегией <b>{match.name}</b>. "
            "После запуска повторите проверку блокировок.",
            "Запустить Zapret",
            lambda: run_task(self, engine.start, on_done=lambda _: self._after_apply(),
                             on_error=lambda msg: self.ctx.notify(msg, "err", "error")),
        )

    def _after_apply(self) -> None:
        if self.ctx.zapret.status == "running":
            self.ctx.notify("Zapret запущен — повторите проверку", "ok", "enable")
        else:
            self.ctx.notify("Не удалось запустить Zapret", "err", "error")

    def _confirm_dns(self, result: ServiceResult) -> None:
        self.ctx.overlay.close_panel()
        if not self.ctx.admin():
            self._admin_help()
            return
        overlays.confirm(
            self.ctx.overlay, "Сменить DNS?",
            "Zentrix переключит IPv4 DNS активного сетевого адаптера на "
            "<b>1.1.1.1</b> (Cloudflare) и <b>1.0.0.1</b>.<br><br>"
            "Это может повлиять на другие приложения. Вернуть автоматические настройки "
            "можно командой <code>netsh interface ipv4 set dnsservers name=\"…\" source=dhcp</code>.",
            "Сменить DNS",
            lambda: self._run_dns_change(result),
            danger=False,
        )

    def _run_dns_change(self, result: ServiceResult) -> None:
        run_task(
            self, winapi.set_dns, "1.1.1.1", "1.0.0.1",
            on_done=lambda outcome: self._dns_done(outcome, result),
            on_error=lambda message: self.ctx.notify(f"DNS: {message}", "err", "error"),
        )

    def _dns_done(self, outcome, result: ServiceResult) -> None:
        success, detail = outcome if isinstance(outcome, tuple) else (False, str(outcome))
        if success:
            self.ctx.notify(f"DNS изменён · {detail}. Повторная проверка через 3 секунды…", "ok",
                            "update")
            from PySide6.QtCore import QTimer

            QTimer.singleShot(3000, self._start)
        else:
            self.ctx.notify(f"Не удалось сменить DNS: {detail}", "err", "error")

    def _admin_help(self) -> None:
        overlays.confirm(
            self.ctx.overlay, "Требуются права администратора",
            "Смена DNS и запуск Zapret выполняются только с повышенными правами.<br><br>"
            "Zentrix перезапустится от имени администратора, настройки сохранятся.",
            "Перезапустить",
            self.ctx.relaunch_admin,
        )

    # ----------------------------------------------------------------- export
    def _set_export_enabled(self, enabled: bool) -> None:
        for button in (self.copy_button, self.export_txt_button, self.export_json_button):
            button.setEnabled(enabled)

    def _ordered_results(self) -> list[ServiceResult]:
        if self.ctx.block_results:
            return [item for item in self.ctx.block_results if isinstance(item, ServiceResult)]
        return list(self._results.values())

    def _copy(self) -> None:
        results = self._ordered_results()
        if not results:
            return
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(report_text(results))
        self.ctx.notify("Отчёт скопирован в буфер обмена", "ok")

    def _export(self, kind: str) -> None:
        results = self._ordered_results()
        if not results:
            self.ctx.notify("Сначала выполните проверку", "warn")
            return
        default = paths.DATA_DIR / f"zentrix-blockcheck-{time.strftime('%Y%m%d-%H%M')}.{kind}"
        filters = "JSON (*.json)" if kind == "json" else "Текст (*.txt)"
        path, _selected = QFileDialog.getSaveFileName(
            self, f"Экспорт отчёта ({kind.upper()})", str(default), filters
        )
        if not path:
            return
        try:
            payload = report_json(results) if kind == "json" else report_text(results)
            Path(path).write_text(payload, encoding="utf-8")
        except OSError as exc:
            self.ctx.notify(f"Не удалось сохранить отчёт: {exc}", "err", "error")
            return
        self.ctx.notify(f"Отчёт сохранён: {Path(path).name}", "ok")

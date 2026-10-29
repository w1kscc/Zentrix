"""Blocking diagnostics: DNS, TCP and TLS/SNI probes for popular services."""

from __future__ import annotations

import json
import socket
import ssl
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Iterable

from PySide6.QtCore import QThread, Signal

from . import constants
from .logger import get_logger

log = get_logger("blockcheck")


@dataclass
class ServiceResult:
    id: str
    name: str
    host: str
    status: str = "pending"  # ok | blocked | unstable | error
    reason: str = ""
    detail: str = ""
    latency_ms: int = 0
    ip: str = ""
    reference_ip: str = ""
    dns_ok: bool = False
    tcp_ok: bool = False
    tls_ok: bool = False
    recommendation: str = ""
    strategy: str = ""
    checked_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "host": self.host, "status": self.status,
            "reason": self.reason, "detail": self.detail, "latency_ms": self.latency_ms,
            "ip": self.ip, "reference_ip": self.reference_ip, "dns_ok": self.dns_ok,
            "tcp_ok": self.tcp_ok, "tls_ok": self.tls_ok,
            "recommendation": self.recommendation, "strategy": self.strategy,
            "checked_at": self.checked_at,
        }


STATUS_LABELS = {
    "ok": "Доступен",
    "blocked": "Заблокирован",
    "unstable": "Нестабильно",
    "error": "Ошибка проверки",
    "pending": "Проверка…",
}

_DOH_CACHE: dict[str, str] = {}


def _doh_lookup(host: str, timeout: float = 5.0) -> str:
    if host in _DOH_CACHE:
        return _DOH_CACHE[host]
    result = ""
    try:
        url = f"https://dns.google/resolve?name={host}&type=A"
        request = urllib.request.Request(url, headers={"User-Agent": "Zentrix/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
        answers = [item.get("data", "") for item in payload.get("Answer", [])
                   if item.get("type") == 1]
        if answers:
            result = answers[0]
    except Exception:
        result = ""
    _DOH_CACHE[host] = result
    return result


def _system_lookup(host: str, timeout: float = 5.0) -> list[str]:
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        future = pool.submit(socket.getaddrinfo, host, 443, socket.AF_INET, socket.SOCK_STREAM)
        try:
            infos = future.result(timeout=timeout)
        except Exception:
            return []
    finally:
        pool.shutdown(wait=False, cancel_futures=True)
    addresses = []
    for info in infos:
        address = info[4][0]
        if address not in addresses:
            addresses.append(address)
    return addresses


def check_service(service: dict, tls_timeout: float = 5.0) -> ServiceResult:
    result = ServiceResult(id=service["id"], name=service["name"],
                           host=service["host"], strategy=service.get("strategy", ""))
    started = time.perf_counter()

    addresses = _system_lookup(result.host)
    result.reference_ip = _doh_lookup(result.host)
    if not addresses:
        result.status = "blocked"
        result.reason = "DNS не отвечает"
        result.detail = f"Системный DNS не вернул адрес для {result.host}"
        result.recommendation = "Сменить DNS на 1.1.1.1 или 8.8.8.8, затем повторить проверку"
        return result

    result.ip = addresses[0]
    result.dns_ok = True
    spoofed = bool(result.reference_ip and result.ip != result.reference_ip)
    if spoofed:
        result.detail = f"DNS: {result.ip} · DoH: {result.reference_ip}"

    tcp_started = time.perf_counter()
    try:
        sock = socket.create_connection((result.ip, 443), timeout=4.0)
        result.tcp_ok = True
    except ConnectionRefusedError:
        result.status = "blocked"
        result.reason = "TCP RST"
        result.detail = "Соединение отклонено на уровне TCP (RST)"
        result.recommendation = f"Запустить Zapret со стратегией «{result.strategy}»"
        return result
    except socket.timeout:
        result.status = "blocked"
        result.reason = "Таймаут TCP"
        result.detail = "Синхронизация TCP не завершилась за 4 секунды"
        result.recommendation = f"Запустить Zapret со стратегией «{result.strategy}»"
        return result
    except OSError as exc:
        result.status = "blocked"
        result.reason = "TCP недоступен"
        result.detail = str(exc)
        result.recommendation = "Проверить подключение или включить обход"
        return result

    tcp_latency = int((time.perf_counter() - tcp_started) * 1000)
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((result.ip, 443), timeout=4.0) as raw:
            raw.settimeout(tls_timeout)
            with context.wrap_socket(raw, server_hostname=result.host) as tls:
                tls.do_handshake()
        result.tls_ok = True
        result.latency_ms = int((time.perf_counter() - started) * 1000)
        if spoofed:
            result.status = "unstable"
            result.reason = "DNS-подмена"
            result.recommendation = "Сменить DNS на 1.1.1.1 / 8.8.8.8"
        elif result.latency_ms > 3500:
            result.status = "unstable"
            result.reason = "Высокая задержка"
            result.recommendation = f"Попробовать стратегию «{result.strategy}»"
        else:
            result.status = "ok"
            result.reason = "Соединение установлено"
            result.recommendation = "Вмешательство не требуется"
        return result
    except ConnectionResetError:
        result.status = "blocked"
        result.reason = "TCP RST при TLS"
        result.detail = "Сервер (или DPI) сбросил соединение во время рукопожатия"
        result.recommendation = f"Запустить Zapret со стратегией «{result.strategy}»"
    except ssl.SSLError as exc:
        result.status = "blocked"
        text = str(exc)
        reason = "SNI-блокировка" if "EOF" in text or "reset" in text.lower() else "TLS-ошибка"
        result.reason = reason
        result.detail = text[:160]
        result.recommendation = f"Запустить Zapret со стратегией «{result.strategy}»"
    except socket.timeout:
        result.status = "blocked"
        result.reason = "Таймаут TLS (SNI)"
        result.detail = "Рукопожатие не завершилось — типичный признак DPI"
        result.recommendation = f"Запустить Zapret со стратегией «{result.strategy}»"
    except OSError as exc:
        result.status = "error"
        result.reason = "Сетевая ошибка"
        result.detail = str(exc)
        result.recommendation = "Повторить проверку"
    finally:
        if not result.latency_ms:
            result.latency_ms = int((time.perf_counter() - started) * 1000)
        if not result.detail:
            result.detail = f"TCP {tcp_latency} мс"
    return result


class BlockCheckRunner(QThread):
    result_ready = Signal(object)
    progress = Signal(int, int, str)
    finished_all = Signal(list)
    failed = Signal(str)

    def __init__(self, services: Iterable[dict] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._services = list(services) if services else list(constants.SERVICES)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def run(self) -> None:
        results: list[ServiceResult] = []
        total = len(self._services)
        try:
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures = {pool.submit(check_service, service): service for service in self._services}
                for index, future in enumerate(as_completed(futures), start=1):
                    if self._stop:
                        break
                    service = futures[future]
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = ServiceResult(
                            id=service["id"], name=service["name"], host=service["host"],
                            status="error", reason="Ошибка проверки", detail=str(exc),
                        )
                    results.append(result)
                    self.result_ready.emit(result)
                    self.progress.emit(index, total, result.name)
            if not self._stop:
                order = {service["id"]: index for index, service in enumerate(self._services)}
                results.sort(key=lambda item: order.get(item.id, 99))
                self.finished_all.emit(results)
        except Exception as exc:  # pragma: no cover - defensive
            log.exception("Проверка блокировок упала: %s", exc)
            self.failed.emit(str(exc))


def report_text(results: list[ServiceResult]) -> str:
    lines = ["Zentrix — отчёт о проверке блокировок",
             time.strftime("Дата: %d.%m.%Y %H:%M"), ""]
    for result in results:
        lines.append(f"{result.name} ({result.host})")
        lines.append(f"  Статус: {STATUS_LABELS.get(result.status, result.status)}")
        lines.append(f"  Причина: {result.reason}")
        if result.detail:
            lines.append(f"  Детали: {result.detail}")
        lines.append(f"  Задержка: {result.latency_ms} мс")
        lines.append(f"  Рекомендация: {result.recommendation}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def report_json(results: list[ServiceResult]) -> str:
    return json.dumps(
        {
            "app": "Zentrix",
            "generated_at": time.time(),
            "results": [result.as_dict() for result in results],
        },
        ensure_ascii=False,
        indent=2,
    )

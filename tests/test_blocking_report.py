"""Blocking-check report formatting and result serialisation."""

from __future__ import annotations

import json

from src.blocking_check import ServiceResult, report_json, report_text


def _result(status: str = "ok") -> ServiceResult:
    return ServiceResult(
        id="youtube", name="YouTube", host="www.youtube.com", status=status,
        reason="Соединение установлено", detail="TCP 42 мс", latency_ms=42,
        ip="142.250.0.1", dns_ok=True, tcp_ok=True, tls_ok=True,
        recommendation="Вмешательство не требуется", strategy="general.bat",
    )


def test_text_report_contains_key_fields() -> None:
    text = report_text([_result()])
    assert "Zentrix" in text
    assert "YouTube (www.youtube.com)" in text
    assert "Доступен" in text
    assert "42 мс" in text
    assert "Вмешательство не требуется" in text


def test_json_report_roundtrips() -> None:
    payload = json.loads(report_json([_result("blocked")]))
    assert payload["app"] == "Zentrix"
    assert payload["results"][0]["status"] == "blocked"
    assert payload["results"][0]["tls_ok"] is True
    assert isinstance(payload["generated_at"], float)

"""Slack 웹훅 알림 — PRD §8.3.

조건:
- FAIL run 발생
- 같은 사이트 연속 2회 WARN
- 36시간 무 OK 수집 (장기 무수집)

웹훅 URL이 설정되지 않으면 silent skip.
"""

from __future__ import annotations

import httpx
import structlog

from total_support.config import get_settings

logger = structlog.get_logger(__name__)


def notify(text: str, *, level: str = "INFO") -> bool:
    """Slack 채널에 단순 메시지 전송. URL이 없으면 False, 전송 시 True."""
    settings = get_settings()
    url = settings.slack_webhook_url
    if not url:
        return False

    color = {"INFO": "#36a64f", "WARN": "#eab308", "ERROR": "#ef4444"}.get(level, "#94a3b8")
    payload = {
        "attachments": [
            {
                "color": color,
                "title": f"[{level}] Total Support · 수집 모듈",
                "text": text,
                "footer": "total_support backend",
            }
        ]
    }
    try:
        r = httpx.post(url, json=payload, timeout=10.0)
        r.raise_for_status()
        return True
    except httpx.HTTPError as e:
        logger.warning("slack_notify_failed", error=str(e))
        return False

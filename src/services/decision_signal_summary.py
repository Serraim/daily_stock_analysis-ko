# -*- coding: utf-8 -*-
"""Low-sensitive DecisionSignal summaries for notifications and risk views."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.utils.sanitize import sanitize_decision_signal_payload, sanitize_decision_signal_text


SUMMARY_FIELDS = (
    "id",
    "stock_code",
    "stock_name",
    "market",
    "action",
    "action_label",
    "horizon",
    "status",
    "source_type",
    "source_report_id",
    "reason",
    "watch_conditions",
    "risk_summary",
    "created_at",
    "expires_at",
)


def summarize_decision_signal(item: Any) -> Optional[Dict[str, Any]]:
    """Return a low-sensitive summary from a serialized DecisionSignal item."""

    if not isinstance(item, dict):
        return None
    summary: Dict[str, Any] = {}
    for field_name in SUMMARY_FIELDS:
        value = item.get(field_name)
        if value in (None, "", [], {}):
            continue
        summary[field_name] = sanitize_decision_signal_payload(value)
    return summary or None


def format_decision_signal_excerpt(summary: Any, report_language: str = "zh") -> str:
    """Format a compact public DecisionSignal excerpt for notification text."""

    if not isinstance(summary, dict) or not summary:
        return ""
    lowered_language = str(report_language or "").lower()
    if lowered_language.startswith("en"):
        language = "en"
    elif lowered_language.startswith(("ko", "kr")):
        language = "ko"
    else:
        language = "zh"
    labels = {
        "zh": {
            "heading": "AI 决策信号",
            "action": "动作",
            "horizon": "周期",
            "reason": "理由",
            "watch_conditions": "观察条件",
            "risk_summary": "风险",
            "source_report_id": "报告",
        },
        "en": {
            "heading": "AI decision signal",
            "action": "Action",
            "horizon": "Horizon",
            "reason": "Reason",
            "watch_conditions": "Watch",
            "risk_summary": "Risk",
            "source_report_id": "Report",
        },
        "ko": {
            "heading": "AI 매매 신호",
            "action": "행동",
            "horizon": "기간",
            "reason": "근거",
            "watch_conditions": "관찰 조건",
            "risk_summary": "리스크",
            "source_report_id": "리포트",
        },
    }[language]

    parts = []
    action_label = _public_scalar(summary.get("action_label") or summary.get("action"), max_length=32)
    if action_label:
        parts.append(f"{labels['action']}: {action_label}")
    horizon = _public_scalar(summary.get("horizon"), max_length=16)
    if horizon:
        parts.append(f"{labels['horizon']}: {horizon}")
    source_report_id = _public_scalar(summary.get("source_report_id"), max_length=24)
    if source_report_id:
        parts.append(f"{labels['source_report_id']}: #{source_report_id}")

    lines = [f"**{labels['heading']}**"]
    if parts:
        lines.append(" | ".join(parts))
    for key in ("reason", "watch_conditions", "risk_summary"):
        max_length = None if key == "reason" else 120
        text = _public_text(summary.get(key), max_length=max_length, separator="; " if language == "ko" else "；")
        if text:
            lines.append(f"- {labels[key]}: {text}")
    return "\n".join(lines)


def _public_scalar(value: Any, *, max_length: int) -> str:
    if value in (None, ""):
        return ""
    return sanitize_decision_signal_text(value)[:max_length]


def _public_text(value: Any, *, max_length: Optional[int], separator: str = "；") -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, (list, tuple)):
        text = separator.join(str(item).strip() for item in value if str(item or "").strip())
    elif isinstance(value, dict):
        text = separator.join(
            f"{key}: {item}"
            for key, item in value.items()
            if str(key or "").strip() and str(item or "").strip()
        )
    else:
        text = str(value).strip()
    sanitized = sanitize_decision_signal_text(text)
    return sanitized if max_length is None else sanitized[:max_length]

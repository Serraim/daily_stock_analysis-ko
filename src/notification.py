# -*- coding: utf-8 -*-
"""
===================================
A주 관심종목 AI 분석 시스템 - 알림 계층
===================================

역할:
1. 분석 결과를 모아 일일 리포트 생성
2. Markdown 형식 출력 지원
3. 여러 채널로 발송(자동 감지):
   - WeCom(기업용 위챗) Webhook
   - Feishu Webhook
   - Telegram Bot
   - 이메일 SMTP
   - Pushover(모바일/데스크톱 알림)
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from enum import Enum

from src.config import Config, get_config
from src.enums import ReportType
from src.market_phase_summary import format_public_market_status_line, format_public_phase_pack_excerpt
from src.notification_routing import (
    get_notification_route_config,
    split_notification_route_channels,
)
from src.notification_contracts import is_feishu_static_configured
from src.notification_noise import (
    NotificationNoiseDecision,
    evaluate_notification_noise,
    record_notification_noise,
    release_notification_noise,
)
from src.report_language import (
    format_korean_amount,
    format_korean_volume,
    get_korean_currency_word,
    get_localized_stock_name,
    get_report_labels,
    get_signal_level,
    get_chip_unavailable_reason,
    is_chip_structure_unavailable,
    localize_chip_health,
    localize_conflict_severity,
    localize_consensus_level,
    localize_strategy_signal,
    localize_strategy_skill,
    localize_strategy_conflict_description,
    localize_strategy_synthesis_summary,
    localize_bias_status,
    localize_data_sources_text,
    localize_display_phrase,
    localize_trend_prediction,
    normalize_report_language,
    normalize_strategy_synthesis_payload,
    strategy_invalid_opinion_count,
)
from src.schemas.decision_action import (
    display_action_fields_for_result,
    display_decision_type_for_result,
    display_operation_advice_for_result,
)
from bot.models import BotMessage
from src.utils.sanitize import sanitize_diagnostic_text
from src.formatters import strip_hidden_markdown_metadata
from src.utils.data_processing import (
    signal_attribution_has_content,
    signal_attribution_weight_items,
    normalize_model_used,
)
from src.notification_sender import (
    AstrbotSender,
    CustomWebhookSender,
    DingtalkSender,
    DiscordSender,
    EmailSender,
    FeishuSender,
    GotifySender,
    NtfySender,
    PushoverSender,
    PushplusSender,
    Serverchan3Sender,
    SlackSender,
    TelegramSender,
    WechatSender,
    WECHAT_IMAGE_MAX_BYTES,
    resolve_gotify_message_endpoint,
    resolve_ntfy_endpoint,
)

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    """Best-effort float conversion; handles `"3.2%"` and `"1,234"` shapes."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    text = str(value).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1].strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _format_strategy_skill_items(items: Any, report_language: str = "zh") -> str:
    none_text = get_report_labels(report_language).get("none_label", "None")
    if not isinstance(items, list):
        return none_text
    formatted: List[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        skill_id = str(item.get("skill_id") or "").strip()
        signal = str(item.get("signal") or "").strip()
        confidence = item.get("confidence")
        if not skill_id:
            continue
        suffix = f"/{localize_strategy_signal(signal, report_language)}" if signal else ""
        if isinstance(confidence, (int, float)):
            suffix += f"/{confidence:.0%}"
        formatted.append(f"{localize_strategy_skill(skill_id, report_language)}{suffix}")
    return "、".join(formatted) if formatted else none_text


def _append_strategy_synthesis_block(lines: List[str], strategy_synthesis: Any, labels: Dict[str, str], report_language: str) -> None:
    strategy_synthesis = normalize_strategy_synthesis_payload(strategy_synthesis)
    if not strategy_synthesis:
        return
    confidence = strategy_synthesis.get("confidence")
    confidence_text = f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "N/A"
    lines.extend([
        f"### 🧩 {labels['strategy_synthesis_heading']}",
        "",
        (
            f"- {labels['strategy_final_signal_label']}: "
            f"{localize_strategy_signal(strategy_synthesis.get('final_signal', 'N/A'), report_language)} | "
            f"{labels['strategy_consensus_level_label']}: "
            f"{localize_consensus_level(strategy_synthesis.get('consensus_level', 'N/A'), report_language)} | "
            f"{labels['strategy_conflict_label']}: "
            f"{localize_conflict_severity(strategy_synthesis.get('conflict_severity', 'none'), report_language)} "
            f"({strategy_synthesis.get('conflict_count', 0)}) | "
            f"{labels['strategy_confidence_label']}: {confidence_text}"
        ),
    ])
    summary = localize_strategy_synthesis_summary(strategy_synthesis, report_language)
    if summary:
        lines.append(f"- {labels['strategy_summary_label']}: {summary}")
    lines.append(
        f"- {labels['strategy_supporting_skills_label']}: "
        f"{_format_strategy_skill_items(strategy_synthesis.get('supporting_skills'), report_language)}"
    )
    lines.append(
        f"- {labels['strategy_opposing_skills_label']}: "
        f"{_format_strategy_skill_items(strategy_synthesis.get('opposing_skills'), report_language)}"
    )
    invalid_opinion_count = strategy_invalid_opinion_count(strategy_synthesis)
    if invalid_opinion_count:
        invalid_label = labels.get("strategy_invalid_opinions_label", "")
        if invalid_label:
            lines.append(f"- {invalid_label.format(count=invalid_opinion_count)}")
    for conflict in (strategy_synthesis.get("conflicts") or [])[:3]:
        if isinstance(conflict, dict) and conflict.get("conflict_type"):
            participants = conflict.get("participants") or []
            participant_text = "、".join(localize_strategy_skill(participant, report_language) for participant in participants)
            suffix = f"（{participant_text}）" if participant_text else ""
            lines.append(
                f"- {localize_conflict_severity(conflict.get('severity', 'medium'), report_language)}: "
                f"{localize_strategy_conflict_description(conflict.get('conflict_type'), report_language)}{suffix}"
            )
    lines.append("")

if TYPE_CHECKING:
    from src.analyzer import AnalysisResult


class NotificationChannel(Enum):
    """알림 채널 종류"""
    WECHAT = "wechat"      # WeCom(기업용 위챗)
    DINGTALK = "dingtalk"
    FEISHU = "feishu"      # Feishu
    TELEGRAM = "telegram"  # Telegram
    EMAIL = "email"        # 이메일
    PUSHOVER = "pushover"  # Pushover(모바일/데스크톱 알림)
    NTFY = "ntfy"          # ntfy
    GOTIFY = "gotify"      # Gotify
    PUSHPLUS = "pushplus"  # PushPlus(중국 내 알림 서비스)
    SERVERCHAN3 = "serverchan3"  # ServerChan3(모바일 앱 알림 서비스)
    CUSTOM = "custom"      # 사용자 정의 Webhook
    DISCORD = "discord"    # Discord 봇(Bot)
    SLACK = "slack"        # Slack
    ASTRBOT = "astrbot"
    UNKNOWN = "unknown"    # 알 수 없음


@dataclass
class ChannelAttemptResult:
    """One static notification channel send attempt."""

    channel: str
    success: bool
    error_code: Optional[str] = None
    retryable: bool = False
    latency_ms: Optional[int] = None
    diagnostics: Optional[str] = None


@dataclass
class NotificationDispatchResult:
    """Structured result for notification dispatch diagnostics."""

    dispatched: bool
    success: bool
    status: str
    channel_results: List[ChannelAttemptResult] = field(default_factory=list)
    message: Optional[str] = None


class ChannelDetector:
    """
    채널 감지기 - 간소화 버전

    설정만 보고 채널 종류를 바로 판단한다(URL 파싱 불필요)
    """

    @staticmethod
    def get_channel_name(channel: NotificationChannel) -> str:
        """채널 표시 이름(중국어)을 반환한다"""
        names = {
            NotificationChannel.WECHAT: "企业微信",
            NotificationChannel.FEISHU: "飞书",
            NotificationChannel.DINGTALK: "钉钉",
            NotificationChannel.TELEGRAM: "Telegram",
            NotificationChannel.EMAIL: "邮件",
            NotificationChannel.PUSHOVER: "Pushover",
            NotificationChannel.NTFY: "ntfy",
            NotificationChannel.GOTIFY: "Gotify",
            NotificationChannel.PUSHPLUS: "PushPlus",
            NotificationChannel.SERVERCHAN3: "Server酱3",
            NotificationChannel.CUSTOM: "自定义Webhook",
            NotificationChannel.DISCORD: "Discord机器人",
            NotificationChannel.SLACK: "Slack",
            NotificationChannel.ASTRBOT: "ASTRBOT机器人",
            NotificationChannel.UNKNOWN: "未知渠道",
        }
        return names.get(channel, "未知渠道")


class NotificationService(
    AstrbotSender,
    CustomWebhookSender,
    DingtalkSender,
    DiscordSender,
    EmailSender,
    FeishuSender,
    GotifySender,
    NtfySender,
    PushoverSender,
    PushplusSender,
    Serverchan3Sender,
    SlackSender,
    TelegramSender,
    WechatSender
):
    """
    알림 서비스

    역할:
    1. Markdown 형식의 일일 분석 리포트 생성
    2. 설정된 모든 채널로 메시지 발송(여러 채널 동시 발송)
    3. 일일 리포트 로컬 저장 지원

    지원 채널:
    - WeCom(기업용 위챗) Webhook
    - Feishu Webhook
    - Telegram Bot
    - 이메일 SMTP
    - Pushover(모바일/데스크톱 알림)

    참고: 설정된 모든 채널이 알림을 받는다
    """

    def __init__(self, source_message: Optional[BotMessage] = None):
        """
        알림 서비스 초기화

        설정된 채널을 모두 감지하고, 발송 시 전체 채널로 보낸다
        """
        config = get_config()
        self._config = config
        self._source_message = source_message
        self._context_channels: List[str] = []

        # Markdown을 이미지로 변환(Issue #289)
        self._markdown_to_image_channels = set(
            getattr(config, 'markdown_to_image_channels', []) or []
        )
        self._markdown_to_image_max_chars = getattr(
            config, 'markdown_to_image_max_chars', 15000
        )

        # 분석 결과 요약만 발송(Issue #262): true이면 종목별 상세 없이 요약만 보낸다
        self._report_summary_only = getattr(config, 'report_summary_only', False)
        self._report_show_llm_model = getattr(config, 'report_show_llm_model', True)
        self._history_compare_cache: Dict[Tuple[int, str, Tuple[Tuple[str, str], ...]], Dict[str, List[Dict[str, Any]]]] = {}

        # 채널별 초기화
        AstrbotSender.__init__(self, config)
        CustomWebhookSender.__init__(self, config)
        DiscordSender.__init__(self, config)
        EmailSender.__init__(self, config)
        FeishuSender.__init__(self, config)
        GotifySender.__init__(self, config)
        NtfySender.__init__(self, config)
        PushoverSender.__init__(self, config)
        PushplusSender.__init__(self, config)
        Serverchan3Sender.__init__(self, config)
        SlackSender.__init__(self, config)
        TelegramSender.__init__(self, config)
        WechatSender.__init__(self, config)
        DingtalkSender.__init__(self, config)

        # 설정된 채널 모두 감지
        self._available_channels = self._detect_all_channels()
        if self._extract_dingtalk_session_webhook() is not None:
            self._context_channels.append("钉钉会话")
        if self._extract_feishu_reply_info() is not None:
            self._context_channels.append("飞书会话")

        if not self._available_channels and not self._context_channels:
            logger.warning("유효한 알림 채널이 설정되지 않아 알림을 보내지 않습니다")
        else:
            channel_names = [ChannelDetector.get_channel_name(ch) for ch in self._available_channels]
            channel_names.extend(self._context_channels)
            logger.info(f"알림 채널 {len(channel_names)}개 설정됨: {', '.join(channel_names)}")

    def _normalize_report_type(self, report_type: Any) -> ReportType:
        """Normalize string/enum input into ReportType."""
        if isinstance(report_type, ReportType):
            return report_type
        return ReportType.from_str(report_type)

    def _get_report_language(self, payload: Optional[Any] = None) -> str:
        """Resolve report language from result payload or global config."""
        if isinstance(payload, list):
            for item in payload:
                language = getattr(item, "report_language", None)
                if language:
                    return normalize_report_language(language)
        elif payload is not None:
            language = getattr(payload, "report_language", None)
            if language:
                return normalize_report_language(language)

        return normalize_report_language(getattr(get_config(), "report_language", "zh"))

    def _get_labels(self, payload: Optional[Any] = None) -> Dict[str, str]:
        return get_report_labels(self._get_report_language(payload))

    def _get_display_name(self, result: AnalysisResult, language: Optional[str] = None) -> str:
        report_language = normalize_report_language(language or self._get_report_language(result))
        display_name = get_localized_stock_name(result.name, result.code, report_language)
        if report_language == "ko":
            display_name = self._korean_display_name(display_name, getattr(result, "code", ""))
        return self._escape_md(display_name)

    @staticmethod
    def _korean_display_name(name: str, code: Any) -> str:
        """ko 보고서에서 한국 종목(.KS/.KQ)이 영문 약칭으로 나오면 한국어 회사 이름으로 바꾼다."""
        code_text = str(code or "").strip().upper()
        if not code_text.endswith((".KS", ".KQ")):
            return name
        if any("\uac00" <= ch <= "\ud7a3" for ch in str(name or "")):
            return name
        try:
            from src.search_service import _korean_stock_name

            korean_name = _korean_stock_name(code_text)
        except Exception as exc:  # 이름 조회 실패는 보고서 생성을 막지 않는다
            logger.debug("Korean stock name lookup skipped for %s: %s", code_text, exc)
            korean_name = None
        return korean_name or name

    def _get_history_compare_context(self, results: List[AnalysisResult]) -> Dict[str, Any]:
        """Fetch and cache history comparison data for markdown rendering."""
        config = get_config()
        history_compare_n = getattr(config, 'report_history_compare_n', 0)
        if history_compare_n <= 0 or not results:
            return {"history_by_code": {}}

        report_language = self._get_report_language(results)

        cache_key = (
            history_compare_n,
            report_language,
            tuple(sorted((r.code, getattr(r, 'query_id', '') or '') for r in results)),
        )
        if cache_key in self._history_compare_cache:
            return {"history_by_code": self._history_compare_cache[cache_key]}

        try:
            from src.services.history_comparison_service import get_signal_changes_batch

            exclude_ids = {
                r.code: r.query_id
                for r in results
                if getattr(r, 'query_id', None)
            }
            codes = list(dict.fromkeys(r.code for r in results))
            history_by_code = get_signal_changes_batch(
                codes,
                limit=history_compare_n,
                exclude_query_ids=exclude_ids,
                report_language=report_language,
            )
        except Exception as e:
            logger.debug("History comparison skipped: %s", e)
            history_by_code = {}

        self._history_compare_cache[cache_key] = history_by_code
        return {"history_by_code": history_by_code}

    @staticmethod
    def _empty_news_disclosure(result: "AnalysisResult", language: str = "zh") -> Optional[str]:
        """뉴스 검색을 하지 않았거나 결과가 0건일 때 해당 안내 문구를 반환한다.

        판정 기준과 문구는 src/services/empty_news에서 일괄 관리한다. 문자열 조합 렌더러와 템플릿
        렌더링 경로가 같은 구현을 공유해, 같은 분석 결과를 어떤 채널은 안내하고 어떤 채널은 빠뜨리는 일을 막는다.
        """
        from src.services.empty_news import empty_news_disclosure

        return empty_news_disclosure(result, language)

    @staticmethod
    def _append_data_sources_line(
        lines: List[str],
        result: AnalysisResult,
        labels: Dict[str, str],
    ) -> bool:
        data_sources = getattr(result, "data_sources", None)
        if not isinstance(data_sources, str):
            return False
        data_sources = data_sources.strip()
        if not data_sources:
            return False
        data_sources = localize_data_sources_text(data_sources, getattr(result, "report_language", None))
        lines.append(f"*📋 {labels['data_sources_label']}：{data_sources}*")
        return True

    def generate_aggregate_report(
        self,
        results: List[AnalysisResult],
        report_type: Any,
        report_date: Optional[str] = None,
    ) -> str:
        """Generate the aggregate report content used by merge/save/push paths."""
        normalized_type = self._normalize_report_type(report_type)
        if normalized_type == ReportType.BRIEF:
            return self.generate_brief_report(results, report_date=report_date)
        return self.generate_dashboard_report(results, report_date=report_date)

    def _collect_models_used(self, results: List[AnalysisResult]) -> List[str]:
        if not self._should_show_llm_model():
            return []
        models: List[str] = []
        for result in results:
            model = normalize_model_used(getattr(result, "model_used", None))
            if model:
                models.append(model)
        return list(dict.fromkeys(models))

    def _public_phase_pack_excerpt(self, result: AnalysisResult, report_language: str) -> str:
        return format_public_phase_pack_excerpt(
            getattr(result, "market_phase_summary", None),
            getattr(result, "analysis_context_pack_overview", None),
            source=getattr(result, "analysis_visibility_source", None) or "evaluator_snapshot",
            report_language=report_language,
        )

    def _public_market_status_line(self, results: List[AnalysisResult], report_language: str) -> str:
        for result in results or []:
            line = format_public_market_status_line(
                getattr(result, "market_phase_summary", None),
                report_language=report_language,
            )
            if line:
                return line
        return ""

    def _append_market_status_line(
        self,
        lines: List[str],
        results: List[AnalysisResult],
        report_language: str,
    ) -> None:
        status_line = self._public_market_status_line(results, report_language)
        if status_line:
            lines.extend([status_line, ""])
        elif lines and lines[-1] != "":
            lines.append("")

    def _should_show_llm_model(self) -> bool:
        return bool(getattr(self._config, "report_show_llm_model", self._report_show_llm_model))

    @staticmethod
    def detect_configured_channels(config: Config) -> List[NotificationChannel]:
        """
        Detect statically configured notification channels from Config.

        This intentionally mirrors sender availability without instantiating
        sender objects, so diagnostics and runtime use the same channel truth.
        Runtime-only context channels are handled by instance methods.
        """
        channels = []

        if getattr(config, "wechat_webhook_url", None):
            channels.append(NotificationChannel.WECHAT)
        if getattr(config, "dingtalk_webhook_url", None):
            channels.append(NotificationChannel.DINGTALK)    

        if is_feishu_static_configured(config):
            channels.append(NotificationChannel.FEISHU)

        if (
            getattr(config, "telegram_bot_token", None)
            and getattr(config, "telegram_chat_id", None)
        ):
            channels.append(NotificationChannel.TELEGRAM)

        if getattr(config, "email_sender", None) and getattr(config, "email_password", None):
            channels.append(NotificationChannel.EMAIL)

        if (
            getattr(config, "pushover_user_key", None)
            and getattr(config, "pushover_api_token", None)
        ):
            channels.append(NotificationChannel.PUSHOVER)

        ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(getattr(config, "ntfy_url", None))
        if ntfy_server_url and ntfy_topic:
            channels.append(NotificationChannel.NTFY)

        gotify_endpoint = resolve_gotify_message_endpoint(getattr(config, "gotify_url", None))
        if gotify_endpoint and (getattr(config, "gotify_token", None) or "").strip():
            channels.append(NotificationChannel.GOTIFY)

        if getattr(config, "pushplus_token", None):
            channels.append(NotificationChannel.PUSHPLUS)

        if getattr(config, "serverchan3_sendkey", None):
            channels.append(NotificationChannel.SERVERCHAN3)

        if getattr(config, "custom_webhook_urls", None):
            channels.append(NotificationChannel.CUSTOM)

        if (
            getattr(config, "discord_webhook_url", None)
            or (
                getattr(config, "discord_bot_token", None)
                and getattr(config, "discord_main_channel_id", None)
            )
        ):
            channels.append(NotificationChannel.DISCORD)

        if (
            getattr(config, "slack_webhook_url", None)
            or (
                getattr(config, "slack_bot_token", None)
                and getattr(config, "slack_channel_id", None)
            )
        ):
            channels.append(NotificationChannel.SLACK)

        if getattr(config, "astrbot_url", None):
            channels.append(NotificationChannel.ASTRBOT)

        return channels

    def _detect_all_channels(self) -> List[NotificationChannel]:
        """
        설정된 채널을 모두 감지한다

        Returns:
            설정된 채널 목록
        """
        return self.detect_configured_channels(self._config)

    def is_available(self) -> bool:
        """알림 서비스 사용 가능 여부 확인(채널 또는 컨텍스트 채널이 하나 이상 있어야 함)"""
        return len(self._available_channels) > 0 or self._has_context_channel()

    def get_available_channels(self) -> List[NotificationChannel]:
        """설정된 채널 전체를 반환한다"""
        return self._available_channels

    def get_channels_for_route(
        self,
        route_type: Optional[str],
        channels: Optional[List[NotificationChannel]] = None,
    ) -> List[NotificationChannel]:
        """Return channels allowed for a route type.

        ``route_type=None`` keeps the legacy behavior and returns all supplied
        static channels. Empty route config also keeps all supplied channels.
        Non-empty route config that matches no enabled channel returns an empty
        list.
        """
        target_channels = list(channels if channels is not None else self._available_channels)
        if route_type is None:
            return target_channels

        route_config = get_notification_route_config(route_type)
        if route_config is None:
            logger.warning("알 수 없는 알림 라우팅 유형 %s, 설정된 채널 전체를 그대로 사용합니다", route_type)
            return target_channels

        configured_route_channels = getattr(self._config, route_config["config_attr"], []) or []
        if not configured_route_channels:
            return target_channels

        valid_channels, invalid_channels = split_notification_route_channels(configured_route_channels)
        if invalid_channels:
            logger.warning(
                "%s에 알 수 없는 알림 채널이 있어 무시합니다: %s",
                route_config["env_key"],
                ", ".join(invalid_channels),
            )

        allowed = set(valid_channels)
        return [channel for channel in target_channels if channel.value in allowed]

    def get_channel_names(self) -> str:
        """설정된 채널 전체의 이름을 반환한다"""
        names = [ChannelDetector.get_channel_name(ch) for ch in self._available_channels]
        if self._has_context_channel():
            names.append("钉钉会话")
        return ', '.join(names)

    def evaluate_noise_control(
        self,
        content: str,
        *,
        route_type: Optional[str] = None,
        severity: Optional[str] = None,
        dedup_key: Optional[str] = None,
        cooldown_key: Optional[str] = None,
    ) -> NotificationNoiseDecision:
        """Evaluate static-channel notification noise controls."""
        return evaluate_notification_noise(
            self._config,
            content=content,
            route_type=route_type,
            severity=severity,
            dedup_key=dedup_key,
            cooldown_key=cooldown_key,
        )

    @staticmethod
    def record_noise_control(decision: NotificationNoiseDecision) -> None:
        """Record static-channel notification noise state after a successful send."""
        record_notification_noise(decision)

    @staticmethod
    def release_noise_control(decision: NotificationNoiseDecision) -> None:
        """Release static-channel in-flight noise reservation after send failure."""
        release_notification_noise(decision)

    # ===== Context channel =====
    def _has_context_channel(self) -> bool:
        """메시지 컨텍스트 기반 임시 채널(DingTalk 대화, Feishu 대화 등)이 있는지 판단한다"""
        return (
            self._extract_dingtalk_session_webhook() is not None
            or self._extract_feishu_reply_info() is not None
            or self._extract_telegram_context_chat_id() is not None
        )

    def _source_platform(self) -> str:
        """Return normalized platform from the source bot message."""
        platform = getattr(self._source_message, "platform", "")
        if hasattr(platform, "value"):
            platform = platform.value
        return str(platform or "").lower()

    def _extract_telegram_context_chat_id(self) -> Optional[str]:
        """원본 메시지에서 Telegram 컨텍스트 chat_id를 추출한다(비동기 답장용)."""
        if not isinstance(self._source_message, BotMessage):
            return None
        if self._source_platform() != "telegram":
            return None
        raw_data = getattr(self._source_message, "raw_data", {}) or {}
        for candidate in (
            getattr(self._source_message, "chat_id", ""),
            raw_data.get("chat_id"),
            raw_data.get("message", {}).get("chat", {}).get("id") if isinstance(raw_data.get("message"), dict) else None,
        ):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if candidate is not None and not isinstance(candidate, str):
                candidate_text = str(candidate).strip()
                if candidate_text:
                    return candidate_text
        return None

    def should_broadcast_static_channels(self) -> bool:
        """Whether static notification channels should receive this dispatch."""
        return not self._has_context_channel()

    def _extract_dingtalk_session_webhook(self) -> Optional[str]:
        """원본 메시지에서 DingTalk 대화 Webhook을 추출한다(Stream 모드 답장용)"""
        if not isinstance(self._source_message, BotMessage):
            return None
        raw_data = getattr(self._source_message, "raw_data", {}) or {}
        if not isinstance(raw_data, dict):
            return None
        session_webhook = (
            raw_data.get("_session_webhook")
            or raw_data.get("sessionWebhook")
            or raw_data.get("session_webhook")
            or raw_data.get("session_webhook_url")
        )
        if not session_webhook and isinstance(raw_data.get("headers"), dict):
            session_webhook = raw_data["headers"].get("sessionWebhook")
        return session_webhook

    def _extract_feishu_reply_info(self) -> Optional[Dict[str, str]]:
        """
        원본 메시지에서 Feishu 답장 정보를 추출한다(Stream 모드 답장용)

        Returns:
            chat_id를 담은 dict, 또는 None
        """
        if not isinstance(self._source_message, BotMessage):
            return None
        if getattr(self._source_message, "platform", "") != "feishu":
            return None
        chat_id = getattr(self._source_message, "chat_id", "")
        if not chat_id:
            return None
        return {"chat_id": chat_id}

    def send_to_context(self, content: str) -> bool:
        """
        메시지 컨텍스트 기반 채널로 메시지를 보낸다(예: DingTalk Stream 대화)

        Args:
            content: Markdown 형식 내용
        """
        return self._send_via_source_context(content)

    def _send_via_source_context(self, content: str) -> bool:
        """
        메시지 컨텍스트(DingTalk/Feishu 대화 등)로 리포트 한 건을 보낸다

        주로 봇 Stream 모드에서 시작된 작업에 쓰며, 결과가 요청한 대화로 돌아가도록 보장한다.
        """
        success = False

        # DingTalk 대화로 시도
        session_webhook = self._extract_dingtalk_session_webhook()
        if session_webhook:
            try:
                if self._send_dingtalk_chunked(session_webhook, content, max_bytes=20000):
                    logger.info("DingTalk 대화(Stream)로 리포트를 보냈습니다")
                    success = True
                else:
                    logger.error("DingTalk 대화(Stream) 발송 실패")
            except Exception as e:
                logger.error(f"DingTalk 대화(Stream) 발송 중 예외: {e}")

        # Feishu 대화로 시도
        feishu_info = self._extract_feishu_reply_info()
        if feishu_info:
            try:
                sanitized_content = strip_hidden_markdown_metadata(content).strip()
                if self._send_feishu_stream_reply(feishu_info["chat_id"], sanitized_content):
                    logger.info("Feishu 대화(Stream)로 리포트를 보냈습니다")
                    success = True
                else:
                    logger.error("Feishu 대화(Stream) 발송 실패")
            except Exception as e:
                logger.error(f"Feishu 대화(Stream) 발송 중 예외: {e}")

        # Telegram 대화 컨텍스트로 시도(원본 chat_id로 회신)
        telegram_chat_id = self._extract_telegram_context_chat_id()
        if telegram_chat_id:
            try:
                if self.send_to_telegram(content, chat_id=telegram_chat_id):
                    logger.info("Telegram 컨텍스트 대화로 리포트를 보냈습니다")
                    success = True
                else:
                    logger.error("Telegram 컨텍스트 대화 발송 실패")
            except Exception as e:
                logger.error(f"Telegram 컨텍스트 대화 발송 중 예외: {e}")

        return success

    def _send_feishu_stream_reply(self, chat_id: str, content: str) -> bool:
        """
        Feishu Stream 모드로 지정한 대화에 메시지를 보낸다

        Args:
            chat_id: Feishu 대화 ID
            content: 메시지 내용

        Returns:
            발송 성공 여부
        """
        try:
            from bot.platforms.feishu_stream import FeishuReplyClient, FEISHU_SDK_AVAILABLE
            if not FEISHU_SDK_AVAILABLE:
                logger.warning("Feishu SDK를 사용할 수 없어 Stream 답장을 보낼 수 없습니다")
                return False

            from src.config import get_config
            config = get_config()

            app_id = getattr(config, 'feishu_app_id', None)
            app_secret = getattr(config, 'feishu_app_secret', None)

            if not app_id or not app_secret:
                logger.warning("Feishu APP_ID 또는 APP_SECRET이 설정되지 않았습니다")
                return False

            # 답장 클라이언트 생성
            reply_client = FeishuReplyClient(app_id, app_secret)

            # Feishu 텍스트 메시지는 길이 제한이 있어 나눠서 보내야 한다
            max_bytes = getattr(config, 'feishu_max_bytes', 20000)
            content = strip_hidden_markdown_metadata(content).strip()
            content_bytes = len(content.encode('utf-8'))

            if content_bytes > max_bytes:
                return self._send_feishu_stream_chunked(reply_client, chat_id, content, max_bytes)

            return reply_client.send_to_chat(chat_id, content)

        except ImportError as e:
            logger.error(f"Feishu Stream 모듈 import 실패: {e}")
            return False
        except Exception as e:
            logger.error(f"Feishu Stream 답장 중 예외: {e}")
            return False

    def _send_feishu_stream_chunked(
        self,
        reply_client,
        chat_id: str,
        content: str,
        max_bytes: int
    ) -> bool:
        """
        긴 메시지를 Feishu로 나눠서 보낸다(Stream 모드)

        Args:
            reply_client: FeishuReplyClient 인스턴스
            chat_id: Feishu 대화 ID
            content: 전체 메시지 내용
            max_bytes: 메시지 1건의 최대 바이트 수

        Returns:
            전부 발송 성공 여부
        """
        import time

        def get_bytes(s: str) -> int:
            return len(s.encode('utf-8'))

        # 단락 또는 구분선 기준으로 분할
        if "\n---\n" in content:
            sections = content.split("\n---\n")
            separator = "\n---\n"
        elif "\n### " in content:
            parts = content.split("\n### ")
            sections = [parts[0]] + [f"### {p}" for p in parts[1:]]
            separator = "\n"
        else:
            # 줄 단위로 분할
            sections = content.split("\n")
            separator = "\n"

        chunks = []
        current_chunk = []
        current_bytes = 0
        separator_bytes = get_bytes(separator)

        for section in sections:
            section_bytes = get_bytes(section) + separator_bytes

            if current_bytes + section_bytes > max_bytes:
                if current_chunk:
                    chunks.append(separator.join(current_chunk))
                current_chunk = [section]
                current_bytes = section_bytes
            else:
                current_chunk.append(section)
                current_bytes += section_bytes

        if current_chunk:
            chunks.append(separator.join(current_chunk))

        # 분할 조각을 하나씩 발송
        success = True
        for i, chunk in enumerate(chunks):
            if i > 0:
                time.sleep(0.5)  # 요청이 너무 빠르지 않도록 대기

            if not reply_client.send_to_chat(chat_id, chunk):
                success = False
                logger.error(f"Feishu Stream 분할 조각 {i+1}/{len(chunks)} 발송 실패")

        return success

    def generate_daily_report(
        self,
        results: List[AnalysisResult],
        report_date: Optional[str] = None
    ) -> str:
        """
        Markdown 형식의 일일 리포트 생성(상세 버전)

        Args:
            results: 분석 결과 목록
            report_date: 리포트 날짜(기본값: 오늘)

        Returns:
            Markdown 형식의 일일 리포트 내용
        """
        if report_date is None:
            report_date = datetime.now().strftime('%Y-%m-%d')
        report_language = self._get_report_language(results)
        labels = get_report_labels(report_language)

        # 제목
        report_lines = [
            f"# 📅 {report_date} {labels['report_title']}",
            "",
            f"> {labels['analyzed_prefix']} **{len(results)}** {labels['stock_unit']} | "
            f"{labels['generated_at_label']}：{datetime.now().strftime('%H:%M:%S')}",
        ]
        self._append_market_status_line(report_lines, results, report_language)
        report_lines.extend(["---", ""])

        # 점수순 정렬(높은 점수가 먼저)
        sorted_results = sorted(
            results,
            key=lambda x: x.sentiment_score,
            reverse=True
        )

        buy_count, sell_count, hold_count = self._count_display_decisions(results, report_language)
        avg_score = sum(r.sentiment_score for r in results) / len(results) if results else 0

        report_lines.extend([
            f"## 📊 {labels['summary_heading']}",
            "",
            "| 指标 | 数值 |",
            "|------|------|",
            f"| 🟢 {labels['buy_label']} | **{buy_count}** {labels['stock_unit_compact']} |",
            f"| 🟡 {labels['watch_label']} | **{hold_count}** {labels['stock_unit_compact']} |",
            f"| 🔴 {labels['sell_label']} | **{sell_count}** {labels['stock_unit_compact']} |",
            f"| 📈 {labels['avg_score_label']} | **{avg_score:.1f}** |",
            "",
            "---",
            "",
        ])

        # Issue #262: summary_only이면 요약만 출력하고 종목별 상세는 생략
        if self._report_summary_only:
            report_lines.extend([f"## 📊 {labels['summary_heading']}", ""])
            for r in sorted_results:
                signal_text, emoji, _ = self._get_signal_level(r)
                report_lines.append(
                    f"{emoji} **{self._get_display_name(r, report_language)}({r.code})**: "
                    f"{signal_text} | "
                    f"{labels['score_label']} {r.sentiment_score} | "
                    f"{localize_trend_prediction(r.trend_prediction, report_language)}"
                )
                news_disclosure = self._empty_news_disclosure(r, report_language)
                if news_disclosure:
                    report_lines.append(news_disclosure)
        else:
            report_lines.extend([f"## 📈 {labels['report_title']}", ""])
            # 종목별 상세 분석
            for result in sorted_results:
                signal_text, emoji, _ = self._get_signal_level(result)
                confidence_stars = result.get_confidence_stars() if hasattr(result, 'get_confidence_stars') else '⭐⭐'

                report_lines.extend([
                    f"### {emoji} {self._get_display_name(result, report_language)} ({result.code})",
                    "",
                    f"**{labels['action_advice_label']}：{signal_text}** | "
                    f"**{labels['score_label']}：{result.sentiment_score}** | "
                    f"**{labels['trend_label']}：{localize_trend_prediction(result.trend_prediction, report_language)}** | "
                    f"**Confidence：{confidence_stars}**",
                    "",
                ])
                self._append_market_snapshot(report_lines, result)

                # 핵심 포인트
                if hasattr(result, 'key_points') and result.key_points:
                    report_lines.extend([
                        f"**🎯 核心看点**：{result.key_points}",
                        "",
                    ])

                # 매수/매도 근거
                if hasattr(result, 'buy_reason') and result.buy_reason:
                    report_lines.extend([
                        f"**💡 操作理由**：{result.buy_reason}",
                        "",
                    ])

                # 추세 분석
                if hasattr(result, 'trend_analysis') and result.trend_analysis:
                    report_lines.extend([
                        "#### 📉 走势分析",
                        f"{result.trend_analysis}",
                        "",
                    ])

                # 단기/중기 전망
                outlook_lines = []
                if hasattr(result, 'short_term_outlook') and result.short_term_outlook:
                    outlook_lines.append(f"- **短期（1-3日）**：{result.short_term_outlook}")
                if hasattr(result, 'medium_term_outlook') and result.medium_term_outlook:
                    outlook_lines.append(f"- **中期（1-2周）**：{result.medium_term_outlook}")
                if outlook_lines:
                    report_lines.extend([
                        "#### 🔮 市场展望",
                        *outlook_lines,
                        "",
                    ])

                # 기술적 분석
                tech_lines = []
                if result.technical_analysis:
                    tech_lines.append(f"**综合**：{result.technical_analysis}")
                if hasattr(result, 'ma_analysis') and result.ma_analysis:
                    tech_lines.append(f"**均线**：{result.ma_analysis}")
                if hasattr(result, 'volume_analysis') and result.volume_analysis:
                    tech_lines.append(f"**量能**：{result.volume_analysis}")
                if hasattr(result, 'pattern_analysis') and result.pattern_analysis:
                    tech_lines.append(f"**形态**：{result.pattern_analysis}")
                if tech_lines:
                    report_lines.extend([
                        "#### 📊 技术面分析",
                        *tech_lines,
                        "",
                    ])

                # 펀더멘털 분석
                fund_lines = []
                if hasattr(result, 'fundamental_analysis') and result.fundamental_analysis:
                    fund_lines.append(result.fundamental_analysis)
                if hasattr(result, 'sector_position') and result.sector_position:
                    fund_lines.append(f"**板块地位**：{result.sector_position}")
                if hasattr(result, 'company_highlights') and result.company_highlights:
                    fund_lines.append(f"**公司亮点**：{result.company_highlights}")
                if fund_lines:
                    report_lines.extend([
                        "#### 🏢 基本面分析",
                        *fund_lines,
                        "",
                    ])

                # 뉴스/투자 심리
                news_lines = []
                if result.news_summary:
                    news_lines.append(f"**新闻摘要**：{result.news_summary}")
                if hasattr(result, 'market_sentiment') and result.market_sentiment:
                    news_lines.append(f"**市场情绪**：{result.market_sentiment}")
                if hasattr(result, 'hot_topics') and result.hot_topics:
                    news_lines.append(f"**相关热点**：{result.hot_topics}")
                news_disclosure = self._empty_news_disclosure(result, report_language)
                if news_lines or news_disclosure:
                    report_lines.append("#### 📰 消息面/情绪面")
                    if news_disclosure:
                        report_lines.append(news_disclosure)
                    report_lines.extend(news_lines)
                    report_lines.append("")

                # 종합 분석
                if result.analysis_summary:
                    report_lines.extend([
                        "#### 📝 综合分析",
                        result.analysis_summary,
                        "",
                    ])

                # 리스크 안내
                if hasattr(result, 'risk_warning') and result.risk_warning:
                    report_lines.extend([
                        f"⚠️ **风险提示**：{result.risk_warning}",
                        "",
                    ])

                # 데이터 출처 안내
                if hasattr(result, 'search_performed') and result.search_performed:
                    report_lines.append("*🔍 已执行联网搜索*")
                self._append_data_sources_line(report_lines, result, labels)

                # 오류 정보(있는 경우)
                if not result.success and result.error_message:
                    report_lines.extend([
                        "",
                        f"❌ **分析异常**：{result.error_message[:100]}",
                    ])

                report_lines.extend([
                    "",
                    "---",
                    "",
                ])

        # 하단 정보(면책 문구 제외)
        report_lines.extend([
            "",
            f"*{labels['generated_at_label']}：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])

        return "\n".join(report_lines)

    @staticmethod
    def _escape_md(name: str) -> str:
        """Escape markdown special characters in stock names (e.g. *ST → \\*ST)."""
        return name.replace('*', r'\*') if name else name

    @staticmethod
    def _clean_sniper_value(value: Any) -> str:
        """Normalize sniper point values and remove redundant label prefixes."""
        if value is None:
            return 'N/A'
        if isinstance(value, (int, float)):
            return str(value)
        if not isinstance(value, str):
            return str(value)
        if not value or value == 'N/A':
            return value
        prefixes = ['理想买入点：', '次优买入点：', '止损位：', '目标位：',
                     '理想买入点:', '次优买入点:', '止损位:', '目标位:',
                     'Ideal Entry:', 'Secondary Entry:', 'Stop Loss:', 'Target:']
        for prefix in prefixes:
            if value.startswith(prefix):
                return value[len(prefix):]
        return value

    @staticmethod
    def _phase_decision_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @classmethod
    def _phase_decision_has_content(cls, phase_decision: Dict[str, Any]) -> bool:
        text_keys = (
            "action_window",
            "immediate_action",
            "next_check_time",
            "confidence_reason",
        )
        if any(str(phase_decision.get(key) or "").strip() for key in text_keys):
            return True
        return bool(
            cls._phase_decision_list(phase_decision.get("watch_conditions"))
            or cls._phase_decision_list(phase_decision.get("data_limitations"))
        )

    def _append_phase_decision_block(
        self,
        report_lines: List[str],
        dashboard: Dict[str, Any],
        labels: Dict[str, str],
        report_language: Optional[str] = None,
    ) -> None:
        phase_decision = dashboard.get("phase_decision") if dashboard else None
        if not isinstance(phase_decision, dict):
            return
        if not self._phase_decision_has_content(phase_decision):
            return

        def _display(value: Any) -> Any:
            return localize_display_phrase(value, report_language)

        watch_conditions = [_display(item) for item in self._phase_decision_list(phase_decision.get("watch_conditions"))]
        data_limitations = [_display(item) for item in self._phase_decision_list(phase_decision.get("data_limitations"))]

        report_lines.extend([
            f"### 🛡️ {labels['phase_decision_heading']}",
            "",
            f"| {labels['action_window_label']} | {labels['immediate_action_label']} | {labels['next_check_time_label']} |",
            "|---------|---------|---------|",
            f"| {_display(phase_decision.get('action_window')) or 'N/A'} | "
            f"{_display(phase_decision.get('immediate_action')) or 'N/A'} | "
            f"{phase_decision.get('next_check_time') or 'N/A'} |",
            "",
        ])

        if watch_conditions:
            report_lines.append(f"**{labels['watch_conditions_label']}**:")
            for condition in watch_conditions:
                report_lines.append(f"- {condition}")
            report_lines.append("")

        confidence_reason = str(phase_decision.get("confidence_reason") or "").strip()
        if confidence_reason:
            report_lines.extend([
                f"**{labels['confidence_reason_label']}**: {confidence_reason}",
                "",
            ])

        if data_limitations:
            report_lines.append(f"**{labels['data_limitations_label']}**:")
            for limitation in data_limitations:
                report_lines.append(f"- {limitation}")
            report_lines.append("")

    def _get_display_operation_advice(
        self,
        result: AnalysisResult,
        report_language: Optional[str] = None,
    ) -> str:
        return display_operation_advice_for_result(
            result,
            report_language=report_language or self._get_report_language(result),
        )

    def _count_display_decisions(
        self,
        results: List[AnalysisResult],
        report_language: Optional[str] = None,
    ) -> Tuple[int, int, int]:
        language = report_language or self._get_report_language(results)
        buckets = [
            display_decision_type_for_result(result, report_language=language)
            for result in results
        ]
        buy_count = sum(1 for bucket in buckets if bucket == "buy")
        sell_count = sum(1 for bucket in buckets if bucket == "sell")
        hold_count = len(buckets) - buy_count - sell_count
        return buy_count, sell_count, hold_count

    def _get_signal_level(self, result: AnalysisResult) -> tuple:
        """Get display text and signal metadata from the resolved action."""
        report_language = self._get_report_language(result)
        display_fields = display_action_fields_for_result(
            result,
            report_language=report_language,
        )
        signal_advice = {
            "buy": "buy",
            "add": "buy",
            "hold": "hold",
            "reduce": "reduce",
            "sell": "sell",
            "watch": "watch",
            "avoid": "hold",
            "alert": "sell",
        }.get(display_fields["action"])
        _, emoji, signal_tag = get_signal_level(
            signal_advice or self._get_display_operation_advice(result, report_language),
            result.sentiment_score,
            report_language,
        )
        return (
            self._get_display_operation_advice(result, report_language),
            emoji,
            signal_tag,
        )

    def generate_dashboard_report(
        self,
        results: List[AnalysisResult],
        report_date: Optional[str] = None
    ) -> str:
        """
        의사결정 대시보드 형식의 일일 리포트 생성(상세 버전)

        구성: 시장 개요 + 주요 정보 + 핵심 결론 + 데이터 분석 + 매매 계획

        Args:
            results: 분석 결과 목록
            report_date: 리포트 날짜(기본값: 오늘)

        Returns:
            Markdown 형식의 의사결정 대시보드 일일 리포트
        """
        config = get_config()
        report_language = self._get_report_language(results)
        labels = get_report_labels(report_language)

        def _nlabel(en: str, zh: str, ko: str) -> str:
            if report_language == "en":
                return en
            if report_language == "ko":
                return ko
            return zh

        reason_label = _nlabel("Rationale", "操作理由", "판단 근거")
        risk_warning_label = _nlabel("Risk Warning", "风险提示", "리스크 경고")
        technical_heading = _nlabel("Technicals", "技术面", "기술적 분석")
        ma_label = _nlabel("Moving Averages", "均线", "이동평균")
        volume_analysis_label = _nlabel("Volume", "量能", "거래량")
        news_heading = _nlabel("News Flow", "消息面", "뉴스 흐름")

        def _display(value: Any) -> Any:
            # ko 보고서에서만 LLM이 남긴 영어 고정값("No rush", "Risk 1:")을 한국어로 바꾼다
            return localize_display_phrase(value, report_language)
        if getattr(config, 'report_renderer_enabled', False) and results:
            from src.services.report_renderer import render
            out = render(
                platform='markdown',
                results=results,
                report_date=report_date,
                summary_only=self._report_summary_only,
                extra_context={
                    **self._get_history_compare_context(results),
                    "report_language": report_language,
                },
            )
            if out:
                return out

        if report_date is None:
            report_date = datetime.now().strftime('%Y-%m-%d')

        # 점수순 정렬(높은 점수가 먼저)
        sorted_results = sorted(results, key=lambda x: x.sentiment_score, reverse=True)

        buy_count, sell_count, hold_count = self._count_display_decisions(results, report_language)

        report_lines = [
            f"# 🎯 {report_date} {labels['dashboard_title']}",
            "",
            f"> {labels['analyzed_prefix']} **{len(results)}** {labels['stock_unit']} | "
            f"🟢{labels['buy_label']}:{buy_count} 🟡{labels['watch_label']}:{hold_count} 🔴{labels['sell_label']}:{sell_count}",
        ]
        self._append_market_status_line(report_lines, results, report_language)

        # === 추가: 분석 결과 요약 (Issue #112) ===
        if results:
            report_lines.extend([
                f"## 📊 {labels['summary_heading']}",
                "",
            ])
            for r in sorted_results:
                signal_text, signal_emoji, _ = self._get_signal_level(r)
                display_name = self._get_display_name(r, report_language)
                report_lines.append(
                    f"{signal_emoji} **{display_name}({r.code})**: "
                    f"{signal_text} | "
                    f"{labels['score_label']} {r.sentiment_score} | "
                    f"{localize_trend_prediction(r.trend_prediction, report_language)}"
                )
                if self._report_summary_only:
                    news_disclosure = self._empty_news_disclosure(r, report_language)
                    if news_disclosure:
                        report_lines.append(news_disclosure)
                    self._append_data_sources_line(report_lines, r, labels)
            report_lines.extend([
                "",
                "---",
                "",
            ])

        # 종목별 의사결정 대시보드(Issue #262: summary_only이면 상세 생략)
        if not self._report_summary_only:
            for result in sorted_results:
                signal_text, signal_emoji, signal_tag = self._get_signal_level(result)
                dashboard = result.dashboard if hasattr(result, 'dashboard') and result.dashboard else {}

                # 종목명(dashboard 또는 result의 이름을 우선 사용하고, *ST 같은 특수문자는 이스케이프)
                stock_name = self._get_display_name(result, report_language)

                report_lines.extend([
                    f"## {signal_emoji} {stock_name} ({result.code})",
                    "",
                ])
                # ========== 여론 및 펀더멘털 개요(맨 앞에 배치) ==========
                intel = dashboard.get('intelligence', {}) if dashboard else {}
                if intel:
                    report_lines.extend([
                        f"### 📰 {labels['info_heading']}",
                        "",
                    ])
                    # 여론·투자 심리 요약
                    if intel.get('sentiment_summary'):
                        report_lines.append(f"**💭 {labels['sentiment_summary_label']}**: {intel['sentiment_summary']}")
                    # 실적 전망
                    if intel.get('earnings_outlook'):
                        report_lines.append(f"**📊 {labels['earnings_outlook_label']}**: {intel['earnings_outlook']}")
                    # 리스크 경고(눈에 띄게 표시)
                    risk_alerts = intel.get('risk_alerts', [])
                    if risk_alerts:
                        report_lines.append("")
                        report_lines.append(f"**🚨 {labels['risk_alerts_label']}**:")
                        for alert in risk_alerts:
                            report_lines.append(f"- {_display(alert)}")
                    # 호재 요인
                    catalysts = intel.get('positive_catalysts', [])
                    if catalysts:
                        report_lines.append("")
                        report_lines.append(f"**✨ {labels['positive_catalysts_label']}**:")
                        for cat in catalysts:
                            report_lines.append(f"- {_display(cat)}")
                    # 최신 뉴스
                    if intel.get('latest_news'):
                        report_lines.append("")
                        report_lines.append(f"**📢 {labels['latest_news_label']}**: {_display(intel['latest_news'])}")
                    report_lines.append("")

                # ========== 핵심 결론 ==========
                core = dashboard.get('core_conclusion', {}) if dashboard else {}
                one_sentence = core.get('one_sentence', result.analysis_summary)
                time_sense = _display(core.get('time_sensitivity', labels['default_time_sensitivity']))
                pos_advice = core.get('position_advice', {})

                report_lines.extend([
                    f"### 📌 {labels['core_conclusion_heading']}",
                    "",
                    f"**{signal_emoji} {signal_text}** | {localize_trend_prediction(result.trend_prediction, report_language)}",
                    "",
                    f"> **{labels['one_sentence_label']}**: {one_sentence}",
                    "",
                    f"⏰ **{labels['time_sensitivity_label']}**: {time_sense}",
                    "",
                ])
                # 보유 여부별 제안
                if pos_advice:
                    report_lines.extend([
                        f"| {labels['position_status_label']} | {labels['action_advice_label']} |",
                        "|---------|---------|",
                        f"| 🆕 **{labels['no_position_label']}** | {pos_advice.get('no_position', self._get_display_operation_advice(result, report_language))} |",
                        f"| 💼 **{labels['has_position_label']}** | {pos_advice.get('has_position', labels['continue_holding'])} |",
                        "",
                    ])

                self._append_market_snapshot(report_lines, result)

                # ========== 데이터 분석 ==========
                data_persp = dashboard.get('data_perspective', {}) if dashboard else {}
                if data_persp:
                    trend_data = data_persp.get('trend_status', {})
                    price_data = data_persp.get('price_position', {})
                    vol_data = data_persp.get('volume_analysis', {})
                    chip_data = data_persp.get('chip_structure', {})

                    report_lines.extend([
                        f"### 📊 {labels['data_perspective_heading']}",
                        "",
                    ])
                    # 추세 상태
                    if trend_data:
                        is_bullish = (
                            f"✅ {labels['yes_label']}"
                            if trend_data.get('is_bullish', False)
                            else f"❌ {labels['no_label']}"
                        )
                        report_lines.extend([
                            f"**{labels['ma_alignment_label']}**: {trend_data.get('ma_alignment', 'N/A')} | "
                            f"{labels['bullish_alignment_label']}: {is_bullish} | "
                            f"{labels['trend_strength_label']}: {trend_data.get('trend_score', 'N/A')}/100",
                            "",
                        ])
                    # 가격 위치
                    if price_data:
                        bias_status = price_data.get('bias_status', 'N/A')
                        if report_language == "ko":
                            bias_status = localize_bias_status(bias_status, report_language)
                        report_lines.extend([
                            f"| {labels['price_metrics_label']} | {labels['current_price_label']} |",
                            "|---------|------|",
                            f"| {labels['current_price_label']} | {price_data.get('current_price', 'N/A')} |",
                            f"| {labels['ma5_label']} | {price_data.get('ma5', 'N/A')} |",
                            f"| {labels['ma10_label']} | {price_data.get('ma10', 'N/A')} |",
                            f"| {labels['ma20_label']} | {price_data.get('ma20', 'N/A')} |",
                            f"| {labels['bias_ma5_label']} | {price_data.get('bias_ma5', 'N/A')}% {bias_status} |",
                            f"| {labels['support_level_label']} | {price_data.get('support_level', 'N/A')} |",
                            f"| {labels['resistance_level_label']} | {price_data.get('resistance_level', 'N/A')} |",
                            "",
                        ])
                    # 거래량 분석
                    if vol_data:
                        report_lines.extend([
                            f"**{labels['volume_label']}**: {labels['volume_ratio_label']} {vol_data.get('volume_ratio', 'N/A')} ({_display(vol_data.get('volume_status', ''))}) | "
                            f"{labels['turnover_rate_label']} {vol_data.get('turnover_rate', 'N/A')}%",
                            f"💡 *{vol_data.get('volume_meaning', '')}*",
                            "",
                        ])
                    # 매물대 구조
                    if chip_data:
                        if is_chip_structure_unavailable(chip_data):
                            report_lines.extend([
                                f"**{labels['chip_label']}**: {get_chip_unavailable_reason(chip_data, report_language)}",
                                "",
                            ])
                        else:
                            chip_health = localize_chip_health(chip_data.get('chip_health', 'N/A'), report_language)
                            report_lines.extend([
                                f"**{labels['chip_label']}**: {chip_data.get('profit_ratio', 'N/A')} | {chip_data.get('avg_cost', 'N/A')} | "
                                f"{chip_data.get('concentration', 'N/A')} {chip_health}",
                                "",
                            ])
                    else:
                        chip_unavailable_reason = get_chip_unavailable_reason(data_persp, report_language)
                        if chip_unavailable_reason:
                            report_lines.extend([
                                f"**{labels['chip_label']}**: {chip_unavailable_reason}",
                                "",
                            ])

                self._append_phase_decision_block(report_lines, dashboard, labels, report_language)

                # ========== 매매 계획 ==========
                battle = dashboard.get('battle_plan', {}) if dashboard else {}
                if battle:
                    report_lines.extend([
                        f"### 🎯 {labels['battle_plan_heading']}",
                        "",
                    ])
                    # 진입·청산 가격대
                    sniper = battle.get('sniper_points', {})
                    if sniper:
                        report_lines.extend([
                            f"**📍 {labels['action_points_heading']}**",
                            "",
                            f"| {labels['action_points_heading']} | {labels['current_price_label']} |",
                            "|---------|------|",
                            f"| 🎯 {labels['ideal_buy_label']} | {self._clean_sniper_value(sniper.get('ideal_buy', 'N/A'))} |",
                            f"| 🔵 {labels['secondary_buy_label']} | {self._clean_sniper_value(sniper.get('secondary_buy', 'N/A'))} |",
                            f"| 🛑 {labels['stop_loss_label']} | {self._clean_sniper_value(sniper.get('stop_loss', 'N/A'))} |",
                            f"| 🎊 {labels['take_profit_label']} | {self._clean_sniper_value(sniper.get('take_profit', 'N/A'))} |",
                            "",
                        ])
                    # 비중 전략
                    position = battle.get('position_strategy', {})
                    if position:
                        report_lines.extend([
                            f"**💰 {labels['suggested_position_label']}**: {position.get('suggested_position', 'N/A')}",
                            f"- {labels['entry_plan_label']}: {position.get('entry_plan', 'N/A')}",
                            f"- {labels['risk_control_label']}: {position.get('risk_control', 'N/A')}",
                            "",
                        ])
                    # 체크리스트
                    checklist = battle.get('action_checklist', []) if battle else []
                    if checklist:
                        report_lines.extend([
                            f"**✅ {labels['checklist_heading']}**",
                            "",
                        ])
                        for item in checklist:
                            report_lines.append(f"- {_display(item)}")
                        report_lines.append("")

                # ========== 신호 근거 분석 ==========
                signal_attr = dashboard.get('signal_attribution', {}) if dashboard else {}
                if signal_attribution_has_content(signal_attr):
                    report_lines.extend([
                        f"### 🎯 {labels['signal_attribution_heading']}",
                        "",
                    ])
                    weight_items = signal_attribution_weight_items(signal_attr)
                    if weight_items:
                        report_lines.append(f"**{labels['attribution_weights_label']}**:")
                        weight_labels = {
                            "technical_indicators": ("📈", labels['technical_indicators_label']),
                            "news_sentiment": ("📰", labels['news_sentiment_label']),
                            "fundamentals": ("📊", labels['fundamentals_label']),
                            "market_conditions": ("🌐", labels['market_conditions_label']),
                        }
                        for key, value in weight_items:
                            icon, label = weight_labels[key]
                            report_lines.append(f"- {icon} {label}: {value}%")
                        report_lines.append("")

                    # 가장 강한 신호
                    if signal_attr.get('strongest_bullish_signal'):
                        report_lines.append(f"**🐂 {labels['strongest_bullish_signal_label']}**: {signal_attr['strongest_bullish_signal']}")
                    if signal_attr.get('strongest_bearish_signal'):
                        report_lines.append(f"**🐻 {labels['strongest_bearish_signal_label']}**: {signal_attr['strongest_bearish_signal']}")
                    report_lines.append("")

                # ========== 다중 전략 종합 ==========
                strategy_synthesis = normalize_strategy_synthesis_payload(
                    dashboard.get('strategy_synthesis') if dashboard else None
                )
                _append_strategy_synthesis_block(report_lines, strategy_synthesis, labels, report_language)

                # 재무 요약 / 주주 환원 / 관련 섹터(데이터가 없으면 해당 소절을 자동으로 숨김)
                self._append_fundamental_blocks(report_lines, result)

                # dashboard가 없으면 기존 형식으로 표시
                if not dashboard:
                    # 판단 근거
                    if result.buy_reason:
                        report_lines.extend([
                            f"**💡 {reason_label}**: {result.buy_reason}",
                            "",
                        ])
                    # 리스크 안내
                    if result.risk_warning:
                        report_lines.extend([
                            f"**⚠️ {risk_warning_label}**: {result.risk_warning}",
                            "",
                        ])
                    # 기술적 분석
                    if result.ma_analysis or result.volume_analysis:
                        report_lines.extend([
                            f"### 📊 {technical_heading}",
                            "",
                        ])
                        if result.ma_analysis:
                            report_lines.append(f"**{ma_label}**: {result.ma_analysis}")
                        if result.volume_analysis:
                            report_lines.append(f"**{volume_analysis_label}**: {result.volume_analysis}")
                        report_lines.append("")
                    # 뉴스 흐름
                    news_disclosure = self._empty_news_disclosure(result, report_language)
                    if result.news_summary or news_disclosure:
                        report_lines.append(f"### 📰 {news_heading}")
                        if news_disclosure:
                            report_lines.append(news_disclosure)
                        if result.news_summary:
                            report_lines.append(f"{result.news_summary}")
                        report_lines.append("")

                if self._append_data_sources_line(report_lines, result, labels):
                    report_lines.append("")

                report_lines.extend([
                    "---",
                    "",
                ])

        # 하단(면책 문구 제외)
        report_lines.extend([
            "",
            f"*{labels['generated_at_label']}：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
        ])
        models = self._collect_models_used(results)
        if models:
            report_lines.append(f"*{labels['analysis_model_label']}：{', '.join(models)}*")

        return "\n".join(report_lines)

    def generate_wechat_dashboard(self, results: List[AnalysisResult]) -> str:
        """
        WeCom용 의사결정 대시보드 간략판 생성(4000자 이내로 제한)

        핵심 결론과 진입·청산 가격대만 남긴다

        Args:
            results: 분석 결과 목록

        Returns:
            간략판 의사결정 대시보드
        """
        config = get_config()
        report_language = self._get_report_language(results)
        labels = get_report_labels(report_language)
        if getattr(config, 'report_renderer_enabled', False) and results:
            from src.services.report_renderer import render
            out = render(
                platform='wechat',
                results=results,
                report_date=datetime.now().strftime('%Y-%m-%d'),
                summary_only=self._report_summary_only,
                extra_context={"report_language": report_language},
            )
            if out:
                return out

        report_date = datetime.now().strftime('%Y-%m-%d')

        # 점수순 정렬
        sorted_results = sorted(results, key=lambda x: x.sentiment_score, reverse=True)

        buy_count, sell_count, hold_count = self._count_display_decisions(results, report_language)

        lines = [
            f"## 🎯 {report_date} {labels['dashboard_title']}",
            "",
            f"> {len(results)} {labels['stock_unit']} | "
            f"🟢{labels['buy_label']}:{buy_count} 🟡{labels['watch_label']}:{hold_count} 🔴{labels['sell_label']}:{sell_count}",
        ]
        self._append_market_status_line(lines, results, report_language)

        # Issue #262: summary_only이면 요약 목록만 출력
        if self._report_summary_only:
            lines.append(f"**📊 {labels['summary_heading']}**")
            lines.append("")
            for r in sorted_results:
                signal_text, signal_emoji, _ = self._get_signal_level(r)
                stock_name = self._get_display_name(r, report_language)
                lines.append(
                    f"{signal_emoji} **{stock_name}({r.code})**: "
                    f"{signal_text} | "
                    f"{labels['score_label']} {r.sentiment_score} | "
                    f"{localize_trend_prediction(r.trend_prediction, report_language)}"
                )
                news_disclosure = self._empty_news_disclosure(r, report_language)
                if news_disclosure:
                    lines.append(news_disclosure)
        else:
            for result in sorted_results:
                signal_text, signal_emoji, _ = self._get_signal_level(result)
                dashboard = result.dashboard if hasattr(result, 'dashboard') and result.dashboard else {}
                core = dashboard.get('core_conclusion', {}) if dashboard else {}
                battle = dashboard.get('battle_plan', {}) if dashboard else {}
                intel = dashboard.get('intelligence', {}) if dashboard else {}

                # 종목명
                stock_name = self._get_display_name(result, report_language)

                # 제목 줄: 신호 등급 + 종목명
                lines.append(f"### {signal_emoji} **{signal_text}** | {stock_name}({result.code})")
                lines.append("")

                # 핵심 판단(한 문장)
                one_sentence = core.get('one_sentence', result.analysis_summary) if core else result.analysis_summary
                if one_sentence:
                    lines.append(f"📌 **{one_sentence[:80]}**")
                    lines.append("")
                # 주요 정보 영역(여론 + 펀더멘털)
                info_lines = []

                # 뉴스 검색 결과가 0건이면 반드시 알려야 한다. 그러지 않으면 WeCom 경로에서는 조용히 빠진다
                news_disclosure = self._empty_news_disclosure(result, report_language)
                if news_disclosure:
                    info_lines.append(news_disclosure)

                # 실적 전망
                if intel.get('earnings_outlook'):
                    outlook = str(intel['earnings_outlook'])[:60]
                    info_lines.append(f"📊 {labels['earnings_outlook_label']}: {outlook}")
                if intel.get('sentiment_summary'):
                    sentiment = str(intel['sentiment_summary'])[:50]
                    info_lines.append(f"💭 {labels['sentiment_summary_label']}: {sentiment}")
                if info_lines:
                    lines.extend(info_lines)
                    lines.append("")

                # 리스크 경고(가장 중요, 눈에 띄게 표시)
                risks = intel.get('risk_alerts', []) if intel else []
                if risks:
                    lines.append(f"🚨 **{labels['risk_alerts_label']}**:")
                    for risk in risks[:2]:  # 최대 2개만 표시
                        risk_str = str(localize_display_phrase(risk, report_language))
                        risk_text = risk_str[:50] + "..." if len(risk_str) > 50 else risk_str
                        lines.append(f"   • {risk_text}")
                    lines.append("")

                # 호재 요인
                catalysts = intel.get('positive_catalysts', []) if intel else []
                if catalysts:
                    lines.append(f"✨ **{labels['positive_catalysts_label']}**:")
                    for cat in catalysts[:2]:  # 최대 2개만 표시
                        cat_str = str(localize_display_phrase(cat, report_language))
                        cat_text = cat_str[:50] + "..." if len(cat_str) > 50 else cat_str
                        lines.append(f"   • {cat_text}")
                    lines.append("")

                # 진입·청산 가격대
                sniper = battle.get('sniper_points', {}) if battle else {}
                if sniper:
                    ideal_buy = str(sniper.get('ideal_buy', ''))
                    stop_loss = str(sniper.get('stop_loss', ''))
                    take_profit = str(sniper.get('take_profit', ''))
                    points = []
                    if ideal_buy:
                        points.append(f"🎯{labels['ideal_buy_label']}:{ideal_buy[:15]}")
                    if stop_loss:
                        points.append(f"🛑{labels['stop_loss_label']}:{stop_loss[:15]}")
                    if take_profit:
                        points.append(f"🎊{labels['take_profit_label']}:{take_profit[:15]}")
                    if points:
                        lines.append(" | ".join(points))
                        lines.append("")

                # 보유 여부별 제안
                pos_advice = core.get('position_advice', {}) if core else {}
                if pos_advice:
                    no_pos = str(pos_advice.get('no_position', ''))
                    has_pos = str(pos_advice.get('has_position', ''))
                    if no_pos:
                        lines.append(f"🆕 {labels['no_position_label']}: {no_pos[:50]}")
                    if has_pos:
                        lines.append(f"💼 {labels['has_position_label']}: {has_pos[:50]}")
                    lines.append("")

                # 다중 전략 종합
                strategy_synthesis = normalize_strategy_synthesis_payload(
                    dashboard.get('strategy_synthesis') if dashboard else None
                )
                if strategy_synthesis:
                    lines.append(
                        f"🧩 **{labels['strategy_synthesis_heading']}**: "
                        f"{localize_strategy_signal(strategy_synthesis.get('final_signal', 'N/A'), report_language)} | "
                        f"{labels['strategy_consensus_level_label']} "
                        f"{localize_consensus_level(strategy_synthesis.get('consensus_level', 'N/A'), report_language)} | "
                        f"{labels['strategy_conflict_label']} "
                        f"{localize_conflict_severity(strategy_synthesis.get('conflict_severity', 'none'), report_language)}"
                        f"({strategy_synthesis.get('conflict_count', 0)})"
                    )
                    invalid_count = strategy_invalid_opinion_count(strategy_synthesis)
                    if invalid_count:
                        lines.append(
                            labels.get(
                                'strategy_invalid_opinions_label', ''
                            ).format(count=invalid_count)
                        )
                    summary = localize_strategy_synthesis_summary(strategy_synthesis, report_language)
                    if summary:
                        lines.append(summary[:80])
                    lines.append("")

                # 체크리스트 간략판
                checklist = battle.get('action_checklist', []) if battle else []
                if checklist:
                    # 통과하지 못한 항목만 표시
                    failed_checks = [str(c) for c in checklist if str(c).startswith('❌') or str(c).startswith('⚠️')]
                    if failed_checks:
                        lines.append(f"**{labels['failed_checks_heading']}**:")
                        for check in failed_checks[:3]:
                            lines.append(f"   {check[:40]}")
                        lines.append("")

                lines.append("---")
                lines.append("")

        # 하단
        lines.append(f"*{labels['report_time_label']}: {datetime.now().strftime('%H:%M')}*")
        models = self._collect_models_used(results)
        if models:
            lines.append(f"*{labels['analysis_model_label']}: {', '.join(models)}*")

        content = "\n".join(lines)

        return content

    def generate_wechat_summary(self, results: List[AnalysisResult]) -> str:
        """
        WeCom용 간략판 일일 리포트 생성(4000자 이내로 제한)

        Args:
            results: 분석 결과 목록

        Returns:
            간략판 Markdown 내용
        """
        report_date = datetime.now().strftime('%Y-%m-%d')
        report_language = self._get_report_language(results)
        labels = get_report_labels(report_language)

        # 점수순 정렬
        sorted_results = sorted(results, key=lambda x: x.sentiment_score, reverse=True)

        buy_count, sell_count, hold_count = self._count_display_decisions(results, report_language)
        avg_score = sum(r.sentiment_score for r in results) / len(results) if results else 0

        lines = [
            f"## 📅 {report_date} {labels['report_title']}",
            "",
            f"> {labels['analyzed_prefix']} **{len(results)}** {labels['stock_unit_compact']} | "
            f"🟢{labels['buy_label']}:{buy_count} 🟡{labels['watch_label']}:{hold_count} 🔴{labels['sell_label']}:{sell_count} | "
            f"{labels['avg_score_label']}:{avg_score:.0f}",
        ]
        self._append_market_status_line(lines, results, report_language)

        # 종목별 간략 정보(길이 제한)
        for result in sorted_results:
            signal_text, emoji, _ = self._get_signal_level(result)

            # 핵심 정보 줄
            lines.append(f"### {emoji} {self._get_display_name(result, report_language)}({result.code})")
            lines.append(
                f"**{signal_text}** | "
                f"{labels['score_label']}:{result.sentiment_score} | "
                f"{localize_trend_prediction(result.trend_prediction, report_language)}"
            )
            news_disclosure = self._empty_news_disclosure(result, report_language)
            if news_disclosure:
                lines.append(news_disclosure)

            # 판단 근거(잘라서 표시)
            if hasattr(result, 'buy_reason') and result.buy_reason:
                reason = result.buy_reason[:80] + "..." if len(result.buy_reason) > 80 else result.buy_reason
                lines.append(f"💡 {reason}")

            # 핵심 포인트
            if hasattr(result, 'key_points') and result.key_points:
                points = result.key_points[:60] + "..." if len(result.key_points) > 60 else result.key_points
                lines.append(f"🎯 {points}")

            # 리스크 안내(잘라서 표시)
            if hasattr(result, 'risk_warning') and result.risk_warning:
                risk = result.risk_warning[:50] + "..." if len(result.risk_warning) > 50 else result.risk_warning
                lines.append(f"⚠️ {risk}")

            lines.append("")

        # 하단(모델 표시 줄은 --- 앞에 둔다, Issue #528)
        models = self._collect_models_used(results)
        if models:
            lines.append(f"*{labels['analysis_model_label']}: {', '.join(models)}*")
        lines.extend([
            "---",
            f"*{labels['not_investment_advice']}*",
            f"*{labels['details_report_hint']} reports/report_{report_date.replace('-', '')}.md*"
        ])

        content = "\n".join(lines)

        return content

    def generate_brief_report(
        self,
        results: List[AnalysisResult],
        report_date: Optional[str] = None,
    ) -> str:
        """
        Generate brief report (3-5 sentences per stock) for mobile/push.

        Args:
            results: Analysis results list (use [result] for single stock).
            report_date: Report date (default: today).

        Returns:
            Brief markdown content.
        """
        if report_date is None:
            report_date = datetime.now().strftime('%Y-%m-%d')
        report_language = self._get_report_language(results)
        labels = get_report_labels(report_language)
        config = get_config()
        if getattr(config, 'report_renderer_enabled', False) and results:
            from src.services.report_renderer import render
            out = render(
                platform='brief',
                results=results,
                report_date=report_date,
                summary_only=False,
                extra_context={"report_language": report_language},
            )
            if out:
                return out
        # Fallback: brief summary from dashboard report
        if not results:
            return f"# {report_date} {labels['brief_title']}\n\n{labels['no_results']}"
        sorted_results = sorted(results, key=lambda x: x.sentiment_score, reverse=True)
        buy_count, sell_count, hold_count = self._count_display_decisions(results, report_language)
        lines = [
            f"# {report_date} {labels['brief_title']}",
            "",
            f"> {len(results)} {labels['stock_unit_compact']} | 🟢{buy_count} 🟡{hold_count} 🔴{sell_count}",
        ]
        self._append_market_status_line(lines, results, report_language)
        for r in sorted_results:
            signal_text, emoji, _ = self._get_signal_level(r)
            name = self._get_display_name(r, report_language)
            dash = r.dashboard or {}
            core = dash.get('core_conclusion', {}) or {}
            one = (core.get('one_sentence') or r.analysis_summary or '')[:60]
            lines.append(
                f"**{name}({r.code})** {emoji} "
                f"{signal_text} | "
                f"{labels['score_label']} {r.sentiment_score} | {one}"
            )
            news_disclosure = self._empty_news_disclosure(r, report_language)
            if news_disclosure:
                lines.append(news_disclosure)
            if self._append_data_sources_line(lines, r, labels):
                lines.append("")
        lines.append("")
        lines.append(f"*{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
        models = self._collect_models_used(results)
        if models:
            lines.append(f"*{labels['analysis_model_label']}: {', '.join(models)}*")
        return "\n".join(lines)

    def generate_single_stock_report(self, result: AnalysisResult) -> str:
        """
        단일 종목 분석 리포트 생성(종목별 발송 모드용 #55)

        형식은 간결하지만 정보는 빠짐없이 담아, 종목 하나를 분석할 때마다 바로 발송하기에 적합하다

        Args:
            result: 단일 종목의 분석 결과

        Returns:
            Markdown 형식의 단일 종목 리포트
        """
        report_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        report_language = self._get_report_language(result)
        labels = get_report_labels(report_language)
        signal_text, signal_emoji, _ = self._get_signal_level(result)
        dashboard = result.dashboard if hasattr(result, 'dashboard') and result.dashboard else {}
        core = dashboard.get('core_conclusion', {}) if dashboard else {}
        battle = dashboard.get('battle_plan', {}) if dashboard else {}
        intel = dashboard.get('intelligence', {}) if dashboard else {}

        # 종목명(*ST 같은 특수문자는 이스케이프)
        stock_name = self._get_display_name(result, report_language)

        lines = [
            f"## {signal_emoji} {stock_name} ({result.code})",
            "",
            f"> {report_date} | {labels['score_label']}: **{result.sentiment_score}** | {localize_trend_prediction(result.trend_prediction, report_language)}",
            "",
        ]

        excerpt = self._public_phase_pack_excerpt(result, report_language)
        if excerpt:
            lines.extend([excerpt, ""])

        self._append_market_snapshot(lines, result)

        # 핵심 판단(한 문장)
        one_sentence = core.get('one_sentence', result.analysis_summary) if core else result.analysis_summary
        if one_sentence:
            lines.extend([
                f"### 📌 {labels['core_conclusion_heading']}",
                "",
                f"**{signal_text}**: {one_sentence}",
                "",
            ])

        # 주요 정보(여론 + 펀더멘털)
        info_added = False
        news_disclosure = self._empty_news_disclosure(result, report_language)
        if news_disclosure:
            lines.append(f"### 📰 {labels['info_heading']}")
            lines.append("")
            lines.append(news_disclosure)
            info_added = True
        if intel:
            if intel.get('earnings_outlook'):
                if not info_added:
                    lines.append(f"### 📰 {labels['info_heading']}")
                    lines.append("")
                    info_added = True
                lines.append(f"📊 **{labels['earnings_outlook_label']}**: {str(intel['earnings_outlook'])[:100]}")

            if intel.get('sentiment_summary'):
                if not info_added:
                    lines.append(f"### 📰 {labels['info_heading']}")
                    lines.append("")
                    info_added = True
                lines.append(f"💭 **{labels['sentiment_summary_label']}**: {str(intel['sentiment_summary'])[:80]}")

            # 리스크 경고
            risks = intel.get('risk_alerts', [])
            if risks:
                if not info_added:
                    lines.append(f"### 📰 {labels['info_heading']}")
                    lines.append("")
                    info_added = True
                lines.append("")
                lines.append(f"🚨 **{labels['risk_alerts_label']}**:")
                for risk in risks[:3]:
                    lines.append(f"- {str(localize_display_phrase(risk, report_language))[:60]}")

            # 호재 요인
            catalysts = intel.get('positive_catalysts', [])
            if catalysts:
                lines.append("")
                lines.append(f"✨ **{labels['positive_catalysts_label']}**:")
                for cat in catalysts[:3]:
                    lines.append(f"- {str(localize_display_phrase(cat, report_language))[:60]}")

        if info_added:
            lines.append("")

        # 진입·청산 가격대
        sniper = battle.get('sniper_points', {}) if battle else {}
        if sniper:
            lines.extend([
                f"### 🎯 {labels['action_points_heading']}",
                "",
                f"| {labels['ideal_buy_label']} | {labels['stop_loss_label']} | {labels['take_profit_label']} |",
                "|------|------|------|",
            ])
            ideal_buy = sniper.get('ideal_buy', '-')
            stop_loss = sniper.get('stop_loss', '-')
            take_profit = sniper.get('take_profit', '-')
            lines.append(f"| {ideal_buy} | {stop_loss} | {take_profit} |")
            lines.append("")

        # ========== 신호 근거 분석 ==========
        signal_attr = dashboard.get('signal_attribution', {}) if dashboard else {}
        if signal_attribution_has_content(signal_attr):
            lines.extend([
                f"### 🎯 {labels.get('signal_attribution_heading', '信号归因分析')}",
                "",
            ])
            # 근거별 가중치
            weight_items = signal_attribution_weight_items(signal_attr)
            if weight_items:
                lines.append(f"**{labels.get('attribution_weights_label', '归因权重')}**:")
                weight_labels = {
                    "technical_indicators": ("📈", labels.get('technical_indicators_label', '技术指标')),
                    "news_sentiment": ("📰", labels.get('news_sentiment_label', '新闻舆情')),
                    "fundamentals": ("📊", labels.get('fundamentals_label', '基本面')),
                    "market_conditions": ("🌐", labels.get('market_conditions_label', '市场环境')),
                }
                for key, value in weight_items:
                    icon, label = weight_labels[key]
                    lines.append(f"- {icon} {label}: {value}%")
                lines.append("")

            # 가장 강한 신호
            bullish = signal_attr.get('strongest_bullish_signal')
            bearish = signal_attr.get('strongest_bearish_signal')
            if bullish:
                lines.append(f"**🐂 {labels.get('strongest_bullish_signal_label', '最强看多信号')}**: {bullish}")
            if bearish:
                lines.append(f"**🐻 {labels.get('strongest_bearish_signal_label', '最强看空信号')}**: {bearish}")
            lines.append("")

        # 보유 여부별 제안
        pos_advice = core.get('position_advice', {}) if core else {}
        if pos_advice:
            lines.extend([
                f"### 💼 {labels['position_advice_heading']}",
                "",
                f"- 🆕 **{labels['no_position_label']}**: {pos_advice.get('no_position', self._get_display_operation_advice(result, report_language))}",
                f"- 💼 **{labels['has_position_label']}**: {pos_advice.get('has_position', labels['continue_holding'])}",
                "",
            ])

        # 재무 요약 / 주주 환원 / 관련 섹터(데이터가 없으면 해당 소절을 자동으로 숨김)
        self._append_fundamental_blocks(lines, result)

        lines.append("---")
        if self._should_show_llm_model():
            model_used = normalize_model_used(getattr(result, "model_used", None))
            if model_used:
                lines.append(f"*{labels['analysis_model_label']}: {model_used}*")
        lines.append(f"*{labels['not_investment_advice']}*")

        return "\n".join(lines)

    # Display name mapping for realtime data sources
    _SOURCE_DISPLAY_NAMES = {
        "tencent": {"zh": "腾讯财经", "en": "Tencent Finance", "ko": "텐센트 증권"},
        "akshare_em": {"zh": "东方财富", "en": "Eastmoney", "ko": "이스트머니"},
        "akshare_sina": {"zh": "新浪财经", "en": "Sina Finance", "ko": "시나 증권"},
        "akshare_qq": {"zh": "腾讯财经", "en": "Tencent Finance", "ko": "텐센트 증권"},
        "efinance": {"zh": "东方财富(efinance)", "en": "Eastmoney (efinance)", "ko": "이스트머니(efinance)"},
        "tushare": {"zh": "Tushare Pro", "en": "Tushare Pro", "ko": "Tushare Pro"},
        "sina": {"zh": "新浪财经", "en": "Sina Finance", "ko": "시나 증권"},
        "stooq": {"zh": "Stooq", "en": "Stooq", "ko": "Stooq"},
        "longbridge": {"zh": "长桥", "en": "Longbridge", "ko": "롱브리지"},
        "fallback": {"zh": "降级兜底", "en": "Fallback", "ko": "대체 데이터(최근 종가 기준)"},
    }

    def _get_source_display_name(self, source: Any, language: Optional[str]) -> str:
        raw_source = str(source or "N/A")
        mapping = self._SOURCE_DISPLAY_NAMES.get(raw_source)
        if not mapping:
            return raw_source
        lang = normalize_report_language(language)
        return mapping.get(lang) or mapping.get("en") or raw_source

    def _append_market_snapshot(self, lines: List[str], result: AnalysisResult) -> None:
        snapshot = getattr(result, 'market_snapshot', None)
        if not snapshot:
            return

        report_language = self._get_report_language(result)
        labels = get_report_labels(report_language)
        if report_language == "ko":
            snapshot = self._koreanize_snapshot_units(snapshot, getattr(result, "code", ""))

        lines.extend([
            f"### 📈 {labels['market_snapshot_heading']}",
            "",
            f"| {labels['close_label']} | {labels['prev_close_label']} | {labels['open_label']} | {labels['high_label']} | {labels['low_label']} | {labels['change_pct_label']} | {labels['change_amount_label']} | {labels['amplitude_label']} | {labels['volume_label']} | {labels['amount_label']} |",
            "|------|------|------|------|------|-------|-------|------|--------|--------|",
            f"| {snapshot.get('close', 'N/A')} | {snapshot.get('prev_close', 'N/A')} | "
            f"{snapshot.get('open', 'N/A')} | {snapshot.get('high', 'N/A')} | "
            f"{snapshot.get('low', 'N/A')} | {snapshot.get('pct_chg', 'N/A')} | "
            f"{snapshot.get('change_amount', 'N/A')} | {snapshot.get('amplitude', 'N/A')} | "
            f"{snapshot.get('volume', 'N/A')} | {snapshot.get('amount', 'N/A')} |",
        ])

        if "price" in snapshot:
            display_source = self._get_source_display_name(snapshot.get('source', 'N/A'), report_language)
            lines.extend([
                "",
                f"| {labels['current_price_label']} | {labels['volume_ratio_label']} | {labels['turnover_rate_label']} | {labels['source_label']} |",
                "|-------|------|--------|----------|",
                f"| {snapshot.get('price', 'N/A')} | {snapshot.get('volume_ratio', 'N/A')} | "
                f"{snapshot.get('turnover_rate', 'N/A')} | {display_source} |",
            ])

        lines.append("")

    _CN_UNIT_TEXT_RE = re.compile(r"^\s*(?P<num>[-+]?[\d,]+(?:\.\d+)?)\s*(?P<scale>亿|万)?\s*(?P<unit>股|元)\s*$")

    @classmethod
    def _koreanize_snapshot_units(cls, snapshot: Dict[str, Any], stock_code: Any) -> Dict[str, Any]:
        """이미 '2208.55 万股'/'12.30 亿元'처럼 중국어 단위로 저장된 시세 값을 한국어 단위로 바꾼다."""
        converted = dict(snapshot)
        currency_word = get_korean_currency_word(None, stock_code)
        for key in ("volume", "amount"):
            value = converted.get(key)
            if not isinstance(value, str):
                continue
            match = cls._CN_UNIT_TEXT_RE.match(value)
            if not match:
                continue
            number = float(match.group("num").replace(",", ""))
            number *= {"亿": 1e8, "万": 1e4}.get(match.group("scale") or "", 1)
            if match.group("unit") == "股":
                converted[key] = format_korean_volume(number)
            else:
                converted[key] = format_korean_amount(number, currency_word)
        return converted

    _CURRENCY_SUFFIX = {
        "USD": "美元",
        "HKD": "港元",
        "CNY": "元",
        "RMB": "元",
        "CNH": "元",
        "TWD": "新台币",  # 대만 주식(TWSE/TPEx)은 대만달러로 표시해 A주의 '元'(위안화)과 헷갈리지 않게 한다
    }

    @classmethod
    def _format_amount_cn(cls, value: Any, currency: Optional[str] = None) -> str:
        """Format absolute amounts in 亿/万 + currency suffix; returns N/A on non-numeric.

        ``currency`` accepts ``USD``/``HKD``/``CNY``; unknown values fall back to 元.
        """
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return "N/A"
        if amount != amount:  # NaN
            return "N/A"
        sign = "-" if amount < 0 else ""
        abs_amount = abs(amount)
        suffix = cls._CURRENCY_SUFFIX.get((currency or "").upper(), "元")
        if abs_amount >= 1e8:
            return f"{sign}{abs_amount / 1e8:.2f} 亿{suffix}"
        if abs_amount >= 1e4:
            return f"{sign}{abs_amount / 1e4:.2f} 万{suffix}"
        return f"{sign}{abs_amount:.0f} {suffix}"

    @staticmethod
    def _format_percent(value: Any) -> str:
        try:
            return f"{float(value):.2f}%"
        except (TypeError, ValueError):
            return "N/A"

    @classmethod
    def _format_per_share(cls, value: Any, currency: Optional[str] = None) -> str:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return "N/A"
        if amount != amount:  # NaN
            return "N/A"
        suffix = cls._CURRENCY_SUFFIX.get((currency or "").upper(), "元")
        return f"{amount:.4f} {suffix}"

    @staticmethod
    def _format_per_share_ko(value: Any, currency_word: str = "") -> str:
        """주당 금액을 한국어 단위로 표시한다(원화는 정수, 그 밖의 통화는 소수 2자리)."""
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return "N/A"
        if amount != amount:  # NaN
            return "N/A"
        number = f"{amount:,.0f}" if currency_word == "원" else f"{amount:,.2f}"
        return f"{number} {currency_word}".strip()

    @staticmethod
    def _format_text(value: Any) -> str:
        if value is None:
            return "N/A"
        text = str(value).strip()
        return text if text else "N/A"

    def _get_fundamental_blocks(self, result: AnalysisResult) -> Dict[str, Any]:
        """Extract financial_report / dividend / belong_boards / board rankings.

        Falls back to empty containers when fundamental_context is missing or partial,
        so callers can rely on dict shape without re-checking types.
        """
        ctx = getattr(result, "fundamental_context", None)
        if not isinstance(ctx, dict):
            return {
                "financial_report": {},
                "growth": {},
                "dividend": {},
                "belong_boards": [],
                "sector_top": [],
                "sector_bottom": [],
                "concept_top": [],
                "concept_bottom": [],
                "institution": {},
                "institution_status": None,
            }

        earnings_block = ctx.get("earnings") if isinstance(ctx.get("earnings"), dict) else {}
        earnings_data = earnings_block.get("data") if isinstance(earnings_block.get("data"), dict) else {}
        financial_report = earnings_data.get("financial_report") if isinstance(earnings_data.get("financial_report"), dict) else {}
        dividend = earnings_data.get("dividend") if isinstance(earnings_data.get("dividend"), dict) else {}

        growth_block = ctx.get("growth") if isinstance(ctx.get("growth"), dict) else {}
        growth_data = growth_block.get("data") if isinstance(growth_block.get("data"), dict) else {}

        boards_block = ctx.get("boards") if isinstance(ctx.get("boards"), dict) else {}
        boards_data = boards_block.get("data") if isinstance(boards_block.get("data"), dict) else {}
        sector_top = boards_data.get("top") if isinstance(boards_data.get("top"), list) else []
        sector_bottom = boards_data.get("bottom") if isinstance(boards_data.get("bottom"), list) else []
        concept_block = ctx.get("concept_boards") if isinstance(ctx.get("concept_boards"), dict) else {}
        if not concept_block and isinstance(ctx.get("concepts"), dict):
            concept_block = ctx.get("concepts")
        if not concept_block and isinstance(ctx.get("concept_rankings"), dict):
            concept_block = ctx.get("concept_rankings")
        concept_data = concept_block.get("data") if isinstance(concept_block.get("data"), dict) else concept_block
        if not isinstance(concept_data, dict):
            concept_data = {}
        concept_top = concept_data.get("top") if isinstance(concept_data.get("top"), list) else []
        concept_bottom = concept_data.get("bottom") if isinstance(concept_data.get("bottom"), list) else []

        belong_boards = ctx.get("belong_boards") if isinstance(ctx.get("belong_boards"), list) else []

        # 三大法人 (institutional flows) — tw-only; other markets keep status='not_supported'
        # and an empty data dict, so this block only renders for a Taiwan stock with data.
        institution_block = ctx.get("institution") if isinstance(ctx.get("institution"), dict) else {}
        institution_data = institution_block.get("data") if isinstance(institution_block.get("data"), dict) else {}

        return {
            "financial_report": financial_report,
            "growth": growth_data,
            "dividend": dividend,
            "belong_boards": belong_boards,
            "sector_top": sector_top,
            "sector_bottom": sector_bottom,
            "concept_top": concept_top,
            "concept_bottom": concept_bottom,
            "institution": institution_data,
            "institution_status": institution_block.get("status"),
        }

    def _append_fundamental_blocks(self, lines: List[str], result: AnalysisResult) -> None:
        """Append 财务摘要 / 股东回报 / 关联板块 markdown blocks.

        Each block is only rendered when at least one cell has data; this keeps
        the email compact when the fundamental pipeline returned partial/failed
        results (e.g. HK/US markets, ETF, or AkShare outages).
        """
        blocks = self._get_fundamental_blocks(result)
        report_language = self._get_report_language(result)
        labels = get_report_labels(report_language)

        stock_code = getattr(result, "code", None)
        self._append_financial_summary(lines, blocks, labels, report_language=report_language, stock_code=stock_code)
        self._append_shareholder_return(lines, blocks, labels, report_language=report_language, stock_code=stock_code)
        self._append_institutional_flow(lines, blocks, labels, report_language=report_language)
        self._append_related_boards(lines, blocks, labels)

    def _format_report_amount(
        self,
        value: Any,
        currency: Optional[str],
        report_language: Optional[str],
        stock_code: Any,
    ) -> str:
        """보고서 언어에 맞춰 금액을 표시한다. ko는 조/억/만 + 원·달러 등 한국어 단위를 쓴다."""
        if normalize_report_language(report_language) == "ko":
            return format_korean_amount(value, get_korean_currency_word(currency, stock_code))
        return self._format_amount_cn(value, currency)

    def _append_financial_summary(
        self,
        lines: List[str],
        blocks: Dict[str, Any],
        labels: Dict[str, str],
        report_language: Optional[str] = None,
        stock_code: Any = None,
    ) -> None:
        report = blocks.get("financial_report") or {}
        growth = blocks.get("growth") or {}
        currency = report.get("currency") if isinstance(report.get("currency"), str) else None

        def _amount(value: Any) -> str:
            return self._format_report_amount(value, currency, report_language, stock_code)

        cells = {
            "report_date": self._format_text(report.get("report_date")),
            "revenue": _amount(report.get("revenue")),
            "net_profit": _amount(report.get("net_profit_parent")),
            "operating_cash_flow": _amount(report.get("operating_cash_flow")),
            "roe": self._format_percent(report.get("roe") if report.get("roe") is not None else growth.get("roe")),
            "revenue_yoy": self._format_percent(growth.get("revenue_yoy")),
            "net_profit_yoy": self._format_percent(growth.get("net_profit_yoy")),
            "gross_margin": self._format_percent(growth.get("gross_margin")),
        }
        if all(v == "N/A" for v in cells.values()):
            return

        lines.extend([
            f"### 💼 {labels['financial_summary_heading']}",
            "",
            (
                f"| {labels['report_date_label']} | {labels['revenue_label']} | "
                f"{labels['net_profit_label']} | {labels['operating_cash_flow_label']} | "
                f"{labels['roe_label']} | {labels['revenue_yoy_label']} | "
                f"{labels['net_profit_yoy_label']} | {labels['gross_margin_label']} |"
            ),
            # 보고 기준일은 가운데, 금액·비율은 오른쪽 정렬 — 기존 시세 스냅샷 스타일과 맞춘다
            "|:------:|-------:|-------:|-------:|------:|------:|------:|------:|",
            (
                f"| {cells['report_date']} | {cells['revenue']} | {cells['net_profit']} | "
                f"{cells['operating_cash_flow']} | {cells['roe']} | {cells['revenue_yoy']} | "
                f"{cells['net_profit_yoy']} | {cells['gross_margin']} |"
            ),
            "",
        ])

    def _append_shareholder_return(
        self,
        lines: List[str],
        blocks: Dict[str, Any],
        labels: Dict[str, str],
        report_language: Optional[str] = None,
        stock_code: Any = None,
    ) -> None:
        dividend = blocks.get("dividend") or {}
        report = blocks.get("financial_report") or {}
        # Dividends are paid in the trading currency (yfinance `info.currency`)
        # which can differ from the financial-statement currency (e.g. HK ADRs
        # often report `financialCurrency=CNY` but pay dividends in HKD).
        dividend_currency = dividend.get("currency") if isinstance(dividend.get("currency"), str) else None
        if not dividend_currency:
            dividend_currency = report.get("currency") if isinstance(report.get("currency"), str) else None
        events = dividend.get("events") if isinstance(dividend.get("events"), list) else []
        latest_event = events[0] if events else {}
        if not isinstance(latest_event, dict):
            latest_event = {}

        ttm_event_count = dividend.get("ttm_event_count")
        if normalize_report_language(report_language) == "ko":
            ttm_cash = self._format_per_share_ko(
                dividend.get("ttm_cash_dividend_per_share"),
                get_korean_currency_word(dividend_currency, stock_code),
            )
        else:
            ttm_cash = self._format_per_share(dividend.get("ttm_cash_dividend_per_share"), dividend_currency)
        cells = {
            "ttm_cash": ttm_cash,
            "ttm_count": str(ttm_event_count) if isinstance(ttm_event_count, int) else "N/A",
            "ttm_yield": self._format_percent(dividend.get("ttm_dividend_yield_pct")),
            "latest_ex": self._format_text(latest_event.get("ex_dividend_date") or latest_event.get("event_date")),
        }
        if all(v == "N/A" for v in cells.values()):
            return

        lines.extend([
            f"### 💵 {labels['shareholder_return_heading']}",
            "",
            (
                f"| {labels['ttm_cash_dividend_label']} | {labels['ttm_event_count_label']} | "
                f"{labels['ttm_dividend_yield_label']} | {labels['latest_ex_dividend_label']} |"
            ),
            "|---------------------:|----------:|--------:|:--------:|",
            (
                f"| {cells['ttm_cash']} | {cells['ttm_count']} | "
                f"{cells['ttm_yield']} | {cells['latest_ex']} |"
            ),
            "",
        ])

    @classmethod
    def _format_net_shares(cls, value: Any) -> str:
        """Format an institutional net buy/sell in 万股/亿股, signed (+ = net buy).

        Thresholds: abs >= 1e8 -> 亿股, >= 1e4 -> 万股, else 股. None/NaN/non-numeric -> N/A.
        """
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return "N/A"
        if amount != amount:  # NaN
            return "N/A"
        sign = "+" if amount > 0 else ("-" if amount < 0 else "")
        a = abs(amount)
        if a >= 1e8:
            return f"{sign}{a / 1e8:.2f} 亿股"
        if a >= 1e4:
            return f"{sign}{a / 1e4:.2f} 万股"
        return f"{sign}{a:.0f} 股"

    def _append_institutional_flow(
        self,
        lines: List[str],
        blocks: Dict[str, Any],
        labels: Dict[str, str],
        report_language: Optional[str] = None,
    ) -> None:
        """Append the 三大法人 (institutional flows) table — tw-only.

        Renders only when the institution block reached status='ok' (a Taiwan stock
        whose TWSE T86 / TPEx fetch succeeded); every other market keeps
        status='not_supported' and is skipped, so this is strictly additive.
        """
        if blocks.get("institution_status") != "ok":
            return
        inst = blocks.get("institution") or {}
        if normalize_report_language(report_language) == "ko":
            def net_shares(value: Any) -> str:
                return format_korean_volume(value, signed="+")
        else:
            net_shares = self._format_net_shares
        cells = {
            "foreign": net_shares(inst.get("foreign_net")),
            "trust": net_shares(inst.get("trust_net")),
            "dealer": net_shares(inst.get("dealer_net")),
            "total": net_shares(inst.get("total_net")),
        }
        if all(v == "N/A" for v in cells.values()):
            return
        date = self._format_text(inst.get("date"))
        source = self._format_text(inst.get("source"))
        lines.extend([
            f"### 📊 {labels['institutional_flow_heading']}（{date} · {source}）",
            "",
            f"> {labels['institutional_flow_note']}",
            "",
            (
                f"| {labels['inst_foreign_label']} | {labels['inst_trust_label']} | "
                f"{labels['inst_dealer_label']} | {labels['inst_total_label']} |"
            ),
            "|-----:|-----:|------:|------------:|",
            f"| {cells['foreign']} | {cells['trust']} | {cells['dealer']} | {cells['total']} |",
            "",
        ])

    def _append_related_boards(
        self,
        lines: List[str],
        blocks: Dict[str, Any],
        labels: Dict[str, str],
    ) -> None:
        belong_boards = blocks.get("belong_boards") or []
        if not belong_boards:
            return

        sector_signals: Dict[str, Tuple[str, float]] = {}
        concept_signals: Dict[str, Tuple[str, float]] = {}

        def add_signals(target: Dict[str, Tuple[str, float]], rows: Any, label: str) -> None:
            for item in rows or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                if not name or name in target:
                    continue
                change_pct = _safe_float(item.get("change_pct"))
                if change_pct is not None:
                    target[name] = (label, change_pct)

        add_signals(sector_signals, blocks.get("sector_top"), labels["leading_board_label"])
        add_signals(sector_signals, blocks.get("sector_bottom"), labels["lagging_board_label"])
        add_signals(concept_signals, blocks.get("concept_top"), labels["leading_board_label"])
        add_signals(concept_signals, blocks.get("concept_bottom"), labels["lagging_board_label"])

        def resolve_board_type(name: str, board_type: str) -> str:
            normalized_type = board_type.strip().lower()
            sector_signal = sector_signals.get(name)
            concept_signal = concept_signals.get(name)
            if concept_signal and not sector_signal:
                return "concept"
            if sector_signal and not concept_signal:
                return "sector"

            normalized_name = name.strip().lower()
            if any(marker in normalized_name for marker in ("概念", "题材", "concept", "theme")):
                return "concept"
            if any(marker in normalized_name for marker in ("行业", "industry", "sector")):
                return "sector"

            if normalized_type in {"概念", "概念板块", "题材", "concept", "theme"}:
                return "concept"
            if normalized_type in {"行业", "行业板块", "industry", "sector"}:
                return "sector"
            # A-share belong_boards may omit type for concept/theme labels.
            # Keep a deterministic display type instead of leaking N/A.
            return "concept"

        def resolve_signal(name: str, board_group: str) -> Tuple[Optional[str], Optional[float]]:
            if board_group == "sector":
                return sector_signals.get(name, (None, None))
            if board_group == "concept":
                return concept_signals.get(name, (None, None))
            sector_signal = sector_signals.get(name)
            concept_signal = concept_signals.get(name)
            if sector_signal and not concept_signal:
                return sector_signal
            if concept_signal and not sector_signal:
                return concept_signal
            return None, None

        def board_type_label(board_group: str) -> str:
            if board_group == "sector":
                return labels["industry_boards_heading"]
            return labels["concept_boards_heading"]

        # Pre-resolve rows so signal-bearing boards can show their own
        # percentage, while boards without a matching change stay plain.
        prepared: List[Tuple[str, str, Optional[str], Optional[float]]] = []
        for raw in belong_boards[:5]:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            board_type = self._format_text(raw.get("type"))
            board_group = resolve_board_type(name, board_type)
            status_text, change_pct = resolve_signal(name, board_group)
            prepared.append((name, board_type_label(board_group), status_text, change_pct))

        if not prepared:
            return

        lines.append(f"### 🧩 {labels['related_boards_heading']}")
        lines.append("")
        has_signal = any(status is not None and change_pct is not None for _, _, status, change_pct in prepared)
        if has_signal:
            for name, board_type, status_text, change_pct in prepared:
                details = []
                if status_text is not None and change_pct is not None:
                    details.append(f"{board_type} {status_text} {change_pct:+.2f}%")
                suffix = f" ({', '.join(details)})" if details else ""
                lines.append(f"- {name}{suffix}")
        else:
            lines.append(" / ".join(name for name, _, _, _ in prepared))
        lines.append("")

    def _should_use_image_for_channel(
        self, channel: NotificationChannel, image_bytes: Optional[bytes]
    ) -> bool:
        """
        Decide whether to send as image for the given channel (Issue #289).

        Fallback rules (send as Markdown text instead of image):
        - image_bytes is None: conversion failed / imgkit not installed / content over max_chars
        - WeChat: image exceeds ~2MB limit
        """
        if channel.value not in self._markdown_to_image_channels or image_bytes is None:
            return False
        if channel == NotificationChannel.WECHAT and len(image_bytes) > WECHAT_IMAGE_MAX_BYTES:
            logger.warning(
                "WeCom 이미지 용량 초과(%d bytes), Markdown 텍스트로 대신 보냅니다",
                len(image_bytes),
            )
            return False
        return True

    @staticmethod
    def _sanitize_notification_diagnostics(text: Any) -> str:
        return sanitize_diagnostic_text(text)

    def _send_to_static_channel(
        self,
        channel: NotificationChannel,
        content: str,
        *,
        image_bytes: Optional[bytes],
        email_stock_codes: Optional[List[str]],
        email_send_to_all: bool,
        route_type: Optional[str] = None,
    ) -> bool:
        use_image = self._should_use_image_for_channel(channel, image_bytes)
        sanitized_content = strip_hidden_markdown_metadata(content).strip()
        if channel == NotificationChannel.WECHAT:
            if use_image:
                return self._send_wechat_image(image_bytes)
            return self.send_to_wechat(content)
        if channel == NotificationChannel.FEISHU:
            if getattr(self, "_feishu_send_as_file", False) and route_type == "report":
                date_str = datetime.now().strftime('%Y%m%d')
                filepath = self.save_report_to_file(
                    sanitized_content, filename=f"report_{date_str}.md"
                )
                return self.send_feishu_file(filepath)
            return self.send_to_feishu(sanitized_content)
        if channel == NotificationChannel.DINGTALK:
            return self.send_to_dingtalk(sanitized_content)
        if channel == NotificationChannel.TELEGRAM:
            if use_image:
                return self._send_telegram_photo(image_bytes)
            return self.send_to_telegram(content)
        if channel == NotificationChannel.EMAIL:
            receivers = None
            if email_send_to_all and self._stock_email_groups:
                receivers = self.get_all_email_receivers()
            elif email_stock_codes and self._stock_email_groups:
                receivers = self.get_receivers_for_stocks(email_stock_codes)
            if use_image:
                return self._send_email_with_inline_image(image_bytes, receivers=receivers)
            return self.send_to_email(
                sanitized_content,
                receivers=receivers,
            )
        if channel == NotificationChannel.PUSHOVER:
            return self.send_to_pushover(content)
        if channel == NotificationChannel.NTFY:
            return self.send_to_ntfy(sanitized_content)
        if channel == NotificationChannel.GOTIFY:
            return self.send_to_gotify(sanitized_content)
        if channel == NotificationChannel.PUSHPLUS:
            return self.send_to_pushplus(sanitized_content)
        if channel == NotificationChannel.SERVERCHAN3:
            return self.send_to_serverchan3(sanitized_content)
        if channel == NotificationChannel.CUSTOM:
            if use_image:
                return self._send_custom_webhook_image(image_bytes, fallback_content=content)
            return self.send_to_custom(sanitized_content)
        if channel == NotificationChannel.DISCORD:
            return self.send_to_discord(content)
        if channel == NotificationChannel.SLACK:
            if use_image:
                return self._send_slack_image(image_bytes, fallback_content=content)
            return self.send_to_slack(content)
        if channel == NotificationChannel.ASTRBOT:
            return self.send_to_astrbot(sanitized_content)
        logger.warning(f"지원하지 않는 알림 채널: {channel}")
        return False

    def send_with_results(
        self,
        content: str,
        email_stock_codes: Optional[List[str]] = None,
        email_send_to_all: bool = False,
        route_type: Optional[str] = None,
        severity: Optional[str] = None,
        dedup_key: Optional[str] = None,
        cooldown_key: Optional[str] = None,
        structured_payload: Optional[Dict[str, Any]] = None,
    ) -> NotificationDispatchResult:
        """
        Send a notification and return per-channel diagnostics.

        ``send()`` keeps the historical bool API and delegates here.

        Fallback rules (Markdown-to-image, Issue #289):
        - When image_bytes is None (conversion failed / imgkit not installed /
          content over max_chars): all channels configured for image will send
          as Markdown text instead.
        - When WeChat image exceeds ~2MB: that channel falls back to Markdown text.

        Args:
            content: 메시지 내용(Markdown 형식)
            email_stock_codes: 종목 코드 목록(선택, 이메일 채널에서 해당 그룹 메일 주소로 보낼 때 사용, Issue #268)
            email_send_to_all: 설정된 모든 메일 주소로 보낼지 여부(시장 전체 리뷰처럼 특정 종목에 속하지 않는 내용용)
            route_type: 알림 라우팅 유형. None이면 기존 동작 유지, report/alert/system_error는 설정에 따라 고정 채널을 거른다
            severity: 알림 심각도. 지정하지 않으면 라우팅 유형으로 추정한다
            dedup_key: 선택적 고정 중복 제거 key. 지정하지 않으면 내용 hash를 쓴다
            cooldown_key: 선택적 쿨다운 key. 지정하지 않으면 라우팅/심각도별 기본 key를 쓴다
            structured_payload: 선택적 종목 또는 시장 구조화 결과. 이미지 템플릿을 정확히 채울 때만 쓴다

        Returns:
            Structured dispatch diagnostics.
        """
        context_success = self.send_to_context(content)
        if not self.should_broadcast_static_channels():
            if context_success:
                logger.info("컨텍스트 대화로 발송을 마쳐 고정 알림 채널은 건너뜁니다")
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                    channel_results=[ChannelAttemptResult(channel="__context__", success=True)],
                )
            logger.warning("대화형 컨텍스트 발송에 실패해 고정 알림 채널을 건너뛰었습니다")
            return NotificationDispatchResult(
                dispatched=True,
                success=False,
                status="all_failed",
                channel_results=[
                    ChannelAttemptResult(
                        channel="__context__",
                        success=False,
                        error_code="send_failed",
                        retryable=True,
                    )
                ],
                message="interactive context delivery failed; static channels skipped",
            )

        if not self._available_channels:
            if context_success:
                logger.info("메시지 컨텍스트 채널로 발송을 마쳤습니다(다른 알림 채널 없음)")
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                    channel_results=[ChannelAttemptResult(channel="__context__", success=True)],
                )
            logger.warning("알림 서비스를 사용할 수 없어 발송을 건너뜁니다")
            return NotificationDispatchResult(
                dispatched=False,
                success=False,
                status="no_channel",
                message="notification service unavailable",
            )

        target_channels = self.get_channels_for_route(route_type)
        if not target_channels:
            if context_success:
                logger.info("메시지 컨텍스트 채널로 발송을 마쳤습니다(라우팅 후 남은 알림 채널 없음)")
                return NotificationDispatchResult(
                    dispatched=True,
                    success=True,
                    status="sent",
                    channel_results=[ChannelAttemptResult(channel="__context__", success=True)],
                )
            logger.warning("알림 라우팅 %s에 해당하는 설정 채널이 없어 고정 알림 채널을 건너뜁니다", route_type)
            return NotificationDispatchResult(
                dispatched=False,
                success=False,
                status="no_channel",
                message=f"notification route {route_type} has no configured channel",
            )

        noise_decision = self.evaluate_noise_control(
            content,
            route_type=route_type,
            severity=severity,
            dedup_key=dedup_key,
            cooldown_key=cooldown_key,
        )
        if not noise_decision.should_send:
            logger.info(noise_decision.message)
            status = "sent" if context_success else "noise_suppressed"
            results = [ChannelAttemptResult(channel="__context__", success=True)] if context_success else []
            return NotificationDispatchResult(
                dispatched=bool(context_success),
                success=bool(context_success),
                status=status,
                channel_results=results,
                message=noise_decision.message,
            )

        # Markdown to image (Issue #289): convert once if any channel needs it.
        # Per-channel decision via _should_use_image_for_channel (see send() docstring for fallback rules).
        image_bytes = None
        channels_needing_image = {
            ch for ch in target_channels
            if ch.value in self._markdown_to_image_channels
            and ch not in {NotificationChannel.NTFY, NotificationChannel.GOTIFY}
        }
        if channels_needing_image:
            from src.md2img import markdown_to_image
            image_bytes = markdown_to_image(
                content,
                max_chars=self._markdown_to_image_max_chars,
                structured_payload=structured_payload,
            )
            if image_bytes:
                logger.info("Markdown을 이미지로 변환했습니다. %s로 이미지를 보냅니다",
                            [ch.value for ch in channels_needing_image])
            elif channels_needing_image:
                try:
                    from src.config import get_config
                    engine = getattr(get_config(), "md2img_engine", "wkhtmltoimage")
                except Exception:
                    engine = "wkhtmltoimage"
                hint = (
                    "npm i -g markdown-to-file" if engine == "markdown-to-file"
                    else "wkhtmltopdf (apt install wkhtmltopdf / brew install wkhtmltopdf)"
                )
                logger.warning(
                    "Markdown 이미지 변환에 실패해 텍스트로 대신 보냅니다. MARKDOWN_TO_IMAGE_CHANNELS 설정을 확인하고 %s를 설치하세요",
                    hint,
                )

        channel_names = ', '.join(ChannelDetector.get_channel_name(ch) for ch in target_channels)
        logger.info(f"채널 {len(target_channels)}개로 알림 발송 중: {channel_names}")

        success_count = 0
        fail_count = 0
        channel_results: List[ChannelAttemptResult] = []

        for channel in target_channels:
            channel_name = ChannelDetector.get_channel_name(channel)
            started_at = time.monotonic()
            try:
                result = self._send_to_static_channel(
                    channel,
                    content,
                    image_bytes=image_bytes,
                    email_stock_codes=email_stock_codes,
                    email_send_to_all=email_send_to_all,
                    route_type=route_type,
                )
                latency_ms = int((time.monotonic() - started_at) * 1000)

                if result:
                    success_count += 1
                else:
                    fail_count += 1
                channel_results.append(
                    ChannelAttemptResult(
                        channel=channel.value,
                        success=bool(result),
                        error_code=None if result else "send_failed",
                        retryable=not bool(result),
                        latency_ms=latency_ms,
                    )
                )

            except Exception as e:
                logger.error(f"{channel_name} 발송 실패: {e}")
                fail_count += 1
                channel_results.append(
                    ChannelAttemptResult(
                        channel=channel.value,
                        success=False,
                        error_code="exception",
                        retryable=True,
                        latency_ms=int((time.monotonic() - started_at) * 1000),
                        diagnostics=self._sanitize_notification_diagnostics(str(e)),
                    )
                )

        logger.info(f"알림 발송 완료: 성공 {success_count}건, 실패 {fail_count}건")
        if success_count > 0:
            self.record_noise_control(noise_decision)
        else:
            self.release_noise_control(noise_decision)
        success = success_count > 0 or context_success
        if success_count > 0 and fail_count > 0:
            status = "partial_failed"
        elif success_count > 0 or context_success:
            status = "sent"
        else:
            status = "all_failed"
        if context_success:
            channel_results.insert(0, ChannelAttemptResult(channel="__context__", success=True))
        return NotificationDispatchResult(
            dispatched=True,
            success=success,
            status=status,
            channel_results=channel_results,
        )

    def send(
        self,
        content: str,
        email_stock_codes: Optional[List[str]] = None,
        email_send_to_all: bool = False,
        route_type: Optional[str] = None,
        severity: Optional[str] = None,
        dedup_key: Optional[str] = None,
        cooldown_key: Optional[str] = None,
        structured_payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        통합 발송 인터페이스 - 설정된 모든 채널로 보낸다.

        Returns:
            하나 이상의 채널에서 발송에 성공했는지 여부
        """
        result = self.send_with_results(
            content,
            email_stock_codes=email_stock_codes,
            email_send_to_all=email_send_to_all,
            route_type=route_type,
            severity=severity,
            dedup_key=dedup_key,
            cooldown_key=cooldown_key,
            structured_payload=structured_payload,
        )
        return bool(result.success)

    def save_report_to_file(
        self,
        content: str,
        filename: Optional[str] = None
    ) -> str:
        """
        일일 리포트를 로컬 파일로 저장한다

        Args:
            content: 일일 리포트 내용
            filename: 파일명(선택, 기본값은 날짜로 생성)

        Returns:
            저장된 파일 경로
        """
        from pathlib import Path

        if filename is None:
            date_str = datetime.now().strftime('%Y%m%d')
            filename = f"report_{date_str}.md"

        # reports 디렉터리가 있는지 확인(프로젝트 루트의 reports 사용)
        reports_dir = Path(__file__).parent.parent / 'reports'
        reports_dir.mkdir(parents=True, exist_ok=True)

        filepath = reports_dir / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"일일 리포트 저장 위치: {filepath}")
        return str(filepath)

    def save_and_send_feishu_file(
        self,
        content: str,
        filename: Optional[str] = None,
    ) -> bool:
        """
        Save report content to a local markdown file and upload it to Feishu.

        This is a convenience wrapper around :meth:`save_report_to_file` +
        :meth:`send_feishu_file`.

        Args:
            content: Report content (Markdown).
            filename: Optional file name; auto-generated from date when omitted.

        Returns:
            Whether the Feishu file upload succeeded.
        """
        filepath = self.save_report_to_file(
            strip_hidden_markdown_metadata(content).strip(),
            filename=filename,
        )
        logger.info("Feishu로 파일을 업로드합니다: %s", filepath)
        return self.send_feishu_file(filepath)


class NotificationBuilder:
    """
    알림 메시지 빌더

    메시지를 손쉽게 만드는 메서드를 제공한다
    """

    @staticmethod
    def build_simple_alert(
        title: str,
        content: str,
        alert_type: str = "info"
    ) -> str:
        """
        간단한 알림 메시지를 만든다

        Args:
            title: 제목
            content: 내용
            alert_type: 유형(info, warning, error, success)
        """
        emoji_map = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
        }
        emoji = emoji_map.get(alert_type, "📢")

        return f"{emoji} **{title}**\n\n{content}"

    @staticmethod
    def build_stock_summary(results: List[AnalysisResult]) -> str:
        """
        종목 요약을 만든다(짧은 버전)

        빠른 알림용
        """
        report_language = normalize_report_language(
            next((getattr(result, "report_language", None) for result in results if getattr(result, "report_language", None)), None)
        )
        labels = get_report_labels(report_language)
        lines = [f"📊 **{labels['summary_heading']}**", ""]

        for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
            display_action = display_action_fields_for_result(
                r,
                report_language=report_language,
            )["action"]
            signal_action = {
                "buy": "buy",
                "add": "buy",
                "hold": "hold",
                "reduce": "reduce",
                "sell": "sell",
                "watch": "watch",
                "avoid": "hold",
                "alert": "sell",
            }.get(display_action)
            display_advice = display_operation_advice_for_result(
                r,
                report_language=report_language,
            )
            signal_text, emoji, _ = get_signal_level(
                signal_action or display_advice,
                r.sentiment_score,
                report_language,
            )
            name = get_localized_stock_name(r.name, r.code, report_language)
            lines.append(
                f"{emoji} {name}({r.code}): {display_advice} | "
                f"{labels['score_label']} {r.sentiment_score}"
            )

        return "\n".join(lines)


# 편의 함수
def get_notification_service() -> NotificationService:
    """알림 서비스 인스턴스를 반환한다"""
    return NotificationService()


def send_daily_report(results: List[AnalysisResult]) -> bool:
    """
    일일 리포트 발송 단축 함수

    채널을 자동 감지해 발송한다
    """
    service = get_notification_service()

    # 리포트 생성
    report = service.generate_daily_report(results)

    # 로컬에 저장
    service.save_report_to_file(report)

    # 설정된 채널로 발송(자동 감지)
    return service.send(report)


if __name__ == "__main__":
    # 테스트 코드
    logging.basicConfig(level=logging.DEBUG)
    from src.analyzer import AnalysisResult

    # 가상 분석 결과
    test_results = [
        AnalysisResult(
            code='600519',
            name='贵州茅台',
            sentiment_score=75,
            trend_prediction='看多',
            analysis_summary='技术面强势，消息面利好',
            operation_advice='买入',
            technical_analysis='放量突破 MA20，MACD 金叉',
            news_summary='公司发布分红公告，业绩超预期',
        ),
        AnalysisResult(
            code='000001',
            name='平安银行',
            sentiment_score=45,
            trend_prediction='震荡',
            analysis_summary='横盘整理，等待方向',
            operation_advice='持有',
            technical_analysis='均线粘合，成交量萎缩',
            news_summary='近期无重大消息',
        ),
        AnalysisResult(
            code='300750',
            name='宁德时代',
            sentiment_score=35,
            trend_prediction='看空',
            analysis_summary='技术面走弱，注意风险',
            operation_advice='卖出',
            technical_analysis='跌破 MA10 支撑，量能不足',
            news_summary='行业竞争加剧，毛利率承压',
        ),
    ]

    service = NotificationService()

    # 감지된 채널 표시
    print("=== 알림 채널 감지 ===")
    print(f"현재 채널: {service.get_channel_names()}")
    print(f"채널 목록: {service.get_available_channels()}")
    print(f"서비스 사용 가능: {service.is_available()}")

    # 일일 리포트 생성
    print("\n=== 일일 리포트 생성 테스트 ===")
    report = service.generate_daily_report(test_results)
    print(report)

    # 파일로 저장
    print("\n=== 일일 리포트 저장 ===")
    filepath = service.save_report_to_file(report)
    print(f"저장 완료: {filepath}")

    # 발송 테스트
    if service.is_available():
        print(f"\n=== 발송 테스트({service.get_channel_names()}) ===")
        success = service.send(report)
        print(f"발송 결과: {'成功' if success else '失败'}")
    else:
        print("\n알림 채널이 설정되지 않아 발송 테스트를 건너뜁니다")

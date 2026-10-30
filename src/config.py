# -*- coding: utf-8 -*-
"""
===================================
A주 관심종목 AI 분석 시스템 - 설정 관리 모듈
===================================

역할:
1. 싱글턴 패턴으로 전역 설정 관리
2. .env 파일에서 민감한 설정 불러오기
3. 타입이 안전한 설정 접근 인터페이스 제공
"""

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Literal, Mapping, Optional, Tuple
from urllib.parse import unquote, urlparse
from dotenv import load_dotenv, dotenv_values
from dataclasses import dataclass, field

from src.core.config_manager import unescape_compose_sensitive_env_value
from src.report_language import (
    is_supported_report_language_value,
    normalize_report_language,
)
from src.notification_routing import parse_notification_route_channels
from src.notification_noise import (
    NOTIFICATION_SEVERITIES,
    is_supported_notification_severity,
    parse_notification_quiet_hours,
    validate_notification_timezone,
)
from src.notification_contracts import (
    is_feishu_app_bot_configured,
    is_feishu_static_configured,
)
from src.services.stock_list_parser import split_stock_list
from src.llm.backend_registry import (
    AUTO_AGENT_BACKEND_ID,
    GENERATION_ONLY_BACKEND_IDS,
    LOCAL_CLI_GENERATION_BACKEND_IDS,
    LITELLM_BACKEND_ID,
    OPENCODE_CLI_BACKEND_ID,
    SUPPORTED_AGENT_GENERATION_BACKENDS,
    SUPPORTED_AGENT_UI_BACKENDS,
    SUPPORTED_GENERATION_BACKENDS,
)
from src.llm.local_cli_backend import (
    DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
    DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES,
    DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS,
    MAX_GENERATION_BACKEND_MAX_CONCURRENCY,
    MAX_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
    MAX_LOCAL_CLI_OUTPUT_BYTES,
    MAX_LOCAL_CLI_TIMEOUT_SECONDS,
)
from src.llm import generation_params as llm_generation_params
from src.llm.hermes import (
    HERMES_DEFAULT_BASE_URL,
    HERMES_DEFAULT_MODEL,
    HERMES_DEFAULT_PROTOCOL,
    HermesConfigIssue,
    hermes_blocked_route_candidates,
    hermes_model_info,
    is_reserved_hermes_name,
    parse_hermes_channel,
    route_identity_candidates,
    route_deployment_origins,
    route_has_hermes,
)
from src.scheduler import normalize_schedule_times
from src.utils.market_review_region import normalize_market_review_region_lenient

logger = logging.getLogger(__name__)

@dataclass
class ConfigIssue:
    """Structured configuration validation issue with a severity level.

    Attributes:
        severity: One of "error", "warning", or "info".
        message:  Human-readable description of the issue.
        field:    The environment variable / config field name most relevant to
                  this issue (empty string when not applicable).
    """

    severity: Literal["error", "warning", "info"]
    message: str
    field: str = ""
    code: str = ""

    def __str__(self) -> str:  # noqa: D105
        return self.message


_MANAGED_LITELLM_KEY_PROVIDERS = {"gemini", "vertex_ai", "anthropic", "openai", "deepseek"}
SUPPORTED_LLM_CHANNEL_PROTOCOLS = ("openai", "anthropic", "gemini", "vertex_ai", "deepseek", "ollama")
SUPPORTED_LLM_CHANNEL_API_SURFACES = ("chat_completions", "responses")
_FALLBACK_LITELLM_MODEL_PROVIDERS = _MANAGED_LITELLM_KEY_PROVIDERS | set(SUPPORTED_LLM_CHANNEL_PROTOCOLS) | {
    "minimax",
    "cohere",
    "huggingface",
    "bedrock",
    "sagemaker",
    "azure",
    "replicate",
    "together_ai",
    "palm",
    "text-completion-openai",
    "command-r",
    "groq",
    "cerebras",
    "fireworks_ai",
    "friendliai",
    "openrouter",
    "xai",
}
_FALSEY_ENV_VALUES = {"0", "false", "no", "off"}
PROMPT_CACHE_DIAGNOSTICS_LEVELS = {"off", "basic", "debug"}
SUPPORTED_AGENT_BACKENDS = {"auto", "litellm"}
AGENT_BACKEND_REMOVED_MESSAGE = (
    "Codex App Server 问股后端已移除。请在 Agent 设置中主动改为默认执行方式，并配置所需模型来源。"
    "独立 Codex CLI 普通报告不受本项移除影响。"
)
TICKFLOW_KLINE_ADJUST_VALUES = {"none", "forward", "backward", "forward_additive", "backward_additive"}
# CSI 300 / CSI 500 / ChiNext / 고배당 저변동 / 나스닥 / 금; 방어 자산은 머니마켓 ETF
DEFAULT_ETF_ROTATION_POOL = ("510300", "510500", "159915", "512890", "513100", "518880")
DEFAULT_ETF_ROTATION_SAFE_ASSET = "511880"
# Fallback defaults used when ANSPIRE_API_KEYS is reused as legacy OpenAI-compatible source.
# These are compatibility examples; actual availability should be validated by Anspire console/model entitlement.
ANSPIRE_LLM_BASE_URL_DEFAULT = "https://open-gateway.anspire.cn/v6"
ANSPIRE_LLM_MODEL_DEFAULT = "Doubao-Seed-2.0-lite"
MODELFLARE_LLM_BASE_URL_DEFAULT = "https://modelflare.dev/v1"
MODELFLARE_LLM_MODEL_DEFAULT = "openai/gpt-6.1-sol"


def _has_ntfy_topic_endpoint(value: Optional[str]) -> bool:
    """Return whether an ntfy URL points at a concrete topic endpoint."""
    raw_url = (value or "").strip()
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return False
    return any(unquote(segment).strip() for segment in parsed.path.split("/") if segment)


def _has_gotify_base_url(value: Optional[str]) -> bool:
    """Return whether a Gotify URL points at a server base URL, not /message."""
    raw_url = (value or "").strip().rstrip("/")
    if not raw_url:
        return False
    parsed = urlparse(raw_url)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.query or parsed.fragment:
        return False
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    return not (path_segments and path_segments[-1].lower() == "message")


def normalize_tickflow_kline_adjust(value: Optional[str]) -> str:
    """Normalize TickFlow daily K-line adjustment mode."""
    normalized = (value or "none").strip().lower()
    if normalized in TICKFLOW_KLINE_ADJUST_VALUES:
        return normalized
    logger.warning(
        "Invalid TICKFLOW_KLINE_ADJUST=%r; falling back to none",
        value,
    )
    return "none"


def parse_prompt_cache_diagnostics_level(value: Optional[str]) -> str:
    """Parse prompt-cache diagnostics level with a conservative fallback."""
    normalized = (value or "off").strip().lower()
    if normalized in PROMPT_CACHE_DIAGNOSTICS_LEVELS:
        return normalized
    logger.warning(
        "Invalid LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL=%r; falling back to off",
        value,
    )
    return "off"


AGENT_MAX_STEPS_DEFAULT = 10
FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT = 8.0
NEWS_STRATEGY_WINDOWS: Dict[str, int] = {
    "ultra_short": 1,
    "short": 3,
    "medium": 7,
    "long": 30,
}


@dataclass(frozen=True)
class AgentContextCompressionPreset:
    """Preset values for visible chat history compression."""

    trigger_tokens: int
    protected_turns: int
    summary_target_tokens: int
    # P1 reserves this budget for future prompt-size controls; it is not
    # enforced by the current rolling-summary state table.
    history_budget_tokens: int


AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE = "balanced"
AGENT_CONTEXT_COMPRESSION_PROFILES: Dict[str, AgentContextCompressionPreset] = {
    "cost": AgentContextCompressionPreset(
        trigger_tokens=6000,
        protected_turns=2,
        summary_target_tokens=900,
        history_budget_tokens=4000,
    ),
    "balanced": AgentContextCompressionPreset(
        trigger_tokens=12000,
        protected_turns=4,
        summary_target_tokens=1500,
        history_budget_tokens=8000,
    ),
    "long_context_raw_first": AgentContextCompressionPreset(
        trigger_tokens=24000,
        protected_turns=6,
        summary_target_tokens=2600,
        history_budget_tokens=14000,
    ),
}


def parse_env_bool(value: Optional[str], default: bool = False) -> bool:
    """Parse common truthy/falsey environment-style values."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if not normalized:
        return default
    return normalized not in _FALSEY_ENV_VALUES


def parse_env_int(
    value: Optional[str],
    default: int,
    *,
    field_name: str,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """Parse an integer env value with warning + fallback semantics."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        parsed = int(default)
    else:
        try:
            parsed = int(str(raw_value).strip())
        except (TypeError, ValueError):
            logger.warning(
                "%s=%r is not a valid integer; falling back to %s",
                field_name,
                raw_value,
                default,
            )
            parsed = int(default)

    if minimum is not None and parsed < minimum:
        logger.warning(
            "%s=%r is below minimum %s; clamping to %s",
            field_name,
            parsed,
            minimum,
            minimum,
        )
        parsed = minimum
    if maximum is not None and parsed > maximum:
        logger.warning(
            "%s=%r is above maximum %s; clamping to %s",
            field_name,
            parsed,
            maximum,
            maximum,
        )
        parsed = maximum
    return parsed


def parse_env_float(
    value: Optional[str],
    default: float,
    *,
    field_name: str,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> float:
    """Parse a float env value with warning + fallback semantics."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        parsed = float(default)
    else:
        try:
            parsed = float(str(raw_value).strip())
        except (TypeError, ValueError):
            logger.warning(
                "%s=%r is not a valid number; falling back to %s",
                field_name,
                raw_value,
                default,
            )
            parsed = float(default)

    if minimum is not None and parsed < minimum:
        logger.warning(
            "%s=%r is below minimum %s; clamping to %s",
            field_name,
            parsed,
            minimum,
            minimum,
        )
        parsed = minimum
    if maximum is not None and parsed > maximum:
        logger.warning(
            "%s=%r is above maximum %s; clamping to %s",
            field_name,
            parsed,
            maximum,
            maximum,
        )
        parsed = maximum
    return parsed


def normalize_news_strategy_profile(value: Optional[str]) -> str:
    """Normalize news strategy profile to known values."""
    candidate = (value or "short").strip().lower()
    return candidate if candidate in NEWS_STRATEGY_WINDOWS else "short"


def resolve_news_window_days(news_max_age_days: int, news_strategy_profile: Optional[str]) -> int:
    """Resolve effective news window days from profile and global max-age."""
    profile = normalize_news_strategy_profile(news_strategy_profile)
    profile_days = NEWS_STRATEGY_WINDOWS.get(profile, NEWS_STRATEGY_WINDOWS["short"])
    return max(1, min(max(1, int(news_max_age_days)), profile_days))


def normalize_agent_context_compression_profile(value: Optional[str]) -> str:
    """Normalize visible-chat context compression profile values."""
    candidate = (value or AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE).strip().lower()
    if candidate in AGENT_CONTEXT_COMPRESSION_PROFILES:
        return candidate
    logger.warning(
        "Invalid AGENT_CONTEXT_COMPRESSION_PROFILE=%r; falling back to %s",
        value,
        AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE,
    )
    return AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE


def get_agent_context_compression_preset(profile: Optional[str]) -> AgentContextCompressionPreset:
    """Return the preset for a normalized profile, falling back to balanced."""
    normalized = normalize_agent_context_compression_profile(profile)
    return AGENT_CONTEXT_COMPRESSION_PROFILES[normalized]


def parse_agent_context_compression_int(
    value: Optional[str],
    default: int,
    *,
    field_name: str,
    minimum: int,
    maximum: int,
) -> int:
    """Parse compression integers; empty/invalid/out-of-range values follow preset defaults."""
    raw_value = value
    if raw_value is None or not str(raw_value).strip():
        return int(default)
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        logger.warning(
            "%s=%r is not a valid integer; falling back to preset default %s",
            field_name,
            raw_value,
            default,
        )
        return int(default)
    if parsed < minimum or parsed > maximum:
        logger.warning(
            "%s=%r is outside supported range [%s, %s]; falling back to preset default %s",
            field_name,
            parsed,
            minimum,
            maximum,
            default,
        )
        return int(default)
    return parsed


def canonicalize_llm_channel_protocol(value: Optional[str]) -> str:
    """Normalize a protocol label into a LiteLLM provider identifier."""
    candidate = (value or "").strip().lower().replace("-", "_")
    aliases = {
        "openai_compatible": "openai",
        "openai_compat": "openai",
        "claude": "anthropic",
        "google": "gemini",
        "vertex": "vertex_ai",
        "vertexai": "vertex_ai",
    }
    return aliases.get(candidate, candidate)


def canonicalize_llm_channel_api_surface(value: Optional[str]) -> str:
    """Normalize an LLM channel endpoint surface label."""
    candidate = (value or "").strip().lower().replace("-", "_")
    aliases = {
        "chat": "chat_completions",
        "chat_completion": "chat_completions",
        "completions": "chat_completions",
        "response": "responses",
        "responses_api": "responses",
    }
    return aliases.get(candidate, candidate)


def normalize_llm_channel_api_surface(value: Optional[str]) -> str:
    """Return a supported endpoint surface, defaulting to Chat Completions."""
    normalized = canonicalize_llm_channel_api_surface(value)
    if normalized in SUPPORTED_LLM_CHANNEL_API_SURFACES:
        return normalized
    return "chat_completions"


def is_supported_llm_channel_api_surface_value(value: Optional[str]) -> bool:
    """Return whether a raw API surface is blank or recognized."""
    canonical = canonicalize_llm_channel_api_surface(value)
    return not canonical or canonical in SUPPORTED_LLM_CHANNEL_API_SURFACES


@lru_cache(maxsize=1)
def get_litellm_model_providers() -> frozenset[str]:
    """Return provider identifiers from the installed LiteLLM routing enum.

    LiteLLM adds direct providers independently of this repository. Loading
    its enum keeps channel validation aligned with the actual router instead
    of relying on a permanently incomplete local allow-list. The fallback is
    only for lightweight test stubs or a broken optional import; a production
    installation gets the complete provider set from its pinned LiteLLM.
    """
    providers = set(_FALLBACK_LITELLM_MODEL_PROVIDERS)
    try:
        from litellm.types.utils import LlmProviders

        providers.update(
            str(provider.value).strip().lower()
            for provider in LlmProviders
            if str(getattr(provider, "value", "")).strip()
        )
    except (ImportError, AttributeError, TypeError):
        logger.debug("LiteLLM provider metadata unavailable; using the compatibility fallback")
    return frozenset(providers)


def get_explicit_llm_channel_model_provider(model: str) -> str:
    """Return the explicit LiteLLM provider prefix, if the model has one.

    A slash alone does not establish a provider: OpenAI-compatible gateways
    commonly expose provider-owned IDs such as ``Qwen/Qwen3`` or
    ``deepseek-ai/DeepSeek-V3``. Only prefixes understood as LiteLLM providers
    are treated as routing declarations.
    """
    normalized_model = (model or "").strip()
    if "/" not in normalized_model:
        return ""
    raw_prefix = normalized_model.split("/", 1)[0].lower()
    canonical_prefix = canonicalize_llm_channel_protocol(raw_prefix)
    providers = get_litellm_model_providers()
    if raw_prefix in providers:
        return raw_prefix
    if canonical_prefix in providers:
        return canonical_prefix
    return ""


def apply_litellm_api_surface(model: str, api_surface: Optional[str]) -> str:
    """Encode an explicit API surface in a LiteLLM wire model.

    LiteLLM's ``provider/responses/model`` convention keeps the public Router
    alias stable while letting ``completion()`` bridge messages, streaming,
    tools, responses, and usage through the provider's Responses endpoint.
    """
    normalized_model = (model or "").strip()
    if not normalized_model or normalize_llm_channel_api_surface(api_surface) != "responses":
        return normalized_model
    provider = get_explicit_llm_channel_model_provider(normalized_model)
    if provider != "openai":
        raise ValueError(
            "Responses API surface requires a normalized openai/<model> route; "
            f"got {normalized_model!r}"
        )
    provider, remainder = normalized_model.split("/", 1)
    if remainder.startswith("responses/"):
        return normalized_model
    return f"{provider}/responses/{remainder}"


def resolve_llm_channel_base_url(channel_name: str, base_url: Optional[str]) -> str:
    """Apply named-channel endpoint defaults without changing explicit configuration."""
    explicit = (base_url or "").strip()
    if explicit:
        return explicit
    if channel_name.strip().lower() == "modelflare":
        return MODELFLARE_LLM_BASE_URL_DEFAULT
    return ""


def resolve_llm_channel_names(config_map: Mapping[str, str]) -> str:
    """Infer the Modelflare channel from its key unless channels are explicit."""
    channels = (config_map.get("LLM_CHANNELS") or "").strip()
    if channels:
        return channels
    if any(
        key.strip()
        for field in ("MODELFLARE_KEY", "LLM_MODELFLARE_API_KEY", "LLM_MODELFLARE_API_KEYS")
        for key in (config_map.get(field) or "").split(',')
    ):
        return "modelflare"
    return ""


def resolve_llm_channel_api_keys(
    channel_name: str, api_keys: List[str], config_map: Mapping[str, str],
) -> List[str]:
    """Keep explicit channel keys first, with MODELFLARE_KEY as its shorthand."""
    if api_keys or channel_name.strip().lower() != "modelflare":
        return api_keys
    return [key.strip() for key in (config_map.get("MODELFLARE_KEY") or "").split(',') if key.strip()]


def resolve_llm_channel_models(
    channel_name: str,
    models: List[str],
    *,
    channel_names: str,
    primary_model: str = "",
    fallback_models: str = "",
) -> List[str]:
    """Resolve explicit routes or the default for a single Modelflare channel."""
    if models:
        return models
    names = [name.strip().lower() for name in channel_names.split(',') if name.strip()]
    primary = primary_model.strip() or MODELFLARE_LLM_MODEL_DEFAULT
    if (names != ["modelflare"] or channel_name.strip().lower() != "modelflare"
            or not primary.startswith("openai/") or not primary[7:].strip()):
        return []
    routes = [primary] + [model.strip() for model in fallback_models.split(',')]
    return list(dict.fromkeys(
        route for route in routes if route.startswith("openai/") and route[7:].strip()
    ))


def resolve_llm_channel_protocol(
    protocol: Optional[str],
    *,
    base_url: Optional[str] = None,
    models: Optional[List[str]] = None,
    channel_name: Optional[str] = None,
) -> str:
    """Resolve the effective protocol for a channel."""
    explicit = canonicalize_llm_channel_protocol(protocol)
    if explicit in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
        return explicit

    # Requesty is OpenAI-compatible; its vendor/model IDs (anthropic/...,
    # vertex/...) are not LiteLLM protocol declarations.
    if is_requesty_gateway_base_url(base_url):
        return "openai"

    for model in models or []:
        if "/" not in model:
            continue
        prefix = canonicalize_llm_channel_protocol(model.split("/", 1)[0])
        if prefix in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            return prefix

    # Infer from channel name (e.g. "deepseek" -> deepseek, "gemini" -> gemini)
    if channel_name:
        name_protocol = canonicalize_llm_channel_protocol(channel_name)
        if name_protocol in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            return name_protocol

    if base_url:
        parsed = urlparse(base_url)
        if parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0"}:
            # Default to openai for local servers (vLLM, LM Studio, LocalAI, etc.).
            # Ollama users should set PROTOCOL=ollama explicitly or name the channel "ollama".
            return "openai"
        return "openai"

    return ""


def channel_allows_empty_api_key(protocol: Optional[str], base_url: Optional[str]) -> bool:
    """Return True when a channel can run without an API key."""
    resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url)
    if resolved_protocol == "ollama":
        return True
    parsed = urlparse(base_url or "")
    return parsed.hostname in {"127.0.0.1", "localhost", "0.0.0.0"}


def is_requesty_gateway_base_url(base_url: Optional[str]) -> bool:
    """Return whether a Base URL points at the Requesty router (any region)."""
    raw_url = (base_url or "").strip()
    if not raw_url:
        return False
    try:
        hostname = (urlparse(raw_url).hostname or "").lower()
    except ValueError:
        return False
    return hostname == "requesty.ai" or hostname.endswith(".requesty.ai")


def route_discovered_llm_model(model_id: str, base_url: Optional[str]) -> str:
    """Return the saved channel value for an ID listed by a gateway ``/models``.

    Requesty lists ``vendor/model`` IDs (``openai/gpt-4o-mini``,
    ``anthropic/claude-sonnet-4-6``, ``vertex/claude-sonnet-4-5``) and managed
    policy IDs without a slash. The vendor segment collides with LiteLLM
    provider names, so the saved value carries the OpenAI-compatible gateway
    route once (``openai/openai/gpt-4o-mini``); LiteLLM strips that layer and
    sends the full Requesty ID unchanged.
    """
    normalized_id = (model_id or "").strip()
    if not normalized_id or not is_requesty_gateway_base_url(base_url):
        return normalized_id
    return f"openai/{normalized_id}"


def normalize_llm_channel_model(model: str, protocol: Optional[str], base_url: Optional[str] = None) -> str:
    """Attach a provider prefix when the model omits it."""
    normalized_model = model.strip()
    if not normalized_model:
        return normalized_model

    resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url, models=[normalized_model])

    if (
        "/" in normalized_model
        and resolved_protocol == "openai"
        and is_requesty_gateway_base_url(base_url)
        and normalized_model.split("/", 1)[0].lower() != "openai"
    ):
        # Requesty vendor IDs such as anthropic/... or vertex/... must stay
        # intact behind the OpenAI-compatible gateway route instead of being
        # read as LiteLLM direct providers.
        return f"openai/{normalized_model}"

    if "/" in normalized_model:
        # The model already has a slash, e.g. 'deepseek-ai/DeepSeek-V3'.
        # Check if the prefix is a known LiteLLM provider; if so, keep it.
        # Otherwise (e.g. HuggingFace-style IDs on SiliconFlow), prepend
        # the resolved protocol so LiteLLM routes via the correct handler.
        raw_prefix, remainder = normalized_model.split("/", 1)
        prefix = raw_prefix.lower()
        canonical_prefix = canonicalize_llm_channel_protocol(prefix)
        providers = get_litellm_model_providers()
        if prefix in providers:
            return normalized_model
        if canonical_prefix in providers:
            return f"{canonical_prefix}/{remainder}"
        # Not a real provider prefix — add one so LiteLLM routes correctly.
        if resolved_protocol:
            return f"{resolved_protocol}/{normalized_model}"
        return normalized_model

    if not resolved_protocol:
        return normalized_model
    return f"{resolved_protocol}/{normalized_model}"


def find_incompatible_llm_channel_models(
    models: List[str],
    protocol: Optional[str],
    api_surface: Optional[str],
    base_url: Optional[str] = None,
) -> List[str]:
    """Return models whose actual LiteLLM route conflicts with the surface.

    Responses routing is implemented through LiteLLM's OpenAI bridge, so both
    the channel protocol and every normalized model route must resolve to the
    OpenAI provider. This is the shared invariant used by validation, runtime
    loading, diagnostics, and screening.
    """
    if normalize_llm_channel_api_surface(api_surface) != "responses":
        return []
    resolved_protocol = resolve_llm_channel_protocol(
        protocol,
        base_url=base_url,
        models=models,
    )
    if resolved_protocol != "openai":
        return [model for model in models if (model or "").strip()]
    incompatible: List[str] = []
    for model in models:
        normalized_model = normalize_llm_channel_model(model, resolved_protocol, base_url)
        if normalized_model and get_explicit_llm_channel_model_provider(normalized_model) != "openai":
            incompatible.append(model)
    return incompatible


def find_llm_channel_surface_conflicts(
    channels: List[Dict[str, Any]],
) -> Dict[str, Tuple[str, ...]]:
    """Return public route aliases declared with more than one API surface."""
    route_surfaces: Dict[str, set[str]] = {}
    for channel in channels:
        if not isinstance(channel, dict) or not channel.get("enabled", True):
            continue
        protocol = str(channel.get("protocol") or "")
        base_url = str(channel.get("base_url") or "")
        surface = normalize_llm_channel_api_surface(channel.get("api_surface"))
        for raw_model in channel.get("models") or []:
            model = normalize_llm_channel_model(str(raw_model), protocol, base_url)
            if model:
                route_surfaces.setdefault(model, set()).add(surface)
    return {
        model: tuple(sorted(surfaces))
        for model, surfaces in route_surfaces.items()
        if len(surfaces) > 1
    }


def get_configured_llm_models(model_list: List[Dict[str, Any]]) -> List[str]:
    """Return non-legacy model names declared in Router model_list order.

    Uses the top-level ``model_name`` (the routing alias that users set in
    LITELLM_MODEL) rather than ``litellm_params.model`` (the wire-level
    model identifier).  For channel-built entries both are identical, but
    YAML configs may define a friendly alias that differs from the
    underlying provider/model path.
    """
    models: List[str] = []
    seen: set = set()
    for entry in model_list or []:
        # Prefer top-level model_name (router routing key); fall back to
        # litellm_params.model for entries that omit it.
        name = str(entry.get("model_name") or "").strip()
        if not name:
            params = entry.get("litellm_params", {}) or {}
            name = str(params.get("model") or "").strip()
        if not name or name.startswith("__legacy_") or name in seen:
            continue
        seen.add(name)
        models.append(name)
    return models


def resolve_litellm_wire_model(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Resolve a router alias to its underlying LiteLLM wire model."""
    return llm_generation_params.resolve_litellm_wire_model(model, model_list)


def resolve_litellm_thinking_enabled(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[bool]:
    """Resolve whether the outgoing LiteLLM request explicitly enables thinking."""
    return llm_generation_params.resolve_litellm_thinking_enabled(
        model,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def get_fixed_litellm_temperature(
    model: str,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[float]:
    """Return a provider-mandated temperature for known strict models."""
    return llm_generation_params.get_fixed_litellm_temperature(
        model,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def normalize_litellm_temperature(
    model: str,
    temperature: Optional[float],
    *,
    default: float = 0.7,
    model_list: Optional[List[Dict[str, Any]]] = None,
    request_overrides: Optional[Dict[str, Any]] = None,
) -> float:
    """Normalize temperature before sending a LiteLLM request."""
    return llm_generation_params.normalize_litellm_temperature(
        model,
        temperature,
        default=default,
        model_list=model_list,
        request_overrides=request_overrides,
    )


def resolve_unified_llm_temperature(model: str) -> float:
    """Resolve the raw unified LLM temperature with backward-compatible fallbacks."""
    llm_temperature_raw = os.getenv("LLM_TEMPERATURE")
    if llm_temperature_raw and llm_temperature_raw.strip():
        try:
            return float(llm_temperature_raw)
        except (ValueError, TypeError):
            pass

    provider_temperature_env = {
        "gemini": "GEMINI_TEMPERATURE",
        "vertex_ai": "GEMINI_TEMPERATURE",
        "anthropic": "ANTHROPIC_TEMPERATURE",
        "openai": "OPENAI_TEMPERATURE",
        "deepseek": "OPENAI_TEMPERATURE",
    }
    preferred_env = provider_temperature_env.get(_get_litellm_provider(model))
    if preferred_env:
        preferred_value = os.getenv(preferred_env)
        if preferred_value and preferred_value.strip():
            try:
                return float(preferred_value)
            except (ValueError, TypeError):
                pass

    for env_name in ("GEMINI_TEMPERATURE", "ANTHROPIC_TEMPERATURE", "OPENAI_TEMPERATURE"):
        env_value = os.getenv(env_name)
        if env_value and env_value.strip():
            try:
                return float(env_value)
            except (ValueError, TypeError):
                continue

    return 0.7


def _get_litellm_provider(model: str) -> str:
    """Extract the LiteLLM provider prefix from a model string."""
    if not model:
        return ""
    if "/" in model:
        return model.split("/", 1)[0]
    return "openai"


def _uses_direct_env_provider(model: str) -> bool:
    """Whether runtime handles the model via direct litellm env/provider resolution."""
    provider = _get_litellm_provider(model)
    return bool(provider) and provider not in _MANAGED_LITELLM_KEY_PROVIDERS


def _matches_route_set(model: str, routes: set[str]) -> bool:
    """Loose safety match for Hermes/provenance checks, not normal route availability."""
    return bool(route_identity_candidates(model) & set(routes or set()))


def _matches_exact_route(model: str, routes: set[str]) -> bool:
    """Match the Router's top-level model_name exactly for normal availability checks."""
    normalized_model = str(model or "").strip()
    return bool(normalized_model) and normalized_model in set(routes or set())


def normalize_agent_litellm_model(
    model: str,
    configured_models: Optional[set[str]] = None,
) -> str:
    """Normalize AGENT_LITELLM_MODEL while preserving configured router aliases."""
    normalized_model = (model or "").strip()
    if not normalized_model:
        return ""
    if "/" not in normalized_model:
        if configured_models and normalized_model in configured_models:
            return normalized_model
        return f"openai/{normalized_model}"
    return normalized_model


def get_effective_agent_primary_model(config: "Config") -> str:
    """Return the effective Agent primary model with fallback inheritance."""
    configured_router_models = set(
        get_configured_llm_models(getattr(config, "llm_model_list", []) or [])
    )
    configured_agent_model = normalize_agent_litellm_model(
        getattr(config, "agent_litellm_model", ""),
        configured_models=configured_router_models,
    )
    if configured_agent_model:
        return configured_agent_model
    return (getattr(config, "litellm_model", "") or "").strip()


def get_effective_agent_models_to_try(config: "Config") -> List[str]:
    """Return Agent model try-order: primary + global fallbacks (deduped)."""
    configured_router_models = set(
        get_configured_llm_models(getattr(config, "llm_model_list", []) or [])
    )
    raw_models = [get_effective_agent_primary_model(config)] + (
        getattr(config, "litellm_fallback_models", []) or []
    )
    seen = set()
    ordered_models: List[str] = []
    for model in raw_models:
        normalized_model = (model or "").strip()
        if not normalized_model:
            continue
        dedupe_key = normalize_agent_litellm_model(
            normalized_model,
            configured_models=configured_router_models,
        )
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        ordered_models.append(normalized_model)
    return ordered_models


def setup_env(override: bool = False):
    """
    Initialize environment variables from .env file.

    Args:
        override: If True, overwrite existing environment variables with values
                  from .env file. Set to True when reloading config after updates.
                  Default is False to preserve behavior on initial load where
                  system environment variables take precedence.
    """
    Config._capture_bootstrap_runtime_env_overrides()
    # src/config.py -> src/ -> root
    env_file = os.getenv("ENV_FILE")
    if env_file:
        env_path = Path(env_file)
    else:
        env_path = Path(__file__).parent.parent / '.env'
    compose_sensitive_keys = ("CUSTOM_WEBHOOK_BODY_TEMPLATE",)
    preexisting_compose_sensitive_keys = {
        key for key in compose_sensitive_keys if key in os.environ
    }
    load_dotenv(dotenv_path=env_path, override=override)
    try:
        raw_env_values = dotenv_values(env_path, interpolate=False)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("Failed to read raw .env values from %s: %s", env_path, exc)
        return

    key = "CUSTOM_WEBHOOK_BODY_TEMPLATE"
    if key in raw_env_values and (
        override or key not in preexisting_compose_sensitive_keys
    ):
        raw_value = raw_env_values.get(key)
        os.environ[key] = unescape_compose_sensitive_env_value(
            key,
            "" if raw_value is None else str(raw_value),
        )


@dataclass
class Config:
    """
    시스템 설정 클래스 - 싱글턴 패턴
    
    설계 메모:
    - dataclass로 설정 속성 정의를 단순화
    - 모든 설정은 환경 변수에서 읽고, 기본값 지원
    - 클래스 메서드 get_instance()로 싱글턴 접근
    """
    
    # === 관심종목 설정 ===
    stock_list: List[str] = field(default_factory=list)

    # === Feishu(페이슈) 클라우드 문서 설정 ===
    feishu_app_id: Optional[str] = None
    feishu_app_secret: Optional[str] = None
    feishu_folder_token: Optional[str] = None  # 대상 폴더 Token

    # === 데이터 소스 API Token ===
    tushare_token: Optional[str] = None
    tickflow_api_key: Optional[str] = None
    tickflow_kline_adjust: str = "none"
    tickflow_priority: int = 2
    tickflow_batch_daily_enabled: bool = True
    tickflow_batch_size: int = 100
    futu_opend_host: Optional[str] = None
    futu_opend_port: int = 11111
    futu_hk_realtime_source_priority: str = "futu,longbridge,akshare,yfinance"
    mx_apikey: Optional[str] = None
    mx_priority: int = 6
    finnhub_api_key: Optional[str] = None
    alphavantage_api_key: Optional[str] = None
    longbridge_app_key: Optional[str] = None
    longbridge_app_secret: Optional[str] = None
    longbridge_access_token: Optional[str] = None
    longbridge_oauth_client_id: Optional[str] = None
    stock_index_remote_update_enabled: bool = True

    # === Built-in stock screening ===
    screening_enabled: bool = False

    # === AI 분석 설정 ===
    generation_backend: str = LITELLM_BACKEND_ID
    generation_fallback_backend: str = LITELLM_BACKEND_ID
    generation_backend_timeout_seconds: int = DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS
    generation_backend_max_output_bytes: int = DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES
    generation_backend_max_concurrency: int = DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY
    local_cli_backend_max_concurrency: int = DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY
    opencode_cli_model: str = ""
    # LiteLLM unified model config (provider/model format, e.g. gemini/gemini-3.1-pro-preview)
    litellm_model: str = ""  # Primary model; must include provider prefix when set explicitly
    litellm_fallback_models: List[str] = field(default_factory=list)  # Cross-model fallback list

    # Unified temperature for all LLM calls (LLM_TEMPERATURE); legacy per-provider temps are fallback only
    llm_temperature: float = 0.7

    # Provider prompt-cache controls. These do not control provider implicit cache.
    llm_prompt_cache_telemetry_enabled: bool = True
    llm_prompt_cache_hints_enabled: bool = False
    llm_prompt_cache_diagnostics_level: str = "off"

    # --- Multi-channel LLM config (new) ---
    # LITELLM_CONFIG: path to a standard litellm_config.yaml file (most powerful)
    litellm_config_path: Optional[str] = None
    # Internal metadata: which config layer actually produced llm_model_list
    llm_models_source: str = "legacy_env"
    # LLM_CHANNELS: list of channel dicts, each with name/base_url/api_keys/models
    llm_channels: List[Dict[str, Any]] = field(default_factory=list)
    # Raw channel names requested through LLM_CHANNELS, including channels that
    # were skipped during parsing because required channel fields were missing.
    llm_channel_names: List[str] = field(default_factory=list)
    # Structured parse issues raised while turning LLM_CHANNELS into deployments.
    llm_channel_config_issues: List[Dict[str, str]] = field(default_factory=list)
    # True when invalid explicit channel config must prevent legacy key inference.
    llm_blocks_legacy_fallback: bool = False
    # Canonical Hermes route names that were requested but blocked by atomic parse issues.
    llm_blocked_hermes_routes: List[str] = field(default_factory=list)
    # Pre-built LiteLLM Router model_list (populated from channels, YAML, or legacy keys)
    llm_model_list: List[Dict[str, Any]] = field(default_factory=list)

    # Multi-key support: each list is parsed from *_API_KEYS (comma-separated) with single-key fallback
    gemini_api_keys: List[str] = field(default_factory=list)
    anthropic_api_keys: List[str] = field(default_factory=list)
    openai_api_keys: List[str] = field(default_factory=list)
    deepseek_api_keys: List[str] = field(default_factory=list)

    # Legacy single-key fields (kept for backward compatibility; gemini_api_keys[0] when set)
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-3.1-pro-preview"  # 주 모델
    gemini_model_fallback: str = "gemini-3-flash-preview"  # 예비 모델
    gemini_temperature: float = 0.7  # 온도 값(0.0-2.0, 출력 무작위성 조절, 기본 0.7)

    # Gemini API 요청 설정(429 요청 제한 방지)
    gemini_request_delay: float = 2.0  # 요청 간격(초)
    gemini_max_retries: int = 5  # 최대 재시도 횟수
    gemini_retry_delay: float = 5.0  # 재시도 기본 대기 시간(초)

    # Anthropic Claude API(예비용, Gemini를 쓸 수 없을 때 사용)
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-6"  # Claude model name
    anthropic_temperature: float = 0.7  # Anthropic temperature (0.0-1.0, default 0.7)
    anthropic_max_tokens: int = 8192  # Max tokens for Anthropic responses

    # OpenAI 호환 API(예비용, Gemini/Anthropic을 쓸 수 없을 때 사용)
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None  # 예: https://api.openai.com/v1
    openai_model: str = "gpt-5.5"  # OpenAI 호환 모델 이름
    openai_vision_model: Optional[str] = None  # Deprecated: use VISION_MODEL instead
    openai_temperature: float = 0.7  # OpenAI 온도 값(0.0-2.0, 기본 0.7)

    # === Vision 설정 ===
    # VISION_MODEL: litellm model string used for image understanding calls.
    # Fallback chain: VISION_MODEL → OPENAI_VISION_MODEL → gemini/gemini-2.0-flash
    vision_model: str = ""
    # VISION_PROVIDER_PRIORITY: comma-separated provider order for Vision fallback.
    vision_provider_priority: str = "gemini,anthropic,openai"

    # === 검색 엔진 설정(여러 Key 부하 분산 지원) ===
    anspire_api_keys: List[str] = field(default_factory=list)  # Anspire Search API Keys
    bocha_api_keys: List[str] = field(default_factory=list)  # Bocha API Keys
    minimax_api_keys: List[str] = field(default_factory=list)  # MiniMax API Keys
    tavily_api_keys: List[str] = field(default_factory=list)  # Tavily API Keys
    brave_api_keys: List[str] = field(default_factory=list)  # Brave Search API Keys
    serpapi_keys: List[str] = field(default_factory=list)  # SerpAPI Keys
    searxng_base_urls: List[str] = field(default_factory=list)  # SearXNG instance URLs (self-hosted, no quota)
    searxng_public_instances_enabled: bool = False  # Opt in to public discovery when base URLs are absent
    searxng_timeout_seconds: int = 10  # 직접 운영하는 SearXNG 1회 검색 제한 시간(초)

    # === Social Sentiment (US stocks only, api.adanos.org) ===
    social_sentiment_api_key: Optional[str] = None
    social_sentiment_api_url: str = "https://api.adanos.org"

    # === 뉴스·분석 필터 설정 ===
    news_max_age_days: int = 3   # 뉴스 최대 유효 기간(일)
    news_strategy_profile: str = "short"  # 뉴스 기간 전략 단계: ultra_short/short/medium/long
    news_intel_retention_days: int = 30  # 로컬 뉴스 저장소 보관 일수
    news_intel_fetch_timeout_sec: float = 8.0  # 뉴스 소스 1개당 수집 제한 시간
    news_intel_max_items_per_source: int = 50  # 1회 수집 시 소스별 최대 건수
    news_intel_auto_fetch_enabled: bool = False  # 분석 전에 로컬 뉴스 소스를 자동 초기화·수집할지 여부
    newsnow_base_url: str = "https://newsnow.busiyi.world"  # NewsNow HTTP API base URL (데이터 소스용, LLM/provider base URL에는 영향 없음)
    bias_threshold: float = 5.0  # 이격도 기준값(%), 넘으면 추격 매수 자제 안내

    # === Agent 모드 설정 ===
    agent_backend: str = "auto"
    agent_generation_backend: str = AUTO_AGENT_BACKEND_ID
    agent_litellm_model: str = ""  # Optional Agent-only primary model; empty inherits LITELLM_MODEL
    agent_mode: bool = False
    _agent_mode_explicit: bool = False  # True when AGENT_MODE was explicitly set in env
    agent_max_steps: int = AGENT_MAX_STEPS_DEFAULT
    agent_skills: List[str] = field(default_factory=list)
    agent_skill_dir: Optional[str] = None
    agent_nl_routing: bool = False  # Enable natural language routing in bot dispatcher
    agent_arch: str = "single"     # Agent architecture: 'single' (legacy) or 'multi' (orchestrator)
    agent_orchestrator_mode: str = "standard"  # Orchestrator mode: quick/standard/full/specialist
    agent_orchestrator_timeout_s: int = 600  # Cooperative timeout budget for the whole multi-agent pipeline
    agent_technical_agent_timeout_s: float = 0
    agent_intel_agent_timeout_s: float = 0
    agent_risk_agent_timeout_s: float = 0
    agent_decision_agent_timeout_s: float = 0
    agent_portfolio_agent_timeout_s: float = 0
    agent_skill_agent_timeout_s: float = 0
    # Per-category default timeouts for agent tool calls (seconds).
    # 0 / unset means "no category default" -> falls back to the global
    # tool_call_timeout_seconds budget.
    agent_data_tool_timeout_s: float = 0.0
    agent_search_tool_timeout_s: float = 0.0
    agent_analysis_tool_timeout_s: float = 0.0
    agent_action_tool_timeout_s: float = 0.0
    agent_skill_concurrency: int = 3
    agent_risk_override: bool = True  # Allow risk agent to veto buy signals
    agent_deep_research_budget: int = 30000  # Max token budget for deep research
    agent_deep_research_timeout: int = 180  # Max seconds for /research command before returning timeout
    agent_memory_enabled: bool = False  # Enable memory & calibration system
    agent_skill_autoweight: bool = True  # Weight skills by attributable Outcome performance
    agent_skill_routing: str = "auto"  # Skill routing: 'auto' (regime-based) or 'manual'
    agent_context_compression_enabled: bool = False  # Compress visible chat history before Agent calls
    agent_context_compression_profile: str = AGENT_CONTEXT_COMPRESSION_DEFAULT_PROFILE
    agent_context_compression_trigger_tokens: int = 12000
    agent_context_protected_turns: int = 4
    agent_event_monitor_enabled: bool = False  # Enable periodic event-driven alert checks in schedule mode
    agent_event_monitor_interval_minutes: int = 5  # Polling interval for event monitor background checks
    agent_event_alert_rules_json: str = ""  # JSON array of serialized EventMonitor rules

    # === 알림 설정(여러 개 동시 설정 가능, 모두에게 발송) ===
    
    # WeCom(기업용 위챗) Webhook
    wechat_webhook_url: Optional[str] = None
    
    # Feishu Webhook
    feishu_webhook_url: Optional[str] = None
    feishu_webhook_secret: Optional[str] = None  # 사용자 정의 봇 서명 키(선택)
    feishu_webhook_keyword: Optional[str] = None  # 사용자 정의 봇 키워드(선택)
    dingtalk_webhook_url: Optional[str] = None
    dingtalk_secret: Optional[str] = None

    # Feishu 앱 봇(App Bot) 알림
    feishu_chat_id: Optional[str] = None  # 대상 그룹 대화 chat_id(그룹 모드) 또는 사용자 open_id(1:1 모드)
    feishu_receive_id_type: str = "chat_id"  # 수신자 ID 종류: "chat_id"(그룹) / "open_id"(1:1)
    feishu_domain: str = "feishu"  # Feishu 도메인: "feishu"(feishu.cn) / "lark"(larksuite.com)
    
    # Telegram 설정(Bot Token과 Chat ID를 함께 설정해야 함)
    telegram_bot_token: Optional[str] = None  # Bot Token(@BotFather에서 발급)
    telegram_chat_id: Optional[str] = None  # Chat ID
    telegram_message_thread_id: Optional[str] = None  # Topic ID (Message Thread ID) for groups
    
    # 이메일 설정(주소와 인증 코드만 있으면 SMTP 자동 인식)
    email_sender: Optional[str] = None  # 보내는 사람 이메일
    email_sender_name: str = "daily_stock_analysis股票分析助手"  # 보내는 사람 표시 이름
    email_password: Optional[str] = None  # 이메일 비밀번호/인증 코드
    email_receivers: List[str] = field(default_factory=list)  # 받는 사람 목록(비워 두면 나에게 발송)

    # Stock-to-email group routing (Issue #268): STOCK_GROUP_N + EMAIL_GROUP_N
    # When configured, each group's report is sent to that group's emails only.
    stock_email_groups: List[Tuple[List[str], List[str]]] = field(default_factory=list)

    # Pushover 설정(휴대폰/데스크톱 푸시 알림)
    pushover_user_key: Optional[str] = None  # 사용자 Key(https://pushover.net 에서 발급)
    pushover_api_token: Optional[str] = None  # 앱 API Token

    # ntfy 설정(전체 topic endpoint, 예: https://ntfy.sh/my-topic)
    ntfy_url: Optional[str] = None
    ntfy_token: Optional[str] = None

    # Gotify 설정(server base URL; sender가 /message를 붙임)
    gotify_url: Optional[str] = None
    gotify_token: Optional[str] = None
    
    # 사용자 정의 Webhook(여러 개 가능, 쉼표로 구분)
    # 대상: DingTalk, Discord, Slack, 직접 운영 서비스 등 POST JSON을 받는 모든 Webhook
    custom_webhook_urls: List[str] = field(default_factory=list)
    custom_webhook_bearer_token: Optional[str] = None  # Bearer Token(인증이 필요한 Webhook용)
    custom_webhook_body_template: Optional[str] = None  # 사용자 정의 Webhook JSON body 템플릿
    webhook_verify_ssl: bool = True  # Webhook HTTPS 인증서 검사, false면 자체 서명 인증서 허용(MITM 위험 있음)

    # Discord 알림 설정
    discord_bot_token: Optional[str] = None  # Discord Bot Token
    discord_main_channel_id: Optional[str] = None  # Discord 메인 채널 ID
    discord_webhook_url: Optional[str] = None  # Discord Webhook URL
    discord_interactions_public_key: Optional[str] = None  # Discord Interaction 수신 서명 검증용 공개 키

    # Slack 알림 설정
    slack_webhook_url: Optional[str] = None  # Slack Incoming Webhook URL
    slack_bot_token: Optional[str] = None  # Slack Bot Token (xoxb-...)
    slack_channel_id: Optional[str] = None  # Slack 채널 ID (Bot 모드에서는 필수)

    # AstrBot 알림 설정
    astrbot_token: Optional[str] = None
    astrbot_url: Optional[str] = None

    # 알림 라우팅 정책(Issue #1200 P3): 비워 두면 해당 유형은 설정된 모든 채널 사용
    notification_report_channels: List[str] = field(default_factory=list)
    notification_alert_channels: List[str] = field(default_factory=list)
    notification_system_error_channels: List[str] = field(default_factory=list)

    # 알림 줄이기 기능(Issue #1200 P4): 기본은 모두 꺼짐, 정적 알림 채널에만 적용
    notification_dedup_ttl_seconds: int = 0
    notification_cooldown_seconds: int = 0
    notification_quiet_hours: str = ""
    notification_timezone: str = ""
    notification_min_severity: str = ""
    notification_daily_digest_enabled: bool = False

    # 종목별 발송 모드: 모아서 보내지 않고 종목 하나 분석이 끝날 때마다 바로 발송
    single_stock_notify: bool = False

    # 리포트 종류: simple(간단) 또는 full(전체)
    report_type: str = "simple"
    report_language: str = "zh"

    # 분석 결과 요약만: true면 요약만 보내고 종목별 상세는 제외(Issue #262)
    report_summary_only: bool = False
    report_show_llm_model: bool = True

    # Report Engine P0: Jinja2 renderer and integrity checks
    report_templates_dir: str = "templates"  # Template directory (relative to project root)
    report_renderer_enabled: bool = False  # Enable Jinja2 rendering (default off for zero regression)
    report_integrity_enabled: bool = True  # Content integrity validation after LLM output
    report_integrity_retry: int = 1  # Retry count when mandatory fields missing (0 = placeholder only)
    report_history_compare_n: int = 0  # History comparison count (0 = disabled)

    # PushPlus 발송 설정
    pushplus_token: Optional[str] = None  # PushPlus Token
    pushplus_topic: Optional[str] = None  # PushPlus 그룹 코드(여러 명에게 발송)

    # ServerChan3 발송 설정
    serverchan3_sendkey: Optional[str] = None  # ServerChan3 SendKey

    # 분석 간격(초) - API 요청 제한을 피하기 위함
    analysis_delay: float = 0.0  # 종목 분석과 시장 전체 분석 사이의 대기 시간

    # Merge stock + market report into one notification (Issue #190)
    merge_email_notification: bool = False

    # 메시지 길이 제한(바이트) - 너무 길면 자동으로 나눠 발송
    feishu_max_bytes: int = 20000  # Feishu 제한 약 20KB, 기본 20000바이트
    feishu_send_as_file: bool = False  # Feishu에서 리포트를 파일로 보낼지 여부(기본은 텍스트 메시지)
    wechat_max_bytes: int = 4000   # WeCom 제한 4096바이트, 기본 4000바이트
    discord_max_words: int = 2000  # Discord 제한 2000자, 기본 2000자
    wechat_msg_type: str = "markdown"  # WeCom 메시지 종류, 기본은 markdown

    # Markdown을 이미지로 변환(Issue #289): Markdown을 지원하지 않는 채널에는 이미지로 발송
    markdown_to_image_channels: List[str] = field(default_factory=list)  # 쉼표로 구분: telegram,wechat,custom,email
    markdown_to_image_max_chars: int = 15000  # 이 길이를 넘으면 변환하지 않음(너무 큰 이미지 방지)
    md2img_engine: str = "wkhtmltoimage"  # wkhtmltoimage | markdown-to-file | playwright
    share_image_xiaohongshu_url: Optional[str] = None
    share_image_xiaohongshu_handle: Optional[str] = None
    share_image_xiaohongshu_id: Optional[str] = None
    share_image_xiaohongshu_qr_path: Optional[str] = None

    # 실시간 시세 미리 받기(Issue #455): false면 끔, efinance/akshare_em 전체 시장 수집을 피함
    prefetch_realtime_quotes: bool = True

    # === 데이터베이스 설정 ===
    database_path: str = "./data/stock_analysis.db"
    sqlite_wal_enabled: bool = True
    sqlite_busy_timeout_ms: int = 5000
    sqlite_write_retry_max: int = 3
    sqlite_write_retry_base_delay: float = 0.1

    # 분석 컨텍스트 스냅샷 저장 여부(이력 조회용)
    save_context_snapshot: bool = True

    # === 백테스트 설정 ===
    backtest_enabled: bool = True
    backtest_eval_window_days: int = 10
    backtest_min_age_days: int = 14
    backtest_engine_version: str = "v1"
    backtest_neutral_band_pct: float = 2.0

    # === ETF 로테이션 설정(--etf-rotation 에서만 사용) ===
    etf_rotation_pool: List[str] = field(default_factory=lambda: list(DEFAULT_ETF_ROTATION_POOL))
    etf_rotation_safe_asset: str = DEFAULT_ETF_ROTATION_SAFE_ASSET
    etf_rotation_lookback_days: int = 60
    etf_rotation_rebalance: str = "weekly"
    etf_rotation_top_n: int = 2
    etf_rotation_switch_buffer_pct: float = 2.0
    etf_rotation_cost_bps: float = 10.0
    etf_rotation_backtest_years: int = 8
    
    # === 로그 설정 ===
    log_dir: str = "./logs"  # 로그 파일 폴더
    log_level: str = "INFO"  # 로그 레벨
    
    # === 시스템 설정 ===
    max_workers: int = 3  # 동시 실행 수를 낮춰 차단 방지
    debug: bool = False
    http_proxy: Optional[str] = None  # HTTP 프록시 (예: http://127.0.0.1:10809)
    https_proxy: Optional[str] = None # HTTPS 프록시
    
    # === 예약 작업 설정 ===
    schedule_enabled: bool = False            # 예약 작업 사용 여부
    schedule_time: str = "18:00"              # 매일 발송 시각(HH:MM 형식)
    schedule_times: List[str] = field(default_factory=lambda: ["18:00"])
    schedule_run_immediately: bool = True     # 시작할 때 바로 한 번 실행할지 여부
    # 예약 모드 시작 시 즉시 실행의 당일 중복 방지 스위치: 그날 전체 분석 성공 기록이 있으면 시작 시 재실행을 건너뜀;
    # false로 두면 이 동작을 완전히 끔(원래의 "시작할 때마다 바로 실행" 방식으로 돌아감)
    schedule_startup_dedup: bool = True
    run_immediately: bool = True              # 시작할 때 바로 한 번 실행할지 여부(예약 모드가 아닐 때)
    market_review_enabled: bool = True        # 시장 전체 리뷰 사용 여부
    daily_market_context_enabled: bool = True   # 시장 환경 요약을 종목 분석 Prompt와 보수적 안전장치에 쓸지 여부
    # 시장 리뷰 대상 지역: cn(중국 A주), hk(홍콩), us(미국), jp(일본), kr(한국), both(전체 시장)
    market_review_region: str = "cn"
    market_review_color_scheme: str = "green_up"
    # 거래일 확인: 기본 켜짐, 휴장일에는 실행 건너뜀; false 또는 --force-run 으로 강제 실행 가능(Issue #373)
    trading_day_check_enabled: bool = True

    # === 실시간 시세 보강 데이터 설정 ===
    # 실시간 시세 스위치(끄면 과거 종가로 분석)
    enable_realtime_quote: bool = True
    # 장중 실시간 기술 지표: 켜면 실시간 가격으로 MA/정배열 계산(Issue #234); 끄면 전일 종가 사용
    enable_realtime_technical_indicators: bool = True
    # 매물대(보유 원가 분포) 스위치(이 API는 불안정해서 클라우드 배포 시 끄기를 권장)
    enable_chip_distribution: bool = True
    # Eastmoney API 패치 스위치
    enable_eastmoney_patch: bool = False
    # 실시간 시세 데이터 소스 우선순위(쉼표로 구분)
    # 추천 순서: tencent > akshare_sina > efinance > akshare_em > tushare
    # - tencent: Tencent 금융, 거래량 비율/회전율/PER 등 제공, 종목별 조회 안정적(추천)
    # - akshare_sina: Sina 금융, 기본 시세는 안정적이나 거래량 비율 없음
    # - efinance/akshare_em: Eastmoney 전체 시장 API, 데이터가 가장 풍부하지만 차단되기 쉬움
    # - tushare: Tushare Pro, 2000포인트 필요, 데이터 풍부(유료 사용자는 우선 사용 가능)
    realtime_source_priority: str = "tencent,akshare_sina,efinance,akshare_em"
    # 실시간 시세 캐시 시간(초)
    realtime_cache_ttl: int = 600
    # 서킷 브레이커 대기 시간(초)
    circuit_breaker_cooldown: int = 300

    # === 기본적 분석(펀더멘털) 수집 스위치와 장애 대비 보호 ===
    # 전체 스위치; 끄면 not_supported를 돌려주고 기본 흐름은 그대로 유지
    enable_fundamental_pipeline: bool = True
    # 펀더멘털 단계 전체 시간 예산(초)
    fundamental_stage_timeout_seconds: float = FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT
    # 소스 1개 호출 제한 시간(초)
    fundamental_fetch_timeout_seconds: float = 8.0
    # 항목별 실패 시 재시도 횟수(첫 시도 포함)
    fundamental_retry_max: int = 1
    # 펀더멘털 컨텍스트 짧은 TTL(초)
    fundamental_cache_ttl_seconds: int = 120
    # 펀더멘털 캐시 최대 항목 수(오래 실행할 때 메모리 증가 방지)
    fundamental_cache_max_entries: int = 256

    # === Portfolio PR2: import/risk/fx settings ===
    portfolio_risk_concentration_alert_pct: float = 35.0
    portfolio_risk_drawdown_alert_pct: float = 15.0
    portfolio_risk_stop_loss_alert_pct: float = 10.0
    portfolio_risk_stop_loss_near_ratio: float = 0.8
    portfolio_risk_lookback_days: int = 180
    portfolio_fx_update_enabled: bool = True

    # Discord 봇 상태
    discord_bot_status: str = "A股智能分析 | /help"

    # === 요청 속도 제어 설정(차단 방지 핵심 값) ===
    # Akshare 요청 간격 범위(초)
    akshare_sleep_min: float = 2.0
    akshare_sleep_max: float = 5.0
    
    # Tushare 분당 최대 요청 수(무료 한도)
    tushare_rate_limit_per_minute: int = 80
    
    # 재시도 설정
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    
    # === WebUI 설정 ===
    webui_enabled: bool = False
    webui_host: str = "127.0.0.1"
    webui_port: int = 8000
    
    # === 봇 설정 ===
    bot_enabled: bool = True              # 봇 기능 사용 여부
    bot_command_prefix: str = "/"         # 명령어 접두사
    bot_rate_limit_requests: int = 10     # 빈도 제한: 시간 창 안의 최대 요청 수
    bot_rate_limit_window: int = 60       # 빈도 제한: 시간 창 길이(초)
    bot_admin_users: List[str] = field(default_factory=list)  # 관리자 사용자 ID 목록
    
    # Feishu 봇(이벤트 구독) - feishu_app_id, feishu_app_secret 은 위에 있음
    feishu_verification_token: Optional[str] = None  # 이벤트 구독 검증 Token
    feishu_encrypt_key: Optional[str] = None         # 메시지 암호화 키(선택)
    feishu_stream_enabled: bool = False              # Stream 상시 연결 모드 사용 여부(공인 IP 불필요)
    
    # DingTalk 봇
    dingtalk_app_key: Optional[str] = None      # 앱 AppKey
    dingtalk_app_secret: Optional[str] = None   # 앱 AppSecret
    dingtalk_stream_enabled: bool = False       # Stream 모드 사용 여부(공인 IP 불필요)
    
    # WeCom 봇(콜백 모드)
    wecom_corpid: Optional[str] = None              # 기업 ID
    wecom_token: Optional[str] = None               # 콜백 Token
    wecom_encoding_aes_key: Optional[str] = None    # 메시지 암호화/복호화 키
    wecom_agent_id: Optional[str] = None            # 앱 AgentId
    
    # Telegram 봇 - telegram_bot_token, telegram_chat_id 는 위에 있음
    telegram_webhook_secret: Optional[str] = None   # Webhook 비밀 키

    # === 설정 검증 모드 ===
    # CONFIG_VALIDATE_MODE=warn (default): log all issues but always continue startup
    # CONFIG_VALIDATE_MODE=strict: exit(1) when any "error" severity issue is found
    config_validate_mode: str = "warn"

    # --- Post-init validation ---------------------------------------------------
    _VALID_AGENT_ARCH = {"single", "multi"}
    _VALID_ORCHESTRATOR_MODES = {"quick", "standard", "full", "specialist"}
    _VALID_SKILL_ROUTING = {"auto", "manual"}
    _WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS = frozenset(
        {
            "STOCK_LIST",
            "RUN_IMMEDIATELY",
            "SCHEDULE_ENABLED",
            "SCHEDULE_TIME",
            "SCHEDULE_TIMES",
            "SCHEDULE_RUN_IMMEDIATELY",
            # Same startup-key treatment as SCHEDULE_RUN_IMMEDIATELY: a
            # bootstrap process env value (docker -e / compose / shell
            # export) that differs from the persisted .env must win, while
            # a WebUI .env edit still takes effect on reload (PR #2366).
            "SCHEDULE_STARTUP_DEDUP",
        }
    )
    _BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = False
    _BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset()
    _BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset()

    def __post_init__(self) -> None:
        _log = logging.getLogger(__name__)
        if self.agent_arch not in self._VALID_AGENT_ARCH:
            _log.warning(
                "Invalid AGENT_ARCH=%r, falling back to 'single'. Valid: %s",
                self.agent_arch, self._VALID_AGENT_ARCH,
            )
            object.__setattr__(self, "agent_arch", "single")
        if self.agent_orchestrator_mode in {"strategy", "skill"}:
            _log.info(
                "AGENT_ORCHESTRATOR_MODE=%s is deprecated; normalizing to 'specialist'",
                self.agent_orchestrator_mode,
            )
            object.__setattr__(self, "agent_orchestrator_mode", "specialist")
        if self.agent_orchestrator_mode not in self._VALID_ORCHESTRATOR_MODES:
            _log.warning(
                "Invalid AGENT_ORCHESTRATOR_MODE=%r, falling back to 'standard'. Valid: %s",
                self.agent_orchestrator_mode, self._VALID_ORCHESTRATOR_MODES,
            )
            object.__setattr__(self, "agent_orchestrator_mode", "standard")
        if self.agent_skill_routing not in self._VALID_SKILL_ROUTING:
            _log.warning(
                "Invalid AGENT_SKILL_ROUTING=%r, falling back to 'auto'. Valid: %s",
                self.agent_skill_routing, self._VALID_SKILL_ROUTING,
            )
            object.__setattr__(self, "agent_skill_routing", "auto")
        normalized_profile = normalize_agent_context_compression_profile(
            self.agent_context_compression_profile
        )
        if normalized_profile != self.agent_context_compression_profile:
            object.__setattr__(self, "agent_context_compression_profile", normalized_profile)

    # 싱글턴 인스턴스 저장
    _instance: Optional['Config'] = None
    
    @classmethod
    def get_instance(cls) -> 'Config':
        """
        설정 싱글턴 인스턴스 가져오기
        
        싱글턴 패턴이 보장하는 것:
        1. 전역에 설정 인스턴스는 하나뿐
        2. 설정은 환경 변수에서 한 번만 불러옴
        3. 모든 모듈이 같은 설정을 공유
        """
        if cls._instance is None:
            cls._instance = cls._load_from_env()
        return cls._instance
    
    @classmethod
    def _load_from_env(cls) -> 'Config':
        """
        .env 파일에서 설정 불러오기
        
        불러오는 우선순위:
        1. 대부분의 설정은 시스템 환경 변수가 우선
        2. WebUI에서 바꿀 수 있는 실행 중 핵심 키는 저장된 `.env` 값을 먼저 쓰되, 시작할 때 명시한 프로세스 환경 변수의 override는 유지
        3. 코드에 적힌 기본값
        """
        cls._capture_bootstrap_runtime_env_overrides()
        preexisting_report_language = os.environ.get("REPORT_LANGUAGE")

        # 환경 변수가 불러와졌는지 확인
        setup_env()

        # === 스마트 프록시 설정 (중요 수정) ===
        # 프록시를 설정했다면 NO_PROXY를 자동 설정해 중국 내 데이터 소스는 프록시를 거치지 않게 함(시세 수집 실패 방지)
        http_proxy = os.getenv('HTTP_PROXY') or os.getenv('http_proxy')
        if http_proxy:
            # 중국 내 금융 데이터 소스 도메인 목록
            domestic_domains = [
                'eastmoney.com',   # Eastmoney (Efinance/Akshare)
                'sina.com.cn',     # Sina 금융 (Akshare)
                '163.com',         # NetEase 금융 (Akshare)
                'tushare.pro',     # Tushare
                'baostock.com',    # Baostock
                'sse.com.cn',      # 상하이 증권거래소
                'szse.cn',         # 선전 증권거래소
                'csindex.com.cn',  # CSI 지수 회사
                'cninfo.com.cn',   # CNINFO(공시 사이트)
                'localhost',
                '127.0.0.1'
            ]

            # 기존 no_proxy 가져오기
            current_no_proxy = os.getenv('NO_PROXY') or os.getenv('no_proxy') or ''
            existing_domains = current_no_proxy.split(',') if current_no_proxy else []

            # 합치고 중복 제거
            final_domains = list(set(existing_domains + domestic_domains))
            final_no_proxy = ','.join(filter(None, final_domains))

            # 환경 변수 설정 (requests/urllib3/aiohttp 모두 이 설정을 따름)
            os.environ['NO_PROXY'] = final_no_proxy
            os.environ['no_proxy'] = final_no_proxy

            # HTTP_PROXY도 제대로 설정되게 함(.env에만 있고 export 되지 않은 경우 대비)
            os.environ['HTTP_PROXY'] = http_proxy
            os.environ['http_proxy'] = http_proxy

            # HTTPS_PROXY도 마찬가지
            https_proxy = os.getenv('HTTPS_PROXY') or os.getenv('https_proxy')
            if https_proxy:
                os.environ['HTTPS_PROXY'] = https_proxy
                os.environ['https_proxy'] = https_proxy

        
        # 관심종목 목록 해석(쉼표로 구분, 모두 대문자로 통일 Issue #355)
        stock_list_str = cls._resolve_env_value(
            'STOCK_LIST',
            default='',
            prefer_env_file=True,
        )
        stock_list = [
            (c or "").strip().upper()
            for c in split_stock_list(stock_list_str)
            if (c or "").strip()
        ]
        
        # === LiteLLM multi-key parsing ===
        # GEMINI_API_KEYS (comma-separated) > GEMINI_API_KEY (single)
        _gemini_keys_raw = os.getenv('GEMINI_API_KEYS', '')
        gemini_api_keys = [k.strip() for k in _gemini_keys_raw.split(',') if k.strip()]
        _single_gemini = os.getenv('GEMINI_API_KEY', '').strip()
        if not gemini_api_keys and _single_gemini:
            gemini_api_keys = [_single_gemini]

        # ANTHROPIC_API_KEYS > ANTHROPIC_API_KEY
        _anthropic_keys_raw = os.getenv('ANTHROPIC_API_KEYS', '')
        anthropic_api_keys = [k.strip() for k in _anthropic_keys_raw.split(',') if k.strip()]
        _single_anthropic = os.getenv('ANTHROPIC_API_KEY', '').strip()
        if not anthropic_api_keys and _single_anthropic:
            anthropic_api_keys = [_single_anthropic]

        # OPENAI_API_KEYS > AIHUBMIX_KEY > OPENAI_API_KEY
        _aihubmix = os.getenv('AIHUBMIX_KEY', '').strip()
        _openai_keys_raw = os.getenv('OPENAI_API_KEYS', '')
        openai_api_keys = [k.strip() for k in _openai_keys_raw.split(',') if k.strip()]
        if not openai_api_keys:
            _single_openai = os.getenv('OPENAI_API_KEY', '').strip()
            _fallback_key = _aihubmix or _single_openai
            if _fallback_key:
                openai_api_keys = [_fallback_key]
        openai_base_url = os.getenv('OPENAI_BASE_URL') or (
            'https://aihubmix.com/v1' if _aihubmix else None
        )

        # DEEPSEEK_API_KEYS > DEEPSEEK_API_KEY (independent from OpenAI-compatible layer)
        _deepseek_keys_raw = os.getenv('DEEPSEEK_API_KEYS', '')
        deepseek_api_keys = [k.strip() for k in _deepseek_keys_raw.split(',') if k.strip()]
        if not deepseek_api_keys:
            _single_deepseek = os.getenv('DEEPSEEK_API_KEY', '').strip()
            if _single_deepseek:
                deepseek_api_keys = [_single_deepseek]

        # Anspire Open shares the same key as Anspire Search and exposes an
        # OpenAI-compatible LLM gateway.  When no other OpenAI-compatible key is
        # configured, use ANSPIRE_API_KEYS as the legacy openai-compatible
        # provider so "one key" setups work without LLM_CHANNELS.
        anspire_keys_str = os.getenv('ANSPIRE_API_KEYS', '')
        anspire_api_keys = [k.strip() for k in anspire_keys_str.split(',') if k.strip()]
        anspire_llm_enabled = parse_env_bool(os.getenv('ANSPIRE_LLM_ENABLED'), default=True)
        anspire_llm_base_url = (
            os.getenv('ANSPIRE_LLM_BASE_URL') or ANSPIRE_LLM_BASE_URL_DEFAULT
        ).strip()
        _anspire_llm_model_env = os.getenv('ANSPIRE_LLM_MODEL', '').strip()
        anspire_channel_declared = False
        for _raw_channel in os.getenv('LLM_CHANNELS', '').split(','):
            if _raw_channel.strip().lower() != "anspire":
                continue
            anspire_channel_declared = True
            break
        using_anspire_llm_legacy = bool(
            anspire_llm_enabled
            and not anspire_channel_declared
            and anspire_api_keys
            and not openai_api_keys
        )
        if using_anspire_llm_legacy:
            openai_api_keys = list(anspire_api_keys)
            openai_base_url = anspire_llm_base_url

        # LITELLM_MODEL / LITELLM_FALLBACK_MODELS explicit values are recorded
        # before YAML/channels are parsed, but legacy inference is delayed until
        # the higher-priority sources and Hermes blocking issues are known.
        litellm_model_explicit = os.getenv('LITELLM_MODEL', '').strip()
        litellm_model = litellm_model_explicit
        inferred_legacy_deepseek_model = False
        _openai_model_env = os.getenv('OPENAI_MODEL', '').strip()
        if using_anspire_llm_legacy:
            _openai_model_name = _anspire_llm_model_env or _openai_model_env or ANSPIRE_LLM_MODEL_DEFAULT
        else:
            _openai_model_name = _openai_model_env or 'gpt-5.5'

        # LITELLM_FALLBACK_MODELS: comma-separated list of fallback models
        _fallback_str = os.getenv('LITELLM_FALLBACK_MODELS', '')
        litellm_fallback_models_explicit = bool(_fallback_str.strip())
        if _fallback_str.strip():
            litellm_fallback_models = [m.strip() for m in _fallback_str.split(',') if m.strip()]
        else:
            litellm_fallback_models = []

        # === LLM Channels + YAML config ===
        litellm_config_path = os.getenv('LITELLM_CONFIG', '').strip() or None
        llm_models_source = "legacy_env"
        llm_channels: List[Dict[str, Any]] = []
        llm_channel_names: List[str] = []
        llm_channel_config_issues: List[Dict[str, str]] = []
        llm_blocks_legacy_fallback = False
        llm_blocked_hermes_routes: List[str] = []
        llm_model_list: List[Dict[str, Any]] = []

        # Priority 1: LITELLM_CONFIG (standard LiteLLM YAML config file)
        if litellm_config_path:
            llm_model_list = cls._parse_litellm_yaml(litellm_config_path)
            if llm_model_list:
                llm_models_source = "litellm_config"

        # Priority 2: LLM_CHANNELS (env var based channel config)
        if not llm_model_list:
            _channels_str = resolve_llm_channel_names(os.environ)
            if _channels_str:
                llm_channel_names = [
                    ch.strip().lower()
                    for ch in _channels_str.split(',')
                    if ch.strip()
                ]
                (
                    llm_channels,
                    hermes_issues,
                    llm_blocks_legacy_fallback,
                    llm_blocked_hermes_routes,
                ) = cls._parse_llm_channels_with_issues(_channels_str)
                llm_channel_config_issues = [issue.as_dict() for issue in hermes_issues]
                llm_model_list = cls._channels_to_model_list(llm_channels)
                if llm_model_list:
                    llm_models_source = "llm_channels"

        route_models = get_configured_llm_models(llm_model_list)
        if route_models:
            if not litellm_model:
                litellm_model = route_models[0]
            if not litellm_fallback_models and not litellm_fallback_models_explicit and litellm_model:
                _seen = {litellm_model}
                litellm_fallback_models = [
                    model for model in route_models
                    if model not in _seen and not _seen.add(model)  # type: ignore[func-returns-value]
                ]

        # Priority 3: Legacy env vars → auto-build model_list (backward compatible).
        # This is skipped when an explicit invalid Hermes channel blocks legacy fallback.
        if not llm_model_list and not llm_blocks_legacy_fallback:
            llm_model_list = cls._legacy_keys_to_model_list(
                gemini_api_keys, anthropic_api_keys, openai_api_keys,
                openai_base_url,
                deepseek_api_keys,
            )
            if llm_model_list:
                llm_models_source = "legacy_env"

            if not litellm_model:
                _gemini_model_name = os.getenv('GEMINI_MODEL', 'gemini-3.1-pro-preview').strip()
                _anthropic_model_name = os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6').strip()
                if gemini_api_keys:
                    litellm_model = f'gemini/{_gemini_model_name}'
                elif anthropic_api_keys:
                    litellm_model = f'anthropic/{_anthropic_model_name}'
                elif deepseek_api_keys:
                    litellm_model = 'deepseek/deepseek-chat'
                    inferred_legacy_deepseek_model = True
                elif openai_api_keys:
                    # For openai-compatible models, add prefix only if not already prefixed
                    if '/' not in _openai_model_name:
                        litellm_model = f'openai/{_openai_model_name}'
                    else:
                        litellm_model = _openai_model_name

            if not litellm_fallback_models and not litellm_fallback_models_explicit:
                # Backward compat: use gemini_model_fallback when primary is gemini
                _gemini_fallback = os.getenv('GEMINI_MODEL_FALLBACK', 'gemini-3-flash-preview').strip()
                if litellm_model.startswith('gemini/') and _gemini_fallback:
                    _fb = f'gemini/{_gemini_fallback}' if '/' not in _gemini_fallback else _gemini_fallback
                    litellm_fallback_models = [_fb]

        if (
            inferred_legacy_deepseek_model
            and llm_models_source == "legacy_env"
            and litellm_model == 'deepseek/deepseek-chat'
        ):
            logger.warning(
                "Deprecation warning:\n"
                "deepseek-chat will be deprecated on 2026-07-24,\n"
                "please migrate to deepseek-v4-flash."
            )

        generation_backend = (
            os.getenv('GENERATION_BACKEND', LITELLM_BACKEND_ID).strip().lower()
            or LITELLM_BACKEND_ID
        )
        _generation_fallback_raw = os.getenv('GENERATION_FALLBACK_BACKEND')
        if _generation_fallback_raw is None:
            generation_fallback_backend = LITELLM_BACKEND_ID
        else:
            generation_fallback_backend = _generation_fallback_raw.strip().lower()
        agent_generation_backend = (
            os.getenv('AGENT_GENERATION_BACKEND', AUTO_AGENT_BACKEND_ID).strip().lower()
            or AUTO_AGENT_BACKEND_ID
        )
        generation_backend_timeout_seconds = parse_env_int(
            os.getenv('GENERATION_BACKEND_TIMEOUT_SECONDS'),
            DEFAULT_LOCAL_CLI_TIMEOUT_SECONDS,
            field_name='GENERATION_BACKEND_TIMEOUT_SECONDS',
            minimum=1,
            maximum=MAX_LOCAL_CLI_TIMEOUT_SECONDS,
        )
        generation_backend_max_output_bytes = parse_env_int(
            os.getenv('GENERATION_BACKEND_MAX_OUTPUT_BYTES'),
            DEFAULT_LOCAL_CLI_MAX_OUTPUT_BYTES,
            field_name='GENERATION_BACKEND_MAX_OUTPUT_BYTES',
            minimum=1,
            maximum=MAX_LOCAL_CLI_OUTPUT_BYTES,
        )
        generation_backend_max_concurrency = parse_env_int(
            os.getenv('GENERATION_BACKEND_MAX_CONCURRENCY'),
            DEFAULT_GENERATION_BACKEND_MAX_CONCURRENCY,
            field_name='GENERATION_BACKEND_MAX_CONCURRENCY',
            minimum=1,
            maximum=MAX_GENERATION_BACKEND_MAX_CONCURRENCY,
        )
        local_cli_backend_max_concurrency = parse_env_int(
            os.getenv('LOCAL_CLI_BACKEND_MAX_CONCURRENCY'),
            DEFAULT_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
            field_name='LOCAL_CLI_BACKEND_MAX_CONCURRENCY',
            minimum=1,
            maximum=MAX_LOCAL_CLI_BACKEND_MAX_CONCURRENCY,
        )
        opencode_cli_model = (os.getenv('OPENCODE_CLI_MODEL', '') or '').strip()

        agent_litellm_model = normalize_agent_litellm_model(
            os.getenv('AGENT_LITELLM_MODEL', ''),
            configured_models=set(get_configured_llm_models(llm_model_list)),
        )
        agent_context_compression_profile = normalize_agent_context_compression_profile(
            os.getenv('AGENT_CONTEXT_COMPRESSION_PROFILE')
        )
        agent_context_compression_preset = get_agent_context_compression_preset(
            agent_context_compression_profile
        )
        agent_context_compression_trigger_tokens = parse_agent_context_compression_int(
            os.getenv('AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS'),
            agent_context_compression_preset.trigger_tokens,
            field_name='AGENT_CONTEXT_COMPRESSION_TRIGGER_TOKENS',
            minimum=1000,
            maximum=200000,
        )
        agent_context_protected_turns = parse_agent_context_compression_int(
            os.getenv('AGENT_CONTEXT_PROTECTED_TURNS'),
            agent_context_compression_preset.protected_turns,
            field_name='AGENT_CONTEXT_PROTECTED_TURNS',
            minimum=1,
            maximum=20,
        )

        # 검색 엔진 API Keys 해석(여러 key 가능, 쉼표로 구분)
        bocha_keys_str = os.getenv('BOCHA_API_KEYS', '')
        bocha_api_keys = [k.strip() for k in bocha_keys_str.split(',') if k.strip()]

        minimax_keys_str = os.getenv('MINIMAX_API_KEYS', '')
        minimax_api_keys = [k.strip() for k in minimax_keys_str.split(',') if k.strip()]
        
        tavily_keys_str = os.getenv('TAVILY_API_KEYS', '')
        tavily_api_keys = [k.strip() for k in tavily_keys_str.split(',') if k.strip()]
        
        serpapi_keys_str = os.getenv('SERPAPI_API_KEYS', '')
        serpapi_keys = [k.strip() for k in serpapi_keys_str.split(',') if k.strip()]

        brave_keys_str = os.getenv('BRAVE_API_KEYS', '')
        brave_api_keys = [k.strip() for k in brave_keys_str.split(',') if k.strip()]

        _raw_urls = [u.strip() for u in os.getenv('SEARXNG_BASE_URLS', '').split(',') if u.strip()]
        searxng_base_urls = []
        invalid_searxng_urls = []
        for u in _raw_urls:
            p = urlparse(u)
            if p.scheme in ('http', 'https') and p.netloc:
                searxng_base_urls.append(u)
            else:
                invalid_searxng_urls.append(u)
        if invalid_searxng_urls:
            logger.warning(
                "SEARXNG_BASE_URLS 에 잘못된 URL이 있어 무시함: %s",
                ", ".join(invalid_searxng_urls[:3]),
            )
        searxng_public_instances_enabled = parse_env_bool(
            os.getenv('SEARXNG_PUBLIC_INSTANCES_ENABLED'),
            default=False,
        )

        # WeCom 메시지 종류와 최대 바이트 수 처리
        wechat_msg_type = os.getenv('WECHAT_MSG_TYPE', 'markdown')
        wechat_msg_type_lower = wechat_msg_type.lower()
        wechat_max_bytes_env = os.getenv('WECHAT_MAX_BYTES')
        if wechat_max_bytes_env not in (None, ''):
            wechat_max_bytes = parse_env_int(
                wechat_max_bytes_env,
                2048 if wechat_msg_type_lower == 'text' else 4000,
                field_name='WECHAT_MAX_BYTES',
                minimum=1,
            )
        else:
            # 따로 설정하지 않았으면 메시지 종류에 따라 기본 바이트 수 선택
            wechat_max_bytes = 2048 if wechat_msg_type_lower == 'text' else 4000

        # Preserve historical semantics for startup flags: only an explicit
        # literal "true" enables immediate execution; empty strings stay False.
        legacy_run_immediately_env = cls._resolve_env_value(
            'RUN_IMMEDIATELY',
            prefer_env_file=True,
        )
        legacy_run_immediately = (
            legacy_run_immediately_env.lower() == 'true'
            if legacy_run_immediately_env is not None
            else True
        )

        schedule_run_immediately_env = cls._resolve_env_value(
            'SCHEDULE_RUN_IMMEDIATELY',
            prefer_env_file=True,
        )
        # Keep backward compatibility for container/process overrides:
        # when RUN_IMMEDIATELY is explicitly provided by the runtime but the
        # schedule-specific alias is absent, schedule mode should inherit the
        # legacy process value instead of being pulled back to the persisted
        # `.env` copy of SCHEDULE_RUN_IMMEDIATELY.
        if (
            not cls._had_bootstrap_runtime_env_key('SCHEDULE_RUN_IMMEDIATELY')
            and cls._has_bootstrap_runtime_env_override('RUN_IMMEDIATELY')
        ):
            schedule_run_immediately = legacy_run_immediately
        else:
            schedule_run_immediately = (
                schedule_run_immediately_env.lower() == 'true'
                if schedule_run_immediately_env is not None
                else legacy_run_immediately
            )
        # Startup-immediate run daily dedup switch (schedule mode only).
        # Unset keeps the dedup enabled; explicit "false" restores the
        # upstream "run on every startup" behavior.
        schedule_startup_dedup_env = cls._resolve_env_value(
            'SCHEDULE_STARTUP_DEDUP',
            prefer_env_file=True,
        )
        schedule_startup_dedup = (
            schedule_startup_dedup_env.lower() == 'true'
            if schedule_startup_dedup_env is not None
            else True
        )
        schedule_time_value = cls._resolve_env_value(
            'SCHEDULE_TIME',
            default='18:00',
            prefer_env_file=True,
        )
        schedule_times_value = cls._resolve_env_value(
            'SCHEDULE_TIMES',
            default='',
            prefer_env_file=True,
        )

        report_language_raw = cls._resolve_report_language_env_value(
            preexisting_report_language
        )
        report_show_llm_model_raw = os.getenv('REPORT_SHOW_LLM_MODEL')
        report_show_llm_model = parse_env_bool(report_show_llm_model_raw, default=True)
        if report_show_llm_model_raw is not None and not report_show_llm_model_raw.strip():
            report_show_llm_model = False

        return cls(
            stock_list=stock_list,
            feishu_app_id=os.getenv('FEISHU_APP_ID'),
            feishu_app_secret=os.getenv('FEISHU_APP_SECRET'),
            feishu_folder_token=os.getenv('FEISHU_FOLDER_TOKEN'),
            tushare_token=os.getenv('TUSHARE_TOKEN'),
            tickflow_api_key=os.getenv('TICKFLOW_API_KEY'),
            tickflow_kline_adjust=normalize_tickflow_kline_adjust(os.getenv('TICKFLOW_KLINE_ADJUST')),
            tickflow_priority=parse_env_int(os.getenv('TICKFLOW_PRIORITY'), 2, field_name='TICKFLOW_PRIORITY', minimum=0),
            tickflow_batch_daily_enabled=parse_env_bool(os.getenv('TICKFLOW_BATCH_DAILY_ENABLED'), default=True),
            tickflow_batch_size=parse_env_int(os.getenv('TICKFLOW_BATCH_SIZE'), 100, field_name='TICKFLOW_BATCH_SIZE', minimum=1),
            futu_opend_host=os.getenv('FUTU_OPEND_HOST') or None,
            futu_opend_port=parse_env_int(os.getenv('FUTU_OPEND_PORT'), 11111, field_name='FUTU_OPEND_PORT', minimum=1, maximum=65535),
            futu_hk_realtime_source_priority=os.getenv('FUTU_HK_REALTIME_SOURCE_PRIORITY', 'futu,longbridge,akshare,yfinance'),
            mx_apikey=os.getenv('MX_APIKEY') or None,
            mx_priority=parse_env_int(os.getenv('MX_PRIORITY'), 6, field_name='MX_PRIORITY', minimum=0),
            finnhub_api_key=os.getenv('FINNHUB_API_KEY') or None,
            alphavantage_api_key=os.getenv('ALPHAVANTAGE_API_KEY') or None,
            longbridge_app_key=os.getenv('LONGBRIDGE_APP_KEY') or None,
            longbridge_app_secret=os.getenv('LONGBRIDGE_APP_SECRET') or None,
            longbridge_access_token=os.getenv('LONGBRIDGE_ACCESS_TOKEN') or None,
            longbridge_oauth_client_id=os.getenv('LONGBRIDGE_OAUTH_CLIENT_ID') or None,
            stock_index_remote_update_enabled=parse_env_bool(
                os.getenv('STOCK_INDEX_REMOTE_UPDATE_ENABLED'),
                default=True,
            ),
            generation_backend=generation_backend,
            generation_fallback_backend=generation_fallback_backend,
            generation_backend_timeout_seconds=generation_backend_timeout_seconds,
            generation_backend_max_output_bytes=generation_backend_max_output_bytes,
            generation_backend_max_concurrency=generation_backend_max_concurrency,
            local_cli_backend_max_concurrency=local_cli_backend_max_concurrency,
            opencode_cli_model=opencode_cli_model,
            litellm_model=litellm_model,
            litellm_fallback_models=litellm_fallback_models,
            llm_temperature=resolve_unified_llm_temperature(litellm_model),
            litellm_config_path=litellm_config_path,
            llm_models_source=llm_models_source,
            llm_channels=llm_channels,
            llm_channel_names=llm_channel_names,
            llm_channel_config_issues=llm_channel_config_issues,
            llm_blocks_legacy_fallback=llm_blocks_legacy_fallback,
            llm_blocked_hermes_routes=llm_blocked_hermes_routes,
            llm_model_list=llm_model_list,
            llm_prompt_cache_telemetry_enabled=parse_env_bool(
                os.getenv("LLM_PROMPT_CACHE_TELEMETRY_ENABLED"),
                default=True,
            ),
            llm_prompt_cache_hints_enabled=parse_env_bool(
                os.getenv("LLM_PROMPT_CACHE_HINTS_ENABLED"),
                default=False,
            ),
            llm_prompt_cache_diagnostics_level=parse_prompt_cache_diagnostics_level(
                os.getenv("LLM_PROMPT_CACHE_DIAGNOSTICS_LEVEL")
            ),
            gemini_api_keys=gemini_api_keys,
            anthropic_api_keys=anthropic_api_keys,
            openai_api_keys=openai_api_keys,
            deepseek_api_keys=deepseek_api_keys,
            gemini_api_key=os.getenv('GEMINI_API_KEY'),
            gemini_model=os.getenv('GEMINI_MODEL', 'gemini-3.1-pro-preview'),
            gemini_model_fallback=os.getenv('GEMINI_MODEL_FALLBACK', 'gemini-3-flash-preview'),
            gemini_temperature=parse_env_float(os.getenv('GEMINI_TEMPERATURE'), 0.7, field_name='GEMINI_TEMPERATURE'),
            gemini_request_delay=parse_env_float(os.getenv('GEMINI_REQUEST_DELAY'), 2.0, field_name='GEMINI_REQUEST_DELAY', minimum=0.0),
            gemini_max_retries=parse_env_int(os.getenv('GEMINI_MAX_RETRIES'), 5, field_name='GEMINI_MAX_RETRIES', minimum=0),
            gemini_retry_delay=parse_env_float(os.getenv('GEMINI_RETRY_DELAY'), 5.0, field_name='GEMINI_RETRY_DELAY', minimum=0.0),
            anthropic_api_key=os.getenv('ANTHROPIC_API_KEY'),
            anthropic_model=os.getenv('ANTHROPIC_MODEL', 'claude-sonnet-4-6'),
            anthropic_temperature=parse_env_float(os.getenv('ANTHROPIC_TEMPERATURE'), 0.7, field_name='ANTHROPIC_TEMPERATURE'),
            anthropic_max_tokens=parse_env_int(os.getenv('ANTHROPIC_MAX_TOKENS'), 8192, field_name='ANTHROPIC_MAX_TOKENS', minimum=1),
            # AIHubmix is the preferred OpenAI-compatible provider (one key, all models, no VPN required).
            # Within the OpenAI-compatible layer: AIHUBMIX_KEY takes priority over OPENAI_API_KEY.
            # Overall provider fallback order: Gemini > Anthropic > OpenAI-compatible (incl. AIHubmix).
            # base_url is auto-set to aihubmix.com/v1 when AIHUBMIX_KEY is used and no explicit
            # OPENAI_BASE_URL override is provided.
            # Model names match upstream (e.g. gemini-3.1-pro-preview, gpt-5.5, deepseek-v4-flash).
            openai_api_key=openai_api_keys[0] if openai_api_keys else None,
            openai_base_url=openai_base_url,
            openai_model=_openai_model_name,
            openai_vision_model=os.getenv('OPENAI_VISION_MODEL') or None,
            openai_temperature=parse_env_float(os.getenv('OPENAI_TEMPERATURE'), 0.7, field_name='OPENAI_TEMPERATURE'),
            # Vision model: VISION_MODEL > OPENAI_VISION_MODEL (alias) > default
            vision_model=(
                os.getenv('VISION_MODEL')
                or os.getenv('OPENAI_VISION_MODEL')
                or ""
            ),
            vision_provider_priority=os.getenv('VISION_PROVIDER_PRIORITY', 'gemini,anthropic,openai'),
            anspire_api_keys=anspire_api_keys,
            bocha_api_keys=bocha_api_keys,
            minimax_api_keys=minimax_api_keys,
            tavily_api_keys=tavily_api_keys,
            brave_api_keys=brave_api_keys,
            serpapi_keys=serpapi_keys,
            searxng_base_urls=searxng_base_urls,
            searxng_public_instances_enabled=searxng_public_instances_enabled,
            searxng_timeout_seconds=parse_env_int(
                os.getenv('SEARXNG_TIMEOUT_SECONDS'), 10, field_name='SEARXNG_TIMEOUT_SECONDS', minimum=1
            ),
            social_sentiment_api_key=os.getenv('SOCIAL_SENTIMENT_API_KEY') or None,
            social_sentiment_api_url=os.getenv('SOCIAL_SENTIMENT_API_URL', 'https://api.adanos.org').rstrip('/'),
            news_max_age_days=parse_env_int(os.getenv('NEWS_MAX_AGE_DAYS'), 3, field_name='NEWS_MAX_AGE_DAYS', minimum=1),
            news_strategy_profile=cls._parse_news_strategy_profile(
                os.getenv('NEWS_STRATEGY_PROFILE', 'short')
            ),
            news_intel_retention_days=parse_env_int(
                os.getenv('NEWS_INTEL_RETENTION_DAYS'),
                30,
                field_name='NEWS_INTEL_RETENTION_DAYS',
                minimum=1,
                maximum=365,
            ),
            news_intel_fetch_timeout_sec=parse_env_float(
                os.getenv('NEWS_INTEL_FETCH_TIMEOUT_SEC'),
                8.0,
                field_name='NEWS_INTEL_FETCH_TIMEOUT_SEC',
                minimum=1.0,
                maximum=30.0,
            ),
            news_intel_max_items_per_source=parse_env_int(
                os.getenv('NEWS_INTEL_MAX_ITEMS_PER_SOURCE'),
                50,
                field_name='NEWS_INTEL_MAX_ITEMS_PER_SOURCE',
                minimum=1,
                maximum=200,
            ),
            news_intel_auto_fetch_enabled=parse_env_bool(
                os.getenv('NEWS_INTEL_AUTO_FETCH_ENABLED'),
                False,
            ),
            newsnow_base_url=((os.getenv('NEWSNOW_BASE_URL') or '').strip().rstrip('/') or 'https://newsnow.busiyi.world'),
            bias_threshold=parse_env_float(os.getenv('BIAS_THRESHOLD'), 5.0, field_name='BIAS_THRESHOLD', minimum=1.0),
            agent_backend=(os.getenv('AGENT_BACKEND', 'auto') or 'auto').strip().lower(),
            agent_generation_backend=agent_generation_backend,
            agent_litellm_model=agent_litellm_model,
            agent_mode=os.getenv('AGENT_MODE', 'false').lower() == 'true',
            _agent_mode_explicit=os.getenv('AGENT_MODE') is not None,
            agent_max_steps=parse_env_int(
                os.getenv('AGENT_MAX_STEPS'),
                AGENT_MAX_STEPS_DEFAULT,
                field_name='AGENT_MAX_STEPS',
                minimum=1,
            ),
            agent_skills=[s.strip() for s in os.getenv('AGENT_SKILLS', '').split(',') if s.strip()],
            agent_skill_dir=os.getenv('AGENT_SKILL_DIR') or os.getenv('AGENT_STRATEGY_DIR'),
            agent_nl_routing=os.getenv('AGENT_NL_ROUTING', 'false').lower() == 'true',
            agent_arch=os.getenv('AGENT_ARCH', 'single').lower(),
            agent_orchestrator_mode=os.getenv('AGENT_ORCHESTRATOR_MODE', 'standard').lower(),
            agent_orchestrator_timeout_s=parse_env_int(
                os.getenv('AGENT_ORCHESTRATOR_TIMEOUT_S'),
                600,
                field_name='AGENT_ORCHESTRATOR_TIMEOUT_S',
                minimum=0,
            ),
            agent_technical_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_TECHNICAL_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_TECHNICAL_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_intel_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_INTEL_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_INTEL_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_risk_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_RISK_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_RISK_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_decision_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_DECISION_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_DECISION_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_portfolio_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_PORTFOLIO_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_PORTFOLIO_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_skill_agent_timeout_s=parse_env_float(
                os.getenv('AGENT_SKILL_AGENT_TIMEOUT_S'), 0,
                field_name='AGENT_SKILL_AGENT_TIMEOUT_S', minimum=0,
            ),
            agent_data_tool_timeout_s=parse_env_float(
                os.getenv('AGENT_DATA_TOOL_TIMEOUT_S'), 0.0,
                field_name='AGENT_DATA_TOOL_TIMEOUT_S', minimum=0.0,
            ),
            agent_search_tool_timeout_s=parse_env_float(
                os.getenv('AGENT_SEARCH_TOOL_TIMEOUT_S'), 0.0,
                field_name='AGENT_SEARCH_TOOL_TIMEOUT_S', minimum=0.0,
            ),
            agent_analysis_tool_timeout_s=parse_env_float(
                os.getenv('AGENT_ANALYSIS_TOOL_TIMEOUT_S'), 0.0,
                field_name='AGENT_ANALYSIS_TOOL_TIMEOUT_S', minimum=0.0,
            ),
            agent_action_tool_timeout_s=parse_env_float(
                os.getenv('AGENT_ACTION_TOOL_TIMEOUT_S'), 0.0,
                field_name='AGENT_ACTION_TOOL_TIMEOUT_S', minimum=0.0,
            ),
            agent_skill_concurrency=parse_env_int(
                os.getenv('AGENT_SKILL_CONCURRENCY'),
                3,
                field_name='AGENT_SKILL_CONCURRENCY',
                minimum=1,
                maximum=4,
            ),
            agent_risk_override=os.getenv('AGENT_RISK_OVERRIDE', 'true').lower() == 'true',
            agent_deep_research_budget=parse_env_int(
                os.getenv('AGENT_DEEP_RESEARCH_BUDGET'),
                30000,
                field_name='AGENT_DEEP_RESEARCH_BUDGET',
                minimum=5000,
            ),
            agent_deep_research_timeout=parse_env_int(
                os.getenv('AGENT_DEEP_RESEARCH_TIMEOUT'),
                180,
                field_name='AGENT_DEEP_RESEARCH_TIMEOUT',
                minimum=30,
            ),
            agent_memory_enabled=os.getenv('AGENT_MEMORY_ENABLED', 'false').lower() == 'true',
            agent_skill_autoweight=(
                os.getenv('AGENT_SKILL_AUTOWEIGHT')
                or os.getenv('AGENT_STRATEGY_AUTOWEIGHT', 'true')
            ).lower() == 'true',
            agent_skill_routing=(
                os.getenv('AGENT_SKILL_ROUTING')
                or os.getenv('AGENT_STRATEGY_ROUTING', 'auto')
            ).lower(),
            agent_context_compression_enabled=parse_env_bool(
                os.getenv('AGENT_CONTEXT_COMPRESSION_ENABLED'),
                default=False,
            ),
            agent_context_compression_profile=agent_context_compression_profile,
            agent_context_compression_trigger_tokens=agent_context_compression_trigger_tokens,
            agent_context_protected_turns=agent_context_protected_turns,
            agent_event_monitor_enabled=os.getenv('AGENT_EVENT_MONITOR_ENABLED', 'false').lower() == 'true',
            agent_event_monitor_interval_minutes=parse_env_int(
                os.getenv('AGENT_EVENT_MONITOR_INTERVAL_MINUTES'),
                5,
                field_name='AGENT_EVENT_MONITOR_INTERVAL_MINUTES',
                minimum=1,
            ),
            agent_event_alert_rules_json=os.getenv('AGENT_EVENT_ALERT_RULES_JSON', ''),
            wechat_webhook_url=os.getenv('WECHAT_WEBHOOK_URL'),
            feishu_webhook_url=os.getenv('FEISHU_WEBHOOK_URL'),
            feishu_webhook_secret=os.getenv('FEISHU_WEBHOOK_SECRET'),
            feishu_webhook_keyword=os.getenv('FEISHU_WEBHOOK_KEYWORD'),
            dingtalk_webhook_url=os.getenv('DINGTALK_WEBHOOK_URL'),
            dingtalk_secret=os.getenv('DINGTALK_SECRET'),
            

            feishu_chat_id=os.getenv('FEISHU_CHAT_ID'),
            feishu_receive_id_type=os.getenv('FEISHU_RECEIVE_ID_TYPE', 'chat_id'),
            feishu_domain=os.getenv('FEISHU_DOMAIN', 'feishu'),
            telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN'),
            telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID'),
            telegram_message_thread_id=os.getenv('TELEGRAM_MESSAGE_THREAD_ID'),
            email_sender=os.getenv('EMAIL_SENDER'),
            email_sender_name=os.getenv('EMAIL_SENDER_NAME', 'daily_stock_analysis股票分析助手'),
            email_password=os.getenv('EMAIL_PASSWORD'),
            email_receivers=[r.strip() for r in os.getenv('EMAIL_RECEIVERS', '').split(',') if r.strip()],
            stock_email_groups=cls._parse_stock_email_groups(),
            pushover_user_key=os.getenv('PUSHOVER_USER_KEY'),
            pushover_api_token=os.getenv('PUSHOVER_API_TOKEN'),
            ntfy_url=os.getenv('NTFY_URL'),
            ntfy_token=os.getenv('NTFY_TOKEN'),
            gotify_url=os.getenv('GOTIFY_URL'),
            gotify_token=os.getenv('GOTIFY_TOKEN'),
            pushplus_token=os.getenv('PUSHPLUS_TOKEN'),
            pushplus_topic=os.getenv('PUSHPLUS_TOPIC'),
            serverchan3_sendkey=os.getenv('SERVERCHAN3_SENDKEY'),
            custom_webhook_urls=[u.strip() for u in os.getenv('CUSTOM_WEBHOOK_URLS', '').split(',') if u.strip()],
            custom_webhook_bearer_token=os.getenv('CUSTOM_WEBHOOK_BEARER_TOKEN'),
            custom_webhook_body_template=unescape_compose_sensitive_env_value(
                'CUSTOM_WEBHOOK_BODY_TEMPLATE',
                os.getenv('CUSTOM_WEBHOOK_BODY_TEMPLATE') or '',
            ) or None,
            webhook_verify_ssl=os.getenv('WEBHOOK_VERIFY_SSL', 'true').lower() == 'true',
            discord_bot_token=os.getenv('DISCORD_BOT_TOKEN'),
            discord_main_channel_id=(
                os.getenv('DISCORD_MAIN_CHANNEL_ID')
                or os.getenv('DISCORD_CHANNEL_ID')
            ),
            discord_webhook_url=os.getenv('DISCORD_WEBHOOK_URL'),
            discord_interactions_public_key=os.getenv('DISCORD_INTERACTIONS_PUBLIC_KEY'),
            slack_webhook_url=os.getenv('SLACK_WEBHOOK_URL'),
            slack_bot_token=os.getenv('SLACK_BOT_TOKEN'),
            slack_channel_id=os.getenv('SLACK_CHANNEL_ID'),
            astrbot_url=os.getenv('ASTRBOT_URL'),
            astrbot_token=os.getenv('ASTRBOT_TOKEN'),
            notification_report_channels=parse_notification_route_channels(
                os.getenv('NOTIFICATION_REPORT_CHANNELS')
            ),
            notification_alert_channels=parse_notification_route_channels(
                os.getenv('NOTIFICATION_ALERT_CHANNELS')
            ),
            notification_system_error_channels=parse_notification_route_channels(
                os.getenv('NOTIFICATION_SYSTEM_ERROR_CHANNELS')
            ),
            notification_dedup_ttl_seconds=parse_env_int(
                os.getenv('NOTIFICATION_DEDUP_TTL_SECONDS'),
                0,
                field_name='NOTIFICATION_DEDUP_TTL_SECONDS',
                minimum=0,
            ),
            notification_cooldown_seconds=parse_env_int(
                os.getenv('NOTIFICATION_COOLDOWN_SECONDS'),
                0,
                field_name='NOTIFICATION_COOLDOWN_SECONDS',
                minimum=0,
            ),
            notification_quiet_hours=(os.getenv('NOTIFICATION_QUIET_HOURS') or '').strip(),
            notification_timezone=(os.getenv('NOTIFICATION_TIMEZONE') or '').strip(),
            notification_min_severity=(os.getenv('NOTIFICATION_MIN_SEVERITY') or '').strip().lower(),
            notification_daily_digest_enabled=parse_env_bool(
                os.getenv('NOTIFICATION_DAILY_DIGEST_ENABLED'),
                default=False,
            ),
            single_stock_notify=os.getenv('SINGLE_STOCK_NOTIFY', 'false').lower() == 'true',
            report_type=cls._parse_report_type(os.getenv('REPORT_TYPE', 'simple')),
            report_language=cls._parse_report_language(report_language_raw),
            report_summary_only=os.getenv('REPORT_SUMMARY_ONLY', 'false').lower() == 'true',
            report_show_llm_model=report_show_llm_model,
            report_templates_dir=os.getenv('REPORT_TEMPLATES_DIR', 'templates'),
            report_renderer_enabled=os.getenv('REPORT_RENDERER_ENABLED', 'false').lower() == 'true',
            report_integrity_enabled=os.getenv('REPORT_INTEGRITY_ENABLED', 'true').lower() == 'true',
            report_integrity_retry=parse_env_int(os.getenv('REPORT_INTEGRITY_RETRY'), 1, field_name='REPORT_INTEGRITY_RETRY', minimum=0),
            report_history_compare_n=parse_env_int(os.getenv('REPORT_HISTORY_COMPARE_N'), 0, field_name='REPORT_HISTORY_COMPARE_N', minimum=0),
            analysis_delay=parse_env_float(os.getenv('ANALYSIS_DELAY'), 0.0, field_name='ANALYSIS_DELAY', minimum=0.0),
            merge_email_notification=os.getenv('MERGE_EMAIL_NOTIFICATION', 'false').lower() == 'true',
            feishu_max_bytes=parse_env_int(os.getenv('FEISHU_MAX_BYTES'), 20000, field_name='FEISHU_MAX_BYTES', minimum=1),
            feishu_send_as_file=os.getenv('FEISHU_SEND_AS_FILE', '').lower() in ('true', '1', 'yes'),
            wechat_max_bytes=wechat_max_bytes,
            wechat_msg_type=wechat_msg_type_lower,
            discord_max_words=parse_env_int(os.getenv('DISCORD_MAX_WORDS'), 2000, field_name='DISCORD_MAX_WORDS', minimum=1),
            markdown_to_image_channels=[
                c.strip().lower()
                for c in os.getenv('MARKDOWN_TO_IMAGE_CHANNELS', '').split(',')
                if c.strip()
            ],
            markdown_to_image_max_chars=parse_env_int(
                os.getenv('MARKDOWN_TO_IMAGE_MAX_CHARS'),
                15000,
                field_name='MARKDOWN_TO_IMAGE_MAX_CHARS',
                minimum=1,
            ),
            md2img_engine=cls._parse_md2img_engine(os.getenv('MD2IMG_ENGINE', 'wkhtmltoimage')),
            share_image_xiaohongshu_url=(os.getenv('SHARE_IMAGE_XIAOHONGSHU_URL') or '').strip() or None,
            share_image_xiaohongshu_handle=(os.getenv('SHARE_IMAGE_XIAOHONGSHU_HANDLE') or '').strip() or None,
            share_image_xiaohongshu_id=(os.getenv('SHARE_IMAGE_XIAOHONGSHU_ID') or '').strip() or None,
            share_image_xiaohongshu_qr_path=(os.getenv('SHARE_IMAGE_XIAOHONGSHU_QR_PATH') or '').strip() or None,
            prefetch_realtime_quotes=os.getenv('PREFETCH_REALTIME_QUOTES', 'true').lower() == 'true',
            database_path=os.getenv('DATABASE_PATH', './data/stock_analysis.db'),
            sqlite_wal_enabled=os.getenv('SQLITE_WAL_ENABLED', 'true').lower() == 'true',
            sqlite_busy_timeout_ms=parse_env_int(
                os.getenv('SQLITE_BUSY_TIMEOUT_MS'),
                5000,
                field_name='SQLITE_BUSY_TIMEOUT_MS',
                minimum=0,
            ),
            sqlite_write_retry_max=parse_env_int(
                os.getenv('SQLITE_WRITE_RETRY_MAX'),
                3,
                field_name='SQLITE_WRITE_RETRY_MAX',
                minimum=0,
            ),
            sqlite_write_retry_base_delay=parse_env_float(
                os.getenv('SQLITE_WRITE_RETRY_BASE_DELAY'),
                0.1,
                field_name='SQLITE_WRITE_RETRY_BASE_DELAY',
                minimum=0.0,
            ),
            save_context_snapshot=os.getenv('SAVE_CONTEXT_SNAPSHOT', 'true').lower() == 'true',
            backtest_enabled=os.getenv('BACKTEST_ENABLED', 'true').lower() == 'true',
            backtest_eval_window_days=parse_env_int(os.getenv('BACKTEST_EVAL_WINDOW_DAYS'), 10, field_name='BACKTEST_EVAL_WINDOW_DAYS', minimum=1),
            backtest_min_age_days=parse_env_int(os.getenv('BACKTEST_MIN_AGE_DAYS'), 14, field_name='BACKTEST_MIN_AGE_DAYS', minimum=1),
            backtest_engine_version=os.getenv('BACKTEST_ENGINE_VERSION', 'v1'),
            backtest_neutral_band_pct=parse_env_float(
                os.getenv('BACKTEST_NEUTRAL_BAND_PCT'),
                2.0,
                field_name='BACKTEST_NEUTRAL_BAND_PCT',
                minimum=0.0,
            ),
            etf_rotation_pool=cls._parse_etf_rotation_pool(os.getenv('ETF_ROTATION_POOL')),
            etf_rotation_safe_asset=(
                os.getenv('ETF_ROTATION_SAFE_ASSET', DEFAULT_ETF_ROTATION_SAFE_ASSET) or ''
            ).strip(),
            etf_rotation_lookback_days=parse_env_int(
                os.getenv('ETF_ROTATION_LOOKBACK_DAYS'), 60,
                field_name='ETF_ROTATION_LOOKBACK_DAYS', minimum=5, maximum=500,
            ),
            etf_rotation_rebalance=cls._parse_etf_rotation_rebalance(os.getenv('ETF_ROTATION_REBALANCE')),
            etf_rotation_top_n=parse_env_int(
                os.getenv('ETF_ROTATION_TOP_N'), 2,
                field_name='ETF_ROTATION_TOP_N', minimum=1, maximum=10,
            ),
            etf_rotation_switch_buffer_pct=parse_env_float(
                os.getenv('ETF_ROTATION_SWITCH_BUFFER_PCT'), 2.0,
                field_name='ETF_ROTATION_SWITCH_BUFFER_PCT', minimum=0.0, maximum=50.0,
            ),
            etf_rotation_cost_bps=parse_env_float(
                os.getenv('ETF_ROTATION_COST_BPS'), 10.0,
                field_name='ETF_ROTATION_COST_BPS', minimum=0.0, maximum=500.0,
            ),
            etf_rotation_backtest_years=parse_env_int(
                os.getenv('ETF_ROTATION_BACKTEST_YEARS'), 8,
                field_name='ETF_ROTATION_BACKTEST_YEARS', minimum=1, maximum=30,
            ),
            log_dir=os.getenv('LOG_DIR', './logs'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
            max_workers=parse_env_int(os.getenv('MAX_WORKERS'), 3, field_name='MAX_WORKERS', minimum=1),
            debug=os.getenv('DEBUG', 'false').lower() == 'true',
            config_validate_mode=os.getenv('CONFIG_VALIDATE_MODE', 'warn').lower(),
            http_proxy=os.getenv('HTTP_PROXY'),
            https_proxy=os.getenv('HTTPS_PROXY'),
            schedule_enabled=cls._resolve_env_value(
                'SCHEDULE_ENABLED',
                default='false',
                prefer_env_file=True,
            ).lower() == 'true',
            schedule_time=(schedule_time_value or '18:00').strip() or '18:00',
            schedule_times=normalize_schedule_times(
                schedule_times_value,
                fallback_time=(schedule_time_value or '18:00').strip() or '18:00',
            ),
            schedule_run_immediately=schedule_run_immediately,
            schedule_startup_dedup=schedule_startup_dedup,
            run_immediately=legacy_run_immediately,
            market_review_enabled=os.getenv('MARKET_REVIEW_ENABLED', 'true').lower() == 'true',
            daily_market_context_enabled=os.getenv('DAILY_MARKET_CONTEXT_ENABLED', 'true').lower() == 'true',
            market_review_region=cls._parse_market_review_region(
                os.getenv('MARKET_REVIEW_REGION', 'cn')
            ),
            market_review_color_scheme=cls._parse_market_review_color_scheme(
                os.getenv('MARKET_REVIEW_COLOR_SCHEME', 'green_up')
            ),
            trading_day_check_enabled=os.getenv('TRADING_DAY_CHECK_ENABLED', 'true').lower() != 'false',
            webui_enabled=os.getenv('WEBUI_ENABLED', 'false').lower() == 'true',
            webui_host=os.getenv('WEBUI_HOST', '127.0.0.1'),
            webui_port=parse_env_int(os.getenv('WEBUI_PORT'), 8000, field_name='WEBUI_PORT', minimum=1, maximum=65535),
            # 봇 설정
            bot_enabled=os.getenv('BOT_ENABLED', 'true').lower() == 'true',
            bot_command_prefix=os.getenv('BOT_COMMAND_PREFIX', '/'),
            bot_rate_limit_requests=parse_env_int(os.getenv('BOT_RATE_LIMIT_REQUESTS'), 10, field_name='BOT_RATE_LIMIT_REQUESTS', minimum=1),
            bot_rate_limit_window=parse_env_int(os.getenv('BOT_RATE_LIMIT_WINDOW'), 60, field_name='BOT_RATE_LIMIT_WINDOW', minimum=1),
            bot_admin_users=[u.strip() for u in os.getenv('BOT_ADMIN_USERS', '').split(',') if u.strip()],
            # Feishu 봇
            feishu_verification_token=os.getenv('FEISHU_VERIFICATION_TOKEN'),
            feishu_encrypt_key=os.getenv('FEISHU_ENCRYPT_KEY'),
            feishu_stream_enabled=os.getenv('FEISHU_STREAM_ENABLED', 'false').lower() == 'true',
            # DingTalk 봇
            dingtalk_app_key=os.getenv('DINGTALK_APP_KEY'),
            dingtalk_app_secret=os.getenv('DINGTALK_APP_SECRET'),
            dingtalk_stream_enabled=os.getenv('DINGTALK_STREAM_ENABLED', 'false').lower() == 'true',
            # WeCom 봇
            wecom_corpid=os.getenv('WECOM_CORPID'),
            wecom_token=os.getenv('WECOM_TOKEN'),
            wecom_encoding_aes_key=os.getenv('WECOM_ENCODING_AES_KEY'),
            wecom_agent_id=os.getenv('WECOM_AGENT_ID'),
            # Telegram
            telegram_webhook_secret=os.getenv('TELEGRAM_WEBHOOK_SECRET'),
            # Discord 봇 추가 설정
            discord_bot_status=os.getenv('DISCORD_BOT_STATUS', 'A股智能分析 | /help'),
            # 실시간 시세 보강 데이터 설정
            enable_realtime_quote=os.getenv('ENABLE_REALTIME_QUOTE', 'true').lower() == 'true',
            enable_realtime_technical_indicators=os.getenv(
                'ENABLE_REALTIME_TECHNICAL_INDICATORS', 'true'
            ).lower() == 'true',
            enable_chip_distribution=os.getenv('ENABLE_CHIP_DISTRIBUTION', 'true').lower() == 'true',
            # Eastmoney API 패치 스위치
            enable_eastmoney_patch=os.getenv('ENABLE_EASTMONEY_PATCH', 'false').lower() == 'true',
            # 실시간 시세 데이터 소스 우선순위:
            # - tencent: Tencent 금융, 거래량 비율/회전율/PE/PB 등 제공, 종목별 조회 안정적(추천)
            # - akshare_sina: Sina 금융, 기본 시세는 안정적이나 거래량 비율 없음
            # - efinance/akshare_em: Eastmoney 전체 시장 API, 데이터가 가장 풍부하지만 차단되기 쉬움
            # - tushare: Tushare Pro, 2000포인트 필요, 데이터 풍부
            realtime_source_priority=cls._resolve_realtime_source_priority(),
            realtime_cache_ttl=parse_env_int(os.getenv('REALTIME_CACHE_TTL'), 600, field_name='REALTIME_CACHE_TTL', minimum=0),
            circuit_breaker_cooldown=parse_env_int(os.getenv('CIRCUIT_BREAKER_COOLDOWN'), 300, field_name='CIRCUIT_BREAKER_COOLDOWN', minimum=0),
            enable_fundamental_pipeline=os.getenv('ENABLE_FUNDAMENTAL_PIPELINE', 'true').lower() == 'true',
            fundamental_stage_timeout_seconds=parse_env_float(
                os.getenv('FUNDAMENTAL_STAGE_TIMEOUT_SECONDS'),
                FUNDAMENTAL_STAGE_TIMEOUT_SECONDS_DEFAULT,
                field_name='FUNDAMENTAL_STAGE_TIMEOUT_SECONDS',
                minimum=0.0,
            ),
            fundamental_fetch_timeout_seconds=parse_env_float(
                os.getenv('FUNDAMENTAL_FETCH_TIMEOUT_SECONDS'),
                8.0,
                field_name='FUNDAMENTAL_FETCH_TIMEOUT_SECONDS',
                minimum=0.0,
            ),
            fundamental_retry_max=parse_env_int(os.getenv('FUNDAMENTAL_RETRY_MAX'), 1, field_name='FUNDAMENTAL_RETRY_MAX', minimum=0),
            fundamental_cache_ttl_seconds=parse_env_int(
                os.getenv('FUNDAMENTAL_CACHE_TTL_SECONDS'),
                120,
                field_name='FUNDAMENTAL_CACHE_TTL_SECONDS',
                minimum=0,
            ),
            fundamental_cache_max_entries=parse_env_int(
                os.getenv('FUNDAMENTAL_CACHE_MAX_ENTRIES'),
                256,
                field_name='FUNDAMENTAL_CACHE_MAX_ENTRIES',
                minimum=1,
            ),
            portfolio_risk_concentration_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT'),
                35.0,
                field_name='PORTFOLIO_RISK_CONCENTRATION_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_drawdown_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT'),
                15.0,
                field_name='PORTFOLIO_RISK_DRAWDOWN_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_stop_loss_alert_pct=parse_env_float(
                os.getenv('PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT'),
                10.0,
                field_name='PORTFOLIO_RISK_STOP_LOSS_ALERT_PCT',
                minimum=0.0,
            ),
            portfolio_risk_stop_loss_near_ratio=parse_env_float(
                os.getenv('PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO'),
                0.8,
                field_name='PORTFOLIO_RISK_STOP_LOSS_NEAR_RATIO',
                minimum=0.0,
            ),
            portfolio_risk_lookback_days=parse_env_int(
                os.getenv('PORTFOLIO_RISK_LOOKBACK_DAYS'),
                180,
                field_name='PORTFOLIO_RISK_LOOKBACK_DAYS',
                minimum=1,
            ),
            portfolio_fx_update_enabled=os.getenv('PORTFOLIO_FX_UPDATE_ENABLED', 'true').lower() == 'true',
            screening_enabled=parse_env_bool(os.getenv('SCREENING_ENABLED'), default=False),
        )
    
    @classmethod
    def _parse_litellm_yaml(cls, config_path: str) -> List[Dict[str, Any]]:
        """Parse a standard LiteLLM config YAML file into Router model_list.

        Supports the ``os.environ/VAR_NAME`` syntax for secret references.
        Returns an empty list on any error (logged, never raises).
        """
        import logging
        _logger = logging.getLogger(__name__)
        try:
            import yaml
        except ImportError:
            _logger.warning("PyYAML not installed; LITELLM_CONFIG ignored. Install with: pip install pyyaml")
            return []

        path = Path(config_path)
        if not path.is_absolute():
            path = Path(__file__).parent.parent / path
        if not path.exists():
            _logger.warning(f"LITELLM_CONFIG file not found: {path}")
            return []

        try:
            with open(path, encoding='utf-8') as f:
                yaml_config = yaml.safe_load(f) or {}
        except Exception as e:
            _logger.warning(f"Failed to parse LITELLM_CONFIG: {e}")
            return []

        model_list = yaml_config.get('model_list', [])
        if not isinstance(model_list, list):
            _logger.warning("LITELLM_CONFIG: model_list must be a list")
            return []

        # Resolve os.environ/ references in string params
        for entry in model_list:
            params = entry.get('litellm_params', {})
            for key in list(params.keys()):
                val = params.get(key)
                if isinstance(val, str) and val.startswith('os.environ/'):
                    env_name = val.split('/', 1)[1]
                    params[key] = os.getenv(env_name, '')

        _logger.info(f"LITELLM_CONFIG: loaded {len(model_list)} model deployment(s) from {path}")
        return model_list

    @classmethod
    def _parse_llm_channels(cls, channels_str: str) -> List[Dict[str, Any]]:
        """Backward-compatible channel parser returning only valid channels."""
        channels, _issues, _blocks, _blocked_routes = cls._parse_llm_channels_with_issues(channels_str)
        return channels

    @classmethod
    def _parse_llm_channels_with_issues(
        cls,
        channels_str: str,
    ) -> Tuple[List[Dict[str, Any]], List[HermesConfigIssue], bool, List[str]]:
        """Parse LLM_CHANNELS env var and per-channel env vars.

        Format:
            LLM_CHANNELS=aihubmix,deepseek,gemini
            LLM_AIHUBMIX_PROTOCOL=openai
            LLM_AIHUBMIX_API_SURFACE=chat_completions
            LLM_AIHUBMIX_BASE_URL=https://aihubmix.com/v1
            LLM_AIHUBMIX_API_KEY=sk-xxx           (or LLM_AIHUBMIX_API_KEYS=k1,k2)
            LLM_AIHUBMIX_MODELS=gpt-5.5,claude-sonnet-4-6
            LLM_AIHUBMIX_ENABLED=true
        """
        import logging
        _logger = logging.getLogger(__name__)

        channels: List[Dict[str, Any]] = []
        issues: List[HermesConfigIssue] = []
        blocks_legacy_fallback = False
        blocked_hermes_routes: List[str] = []

        def record_blocked_hermes_routes(raw_models: List[str]) -> None:
            nonlocal blocks_legacy_fallback
            blocks_legacy_fallback = True
            for raw_model in raw_models or [HERMES_DEFAULT_MODEL]:
                for route_name in hermes_blocked_route_candidates(raw_model):
                    if route_name not in blocked_hermes_routes:
                        blocked_hermes_routes.append(route_name)

        for raw_name in channels_str.split(','):
            ch_name = raw_name.strip()
            if not ch_name:
                continue
            ch_lower = ch_name.lower()
            ch_upper = ch_name.upper()

            base_url = resolve_llm_channel_base_url(
                ch_name, os.getenv(f'LLM_{ch_upper}_BASE_URL', '')
            ) or None
            if ch_lower == "anspire" and not base_url:
                base_url = (
                    os.getenv('ANSPIRE_LLM_BASE_URL') or ANSPIRE_LLM_BASE_URL_DEFAULT
                ).strip() or None
            protocol_raw = os.getenv(f'LLM_{ch_upper}_PROTOCOL', '').strip()
            if ch_lower == "anspire" and not protocol_raw:
                protocol_raw = "openai"
            api_surface_raw = os.getenv(f'LLM_{ch_upper}_API_SURFACE', '').strip()
            enabled_raw = os.getenv(f'LLM_{ch_upper}_ENABLED')
            if ch_lower == "anspire" and (enabled_raw is None or not enabled_raw.strip()):
                enabled_raw = os.getenv('ANSPIRE_LLM_ENABLED')
            enabled = parse_env_bool(enabled_raw, default=True)

            # API keys: LLM_{NAME}_API_KEYS (multi) > LLM_{NAME}_API_KEY (single)
            api_keys_raw = os.getenv(f'LLM_{ch_upper}_API_KEYS', '')
            api_keys = [k.strip() for k in api_keys_raw.split(',') if k.strip()]
            single_key = os.getenv(f'LLM_{ch_upper}_API_KEY', '').strip()
            if not api_keys:
                if single_key:
                    api_keys = [single_key]
            if not api_keys and ch_lower == "anspire":
                anspire_keys_raw = os.getenv('ANSPIRE_API_KEYS', '')
                api_keys = [k.strip() for k in anspire_keys_raw.split(',') if k.strip()]
            api_keys = resolve_llm_channel_api_keys(ch_name, api_keys, os.environ)

            # Models
            models_raw = os.getenv(f'LLM_{ch_upper}_MODELS', '')
            raw_models = [m.strip() for m in models_raw.split(',') if m.strip()]
            raw_models = resolve_llm_channel_models(
                ch_name, raw_models, channel_names=channels_str,
                primary_model=os.getenv('LITELLM_MODEL', ''),
                fallback_models=os.getenv('LITELLM_FALLBACK_MODELS', ''),
            )
            if not raw_models and ch_lower == "anspire":
                anspire_model = (
                    os.getenv('ANSPIRE_LLM_MODEL') or ANSPIRE_LLM_MODEL_DEFAULT
                ).strip()
                if anspire_model:
                    raw_models = [anspire_model]

            # Disabled channels are inert. In particular, stale values such as
            # LLM_HERMES_API_SURFACE=responses must not block valid legacy
            # deployments after Hermes has been explicitly disabled.
            if not enabled:
                _logger.info("LLM channel '%s': disabled, skipped", ch_name)
                continue

            if not is_supported_llm_channel_api_surface_value(api_surface_raw):
                issues.append(HermesConfigIssue(
                    f"LLM_{ch_upper}_API_SURFACE",
                    "invalid_api_surface",
                    (
                        f"Unsupported LLM API surface '{api_surface_raw}'. "
                        f"Supported: {', '.join(SUPPORTED_LLM_CHANNEL_API_SURFACES)}"
                    ),
                ))
                if is_reserved_hermes_name(ch_name):
                    record_blocked_hermes_routes(raw_models)
                _logger.warning(
                    "LLM_%s_API_SURFACE=%s is unsupported; channel skipped",
                    ch_upper,
                    api_surface_raw,
                )
                continue
            api_surface = normalize_llm_channel_api_surface(api_surface_raw)

            if is_reserved_hermes_name(ch_name):
                if api_surface == "responses":
                    issues.append(HermesConfigIssue(
                        f"LLM_{ch_upper}_API_SURFACE",
                        "hermes_responses_unsupported",
                        "The reserved Hermes channel does not support the Responses API surface",
                    ))
                    record_blocked_hermes_routes(raw_models)
                    _logger.warning(
                        "LLM_%s_API_SURFACE=responses is unsupported for reserved Hermes channel; channel skipped",
                        ch_upper,
                    )
                    continue
                if not raw_models:
                    raw_models = [HERMES_DEFAULT_MODEL]
                result = parse_hermes_channel(
                    enabled=enabled,
                    protocol=protocol_raw or HERMES_DEFAULT_PROTOCOL,
                    base_url=base_url or HERMES_DEFAULT_BASE_URL,
                    api_key=single_key,
                    api_keys_raw=api_keys_raw,
                    extra_headers_raw=os.getenv(f'LLM_{ch_upper}_EXTRA_HEADERS', ''),
                    models=raw_models,
                )
                issues.extend(result.issues)
                blocks_legacy_fallback = blocks_legacy_fallback or result.blocks_legacy_fallback
                for route_name in result.blocked_route_names:
                    if route_name not in blocked_hermes_routes:
                        blocked_hermes_routes.append(route_name)
                if result.channel is None:
                    if not enabled:
                        _logger.info("LLM channel '%s': disabled, skipped", ch_name)
                    else:
                        _logger.warning("LLM channel '%s': invalid reserved Hermes channel, skipped", ch_name)
                    continue
                channels.append(result.channel)
                _logger.info("LLM channel '%s': Hermes preset with %d model(s)", ch_name, len(result.channel["models"]))
                continue

            protocol = resolve_llm_channel_protocol(protocol_raw, base_url=base_url, models=raw_models, channel_name=ch_name)
            if api_surface == "responses" and protocol != "openai":
                issues.append(HermesConfigIssue(
                    f"LLM_{ch_upper}_API_SURFACE",
                    "responses_requires_openai_protocol",
                    "Responses API surface currently requires the openai protocol",
                ))
                _logger.warning(
                    "LLM_%s_API_SURFACE=responses requires protocol=openai; channel skipped",
                    ch_upper,
                )
                continue
            incompatible_models = find_incompatible_llm_channel_models(
                raw_models,
                protocol,
                api_surface,
                base_url,
            )
            if incompatible_models:
                issues.append(HermesConfigIssue(
                    f"LLM_{ch_upper}_MODELS",
                    "responses_requires_openai_model_provider",
                    (
                        "Responses API surface requires every model to use the OpenAI "
                        f"provider route; incompatible: {', '.join(incompatible_models[:3])}"
                    ),
                ))
                _logger.warning(
                    "LLM_%s_API_SURFACE=responses has non-OpenAI model routes (%s); channel skipped",
                    ch_upper,
                    ", ".join(incompatible_models[:3]),
                )
                continue
            models = [normalize_llm_channel_model(m, protocol, base_url) for m in raw_models]

            # Extra headers (JSON string, optional)
            extra_headers_raw = os.getenv(f'LLM_{ch_upper}_EXTRA_HEADERS', '').strip()
            extra_headers = None
            if extra_headers_raw:
                try:
                    extra_headers = json.loads(extra_headers_raw)
                except json.JSONDecodeError:
                    _logger.warning(f"LLM_{ch_upper}_EXTRA_HEADERS: invalid JSON, ignored")

            if protocol_raw and canonicalize_llm_channel_protocol(protocol_raw) not in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
                _logger.warning(
                    "LLM_%s_PROTOCOL=%s is unsupported; auto-detected protocol=%s",
                    ch_upper,
                    protocol_raw,
                    protocol or "unknown",
                )

            if not api_keys and channel_allows_empty_api_key(protocol, base_url):
                api_keys = [""]

            if not api_keys:
                _logger.warning(f"LLM channel '{ch_name}': no API key configured, skipped")
                continue
            if not models:
                _logger.warning(f"LLM channel '{ch_name}': no models configured, skipped")
                continue

            channels.append({
                'name': ch_name.lower(),
                'protocol': protocol,
                'api_surface': api_surface,
                'enabled': enabled,
                'base_url': base_url,
                'api_keys': api_keys,
                'models': models,
                'extra_headers': extra_headers,
            })
            _logger.info(f"LLM channel '{ch_name}': {len(models)} model(s), {len(api_keys)} key(s)")

        surface_conflicts = find_llm_channel_surface_conflicts(channels)
        if surface_conflicts:
            conflicting_models = set(surface_conflicts)
            for model, surfaces in surface_conflicts.items():
                issues.append(HermesConfigIssue(
                    "LLM_CHANNELS",
                    "mixed_api_surfaces_for_route",
                    (
                        f"LLM route alias '{model}' is declared with multiple API surfaces: "
                        f"{', '.join(surfaces)}"
                    ),
                ))
                _logger.warning(
                    "LLM route alias '%s' mixes API surfaces (%s); conflicting channels skipped",
                    model,
                    ", ".join(surfaces),
                )
            channels = [
                channel
                for channel in channels
                if not {
                    normalize_llm_channel_model(
                        str(model),
                        str(channel.get("protocol") or ""),
                        str(channel.get("base_url") or ""),
                    )
                    for model in channel.get("models") or []
                }.intersection(conflicting_models)
            ]

        return channels, issues, blocks_legacy_fallback, blocked_hermes_routes

    @classmethod
    def _channels_to_model_list(cls, channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert parsed LLM channels to LiteLLM Router model_list format.

        Mapping follows:
        - LiteLLM providers: https://docs.litellm.ai/docs/providers
        - LiteLLM model_list 의미: https://docs.litellm.ai/docs/proxy/configs#the-model_list-key
        """
        surface_conflicts = find_llm_channel_surface_conflicts(channels)
        if surface_conflicts:
            raise ValueError(
                "LLM route aliases cannot mix API surfaces: "
                + ", ".join(sorted(surface_conflicts))
            )
        model_list: List[Dict[str, Any]] = []
        for ch in channels:
            hermes_refs = {
                str(ref.get("route_model") or ""): ref
                for ref in (ch.get("model_refs") or [])
                if isinstance(ref, dict)
            }
            for model_name in ch['models']:
                for api_key in ch['api_keys']:
                    model_ref = hermes_refs.get(str(model_name))
                    wire_model = str((model_ref or {}).get("wire_model") or model_name)
                    api_surface = normalize_llm_channel_api_surface(ch.get("api_surface"))
                    wire_model = apply_litellm_api_surface(wire_model, api_surface)
                    litellm_params: Dict[str, Any] = {
                        'model': wire_model,
                    }
                    if api_key:
                        litellm_params['api_key'] = api_key
                    if ch['base_url']:
                        litellm_params['api_base'] = ch['base_url']
                    # Auto-inject aihubmix sponsored header
                    headers = dict(ch.get('extra_headers') or {})
                    if ch['base_url'] and 'aihubmix.com' in ch['base_url']:
                        headers.setdefault('APP-Code', 'GPIJ3886')
                    if headers:
                        litellm_params['extra_headers'] = headers

                    entry: Dict[str, Any] = {
                        'model_name': model_name,
                        'litellm_params': litellm_params,
                    }
                    if ch.get("is_hermes") or is_reserved_hermes_name(str(ch.get("name") or "")):
                        entry["model_info"] = hermes_model_info(
                            str((model_ref or {}).get("display_model") or "")
                        )
                    elif api_surface == "responses":
                        entry["model_info"] = {"dsa_api_surface": "responses"}
                    model_list.append(entry)
        return model_list

    @classmethod
    def _legacy_keys_to_model_list(
        cls,
        gemini_keys: List[str],
        anthropic_keys: List[str],
        openai_keys: List[str],
        openai_base_url: Optional[str],
        deepseek_keys: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build Router model_list from legacy per-provider keys (backward compat).

        Returns a model_list where each provider's keys are expanded into
        deployments, keyed by placeholder model_name tokens.  The analyzer
        resolves actual model_names at call time from LITELLM_MODEL /
        LITELLM_FALLBACK_MODELS.

        Compatibility note:
        - LiteLLM OpenAI-compatible 규칙: https://docs.litellm.ai/docs/providers/openai_compatible
        - OpenAI 요청·인증 규칙: https://platform.openai.com/docs/api-reference/making-requests
          / https://platform.openai.com/docs/api-reference/authentication
        """
        model_list: List[Dict[str, Any]] = []

        # Gemini keys
        for k in gemini_keys:
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_gemini__',
                    'litellm_params': {'model': '__legacy_gemini__', 'api_key': k},
                })

        # Anthropic keys
        for k in anthropic_keys:
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_anthropic__',
                    'litellm_params': {'model': '__legacy_anthropic__', 'api_key': k},
                })

        # OpenAI-compatible keys
        for k in openai_keys:
            if k and len(k) >= 8:
                params: Dict[str, Any] = {'model': '__legacy_openai__', 'api_key': k}
                if openai_base_url:
                    params['api_base'] = openai_base_url
                if openai_base_url and 'aihubmix.com' in openai_base_url:
                    params['extra_headers'] = {'APP-Code': 'GPIJ3886'}
                model_list.append({
                    'model_name': '__legacy_openai__',
                    'litellm_params': params,
                })

        # DeepSeek keys (native litellm provider — auto-resolves api_base)
        for k in (deepseek_keys or []):
            if k and len(k) >= 8:
                model_list.append({
                    'model_name': '__legacy_deepseek__',
                    'litellm_params': {
                        'model': '__legacy_deepseek__',
                        'api_key': k,
                    },
                })

        return model_list

    @classmethod
    def _parse_stock_email_groups(cls) -> List[Tuple[List[str], List[str]]]:
        """
        Parse STOCK_GROUP_N and EMAIL_GROUP_N from environment.
        Returns [(stocks, emails), ...] ordered by group index.
        Stock codes are canonicalized via normalize_stock_code so that
        runtime routing matches the same equivalence used in validation.
        """
        from data_provider.base import normalize_stock_code

        groups: dict = {}
        stock_re = re.compile(r'^STOCK_GROUP_(\d+)$', re.IGNORECASE)
        email_re = re.compile(r'^EMAIL_GROUP_(\d+)$', re.IGNORECASE)
        for key in os.environ:
            m = stock_re.match(key)
            if m:
                idx = int(m.group(1))
                val = os.environ[key].strip()
                groups.setdefault(idx, {})['stocks'] = [
                    normalize_stock_code(c.strip())
                    for c in val.split(',') if c.strip()
                ]
            m = email_re.match(key)
            if m:
                idx = int(m.group(1))
                val = os.environ[key].strip()
                groups.setdefault(idx, {})['emails'] = [e.strip() for e in val.split(',') if e.strip()]
        result = []
        for idx in sorted(groups.keys()):
            g = groups[idx]
            if 'stocks' in g and 'emails' in g and g['stocks'] and g['emails']:
                result.append((g['stocks'], g['emails']))
        return result

    @classmethod
    def _parse_report_type(cls, value: str) -> str:
        """Parse REPORT_TYPE, fallback to simple for invalid values (supports brief)."""
        v = (value or 'simple').strip().lower()
        if v in ('simple', 'full', 'brief'):
            return v
        import logging
        logging.getLogger(__name__).warning(
            f"REPORT_TYPE '{value}' invalid, fallback to 'simple' (valid: simple/full/brief)"
        )
        return 'simple'

    @classmethod
    def _get_env_file_value(cls, key: str) -> Optional[str]:
        """Read one config key directly from the active `.env` file."""
        env_file = os.getenv("ENV_FILE")
        env_path = Path(env_file) if env_file else (Path(__file__).parent.parent / ".env")
        if not env_path.exists():
            return None

        try:
            env_values = dotenv_values(env_path)
        except Exception as exc:  # pragma: no cover - defensive branch
            logging.getLogger(__name__).warning(
                "Failed to read %s while resolving %s: %s",
                env_path,
                key,
                exc,
            )
            return None

        value = env_values.get(key)
        if value is None:
            return None
        return unescape_compose_sensitive_env_value(key, str(value))

    @classmethod
    def _resolve_env_value(
        cls,
        key: str,
        *,
        default: Optional[str] = None,
        prefer_env_file: bool = False,
    ) -> Optional[str]:
        """Resolve one env value, optionally preferring the persisted `.env` copy."""
        env_value = os.getenv(key)
        file_value = cls._get_env_file_value(key)

        should_prefer_file = prefer_env_file or key in cls._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS
        if should_prefer_file and file_value is not None:
            if env_value is not None and cls._has_bootstrap_runtime_env_override(key):
                return env_value
            return file_value
        if env_value is not None:
            return env_value
        if file_value is not None:
            return file_value
        return default

    @classmethod
    def _capture_bootstrap_runtime_env_overrides(cls) -> None:
        """Remember process-provided runtime env overrides before dotenv mutates os.environ.

        Called by ``setup_env()`` **before** ``load_dotenv()``, so ``os.environ``
        only contains genuine process-level values (Docker ``environment:``,
        Dockerfile ``ENV``, shell exports, etc.).

        A key is treated as an explicit override when it is present in
        ``os.environ`` and either:
        * absent from the persisted ``.env`` file, **or**
        * present with a **different** value.

        When both values are identical, the distinction is irrelevant and we
        do **not** flag the key, so that a later ``.env`` update by WebUI can
        take effect on config reload without requiring a container restart.
        """
        if cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED:
            return

        explicit_overrides = set()
        present_keys = set()
        for key in cls._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS:
            env_value = os.environ.get(key)
            if env_value is None:
                continue

            present_keys.add(key)
            file_value = cls._get_env_file_value(key)
            if file_value is None or env_value != file_value:
                explicit_overrides.add(key)

        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset(explicit_overrides)
        cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset(present_keys)
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = True

    @classmethod
    def _has_bootstrap_runtime_env_override(cls, key: str) -> bool:
        cls._capture_bootstrap_runtime_env_overrides()
        return key in cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES

    @classmethod
    def _had_bootstrap_runtime_env_key(cls, key: str) -> bool:
        cls._capture_bootstrap_runtime_env_overrides()
        return key in cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS

    @classmethod
    def _resolve_report_language_env_value(
        cls,
        preexisting_env_value: Optional[str],
    ) -> str:
        """Resolve REPORT_LANGUAGE while preserving real process env overrides."""
        file_value = cls._get_env_file_value("REPORT_LANGUAGE")
        env_value = os.getenv("REPORT_LANGUAGE")

        if preexisting_env_value is not None:
            env_text = preexisting_env_value.strip()
            file_text = (file_value or "").strip()
            if file_text and env_text and env_text.lower() != file_text.lower():
                env_file = os.getenv("ENV_FILE") or str(Path(__file__).parent.parent / ".env")
                logging.getLogger(__name__).warning(
                    "REPORT_LANGUAGE environment value '%s' overrides %s ('%s')",
                    preexisting_env_value,
                    env_file,
                    file_value,
                )
            return preexisting_env_value

        if file_value is not None:
            return file_value

        return env_value or "zh"

    @classmethod
    def _parse_report_language(cls, value: Optional[str]) -> str:
        """Parse REPORT_LANGUAGE, fallback to zh for invalid values."""
        normalized = normalize_report_language(value, default="zh")
        raw = (value or "").strip()
        if raw and not is_supported_report_language_value(raw):
            logging.getLogger(__name__).warning(
                "REPORT_LANGUAGE '%s' invalid, fallback to 'zh' (valid: zh/en/ko)",
                value,
            )
        return normalized

    @classmethod
    def _parse_news_strategy_profile(cls, value: Optional[str]) -> str:
        """Parse NEWS_STRATEGY_PROFILE, fallback to short for invalid values."""
        normalized = normalize_news_strategy_profile(value)
        raw = (value or "short").strip().lower()
        if raw != normalized:
            logging.getLogger(__name__).warning(
                "NEWS_STRATEGY_PROFILE '%s' invalid, fallback to 'short' "
                "(valid: ultra_short/short/medium/long)",
                value,
            )
        return normalized

    def get_effective_news_window_days(self) -> int:
        """Return effective news window days after profile + max-age merge."""
        return resolve_news_window_days(
            news_max_age_days=self.news_max_age_days,
            news_strategy_profile=self.news_strategy_profile,
        )

    @staticmethod
    def _parse_etf_rotation_pool(value: Optional[str]) -> List[str]:
        if value is None or not value.strip():
            return list(DEFAULT_ETF_ROTATION_POOL)
        codes: List[str] = []
        for raw in value.split(','):
            code = raw.strip()
            if code and code not in codes:
                codes.append(code)
        return codes

    @staticmethod
    def _parse_etf_rotation_rebalance(value: Optional[str]) -> str:
        normalized = (value or 'weekly').strip().lower()
        if normalized in ('weekly', 'monthly'):
            return normalized
        logger.warning("ETF_ROTATION_REBALANCE=%r is invalid; falling back to weekly", value)
        return 'weekly'

    @classmethod
    def _parse_market_review_region(cls, value: str) -> str:
        """시장 리뷰 지역을 해석. 잘못된 값이면 경고를 남기고 cn으로 되돌림"""
        normalized = normalize_market_review_region_lenient(value)
        if normalized is not None:
            return normalized

        logging.getLogger(__name__).warning(
            f"MARKET_REVIEW_REGION 설정값 '{value}' 이(가) 잘못되어 기본값 'cn'으로 되돌림(허용 값: cn / hk / us / jp / kr / both; 쉼표로 여러 개 지정 가능)"
        )
        return 'cn'

    @classmethod
    def _parse_market_review_color_scheme(cls, value: str) -> str:
        """Parse market-review index change color scheme."""
        import logging
        v = (value or 'green_up').strip().lower().replace('-', '_')
        if v in ('green_up', 'red_up'):
            return v
        logging.getLogger(__name__).warning(
            "MARKET_REVIEW_COLOR_SCHEME 설정값 '%s' 이(가) 잘못되어 기본값 'green_up'으로 되돌림(허용 값: green_up / red_up)",
            value,
        )
        return 'green_up'

    @classmethod
    def _parse_md2img_engine(cls, value: str) -> str:
        """Parse MD2IMG_ENGINE, fallback to wkhtmltoimage for invalid values (Issue #455)."""
        v = (value or 'wkhtmltoimage').strip().lower()
        if v in ('wkhtmltoimage', 'markdown-to-file', 'playwright'):
            return v
        if v:
            import logging
            logging.getLogger(__name__).warning(
                f"MD2IMG_ENGINE '{value}' invalid, fallback to 'wkhtmltoimage' "
                "(valid: wkhtmltoimage | markdown-to-file | playwright)"
            )
        return 'wkhtmltoimage'

    @classmethod
    def _resolve_realtime_source_priority(cls) -> str:
        """
        Resolve realtime source priority with automatic tushare injection.

        When TUSHARE_TOKEN is configured but REALTIME_SOURCE_PRIORITY is not
        explicitly set, automatically prepend 'tushare' to the default priority
        so that the paid data source is utilized for realtime quotes as well.
        """
        explicit = os.getenv('REALTIME_SOURCE_PRIORITY')
        default_priority = 'tencent,akshare_sina,efinance,akshare_em'

        if explicit:
            # User explicitly set priority, respect it
            return explicit

        tushare_token = os.getenv('TUSHARE_TOKEN', '').strip()
        if tushare_token:
            # Token configured but no explicit priority override
            # Prepend tushare so the paid source is tried first
            import logging
            logger = logging.getLogger(__name__)
            resolved = f'tushare,{default_priority}'
            logger.info(
                f"TUSHARE_TOKEN detected, auto-injecting tushare into realtime priority: {resolved}"
            )
            return resolved

        return default_priority

    @classmethod
    def reset_instance(cls) -> None:
        """싱글턴 초기화(주로 테스트용)"""
        cls._instance = None
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED = False
        cls._BOOTSTRAP_RUNTIME_ENV_OVERRIDES = frozenset()
        cls._BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS = frozenset()

    def has_searxng_enabled(self) -> bool:
        """Whether SearXNG fallback is enabled via self-hosted or public mode."""
        return bool(self.searxng_base_urls) or bool(self.searxng_public_instances_enabled)

    def has_search_capability_enabled(self) -> bool:
        """Whether any search provider is configured or SearXNG fallback is enabled."""
        return bool(
            self.anspire_api_keys
            or self.bocha_api_keys
            or self.minimax_api_keys
            or self.tavily_api_keys
            or self.brave_api_keys
            or self.serpapi_keys
            or self.has_searxng_enabled()
        )

    def is_agent_available(self) -> bool:
        """Check whether agent capabilities are usable.

        Decision table:

        +-----------------------+----------------------------+-----------------+
        | AGENT_MODE env        | Agent-safe route available | Result          |
        +-----------------------+----------------------------+-----------------+
        | ``false`` (explicit)  | any                        | False           |
        | ``true``              | yes                        | True            |
        | ``true``              | no                         | False           |
        | not set (default)     | yes                        | True            |
        | not set (default)     | no                         | False           |
        +-----------------------+----------------------------+-----------------+

        ``AGENT_MODE=true`` expresses user intent, but Phase 3 Hermes safety
        still requires a non-Hermes Agent route. Hermes-only deployments cannot
        satisfy Agent tool roundtrip support; mixed routes are usable only via
        their non-Hermes deployments. ``AGENT_MODE=false`` remains an explicit
        kill-switch. Explicit local CLI Agent backends are unavailable because
        they are text generation backends, not Agent tool-calling runtimes.
        """
        if (self.agent_generation_backend or AUTO_AGENT_BACKEND_ID).strip().lower() in GENERATION_ONLY_BACKEND_IDS:
            return False
        # Phase 3 no longer lets AGENT_MODE=true bypass tool-route safety.
        if self._agent_mode_explicit:
            if not self.agent_mode:
                return False
            primary_model = get_effective_agent_primary_model(self)
            origins = route_deployment_origins(self.llm_model_list, primary_model)
            return not origins.is_hermes_only
        # Auto-detect: Agent inherits global model when AGENT_LITELLM_MODEL is empty.
        primary_model = get_effective_agent_primary_model(self)
        if not primary_model:
            return False
        origins = route_deployment_origins(self.llm_model_list, primary_model)
        return not origins.is_hermes_only

    def refresh_stock_list(self) -> None:
        """
        STOCK_LIST 환경 변수를 다시 읽어 설정의 관심종목 목록을 갱신
        
        두 가지 설정 방식 지원:
        1. .env 파일(로컬 개발, 예약 작업 모드) - 수정하면 다음 실행부터 자동 적용
        2. 시스템 환경 변수(GitHub Actions, Docker) - 시작할 때 고정, 실행 중에는 바뀌지 않음
        """
        # .env 파일의 최신 설정을 먼저 읽음. 그래야 컨테이너 안에서 .env 파일을 고쳐도
        # 최신 종목 목록을 가져올 수 있음
        env_file = os.getenv("ENV_FILE")
        env_path = Path(env_file) if env_file else (Path(__file__).parent.parent / '.env')
        stock_list_str = ''
        if env_path.exists():
            # .env 파일에서 최신 설정을 바로 읽음
            env_values = dotenv_values(env_path)
            stock_list_str = (env_values.get('STOCK_LIST') or '').strip()

        # .env 파일이 없거나 값이 없을 때만 시스템 환경 변수에서 읽음
        if not stock_list_str:
            stock_list_str = os.getenv('STOCK_LIST', '')

        stock_list = [
            (c or "").strip().upper()
            for c in split_stock_list(stock_list_str)
            if (c or "").strip()
        ]

        self.stock_list = stock_list
    
    def validate_structured(self) -> List[ConfigIssue]:
        """Return structured validation issues with severity levels.

        Covers all three LLM configuration tiers introduced by PR #494:
        - LITELLM_CONFIG (YAML)
        - LLM_CHANNELS (env)
        - Legacy per-provider keys

        Returns:
            List of ConfigIssue objects, each carrying a severity
            ("error" | "warning" | "info"), a human-readable message, and the
            primary environment variable / field name it relates to.
        """
        issues: List[ConfigIssue] = []

        # --- Stock list ---
        if not self.stock_list:
            issues.append(ConfigIssue(
                severity="error",
                message="未配置 STOCK_LIST。请设置至少一个股票代码，例如：600519,hk00700,AAPL。",
                field="STOCK_LIST",
            ))
        elif self.stock_email_groups:
            from data_provider.base import normalize_stock_code
            configured_stock_set = {
                normalize_stock_code(code)
                for code in self.stock_list
                if (code or "").strip()
            }
            missing_group_stocks_dict: Dict[str, None] = {}
            for stocks, _emails in self.stock_email_groups:
                for stock in stocks:
                    raw = (stock or "").strip()
                    if not raw:
                        continue
                    normalized_stock = normalize_stock_code(stock)
                    if normalized_stock in configured_stock_set:
                        continue
                    if normalized_stock in missing_group_stocks_dict:
                        continue
                    missing_group_stocks_dict[normalized_stock] = None
            missing_group_stocks = list(missing_group_stocks_dict.keys())
            if missing_group_stocks:
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "检测到 STOCK_GROUP_N 中存在未包含在 STOCK_LIST 内的股票："
                        f"{', '.join(missing_group_stocks[:6])}。"
                        "STOCK_GROUP_N 仅用于邮件路由，不会扩大分析范围；"
                        "请先将这些股票加入 STOCK_LIST。"
                    ),
                    field="STOCK_GROUP_N",
                ))

        # --- Data sources (informational only) ---
        if not self.tushare_token:
            issues.append(ConfigIssue(
                severity="info",
                message="Tushare Token이 설정되지 않아 다른 데이터 소스를 사용합니다",
                field="TUSHARE_TOKEN",
            ))

        # --- Generation backend selection ---
        generation_backend = (self.generation_backend or LITELLM_BACKEND_ID).strip().lower()
        generation_fallback_backend = str(self.generation_fallback_backend or "").strip().lower()
        agent_generation_backend = (
            self.agent_generation_backend or AUTO_AGENT_BACKEND_ID
        ).strip().lower()
        agent_backend = (self.agent_backend or "auto").strip().lower()
        if generation_backend not in SUPPORTED_GENERATION_BACKENDS:
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "GENERATION_BACKEND 지원 값: "
                    f"{'、'.join(sorted(SUPPORTED_GENERATION_BACKENDS))}。"
                    f"현재 설정값: {generation_backend}."
                ),
                field="GENERATION_BACKEND",
            ))
        if generation_fallback_backend and generation_fallback_backend == generation_backend:
            generation_fallback_backend = ""
        if generation_fallback_backend and generation_fallback_backend != LITELLM_BACKEND_ID:
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "GENERATION_FALLBACK_BACKEND 는 litellm, primary와 같은 값(no-op), 또는 빈 문자열만 지원합니다. "
                    f"현재 설정값: {generation_fallback_backend}."
                ),
                field="GENERATION_FALLBACK_BACKEND",
            ))
        if agent_generation_backend not in SUPPORTED_AGENT_GENERATION_BACKENDS:
            agent_ui_backends = "、".join(sorted(SUPPORTED_AGENT_UI_BACKENDS))
            local_toolless_backends = "、".join(sorted(GENERATION_ONLY_BACKEND_IDS))
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    f"AGENT_GENERATION_BACKEND 当前支持 {agent_ui_backends}；"
                    f"local CLI backend（{local_toolless_backends}）仅作为显式 unsupported diagnostic 保留，"
                    "不支持 Agent 工具调用。"
                    f"已配置的值为：{agent_generation_backend}。"
                ),
                field="AGENT_GENERATION_BACKEND",
            ))
        if agent_backend == "codex_app_server":
            issues.append(ConfigIssue(
                severity="warning",
                message=AGENT_BACKEND_REMOVED_MESSAGE,
                field="AGENT_BACKEND",
                code="backend_removed",
            ))
        elif agent_backend not in SUPPORTED_AGENT_BACKENDS:
            issues.append(ConfigIssue(
                severity="error",
                message=f"AGENT_BACKEND 当前支持 auto、litellm。已配置的值为：{agent_backend}。",
                field="AGENT_BACKEND",
                code="capability_unsupported",
            ))
        litellm_model_lower = (self.litellm_model or "").strip().lower()
        local_model_prefix = next(
            (
                backend_id
                for backend_id in GENERATION_ONLY_BACKEND_IDS
                if litellm_model_lower.startswith(f"{backend_id}/")
            ),
            "",
        )
        if local_model_prefix:
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    f"{local_model_prefix} 是 GENERATION_BACKEND，不是 LiteLLM provider。"
                    f"请不要使用 LITELLM_MODEL={local_model_prefix}/...。"
                ),
                field="LITELLM_MODEL",
            ))
        if generation_backend == OPENCODE_CLI_BACKEND_ID:
            opencode_model = (self.opencode_cli_model or "").strip()
            unsafe_model = bool(opencode_model) and (
                any(ch.isspace() for ch in opencode_model)
                or any(
                    marker in opencode_model
                    for marker in ("|", ">", "<", ";", "`", "&&", "||", "$")
                )
            )
            if unsafe_model:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "OPENCODE_CLI_MODEL 은 선택 사항인 OpenCode 모델 덮어쓰기 값입니다. "
                        "설정하면 --model 인자 하나로 OpenCode에 전달되므로 공백이나 shell 특수문자를 넣을 수 없습니다. "
                        "설정하지 않으면 DSA는 OpenCode 자체 기본 모델을 사용합니다."
                    ),
                    field="OPENCODE_CLI_MODEL",
                ))

        # --- LLM availability ---
        for raw_issue in self.llm_channel_config_issues or []:
            issues.append(ConfigIssue(
                severity=raw_issue.get("severity", "error"),  # type: ignore[arg-type]
                message=raw_issue.get("message", "LLM channel configuration is invalid"),
                field=raw_issue.get("field", "LLM_CHANNELS"),
                code=raw_issue.get("code", "invalid_channel_config"),
            ))

        # llm_model_list is populated for YAML / channels / managed legacy keys.
        # Other LiteLLM-native providers (for example cohere/*) run through the
        # direct litellm env path and therefore do not populate llm_model_list.
        has_direct_env_model = bool(self.litellm_model) and _uses_direct_env_provider(self.litellm_model)
        local_generation_backend = generation_backend in LOCAL_CLI_GENERATION_BACKEND_IDS
        if not local_generation_backend and not self.llm_model_list and not has_direct_env_model:
            if self.litellm_config_path:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "LITELLM_CONFIG 가 설정되어 있지만 쓸 수 있는 모델을 찾지 못했습니다. "
                        "YAML의 model_list, litellm_params, 환경 변수 참조를 확인하세요."
                    ),
                    field="LITELLM_CONFIG",
                ))
            elif self.llm_channel_names:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置 LLM_CHANNELS，但未解析出可用模型渠道。"
                        "请检查对应 LLM_<CHANNEL>_API_KEY(S)、"
                        "LLM_<CHANNEL>_MODELS、LLM_<CHANNEL>_PROTOCOL 或 Base URL。"
                    ),
                    field="LLM_CHANNELS",
                ))
            else:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "未配置任何可用的 AI 模型接入。请至少配置 ANSPIRE_API_KEYS、"
                        "AIHUBMIX_KEY、GEMINI_API_KEY、ANTHROPIC_API_KEY、"
                        "OPENAI_API_KEY 或 DEEPSEEK_API_KEY 中的一个，或配置 "
                        "LITELLM_CONFIG / LLM_CHANNELS 可用模型渠道。"
                    ),
                    field="LITELLM_CONFIG",
                ))
        elif not local_generation_backend and not self.litellm_model:
            issues.append(ConfigIssue(
                severity="info",
                message=(
                    "尚未明确指定主模型，系统将自动从可用 API Key 推断。"
                    "建议尽早配置主模型（格式如 gemini/gemini-3.1-pro-preview）"
                ),
                field="LITELLM_MODEL",
            ))

        available_router_models = get_configured_llm_models(self.llm_model_list)
        available_router_model_set = set(available_router_models)

        def _has_runtime_source_for_model(model: str) -> bool:
            if not model or _uses_direct_env_provider(model):
                return True
            provider = _get_litellm_provider(model)
            if provider in {"gemini", "vertex_ai"}:
                return any(k and len(k) >= 8 for k in (self.gemini_api_keys or []))
            if provider == "anthropic":
                return any(k and len(k) >= 8 for k in (self.anthropic_api_keys or []))
            if provider == "deepseek":
                return any(k and len(k) >= 8 for k in (self.deepseek_api_keys or []))
            if provider == "openai":
                return any(k and len(k) >= 8 for k in (self.openai_api_keys or []))
            return False

        configured_agent_primary_model = bool((self.agent_litellm_model or "").strip())
        effective_agent_primary_model = get_effective_agent_primary_model(self)

        if available_router_model_set:
            if self.litellm_model:
                origins = route_deployment_origins(self.llm_model_list, self.litellm_model)
                if origins.is_mixed:
                    issues.append(ConfigIssue(
                        severity="error",
                        message=(
                            "Hermes/non-Hermes mixed generation routes are not supported in Phase 3. "
                            "Hermes만 쓰는 주 모델 또는 Hermes를 전혀 쓰지 않는 주 모델 중 하나를 고르세요."
                        ),
                        field="LITELLM_MODEL",
                        code="mixed_hermes_route_unsupported",
                    ))
            if (
                self.litellm_model
                and not _uses_direct_env_provider(self.litellm_model)
                and not _matches_exact_route(self.litellm_model, available_router_model_set)
            ):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "已配置的主模型未出现在当前渠道或高级模型路由配置中。"
                        f" 当前可用模型：{', '.join(available_router_models[:6])}"
                    ),
                    field="LITELLM_MODEL",
                ))

            if configured_agent_primary_model and effective_agent_primary_model:
                origins = route_deployment_origins(self.llm_model_list, effective_agent_primary_model)
                if origins.is_hermes_only:
                    issues.append(ConfigIssue(
                        severity="error",
                        message=(
                            "Hermes-only route 는 Agent 주 모델로 쓸 수 없습니다. "
                            "Hermes가 아닌 deployment가 포함된 Agent-safe route를 고르세요."
                        ),
                        field="AGENT_LITELLM_MODEL",
                        code="explicit_agent_model_no_safe_deployment",
                    ))

            if (
                configured_agent_primary_model
                and effective_agent_primary_model
                and not _uses_direct_env_provider(effective_agent_primary_model)
                and not _matches_exact_route(effective_agent_primary_model, available_router_model_set)
            ):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "설정한 Agent 주 모델이 현재 채널이나 고급 모델 라우팅 설정에 없습니다."
                        f" 현재 쓸 수 있는 모델: {', '.join(available_router_models[:6])}"
                    ),
                    field="AGENT_LITELLM_MODEL",
                ))

            mixed_fallbacks = [
                model for model in (self.litellm_fallback_models or [])
                if route_deployment_origins(self.llm_model_list, model).is_mixed
            ]
            if mixed_fallbacks:
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "Hermes/non-Hermes mixed generation routes are not supported as fallback models in Phase 3: "
                        f"{', '.join(mixed_fallbacks[:3])}"
                    ),
                    field="LITELLM_FALLBACK_MODELS",
                    code="mixed_hermes_route_unsupported",
                ))

            invalid_fallbacks = [
                model for model in (self.litellm_fallback_models or [])
                if model and not _matches_exact_route(model, available_router_model_set)
                and not _uses_direct_env_provider(model)
            ]
            if invalid_fallbacks:
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "예비 모델 중 현재 채널이나 고급 모델 라우팅 설정에 없는 모델이 있습니다: "
                        f"{', '.join(invalid_fallbacks[:3])}"
                    ),
                    field="LITELLM_FALLBACK_MODELS",
                ))

            if (
                self.vision_model
                and not _uses_direct_env_provider(self.vision_model)
                and not _matches_exact_route(self.vision_model, available_router_model_set)
            ):
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "VISION_MODEL 이 현재 채널 설정에 없습니다."
                        f" 현재 쓸 수 있는 모델: {', '.join(available_router_models[:6])}"
                    ),
                    field="VISION_MODEL",
                ))
            if self.vision_model and route_has_hermes(self.llm_model_list, self.vision_model):
                issues.append(ConfigIssue(
                    severity="error",
                    message=(
                        "Hermes Phase 3 에서는 Vision 기능이 검증되지 않아, VISION_MODEL 에 Hermes deployment가 포함된 route를 고를 수 없습니다."
                    ),
                    field="VISION_MODEL",
                    code="hermes_vision_unsupported",
                ))
        elif (
            configured_agent_primary_model
            and effective_agent_primary_model
            and not _has_runtime_source_for_model(effective_agent_primary_model)
        ):
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "Agent 주 모델은 설정되어 있지만 실행에 쓸 수 있는 소스를 찾지 못했습니다"
                    "(켜진 채널 또는 맞는 API Key)."
                ),
                field="AGENT_LITELLM_MODEL",
            ))

        # --- Search engine (informational only) ---
        if not self.has_search_capability_enabled():
            issues.append(ConfigIssue(
                severity="info",
                message="未配置搜索引擎能力 (Bocha/MiniMax/Tavily/Brave/SerpAPI/SearXNG)，新闻搜索功能将不可用",
                field="BOCHA_API_KEYS",
            ))

        # --- Notification channels ---
        has_notification = bool(
            self.wechat_webhook_url
            or self.dingtalk_webhook_url
            or self.feishu_webhook_url
            or (
                (self.feishu_app_id or "")
                and (self.feishu_app_secret or "")
                and (self.feishu_chat_id or "")
            )
            or (self.telegram_bot_token and self.telegram_chat_id)
            or (self.email_sender and self.email_password)
            or (self.pushover_user_key and self.pushover_api_token)
            or _has_ntfy_topic_endpoint(self.ntfy_url)
            or (
                self.gotify_url
                and (self.gotify_token or "").strip()
                and _has_gotify_base_url(self.gotify_url)
            )
            or self.pushplus_token
            or self.serverchan3_sendkey
            or self.custom_webhook_urls
            or self.astrbot_url
            or (self.discord_bot_token and self.discord_main_channel_id)
            or self.discord_webhook_url
            or self.slack_webhook_url
            or (self.slack_bot_token and self.slack_channel_id)
        )

        if not has_notification:
            issues.append(ConfigIssue(
                severity="warning",
                message="未配置通知渠道，将不发送推送通知",
                field="WECHAT_WEBHOOK_URL",
            ))

        has_telegram_token = bool((self.telegram_bot_token or "").strip())
        has_telegram_chat_id = bool((self.telegram_chat_id or "").strip())
        if has_telegram_token != has_telegram_chat_id:
            issues.append(ConfigIssue(
                severity="error",
                message="Telegram 通知配置不完整：TELEGRAM_BOT_TOKEN 和 TELEGRAM_CHAT_ID 必须同时配置。",
                field="TELEGRAM_CHAT_ID" if has_telegram_token else "TELEGRAM_BOT_TOKEN",
            ))

        has_email_sender = bool((self.email_sender or "").strip())
        has_email_password = bool((self.email_password or "").strip())
        if has_email_sender != has_email_password:
            issues.append(ConfigIssue(
                severity="error",
                message="邮件通知配置不完整：EMAIL_SENDER 和 EMAIL_PASSWORD 必须同时配置。",
                field="EMAIL_PASSWORD" if has_email_sender else "EMAIL_SENDER",
            ))

        def _warn_if_webhook_url_invalid(field: str, value: Optional[str]) -> None:
            raw_url = (value or "").strip()
            if not raw_url:
                return
            parsed = urlparse(raw_url)
            if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
                return
            issues.append(ConfigIssue(
                severity="warning",
                message=f"{field} 看起来不是有效 URL，请确认是否以 http:// 或 https:// 开头。",
                field=field,
            ))

        for field, value in (
            ("WECHAT_WEBHOOK_URL", self.wechat_webhook_url),
            ("FEISHU_WEBHOOK_URL", self.feishu_webhook_url),
            ("DINGTALK_WEBHOOK_URL", self.dingtalk_webhook_url),
            ("DISCORD_WEBHOOK_URL", self.discord_webhook_url),
            ("SLACK_WEBHOOK_URL", self.slack_webhook_url),
            ("ASTRBOT_URL", self.astrbot_url),
        ):
            _warn_if_webhook_url_invalid(field, value)

        for custom_url in self.custom_webhook_urls:
            _warn_if_webhook_url_invalid("CUSTOM_WEBHOOK_URLS", custom_url)

        if self.ntfy_url and not _has_ntfy_topic_endpoint(self.ntfy_url):
            issues.append(ConfigIssue(
                severity="error",
                message="NTFY_URL 에는 topic path가 있어야 합니다. 예: https://ntfy.sh/my-topic",
                field="NTFY_URL",
            ))

        if self.gotify_url and not _has_gotify_base_url(self.gotify_url):
            issues.append(ConfigIssue(
                severity="error",
                message="GOTIFY_URL 은 /message 없이 Gotify server base URL이어야 합니다. 예: https://gotify.example",
                field="GOTIFY_URL",
            ))

        if (
            self.gotify_url
            and _has_gotify_base_url(self.gotify_url)
            and not (self.gotify_token or "").strip()
        ):
            issues.append(ConfigIssue(
                severity="warning",
                message="GOTIFY_URL 은 설정됐지만 GOTIFY_TOKEN 이 없어 Gotify 채널이 켜지지 않습니다",
                field="GOTIFY_TOKEN",
            ))

        if self.notification_quiet_hours:
            try:
                parse_notification_quiet_hours(self.notification_quiet_hours)
            except ValueError as exc:
                issues.append(ConfigIssue(
                    severity="error",
                    message=f"알림 무음 시간대 설정이 잘못되었습니다: {exc}",
                    field="NOTIFICATION_QUIET_HOURS",
                ))

        if self.notification_timezone:
            try:
                validate_notification_timezone(self.notification_timezone)
            except ValueError as exc:
                issues.append(ConfigIssue(
                    severity="error",
                    message=f"알림 시간대 설정이 잘못되었습니다: {exc}",
                    field="NOTIFICATION_TIMEZONE",
                ))

        if self.notification_min_severity and not is_supported_notification_severity(self.notification_min_severity):
            issues.append(ConfigIssue(
                severity="error",
                message=(
                    "알림 최소 등급 설정이 잘못되었습니다. 허용 값: "
                    f"{', '.join(NOTIFICATION_SEVERITIES)}"
                ),
                field="NOTIFICATION_MIN_SEVERITY",
            ))

        if self.notification_daily_digest_enabled:
            issues.append(ConfigIssue(
                severity="warning",
                message=(
                    "NOTIFICATION_DAILY_DIGEST_ENABLED 는 아직 예약만 된 설정입니다. "
                    "P4에서는 일일 요약을 보내거나 저장하지 않습니다."
                ),
                field="NOTIFICATION_DAILY_DIGEST_ENABLED",
            ))

        has_feishu_app_id = bool((self.feishu_app_id or "").strip())
        has_feishu_app_secret = bool((self.feishu_app_secret or "").strip())
        has_feishu_app_credentials_complete = has_feishu_app_id and has_feishu_app_secret
        has_feishu_app_credentials = has_feishu_app_id or has_feishu_app_secret
        has_feishu_doc_token = bool((self.feishu_folder_token or "").strip())
        has_feishu_full_cloud_doc_credentials = (
            has_feishu_app_credentials_complete
            and has_feishu_doc_token
        )
        has_feishu_stream_route = bool(self.feishu_stream_enabled and has_feishu_app_credentials_complete)
        has_feishu_app_notification_route = is_feishu_app_bot_configured(self)
        if (
            has_feishu_app_credentials
            and not has_feishu_full_cloud_doc_credentials
            and not is_feishu_static_configured(self)
            and not has_feishu_stream_route
            and not has_feishu_app_notification_route
        ):
            suggestions = []
            if has_feishu_app_credentials_complete:
                suggestions.append("FEISHU_CHAT_ID 를 설정해 App Bot 능동 발송 켜기")
                suggestions.append("FEISHU_STREAM_ENABLED 를 켜서 앱 봇 이벤트 구독 사용")
            else:
                suggestions.append("FEISHU_APP_ID / FEISHU_APP_SECRET 을 모두 채운 뒤 FEISHU_CHAT_ID 를 설정해 App Bot 능동 발송 켜기")
            suggestions.append("FEISHU_WEBHOOK_URL 을 설정해 사용자 정의 봇 Webhook으로 발송")
            issues.append(ConfigIssue(
                severity="warning",
                message="FEISHU_APP_ID / FEISHU_APP_SECRET 만으로는 Feishu 정적 알림이 켜지지 않습니다."
                        + " 다음 중 하나를 고르세요: "
                        + "; ".join(suggestions) + ".",
                field="FEISHU_CHAT_ID",
            ))

        # --- Deprecated field migration hints ---
        if os.getenv("OPENAI_VISION_MODEL"):
            issues.append(ConfigIssue(
                severity="info",
                message=(
                    "OPENAI_VISION_MODEL 은 더 이상 쓰지 않습니다. VISION_MODEL 을 쓰세요. "
                    "현재 값은 자동으로 옮겨졌으니, 이 안내가 사라지도록 설정 파일을 고쳐 주세요."
                ),
                field="OPENAI_VISION_MODEL",
            ))

        # --- Vision key availability ---
        # Only warn when user explicitly set VISION_MODEL (or OPENAI_VISION_MODEL alias).
        # Skipped when vision_model is empty (Vision not intentionally configured).
        if self.vision_model:
            # Maps provider prefix → the corresponding key list tracked by Config.
            # vertex_ai shares gemini keys; other LiteLLM-native providers are not
            # in this map (their keys come from env vars, which we cannot inspect here).
            _VISION_KEY_MAP = {
                "gemini": self.gemini_api_keys,
                "vertex_ai": self.gemini_api_keys,
                "anthropic": self.anthropic_api_keys,
                "openai": self.openai_api_keys,
                "deepseek": self.deepseek_api_keys,
            }
            # Derive the primary model's provider prefix so that its key is also
            # checked even when the provider is absent from VISION_PROVIDER_PRIORITY.
            _primary_prefix = (
                self.vision_model.split("/")[0]
                if "/" in self.vision_model
                else "openai"
            )
            _priority_providers = [
                p.strip().lower()
                for p in self.vision_provider_priority.split(",")
                if p.strip()
            ]
            # Union: fallback providers + primary model's own provider
            _all_providers = {_primary_prefix} | set(_priority_providers)

            # Align with get_api_keys_for_model: keys must be non-empty and len >= 8
            _has_any_key = any(
                any(k and len(k) >= 8 for k in (_VISION_KEY_MAP.get(p) or []))
                for p in _all_providers
                if p in _VISION_KEY_MAP
            )
            if not _has_any_key:
                _checked = sorted(_all_providers & _VISION_KEY_MAP.keys())
                issues.append(ConfigIssue(
                    severity="warning",
                    message=(
                        "VISION_MODEL 은 설정됐지만 쓸 수 있는 Vision API Key를 찾지 못했습니다 "
                        f"(확인한 항목: {', '.join(_checked)}). "
                        "이미지에서 종목 코드를 뽑는 기능을 쓸 수 없으니 해당 API Key를 설정하세요."
                    ),
                    field="VISION_MODEL",
                ))

        return issues

    def validate(self) -> List[str]:
        """Return validation messages as plain strings (backward-compatible).

        Internally delegates to validate_structured().  Callers that only need
        the human-readable strings can continue to use this method unchanged.

        Returns:
            List of message strings, one per ConfigIssue.
        """
        return [issue.message for issue in self.validate_structured()]
    
    def get_db_url(self) -> str:
        """
        SQLAlchemy 데이터베이스 연결 URL 가져오기
        
        데이터베이스 폴더가 없으면 자동으로 만듦
        """
        db_path = Path(self.database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{db_path.absolute()}"


# === 간편한 설정 접근 함수 ===
def get_config() -> Config:
    """전역 설정 인스턴스를 가져오는 바로가기"""
    return Config.get_instance()


# ============================================================
# Shared LLM helpers (used by both analyzer and agent/llm_adapter)
# ============================================================

def get_api_keys_for_model(model: str, config: Config) -> List[str]:
    """Return explicitly managed API keys for a litellm model (legacy path only).

    When llm_model_list is populated (channels / YAML), the Router handles key
    selection, so this function is not needed.  Kept for backward compat when
    no Router is built and a direct litellm.completion() call is needed.
    """
    provider = _get_litellm_provider(model)
    if provider in {"gemini", "vertex_ai"}:
        return [k for k in config.gemini_api_keys if k and len(k) >= 8]
    if provider == "anthropic":
        return [k for k in config.anthropic_api_keys if k and len(k) >= 8]
    if provider == "deepseek":
        return [k for k in config.deepseek_api_keys if k and len(k) >= 8]
    if provider == "openai":
        return [k for k in config.openai_api_keys if k and len(k) >= 8]
    # Other LiteLLM-native providers – API key resolved from env vars
    return []


def extra_litellm_params(model: str, config: Config) -> Dict[str, Any]:
    """Build extra litellm params for a model (legacy path only).

    When llm_model_list is populated, the Router already carries api_base
    and headers per-deployment, so this is not called.
    """
    params: Dict[str, Any] = {}
    # deepseek/ provider: litellm auto-resolves api_base, no manual override needed
    if model.startswith("deepseek/"):
        return params
    if model.startswith("openai/") or "/" not in model:
        if config.openai_base_url:
            params["api_base"] = config.openai_base_url
        if config.openai_base_url and "aihubmix.com" in config.openai_base_url:
            params["extra_headers"] = {"APP-Code": "GPIJ3886"}
    return params


if __name__ == "__main__":
    # 설정 불러오기 테스트
    config = get_config()
    print("=== 설정 불러오기 테스트 ===")
    print(f"관심종목 목록: {config.stock_list}")
    print(f"데이터베이스 경로: {config.database_path}")
    print(f"최대 동시 실행 수: {config.max_workers}")
    print(f"디버그 모드: {config.debug}")
    
    # 설정 검증
    warnings = config.validate()
    if warnings:
        print("\n설정 검증 결과:")
        for w in warnings:
            print(f"  - {w}")

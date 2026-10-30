# -*- coding: utf-8 -*-
"""
===================================
명령 분배기
===================================

명령을 해석하고, 처리기를 찾아, 실행을 넘깁니다.
"""

import asyncio
import logging
import re
import threading
import time
from collections import defaultdict
from typing import Dict, List, Optional, Type, Callable

from bot.models import BotMessage, BotResponse
from bot.commands.base import BotCommand

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    간단한 요청 빈도 제한기

    슬라이딩 윈도 방식으로 사용자별 요청 빈도를 제한합니다.
    """

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        """
        Args:
            max_requests: 윈도 안 최대 요청 수
            window_seconds: 윈도 시간(초)
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, user_id: str) -> bool:
        """
        사용자 요청을 허용할지 확인

        Args:
            user_id: 사용자 식별자

        Returns:
            허용 여부
        """
        now = time.time()
        window_start = now - self.window_seconds

        # 만료된 기록 정리
        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if t > window_start
        ]

        # 한도 초과 여부 확인
        if len(self._requests[user_id]) >= self.max_requests:
            return False

        # 이번 요청 기록
        self._requests[user_id].append(now)
        return True

    def get_remaining(self, user_id: str) -> int:
        """남은 요청 가능 횟수 가져오기"""
        now = time.time()
        window_start = now - self.window_seconds

        # 만료된 기록 정리
        self._requests[user_id] = [
            t for t in self._requests[user_id]
            if t > window_start
        ]

        return max(0, self.max_requests - len(self._requests[user_id]))


class CommandDispatcher:
    """
    명령 분배기

    역할:
    1. 명령 처리기 등록과 관리
    2. 메시지에서 명령과 인자 해석
    3. 명령을 맞는 처리기로 분배
    4. 알 수 없는 명령과 오류 처리

    사용 예:
        dispatcher = CommandDispatcher()
        dispatcher.register(AnalyzeCommand())
        dispatcher.register(HelpCommand())

        response = dispatcher.dispatch(message)
    """

    def __init__(
        self,
        command_prefix: str = "/",
        rate_limit_requests: int = 10,
        rate_limit_window: int = 60,
        admin_users: Optional[List[str]] = None
    ):
        """
        Args:
            command_prefix: 명령 접두사, 기본값 "/"
            rate_limit_requests: 빈도 제한: 윈도 안 최대 요청 수
            rate_limit_window: 빈도 제한: 윈도 시간(초)
            admin_users: 관리자 사용자 ID 목록
        """
        self.command_prefix = command_prefix
        self.admin_users = set(admin_users or [])

        self._commands: Dict[str, BotCommand] = {}
        self._aliases: Dict[str, str] = {}
        self._rate_limiter = RateLimiter(rate_limit_requests, rate_limit_window)

        # 콜백 함수: 도움말 명령이 쓸 명령 목록 가져오기
        self._help_command_getter: Optional[Callable] = None

    def register(self, command: BotCommand) -> None:
        """
        명령 등록

        Args:
            command: 명령 인스턴스
        """
        name = command.name.lower()

        if name in self._commands:
            logger.warning(f"[Dispatcher] 명령 '{name}'이 이미 있어 덮어씁니다")

        self._commands[name] = command
        logger.debug(f"[Dispatcher] 명령 등록: {name}")

        # 별칭 등록
        for alias in command.aliases:
            alias_lower = alias.lower()
            if alias_lower in self._aliases:
                logger.warning(f"[Dispatcher] 별칭 '{alias_lower}'이 이미 있어 덮어씁니다")
            self._aliases[alias_lower] = name
            logger.debug(f"[Dispatcher] 별칭 등록: {alias_lower} -> {name}")

    def register_class(self, command_class: Type[BotCommand]) -> None:
        """
        명령 클래스 등록(자동 인스턴스화)

        Args:
            command_class: 명령 클래스
        """
        self.register(command_class())

    def unregister(self, name: str) -> bool:
        """
        명령 등록 해제

        Args:
            name: 명령 이름

        Returns:
            등록 해제 성공 여부
        """
        name = name.lower()

        if name not in self._commands:
            return False

        command = self._commands.pop(name)

        # 별칭 제거
        for alias in command.aliases:
            self._aliases.pop(alias.lower(), None)

        logger.debug(f"[Dispatcher] 명령 등록 해제: {name}")
        return True

    def get_command(self, name: str) -> Optional[BotCommand]:
        """
        명령 가져오기

        명령 이름과 별칭으로 찾을 수 있습니다.

        Args:
            name: 명령 이름 또는 별칭

        Returns:
            명령 인스턴스 또는 None
        """
        name = name.lower()

        # 먼저 명령 이름으로 찾기
        if name in self._commands:
            return self._commands[name]

        # 다음으로 별칭으로 찾기
        if name in self._aliases:
            return self._commands.get(self._aliases[name])

        return None

    def list_commands(self, include_hidden: bool = False) -> List[BotCommand]:
        """
        모든 명령 나열

        Args:
            include_hidden: 숨긴 명령 포함 여부

        Returns:
            명령 목록
        """
        commands = list(self._commands.values())

        if not include_hidden:
            commands = [c for c in commands if not c.hidden]

        return sorted(commands, key=lambda c: c.name)

    def is_admin(self, user_id: str) -> bool:
        """사용자가 관리자인지 확인"""
        return user_id in self.admin_users

    def add_admin(self, user_id: str) -> None:
        """관리자 추가"""
        self.admin_users.add(user_id)

    def remove_admin(self, user_id: str) -> None:
        """관리자 제거"""
        self.admin_users.discard(user_id)

    def dispatch(self, message: BotMessage) -> BotResponse:
        """메시지를 동기 방식으로 분배합니다.

        기존 동기 호출 코드와 호환되도록 두고, 실제 로직은 `dispatch_async()`에 맡깁니다.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return self._dispatch_sync(message)

        result_holder: Dict[str, BotResponse] = {}
        error_holder: Dict[str, BaseException] = {}

        def _runner() -> None:
            try:
                result_holder["response"] = self._dispatch_sync(message)
            except BaseException as exc:  # pragma: no cover
                error_holder["error"] = exc

        worker = threading.Thread(target=_runner, daemon=True)
        worker.start()
        worker.join()

        if "error" in error_holder:
            raise error_holder["error"]

        return result_holder.get("response", BotResponse.error_response("명령 실행 실패"))

    def _prepare_dispatch(self, message: BotMessage) -> tuple[Optional[str], List[str], Optional[BotCommand], Optional[BotResponse]]:
        """Run shared dispatch pre-checks for sync/async entrypoints."""
        if not self._rate_limiter.is_allowed(message.user_id):
            remaining_time = self._rate_limiter.window_seconds
            return None, [], None, BotResponse.error_response(
                f"요청이 너무 잦습니다. {remaining_time}초 후에 다시 시도해 주세요"
            )

        cmd_name, args = message.get_command_and_args(self.command_prefix)
        if cmd_name is None:
            return None, args, None, None

        logger.info(f"[Dispatcher] 명령 받음: {cmd_name}, 인자: {args}, 사용자: {message.user_name}")

        command = self.get_command(cmd_name)
        if command is None:
            return cmd_name, args, None, BotResponse.error_response(
                f"알 수 없는 명령: {cmd_name}\n"
                f"`{self.command_prefix}help`를 보내면 사용 가능한 명령을 볼 수 있습니다."
            )

        if command.admin_only and not self.is_admin(message.user_id):
            return cmd_name, args, None, BotResponse.error_response("이 명령은 관리자 권한이 필요합니다")

        error_msg = command.validate_args(args)
        if error_msg:
            return cmd_name, args, None, BotResponse.error_response(
                f"{error_msg}\n사용법: `{command.usage}`"
            )

        return cmd_name, args, command, None

    def _dispatch_sync(self, message: BotMessage) -> BotResponse:
        """Pure synchronous dispatch path for webhook/stream integrations."""
        cmd_name, args, command, early_response = self._prepare_dispatch(message)
        if early_response is not None:
            return early_response

        if cmd_name is None:
            nl_result = self._try_nl_routing_sync(message)
            if nl_result is not None:
                return nl_result
            if message.mentioned:
                return BotResponse.text_response(
                    "안녕하세요! 주식 분석 도우미입니다.\n"
                    f"`{self.command_prefix}help`를 보내면 사용 가능한 명령을 볼 수 있습니다."
                )
            return BotResponse.text_response("")

        if command is None:
            return BotResponse.error_response("명령 실행 실패")

        try:
            response = command.execute(message, args)
            logger.info(f"[Dispatcher] 명령 {cmd_name} 실행 성공")
            return response
        except Exception as e:
            logger.error(f"[Dispatcher] 명령 {cmd_name} 실행 실패: {e}")
            logger.exception(e)
            return BotResponse.error_response(f"명령 실행 실패: {str(e)[:100]}")

    async def dispatch_async(self, message: BotMessage) -> BotResponse:
        """
        메시지를 맞는 명령으로 비동기 분배

        Args:
            message: 메시지 객체

        Returns:
            응답 객체
        """
        cmd_name, args, command, early_response = self._prepare_dispatch(message)
        if early_response is not None:
            return early_response

        if cmd_name is None:
            # Not a command — try natural language routing before falling back
            nl_result = await self._try_nl_routing(message)
            if nl_result is not None:
                return nl_result
            # No NL match — check if @mentioned for a help hint
            if message.mentioned:
                return BotResponse.text_response(
                    "안녕하세요! 주식 분석 도우미입니다.\n"
                    f"`{self.command_prefix}help`를 보내면 사용 가능한 명령을 볼 수 있습니다."
                )
            # 명령이 아닌 메시지는 처리하지 않음
            return BotResponse.text_response("")

        if command is None:
            return BotResponse.error_response("명령 실행 실패")

        # 6. 명령 실행
        try:
            response = await command.execute_async(message, args)
            logger.info(f"[Dispatcher] 명령 {cmd_name} 실행 성공")
            return response
        except Exception as e:
            logger.error(f"[Dispatcher] 명령 {cmd_name} 실행 실패: {e}")
            logger.exception(e)
            return BotResponse.error_response(f"명령 실행 실패: {str(e)[:100]}")

    def set_help_command_getter(self, getter: Callable) -> None:
        """
        도움말 명령용 명령 목록 가져오기 함수 설정

        HelpCommand가 명령 목록을 가져갈 수 있게 합니다.

        Args:
            getter: 명령 목록을 반환하는 콜백 함수
        """
        self._help_command_getter = getter

    # ------------------------------------------------------------------ #
    #  Natural language routing (LLM-based)                              #
    # ------------------------------------------------------------------ #

    # Lightweight intent-parsing prompt.  Asks the LLM to output a small
    # JSON object so we can route to the right command.
    _NL_PARSE_PROMPT = """\
You are a stock analysis assistant router.  Given a user's natural-language
message, determine whether it contains a stock-analysis request.

Return a JSON object (and NOTHING else) with these fields:
- "intent": one of "analysis", "chat", "none"
  * "analysis" → the user wants stock analysis / diagnosis / comparison
  * "chat" → the user is asking a general question related to finance
  * "none" → the message is irrelevant or you are unsure
- "codes": a list of stock codes mentioned (may be empty).
  Format: A-share 6-digit ("600519"), HK with prefix ("hk00700"), US ticker uppercase ("AAPL").
- "strategy": strategy/technique name if the user specified one, else null.
  e.g. "缠论", "MACD", "趋势跟踪", "chan_theory", etc.

Examples:
User: "帮我分析一下600519和000858"
{"intent":"analysis","codes":["600519","000858"],"strategy":null}

User: "用缠论看看AAPL"
{"intent":"analysis","codes":["AAPL"],"strategy":"缠论"}

User: "今天大盘怎么样"
{"intent":"chat","codes":[],"strategy":null}

User: "明天天气如何"
{"intent":"none","codes":[],"strategy":null}

User: "600519"
{"intent":"analysis","codes":["600519"],"strategy":null}

User: "帮我分析茅台"
{"intent":"analysis","codes":[],"strategy":null}

User: "analyze TSLA and NVDA using trend strategy"
{"intent":"analysis","codes":["TSLA","NVDA"],"strategy":"trend"}
"""

    # Cheap pre-filter: only invoke LLM when the message plausibly contains
    # stock-related content.  This regex checks for:
    #   - 6-digit A-share / BSE codes (0/3/6 and 43/83/87/88/92 prefixes)
    #   - HK codes like hk00700
    #   - 2-5 uppercase ASCII letters (US tickers)
    #   - Common finance/analysis keywords (Chinese and English)
    _NL_PREFILTER = re.compile(
        r'(?:[036]\d{5}|(?:43|83|87|88|92)\d{4})'  # A-share / BSE 6-digit codes
        r'|(?:hk|HK)\d{5}'                    # HK code
        r'|(?<![a-zA-Z])[A-Z]{2,5}(?![a-zA-Z])'  # US ticker — UPPERCASE only, no IGNORECASE
        r'|分析|看看|查一?下|研究|诊断|怎么样|走势|趋势'
        r'|能买|可以买|涨还是跌|怎么看|能追|建议|目标价'
        r'|支撑|压力|阻力|止损|买点|卖点|技术面|基本面|筹码'
        r'|(?i:analyz|stock|buy|sell|trend|backtest|strateg)',
    )

    _NL_NAME_CLEANUP_PATTERNS = (
        r'[，,。.!！?？:：;；`\'"“”‘’（）()\[\]{}<>]+',
        r'(?i:\b(?:please|analy[sz]e|analysis|research|check|look\s+at|stock|ticker|trend|price)\b)',
        r'(?:帮我|帮忙|麻烦|请|想请你|我想|想|用|按照|基于|关于|对)\s*',
        r'(?:分析|看看|研究|诊断|查一?下|聊聊|说说|问问|评估)\s*',
        r'(?:最近|近期|当前|今天|这只|这个|个股|股票)\s*',
        r'(?:走势|情况|表现|如何|怎么样|怎么看|可以吗|能买吗|值不值得买|技术面|基本面|策略)\s*',
        r'\s+',
    )

    @classmethod
    def _passes_nl_prefilter(cls, text: str) -> bool:
        """Return whether the message is worth the LLM intent-routing cost."""
        if cls._NL_PREFILTER.search(text):
            return True

        stripped = (text or "").strip()
        if " " in stripped or len(stripped) > 10:
            return False

        from src.agent.orchestrator import _extract_stock_code

        return bool(_extract_stock_code(stripped))

    async def _try_nl_routing(self, message: BotMessage) -> Optional[BotResponse]:
        """Route a non-command message to the appropriate command via LLM intent parsing.

        Two-layer approach to balance cost and accuracy:
        1. **Cheap regex pre-filter**: skip messages that clearly have no stock
           or finance content (avoids LLM cost for irrelevant messages).
        2. **LLM intent parsing**: extract intent, stock codes, and strategy
           from the user text with full multilingual support.

        Only activates when:
        - ``AGENT_NL_ROUTING=true`` in config, **and**
        - the message is in a private chat, **or** the bot was @mentioned.

        Returns ``BotResponse`` if a route was found, ``None`` otherwise.
        """
        from src.config import get_config
        config = get_config()

        if not getattr(config, 'agent_nl_routing', False):
            return None

        # Only handle private chat or @mentioned messages to avoid hijacking
        is_private = message.chat_type.value == "private"
        if not is_private and not message.mentioned:
            return None

        # Keep Bot-side Agent entrypoints behind explicit opt-in so NL routing
        # cannot bypass AGENT_MODE=false.
        if not getattr(config, 'agent_mode', False):
            return None

        text = message.content.strip()
        if not text or len(text) > 500:
            return None

        # Layer 1: cheap pre-filter — skip obviously irrelevant messages
        if not self._passes_nl_prefilter(text):
            return None

        # Layer 2: LLM intent parsing — extract codes, intent, strategy
        parsed = await self._parse_intent_via_llm(text, config)
        if parsed is None:
            return None

        intent = parsed.get("intent", "none")
        codes = parsed.get("codes") or []
        strategy = parsed.get("strategy")

        if intent == "none":
            return None

        if intent == "analysis" and not codes:
            resolved_code = self._resolve_stock_code_from_text(text)
            if resolved_code:
                codes = [resolved_code]

        # "chat" intent → route to /chat with original text
        if intent == "chat":
            chat_cmd = self.get_command("chat")
            if chat_cmd:
                logger.info("[Dispatcher] NL routing → /chat: %s", text[:60])
                return await chat_cmd.execute_async(message, [text])
            return None

        # "analysis" intent → route to /ask
        if intent == "analysis" and codes:
            ask_cmd = self.get_command("ask")
            if not ask_cmd:
                return None

            # Build args: "code1,code2 [strategy]"
            code_str = ",".join(codes[:5])  # cap at 5
            args = [code_str]
            if strategy:
                args.append(strategy)

            logger.info(
                "[Dispatcher] NL routing → /ask %s (strategy=%s, text=%s)",
                code_str, strategy, text[:60],
            )
            return await ask_cmd.execute_async(message, args)

        return None

    def _try_nl_routing_sync(self, message: BotMessage) -> Optional[BotResponse]:
        """Synchronous companion to `_try_nl_routing` for legacy call sites."""
        from src.config import get_config

        config = get_config()
        if not getattr(config, 'agent_nl_routing', False):
            return None

        is_private = message.chat_type.value == "private"
        if not is_private and not message.mentioned:
            return None

        if not getattr(config, 'agent_mode', False):
            return None

        text = message.content.strip()
        if not text or len(text) > 500:
            return None

        if not self._passes_nl_prefilter(text):
            return None

        parsed = self._parse_intent_via_llm_sync(text, config)
        if parsed is None:
            return None

        intent = parsed.get("intent", "none")
        codes = parsed.get("codes") or []
        strategy = parsed.get("strategy")

        if intent == "none":
            return None

        if intent == "analysis" and not codes:
            resolved_code = self._resolve_stock_code_from_text(text)
            if resolved_code:
                codes = [resolved_code]

        if intent == "chat":
            chat_cmd = self.get_command("chat")
            if chat_cmd:
                logger.info("[Dispatcher] NL routing → /chat: %s", text[:60])
                return chat_cmd.execute(message, [text])
            return None

        if intent == "analysis" and codes:
            ask_cmd = self.get_command("ask")
            if not ask_cmd:
                return None

            code_str = ",".join(codes[:5])
            args = [code_str]
            if strategy:
                args.append(strategy)

            logger.info(
                "[Dispatcher] NL routing → /ask %s (strategy=%s, text=%s)",
                code_str, strategy, text[:60],
            )
            return ask_cmd.execute(message, args)

        return None

    @staticmethod
    async def _parse_intent_via_llm(text: str, config) -> Optional[dict]:
        """Call LLM to parse user intent.  Returns parsed dict or None on failure."""
        try:
            from src.agent.llm_adapter import LLMToolAdapter

            messages = [
                {"role": "system", "content": CommandDispatcher._NL_PARSE_PROMPT},
                {"role": "user", "content": text},
            ]
            adapter = LLMToolAdapter(config)
            resp = await asyncio.to_thread(
                adapter.call_text,
                messages,
                temperature=0,
                max_tokens=200,
                timeout=10,
            )
            return CommandDispatcher._parse_intent_payload(resp.content or "")
        except Exception as exc:
            logger.debug("[Dispatcher] NL parse LLM call failed: %s", exc)
            return None

    @staticmethod
    def _parse_intent_via_llm_sync(text: str, config) -> Optional[dict]:
        """Synchronous variant for webhook/stream integrations."""
        try:
            from src.agent.llm_adapter import LLMToolAdapter

            messages = [
                {"role": "system", "content": CommandDispatcher._NL_PARSE_PROMPT},
                {"role": "user", "content": text},
            ]
            adapter = LLMToolAdapter(config)
            resp = adapter.call_text(
                messages,
                temperature=0,
                max_tokens=200,
                timeout=10,
            )
            return CommandDispatcher._parse_intent_payload(resp.content or "")
        except Exception as exc:
            logger.debug("[Dispatcher] NL parse LLM call failed: %s", exc)
            return None

    @staticmethod
    def _parse_intent_payload(raw: str) -> Optional[dict]:
        """Parse the JSON payload returned by the intent-routing LLM call."""
        import json as _json

        cleaned = (raw or "").strip()
        if not cleaned:
            return None

        if cleaned.startswith("```"):
            cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
            cleaned = re.sub(r'\s*```$', '', cleaned)

        try:
            result = _json.loads(cleaned)
        except _json.JSONDecodeError:
            logger.debug("[Dispatcher] NL parse: invalid JSON from LLM: %s", cleaned[:200])
            return None

        if isinstance(result, dict) and "intent" in result:
            return result

        logger.debug("[Dispatcher] NL parse: unexpected structure: %s", cleaned[:200])
        return None

    @classmethod
    def _resolve_stock_code_from_text(cls, text: str) -> Optional[str]:
        """Best-effort stock name/code resolution for NL-routed analysis requests."""
        from data_provider.base import canonical_stock_code
        from src.data.stock_mapping import STOCK_NAME_MAP
        from src.services.name_to_code_resolver import resolve_name_to_code

        def _iter_candidates(raw_text: str) -> List[str]:
            candidates: List[str] = []
            stripped = (raw_text or "").strip()
            if stripped:
                candidates.append(stripped)

            cleaned = stripped
            for pattern in cls._NL_NAME_CLEANUP_PATTERNS:
                cleaned = re.sub(pattern, " ", cleaned)
            cleaned = cleaned.strip(" 的").strip()
            if cleaned and cleaned not in candidates:
                candidates.append(cleaned)

            for source in list(candidates):
                for token in re.findall(r'[A-Za-z][A-Za-z0-9\.]{0,9}|[\u4e00-\u9fff]{2,12}', source):
                    normalized = token.strip(" 的").strip()
                    if normalized and normalized not in candidates:
                        candidates.append(normalized)

            return sorted(candidates, key=len, reverse=True)

        def _unique_partial_match(candidate: str) -> Optional[str]:
            if not re.search(r'[\u4e00-\u9fff]', candidate):
                return None
            matches = [
                code for code, stock_name in STOCK_NAME_MAP.items()
                if candidate and candidate in stock_name
            ]
            unique_matches = list(dict.fromkeys(matches))
            if len(unique_matches) == 1:
                return canonical_stock_code(unique_matches[0])
            return None

        candidates = _iter_candidates(text)

        # Prefer deterministic local alias/partial-name matches before any
        # resolver path that may touch online market data providers.
        for candidate in candidates:
            partial = _unique_partial_match(candidate)
            if partial:
                return partial

        for candidate in candidates:
            resolved = resolve_name_to_code(candidate)
            if resolved:
                return canonical_stock_code(resolved)

        return None


# 전역 분배기 인스턴스
_dispatcher: Optional[CommandDispatcher] = None


def get_dispatcher() -> CommandDispatcher:
    """
    전역 분배기 인스턴스 가져오기

    싱글턴 방식. 처음 호출할 때 자동으로 초기화하고 모든 명령을 등록합니다.
    """
    global _dispatcher

    if _dispatcher is None:
        from src.config import get_config

        config = get_config()

        # 분배기 만들기
        _dispatcher = CommandDispatcher(
            command_prefix=getattr(config, 'bot_command_prefix', '/'),
            rate_limit_requests=getattr(config, 'bot_rate_limit_requests', 10),
            rate_limit_window=getattr(config, 'bot_rate_limit_window', 60),
            admin_users=getattr(config, 'bot_admin_users', []),
        )

        # 모든 명령 자동 등록
        from bot.commands import ALL_COMMANDS
        for command_class in ALL_COMMANDS:
            _dispatcher.register_class(command_class)

        logger.info(f"[Dispatcher] 초기화 완료, 명령 {len(_dispatcher._commands)}개 등록됨")

    return _dispatcher


def reset_dispatcher() -> None:
    """전역 분배기 초기화(주로 테스트용)"""
    global _dispatcher
    _dispatcher = None

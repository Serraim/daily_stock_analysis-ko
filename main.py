# -*- coding: utf-8 -*-
"""
===================================
A주 관심종목 AI 분석 시스템 - 메인 실행 프로그램
===================================

하는 일:
1. 각 모듈을 묶어 주식 분석 과정을 끝까지 실행
2. 동시 실행 수를 낮게 잡은 스레드 풀로 작업 배분
3. 전체 예외 처리: 한 종목이 실패해도 나머지는 계속 진행
4. 명령줄 실행 진입점 제공

사용법:
    python main.py              # 일반 실행
    python main.py --debug      # 디버그 모드
    python main.py --dry-run    # 데이터만 받고 분석은 안 함

매매 원칙(분석에 반영됨):
- 신중한 진입: 급등주를 쫓지 않음, 이격도 > 5%면 매수 안 함
- 추세 매매: MA5>MA10>MA20 정배열일 때만 매매
- 효율 우선: 매물이 한곳에 잘 모인 종목에 주목
- 선호 매수 시점: 거래량이 줄며 MA5/MA10 지지선까지 눌릴 때
"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from dotenv import dotenv_values
from src.config import setup_env

_INITIAL_PROCESS_ENV = dict(os.environ)
setup_env()

# 프록시 설정 - USE_PROXY 환경 변수로 켜고 끔, 기본값은 꺼짐
# GitHub Actions 환경에서는 프록시 설정을 자동으로 건너뜀
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    # 로컬 개발 환경: 프록시 사용(.env에서 PROXY_HOST와 PROXY_PORT 설정 가능)
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

_packaged_import_probe = os.getenv("DSA_PACKAGED_IMPORT_PROBE")
if _packaged_import_probe:
    import importlib
    import sys

    try:
        probe_module = importlib.import_module(_packaged_import_probe)
        if _packaged_import_probe == "py_mini_racer":
            # Importing the Python wrapper does not load V8 or its data files.
            # Exercise the installed runtime to detect missing/mismatched assets.
            engine = probe_module.MiniRacer()
            try:
                if engine.eval("1 + 1") != 2:
                    raise RuntimeError("MiniRacer JavaScript evaluation failed")
            finally:
                close = getattr(engine, "close", None)
                if callable(close):
                    close()
        elif _packaged_import_probe == "src.agent.factory":
            # Build the agent tool registry so tool modules that read package
            # data at import time (e.g. the FXMacroData operation catalogue)
            # are exercised in the frozen artifact.
            registry = probe_module.get_tool_registry()
            if not any(name.startswith("fxmacrodata_") for name in registry.list_names()):
                raise RuntimeError("FXMacroData tools are missing from the agent tool registry")
    except Exception as exc:
        print(
            f"ERROR: packaged runtime probe failed for {_packaged_import_probe}: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"OK: packaged import succeeded for {_packaged_import_probe}")
    sys.exit(0)

import argparse
import logging
import sys
import time
import uuid
from datetime import date, datetime, timezone, timedelta

from src.webui_frontend import prepare_webui_frontend_assets
from src.config import get_config, Config
from src.logging_config import setup_logging
from src.brokers.futu.portfolio import FutuPortfolioError
from src.core.analysis_run_marker import (
    record_analysis_run_marker,
    should_skip_startup_immediate_run,
)
from data_provider.base import canonical_stock_code
from src.services.stock_list_parser import (
    AnalysisTarget,
    ParseStatus,
    parse_analysis_target,
    split_stock_list,
)
from src.services.stock_code_utils import resolve_index_stock_code_for_analysis


logger = logging.getLogger(__name__)
_RUNTIME_ENV_FILE_KEYS = set()
_PUBLIC_BIND_HOSTS = frozenset({"0.0.0.0", "::", "[::]", "*"})
_LAST_ANALYSIS_FAILURE_REASON: Optional[str] = None


def _get_active_env_path() -> Path:
    env_file = os.getenv("ENV_FILE")
    if env_file:
        return Path(env_file)
    return Path(__file__).resolve().parent / ".env"


def _is_public_bind_host(host: str) -> bool:
    return (host or "").strip().lower() in _PUBLIC_BIND_HOSTS


def _warn_if_public_webui_without_auth(host: str) -> None:
    if not _is_public_bind_host(host):
        return

    from src.auth import is_auth_enabled

    if is_auth_enabled():
        return
    logger.warning(
        "WEBUI_HOST=%s binds the Web UI to a public interface while "
        "ADMIN_AUTH_ENABLED=false. Keep this service behind a trusted network "
        "boundary or enable admin authentication before exposing it.",
        host,
    )


def _resolve_web_service_bind(args: argparse.Namespace, config: Config) -> Tuple[str, int]:
    """Resolve the effective Web/API bind address from CLI first, then config."""
    host = args.host if args.host is not None else (config.webui_host or "127.0.0.1")
    port = args.port if args.port is not None else config.webui_port
    return host, port


def _read_active_env_values() -> Optional[Dict[str, str]]:
    env_path = _get_active_env_path()
    if not env_path.exists():
        return {}

    try:
        values = dotenv_values(env_path)
    except Exception as exc:  # pragma: no cover - defensive branch
        logger.warning("설정 파일 %s 읽기 실패, 현재 환경 변수를 그대로 사용합니다: %s", env_path, exc)
        return None

    return {
        str(key): "" if value is None else str(value)
        for key, value in values.items()
        if key is not None
    }


_ACTIVE_ENV_FILE_VALUES = _read_active_env_values() or {}
_RUNTIME_ENV_FILE_KEYS = {
    key for key in _ACTIVE_ENV_FILE_VALUES
    if key not in _INITIAL_PROCESS_ENV
}

# setup_env() already ran at import time above.
_env_bootstrapped = True


def _bootstrap_environment() -> None:
    """Load .env and apply optional local proxy settings.

    Guarded to be idempotent so it can safely be called from lazy-import
    paths used by API / bot consumers.
    """
    global _env_bootstrapped
    if _env_bootstrapped:
        return

    from src.config import setup_env

    setup_env()

    if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
        proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
        proxy_port = os.getenv("PROXY_PORT", "10809")
        proxy_url = f"http://{proxy_host}:{proxy_port}"
        os.environ["http_proxy"] = proxy_url
        os.environ["https_proxy"] = proxy_url

    _env_bootstrapped = True


def _setup_bootstrap_logging(debug: bool = False) -> None:
    """Initialize stderr-only logging before config is loaded.

    File handlers are deferred until ``config.log_dir`` is known (via the
    subsequent ``setup_logging()`` call) so that healthy runs never create
    log files in a hard-coded directory.
    """
    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)
    if not any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) is sys.stderr
        for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        root.addHandler(handler)


def _setup_runtime_logging(log_dir: str, debug: bool = False) -> bool:
    """Switch to configured logging, falling back to console on file I/O errors."""
    try:
        setup_logging(log_prefix="stock_analysis", debug=debug, log_dir=log_dir)
        return True
    except OSError as exc:
        logger.warning(
            "文件日志初始化失败，已降级为控制台日志输出；日志目录 %r 当前不可写或不可创建: %s。"
            "官方 Docker 镜像启动入口会自动修复默认挂载目录权限；若仍失败，"
            "请检查是否使用了 --user、只读挂载、rootless Docker 或 NFS 等限制写入的环境。",
            log_dir,
            exc,
        )
        return False


def _get_stock_analysis_pipeline():
    """Lazily import StockAnalysisPipeline for external consumers.

    Also ensures env/proxy bootstrap has run so that API / bot consumers
    that never call ``main()`` still get ``USE_PROXY`` applied.
    """
    _bootstrap_environment()
    from src.core.pipeline import StockAnalysisPipeline as _Pipeline

    return _Pipeline


class _LazyPipelineDescriptor:
    """Descriptor that resolves StockAnalysisPipeline on first attribute access."""

    _resolved = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        if self._resolved is None:
            self._resolved = _get_stock_analysis_pipeline()
        return self._resolved


class _ModuleExports:
    StockAnalysisPipeline = _LazyPipelineDescriptor()


_exports = _ModuleExports()


def __getattr__(name: str):
    if name == "StockAnalysisPipeline":
        return _exports.StockAnalysisPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def _reload_env_file_values_preserving_overrides() -> None:
    """Refresh `.env`-managed env vars without clobbering process env overrides."""
    global _RUNTIME_ENV_FILE_KEYS

    latest_values = _read_active_env_values()
    if latest_values is None:
        return

    managed_keys = {
        key for key in latest_values
        if key not in _INITIAL_PROCESS_ENV
    }

    for key in _RUNTIME_ENV_FILE_KEYS - managed_keys:
        os.environ.pop(key, None)

    for key in managed_keys:
        os.environ[key] = latest_values[key]

    _RUNTIME_ENV_FILE_KEYS = managed_keys


def parse_arguments() -> argparse.Namespace:
    """명령줄 인자 해석"""
    parser = argparse.ArgumentParser(
        description='A주 관심종목 AI 분석 시스템',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
예시:
  python main.py                    # 일반 실행
  python main.py --debug            # 디버그 모드
  python main.py --dry-run          # 데이터만 받고 AI 분석은 안 함
  python main.py --stocks 600519,000001  # 지정한 종목만 분석
  python main.py --stocks sh000016,000300.CSI,930955.CSI  # 등록된 지수 분석(sh/sz 접두사 또는 .CSI 별칭)
  python main.py --portfolio futu   # Futu 실제 보유 주식 사용(--stocks 무시)
  python main.py --no-notify        # 알림 보내지 않음
  python main.py --check-notify     # 알림 설정만 점검, 알림은 보내지 않음
  python main.py --single-notify    # 종목별 알림 모드(한 종목 분석이 끝날 때마다 바로 알림)
  python main.py --schedule         # 예약 실행 모드
  python main.py --market-review    # 시장 전체 리뷰만 실행
  python main.py --etf-rotation     # ETF 로테이션: 최신 신호 + 규칙 백테스트 보고서
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='디버그 모드 켜기, 자세한 로그 출력'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='데이터만 받고 AI 분석은 하지 않음'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='분석할 종목 코드, 쉼표로 구분(설정 파일보다 우선). 등록된 지수도 가능: sh/sz 접두사(예: sh000016) 또는 .CSI 별칭(예: 000300.CSI, 930955.CSI)'
    )

    parser.add_argument(
        '--portfolio',
        type=str.lower,
        choices=('futu',),
        help='증권사 실제 보유 종목을 종목 목록으로 사용. 현재 futu만 지원하며 --stocks/STOCK_LIST보다 우선'
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='알림 보내지 않음'
    )

    parser.add_argument(
        '--check-notify',
        action='store_true',
        help='알림 채널 설정만 읽어서 점검, 알림은 보내지 않음'
    )

    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='종목별 알림 모드: 모아서 보내지 않고 한 종목 분석이 끝날 때마다 바로 알림'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='동시 실행 스레드 수(기본값은 설정 값)'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='예약 실행 모드: 매일 정해진 시간에 실행'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='예약 실행 시작 시 바로 한 번 실행하지 않음'
    )

    parser.add_argument(
        '--market-review',
        action='store_true',
        help='시장 전체 리뷰 분석만 실행'
    )

    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='시장 전체 리뷰 분석 건너뛰기'
    )

    parser.add_argument(
        '--force-run',
        action='store_true',
        help='거래일 확인을 건너뛰고 전체 분석을 강제로 실행(Issue #373)'
    )

    parser.add_argument(
        '--webui',
        action='store_true',
        help='웹 관리 화면 실행'
    )

    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='웹 서비스만 실행, 자동 분석은 안 함'
    )

    parser.add_argument(
        '--serve',
        action='store_true',
        help='FastAPI 백엔드 서비스 실행(분석 작업도 함께 실행)'
    )

    parser.add_argument(
        '--serve-only',
        action='store_true',
        help='FastAPI 백엔드 서비스만 실행, 자동 분석은 안 함'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='FastAPI 서비스 포트(기본값은 WEBUI_PORT, 설정이 없으면 8000)'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=None,
        help='FastAPI 서비스 접속 주소(기본값은 WEBUI_HOST, 설정이 없으면 127.0.0.1)'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='분석 컨텍스트 스냅샷을 저장하지 않음'
    )

    # === Backtest ===
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='백테스트 실행(과거 분석 결과 평가)'
    )

    parser.add_argument(
        '--backtest-code',
        type=str,
        default=None,
        help='지정한 종목 코드만 백테스트'
    )

    parser.add_argument(
        '--backtest-days',
        type=int,
        default=None,
        help='백테스트 평가 기간(거래일 수, 기본값은 설정 값)'
    )

    parser.add_argument(
        '--backtest-force',
        action='store_true',
        help='백테스트 강제 실행(이미 결과가 있어도 다시 계산)'
    )

    # === ETF Rotation ===
    parser.add_argument(
        '--etf-rotation',
        action='store_true',
        help='ETF 로테이션 실행: 최신 리밸런싱 신호와 규칙 백테스트 보고서 출력(LLM 호출 없음, 설정은 ETF_ROTATION_* 참고)'
    )

    return parser.parse_args()


def _compute_trading_day_filter(
    config: Config,
    args: argparse.Namespace,
    stock_codes: List[str],
) -> Tuple[List[str], Optional[str], bool]:
    """
    Compute filtered stock list and effective market review region (Issue #373).

    Returns:
        (filtered_codes, effective_region, should_skip_all)
        - effective_region None = use config default (check disabled)
        - effective_region '' = all relevant markets closed, skip market review
        - should_skip_all: skip entire run when no stocks and no market review to run
    """
    force_run = getattr(args, 'force_run', False)
    if force_run or not getattr(config, 'trading_day_check_enabled', True):
        return (stock_codes, None, False)

    from src.core.trading_calendar import (
        get_market_for_stock,
        get_open_markets_today,
        compute_effective_region,
    )

    open_markets = get_open_markets_today()
    filtered_codes = []
    for code in stock_codes:
        mkt = get_market_for_stock(code)
        if mkt is None:
            # 지수 code(예: sh000016/csi930955/930955.CSI)는 get_market_for_stock 결과가
            # None이라서, 그냥 fail-open으로 남기면 A주 휴장일에도 지수가 걸러지지 않아
            # 종목별 거래일 규칙이 깨진다. 시장을 모르는 code는 parse_analysis_target으로
            # 종류를 판별해, 등록된 지수는 market=cn으로 CN 거래일 필터를 거친다. 그래도 모르는 비지수
            # code는 계속 fail-open으로 남긴다.
            target = parse_analysis_target(code)
            if target.asset_type == ParseStatus.INDEX:
                mkt = "cn"
        if mkt in open_markets or mkt is None:
            filtered_codes.append(code)

    if config.market_review_enabled and not getattr(args, 'no_market_review', False):
        effective_region = compute_effective_region(
            getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
        )
    else:
        effective_region = None

    should_skip_all = (not filtered_codes) and (effective_region or '') == ''
    return (filtered_codes, effective_region, should_skip_all)


def _classify_stock_list_tokens(
    tokens: List[str],
    *,
    entry_label: str,
) -> Optional[Tuple[List[str], List[AnalysisTarget]]]:
    """Classify stock-list tokens into aligned ``(stock_codes, analysis_targets)``.

    Shared by the one-shot ``--stocks`` entry and the GitHub Actions
    ``STOCK_LIST`` entry: explicit index tokens resolve through
    ``parse_analysis_target`` and keep their index canonical, while every
    other token keeps the legacy ``resolve_index_stock_code_for_analysis``
    path. ``unsupported`` tokens (e.g. an unregistered ``.CSI``) reject the
    whole run up-front with an explicit error — provider calls are never
    reached for any token in the batch. Returns ``None`` after logging the
    rejection, so callers exit without running analysis.
    """
    targets = [parse_analysis_target(t) for t in tokens]
    unsupported = [
        (token, target.unsupported_reason or "unsupported target")
        for token, target in zip(tokens, targets)
        if target.asset_type == ParseStatus.UNSUPPORTED
    ]
    if unsupported:
        token, reason = unsupported[0]
        logger.error(
            "%s 包含不支持的目标 %r：%s；本轮不执行任何分析。",
            entry_label,
            token,
            reason,
        )
        return None
    stock_codes = [
        t.canonical_id
        if t.asset_type == ParseStatus.INDEX
        else resolve_index_stock_code_for_analysis(raw)
        for t, raw in zip(targets, tokens)
    ]
    return stock_codes, targets


def _run_market_review_with_shared_lock(
    config: Config,
    run_market_review_func: Callable[..., Any],
    **kwargs: Any,
) -> Any:
    from src.core.market_review_lock import (
        release_market_review_lock,
        try_acquire_market_review_lock,
    )

    lock_token = try_acquire_market_review_lock(config)
    if lock_token is None:
        logger.warning("시장 전체 리뷰가 이미 실행 중이라 이번 리뷰는 건너뜁니다")
        return None

    try:
        params = dict(kwargs)
        params.setdefault("config", config)
        return run_market_review_func(**params)
    finally:
        release_market_review_lock(lock_token)


def _is_multi_market_region(region: str) -> bool:
    normalized = str(region or "").strip().lower()
    if not normalized:
        return False
    if normalized == "both":
        return True
    parts = {item.strip() for item in normalized.split(",") if item.strip()}
    return len(parts) > 1


def _refresh_stock_index_cache_for_analysis(config: Config) -> None:
    """Best-effort stock-index refresh for CLI/scheduled analysis paths."""
    try:
        from src.services.stock_index_remote_service import (
            refresh_remote_stock_index_cache,
            settings_from_config,
        )

        result = refresh_remote_stock_index_cache(settings_from_config(config))
        if result.refreshed:
            logger.info("[stock-index] 분석 전에 종목 인덱스 캐시를 새로 고쳤습니다: %s", result.cache_path)
        elif result.error:
            logger.debug("[stock-index] 분석 전 새로 고침이 끝나지 않아 로컬 인덱스를 그대로 씁니다: %s", result.error)
    except Exception as exc:  # noqa: BLE001 - stock index freshness must not block analysis.
        logger.warning("[stock-index] 분석 전 종목 인덱스 새로 고침 실패, 분석은 계속합니다: %s", exc)


def _resolve_portfolio_stock_codes(args: argparse.Namespace) -> Optional[List[str]]:
    """Resolve an optional broker portfolio into the analysis stock list."""
    portfolio = str(getattr(args, "portfolio", "") or "").strip().lower()
    if not portfolio:
        return None
    if portfolio != "futu":  # argparse prevents this for CLI callers; keep API callers safe.
        raise ValueError(f"지원하지 않는 portfolio: {portfolio}")

    from src.brokers.futu.portfolio import load_futu_stock_codes

    stock_codes = [
        canonical_stock_code(code)
        for code in load_futu_stock_codes()
        if (code or "").strip()
    ]
    logger.info("portfolio=futu가 stocks/STOCK_LIST를 대신합니다, 실제 보유 주식 %d개 사용", len(stock_codes))
    return stock_codes


def _resolve_gate_expected_stock_codes(
    config: Config,
    args: argparse.Namespace,
    *,
    stock_codes: Optional[List[str]] = None,
) -> Tuple[Optional[List[str]], Optional[str]]:
    """Resolve the startup dedup gate's expected list like the run entry.

    Mirrors ``run_full_analysis``' real target resolution (Futu portfolio
    first, then the ``STOCK_LIST`` .env hot-reload, then the trading-day
    filter) so the skip decision uses what THIS startup would actually
    analyze instead of a possibly stale ``config.stock_list`` snapshot
    (second-round review blockers OR-COR-e59aed48 / OR-COR-c4971c31).

    The result is a snapshot taken at gate time: if the portfolio or the
    .env watchlist changes strictly after this resolution but before the
    run re-resolves them, the gate may miss that and a new target waits
    for the next scheduled run. The drift direction still never skips a
    run that would cover more than recorded (fail-open), and the residual
    race window is a single task invocation.

    Returns ``(expected_codes, fail_open_reason)``:

    - Portfolio mode: the trading-day-filtered live position codes. An
      empty filtered list (no positions / no open market) can never prove
      coverage, so it returns a fail-open reason instead — the run itself
      decides downstream, the gate never skips on it.
    - Non-portfolio mode: mirrors the run's refresh condition verbatim
      (``stock_codes is None`` on the schedule path; the refresh is
      idempotent on the same config object the run reuses) and keeps the
      existing semantics for an empty config watchlist (pure-review dedup).
    - Any resolution failure fails open too: ``None`` expected codes plus a
      reason string for the gate log. Never miss a run outranks never
      re-run.
    """
    try:
        portfolio_stock_codes = _resolve_portfolio_stock_codes(args)
        if portfolio_stock_codes is not None:
            filtered_codes, _, _ = _compute_trading_day_filter(
                config, args, portfolio_stock_codes
            )
            if not filtered_codes:
                return (None, "portfolio mode resolved no tradable targets")
            return (filtered_codes, None)

        # Issue #529: keep this condition verbatim-identical to
        # run_full_analysis — hot-reload STOCK_LIST from .env before a
        # config-list run. The gate and the run share the same config
        # object, so this refresh converges to what the run would do anyway.
        if stock_codes is None:
            config.refresh_stock_list()
        effective_codes = (
            stock_codes
            if stock_codes is not None
            else getattr(config, "stock_list", None) or []
        )
        filtered_codes, _, _ = _compute_trading_day_filter(
            config, args, effective_codes
        )
        return (filtered_codes, None)
    except Exception as exc:  # noqa: BLE001 - the gate must never block a run
        return (None, f"target resolution failed: {exc}")


def _prime_daily_market_context(
    config: Config,
    pipeline: Any,
    *,
    region: str,
    no_market_review: bool,
    allow_generate: bool,
    force_refresh: bool = False,
    target_date: Optional[date] = None,
    return_full_report: bool = False,
    require_current_query_match: bool = False,
) -> Union[str, Tuple[str, str]]:
    """Load/reuse the run's market context, avoiding unbounded background generation."""
    if no_market_review or not region:
        return ("", "") if return_full_report else ""

    from src.services.daily_market_context import DailyMarketContextService

    if not _is_multi_market_region(region):
        service = getattr(pipeline, "_daily_market_context_service", None)
        if service is None:
            service = DailyMarketContextService(db_manager=pipeline.db)
            pipeline._daily_market_context_service = service
    else:
        service = DailyMarketContextService(db_manager=pipeline.db)

    get_context_kwargs = {
        "region": region,
        "config": config,
        "notifier": pipeline.notifier,
        "analyzer": pipeline.analyzer,
        "search_service": pipeline.search_service,
        "force_refresh": force_refresh,
        "allow_generate": allow_generate,
        "persist_market_review_history": False,
        "target_date": target_date,
        "require_query_id_match": require_current_query_match,
    }
    current_query_id = getattr(pipeline, "query_id", None)
    if isinstance(current_query_id, str) and current_query_id.strip():
        get_context_kwargs["current_query_id"] = current_query_id

    context = service.get_context(**get_context_kwargs)
    if context is None:
        return ("", "") if return_full_report else ""

    # Runtime context generation is preload-only and must not replace the full
    # market review run, except the query-scoped fallback after that run fails.
    if context.source != "analysis_history" and not (
        require_current_query_match and context.source == "market_review_runtime"
    ):
        return ("", "") if return_full_report else ""

    summary = str(getattr(context, "summary", ""))
    full_report = str(getattr(context, "full_report", "") or "")
    if return_full_report:
        return summary, full_report
    return summary


def _can_reuse_market_context_for_review(summary: str, region: str) -> bool:
    if not summary:
        return False
    normalized = str(region or "").strip().lower()
    if normalized == "both":
        return False
    parts = {item.strip() for item in normalized.split(",") if item.strip()}
    return len(parts) <= 1


def _resolve_daily_market_context_market(market: str, normalized_region: str) -> str:
    if "," not in normalized_region:
        return market
    parts = [item.strip() for item in normalized_region.split(",") if item.strip()]
    if parts and all(item in {"jp", "kr"} for item in parts):
        return parts[0]
    return market


def _resolve_daily_market_context_target_date(
    region: str,
    current_time: datetime,
) -> date:
    normalized_region = str(region or "cn").strip().lower()
    market = normalized_region if normalized_region in {"cn", "hk", "us", "jp", "kr"} else "cn"

    from src.core.trading_calendar import get_effective_trading_date

    return get_effective_trading_date(
        _resolve_daily_market_context_market(market, normalized_region),
        current_time=current_time,
    )


def _market_review_report_text(review_result: Any) -> str:
    if review_result is None:
        return ""
    report = getattr(review_result, "report", None)
    if isinstance(report, str):
        return report
    return review_result if isinstance(review_result, str) else ""


def _save_reused_market_review_report(
    notifier: Any,
    market_report: str,
    *,
    config: Config,
    trigger_source: str,
    region: str,
) -> None:
    body = str(market_report or "").strip()
    if not body:
        return
    title = (
        "# 🎯 Market Review"
        if str(getattr(config, "report_language", "zh")).strip().lower() == "en"
        else "# 🎯 大盘复盘"
    )
    if not any(body.startswith(item) for item in ("# 🎯 大盘复盘", "# 🎯 Market Review")):
        body = f"{title}\n\n{body}"
    try:
        date_str = datetime.now().strftime('%Y%m%d')
        report_filename = f"market_review_{date_str}.md"
        filepath = notifier.save_report_to_file(body, report_filename)
        logger.info(
            "[MarketReview] component=market_review action=save_reused_report "
            "trigger_source=%s region=%s path=%s",
            trigger_source,
            region,
            filepath,
        )
    except Exception as exc:
        logger.warning("시장 컨텍스트를 재사용해 시장 리뷰 보고서를 저장하지 못했습니다: %s", exc)


def _run_auto_backtest(config: Config) -> None:
    """Run the independently configured auto-backtest without failing analysis."""

    try:
        if not getattr(config, 'backtest_enabled', False):
            return

        from src.services.backtest_service import BacktestService

        logger.info("자동 백테스트 시작...")
        service = BacktestService()
        stats = service.run_backtest(
            force=False,
            eval_window_days=getattr(config, 'backtest_eval_window_days', 10),
            min_age_days=getattr(config, 'backtest_min_age_days', 14),
            limit=200,
        )
        logger.info(
            f"자동 백테스트 완료: processed={stats.get('processed')} "
            f"saved={stats.get('saved')} completed={stats.get('completed')} "
            f"insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
        )
    except Exception as exc:
        logger.warning(f"자동 백테스트 실패(무시함): {exc}")


def _all_stock_targets_succeeded(
    stock_codes: Optional[List[str]],
    results: List[Any],
) -> bool:
    """Return True only when every requested stock target produced a result.

    ``StockAnalysisPipeline.run`` returns just the successful results, so
    run completeness is "every requested code shows up in the results".
    Both sides normalize to ``str(code)`` — exactly the normalization the
    run marker's ``stock_codes`` field uses — and order/duplicates are
    ignored. An empty target list is a vacuous success (pure-review
    deployments keep their same-day dedup). Market-review completeness is
    deliberately NOT part of this check: a failing review must never
    resurrect the restart loop the dedup gate fixes (the daily run
    backfills it).
    """
    try:
        requested = {str(code) for code in (stock_codes or [])}
        produced = {
            str(getattr(result, "code", "")) for result in (results or [])
        }
        return requested.issubset(produced)
    except Exception:  # pragma: no cover - defensive: a bookkeeping error
        # must never break the analysis run; not recording the marker just
        # makes the next startup re-run (fail-open).
        return False


def run_full_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
    *,
    raise_errors: bool = False,
    analysis_targets: Optional[List[AnalysisTarget]] = None,
    refresh_watchlist: bool = True,
) -> bool:
    """
    전체 분석 과정 실행(개별 종목 + 시장 전체 리뷰)

    예약 실행이 부르는 메인 함수. Futu 보유 종목 해석 실패는 항상 호출한 쪽으로 전달된다.
    ``raise_errors`` 는 보유 종목 해석이 성공한 뒤 분석 과정의 예외 처리 방식만 정한다.
    ``analysis_targets`` 는 ``stock_codes``와 순서가 같고, 구조화된 분석 대상을 담는다
    (지수 대상은 market=cn과 기능 매트릭스를 정하는 데 쓰인다).
    ``refresh_watchlist=False`` 는 이미 원자적으로 확보한 예약 스냅샷에만 쓰며, 확보 후 다시 핫 업데이트되는 것을 막는다.
    """
    # Capture the entry-level stock list for the run-marker scope: the local
    # ``stock_codes`` variable is later replaced by the trading-day filter and
    # Futu positions, so it must never feed the dedup decision (the marker
    # fingerprint always comes from config.stock_list on both sides).
    entry_stock_codes = stock_codes
    # Portfolio resolution is its own CLI contract boundary. A broker import
    # failure must reach the one-shot caller, while all later work keeps the
    # existing run_full_analysis return-value semantics.
    portfolio_stock_codes = _resolve_portfolio_stock_codes(args)
    portfolio_is_empty = portfolio_stock_codes == []
    market_review_requested = (
        getattr(config, 'market_review_enabled', False)
        and not getattr(args, 'no_market_review', False)
    )
    if portfolio_is_empty and not market_review_requested:
        logger.info(
            "真实账户中无符合条件的 Futu 持仓，"
            "本轮跳过个股分析和大盘复盘。"
        )
        _run_auto_backtest(config)
        return True

    # Import pipeline modules outside the broad try/except so that import-time
    # failures propagate to the caller instead of being silently swallowed.
    from src.core.market_review import run_market_review
    from src.core.pipeline import StockAnalysisPipeline

    global _LAST_ANALYSIS_FAILURE_REASON
    _LAST_ANALYSIS_FAILURE_REASON = None

    def _return_with_auto_backtest(result: bool) -> bool:
        _run_auto_backtest(config)
        return result

    try:
        _refresh_stock_index_cache_for_analysis(config)
        if portfolio_stock_codes is not None:
            stock_codes = portfolio_stock_codes
            analysis_targets = None

        # Issue #529: Hot-reload STOCK_LIST from .env on each scheduled run
        if stock_codes is None and portfolio_stock_codes is None and refresh_watchlist:
            config.refresh_stock_list()

        using_config_stock_list = stock_codes is None and portfolio_stock_codes is None
        effective_codes = stock_codes if stock_codes is not None else config.stock_list
        # Fail fast on an empty persisted watchlist before trading-day filtering.
        # Otherwise should_skip=True would mask the configuration error as success.
        if (
            not getattr(args, "dry_run", False)
            and using_config_stock_list
            and not effective_codes
            and not market_review_requested
        ):
            _LAST_ANALYSIS_FAILURE_REASON = "empty_stock_list"
            logger.error(
                "이번 분석에서 보고서가 만들어지지 않았습니다: STOCK_LIST가 비어 있고 시장 전체 리뷰도 꺼져 있습니다."
            )
            return _return_with_auto_backtest(False)

        # Issue #373: Trading day filter (per-stock, per-market)
        filtered_codes, effective_region, should_skip = _compute_trading_day_filter(
            config, args, effective_codes
        )
        if should_skip:
            if portfolio_is_empty:
                logger.info(
                    "真实账户中无符合条件的 Futu 持仓，"
                    "本轮无需执行个股分析或大盘复盘，跳过执行。"
                )
            else:
                logger.info(
                    "今日所有相关市场均为非交易日，跳过执行。"
                    "可使用 --force-run 强制执行。"
                )
            return True
        if set(filtered_codes) != set(effective_codes):
            skipped = set(effective_codes) - set(filtered_codes)
            logger.info("오늘 휴장인 종목은 건너뜀: %s", skipped)
        if analysis_targets is not None:
            if len(analysis_targets) != len(effective_codes):
                raise ValueError("analysis_targets must align with stock_codes")
            remaining_pairs = list(zip(effective_codes, analysis_targets))
            filtered_targets = []
            for filtered_code in filtered_codes:
                for index, (code, target) in enumerate(remaining_pairs):
                    if code == filtered_code:
                        filtered_targets.append(target)
                        remaining_pairs.pop(index)
                        break
            analysis_targets = filtered_targets
        stock_codes = filtered_codes
        skip_futu_stock_analysis = (
            portfolio_stock_codes is not None and not stock_codes
        )

        # 명령줄 인자 --single-notify가 설정보다 우선(#55)
        if getattr(args, 'single_notify', False):
            config.single_stock_notify = True

        # Issue #190: 개별 종목과 시장 전체 리뷰를 한 번에 알림
        merge_notification = (
            getattr(config, 'merge_email_notification', False)
            and config.market_review_enabled
            and not getattr(args, 'no_market_review', False)
            and not config.single_stock_notify
        )

        # 스케줄러 만들기
        save_context_snapshot = None
        if getattr(args, 'no_context_snapshot', False):
            save_context_snapshot = False
        query_id = uuid.uuid4().hex
        market_review_region = (
            effective_region
            if effective_region is not None
            else (getattr(config, 'market_review_region', 'cn') or 'cn')
        )
        should_run_market_review = (
            config.market_review_enabled
            and not args.no_market_review
            and (market_review_region or '') != ''
        )
        if (
            not getattr(args, "dry_run", False)
            and not stock_codes
            and using_config_stock_list
            and not should_run_market_review
        ):
            _LAST_ANALYSIS_FAILURE_REASON = "empty_stock_list"
            logger.error(
                "이번 분석에서 보고서가 만들어지지 않았습니다: STOCK_LIST가 비어 있고 시장 전체 리뷰도 꺼져 있습니다."
            )
            return _return_with_auto_backtest(False)
        should_use_daily_market_context = (
            should_run_market_review
            and getattr(config, 'daily_market_context_enabled', True)
        )
        analysis_reference_time = datetime.now(timezone.utc)
        daily_market_context_target_date = None
        if should_use_daily_market_context:
            daily_market_context_target_date = _resolve_daily_market_context_target_date(
                market_review_region,
                analysis_reference_time,
            )
        market_report = ""
        market_context_summary = ""
        market_context_full_report = ""
        market_context_generated_during_stock = False
        pipeline = StockAnalysisPipeline(
            config=config,
            max_workers=args.workers,
            query_id=query_id,
            query_source="cli",
            save_context_snapshot=save_context_snapshot,
            daily_market_context_enabled=should_use_daily_market_context,
            daily_market_context_allow_generate=should_use_daily_market_context,
        )
        if should_use_daily_market_context:
            # Prompt-side context can reuse historical summaries, while full-merge
            # content must avoid silently reusing unrelated historical reports.
            _prime_daily_market_context(
                config,
                pipeline=pipeline,
                region=market_review_region,
                no_market_review=args.no_market_review,
                allow_generate=False,
                target_date=daily_market_context_target_date,
                return_full_report=False,
            )
            (
                market_context_summary,
                market_context_full_report,
            ) = _prime_daily_market_context(
                config,
                pipeline=pipeline,
                region=market_review_region,
                no_market_review=args.no_market_review,
                allow_generate=False,
                target_date=daily_market_context_target_date,
                return_full_report=True,
                require_current_query_match=True,
            )

        # 1. 개별 종목 분석 실행
        if skip_futu_stock_analysis:
            if portfolio_is_empty:
                logger.info("真实账户中无符合条件的 Futu 持仓，跳过个股分析。")
            else:
                logger.info("Futu 보유 종목을 거래일로 걸러 보니 분석할 종목이 없어 개별 종목 분석을 건너뜁니다.")
            results = []
        else:
            results = pipeline.run(
                stock_codes=stock_codes,
                dry_run=args.dry_run,
                send_notification=not args.no_notify,
                merge_notification=merge_notification,
                current_time=analysis_reference_time,
                analysis_targets=analysis_targets,
            )

        if should_use_daily_market_context and not market_context_summary:
            (
                market_context_summary,
                market_context_full_report,
            ) = _prime_daily_market_context(
                config,
                pipeline=pipeline,
                region=market_review_region,
                no_market_review=args.no_market_review,
                allow_generate=False,
                target_date=daily_market_context_target_date,
                return_full_report=True,
                require_current_query_match=True,
            )
            market_context_generated_during_stock = bool(market_context_summary)

        # Issue #128: 분석 간격 - 개별 종목 분석과 시장 분석 사이에 잠시 대기
        analysis_delay = getattr(config, 'analysis_delay', 0)

        # 2. 시장 전체 리뷰 실행(켜져 있고 개별 종목 전용 모드가 아닐 때)
        if should_run_market_review:
            schedule_mode = bool(
                getattr(args, 'schedule', False)
                or getattr(config, 'schedule_enabled', False)
            )
            review_trigger_source = "schedule" if schedule_mode else "cli"
            can_reuse_market_context = (
                _can_reuse_market_context_for_review(
                    market_context_summary,
                    market_review_region,
                )
                if should_use_daily_market_context
                else False
            )

            can_skip_market_review = (
                (merge_notification or market_context_generated_during_stock)
                and can_reuse_market_context
                and bool(market_context_full_report or market_context_summary)
            )
            if can_skip_market_review:
                market_report = market_context_full_report or market_context_summary
                logger.info(
                    "리뷰 컨텍스트를 재사용할 수 있어 시장 리뷰를 다시 돌리지 않고 기존 내용을 씁니다."
                )
                _save_reused_market_review_report(
                    pipeline.notifier,
                    market_report,
                    config=config,
                    trigger_source=review_trigger_source,
                    region=market_review_region,
                )
                if (
                    market_context_generated_during_stock
                    and not merge_notification
                    and not args.no_notify
                    and pipeline.notifier.is_available()
                ):
                    if pipeline.notifier.send(
                        f"# 📈 大盘复盘\n\n{market_report}",
                        email_send_to_all=True,
                        route_type="report",
                    ):
                        logger.info("이번 시장 컨텍스트를 재사용해 시장 리뷰 알림 전송 성공")
                    else:
                        logger.warning("이번 시장 컨텍스트를 재사용한 시장 리뷰 알림 전송 실패")

            review_result = None
            if not can_skip_market_review:
                if analysis_delay > 0:
                    logger.info(f"{analysis_delay}초 기다린 뒤 시장 전체 리뷰 실행(API 호출 제한 회피)...")
                    time.sleep(analysis_delay)

                review_result = _run_market_review_with_shared_lock(
                    config,
                    run_market_review,
                    notifier=pipeline.notifier,
                    analyzer=pipeline.analyzer,
                    search_service=pipeline.search_service,
                    send_notification=not args.no_notify,
                    merge_notification=merge_notification,
                    override_region=market_review_region,
                    query_id=query_id,
                    trigger_source=review_trigger_source,
                )
                # 리뷰가 아직 성공하지 못했다면 기록/캐시를 한 번 더 읽어 재사용(동시 실행 경합 방지).
                if not review_result and should_use_daily_market_context:
                    (
                        market_context_summary,
                        market_context_full_report,
                    ) = _prime_daily_market_context(
                        config,
                        pipeline=pipeline,
                        region=market_review_region,
                        no_market_review=args.no_market_review,
                        allow_generate=False,
                        target_date=daily_market_context_target_date,
                        return_full_report=True,
                        require_current_query_match=True,
                    )
                    can_reuse_market_context = _can_reuse_market_context_for_review(
                        market_context_summary,
                        market_review_region,
                    )
                elif not review_result:
                    can_reuse_market_context = False

            # 결과가 있으면 market_report에 담아 이후 Feishu 문서 생성에 사용
            if review_result:
                market_report = _market_review_report_text(review_result)
            elif can_reuse_market_context:
                market_report = market_context_full_report or market_context_summary

        expected_stock_report = (
            not getattr(args, "dry_run", False)
            and bool(stock_codes)
            and not skip_futu_stock_analysis
        )
        deferred_failure_result = None
        if expected_stock_report and results and not getattr(
            pipeline, "_last_local_report_path", None
        ):
            _LAST_ANALYSIS_FAILURE_REASON = "report_save_failed"
            save_error = getattr(pipeline, "_last_local_report_error", None) or "unknown error"
            logger.error(
                "이번 분석에서 개별 종목 결과는 나왔지만 종합 보고서 저장에 실패해 로컬 보고서 파일이 없습니다: %s",
                save_error,
            )
            deferred_failure_result = False
        expected_market_report = (
            not getattr(args, "dry_run", False)
            and should_run_market_review
        )
        if (expected_stock_report or expected_market_report) and not results and not market_report:
            _LAST_ANALYSIS_FAILURE_REASON = "no_report"
            logger.error(
                "이번 분석에서 보고서가 하나도 만들어지지 않았습니다: 예정된 개별 종목 분석과 시장 전체 리뷰 모두 결과가 없습니다."
            )
            return _return_with_auto_backtest(False)

        # Issue #190: 한 번에 알림(개별 종목 + 시장 전체 리뷰)
        if merge_notification and (results or market_report) and not args.no_notify:
            parts = []
            if market_report:
                parts.append(f"# 📈 大盘复盘\n\n{market_report}")
            if results:
                dashboard_content = pipeline.notifier.generate_aggregate_report(
                    results,
                    getattr(config, 'report_type', 'simple'),
                )
                parts.append(f"# 🚀 个股决策仪表盘\n\n{dashboard_content}")
            if parts:
                combined_content = "\n\n---\n\n".join(parts)
                if pipeline.notifier.is_available():
                    if pipeline.notifier.send(combined_content, email_send_to_all=True, route_type="report"):
                        logger.info("한 번에 알림 보냄(개별 종목 + 시장 전체 리뷰)")
                    else:
                        logger.warning("통합 알림 전송 실패")

        # 요약 출력
        if results:
            logger.info("\n===== 분석 결과 요약 =====")
            for r in sorted(results, key=lambda x: x.sentiment_score, reverse=True):
                emoji = r.get_emoji()
                logger.info(
                    f"{emoji} {r.name}({r.code}): {r.operation_advice} | "
                    f"점수 {r.sentiment_score} | {r.trend_prediction}"
                )

        logger.info("\n작업 완료")

        # === 추가: Feishu 클라우드 문서 생성 ===
        try:
            from src.feishu_doc import FeishuDocManager

            feishu_doc = FeishuDocManager()
            if feishu_doc.is_configured() and (results or market_report):
                logger.info("Feishu 클라우드 문서를 만드는 중...")

                # 1. 제목 준비 "01-01 13:01大盘复盘"
                tz_cn = timezone(timedelta(hours=8))
                now = datetime.now(tz_cn)
                doc_title = f"{now.strftime('%Y-%m-%d %H:%M')} 大盘复盘"

                # 2. 내용 준비(개별 종목 분석과 시장 전체 리뷰를 이어 붙임)
                full_content = ""

                # 시장 전체 리뷰 내용 추가(있으면)
                if market_report:
                    full_content += f"# 📈 大盘复盘\n\n{market_report}\n\n---\n\n"

                # 개별 종목 결정 대시보드 추가(NotificationService로 생성, report_type에 따라 분기)
                if results:
                    dashboard_content = pipeline.notifier.generate_aggregate_report(
                        results,
                        getattr(config, 'report_type', 'simple'),
                    )
                    full_content += f"# 🚀 个股决策仪表盘\n\n{dashboard_content}"

                # 3. 문서 만들기
                doc_url = feishu_doc.create_daily_doc(doc_title, full_content)
                if doc_url:
                    logger.info(f"Feishu 클라우드 문서 생성 성공: {doc_url}")
                    # 선택: 문서 링크도 그룹 채팅에 알림
                    if not args.no_notify:
                        pipeline.notifier.send(
                            f"[{now.strftime('%Y-%m-%d %H:%M')}] 리뷰 문서 생성 성공: {doc_url}",
                            route_type="report",
                        )

        except Exception as e:
            logger.error(f"Feishu 문서 생성 실패: {e}")

        final_result = (
            deferred_failure_result
            if deferred_failure_result is not None
            else True
        )
        # Startup daily dedup bookkeeping: only a genuinely successful AND
        # complete run records the marker — every requested stock target
        # must have produced a result (pipeline.run returns just the
        # successes, so partial failures shrink ``results``). Skip paths,
        # failures and partial-failure rounds must not record, otherwise a
        # restart would wrongly dedup away the missing stocks. The scope
        # reflects the entry-level stock list; the covered ``stock_codes``
        # are written verbatim (str(code), same normalization as the
        # completeness check); the stock-list fingerprint stays an
        # observability field computed inside the marker module.
        if (
            final_result is True
            and _all_stock_targets_succeeded(stock_codes, results)
            and not getattr(args, "dry_run", False)
        ):
            record_analysis_run_marker(
                config,
                scope="subset" if entry_stock_codes is not None else "full",
                stock_codes=stock_codes,
                market_review_requested=market_review_requested,
                market_review_completed=(
                    bool(market_report) if market_review_requested else None
                ),
                args=args,
            )
        return _return_with_auto_backtest(final_result)

    except Exception as e:
        if _LAST_ANALYSIS_FAILURE_REASON is None:
            _LAST_ANALYSIS_FAILURE_REASON = "runtime_error"
        logger.exception(f"분석 과정 실행 실패: {e}")
        if raise_errors:
            raise
        return False


def run_scheduled_analysis(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
) -> bool:
    """Run scheduled analysis with failures propagated to the scheduler."""
    scheduled_for = getattr(args, "_scheduled_for", None)
    if scheduled_for is None:
        return run_full_analysis(config, args, stock_codes, raise_errors=True)

    from src.services.scheduled_analysis_claim import run_claimed_scheduled_analysis

    return run_claimed_scheduled_analysis(
        config, args, scheduled_for,
        lambda snapshot: run_full_analysis(
            snapshot, args, stock_codes, raise_errors=True, refresh_watchlist=False,
        ),
    )


def _run_analysis_with_runtime_scheduler_lock(
    config: Config,
    args: argparse.Namespace,
    stock_codes: Optional[List[str]] = None,
    analysis_targets: Optional[List[AnalysisTarget]] = None,
) -> bool:
    from src.services.runtime_scheduler import run_with_global_analysis_lock

    task_result: Dict[str, bool] = {"ok": True}

    def _locked_task_runner(
        locked_config: Config,
        locked_args: argparse.Namespace,
        locked_stock_codes: Optional[List[str]] = None,
    ) -> bool:
        if analysis_targets is None:
            result = run_full_analysis(locked_config, locked_args, locked_stock_codes)
        else:
            result = run_full_analysis(
                locked_config,
                locked_args,
                locked_stock_codes,
                analysis_targets=analysis_targets,
            )
        task_result["ok"] = bool(result)
        return task_result["ok"]

    # Keep startup/triggered analysis in sync with API runtime scheduler and
    # run-now entrypoint. Blocking is expected here because startup paths should
    # wait for an in-flight job before returning a response.
    lock_acquired = run_with_global_analysis_lock(
        task_runner=_locked_task_runner,
        config=config,
        args=args,
        stock_codes=stock_codes,
        blocking=True,
    )
    return bool(lock_acquired and task_result["ok"])


def start_api_server(host: str, port: int, config: Config) -> None:
    """
    백그라운드 스레드에서 FastAPI 서비스 실행

    Args:
        host: 접속 주소
        port: 접속 포트
        config: 설정 객체
    """
    import socket
    import threading
    import uvicorn

    probe = socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
    except OSError as exc:
        raise RuntimeError(f"FastAPI port is not available: {host}:{port}") from exc
    finally:
        probe.close()

    level_name = (config.log_level or "INFO").lower()
    use_config_signal_handlers = True
    uvicorn_kwargs = {
        "host": host,
        "port": port,
        "log_level": level_name,
        "log_config": None,
    }
    # Import the ASGI app object in the calling thread instead of handing uvicorn
    # the "api.app:app" import string. With the string, uvicorn imports the app
    # lazily inside the server thread, and that import (litellm + the full app
    # tree, ~10s+ on constrained hosts) runs inside the startup probe window
    # below, tripping the 3.0s timeout and causing a restart loop on slower
    # machines. Importing first keeps the heavy work out of the probe window;
    # genuine import failures still surface immediately to the caller.
    from api.app import app as fastapi_app
    from api.middlewares.security_guard import uvicorn_proxy_kwargs

    uvicorn_kwargs.update(uvicorn_proxy_kwargs())

    try:
        uvicorn_config = uvicorn.Config(
            fastapi_app,
            install_signal_handlers=False,
            **uvicorn_kwargs,
        )
    except TypeError:
        # Older uvicorn versions do not accept install_signal_handlers in
        # Config; fall back and only disable signal handling via Server attribute
        # when it's a boolean flag.
        use_config_signal_handlers = False
        uvicorn_config = uvicorn.Config(
            fastapi_app,
            **uvicorn_kwargs,
        )
    uvicorn_server = uvicorn.Server(config=uvicorn_config)
    if not use_config_signal_handlers:
        install_signal_handlers = getattr(uvicorn_server, "install_signal_handlers", None)
        if isinstance(install_signal_handlers, bool):
            uvicorn_server.install_signal_handlers = False

    startup_error: list[BaseException] = []

    def run_server():
        try:
            uvicorn_server.run()
        except Exception as exc:  # noqa: BLE001 - surface startup issues to caller promptly
            startup_error.append(exc)

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()

    timeout_seconds = 3.0
    wait_deadline = time.time() + timeout_seconds
    while time.time() < wait_deadline:
        if startup_error:
            raise RuntimeError(
                f"FastAPI server failed to start: {host}:{port}; {startup_error[0]}"
            )
        if uvicorn_server.started:
            logger.info(f"FastAPI 서비스 시작됨: http://{host}:{port}")
            return
        if not thread.is_alive():
            break
        time.sleep(0.05)

    if startup_error:
        raise RuntimeError(f"FastAPI server failed to start: {host}:{port}; {startup_error[0]}")
    if uvicorn_server.started:
        logger.info(f"FastAPI 서비스 시작됨: http://{host}:{port}")
        return
    if not thread.is_alive():
        raise RuntimeError(f"FastAPI 서버가 시작하자마자 종료됨: {host}:{port}")

    raise RuntimeError(f"FastAPI 서비스가 {timeout_seconds:.1f}초 안에 시작을 마치지 못함: {host}:{port}")


def _is_truthy_env(var_name: str, default: str = "true") -> bool:
    """Parse common truthy / falsy environment values."""
    value = os.getenv(var_name, default).strip().lower()
    return value not in {"0", "false", "no", "off"}


def start_bot_stream_clients(config: Config) -> None:
    """Start bot stream clients when enabled in config."""
    # DingTalk Stream 클라이언트 실행
    if config.dingtalk_stream_enabled:
        try:
            from bot.platforms import start_dingtalk_stream_background, DINGTALK_STREAM_AVAILABLE
            if DINGTALK_STREAM_AVAILABLE:
                if start_dingtalk_stream_background():
                    logger.info("[Main] Dingtalk Stream client started in background.")
                else:
                    logger.warning("[Main] Dingtalk Stream client failed to start.")
            else:
                logger.warning("[Main] Dingtalk Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install dingtalk-stream")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Dingtalk Stream client: {exc}")

    # Feishu Stream 클라이언트 실행
    if getattr(config, 'feishu_stream_enabled', False):
        try:
            from bot.platforms import start_feishu_stream_background, FEISHU_SDK_AVAILABLE
            if FEISHU_SDK_AVAILABLE:
                if start_feishu_stream_background():
                    logger.info("[Main] Feishu Stream client started in background.")
                else:
                    logger.warning("[Main] Feishu Stream client failed to start.")
            else:
                logger.warning("[Main] Feishu Stream enabled but SDK is missing.")
                logger.warning("[Main] Run: pip install lark-oapi")
        except Exception as exc:
            logger.error(f"[Main] Failed to start Feishu Stream client: {exc}")


def _resolve_scheduled_stock_codes(stock_codes: Optional[List[str]]) -> Optional[List[str]]:
    """Scheduled runs should always read the latest persisted watchlist."""
    if stock_codes is not None:
        logger.warning(
            "定时模式下检测到 --stocks 参数；计划执行将忽略启动时股票快照，并在每次运行前重新读取最新的 STOCK_LIST。"
        )
    return None


def _skips_stock_entry(args: argparse.Namespace, config: Config) -> bool:
    """Whether the active mode consumes a stock list at all.

    Modes that do not analyze the watchlist must not parse/classify
    ``--stocks``/``STOCK_LIST`` tokens nor refresh the stock-index registry
    before the mode dispatch, otherwise an unsupported index token would
    wrongly block a run that never consumes it. Covered modes:
    ``--backtest``, ``--market-review``, ``--etf-rotation``, ``--serve-only``/``--webui-only``,
    ``--portfolio`` (any value) and ``--schedule``/``config.schedule_enabled``.
    ``--serve`` (not serve-only) and plain one-shot runs still consume the
    stock list and stay outside the guard. The webui-only flag is read
    directly here because the webui -> serve mapping happens only later in
    ``main()``.
    """
    return bool(
        getattr(args, "backtest", False)
        or getattr(args, "etf_rotation", False)
        or getattr(args, "market_review", False)
        or getattr(args, "serve_only", False)
        or getattr(args, "webui_only", False)
        or bool(getattr(args, "portfolio", None))
        or getattr(args, "schedule", False)
        or getattr(config, "schedule_enabled", False)
    )


def _reload_runtime_config() -> Config:
    """Reload config from the latest persisted `.env` values for scheduled runs."""
    _reload_env_file_values_preserving_overrides()
    Config.reset_instance()
    new_config = get_config()

    # Drop the module-level ToolRegistry so the next
    # ``build_agent_executor`` / ``build_agent_chat_executor`` call rebuilds
    # it against the freshly-loaded Config and picks up new
    # ``AGENT_*_TOOL_TIMEOUT_S`` overrides (Issue #1890). Wrap in try/except
    # so a future runtime reset helper cannot crash scheduled-job bootstrap.
    try:
        from src.agent.factory import reset_tool_registry

        reset_tool_registry()
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning("Failed to reset tool registry during config reload: %s", exc)

    return new_config


def _build_schedule_time_provider(default_schedule_time: str):
    """Read the latest schedule time directly from the active config file.

    Fallback order:
    1. Process-level env override (set before launch) → honour it.
    2. Persisted config file value (written by WebUI) → use it.
    3. Documented system default ``"18:00"`` → always fall back here so
       that clearing SCHEDULE_TIME in WebUI correctly resets the schedule.
    """
    from src.core.config_manager import ConfigManager

    _SYSTEM_DEFAULT_SCHEDULE_TIME = "18:00"
    manager = ConfigManager()

    def _provider() -> str:
        if "SCHEDULE_TIME" in _INITIAL_PROCESS_ENV:
            return os.getenv("SCHEDULE_TIME", default_schedule_time)

        config_map = manager.read_config_map()
        schedule_time = (config_map.get("SCHEDULE_TIME", "") or "").strip()
        if schedule_time:
            return schedule_time
        return _SYSTEM_DEFAULT_SCHEDULE_TIME

    return _provider


def _build_schedule_times_provider(default_schedule_time: str):
    """Read the latest SCHEDULE_TIMES with SCHEDULE_TIME fallback."""
    from src.core.config_manager import ConfigManager
    from src.scheduler import normalize_schedule_times

    _SYSTEM_DEFAULT_SCHEDULE_TIME = "18:00"
    manager = ConfigManager()

    def _provider():
        if "SCHEDULE_TIMES" in _INITIAL_PROCESS_ENV:
            return normalize_schedule_times(
                os.getenv("SCHEDULE_TIMES", ""),
                fallback_time=os.getenv("SCHEDULE_TIME", default_schedule_time),
            )
        if "SCHEDULE_TIME" in _INITIAL_PROCESS_ENV:
            return normalize_schedule_times(
                os.getenv("SCHEDULE_TIMES", ""),
                fallback_time=os.getenv("SCHEDULE_TIME", default_schedule_time),
            )

        config_map = manager.read_config_map()
        schedule_time = (config_map.get("SCHEDULE_TIME", "") or "").strip() or _SYSTEM_DEFAULT_SCHEDULE_TIME
        return normalize_schedule_times(
            config_map.get("SCHEDULE_TIMES", ""),
            fallback_time=schedule_time,
        )

    return _provider


def main() -> int:
    """
    메인 진입 함수

    Returns:
        종료 코드(0이면 성공)
    """
    # 명령줄 인자 해석
    args = parse_arguments()

    # 설정을 읽기 전에 bootstrap 로그부터 준비해, 초기 실패도 파일에 남도록 함
    try:
        _setup_bootstrap_logging(debug=args.debug)
    except Exception as exc:
        logging.basicConfig(
            level=logging.DEBUG if getattr(args, "debug", False) else logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stderr,
        )
        logger.warning("Bootstrap 로그 준비 실패, stderr로 대신 출력합니다: %s", exc)

    # 설정 불러오기(bootstrap logging 다음에 실행해 예외도 로그에 남김)
    try:
        config = get_config()
    except Exception as exc:
        logger.exception("加载配置失败: %s", exc)
        return 1

    # 로그 설정(콘솔과 파일에 출력)
    try:
        _setup_runtime_logging(config.log_dir, debug=args.debug)
    except Exception as exc:
        logger.exception("설정된 로그 폴더로 바꾸지 못했습니다: %s", exc)
        return 1

    logger.info("=" * 60)
    logger.info("A주 관심종목 AI 분석 시스템 시작")
    logger.info(f"실행 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    # 설정 확인
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)

    if getattr(args, "check_notify", False):
        from src.services.notification_diagnostics import (
            format_notification_diagnostics,
            run_notification_diagnostics,
        )

        result = run_notification_diagnostics(config)
        print(format_notification_diagnostics(result))
        return 0 if result.ok else 1

    # 종목 목록 해석(모두 대문자로 통일, Issue #355)
    # Story 1.5: 1회 실행용 --stocks 입력은 parse_analysis_target으로 구조화된
    # AnalysisTarget 목록을 만든다. 지수 대상(sh/sz/csi 접두사와 .CSI 별칭)은 입력 단계에서
    # 지수라는 정체를 유지하고, 지원하지 않는 대상(예: 미등록 .CSI)은 입력 단계에서 거절해 provider로 넘기지 않는다.
    # 종목 목록을 쓰지 않는 모드(백테스트/시장 리뷰/서비스 전용/portfolio/예약)는
    # 분류와 인덱스 새로 고침을 통째로 건너뛰어(_skips_stock_entry) 상관없는 잘못된 token이 모드를 막지 않게 한다.
    _skip_stock_entry = _skips_stock_entry(args, config)
    if args.stocks and getattr(args, "portfolio", None):
        logger.info("--portfolio도 함께 지정됨. 실제 분석 때는 portfolio가 --stocks보다 우선합니다")
    stock_codes = None
    analysis_targets = None
    if args.stocks and not _skip_stock_entry:
        # --stocks를 해석하기 전에 종목 인덱스 목록을 가능한 범위에서 새로 고쳐, 첫 실행에도
        # 새 별칭/정보가 반영되게 한다. 실패/시간 초과/비활성이어도 분석은 막지 않는다. --stocks 입력에만 필요하고,
        # 다른 모드는 run_full_analysis 안의 기존 새로 고침이 맡는다.
        _refresh_stock_index_cache_for_analysis(config)
        tokens = [c for c in split_stock_list(args.stocks) if (c or "").strip()]
        resolved = _classify_stock_list_tokens(tokens, entry_label="--stocks")
        if resolved is None:
            return 1
        stock_codes, analysis_targets = resolved
        logger.info(f"명령줄에서 지정한 종목 목록 사용: {stock_codes}")
    elif (
        os.getenv("GITHUB_ACTIONS") == "true"
        and not _skip_stock_entry
    ):
        # 매일 도는 워크플로(GITHUB_ACTIONS=true)가 인자 없이 `python main.py`를 실행할 때(full 또는
        # stocks-only 모드): STOCK_LIST token을 1회 실행용 --stocks와 같은 방식으로
        # 구조화된 target으로 분류한다. 명시된 지수 token은 지수 경로로, 개별 종목 token은 기존 경로로 간다.
        # 종목 목록을 쓰지 않는 모드는 _skips_stock_entry로 통째로 건너뛰고(새로 고침·분류 없음),
        # 로컬 기본 실행은 여기서 target을 만들지 않는다.
        raw_value = config.stock_list or []
        raw_tokens = (
            split_stock_list(raw_value)
            if isinstance(raw_value, str)
            else [str(c).strip() for c in raw_value if str(c or "").strip()]
        )
        raw_tokens = [c for c in raw_tokens if (c or "").strip()]
        if raw_tokens:
            _refresh_stock_index_cache_for_analysis(config)
            resolved = _classify_stock_list_tokens(
                raw_tokens, entry_label="GitHub Actions STOCK_LIST"
            )
            if resolved is None:
                return 1
            stock_codes, analysis_targets = resolved
            logger.info(f"GitHub Actions 기본 STOCK_LIST: {stock_codes}")

    # === --webui / --webui-only 인자를 --serve / --serve-only로 연결 ===
    if args.webui:
        args.serve = True
    if args.webui_only:
        args.serve_only = True

    # 예전 WEBUI_ENABLED 환경 변수도 지원
    if config.webui_enabled and not (args.serve or args.serve_only):
        args.serve = True

    # === 웹 서비스 실행(켜져 있으면) ===
    start_serve = (args.serve or args.serve_only) and os.getenv("GITHUB_ACTIONS") != "true"

    if start_serve:
        args.host, args.port = _resolve_web_service_bind(args, config)
        _warn_if_public_webui_without_auth(args.host)

    bot_clients_started = False
    if start_serve:
        from src.services.runtime_scheduler import (
            CLI_SCHEDULER_OWNER_ENV,
            RUNTIME_SCHEDULER_ARGS_ENV,
            RUNTIME_SCHEDULER_FORCE_ENABLED_ENV,
            RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV,
            RUNTIME_SCHEDULER_SUPPRESS_START_ENV,
        )

        # The API runtime scheduler owns schedules once the Web/API service starts.
        # This keeps Web settings, status, and run-now actions attached to the real
        # scheduler instead of a separate CLI loop.
        os.environ.pop(CLI_SCHEDULER_OWNER_ENV, None)
        os.environ.pop(RUNTIME_SCHEDULER_SUPPRESS_START_ENV, None)
        runtime_schedule_requested = args.schedule or config.schedule_enabled
        if args.schedule:
            os.environ[RUNTIME_SCHEDULER_FORCE_ENABLED_ENV] = "true"
        else:
            os.environ.pop(RUNTIME_SCHEDULER_FORCE_ENABLED_ENV, None)
        if runtime_schedule_requested:
            # ``--serve-only`` must restore persisted schedules, but it must not
            # turn service/Desktop startup into an immediate analysis run.
            runtime_run_immediately = (
                False if args.serve_only else config.schedule_run_immediately
            )
            if getattr(args, 'no_run_immediately', False):
                runtime_run_immediately = False
            os.environ[RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV] = (
                "true" if runtime_run_immediately else "false"
            )
        else:
            os.environ.pop(RUNTIME_SCHEDULER_RUN_IMMEDIATELY_ENV, None)
        runtime_scheduler_args = {
            "no_notify": bool(getattr(args, "no_notify", False)),
            "no_market_review": bool(getattr(args, "no_market_review", False)),
            "dry_run": bool(getattr(args, "dry_run", False)),
            "force_run": bool(getattr(args, "force_run", False)),
            "single_notify": bool(getattr(args, "single_notify", False)),
            "no_context_snapshot": bool(getattr(args, "no_context_snapshot", False)),
            "workers": getattr(args, "workers", None),
        }
        if getattr(args, "portfolio", None):
            runtime_scheduler_args["portfolio"] = args.portfolio
        os.environ[RUNTIME_SCHEDULER_ARGS_ENV] = json.dumps(runtime_scheduler_args)
        if not prepare_webui_frontend_assets():
            logger.warning("프론트엔드 정적 파일이 준비되지 않았지만 FastAPI 서비스는 계속 실행합니다(웹 페이지가 안 열릴 수 있음)")
        try:
            start_api_server(host=args.host, port=args.port, config=config)
            bot_clients_started = True
        except Exception as e:
            logger.error(f"FastAPI 서비스 실행 실패: {e}")
            if args.serve_only:
                return 1
            start_serve = False

    if bot_clients_started:
        start_bot_stream_clients(config)

    # === 웹 서비스 전용 모드: 자동 분석 안 함 ===
    if args.serve_only:
        logger.info("모드: 웹 서비스 전용")
        logger.info(f"웹 서비스 실행 중: http://{args.host}:{args.port}")
        logger.info("/api/v1/analysis/analyze API로 분석을 시작하세요")
        logger.info(f"API 문서: http://{args.host}:{args.port}/docs")
        logger.info("끝내려면 Ctrl+C를 누르세요...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("\n사용자가 중단해 프로그램을 종료합니다")
        return 0

    try:
        # 모드 0: 백테스트
        if getattr(args, 'backtest', False):
            logger.info("모드: 백테스트")
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            stats = service.run_backtest(
                code=getattr(args, 'backtest_code', None),
                force=getattr(args, 'backtest_force', False),
                eval_window_days=getattr(args, 'backtest_days', None),
            )
            logger.info(
                f"백테스트 완료: processed={stats.get('processed')} saved={stats.get('saved')} "
                f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
            )
            return 0

        # 모드 0.5: ETF 로테이션(규칙 기반, LLM 호출 없음)
        if getattr(args, 'etf_rotation', False):
            logger.info("모드: ETF 로테이션")
            from src.services.etf_rotation_service import run_etf_rotation

            report = run_etf_rotation(config, send_notification=not args.no_notify)
            logger.info(
                "ETF 로테이션 완료: as_of=%s target=%s failed=%s",
                f"{report.as_of:%Y-%m-%d}", report.target_weights, list(report.failed_codes),
            )
            return 0

        # 모드 1: 시장 전체 리뷰만
        if args.market_review:
            from src.core.market_review import run_market_review
            from src.core.market_review_runtime import build_market_review_runtime

            # Issue #373: Trading day check for market-review-only mode.
            # Do NOT use _compute_trading_day_filter here: that helper checks
            # config.market_review_enabled, which would wrongly block an
            # explicit --market-review invocation when the flag is disabled.
            effective_region = None
            if not getattr(args, 'force_run', False) and getattr(config, 'trading_day_check_enabled', True):
                from src.core.trading_calendar import get_open_markets_today, compute_effective_region as _compute_region
                open_markets = get_open_markets_today()
                effective_region = _compute_region(
                    getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
                )
                if effective_region == '':
                    logger.info("오늘은 시장 리뷰 대상 시장이 모두 휴장일이라 건너뜁니다. --force-run으로 강제 실행할 수 있습니다.")
                    return 0

            logger.info("모드: 시장 전체 리뷰만")
            notifier, analyzer, search_service = build_market_review_runtime(config)

            market_review_result = _run_market_review_with_shared_lock(
                config,
                run_market_review,
                notifier=notifier,
                analyzer=analyzer,
                search_service=search_service,
                send_notification=not args.no_notify,
                override_region=effective_region,
                trigger_source="cli",
            )
            return 0 if market_review_result else 1

        # 모드 2: 예약 실행 모드
        if args.schedule or config.schedule_enabled:
            if start_serve:
                # 모드 2 + 웹 서비스: --schedule/--webui/--serve와
                # config.schedule_enabled 조합에서 오는 경로(모두 guard에 포함)로, API runtime
                # scheduler가 맡는다. --serve-only는 위 serve_only 분기에서 이미 반환됨.
                logger.info("모드: Web/API runtime scheduler")
                logger.info(f"웹 서비스 실행 중: http://{args.host}:{args.port}")
                logger.info("Web/API runtime scheduler가 예약 실행을 맡았습니다. 설정을 저장하면 지금 실행 중인 프로세스에 바로 반영됩니다")
                logger.info("끝내려면 Ctrl+C를 누르세요...")
                try:
                    while True:
                        time.sleep(1)
                except KeyboardInterrupt:
                    logger.info("\n사용자가 중단해 프로그램을 종료합니다")
                return 0

            logger.info("모드: 예약 실행")
            logger.info(f"매일 실행 시각: {config.schedule_time}")

            # Determine whether to run immediately:
            # Command line arg --no-run-immediately overrides config if present.
            # Otherwise use config (defaults to True).
            should_run_immediately = config.schedule_run_immediately
            if getattr(args, 'no_run_immediately', False):
                should_run_immediately = False

            logger.info(f"시작하자마자 실행: {should_run_immediately}")

            from src.scheduler import run_with_schedule
            scheduled_stock_codes = _resolve_scheduled_stock_codes(args.stocks or None)
            schedule_time_provider = _build_schedule_time_provider(config.schedule_time)
            schedule_times_provider = _build_schedule_times_provider(config.schedule_time)

            # Startup daily dedup gate (src/core/analysis_run_marker.py):
            # only the startup-immediate invocation consults the gate; the
            # daily scheduled invocations never do. --force-run bypasses the
            # gate entirely (explicit request for an immediate full run,
            # mirroring the trading-day skip override). The flag is consumed
            # by the first task call whatever its outcome. Fail-open by design.
            startup_gate_active = should_run_immediately

            def scheduled_task(scheduled_for=None):
                nonlocal startup_gate_active
                gated, startup_gate_active = startup_gate_active, False
                runtime_config = _reload_runtime_config()
                force_run = getattr(args, "force_run", False)
                if (
                    gated
                    and not force_run
                    and getattr(runtime_config, "schedule_startup_dedup", True)
                ):
                    # Expected list = what THIS startup would actually
                    # analyze, resolved through the same real target chain
                    # as run_full_analysis (Futu portfolio first, .env
                    # hot-reload second, trading-day filter last; schema 2
                    # coverage gate). Only used for the skip decision; the
                    # run below still applies its own filter. A resolution
                    # failure or an empty portfolio resolution comes back
                    # as a fail-open reason instead of an expected list —
                    # the gate then never skips.
                    expected_codes, fail_open_reason = (
                        _resolve_gate_expected_stock_codes(
                            runtime_config,
                            args,
                            stock_codes=scheduled_stock_codes,
                        )
                    )
                    if fail_open_reason is not None:
                        logger.info(
                            "시작 직후 실행 중복 확인 fail-open(%s), 분석은 평소대로 실행",
                            fail_open_reason,
                        )
                    else:
                        decision = should_skip_startup_immediate_run(
                            runtime_config,
                            expected_stock_codes=expected_codes,
                        )
                        if decision.skip:
                            logger.info(
                                "启动立即执行已跳过:当日全量分析已完成(%s)",
                                decision.reason,
                            )
                            return
                        logger.info(
                            "启动立即执行去重检查通过:%s", decision.reason
                        )
                elif gated and force_run:
                    logger.info("--force-run 指定,跳过启动去重检查")
                if scheduled_for is None:
                    result = run_full_analysis(runtime_config, args, scheduled_stock_codes)
                else:
                    from src.services.scheduled_analysis_claim import ScheduledAnalysisSkipped

                    scheduled_args = argparse.Namespace(**vars(args))
                    scheduled_args._scheduled_for = scheduled_for
                    try:
                        result = run_scheduled_analysis(runtime_config, scheduled_args, scheduled_stock_codes)
                    except ScheduledAnalysisSkipped:
                        logger.info("Scheduled analysis already claimed; skipping occurrence %s", scheduled_for)
                        return

                if result is False:
                    reason = _LAST_ANALYSIS_FAILURE_REASON or "unknown"
                    raise RuntimeError(
                        f"scheduled analysis reported failure: {reason}"
                    )

            background_tasks = []
            if getattr(config, 'agent_event_monitor_enabled', False):
                from src.services.alert_worker import AlertWorker

                interval_minutes = max(1, getattr(config, 'agent_event_monitor_interval_minutes', 5))
                alert_worker = AlertWorker(config_provider=_reload_runtime_config)

                def event_monitor_task():
                    stats = alert_worker.run_once()
                    triggered_count = stats.get("triggered", 0)
                    if triggered_count:
                        logger.info("[EventMonitor] 本轮触发 %d 条提醒", triggered_count)

                background_tasks.append({
                    "task": event_monitor_task,
                    "interval_seconds": interval_minutes * 60,
                    "run_immediately": True,
                    "name": "agent_event_monitor",
                })

            schedule_kwargs = {
                "task": scheduled_task,
                "schedule_time": config.schedule_time,
                "run_immediately": should_run_immediately,
                "background_tasks": background_tasks,
                "schedule_time_provider": schedule_time_provider,
                "pass_scheduled_for": True,
            }
            if hasattr(config, "schedule_times"):
                schedule_kwargs["schedule_times"] = config.schedule_times
                schedule_kwargs["schedule_times_provider"] = schedule_times_provider
            run_with_schedule(**schedule_kwargs)
            return 0

        # 모드 3: 일반 1회 실행
        if config.run_immediately:
            try:
                analysis_ok = _run_analysis_with_runtime_scheduler_lock(
                    config, args, stock_codes, analysis_targets
                )
            except FutuPortfolioError as exc:
                if not start_serve:
                    raise
                logger.exception(
                    "Futu 持仓导入失败，Web/API 服务继续运行: %s",
                    exc,
                )
            else:
                if analysis_ok is False:
                    if start_serve:
                        logger.error("시작 시 분석 실행에 실패했지만 Web/API 서비스는 계속 실행합니다.")
                    elif _LAST_ANALYSIS_FAILURE_REASON in {
                        "no_report",
                        "empty_stock_list",
                        "report_save_failed",
                    }:
                        return 1
        else:
            logger.info("설정상 분석을 바로 실행하지 않음 (RUN_IMMEDIATELY=false)")

        logger.info("\n프로그램 실행 완료")

        # 서비스가 켜져 있고 예약 실행 모드가 아니면 프로그램을 계속 띄워 둠
        keep_running = start_serve and not (args.schedule or config.schedule_enabled)
        if keep_running:
            logger.info("API 서비스 실행 중 (끝내려면 Ctrl+C)...")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

        return 0

    except KeyboardInterrupt:
        logger.info("\n사용자가 중단해 프로그램을 종료합니다")
        return 130

    except Exception as e:
        logger.exception(f"프로그램 실행 실패: {e}")
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    sys.exit(main())

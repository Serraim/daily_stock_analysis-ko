# -*- coding: utf-8 -*-
"""
===================================
로그 설정 모듈 - 공통 로그 시스템 초기화
===================================

역할:
1. 공통 로그 형식과 설정 상수 제공
2. 콘솔 + 파일(일반/디버그) 3단 로그 출력 지원
3. 외부 라이브러리 로그 수준을 자동으로 낮춤
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional, Tuple


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(pathname)s:%(lineno)d | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_ALLOWED_LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
}
_DEFAULT_LITELLM_LOG_LEVEL = 'WARNING'


class RelativePathFormatter(logging.Formatter):
    """절대 경로 대신 상대 경로를 출력하는 사용자 정의 Formatter"""

    def __init__(self, fmt=None, datefmt=None, relative_to=None):
        super().__init__(fmt, datefmt)
        self.relative_to = Path(relative_to) if relative_to else Path.cwd()

    def format(self, record):
        # 절대 경로를 상대 경로로 변환
        try:
            record.pathname = str(Path(record.pathname).relative_to(self.relative_to))
        except ValueError:
            # 상대 경로로 바꿀 수 없으면 그대로 둠
            pass
        return super().format(record)



# 기본으로 로그 수준을 낮출 외부 라이브러리
DEFAULT_QUIET_LOGGERS = [
    'urllib3',
    'sqlalchemy',
    'google',
    'httpx',
]

LITELLM_LOGGERS = [
    'LiteLLM',
    'LiteLLM Router',
    'LiteLLM Proxy',
    'litellm',
]


def _resolve_litellm_log_level(raw_level: Optional[str] = None) -> Tuple[int, Optional[str]]:
    """Resolve LiteLLM logger level from env, returning invalid raw value if any."""
    if raw_level is None:
        raw_level = os.getenv('LITELLM_LOG_LEVEL', '')

    normalized = (raw_level or '').strip().upper()
    if not normalized:
        normalized = _DEFAULT_LITELLM_LOG_LEVEL

    level = _ALLOWED_LOG_LEVELS.get(normalized)
    if level is None:
        return _ALLOWED_LOG_LEVELS[_DEFAULT_LITELLM_LOG_LEVEL], raw_level
    return level, None


def setup_logging(
    log_prefix: str = "app",
    log_dir: str = "./logs",
    console_level: Optional[int] = None,
    debug: bool = False,
    extra_quiet_loggers: Optional[List[str]] = None,
) -> None:
    """
    공통 로그 시스템 초기화

    3단 로그 출력 설정:
    1. 콘솔: debug 인자 또는 console_level 로 수준 결정
    2. 일반 로그 파일: INFO 수준, 10MB마다 교체, 백업 5개 보관
    3. 디버그 로그 파일: DEBUG 수준, 50MB마다 교체, 백업 3개 보관

    Args:
        log_prefix: 로그 파일 이름 앞부분 (예: "api_server" -> api_server_20240101.log)
        log_dir: 로그 파일 폴더, 기본값 ./logs
        console_level: 콘솔 로그 수준 (선택, debug 인자보다 우선)
        debug: 디버그 모드 사용 여부 (콘솔에 DEBUG 수준 출력)
        extra_quiet_loggers: 로그 수준을 추가로 낮출 외부 라이브러리 목록
    """
    # 콘솔 로그 수준 결정
    if console_level is not None:
        level = console_level
    else:
        level = logging.DEBUG if debug else logging.INFO

    # 로그 폴더 생성
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # 로그 파일 경로 (날짜별로 파일 분리)
    today_str = datetime.now().strftime('%Y%m%d')
    log_file = log_path / f"{log_prefix}_{today_str}.log"
    debug_log_file = log_path / f"{log_prefix}_debug_{today_str}.log"

    # 루트 logger 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 루트 logger 는 DEBUG, 실제 출력 수준은 handler 가 결정

    # 기존 handler 제거 (중복 추가 방지)
    if root_logger.handlers:
        root_logger.handlers.clear()
    # 상대 경로 Formatter 생성 (프로젝트 루트 기준)
    project_root = Path.cwd()
    rel_formatter = RelativePathFormatter(
        LOG_FORMAT, LOG_DATE_FORMAT, relative_to=project_root
    )
    # Handler 1: 콘솔 출력
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(rel_formatter)
    root_logger.addHandler(console_handler)

    # Handler 2: 일반 로그 파일 (INFO 수준, 10MB마다 교체)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(rel_formatter)
    root_logger.addHandler(file_handler)

    # Handler 3: 디버그 로그 파일 (DEBUG 수준, 모든 상세 정보 포함)
    debug_handler = RotatingFileHandler(
        debug_log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=3,
        encoding='utf-8'
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(rel_formatter)
    root_logger.addHandler(debug_handler)

    # 외부 라이브러리 로그 수준 낮추기
    quiet_loggers = DEFAULT_QUIET_LOGGERS.copy()
    if extra_quiet_loggers:
        quiet_loggers.extend(extra_quiet_loggers)

    for logger_name in quiet_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    litellm_level, invalid_litellm_level = _resolve_litellm_log_level()
    for logger_name in LITELLM_LOGGERS:
        logging.getLogger(logger_name).setLevel(litellm_level)

    # 초기화 완료 메시지 출력 (상대 경로 사용)
    try:
        rel_log_path = log_path.resolve().relative_to(project_root)
    except ValueError:
        rel_log_path = log_path

    try:
        rel_log_file = log_file.resolve().relative_to(project_root)
    except ValueError:
        rel_log_file = log_file

    try:
        rel_debug_log_file = debug_log_file.resolve().relative_to(project_root)
    except ValueError:
        rel_debug_log_file = debug_log_file

    logging.info(f"로그 시스템 초기화 완료, 로그 폴더: {rel_log_path}")
    logging.info(f"일반 로그: {rel_log_file}")
    logging.info(f"디버그 로그: {rel_debug_log_file}")
    if invalid_litellm_level is not None:
        logging.warning(
            "LITELLM_LOG_LEVEL=%r 无效，已回退为 %s；可选值：%s",
            invalid_litellm_level,
            _DEFAULT_LITELLM_LOG_LEVEL,
            ", ".join(_ALLOWED_LOG_LEVELS),
        )

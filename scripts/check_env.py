# -*- coding: utf-8 -*-
"""
===================================
A주 관심종목 AI 분석 시스템 - 환경 점검 테스트
===================================

.env 설정이 올바른지 확인합니다. 점검 항목:
1. 설정 불러오기 테스트
2. 데이터베이스 조회
3. 데이터 소스 테스트
4. LLM 호출 테스트
5. 알림 발송 테스트

사용법:
    python scripts/check_env.py              # 모든 테스트 실행
    python scripts/check_env.py --db         # 데이터베이스만 조회
    python scripts/check_env.py --llm        # LLM만 테스트
    python scripts/check_env.py --fetch      # 데이터 받기만 테스트
    python scripts/check_env.py --notify     # 알림만 테스트

"""
import os
# Proxy config - controlled by USE_PROXY env var, off by default.
# Set USE_PROXY=true in .env if you need a local proxy (e.g. mainland China).
# GitHub Actions always skips this regardless of USE_PROXY.
if os.getenv("GITHUB_ACTIONS") != "true" and os.getenv("USE_PROXY", "false").lower() == "true":
    proxy_host = os.getenv("PROXY_HOST", "127.0.0.1")
    proxy_port = os.getenv("PROXY_PORT", "10809")
    proxy_url = f"http://{proxy_host}:{proxy_port}"
    os.environ["http_proxy"] = proxy_url
    os.environ["https_proxy"] = proxy_url

import argparse
import logging
import sys
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _reconfigure_output_stream(stream):
    """Avoid UnicodeEncodeError on legacy Windows console code pages."""
    reconfigure = getattr(stream, "reconfigure", None)
    if not callable(reconfigure):
        return

    for kwargs in (
        {"encoding": "utf-8", "errors": "replace"},
        {"errors": "replace"},
    ):
        try:
            reconfigure(**kwargs)
            return
        except Exception:
            continue


def configure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        _reconfigure_output_stream(stream)


# 로그 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def print_header(title: str):
    """제목 출력"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def print_section(title: str):
    """소제목 출력"""
    print(f"\n--- {title} ---")


def check_config():
    """설정 불러오기 테스트"""
    print_header("1. 설정 불러오기 테스트")
    
    from src.config import get_config
    config = get_config()
    
    print_section("기본 설정")
    print(f"  종목 목록: {config.stock_list}")
    print(f"  데이터베이스 경로: {config.database_path}")
    print(f"  최대 동시 작업 수: {config.max_workers}")
    print(f"  디버그 모드: {config.debug}")
    
    print_section("API 설정")
    print(f"  Tushare Token: {'설정됨 ✓' if config.tushare_token else '설정 안 됨 ✗'}")
    if config.tushare_token:
        print(f"    Token 앞 8자리: {config.tushare_token[:8]}...")
    
    print(f"  Gemini API Key: {'설정됨 ✓' if config.gemini_api_key else '설정 안 됨 ✗'}")
    if config.gemini_api_key:
        print(f"    Key 앞 8자리: {config.gemini_api_key[:8]}...")
    print(f"  Gemini 기본 모델: {config.gemini_model}")
    print(f"  Gemini 예비 모델: {config.gemini_model_fallback}")
    
    print(f"  WeCom(기업 위챗) Webhook: {'설정됨 ✓' if config.wechat_webhook_url else '설정 안 됨 ✗'}")
    
    print_section("설정 검증")
    issues = config.validate_structured()
    _prefix = {"error": "  ✗", "warning": "  ⚠", "info": "  ·"}
    for issue in issues:
        print(f"{_prefix.get(issue.severity, '  ?')} [{issue.severity.upper()}] {issue.message}")
    if not any(i.severity in ("error", "warning") for i in issues):
        print("  ✓ 핵심 설정 항목 검증 통과")
    
    return True


def view_database():
    """데이터베이스 내용 조회"""
    print_header("2. 데이터베이스 내용 조회")
    
    from src.storage import get_db
    from sqlalchemy import text
    
    db = get_db()
    
    print_section("데이터베이스 연결")
    print(f"  ✓ 연결 성공")
    
    # 별도 session으로 조회
    session = db.get_session()
    try:
        # 통계 정보
        result = session.execute(text("""
            SELECT 
                code,
                COUNT(*) as count,
                MIN(date) as min_date,
                MAX(date) as max_date,
                data_source
            FROM stock_daily 
            GROUP BY code
            ORDER BY code
        """))
        stocks = result.fetchall()
        
        print_section(f"저장된 종목 데이터 (총 {len(stocks)}개)")
        if stocks:
            print(f"  {'코드':<10} {'기록 수':<8} {'시작일':<12} {'최근일':<12} {'데이터 소스'}")
            print("  " + "-" * 60)
            for row in stocks:
                print(f"  {row[0]:<10} {row[1]:<8} {row[2]!s:<12} {row[3]!s:<12} {row[4] or 'Unknown'}")
        else:
            print("  데이터 없음")
        
        # 오늘 데이터 조회
        today = date.today()
        result = session.execute(text("""
            SELECT code, date, open, high, low, close, pct_chg, volume, ma5, ma10, ma20, volume_ratio
            FROM stock_daily 
            WHERE date = :today
            ORDER BY code
        """), {"today": today})
        today_data = result.fetchall()
        
        print_section(f"오늘 데이터 ({today})")
        if today_data:
            for row in today_data:
                code, dt, open_, high, low, close, pct_chg, volume, ma5, ma10, ma20, vol_ratio = row
                print(f"\n  【{code}】")
                print(f"    시가: {open_:.2f}  고가: {high:.2f}  저가: {low:.2f}  종가: {close:.2f}")
                print(f"    등락률: {pct_chg:.2f}%  거래량: {volume/10000:.2f}만 주")
                print(f"    MA5: {ma5:.2f}  MA10: {ma10:.2f}  MA20: {ma20:.2f}  거래량 비율: {vol_ratio:.2f}")
        else:
            print("  오늘 데이터 없음")
        
        # 최근 10건 조회
        result = session.execute(text("""
            SELECT code, date, close, pct_chg, volume, data_source
            FROM stock_daily 
            ORDER BY date DESC, code
            LIMIT 10
        """))
        recent = result.fetchall()
        
        print_section("최근 10건 기록")
        if recent:
            print(f"  {'코드':<10} {'날짜':<12} {'종가':<10} {'등락%':<8} {'거래량':<15} {'출처'}")
            print("  " + "-" * 70)
            for row in recent:
                vol_str = f"{row[4]/10000:.2f}만" if row[4] else "N/A"
                print(f"  {row[0]:<10} {row[1]!s:<12} {row[2]:<10.2f} {row[3]:<8.2f} {vol_str:<15} {row[5] or 'Unknown'}")
    finally:
        session.close()
    
    return True


def check_data_fetch(stock_code: str = "600519"):
    """데이터 받기 테스트"""
    print_header("3. 데이터 받기 테스트")
    
    from data_provider import DataFetcherManager
    
    manager = DataFetcherManager()
    
    print_section("데이터 소스 목록")
    for i, name in enumerate(manager.available_fetchers, 1):
        print(f"  {i}. {name}")
    
    print_section(f"{stock_code} 데이터 받기")
    print(f"  받는 중 (몇 초 걸릴 수 있어요)...")
    
    try:
        df, source = manager.get_daily_data(stock_code, days=5)
        
        print(f"  ✓ 받기 성공")
        print(f"    데이터 소스: {source}")
        print(f"    기록 수: {len(df)}")
        
        print_section("데이터 미리보기 (최근 5건)")
        if not df.empty:
            preview_cols = ['date', 'open', 'high', 'low', 'close', 'pct_chg', 'volume']
            existing_cols = [c for c in preview_cols if c in df.columns]
            print(df[existing_cols].tail().to_string(index=False))
        
        return True
        
    except Exception as e:
        print(f"  ✗ 받기 실패: {e}")
        return False


def check_llm():
    """LLM 호출 테스트"""
    print_header("4. LLM (Gemini) 호출 테스트")
    
    from src.analyzer import GeminiAnalyzer
    from src.config import get_config
    import time
    
    config = get_config()
    
    print_section("모델 설정")
    print(f"  기본 모델: {config.gemini_model}")
    print(f"  예비 모델: {config.gemini_model_fallback}")
    
    # 네트워크 연결 확인
    print_section("네트워크 연결 확인")
    try:
        import socket
        socket.setdefaulttimeout(10)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect(("generativelanguage.googleapis.com", 443))
        print(f"  ✓ Google API 서버에 연결할 수 있어요")
    except Exception as e:
        print(f"  ✗ Google API 서버에 연결할 수 없어요: {e}")
        print(f"  팁: 네트워크 연결이나 프록시 설정을 확인하세요")
        print(f"  팁: 환경 변수를 설정할 수 있어요 HTTPS_PROXY=http://your-proxy:port")
        return False
    
    analyzer = GeminiAnalyzer()
    
    print_section("모델 초기화")
    if analyzer.is_available():
        print(f"  ✓ 모델 초기화 성공")
    else:
        print(f"  ✗ 모델 초기화 실패 (API Key를 확인하세요)")
        return False
    
    # 테스트용 컨텍스트 만들기
    test_context = {
        'code': '600519',
        'date': date.today().isoformat(),
        'today': {
            'open': 1420.0,
            'high': 1435.0,
            'low': 1415.0,
            'close': 1428.0,
            'volume': 5000000,
            'amount': 7140000000,
            'pct_chg': 0.56,
            'ma5': 1425.0,
            'ma10': 1418.0,
            'ma20': 1410.0,
            'volume_ratio': 1.1,
        },
        'ma_status': '多头排列 📈',
        'volume_change_ratio': 1.05,
        'price_change_ratio': 0.56,
    }
    
    print_section("테스트 요청 보내기")
    print(f"  테스트 종목: 贵州茅台 (600519)")
    print(f"  Gemini API 호출 중 (제한 시간: 60초)...")
    
    start_time = time.time()
    
    try:
        result = analyzer.analyze(test_context)
        
        elapsed = time.time() - start_time
        print(f"\n  ✓ API 호출 성공 (걸린 시간: {elapsed:.2f}초)")
        
        print_section("분석 결과")
        print(f"  심리 점수: {result.sentiment_score}/100")
        print(f"  추세 예측: {result.trend_prediction}")
        print(f"  매매 의견: {result.operation_advice}")
        print(f"  기술적 분석: {result.technical_analysis[:80]}..." if len(result.technical_analysis) > 80 else f"  기술적 분석: {result.technical_analysis}")
        print(f"  뉴스 요약: {result.news_summary[:80]}..." if len(result.news_summary) > 80 else f"  뉴스 요약: {result.news_summary}")
        print(f"  종합 요약: {result.analysis_summary}")
        
        if not result.success:
            print(f"\n  ⚠ 주의: {result.error_message}")
        
        return result.success
        
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n  ✗ API 호출 실패 (걸린 시간: {elapsed:.2f}초)")
        print(f"  오류: {e}")
        
        # 더 자세한 오류 안내
        error_str = str(e).lower()
        if 'timeout' in error_str or 'unavailable' in error_str:
            print(f"\n  진단: 네트워크 시간 초과. 가능한 원인:")
            print(f"    1. 네트워크 불통 (Google 접속에 프록시가 필요할 수 있어요)")
            print(f"    2. API 서비스 일시 장애")
            print(f"    3. 요청이 너무 많아 제한됨")
        elif 'invalid' in error_str or 'api key' in error_str:
            print(f"\n  진단: API Key가 잘못됐을 수 있어요")
        elif 'model' in error_str:
            print(f"\n  진단: 모델 이름이 틀렸을 수 있어요. .env의 GEMINI_MODEL을 바꿔 보세요")
        
        return False


def check_notification():
    """알림 발송 테스트"""
    print_header("5. 알림 발송 테스트")
    
    from src.notification import NotificationService
    from src.config import get_config
    
    config = get_config()
    service = NotificationService()
    
    print_section("설정 확인")
    if service.is_available():
        print(f"  ✓ WeCom(기업 위챗) Webhook 설정됨")
        webhook_preview = config.wechat_webhook_url[:50] + "..." if len(config.wechat_webhook_url) > 50 else config.wechat_webhook_url
        print(f"    URL: {webhook_preview}")
    else:
        print(f"  ✗ WeCom(기업 위챗) Webhook 설정 안 됨")
        return False
    
    print_section("테스트 메시지 보내기")
    
    test_message = f"""## 🧪 시스템 테스트 메시지

**A주 관심종목 AI 분석 시스템**에서 보낸 테스트 메시지입니다.

- 테스트 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- 테스트 목적: WeCom(기업 위챗) Webhook 설정 확인

이 메시지를 받았다면 알림 설정이 올바른 거예요 ✓"""
    
    print(f"  보내는 중...")
    
    try:
        success = service.send_to_wechat(test_message)
        
        if success:
            print(f"  ✓ 메시지 발송 성공. WeCom(기업 위챗)을 확인하세요")
        else:
            print(f"  ✗ 메시지 발송 실패")
        
        return success
        
    except Exception as e:
        print(f"  ✗ 발송 중 예외: {e}")
        return False


def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "🚀" * 20)
    print("  A주 관심종목 AI 분석 시스템 - 환경 점검")
    print("  " + datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    print("🚀" * 20)
    
    results = {}
    
    # 1. 설정 테스트
    try:
        results['설정 불러오기'] = check_config()
    except Exception as e:
        print(f"  ✗ 설정 테스트 실패: {e}")
        results['설정 불러오기'] = False
    
    # 2. 데이터베이스 조회
    try:
        results['데이터베이스'] = view_database()
    except Exception as e:
        print(f"  ✗ 데이터베이스 테스트 실패: {e}")
        results['데이터베이스'] = False
    
    # 3. 데이터 받기 (너무 느려서 건너뜀)
    # results['데이터 받기'] = check_data_fetch()
    
    # 4. LLM 테스트 (선택)
    # results['LLM 호출'] = check_llm()
    
    # 요약
    print_header("테스트 결과 요약")
    for name, passed in results.items():
        status = "✓ 통과" if passed else "✗ 실패"
        print(f"  {status}: {name}")
    
    print(f"\n팁: --llm 옵션으로 LLM 호출만 따로 테스트할 수 있어요")
    print(f"팁: --fetch 옵션으로 데이터 받기만 따로 테스트할 수 있어요")
    print(f"팁: --notify 옵션으로 알림 발송만 따로 테스트할 수 있어요")


def query_stock_data(stock_code: str, days: int = 10):
    """지정한 종목의 데이터 조회"""
    print_header(f"종목 데이터 조회: {stock_code}")
    
    from src.storage import get_db
    from sqlalchemy import text
    
    db = get_db()
    
    session = db.get_session()
    try:
        result = session.execute(text("""
            SELECT date, open, high, low, close, pct_chg, volume, amount, ma5, ma10, ma20, volume_ratio
            FROM stock_daily 
            WHERE code = :code
            ORDER BY date DESC
            LIMIT :limit
        """), {"code": stock_code, "limit": days})
        
        rows = result.fetchall()
        
        if rows:
            print(f"\n  최근 {len(rows)}건 기록:\n")
            print(f"  {'날짜':<12} {'시가':<10} {'고가':<10} {'저가':<10} {'종가':<10} {'등락%':<8} {'MA5':<10} {'MA10':<10} {'거래량 비율':<8}")
            print("  " + "-" * 100)
            for row in rows:
                dt, open_, high, low, close, pct_chg, vol, amt, ma5, ma10, ma20, vol_ratio = row
                print(f"  {dt!s:<12} {open_:<10.2f} {high:<10.2f} {low:<10.2f} {close:<10.2f} {pct_chg:<8.2f} {ma5:<10.2f} {ma10:<10.2f} {vol_ratio:<8.2f}")
        else:
            print(f"  {stock_code} 데이터를 찾을 수 없어요")
    finally:
        session.close()


def main():
    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description='A주 관심종목 AI 분석 시스템 - 환경 점검 테스트',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument('--db', action='store_true', help='데이터베이스 내용 조회')
    parser.add_argument('--llm', action='store_true', help='LLM 호출 테스트')
    parser.add_argument('--fetch', action='store_true', help='데이터 받기 테스트')
    parser.add_argument('--notify', action='store_true', help='알림 발송 테스트')
    parser.add_argument('--config', action='store_true', help='설정 조회')
    parser.add_argument('--stock', type=str, help='지정한 종목 데이터 조회 (예: --stock 600519)')
    parser.add_argument('--all', action='store_true', help='모든 테스트 실행 (LLM 포함)')
    
    args = parser.parse_args()
    
    # 옵션을 하나도 안 주면 기본 테스트 실행
    if not any([args.db, args.llm, args.fetch, args.notify, args.config, args.stock, args.all]):
        run_all_tests()
        return 0
    
    # 옵션에 따라 해당 테스트 실행
    if args.config:
        check_config()
    
    if args.db:
        view_database()
    
    if args.stock:
        query_stock_data(args.stock)
    
    if args.fetch:
        check_data_fetch()
    
    if args.llm:
        check_llm()
    
    if args.notify:
        check_notification()
    
    if args.all:
        check_config()
        view_database()
        check_data_fetch()
        check_llm()
        check_notification()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/bin/bash
# ===================================
# A주/홍콩/미국 주식 AI 분석 시스템 - 테스트 스크립트
# ===================================
#
# 사용법:
#   ./scripts/test.sh [테스트 시나리오]
#
# 테스트 시나리오:
#   market      - 시장 전체 리뷰만
#   a-stock     - A주 개별 종목 분석(마오타이, 핑안은행)
#   etf         - ETF 분석(위성 ETF 563230)
#   hk-stock    - 홍콩 주식 분석(텐센트, 알리바바)
#   us-stock    - 미국 주식 분석(애플, 테슬라)
#   mixed       - 여러 시장 섞어서 분석
#   single      - 종목별 알림 모드 테스트
#   dry-run     - 데이터만 받고 분석은 안 함
#   full        - 전체 과정 테스트
#   quick       - 빠른 테스트(종목 1개)
#   all         - 모든 테스트 실행
#
# 예시:
#   ./scripts/test.sh market      # 시장 전체 리뷰 테스트
#   ./scripts/test.sh us-stock    # 미국 주식 분석 테스트
#   ./scripts/test.sh quick       # 빠른 테스트
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 색을 입혀 메시지 출력
info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

header() {
    echo ""
    echo "=============================================="
    echo -e "${GREEN}$1${NC}"
    echo "=============================================="
    echo ""
}

# Python 환경 확인
check_python() {
    if ! command -v python3 &> /dev/null; then
        error "Python3가 설치되어 있지 않습니다"
        exit 1
    fi
    info "Python 버전: $(python3 --version)"
}

# 의존성 확인
check_deps() {
    info "의존성 확인 중..."
    python3 -c "import yfinance" 2>/dev/null || { warn "yfinance가 없어서 미국 주식 테스트가 실패할 수 있습니다"; }
    python3 -c "import akshare" 2>/dev/null || { warn "akshare가 없어서 A주/홍콩 주식 테스트가 실패할 수 있습니다"; }
    success "의존성 확인 완료"
}

# ==================== 테스트 시나리오 ====================

# 테스트 1: 시장 전체 리뷰
test_market() {
    header "테스트 시나리오: 시장 전체 리뷰"
    info "시장 전체 리뷰 분석 실행 중..."
    python3 main.py --market-review "$@"
    success "시장 전체 리뷰 테스트 완료"
}

# 테스트 2: A주 분석
test_a_stock() {
    header "테스트 시나리오: A주 분석"
    info "A주 분석: 600519(마오타이), 000001(핑안은행)"
    python3 main.py --stocks 600519,000001  --no-market-review "$@"
    success "A주 분석 테스트 완료"
}

# 테스트 2.5: ETF 분석
test_etf() {
    header "테스트 시나리오: ETF 분석"
    info "ETF 분석: 563230(위성 ETF)"
    python3 main.py --stocks 563230,512400 --no-market-review "$@"
    success "ETF 분석 테스트 완료"
}

# 테스트 3: 홍콩 주식 분석
test_hk_stock() {
    header "테스트 시나리오: 홍콩 주식 분석"
    info "홍콩 주식 분석: hk00700(텐센트), hk09988(알리바바)"
    python3 main.py --stocks hk00700,hk09988 --no-market-review "$@"
    success "홍콩 주식 분석 테스트 완료"
}

# 테스트 4: 미국 주식 분석
test_us_stock() {
    header "테스트 시나리오: 미국 주식 분석"
    info "미국 주식 분석: AAPL(애플), TSLA(테슬라)"
    # 받은 인자를 그대로 넘김, 기본은 --no-notify 없음
    python3 main.py --stocks AAPL --no-market-review "$@"
    success "미국 주식 분석 테스트 완료"
}

# 테스트 5: 여러 시장 섞기
test_mixed() {
    header "테스트 시나리오: 여러 시장 섞어서 분석"
    info "여러 시장 분석: 600519(A주), hk00700(홍콩), AAPL(미국)"
    python3 main.py --stocks 600519,hk00700,AAPL --no-market-review
    success "여러 시장 테스트 완료"
}

# 테스트 6: 종목별 알림 모드
test_single() {
    header "테스트 시나리오: 종목별 알림 모드"
    info "종목별 알림 모드 테스트 중..."
    python3 main.py --stocks 600519 --single-notify --no-market-review
    success "종목별 알림 모드 테스트 완료"
}

# 테스트 7: dry-run 모드
test_dry_run() {
    header "테스트 시나리오: Dry-Run 모드"
    info "데이터만 받고 AI 분석은 안 함..."
    python3 main.py --stocks 600519,AAPL --dry-run --no-notify
    success "Dry-Run 테스트 완료"
}

# 테스트 8: 전체 과정
test_full() {
    header "테스트 시나리오: 전체 과정"
    info "전체 분석 과정 실행 중(개별 종목 + 시장)..."
    python3 main.py --stocks 600519 --no-notify
    success "전체 과정 테스트 완료"
}

# 테스트 9: 빠른 테스트
test_quick() {
    header "테스트 시나리오: 빠른 테스트"
    info "종목 1개로 빠른 테스트 중..."
    python3 main.py --stocks 600519 --no-market-review --no-notify "$@"
    success "빠른 테스트 완료"
}

# 테스트 10: 종목 코드 인식 테스트
test_code_recognition() {
    header "테스트 시나리오: 종목 코드 인식"
    info "종목 코드 인식 로직 테스트 중..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')
from data_provider.akshare_fetcher import _is_hk_code, _is_us_code

test_cases = [
    # (코드, 기대 HK, 기대 US, 설명)
    ("AAPL", False, True, "미국 주식-애플"),
    ("TSLA", False, True, "미국 주식-테슬라"),
    ("BRK.B", False, True, "미국 주식-버크셔 B"),
    ("hk00700", True, False, "홍콩 주식-텐센트"),
    ("HK09988", True, False, "홍콩 주식-알리바바"),
    ("600519", False, False, "A주-마오타이"),
    ("000001", False, False, "A주-핑안"),
]

print("\n종목 코드 인식 테스트:")
print("-" * 60)
all_pass = True
for code, exp_hk, exp_us, desc in test_cases:
    is_hk = _is_hk_code(code)
    is_us = _is_us_code(code)
    hk_ok = is_hk == exp_hk
    us_ok = is_us == exp_us
    status = "✅" if (hk_ok and us_ok) else "❌"
    all_pass = all_pass and hk_ok and us_ok
    print(f"{status} {code:10} | HK:{is_hk:5} US:{is_us:5} | {desc}")

print("-" * 60)
print(f"{'✅ 모든 테스트 통과!' if all_pass else '❌ 실패한 테스트가 있습니다!'}")
sys.exit(0 if all_pass else 1)
PYTEST

    success "종목 코드 인식 테스트 완료"
}

# 테스트 11: YFinance 코드 변환 테스트
test_yfinance_convert() {
    header "테스트 시나리오: YFinance 코드 변환"
    info "YFinance 코드 변환 로직 테스트 중..."

    python3 << 'PYTEST'
import sys
sys.path.insert(0, '.')
from data_provider.yfinance_fetcher import YfinanceFetcher

fetcher = YfinanceFetcher()

test_cases = [
    ("AAPL", "AAPL", "미국 주식"),
    ("tsla", "TSLA", "미국 주식 소문자"),
    ("BRK.B", "BRK.B", "미국 주식 특수 기호"),
    ("hk00700", "0700.HK", "홍콩 주식"),
    ("HK09988", "9988.HK", "홍콩 주식 대문자"),
    ("600519", "600519.SS", "A주 상하이"),
    ("000001", "000001.SZ", "A주 선전"),
    ("300750", "300750.SZ", "A주 촹예반"),
]

print("\nYFinance 코드 변환 테스트:")
print("-" * 60)
all_pass = True
for input_code, expected, desc in test_cases:
    result = fetcher._convert_stock_code(input_code)
    status = "✅" if result == expected else "❌"
    all_pass = all_pass and (result == expected)
    print(f"{status} {input_code:10} -> {result:12} (기대값: {expected:12}) | {desc}")

print("-" * 60)
print(f"{'✅ 모든 테스트 통과!' if all_pass else '❌ 실패한 테스트가 있습니다!'}")
sys.exit(0 if all_pass else 1)
PYTEST

    success "YFinance 코드 변환 테스트 완료"
}

# 테스트 12: 문법 검사
test_syntax() {
    header "테스트 시나리오: Python 문법 검사"
    info "모든 Python 파일 문법 검사 중..."

    python3 -m py_compile main.py src/config.py src/notification.py \
        data_provider/akshare_fetcher.py \
        data_provider/yfinance_fetcher.py \
        bot/commands/analyze.py

    success "문법 검사 통과"
}

# 테스트 13: Flake8 정적 검사
test_flake8() {
    header "테스트 시나리오: Flake8 정적 검사"
    info "Flake8로 심각한 오류 검사 중..."

    if command -v flake8 &> /dev/null; then
        flake8 main.py src/config.py src/notification.py --select=F821,E999 --max-line-length=120
        success "Flake8 검사 통과"
    else
        warn "Flake8가 없어 검사를 건너뜁니다"
    fi
}

# 모든 테스트 실행
test_all() {
    header "모든 테스트 실행"

    test_syntax
    test_code_recognition
    test_yfinance_convert
    test_flake8

    echo ""
    info "아래 테스트는 네트워크와 API 설정이 필요해 실패할 수 있습니다:"
    echo ""

    test_dry_run || warn "Dry-Run 테스트 실패(네트워크 문제일 수 있음)"
    test_quick || warn "빠른 테스트 실패(API 문제일 수 있음)"

    success "모든 테스트 완료!"
}

# ==================== 메인 ====================

main() {
    header "A주/홍콩/미국 주식 AI 분석 시스템 - 테스트"

    check_python
    check_deps

    case "${1:-help}" in
        market)
            shift
            test_market "$@"
            ;;
        a-stock|a_stock|astock)
            shift
            test_a_stock "$@"
            ;;
        etf)
            shift
            test_etf "$@"
            ;;
        hk-stock|hk_stock|hkstock|hk)
            shift
            test_hk_stock "$@"
            ;;
        us-stock|us_stock|usstock|us)
            shift
            test_us_stock "$@"
            ;;
        mixed|mix)
            shift
            test_mixed "$@"
            ;;
        single)
            shift
            test_single "$@"
            ;;
        dry-run|dryrun|dry)
            shift
            test_dry_run "$@"
            ;;
        full)
            shift
            test_full "$@"
            ;;
        quick|q)
            shift
            test_quick "$@"
            ;;
        code|recognition)
            shift
            test_code_recognition "$@"
            ;;
        yfinance|yf)
            shift
            test_yfinance_convert "$@"
            ;;
        syntax)
            shift
            test_syntax "$@"
            ;;
        flake8|lint)
            shift
            test_flake8 "$@"
            ;;
        all)
            shift
            test_all "$@"
            ;;
        help|--help|-h|*)
            echo "사용법: $0 [테스트 시나리오]"
            echo ""
            echo "테스트 시나리오:"
            echo "  market      - 시장 전체 리뷰만"
            echo "  a-stock     - A주 개별 종목 분석"
            echo "  etf         - ETF 분석"
            echo "  hk-stock    - 홍콩 주식 분석"
            echo "  us-stock    - 미국 주식 분석"
            echo "  mixed       - 여러 시장 섞어서 분석"
            echo "  single      - 종목별 알림 모드"
            echo "  dry-run     - 데이터만 받기"
            echo "  full        - 전체 과정"
            echo "  quick       - 빠른 테스트(추천)"
            echo "  code        - 종목 코드 인식 테스트"
            echo "  yfinance    - YFinance 변환 테스트"
            echo "  syntax      - 문법 검사"
            echo "  flake8      - 정적 검사"
            echo "  all         - 모든 테스트 실행"
            echo ""
            echo "예시:"
            echo "  $0 quick     # 빠른 테스트"
            echo "  $0 us-stock  # 미국 주식 테스트"
            echo "  $0 code      # 종목 코드 인식 테스트"
            echo "  $0 all       # 모든 테스트 실행"
            ;;
    esac
}

main "$@"

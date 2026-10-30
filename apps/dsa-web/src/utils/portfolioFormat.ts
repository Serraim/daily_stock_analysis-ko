import type {
  PortfolioCashDirection,
  PortfolioCorporateActionType,
  PortfolioFxRefreshResponse,
  PortfolioImportCommitResponse,
  PortfolioImportParseResponse,
  PortfolioPositionItem,
  PortfolioSide,
} from '../types/portfolio';
import { toDateInputValue } from './format';
import { koOrZh } from './uiLanguage';

export type FxRefreshFeedback = {
  tone: 'neutral' | 'success' | 'warning';
  text: string;
};

export type PortfolioAlertVariant = 'info' | 'success' | 'warning' | 'danger';

export function getTodayIso(): string {
  return toDateInputValue(new Date());
}

export function formatMoney(value: number | undefined | null, currency = 'CNY'): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${currency} ${Number(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export function formatPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  return `${value.toFixed(2)}%`;
}

export function formatSignedPct(value: number | undefined | null): string {
  if (value == null || Number.isNaN(value)) return '--';
  const sign = value > 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
}

export function hasPositionPrice(row: PortfolioPositionItem): boolean {
  return row.priceAvailable !== false && row.priceSource !== 'missing';
}

export function formatPositionPrice(row: PortfolioPositionItem): string {
  if (!hasPositionPrice(row)) return '--';
  return row.lastPrice.toFixed(4);
}

export function formatPositionMoney(value: number, row: PortfolioPositionItem): string {
  if (!hasPositionPrice(row)) return '--';
  return formatMoney(value, row.valuationCurrency);
}

export function getPositionPriceLabel(row: PortfolioPositionItem): string {
  if (!hasPositionPrice(row)) return koOrZh('缺价', '가격 없음');
  if (row.priceSource === 'realtime_quote') {
    return row.priceProvider ? koOrZh(`实时价 · ${row.priceProvider}`, `실시간가 · ${row.priceProvider}`) : koOrZh('实时价', '실시간가');
  }
  if (row.priceSource === 'history_close') {
    return row.priceStale && row.priceDate ? koOrZh(`收盘价 · ${row.priceDate}`, `종가 · ${row.priceDate}`) : koOrZh('收盘价', '종가');
  }
  return row.priceSource || koOrZh('未知来源', '출처 모름');
}

export function formatSideLabel(value: PortfolioSide): string {
  return value === 'buy' ? koOrZh('买入', '매수') : koOrZh('卖出', '매도');
}

export function formatCashDirectionLabel(value: PortfolioCashDirection): string {
  return value === 'in' ? koOrZh('流入', '입금') : koOrZh('流出', '출금');
}

export function formatCorporateActionLabel(value: PortfolioCorporateActionType): string {
  return value === 'cash_dividend' ? koOrZh('现金分红', '현금배당') : koOrZh('拆并股调整', '액면분할·병합 조정');
}

export function formatBrokerLabel(value: string, displayName?: string): string {
  if (displayName && displayName.trim()) return `${value}（${displayName.trim()}）`;
  if (value === 'huatai') return koOrZh('huatai（华泰）', 'huatai (화타이)');
  if (value === 'citic') return koOrZh('citic（中信）', 'citic (중신)');
  if (value === 'cmb') return koOrZh('cmb（招商）', 'cmb (자오상)');
  return value;
}

export function buildFxRefreshFeedback(data: PortfolioFxRefreshResponse): FxRefreshFeedback {
  if (data.refreshEnabled === false) {
    return {
      tone: 'neutral',
      text: koOrZh('汇率在线刷新已被禁用。', '환율 온라인 새로고침이 꺼져 있어요.'),
    };
  }

  if (data.pairCount === 0) {
    return {
      tone: 'neutral',
      text: koOrZh('当前范围无可刷新的汇率对。', '지금 범위에는 새로고침할 환율이 없어요.'),
    };
  }

  if (data.updatedCount > 0 && data.staleCount === 0 && data.errorCount === 0) {
    return {
      tone: 'success',
      text: koOrZh(`汇率已刷新，共更新 ${data.updatedCount} 对。`, `환율을 새로고침했어요. 모두 ${data.updatedCount}건을 갱신했어요.`),
    };
  }

  const summary = koOrZh(`更新 ${data.updatedCount} 对，仍过期 ${data.staleCount} 对，失败 ${data.errorCount} 对。`, `갱신 ${data.updatedCount}건, 여전히 지난 값 ${data.staleCount}건, 실패 ${data.errorCount}건이에요.`);
  if (data.staleCount > 0) {
    return {
      tone: 'warning',
      text: koOrZh(`已尝试刷新，但仍有部分货币对使用 stale/fallback 汇率。${summary}`, `새로고침했지만 일부 통화는 아직 지난 값이나 대체 환율을 써요. ${summary}`),
    };
  }

  return {
    tone: 'warning',
    text: koOrZh(`在线刷新未完全成功。${summary}`, `온라인 새로고침이 모두 성공하지는 않았어요. ${summary}`),
  };
}

export function getFxRefreshFeedbackVariant(tone: FxRefreshFeedback['tone']): PortfolioAlertVariant {
  if (tone === 'success') return 'success';
  if (tone === 'warning') return 'warning';
  return 'info';
}

export function getCsvParseVariant(result: PortfolioImportParseResponse): PortfolioAlertVariant {
  return result.errorCount > 0 || result.skippedCount > 0 ? 'warning' : 'info';
}

export function getCsvCommitVariant(result: PortfolioImportCommitResponse, isDryRun: boolean): PortfolioAlertVariant {
  if (isDryRun) return 'info';
  return result.failedCount > 0 || result.duplicateCount > 0 ? 'warning' : 'success';
}

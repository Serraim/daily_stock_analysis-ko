import type React from 'react';
import { Activity } from 'lucide-react';
import { Badge, Card, EmptyState, Loading } from '../common';
import type { AlertTriggerItem } from '../../types/alerts';
import { formatDateTime } from '../../utils/format';
import { getMarketPhaseSummaryLabel } from '../../utils/marketPhase';
import { koOrZh } from '../../utils/uiLanguage';

const statusLabel: Record<string, string> = {
  triggered: '已触发',
  skipped: '已跳过',
  degraded: '降级',
  failed: '失败',
};

const statusLabelKo: Record<string, string> = {
  triggered: '발동',
  skipped: '건너뜀',
  degraded: '부분 실패',
  failed: '실패',
};

function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'default' {
  if (status === 'triggered') return 'success';
  if (status === 'skipped' || status === 'degraded') return 'warning';
  if (status === 'failed') return 'danger';
  return 'default';
}

function formatNullable(value?: string | number | null): string {
  if (value === null || value === undefined || value === '') return '--';
  return String(value);
}

function renderPhaseQuality(trigger: AlertTriggerItem): React.ReactNode {
  const phase = getMarketPhaseSummaryLabel(trigger.marketPhaseSummary, 'zh');
  const quality = trigger.analysisContextPackOverview?.dataQuality?.level;
  const limitations = trigger.analysisContextPackOverview?.dataQuality?.limitations?.slice(0, 2) ?? [];
  if (!phase && !quality && limitations.length === 0) {
    return <span className="text-xs text-muted-text">--</span>;
  }
  return (
    <div className="space-y-1">
      {phase ? <Badge variant="default">{phase.replace('市场阶段: ', '').replace('市场阶段：', '')}</Badge> : null}
      {quality ? <div className="text-xs text-secondary-text">{koOrZh('质量：', '품질: ')}{quality}</div> : null}
      {limitations.length ? (
        <div className="max-w-[180px] text-xs text-muted-text">{limitations.join('；')}</div>
      ) : null}
    </div>
  );
}

interface AlertTriggerHistoryProps {
  triggers: AlertTriggerItem[];
  isLoading?: boolean;
}

export const AlertTriggerHistory: React.FC<AlertTriggerHistoryProps> = ({ triggers, isLoading = false }) => {
  return (
    <Card title={koOrZh('触发历史', '발동 기록')} subtitle={koOrZh('评估记录', '평가 기록')} variant="bordered" padding="md">
      {isLoading ? <Loading label={koOrZh('正在加载触发历史', '발동 기록을 불러오는 중')} /> : null}
      {!isLoading && triggers.length === 0 ? (
        <EmptyState
          icon={<Activity className="h-6 w-6" />}
          title={koOrZh('暂无触发历史', '발동 기록이 없어요')}
          description={koOrZh('后台评估会记录 triggered、skipped、degraded 和 failed 状态；正常未触发不会写入历史。', '백그라운드 평가는 triggered, skipped, degraded, failed 상태를 기록해요. 발동하지 않은 정상 상태는 남기지 않아요.')}
        />
      ) : null}
      {!isLoading && triggers.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="border-b border-border/60 text-xs uppercase text-muted-text">
              <tr>
                <th className="px-3 py-2 font-medium">{koOrZh('状态', '상태')}</th>
                <th className="px-3 py-2 font-medium">{koOrZh('阶段 / 质量', '장 구간 / 품질')}</th>
                <th className="px-3 py-2 font-medium">{koOrZh('目标', '대상')}</th>
                <th className="px-3 py-2 font-medium">{koOrZh('观察值', '관측값')}</th>
                <th className="px-3 py-2 font-medium">{koOrZh('阈值', '기준값')}</th>
                <th className="px-3 py-2 font-medium">{koOrZh('数据源', '데이터 소스')}</th>
                <th className="px-3 py-2 font-medium">{koOrZh('数据时间', '데이터 시각')}</th>
                <th className="px-3 py-2 font-medium">{koOrZh('原因', '이유')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {triggers.map((trigger) => (
                <tr key={trigger.id} className="align-top">
                  <td className="px-3 py-3">
                    <Badge variant={statusVariant(trigger.status)}>
                      {koOrZh(statusLabel[trigger.status] ?? trigger.status, statusLabelKo[trigger.status] ?? trigger.status)}
                    </Badge>
                  </td>
                  <td className="px-3 py-3">{renderPhaseQuality(trigger)}</td>
                  <td className="px-3 py-3 font-mono text-secondary-text">{trigger.target}</td>
                  <td className="px-3 py-3 text-secondary-text">{formatNullable(trigger.observedValue)}</td>
                  <td className="px-3 py-3 text-secondary-text">{formatNullable(trigger.threshold)}</td>
                  <td className="px-3 py-3 text-secondary-text">{formatNullable(trigger.dataSource)}</td>
                  <td className="px-3 py-3 text-xs text-secondary-text">
                    {formatDateTime(trigger.dataTimestamp ?? trigger.triggeredAt)}
                  </td>
                  <td className="px-3 py-3 text-secondary-text">
                    {trigger.reason || trigger.diagnostics || '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </Card>
  );
};

import type React from 'react';
import { useCallback, useEffect, useRef, useState } from 'react';
import { BellRing } from 'lucide-react';
import { alertsApi } from '../api/alerts';
import type { ParsedApiError } from '../api/error';
import { getParsedApiError } from '../api/error';
import { AlertRuleForm } from '../components/alerts/AlertRuleForm';
import {
  AlertRuleList,
  type AlertRuleBusyState,
  type AlertRuleEnabledFilter,
  type AlertTypeFilter,
} from '../components/alerts/AlertRuleList';
import { AlertTriggerHistory } from '../components/alerts/AlertTriggerHistory';
import { ApiErrorAlert, AppPage, Card, EmptyState, InlineAlert, Loading, PageHeader } from '../components/common';
import type {
  AlertNotificationItem,
  AlertRuleCreateRequest,
  AlertRuleItem,
  AlertRuleListResponse,
  AlertRuleTestResponse,
  AlertTriggerItem,
  AlertType,
} from '../types/alerts';
import { formatDateTime } from '../utils/format';
import { koOrZh } from '../utils/uiLanguage';

const PAGE_SIZE = 20;

function enabledFilterToQuery(value: AlertRuleEnabledFilter): boolean | undefined {
  if (value === 'enabled') return true;
  if (value === 'disabled') return false;
  return undefined;
}

function alertTypeFilterToQuery(value: AlertTypeFilter): AlertType | undefined {
  return value === 'all' ? undefined : value;
}

function testVariant(result: AlertRuleTestResponse): 'success' | 'warning' | 'danger' {
  if (result.status === 'evaluation_error') return 'danger';
  return result.triggered ? 'success' : 'warning';
}

function renderTestResultMessage(result: AlertRuleTestResponse): React.ReactNode {
  const targetResults = result.targetResults ?? [];
  return (
    <div className="space-y-2">
      <div>
        {result.message}
        {koOrZh(' · 状态：', ' · 상태: ')}
        {result.status}
        {koOrZh(' · 触发：', ' · 발동: ')}
        {result.triggered ? koOrZh('是', '예') : koOrZh('否', '아니요')}
        {koOrZh(' · 观察值：', ' · 관측값: ')}
        {result.observedValue == null ? '--' : String(result.observedValue)}
      </div>
      {result.evaluatedCount != null && result.evaluatedCount > 1 ? (
        <div className="text-xs">
          {koOrZh(
            `评估 ${result.evaluatedCount} · 触发 ${result.triggeredCount ?? 0} · 降级 ${result.degradedCount ?? 0} · 跳过 ${result.skippedCount ?? 0}`,
            `평가 ${result.evaluatedCount} · 발동 ${result.triggeredCount ?? 0} · 부분 실패 ${result.degradedCount ?? 0} · 건너뜀 ${result.skippedCount ?? 0}`,
          )}
        </div>
      ) : null}
      {targetResults.length > 1 ? (
        <div className="grid gap-1 text-xs">
          {targetResults.slice(0, 20).map((item) => (
            <div key={`${item.target}-${item.status}`} className="flex flex-wrap justify-between gap-2">
              <span>{item.displayTarget ?? item.target}</span>
              <span>
                {item.status}
                {item.recordStatus ? ` / ${item.recordStatus}` : ''}
              </span>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

const notificationChannelLabel: Record<string, string> = {
  __cooldown__: '业务冷却',
  __cooldown_read_failed__: '冷却读取失败',
  __noise_suppressed__: '通知降噪',
  __no_channel__: '无可用渠道',
  __dispatch__: '通知调度',
  __context__: '会话渠道',
};

const notificationChannelLabelKo: Record<string, string> = {
  __cooldown__: '재알림 대기',
  __cooldown_read_failed__: '대기 상태 읽기 실패',
  __noise_suppressed__: '중복 알림 줄이기',
  __no_channel__: '쓸 수 있는 채널 없음',
  __dispatch__: '알림 전송',
  __context__: '대화 채널',
};

function formatNotificationChannel(channel: string): string {
  return koOrZh(notificationChannelLabel[channel] ?? channel, notificationChannelLabelKo[channel] ?? channel);
}

function formatNotificationStatus(notification: AlertNotificationItem): string {
  if (notification.success) return koOrZh('成功', '성공');
  if (notification.errorCode === 'cooldown_active') return koOrZh('冷却抑制', '재알림 대기로 보류');
  if (notification.errorCode === 'cooldown_read_failed') return koOrZh('冷却读取失败', '대기 상태 읽기 실패');
  if (notification.errorCode === 'noise_suppressed') return koOrZh('降噪抑制', '중복 알림으로 보류');
  if (notification.errorCode === 'no_channel') return koOrZh('无渠道', '채널 없음');
  return koOrZh('失败', '실패');
}

const AlertsPage: React.FC = () => {
  useEffect(() => {
    document.title = koOrZh('告警中心 - DSA', '알림 센터 - DSA');
  }, []);

  const [rules, setRules] = useState<AlertRuleItem[]>([]);
  const [rulesTotal, setRulesTotal] = useState(0);
  const [ruleSources, setRuleSources] = useState<AlertRuleListResponse['ruleSources']>(null);
  const [rulesPage, setRulesPage] = useState(1);
  const [enabledFilter, setEnabledFilter] = useState<AlertRuleEnabledFilter>('all');
  const [alertTypeFilter, setAlertTypeFilter] = useState<AlertTypeFilter>('all');
  const [rulesLoading, setRulesLoading] = useState(false);
  const [rulesError, setRulesError] = useState<ParsedApiError | null>(null);
  const [rulesLoaded, setRulesLoaded] = useState(false);
  const [rulesRefreshKey, setRulesRefreshKey] = useState(0);

  const [triggers, setTriggers] = useState<AlertTriggerItem[]>([]);
  const [triggersLoading, setTriggersLoading] = useState(false);
  const [triggersError, setTriggersError] = useState<ParsedApiError | null>(null);

  const [notifications, setNotifications] = useState<AlertNotificationItem[]>([]);
  const [notificationsLoading, setNotificationsLoading] = useState(false);
  const [notificationsError, setNotificationsError] = useState<ParsedApiError | null>(null);

  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<ParsedApiError | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [busyRule, setBusyRule] = useState<AlertRuleBusyState | null>(null);
  const [testResult, setTestResult] = useState<AlertRuleTestResponse | null>(null);
  const rulesRequestIdRef = useRef(0);

  const loadRules = useCallback(async () => {
    const requestId = rulesRequestIdRef.current + 1;
    rulesRequestIdRef.current = requestId;
    const isLatestRequest = () => rulesRequestIdRef.current === requestId;
    const requestedPage = rulesPage;
    const baseQuery = {
      enabled: enabledFilterToQuery(enabledFilter),
      alertType: alertTypeFilterToQuery(alertTypeFilter),
      pageSize: PAGE_SIZE,
    };
    setRulesLoading(true);
    try {
      let response = await alertsApi.listRules({ ...baseQuery, page: requestedPage });
      if (!isLatestRequest()) return null;
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
      if (response.items.length === 0 && response.total > 0 && requestedPage > lastPage) {
        setRulesPage(lastPage);
        response = await alertsApi.listRules({ ...baseQuery, page: lastPage });
        if (!isLatestRequest()) return null;
      }
      setRules(response.items);
      setRulesTotal(response.total);
      setRuleSources(response.ruleSources ?? null);
      setRulesError(null);
      setRulesLoaded(true);
      return response;
    } catch (error) {
      if (!isLatestRequest()) return null;
      setRulesError(getParsedApiError(error));
      return null;
    } finally {
      if (isLatestRequest()) {
        setRulesLoading(false);
      }
    }
  }, [alertTypeFilter, enabledFilter, rulesPage]);

  const loadTriggers = useCallback(async () => {
    setTriggersLoading(true);
    try {
      const response = await alertsApi.listTriggers({ page: 1, pageSize: PAGE_SIZE });
      setTriggers(response.items);
      setTriggersError(null);
    } catch (error) {
      setTriggersError(getParsedApiError(error));
    } finally {
      setTriggersLoading(false);
    }
  }, []);

  const loadNotifications = useCallback(async () => {
    setNotificationsLoading(true);
    try {
      const response = await alertsApi.listNotifications({ page: 1, pageSize: PAGE_SIZE });
      setNotifications(response.items);
      setNotificationsError(null);
    } catch (error) {
      setNotificationsError(getParsedApiError(error));
    } finally {
      setNotificationsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules, rulesRefreshKey]);

  useEffect(() => {
    if (!rulesLoaded) return;
    void loadTriggers();
    void loadNotifications();
  }, [loadNotifications, loadTriggers, rulesLoaded]);

  const handleCreateRule = async (payload: AlertRuleCreateRequest) => {
    setCreateLoading(true);
    setCreateError(null);
    setCreateSuccess(null);
    try {
      const created = await alertsApi.createRule(payload);
      setCreateSuccess(koOrZh(`已创建告警规则「${created.name}」`, `알림 규칙 「${created.name}」을 만들었어요`));
      setRulesPage(1);
      setRulesRefreshKey((value) => value + 1);
      return true;
    } catch (error) {
      setCreateError(getParsedApiError(error));
      return false;
    } finally {
      setCreateLoading(false);
    }
  };

  const handleToggleEnabled = async (rule: AlertRuleItem) => {
    setBusyRule({ id: rule.id, action: 'toggle' });
    try {
      if (rule.enabled) {
        await alertsApi.disableRule(rule.id);
      } else {
        await alertsApi.enableRule(rule.id);
      }
      setRulesRefreshKey((value) => value + 1);
    } catch (error) {
      setRulesError(getParsedApiError(error));
    } finally {
      setBusyRule(null);
    }
  };

  const handleDeleteRule = async (rule: AlertRuleItem) => {
    setBusyRule({ id: rule.id, action: 'delete' });
    try {
      await alertsApi.deleteRule(rule.id);
      setRulesRefreshKey((value) => value + 1);
    } catch (error) {
      setRulesError(getParsedApiError(error));
    } finally {
      setBusyRule(null);
    }
  };

  const handleTestRule = async (rule: AlertRuleItem) => {
    setBusyRule({ id: rule.id, action: 'test' });
    setTestResult(null);
    try {
      const result = await alertsApi.testRule(rule.id);
      setTestResult(result);
    } catch (error) {
      setRulesError(getParsedApiError(error));
    } finally {
      setBusyRule(null);
    }
  };

  return (
    <AppPage className="space-y-5">
      <PageHeader
        eyebrow="Alert Center"
        title={koOrZh('告警中心', '알림 센터')}
        description={koOrZh('管理事件告警、日线技术指标、自选股、持仓/账户联动和大盘红绿灯规则，执行一次性测试，并查看后台评估任务记录的触发历史。', '이벤트 알림, 일봉 기술 지표, 관심종목, 보유 종목·계좌 연동, 시장 신호등 규칙을 관리하고, 한 번 테스트해 보고, 백그라운드 평가가 남긴 발동 기록을 볼 수 있어요.')}
      />

      {createError ? <ApiErrorAlert error={createError} onDismiss={() => setCreateError(null)} /> : null}
      {createSuccess ? (
        <InlineAlert
          title={koOrZh('创建成功', '만들었어요')}
          message={createSuccess}
          variant="success"
          action={(
            <button type="button" className="text-sm underline" onClick={() => setCreateSuccess(null)}>
              {koOrZh('关闭', '닫기')}
            </button>
          )}
        />
      ) : null}
      {rulesError ? <ApiErrorAlert error={rulesError} onDismiss={() => setRulesError(null)} /> : null}
      {!rulesError && ruleSources && ruleSources.legacyConfigured > 0 ? (
        <InlineAlert
          title={koOrZh('存在环境变量告警规则', '환경 변수로 설정한 알림 규칙이 있어요')}
          variant="warning"
          message={koOrZh(`环境变量配置了 ${ruleSources.legacyConfigured} 条有效规则，按当前启用的页面规则去重后有 ${ruleSources.legacyEffective} 条可供后台轮询。此数量不受页面筛选影响，也不表示后台轮询已启动。页面仅管理数据库规则；删除或禁用页面规则不会停用环境规则。若需停用，请在部署配置中修改 AGENT_EVENT_ALERT_RULES_JSON 并重新加载配置。`, `환경 변수에 유효한 규칙이 ${ruleSources.legacyConfigured}개 있고, 화면 규칙과 겹치는 것을 빼면 ${ruleSources.legacyEffective}개가 백그라운드 점검 대상이에요. 이 숫자는 화면 필터와 상관없고, 백그라운드 점검이 시작됐다는 뜻도 아니에요. 이 화면은 데이터베이스 규칙만 관리해요. 화면 규칙을 지우거나 꺼도 환경 변수 규칙은 꺼지지 않으니, 끄려면 배포 설정의 AGENT_EVENT_ALERT_RULES_JSON을 고친 뒤 설정을 다시 불러와 주세요.`)}
        />
      ) : null}

      <div className="grid items-stretch gap-5 xl:grid-cols-[380px_minmax(0,1fr)]">
        <AlertRuleForm onSubmit={handleCreateRule} isSubmitting={createLoading} />
        <div className="flex h-full min-h-0 flex-col gap-4">
          <AlertRuleList
            className="flex h-full min-h-0 flex-col"
            rules={rules}
            total={rulesTotal}
            page={rulesPage}
            pageSize={PAGE_SIZE}
            isLoading={rulesLoading}
            enabledFilter={enabledFilter}
            alertTypeFilter={alertTypeFilter}
            onEnabledFilterChange={(value) => {
              setEnabledFilter(value);
              setRulesPage(1);
            }}
            onAlertTypeFilterChange={(value) => {
              setAlertTypeFilter(value);
              setRulesPage(1);
            }}
            onPageChange={setRulesPage}
            onToggleEnabled={(rule) => void handleToggleEnabled(rule)}
            onDelete={(rule) => void handleDeleteRule(rule)}
            onTest={(rule) => void handleTestRule(rule)}
            busyRule={busyRule}
          />
          {testResult ? (
            <InlineAlert
              title={koOrZh('测试结果', '테스트 결과')}
              variant={testVariant(testResult)}
              message={renderTestResultMessage(testResult)}
            />
          ) : null}
        </div>
      </div>

      {triggersError ? <ApiErrorAlert error={triggersError} onDismiss={() => setTriggersError(null)} /> : null}
      <AlertTriggerHistory triggers={triggers} isLoading={triggersLoading} />

      {notificationsError ? <ApiErrorAlert error={notificationsError} onDismiss={() => setNotificationsError(null)} /> : null}
      <Card title={koOrZh('通知尝试记录', '알림 전송 기록')} subtitle={koOrZh('通知结果', '알림 결과')} variant="bordered" padding="md">
        {notificationsLoading ? <Loading label={koOrZh('正在加载通知尝试记录', '알림 전송 기록을 불러오는 중')} /> : null}
        {!notificationsLoading && notifications.length === 0 ? (
          <EmptyState
            icon={<BellRing className="h-6 w-6" />}
            title={koOrZh('暂无通知尝试记录', '알림 전송 기록이 없어요')}
            description={koOrZh('当前没有可展示的通知尝试明细；告警触发仍会按已配置通知渠道发送。', '보여 줄 전송 기록이 없어요. 알림이 발동하면 설정한 채널로 계속 보내요.')}
          />
        ) : null}
        {!notificationsLoading && notifications.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[680px] text-left text-sm">
              <thead className="border-b border-border/60 text-xs uppercase text-muted-text">
                <tr>
                  <th className="px-3 py-2 font-medium">{koOrZh('渠道', '채널')}</th>
                  <th className="px-3 py-2 font-medium">{koOrZh('状态', '상태')}</th>
                  <th className="px-3 py-2 font-medium">{koOrZh('错误码', '오류 코드')}</th>
                  <th className="px-3 py-2 font-medium">{koOrZh('耗时', '걸린 시간')}</th>
                  <th className="px-3 py-2 font-medium">{koOrZh('时间', '시간')}</th>
                  <th className="px-3 py-2 font-medium">{koOrZh('诊断', '진단')}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {notifications.map((notification) => (
                  <tr key={notification.id}>
                    <td className="px-3 py-3">{formatNotificationChannel(notification.channel)}</td>
                    <td className="px-3 py-3">{formatNotificationStatus(notification)}</td>
                    <td className="px-3 py-3">{notification.errorCode ?? '--'}</td>
                    <td className="px-3 py-3">{notification.latencyMs == null ? '--' : `${notification.latencyMs}ms`}</td>
                    <td className="px-3 py-3">{formatDateTime(notification.createdAt)}</td>
                    <td className="px-3 py-3">{notification.diagnostics ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Card>
    </AppPage>
  );
};

export default AlertsPage;

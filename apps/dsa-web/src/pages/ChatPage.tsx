import React, { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import Markdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ChevronDown, SlidersHorizontal } from 'lucide-react';
import { cn } from '../utils/cn';
import { agentApi } from '../api/agent';
import { systemConfigApi } from '../api/systemConfig';
import { ApiErrorAlert, Badge, Button, ConfirmDialog, EmptyState, InlineAlert, ScrollArea, Tooltip } from '../components/common';
import { createParsedApiError, getParsedApiError } from '../api/error';
import type { AgentStatusResponse, SkillInfo } from '../api/agent';
import { DashboardStateBlock } from '../components/dashboard';
import {
  useAgentChatStore,
  type Message,
  type ProgressStep,
} from '../stores/agentChatStore';
import { downloadSession, formatSessionAsMarkdown } from '../utils/chatExport';
import type { ChatFollowUpContext } from '../utils/chatFollowUp';
import {
  buildFollowUpPrompt,
  parseFollowUpRecordId,
  resolveChatFollowUpContext,
  sanitizeFollowUpStockCode,
  sanitizeFollowUpStockName,
} from '../utils/chatFollowUp';
import { isNearBottom } from '../utils/chatScroll';
import { getReportText } from '../utils/reportLanguage';
import {
  findMatchingStockCode,
  includesStockCode,
  resolveRegisteredIndexCanonical,
} from '../utils/stockCode';
import { useStockIndex } from '../hooks/useStockIndex';
import { useUiLanguage } from '../contexts/UiLanguageContext';
import { koOrZh } from '../utils/uiLanguage';

// Quick question examples shown on empty state
type ActiveStockContext = Pick<ChatFollowUpContext, 'stock_code' | 'stock_name'>;

const QUICK_QUESTIONS: Array<{
  label: string;
  labelKo: string;
  skill: string;
  stockContext?: ActiveStockContext;
}> = [
  { label: '用缠论分析茅台', labelKo: '찬론(缠论)으로 구이저우 마오타이 분석해 줘', skill: 'chan_theory', stockContext: { stock_code: '600519', stock_name: '贵州茅台' } },
  { label: '波浪理论看宁德时代', labelKo: '엘리엇 파동 이론으로 CATL(닝더스다이) 봐 줘', skill: 'wave_theory', stockContext: { stock_code: '300750', stock_name: '宁德时代' } },
  { label: '分析比亚迪趋势', labelKo: 'BYD 추세 분석해 줘', skill: 'bull_trend', stockContext: { stock_code: '002594', stock_name: '比亚迪' } },
  { label: '用箱体震荡分析 A 股中芯国际 688981', labelKo: '박스권 매매 관점으로 SMIC(중신궈지) 688981 분석해 줘', skill: 'box_oscillation', stockContext: { stock_code: '688981', stock_name: '中芯国际' } },
  { label: '分析腾讯 hk00700', labelKo: '텐센트 hk00700 분석해 줘', skill: 'bull_trend', stockContext: { stock_code: 'HK00700', stock_name: '腾讯控股' } },
  { label: '用情绪周期分析东方财富', labelKo: '투자 심리 사이클로 둥팡차이푸 분석해 줘', skill: 'emotion_cycle', stockContext: { stock_code: '300059', stock_name: '东方财富' } },
];

const MAX_SELECTED_SKILLS = 3;
const CONTEXT_COMPRESSION_CONFIG_KEY = 'AGENT_CONTEXT_COMPRESSION_ENABLED';
const getMessageSkillNames = (msg: Message): string[] => {
  if (msg.skillNames?.length) return msg.skillNames;
  if (msg.skillName) return [msg.skillName];
  if (msg.skills?.length) return msg.skills;
  if (msg.skill) return [msg.skill];
  return [];
};

const getMessageSkillLabel = (msg: Message): string => getMessageSkillNames(msg).join(koOrZh('、', ', '));

const isStageDoneSuccessful = (status?: string): boolean => {
  if (!status) return true;
  const normalized = status.trim().toLowerCase();
  return ['completed', 'success', 'succeeded', 'done'].includes(normalized);
};

const getStageDoneLabel = (step: ProgressStep): string => {
  const stage = step.stage || 'stage';
  if (step.message) return step.message;
  if (isStageDoneSuccessful(step.status)) return `${stage} completed`;
  return `${stage} ${step.status || 'finished'}`;
};

const getPipelineBudgetSkippedLabel = (step: ProgressStep): string => {
  if (step.message) return step.message;
  return `${step.stage || 'pipeline'} skipped: insufficient budget`;
};

const ChatPage: React.FC = () => {
  const { t } = useUiLanguage();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [input, setInput] = useState('');
  const [skills, setSkills] = useState<SkillInfo[]>([]);
  const [defaultSkillIds, setDefaultSkillIds] = useState<string[]>([]);
  const [showSkillDesc, setShowSkillDesc] = useState<string | null>(null);
  const [mobileSkillPickerOpen, setMobileSkillPickerOpen] = useState(false);
  const [expandedThinking, setExpandedThinking] = useState<Set<string>>(new Set());
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const [isFollowUpContextLoading, setIsFollowUpContextLoading] = useState(false);
  const [sendToast, setSendToast] = useState<{
    type: 'success' | 'error';
    message: string;
  } | null>(null);
  const [contextCompressionEnabled, setContextCompressionEnabled] = useState(false);
  const [contextCompressionLoaded, setContextCompressionLoaded] = useState(false);
  const [contextCompressionSaving, setContextCompressionSaving] = useState(false);
  const [contextCompressionConfigVersion, setContextCompressionConfigVersion] = useState('');
  const [contextCompressionMaskToken, setContextCompressionMaskToken] = useState('******');
  const [contextCompressionError, setContextCompressionError] = useState<string | null>(null);
  const [copiedMessages, setCopiedMessages] = useState<Set<string>>(new Set());
  const [showJumpToBottom, setShowJumpToBottom] = useState(false);
  const [watchlistCodes, setWatchlistCodes] = useState<string[]>([]);
  const [isWatchlistActioning, setIsWatchlistActioning] = useState(false);
  const [watchlistMessage, setWatchlistMessage] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<AgentStatusResponse | null>(null);
  const [agentStatusError, setAgentStatusError] = useState<string | null>(null);
  const [agentStatusChecking, setAgentStatusChecking] = useState(true);
  // The registry is used only to validate report hints, never to confirm Chat state.
  const { index: stockIndex, loading: stockIndexLoading } = useStockIndex();

  const watchlistMessageTimerRef = useRef<number | null>(null);
  const copyResetTimerRef = useRef<Partial<Record<string, number>>>({});
  const messagesViewportRef = useRef<HTMLDivElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const isMountedRef = useRef(true);
  const sendToastTimerRef = useRef<number | null>(null);
  const followUpHydrationTokenRef = useRef(0);
  const followUpContextRef = useRef<ChatFollowUpContext | null>(null);
  const shouldStickToBottomRef = useRef(true);
  const pendingScrollBehaviorRef = useRef<ScrollBehavior>('auto');
  const agentStatusRequestIdRef = useRef(0);

  // Get localized text (default to Chinese)
  const text = getReportText('zh');

  // Cleanup timers on unmount
  useEffect(() => {
    const timers = copyResetTimerRef.current;
    return () => {
      if (sendToastTimerRef.current !== null) {
        window.clearTimeout(sendToastTimerRef.current);
      }
      Object.values(timers).forEach((timerId) => {
        if (timerId !== undefined) {
          window.clearTimeout(timerId);
        }
      });
    };
  }, []);

  // Set page title
  useEffect(() => {
    document.title = koOrZh('问股 - DSA', 'AI 상담 - DSA');
  }, []);

  useEffect(() => {
    isMountedRef.current = true;
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const loadWatchlist = useCallback(async () => {
    try {
      const codes = await systemConfigApi.getWatchlist();
      if (isMountedRef.current) {
        setWatchlistCodes(codes);
      }
    } catch {
      // ignore error silently
    }
  }, []);

  useEffect(() => {
    void loadWatchlist();
  }, [loadWatchlist]);

  const stockInWatchlist = useCallback(
    (stockCode: string) => includesStockCode(watchlistCodes, stockCode),
    [watchlistCodes],
  );

  const handleToggleWatchlist = useCallback(
    async (stockCode: string) => {
      if (!stockCode || isWatchlistActioning) return;
      setIsWatchlistActioning(true);
      setWatchlistMessage(null);
      try {
        const existingStockCode = findMatchingStockCode(watchlistCodes, stockCode);
        if (existingStockCode) {
          const codes = await systemConfigApi.removeFromWatchlist(existingStockCode);
          if (isMountedRef.current) {
            setWatchlistCodes(codes);
            setWatchlistMessage(koOrZh(`已从自选中移除 ${stockCode}`, `관심종목에서 뺐어요: ${stockCode}`));
          }
        } else {
          const codes = await systemConfigApi.addToWatchlist(stockCode);
          if (isMountedRef.current) {
            setWatchlistCodes(codes);
            setWatchlistMessage(koOrZh(`已加入自选 ${stockCode}`, `관심종목에 추가했어요: ${stockCode}`));
          }
        }
      } catch {
        if (isMountedRef.current) {
          setWatchlistMessage(koOrZh('操作失败，请重试', '처리하지 못했어요. 다시 시도해 주세요'));
        }
      } finally {
        if (isMountedRef.current) {
          setIsWatchlistActioning(false);
          if (watchlistMessageTimerRef.current !== null) {
            window.clearTimeout(watchlistMessageTimerRef.current);
          }
          watchlistMessageTimerRef.current = window.setTimeout(() => {
            if (isMountedRef.current) {
              setWatchlistMessage(null);
            }
          }, 3000);
        }
      }
    },
    [isWatchlistActioning, watchlistCodes],
  );

  const {
    messages,
    selectedSkillIds: sessionSelectedSkillIds,
    activeStockContext,
    stateContract,
    loading,
    progressSteps,
    sessionId,
    sessions,
    sessionsLoading,
    chatError,
    terminalStatus,
    setSelectedSkillIds,
    loadSessions,
    loadInitialSession,
    switchSession,
    refreshSession,
    startStream,
    clearCompletionBadge,
  } = useAgentChatStore();
  const selectedSkillIds = sessionSelectedSkillIds ?? defaultSkillIds;

  const activeStockCode = activeStockContext?.stock_code ?? null;

  const syncScrollState = useCallback(() => {
    const viewport = messagesViewportRef.current;
    if (!viewport) return;
    const nearBottom = isNearBottom({
      scrollTop: viewport.scrollTop,
      clientHeight: viewport.clientHeight,
      scrollHeight: viewport.scrollHeight,
    });
    shouldStickToBottomRef.current = nearBottom;
    setShowJumpToBottom((prev) => (nearBottom ? false : prev));
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    messagesEndRef.current?.scrollIntoView({ behavior });
  }, []);

  const requestScrollToBottom = useCallback((behavior: ScrollBehavior = 'auto') => {
    shouldStickToBottomRef.current = true;
    pendingScrollBehaviorRef.current = behavior;
    setShowJumpToBottom(false);
  }, []);

  const handleMessagesScroll = useCallback(() => {
    syncScrollState();
  }, [syncScrollState]);

  useEffect(() => {
    syncScrollState();
  }, [syncScrollState, sessionId]);

  useEffect(() => {
    const behavior = pendingScrollBehaviorRef.current;
    const shouldAutoScroll = shouldStickToBottomRef.current;
    if (!shouldAutoScroll) {
      if (messages.length > 0 || progressSteps.length > 0 || loading) {
        setShowJumpToBottom(true);
      }
      return;
    }

    const frame = window.requestAnimationFrame(() => {
      scrollToBottom(behavior);
      pendingScrollBehaviorRef.current = loading ? 'auto' : 'smooth';
    });

    return () => window.cancelAnimationFrame(frame);
  }, [messages, progressSteps, loading, sessionId, scrollToBottom]);

  useEffect(() => {
    if (!loading) {
      pendingScrollBehaviorRef.current = 'smooth';
    }
  }, [loading]);

  useEffect(() => {
    clearCompletionBadge();
  }, [clearCompletionBadge]);

  useEffect(() => {
    loadInitialSession();
  }, [loadInitialSession]);

  useEffect(() => {
    agentApi.getSkills()
      .then((res) => {
        setSkills(res.skills);
        const defaultId =
          res.default_skill_id ||
          res.skills[0]?.id ||
          '';
        setDefaultSkillIds(defaultId ? [defaultId] : []);
      })
      .catch((error) => {
        console.error('Failed to load chat skills:', error);
      });
  }, []);

  const loadAgentStatus = useCallback(async () => {
    const requestId = agentStatusRequestIdRef.current + 1;
    agentStatusRequestIdRef.current = requestId;
    setAgentStatusChecking(true);
    try {
      const status = await agentApi.getStatus();
      if (!isMountedRef.current || agentStatusRequestIdRef.current !== requestId) return;
      setAgentStatus(status);
      setAgentStatusError(null);
    } catch (error: unknown) {
      if (!isMountedRef.current || agentStatusRequestIdRef.current !== requestId) return;
      setAgentStatus(null);
      setAgentStatusError(getParsedApiError(error).message);
    } finally {
      if (isMountedRef.current && agentStatusRequestIdRef.current === requestId) {
        setAgentStatusChecking(false);
      }
    }
  }, []);

  useEffect(() => {
    void loadAgentStatus();
  }, [loadAgentStatus]);

  useEffect(() => {
    let active = true;

    void systemConfigApi.getConfig(false)
      .then((config) => {
        if (!active) {
          return;
        }
        const enabledItem = config.items.find((item) => item.key === CONTEXT_COMPRESSION_CONFIG_KEY);
        setContextCompressionEnabled(String(enabledItem?.value ?? '').trim().toLowerCase() === 'true');
        setContextCompressionConfigVersion(config.configVersion);
        setContextCompressionMaskToken(config.maskToken || '******');
        setContextCompressionLoaded(true);
        setContextCompressionError(null);
      })
      .catch((error) => {
        if (!active) {
          return;
        }
        const parsed = getParsedApiError(error);
        setContextCompressionLoaded(false);
        setContextCompressionError(parsed.message || koOrZh('无法读取上下文压缩配置', '대화 압축 설정을 읽지 못했어요'));
        console.error('Failed to load context compression setting:', error);
      });

    return () => {
      active = false;
    };
  }, []);

  const updateContextCompressionEnabled = useCallback(
    async (nextEnabled: boolean) => {
      if (!contextCompressionLoaded || contextCompressionSaving) {
        return;
      }

      const previousEnabled = contextCompressionEnabled;
      setContextCompressionEnabled(nextEnabled);
      setContextCompressionSaving(true);
      setContextCompressionError(null);

      try {
        const result = await systemConfigApi.update({
          configVersion: contextCompressionConfigVersion,
          maskToken: contextCompressionMaskToken,
          reloadNow: true,
          items: [
            {
              key: CONTEXT_COMPRESSION_CONFIG_KEY,
              value: nextEnabled ? 'true' : 'false',
            },
          ],
        });
        setContextCompressionConfigVersion(result.configVersion || contextCompressionConfigVersion);
      } catch (error) {
        const parsed = getParsedApiError(error);
        setContextCompressionEnabled(previousEnabled);
        setContextCompressionError(parsed.message || koOrZh('上下文压缩设置保存失败', '대화 압축 설정을 저장하지 못했어요'));
      } finally {
        setContextCompressionSaving(false);
      }
    },
    [
      contextCompressionConfigVersion,
      contextCompressionEnabled,
      contextCompressionLoaded,
      contextCompressionMaskToken,
      contextCompressionSaving,
    ],
  );

  const availableSkillIds = new Set(skills.map((skill) => skill.id));
  const quickQuestions = QUICK_QUESTIONS.filter((question) => availableSkillIds.size === 0 || availableSkillIds.has(question.skill));
  const selectedSkillIdSet = new Set(selectedSkillIds);
  const skillLimitReached = selectedSkillIds.length >= MAX_SELECTED_SKILLS;
  const agentConfirmedUnavailable = Boolean(agentStatus && !agentStatus.available);
  const agentAvailable = Boolean(agentStatus?.available) && !agentStatusChecking;
  const agentUnavailableMessage = agentStatus?.errorCode === 'backend_removed'
    ? t('settings.agentBackendRemoved')
    : agentStatus?.errorCode === 'agent_mode_disabled'
      ? t('chat.agentModeDisabled')
      : t('chat.defaultUnavailableMessage');
  const agentUnavailableError = agentConfirmedUnavailable
    ? createParsedApiError({
        title: t('chat.agentBackendUnavailableTitle'),
        message: agentUnavailableMessage,
        rawMessage: `${agentStatus?.errorCode || 'capability_unsupported'}: ${agentStatus?.message || ''}`,
        category: 'upstream_network',
      })
    : null;

  const getSkillNames = useCallback(
    (skillIds: string[]) => skillIds.map((id) => skills.find((s) => s.id === id)?.name || id),
    [skills],
  );

  const normalizeSelectedSkillIds = useCallback((skillIds: string[]) => {
    const normalized: string[] = [];
    for (const skillId of skillIds) {
      const cleaned = skillId.trim();
      if (cleaned && !normalized.includes(cleaned)) {
        normalized.push(cleaned);
      }
    }
    return normalized.slice(0, MAX_SELECTED_SKILLS);
  }, []);

  const toggleSkillSelection = useCallback((skillId: string) => {
    if (selectedSkillIds.includes(skillId)) {
      setSelectedSkillIds(selectedSkillIds.filter((id) => id !== skillId));
      return;
    }
    if (selectedSkillIds.length < MAX_SELECTED_SKILLS) {
      setSelectedSkillIds([...selectedSkillIds, skillId]);
    }
  }, [selectedSkillIds, setSelectedSkillIds]);

  const handleStartNewChat = useCallback(() => {
    followUpContextRef.current = null;
    requestScrollToBottom('auto');
    useAgentChatStore.getState().startNewChat();
    setSidebarOpen(false);
  }, [requestScrollToBottom]);

  const handleSwitchSession = useCallback((targetSessionId: string) => {
    if (targetSessionId === sessionId) {
      setSidebarOpen(false);
      return;
    }
    followUpContextRef.current = null;
    requestScrollToBottom('auto');
    switchSession(targetSessionId);
    setSidebarOpen(false);
  }, [requestScrollToBottom, sessionId, switchSession]);

  const confirmDelete = useCallback(() => {
    if (!deleteConfirmId) return;
    agentApi.deleteChatSession(deleteConfirmId)
      .then(() => {
        loadSessions();
        if (deleteConfirmId === sessionId) {
          handleStartNewChat();
        }
      })
      .catch((error) => {
        console.error('Failed to delete chat session:', error);
      });
    setDeleteConfirmId(null);
  }, [deleteConfirmId, sessionId, loadSessions, handleStartNewChat]);

  // Handle follow-up from report page: ?stock=600519&name=贵州茅台&recordId=xxx
  useEffect(() => {
    const rawStockCode = searchParams.get('stock');
    if (!rawStockCode) {
      // Nothing to follow up — only clear when there actually ARE stale query
      // params. Skipping the empty case avoids redundant `replace: true`
      // navigations on every effect re-run (the gate below legitimately re-runs
      // as status/registry state settles), which would otherwise clobber
      // subsequent RouterProvider navigation state asserted by other tests.
      if (searchParams.size === 0) {
        return;
      }
      setSearchParams({}, { replace: true });
      return;
    }

    if (stockIndexLoading) {
      return;
    }
    if (agentStatusChecking) {
      return;
    }

    // Registry canonical first for explicit index follow-ups (sh000016 /
    // 000016.SH / 930955.CSI / csi930955) so the report-follow-up canonical is
    // preserved end-to-end; the sanitize contract is untouched and remains the
    // stock fail-open when the registry is unavailable or the code unregistered.
    const registryCanonical = resolveRegisteredIndexCanonical(stockIndex, rawStockCode);
    const stock = registryCanonical ?? sanitizeFollowUpStockCode(rawStockCode);
    const name = sanitizeFollowUpStockName(searchParams.get('name'));
    const recordId = parseFollowUpRecordId(searchParams.get('recordId'));

    if (!stock) {
      setSearchParams({}, { replace: true });
      return;
    }

    const hydrationToken = ++followUpHydrationTokenRef.current;
    setInput(buildFollowUpPrompt(stock, name));
    followUpContextRef.current = {
      stock_code: stock,
      stock_name: name,
    };
    if (recordId !== undefined) {
      setIsFollowUpContextLoading(true);
    }
    void resolveChatFollowUpContext({
      stockCode: stock,
      stockName: name,
      recordId,
      index: stockIndex,
    }).then((context) => {
      if (!isMountedRef.current || followUpHydrationTokenRef.current !== hydrationToken) {
        return;
      }
      followUpContextRef.current = context;
    }).finally(() => {
      if (isMountedRef.current && followUpHydrationTokenRef.current === hydrationToken) {
        setIsFollowUpContextLoading(false);
      }
    });
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams, stockIndex, stockIndexLoading, agentStatusChecking]);

  const handleSend = useCallback(
    async (
      overrideMessage?: string,
      overrideSkillIds?: string[],
      overrideStockContext?: ActiveStockContext,
    ) => {
      const msgText = (overrideMessage ?? input).trim();
      if (!msgText || loading || !agentAvailable || !agentStatus) return;
      if (overrideMessage !== undefined) {
        setInput(msgText);
      }
      const requestedSkillIds = overrideSkillIds ?? sessionSelectedSkillIds;
      const usedSkillIds = normalizeSelectedSkillIds(
        requestedSkillIds ?? selectedSkillIds,
      );
      const usedSkillNames = usedSkillIds.length > 0 ? getSkillNames(usedSkillIds) : [koOrZh('通用', '일반')];
      // Only report/shortcut hints accompany this request. Ordinary follow-ups
      // rely on the server's accepted state, not a replay or a client-selected fact.
      const contextForSend = overrideStockContext ?? followUpContextRef.current ?? undefined;

      const payload = {
        message: msgText,
        session_id: sessionId,
        ...(requestedSkillIds !== null
          ? { skills: normalizeSelectedSkillIds(requestedSkillIds) }
          : {}),
        context: contextForSend ?? undefined,
      };
      await startStream(payload, {
        skillNames: usedSkillNames,
        skillName: usedSkillNames.join('、'),
        onAccepted: () => {
          followUpHydrationTokenRef.current += 1;
          followUpContextRef.current = null;
          setIsFollowUpContextLoading(false);
          setInput('');
          setMobileSkillPickerOpen(false);
          requestScrollToBottom('smooth');
        },
      });
    },
    [agentAvailable, agentStatus, getSkillNames, input, loading, normalizeSelectedSkillIds, requestScrollToBottom, selectedSkillIds, sessionId, sessionSelectedSkillIds, startStream],
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuickQuestion = (q: (typeof QUICK_QUESTIONS)[0]) => {
    setSelectedSkillIds([q.skill]);
    handleSend(koOrZh(q.label, q.labelKo), [q.skill], q.stockContext);
  };

  const showSendFeedback = useCallback((nextToast: { type: 'success' | 'error'; message: string }, durationMs: number) => {
    if (sendToastTimerRef.current !== null) {
      window.clearTimeout(sendToastTimerRef.current);
    }
    setSendToast(nextToast);
    sendToastTimerRef.current = window.setTimeout(() => {
      setSendToast(null);
      sendToastTimerRef.current = null;
    }, durationMs);
  }, []);

  const toggleThinking = (msgId: string) => {
    setExpandedThinking((prev) => {
      const next = new Set(prev);
      if (next.has(msgId)) next.delete(msgId);
      else next.add(msgId);
      return next;
    });
  };

  const copyMessageToClipboard = async (msgId: string, content: string) => {
    try {
      await navigator.clipboard.writeText(content);
      setCopiedMessages((prev) => new Set(prev).add(msgId));
      const existingTimer = copyResetTimerRef.current[msgId];
      if (existingTimer !== undefined) {
        window.clearTimeout(existingTimer);
      }
      copyResetTimerRef.current[msgId] = window.setTimeout(() => {
        setCopiedMessages((prev) => {
          const next = new Set(prev);
          next.delete(msgId);
          return next;
        });
        delete copyResetTimerRef.current[msgId];
      }, 2000);
    } catch (err) {
      console.error('Copy failed:', err);
    }
  };

  const downloadMessageAsMarkdown = useCallback((msg: Message) => {
    const skillLabel = getMessageSkillLabel(msg);
    const heading = msg.role === 'user' ? koOrZh('# 用户消息', '# 내 질문') : koOrZh(`# AI 回复${skillLabel ? ` · ${skillLabel}` : ''}`, `# AI 답변${skillLabel ? ` · ${skillLabel}` : ''}`);
    const content = [heading, '', msg.content].join('\n');
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = `${msg.role === 'user' ? 'user' : 'assistant'}-message-${msg.id}.md`;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
  }, []);

  const getCurrentStage = (steps: ProgressStep[]): string => {
    if (steps.length === 0) return koOrZh('正在连接...', '연결하는 중...');
    const last = steps[steps.length - 1];
    if (last.type === 'thinking') return last.message || koOrZh('AI 正在思考...', 'AI가 생각하는 중...');
    if (last.type === 'tool_start')
      return `${last.display_name || last.tool}...`;
    if (last.type === 'tool_done')
      return koOrZh(`${last.display_name || last.tool} 完成`, `${last.display_name || last.tool} 완료`);
    if (last.type === 'stage_start')
      return last.message || `Starting ${last.stage || 'stage'}...`;
    if (last.type === 'stage_done')
      return getStageDoneLabel(last);
    if (last.type === 'pipeline_timeout')
      return last.message || `${last.stage || 'pipeline'} timed out`;
    if (last.type === 'pipeline_budget_skipped')
      return getPipelineBudgetSkippedLabel(last);
    if (last.type === 'generating')
      return last.message || koOrZh('正在生成最终分析...', '최종 분석을 만드는 중...');
    return koOrZh('处理中...', '처리 중...');
  };

  const renderThinkingBlock = (msg: Message) => {
    if (!msg.thinkingSteps || msg.thinkingSteps.length === 0) return null;
    const isExpanded = expandedThinking.has(msg.id);
    const toolSteps = msg.thinkingSteps.filter((s) => s.type === 'tool_done');
    const totalDuration = toolSteps.reduce(
      (sum, s) => sum + (s.duration || 0),
      0,
    );
    const summary = koOrZh(`${toolSteps.length} 个工具调用 · ${totalDuration.toFixed(1)}s`, `도구 호출 ${toolSteps.length}회 · ${totalDuration.toFixed(1)}초`);

    return (
      <button
        onClick={() => toggleThinking(msg.id)}
        className="flex items-center gap-2 text-xs text-muted-text hover:text-secondary-text transition-colors mb-2 w-full text-left"
      >
        <svg
          className={`w-3 h-3 transition-transform flex-shrink-0 ${isExpanded ? 'rotate-90' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 5l7 7-7 7"
          />
        </svg>
        <span className="flex items-center gap-1.5">
          <span className="opacity-60">{koOrZh('思考过程', '생각 과정')}</span>
          <span className="text-muted-text/50">·</span>
          <span className="opacity-50">{summary}</span>
        </span>
      </button>
    );
  };

  const renderThinkingDetails = (steps: ProgressStep[]) => (
    <div className="mb-3 pl-5 border-l border-border/40 space-y-1.5 animate-fade-in">
      {steps.map((step, idx) => {
        let statusClass = 'chat-progress-item-muted';
        let iconClass = 'chat-progress-dot-muted';
        let text = '';
        if (step.type === 'thinking') {
          text = step.message || koOrZh(`第 ${step.step} 步：思考`, `${step.step}단계: 생각`);
          statusClass = 'chat-progress-item-thinking';
          iconClass = 'chat-progress-dot-thinking';
        } else if (step.type === 'tool_start') {
          text = `${step.display_name || step.tool}...`;
          statusClass = 'chat-progress-item-tool';
          iconClass = 'chat-progress-dot-tool';
        } else if (step.type === 'tool_done') {
          text = `${step.display_name || step.tool} (${step.duration}s)`;
          statusClass = step.success ? 'chat-progress-item-success' : 'chat-progress-item-danger';
          iconClass = step.success ? 'chat-progress-dot-success' : 'chat-progress-dot-danger';
        } else if (step.type === 'stage_start') {
          text = step.message || `Starting ${step.stage || 'stage'}...`;
          statusClass = 'chat-progress-item-thinking';
          iconClass = 'chat-progress-dot-thinking';
        } else if (step.type === 'stage_done') {
          const isSuccess = isStageDoneSuccessful(step.status);
          text = getStageDoneLabel(step);
          statusClass = isSuccess ? 'chat-progress-item-success' : 'chat-progress-item-danger';
          iconClass = isSuccess ? 'chat-progress-dot-success' : 'chat-progress-dot-danger';
        } else if (step.type === 'pipeline_timeout') {
          text = step.message || `${step.stage || 'pipeline'} timed out`;
          statusClass = 'chat-progress-item-danger';
          iconClass = 'chat-progress-dot-danger';
        } else if (step.type === 'pipeline_budget_skipped') {
          text = getPipelineBudgetSkippedLabel(step);
          statusClass = 'chat-progress-item-muted';
          iconClass = 'chat-progress-dot-muted';
        } else if (step.type === 'generating') {
          text = step.message || koOrZh('生成分析', '분석 생성');
          statusClass = 'chat-progress-item-generating';
          iconClass = 'chat-progress-dot-generating';
        } else {
          text = step.message || step.type;
        }
        return (
          <div
            key={idx}
            className={cn('chat-progress-item', statusClass)}
          >
            <span className={cn('chat-progress-dot', iconClass)} />
            <span className="leading-relaxed">{text}</span>
          </div>
        );
      })}
    </div>
  );

  const sidebarContent = (
    <>
      <div className="flex items-center justify-between border-b border-white/5 bg-white/2 p-3.5">
        <h2 className="text-sm font-semibold text-cyan uppercase tracking-[0.2em] flex items-center gap-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          {koOrZh('历史对话', '지난 대화')}
        </h2>
        <button
          onClick={handleStartNewChat}
          className="rounded-lg p-1.5 text-muted-text transition-all hover:bg-white/10 hover:text-foreground"
          aria-label={koOrZh('开启新对话', '새 대화 시작')}
        >
          <svg
            className="w-4 h-4"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 4v16m8-8H4"
            />
          </svg>
        </button>
      </div>
      <ScrollArea testId="chat-session-list-scroll" viewportClassName="p-3">
        {sessionsLoading ? (
          <DashboardStateBlock
            loading
            compact
            title={koOrZh('加载对话中...', '대화를 불러오는 중...')}
            className="rounded-2xl border border-dashed border-border/50 bg-surface/30"
          />
        ) : sessions.length === 0 ? (
          <DashboardStateBlock
            compact
            title={koOrZh('暂无历史对话', '지난 대화가 없어요')}
            description={koOrZh('开始提问后，这里会保留会话记录。', '질문을 시작하면 여기에 대화 기록이 남아요.')}
            className="rounded-2xl border border-dashed border-border/50 bg-surface/30"
          />
        ) : (
          <div className="space-y-2">
            {sessions.map((s) => (
              <div key={s.session_id} className="session-item-row">
                <button
                  type="button"
                  onClick={() => handleSwitchSession(s.session_id)}
                  className={`session-item ${s.session_id === sessionId ? 'active' : ''}`}
                  aria-label={koOrZh(`切换到对话 ${s.title}`, `${s.title} 대화로 이동`)}
                  aria-current={s.session_id === sessionId ? 'page' : undefined}
                >
                  <div className="indicator" />
                  <div className="content">
                    <span className="title">{s.title}</span>
                    <div className="mt-0.5 flex items-center gap-2">
                      <span className="meta">
                        {koOrZh(`${s.message_count} 条对话`, `대화 ${s.message_count}개`)}
                      </span>
                      {s.last_active && (
                        <>
                          <span className="separator" />
                          <span className="meta">
                            {new Date(s.last_active).toLocaleDateString(koOrZh('zh-CN', 'ko-KR'), { month: 'short', day: 'numeric' })}
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                </button>
                <button
                  type="button"
                  className="delete-btn"
                  onClick={() => {
                    setDeleteConfirmId(s.session_id);
                  }}
                  aria-label={koOrZh(`删除对话 ${s.title}`, `${s.title} 대화 삭제`)}
                >
                  <svg
                    className="w-3.5 h-3.5"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </ScrollArea>
    </>
  );

  const selectedSkillSummary = selectedSkillIds.length > 0
    ? getSkillNames(selectedSkillIds).join('、')
    : koOrZh('通用分析', '일반 분석');

  return (
    <div
      data-testid="chat-workspace"
      className="flex h-[calc(100vh-5rem)] w-full min-w-0 gap-4 overflow-hidden sm:h-[calc(100vh-5.5rem)] lg:h-[calc(100vh-2rem)]"
    >
      {/* Desktop sidebar */}
      <div className="hidden h-full w-64 flex-shrink-0 flex-col overflow-hidden rounded-[1.25rem] border border-white/8 bg-card/82 shadow-soft-card md:flex">
        {sidebarContent}
      </div>

      {/* Mobile sidebar overlay */}
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          onClick={() => setSidebarOpen(false)}
        >
          <div className="page-drawer-overlay absolute inset-0" />
          <div
            className="absolute left-0 top-0 bottom-0 w-72 flex flex-col glass-card overflow-hidden border-r border-white/10 bg-card/90 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            {sidebarContent}
          </div>
        </div>
      )}

      {/* Delete confirmation dialog */}
      <ConfirmDialog
        isOpen={Boolean(deleteConfirmId)}
        title={koOrZh('删除对话', '대화 삭제')}
        message={koOrZh('删除后，该对话将不可恢复，确认删除吗？', '삭제하면 이 대화는 되돌릴 수 없어요. 삭제할까요?')}
        confirmText={koOrZh('删除', '삭제')}
        cancelText={koOrZh('取消', '취소')}
        isDanger
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirmId(null)}
      />

      {/* Main chat area */}
      <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
        <header className="mb-4 flex-shrink-0 space-y-3">
          <div className="flex items-start justify-between gap-4">
            <h1 className="text-2xl font-bold text-foreground flex items-center gap-2">
              <button
                onClick={() => setSidebarOpen(true)}
                className="md:hidden p-1.5 -ml-1 rounded-lg hover:bg-hover transition-colors text-secondary-text hover:text-foreground"
                aria-label={koOrZh('历史对话', '지난 대화')}
              >
                <svg
                  className="w-5 h-5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 6h16M4 12h16M4 18h16"
                  />
                </svg>
              </button>
              <svg
                className="w-6 h-6 text-cyan"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                />
              </svg>
              {koOrZh('问股', 'AI 상담')}
              {agentStatus ? (
                <Badge
                  variant={agentStatus.errorCode === 'backend_removed' ? 'warning' : 'history'}
                  size="sm"
                >
                  {t(agentStatus.errorCode === 'backend_removed' ? 'settings.agentBackendRemovedLabel' : 'chat.defaultBackendBadge')}
                </Badge>
              ) : null}
            </h1>
            {messages.length > 0 && (
              <div className="flex flex-shrink-0 flex-wrap items-center justify-end gap-2">
                <Tooltip content={koOrZh('导出会话为 Markdown 文件', '대화를 Markdown 파일로 내보내기')}>
                  <span className="inline-flex">
                    <Button
                      variant="action-primary"
                      size="sm"
                      onClick={() => downloadSession(messages)}
                      aria-label={koOrZh('导出会话为 Markdown 文件', '대화를 Markdown 파일로 내보내기')}
                    >
                      <svg
                        className="w-4 h-4"
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
                        />
                      </svg>
                      {koOrZh('导出会话', '대화 내보내기')}
                    </Button>
                  </span>
                </Tooltip>
                <Tooltip content={koOrZh('发送到已配置的通知机器人/邮箱', '설정한 알림 봇/이메일로 보내기')}>
                  <span className="inline-flex">
                    <Button
                      variant="action-primary"
                      size="sm"
                      disabled={sending}
                      onClick={async () => {
                        if (sending) return;
                        setSending(true);
                        setSendToast(null);
                        try {
                          const content = formatSessionAsMarkdown(messages);
                          await agentApi.sendChat(content);
                          showSendFeedback({ type: 'success', message: koOrZh('已发送到通知渠道', '알림 채널로 보냈어요') }, 3000);
                        } catch (err) {
                          const parsed = getParsedApiError(err);
                          showSendFeedback({
                            type: 'error',
                            message: parsed.message || koOrZh('发送失败', '보내지 못했어요'),
                          }, 5000);
                        } finally {
                          setSending(false);
                        }
                      }}
                      aria-label={koOrZh('发送到已配置的通知机器人/邮箱', '설정한 알림 봇/이메일로 보내기')}
                    >
                      {sending ? (
                        <svg
                          className="w-4 h-4 animate-spin"
                          fill="none"
                          viewBox="0 0 24 24"
                        >
                          <circle
                            className="opacity-25"
                            cx="12"
                            cy="12"
                            r="10"
                            stroke="currentColor"
                            strokeWidth="4"
                          />
                          <path
                            className="opacity-75"
                            fill="currentColor"
                            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                          />
                        </svg>
                      ) : (
                        <svg
                          className="w-4 h-4"
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                          />
                        </svg>
                      )}
                      {koOrZh('发送', '보내기')}
                    </Button>
                  </span>
                </Tooltip>
              </div>
            )}
          </div>
          <p className="text-secondary-text text-sm">
            {t('chat.introDefault')}
          </p>
          {sendToast ? (
            <InlineAlert
              variant={sendToast.type === 'success' ? 'success' : 'danger'}
              title={sendToast.type === 'success' ? koOrZh('发送成功', '보냈어요') : koOrZh('发送失败', '보내지 못했어요')}
              message={sendToast.message}
              className="max-w-md rounded-xl px-3 py-2 text-xs shadow-none"
            />
          ) : null}
        </header>

        <div className="relative z-10 flex min-h-0 flex-1 flex-col overflow-hidden border border-white/6 bg-card/78 glass-card">
          {/* Messages */}
          <ScrollArea
            className="relative z-10 flex-1"
            viewportRef={messagesViewportRef}
            onScroll={handleMessagesScroll}
            viewportClassName="space-y-6 p-4 md:p-6"
            testId="chat-message-scroll"
          >
            {messages.length === 0 && !loading ? (
              <div className="flex h-full items-center justify-center">
                <EmptyState
                  title={koOrZh('开始问股', 'AI 상담 시작')}
                  description={t('chat.emptyDescriptionDefault')}
                  className="max-w-2xl border-dashed bg-card/55"
                  icon={(
                    <svg
                      className="h-8 w-8"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.5}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                      />
                    </svg>
                  )}
                  action={(
                    <div className="flex max-w-lg flex-wrap justify-center gap-2">
                      {quickQuestions.map((q, i) => (
                        <button
                          key={i}
                          onClick={() => handleQuickQuestion(q)}
                          disabled={!agentAvailable}
                          className="quick-question-btn disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {koOrZh(q.label, q.labelKo)}
                        </button>
                      ))}
                    </div>
                  )}
                />
              </div>
            ) : (
              messages.map((msg) => {
                const skillLabel = getMessageSkillLabel(msg);
                return (
                <div
                  key={msg.id}
                  className={`flex gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}
                >
                  <div
                    className={cn(
                      'flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[10px] font-bold shadow-sm transition-all',
                      msg.role === 'user' ? 'chat-avatar-user' : 'chat-avatar-ai'
                    )}
                  >
                    {msg.role === 'user' ? 'U' : 'AI'}
                  </div>
                  <div
                    className={cn(
                      'group/message min-w-0 w-fit max-w-[min(100%,48rem)] overflow-hidden px-5 py-3.5 transition-colors',
                      msg.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-ai'
                    )}
                  >
                    {msg.role === 'assistant' && (skillLabel || msg.backend) && (
                      <div className="mb-2 flex flex-wrap gap-2">
                        {skillLabel ? <Badge variant="info" className="chat-skill-badge shadow-none" aria-label={koOrZh(`技能 ${skillLabel}`, `전략 ${skillLabel}`)}>
                          <svg
                            className="w-3 h-3"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M13 10V3L4 14h7v7l9-11h-7z"
                            />
                          </svg>
                          {skillLabel}
                        </Badge> : null}
                        {msg.backend ? (
                          <Badge variant={msg.backend === 'codex_app_server' ? 'warning' : 'history'} size="sm">
                            {t(msg.backend === 'codex_app_server' ? 'chat.historicalCodexBackendBadge' : 'chat.defaultBackendBadge')}
                          </Badge>
                        ) : null}
                      </div>
                    )}
                    {msg.role === 'assistant' && renderThinkingBlock(msg)}
                    {msg.role === 'assistant' &&
                      expandedThinking.has(msg.id) &&
                      msg.thinkingSteps &&
                      renderThinkingDetails(msg.thinkingSteps)}
                    {msg.role === 'assistant' ? (
                      <div className="relative">
                        <div className="chat-message-actions">
                          <button
                            type="button"
                            onClick={() => copyMessageToClipboard(msg.id, msg.content)}
                            className="chat-copy-btn"
                            aria-label={copiedMessages.has(msg.id) ? text.copied : text.copy}
                          >
                            {copiedMessages.has(msg.id) ? text.copied : text.copy}
                          </button>
                          <button
                            type="button"
                            onClick={() => downloadMessageAsMarkdown(msg)}
                            className="chat-copy-btn"
                            aria-label={koOrZh('导出此条消息为 Markdown', '이 메시지를 Markdown으로 내보내기')}
                          >
                            {koOrZh('导出', '내보내기')}
                          </button>
                        </div>
                        <div className="chat-prose pr-20 sm:pr-24">
                          <Markdown remarkPlugins={[remarkGfm]}>
                            {msg.content}
                          </Markdown>
                        </div>
                      </div>
                    ) : (
                      msg.content
                        .split('\n')
                        .map((line, i) => (
                          <p
                            key={i}
                            className="mb-1 last:mb-0 leading-relaxed"
                          >
                            {line || '\u00A0'}
                          </p>
                        ))
                    )}
                  </div>
                </div>
                );
              })
            )}

            {loading && (
              <div className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-elevated text-foreground flex items-center justify-center flex-shrink-0 text-xs font-bold">
                  AI
                </div>
                <div className="min-w-[200px] max-w-[min(100%,48rem)] overflow-hidden rounded-2xl rounded-tl-sm border border-white/6 bg-card/72 px-5 py-4">
                  <div className="flex items-center gap-2.5 text-sm text-secondary-text">
                    <div className="relative w-4 h-4 flex-shrink-0">
                      <div className="absolute inset-0 rounded-full border-2 border-cyan/20" />
                      <div className="absolute inset-0 rounded-full border-2 border-cyan border-t-transparent animate-spin" />
                    </div>
                    <span className="text-secondary-text">
                      {getCurrentStage(progressSteps)}
                    </span>
                  </div>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </ScrollArea>

          {showJumpToBottom && (
            <div className="pointer-events-none absolute bottom-[5.75rem] right-4 z-20 md:bottom-24 md:right-6">
              <button
                type="button"
                className="pointer-events-auto chat-copy-btn shadow-soft-card"
                onClick={() => {
                  requestScrollToBottom('smooth');
                  scrollToBottom('smooth');
                }}
                aria-label={koOrZh('查看最新消息', '최신 메시지 보기')}
              >
                <svg
                  className="h-3.5 w-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M19 14l-7 7m0 0l-7-7m7 7V3"
                  />
                </svg>
                {koOrZh('有新消息', '새 메시지')}
              </button>
            </div>
          )}

          {/* Input area */}
          <div className="border-t border-white/6 bg-card/88 p-4 md:p-6 relative z-20">
            <div className="space-y-3">
              {chatError ? <ApiErrorAlert error={chatError.code === 'backend_removed'
                ? { ...chatError, title: t('settings.agentBackendRemovedLabel'), message: t('settings.agentBackendRemoved') }
                : chatError} /> : null}
              {chatError?.code === 'backend_removed' && (
                <Button variant="secondary" size="sm" onClick={() => navigate('/settings?category=agent')}>
                  {t('chat.openAgentSettings')}
                </Button>
              )}
              {chatError?.code === 'session_state_conflict' && (
                <Button variant="secondary" size="xsm" onClick={() => void refreshSession()}>
                  {t('chat.refreshSession')}
                </Button>
              )}
              {terminalStatus === 'timeout' ? (
                <div role="status" className="rounded-xl border border-amber-500/20 bg-amber-500/5 px-4 py-3 text-sm">
                  {t('chat.analysisTimedOut')}
                </div>
              ) : null}
              {agentUnavailableError ? (
                <div className="space-y-2">
                  <ApiErrorAlert
                    error={agentUnavailableError}
                    actionLabel={t('chat.openAgentSettings')}
                    onAction={() => navigate('/settings?category=agent')}
                  />
                  <Button variant="secondary" size="sm" onClick={() => void loadAgentStatus()}>
                    {t('chat.recheckAgentStatus')}
                  </Button>
                </div>
              ) : null}
              {agentStatusError ? (
                <InlineAlert
                  variant="warning"
                  title={t('chat.statusUnavailableTitle')}
                  message={t('chat.statusUnavailableMessage')}
                  action={(
                    <Button variant="secondary" size="sm" onClick={() => void loadAgentStatus()}>
                      {t('chat.recheckAgentStatus')}
                    </Button>
                  )}
                  className="rounded-xl px-3 py-2 text-xs shadow-none"
                />
              ) : null}
              {agentStatusChecking ? (
                <InlineAlert
                  variant="info"
                  title={t('chat.statusCheckingTitle')}
                  message={t('chat.statusCheckingMessage')}
                  className="rounded-xl px-3 py-2 text-xs shadow-none"
                />
              ) : null}
              {isFollowUpContextLoading ? (
                <InlineAlert
                  variant="info"
                  title={koOrZh('追问上下文加载中', '이어서 묻기 맥락을 불러오는 중')}
                  message={koOrZh('正在加载历史分析上下文；现在可直接发送追问。', '이전 분석 맥락을 불러오는 중이에요. 지금 바로 이어서 질문해도 돼요.')}
                  className="rounded-xl px-3 py-2 text-xs shadow-none"
                />
              ) : null}
              <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/6 bg-surface/25 px-3 py-2">
                <label
                  className={cn(
                    'inline-flex items-center gap-2 text-sm',
                    contextCompressionLoaded && !contextCompressionSaving
                      ? 'cursor-pointer text-foreground'
                      : 'cursor-not-allowed text-muted-text',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={contextCompressionEnabled}
                    disabled={!contextCompressionLoaded || contextCompressionSaving}
                    onChange={(event) => void updateContextCompressionEnabled(event.target.checked)}
                    className="chat-skill-checkbox"
                  />
                  <span className="font-medium">{koOrZh('上下文压缩', '대화 압축')}</span>
                  <span className="text-xs text-muted-text">{koOrZh('节省长会话 token', '긴 대화의 token 절약')}</span>
                </label>
                <span className="text-xs text-muted-text">
                  {contextCompressionSaving
                    ? koOrZh('保存中...', '저장 중...')
                    : contextCompressionEnabled
                      ? koOrZh('已启用', '켜짐')
                      : koOrZh('未启用', '꺼짐')}
                </span>
              </div>
              {contextCompressionError ? (
                <InlineAlert
                  variant="danger"
                  title={koOrZh('上下文压缩设置未保存', '대화 압축 설정이 저장되지 않았어요')}
                  message={contextCompressionError}
                  className="rounded-xl px-3 py-2 text-xs shadow-none"
                />
              ) : null}
              {skills.length > 0 && (
                <div className="space-y-2">
                  <button
                    type="button"
                    className="home-surface-button flex h-10 w-full items-center justify-between gap-3 rounded-xl px-3 text-left text-sm text-foreground md:hidden"
                    aria-label={mobileSkillPickerOpen ? koOrZh('收起策略选择', '전략 선택 접기') : koOrZh('展开策略选择', '전략 선택 펼치기')}
                    aria-expanded={mobileSkillPickerOpen}
                    aria-controls="chat-skill-picker-panel"
                    onClick={() => setMobileSkillPickerOpen((open) => !open)}
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <SlidersHorizontal className="h-4 w-4 flex-shrink-0" aria-hidden="true" />
                      <span className="flex-shrink-0 font-medium">{koOrZh('策略', '전략')}</span>
                      <span className="truncate text-xs text-muted-text">{selectedSkillSummary}</span>
                    </span>
                    <ChevronDown
                      className={cn(
                        'h-4 w-4 flex-shrink-0 text-muted-text transition-transform',
                        mobileSkillPickerOpen ? 'rotate-180' : '',
                      )}
                      aria-hidden="true"
                    />
                  </button>
                  <div
                    id="chat-skill-picker-panel"
                    data-testid="chat-skill-picker-panel"
                    className={cn(
                      mobileSkillPickerOpen ? 'flex' : 'hidden',
                      'max-h-40 flex-wrap items-start gap-x-5 gap-y-2 overflow-y-auto rounded-xl border border-white/6 bg-surface/25 px-3 py-2 md:flex md:max-h-none md:overflow-visible md:border-0 md:bg-transparent md:p-0',
                    )}
                  >
                    <span className="text-xs text-muted-text font-medium uppercase tracking-wider flex-shrink-0 mt-1">
                      {koOrZh('策略', '전략')}
                    </span>
                    <label className="flex items-center gap-1.5 text-sm cursor-pointer group mt-0.5">
                      <input
                        type="checkbox"
                        name="general-analysis"
                        value=""
                        checked={selectedSkillIds.length === 0}
                        onChange={() => setSelectedSkillIds([])}
                        className="chat-skill-checkbox"
                      />
                      <span
                        className={`transition-colors text-sm ${selectedSkillIds.length === 0 ? 'text-foreground font-medium' : 'text-secondary-text group-hover:text-foreground'}`}
                      >
                        {koOrZh('通用分析', '일반 분석')}
                      </span>
                    </label>
                    {skills.map((s) => {
                      const checked = selectedSkillIdSet.has(s.id);
                      const disabled = !checked && skillLimitReached;
                      return (
                        <label
                          key={s.id}
                          className={`flex items-center gap-1.5 cursor-pointer group relative mt-0.5 ${disabled ? 'opacity-60 cursor-not-allowed' : ''}`}
                          onMouseEnter={() => setShowSkillDesc(s.id)}
                          onMouseLeave={() => setShowSkillDesc(null)}
                        >
                          <input
                            type="checkbox"
                            name="skills"
                            value={s.id}
                            checked={checked}
                            disabled={disabled}
                            onChange={() => toggleSkillSelection(s.id)}
                            className="chat-skill-checkbox"
                          />
                          <span
                            className={`transition-colors text-sm ${checked ? 'text-foreground font-medium' : 'text-secondary-text group-hover:text-foreground'}`}
                          >
                            {s.name}
                          </span>
                          {showSkillDesc === s.id && s.description && (
                            <div className="skill-desc-tooltip">
                              <p className="skill-title">{s.name}</p>
                              <p>{s.description}</p>
                            </div>
                          )}
                        </label>
                      );
                    })}
                  </div>
                </div>
              )}

            <div className="text-xs text-muted-text" aria-label={t('chat.currentObjectLabel')}>
              {activeStockContext
                ? t('chat.currentObject', { object: `${activeStockContext.stock_name ? `${activeStockContext.stock_name} · ` : ''}${activeStockContext.stock_code}` })
                : t(stateContract === 'legacy' ? 'chat.objectUnconfirmedLegacy' : 'chat.objectUnconfirmed')}
            </div>
            {activeStockCode && activeStockContext?.asset_type === 'stock' && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-muted-text font-mono">{activeStockCode}</span>
                <Button
                  variant="secondary"
                  size="xsm"
                  isLoading={isWatchlistActioning}
                  onClick={() => void handleToggleWatchlist(activeStockCode)}
                  className="text-[11px]"
                >
                  {stockInWatchlist(activeStockCode) ? koOrZh('从自选删除', '관심종목에서 빼기') : koOrZh('加入自选', '관심종목에 추가')}
                </Button>
                {watchlistMessage && (
                  <span className="text-[11px] text-secondary-text animate-in fade-in">{watchlistMessage}</span>
                )}
              </div>
            )}

              <div className="flex items-end gap-3">
                <textarea
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={koOrZh('例如：分析 600519 / 茅台现在适合买入吗？ (Enter 发送, Shift+Enter 换行)', '예: 600519 분석해 줘 / 지금 마오타이 사도 될까? (Enter 보내기, Shift+Enter 줄바꿈)')}
                  disabled={loading || !agentAvailable}
                  rows={1}
                  className="input-surface input-focus-glow flex-1 min-h-[44px] max-h-[200px] rounded-xl border bg-transparent px-4 py-2.5 text-sm transition-all focus:outline-none resize-none disabled:cursor-not-allowed disabled:opacity-60"
                  style={{ height: 'auto' }}
                  onInput={(e) => {
                    const t = e.target as HTMLTextAreaElement;
                    t.style.height = 'auto';
                    t.style.height = `${Math.min(t.scrollHeight, 200)}px`;
                  }}
                />
                  <Button
                    variant="primary"
                    onClick={() => handleSend()}
                    disabled={!input.trim() || loading || !agentAvailable}
                    isLoading={loading}
                    className="btn-primary flex-shrink-0"
                  >
                    {koOrZh('发送', '보내기')}
                  </Button>

              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default ChatPage;

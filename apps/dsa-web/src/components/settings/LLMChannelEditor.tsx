import { useEffect, useMemo, useRef, useState } from 'react';
import type React from 'react';
import type { ParsedApiError } from '../../api/error';
import { getParsedApiError } from '../../api/error';
import { systemConfigApi } from '../../api/systemConfig';
import type { LLMApiSurface, LLMCapabilityCheck, LLMCapabilityCheckResult } from '../../types/systemConfig';
import { ApiErrorAlert, Badge, Button, InlineAlert, Input, Select, StatusDot, Tooltip } from '../common';
import type { ChannelProtocol } from './llmProviderTemplates';
import {
  LLM_PROVIDER_CAPABILITY_LABELS,
  LLM_PROVIDER_CAPABILITY_LABELS_KO,
  LLM_PROVIDER_SOURCE_LABELS_KO,
  LLM_PROVIDER_TEMPLATES,
  LLM_PROVIDER_TEMPLATE_TEXT_KO,
  MODELFLARE_APP_REGISTRATION_URL,
  MODELFLARE_DEFAULT_MODEL,
  MODEL_PLACEHOLDERS_BY_PROTOCOL,
  filterDiscoveredTextModels,
  getProviderTemplate,
  isKnownProviderTemplate,
} from './llmProviderTemplates';
import { SettingsHelpButton } from './SettingsHelpButton';
import { getRuntimeInitialLanguage, koOrZh } from '../../utils/uiLanguage';

const PROTOCOL_OPTIONS: Array<{ value: ChannelProtocol; label: string }> = [
  { value: 'openai', label: 'OpenAI Compatible' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'gemini', label: 'Gemini' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'vertex_ai', label: 'Vertex AI' },
  { value: 'ollama', label: 'Ollama' },
];

const API_SURFACE_OPTIONS: Array<{ value: LLMApiSurface; label: string }> = [
  { value: 'chat_completions', label: 'Chat Completions（默认）' },
  { value: 'responses', label: 'Responses API' },
];

const API_SURFACE_OPTIONS_KO: Array<{ value: LLMApiSurface; label: string }> = [
  { value: 'chat_completions', label: 'Chat Completions (기본값)' },
  { value: 'responses', label: 'Responses API' },
];

// 한국어 UI 여부는 렌더 시점에 판단한다(모듈 상수는 import 시 한 번만 평가되므로).
const isKoUi = (): boolean => getRuntimeInitialLanguage() === 'ko';

const CHANNEL_FIELD_SUFFIXES = ['PROTOCOL', 'API_SURFACE', 'BASE_URL', 'API_KEY', 'API_KEYS', 'MODELS', 'EXTRA_HEADERS', 'ENABLED'] as const;
const CHANNEL_FIELD_KEY_PATTERN = /^LLM_([A-Z0-9_]+)_(PROTOCOL|API_SURFACE|BASE_URL|API_KEY|API_KEYS|MODELS|EXTRA_HEADERS|ENABLED)$/;
const FALSEY_VALUES = new Set(['0', 'false', 'no', 'off']);
const HERMES_CHANNEL_NAME = 'hermes';
const HERMES_DEFAULT_MODEL = 'hermes-agent';

const RUNTIME_CAPABILITY_OPTIONS: Array<{ value: LLMCapabilityCheck; label: string; hint: string }> = [
  { value: 'json', label: 'JSON', hint: '检测 response_format JSON 输出是否可用。' },
  { value: 'tools', label: 'Tools', hint: '检测 function/tool calling 是否可用。' },
  { value: 'stream', label: 'Stream', hint: '检测流式输出是否能返回有效 chunk。' },
  { value: 'vision', label: 'Vision', hint: '检测当前模型是否接受 image_url 输入。' },
];

const RUNTIME_CAPABILITY_HINTS_KO: Record<LLMCapabilityCheck, string> = {
  json: 'response_format JSON 출력이 되는지 확인해요.',
  tools: 'function/tool calling이 되는지 확인해요.',
  stream: '스트리밍 출력이 정상 chunk를 돌려주는지 확인해요.',
  vision: '지금 모델이 image_url 입력을 받는지 확인해요.',
};

const CAPABILITY_STATUS_LABELS: Record<LLMCapabilityCheckResult['status'], string> = {
  passed: '通过',
  failed: '失败',
  skipped: '跳过',
};

const CAPABILITY_STATUS_LABELS_KO: Record<LLMCapabilityCheckResult['status'], string> = {
  passed: '통과',
  failed: '실패',
  skipped: '건너뜀',
};

const isHermesChannel = (channel: Pick<ChannelConfig, 'name'>): boolean => (
  channel.name.trim().toLowerCase() === HERMES_CHANNEL_NAME
);

function canonicalizeHermesRouteModel(model: string): string {
  const trimmed = model.trim() || HERMES_DEFAULT_MODEL;
  return trimmed.startsWith('openai/') ? trimmed : `openai/${trimmed}`;
}

function routeIdentityCandidates(model: string): Set<string> {
  const trimmed = model.trim();
  if (!trimmed) return new Set();
  const candidates = new Set<string>([trimmed]);
  if (!trimmed.startsWith('openai/') && !trimmed.includes('/')) {
    candidates.add(`openai/${trimmed}`);
  }
  return candidates;
}

function getRouteProvenance(
  routeProvenanceMap: Map<string, RouteProvenance>,
  model: string,
): RouteProvenance | undefined {
  for (const candidate of routeIdentityCandidates(model)) {
    const origin = routeProvenanceMap.get(candidate);
    if (origin) return origin;
  }
  return undefined;
}

const shouldUseSavedHermesSecret = (
  channel: Pick<ChannelConfig, 'name' | 'apiKey'>,
  maskToken: string,
  hasPersistedSecret: boolean,
): boolean => (
  isHermesChannel(channel) && channel.apiKey === maskToken && hasPersistedSecret
);

const hasRuntimeOnlyMaskedHermesSecret = (
  channel: Pick<ChannelConfig, 'name' | 'apiKey'>,
  maskToken: string,
  hasPersistedSecret: boolean,
): boolean => (
  isHermesChannel(channel) && channel.apiKey === maskToken && !hasPersistedSecret
);

const RUNTIME_ONLY_HERMES_SECRET_MESSAGE = '运行时注入的 Hermes Key 不会回传；如需在设置页测试，请重新输入 Key 或保存到 .env。';
const RUNTIME_ONLY_HERMES_SECRET_MESSAGE_KO = '실행 중에 넣은 Hermes 키는 화면으로 다시 불러오지 않아요. 설정 페이지에서 테스트하려면 키를 다시 입력하거나 .env에 저장해 주세요.';

interface ChannelConfig {
  id: string;
  name: string;
  protocol: ChannelProtocol;
  apiSurface: string;
  baseUrl: string;
  apiKey: string;
  models: string;
  enabled: boolean;
}

interface ChannelTestState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
}

interface ChannelDiscoveryState {
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
  models: string[];
}

interface ChannelCapabilityState {
  selected: LLMCapabilityCheck[];
  status: 'idle' | 'loading' | 'success' | 'error';
  text?: string;
  hint?: string;
  results: Partial<Record<LLMCapabilityCheck, LLMCapabilityCheckResult>>;
}

interface RuntimeConfig {
  primaryModel: string;
  agentPrimaryModel: string;
  fallbackModels: string[];
  visionModel: string;
  temperature: string;
}

interface LLMChannelEditorProps {
  items: Array<{ key: string; value: string; rawValueExists?: boolean }>;
  configVersion: string;
  maskToken: string;
  modelProviderPrefixes?: string[];
  onSaved: (updatedItems: Array<{ key: string; value: string }>) => void | Promise<void>;
  onDraftItemsChange?: (items: Array<{ key: string; value: string }>) => void;
  onDirtyChange?: (dirty: boolean) => void;
  onSavingChange?: (saving: boolean) => void;
  draftResetToken?: number;
  disabled?: boolean;
}

interface ChannelRowProps {
  channel: ChannelConfig;
  index: number;
  busy: boolean;
  visibleKey: boolean;
  expanded: boolean;
  testState?: ChannelTestState;
  discoveryState?: ChannelDiscoveryState;
  capabilityState?: ChannelCapabilityState;
  modelProviderPrefixes: ReadonlySet<string>;
  onUpdate: (index: number, field: keyof ChannelConfig, value: string | boolean) => void;
  onRemove: (index: number) => void;
  onToggleExpand: (index: number) => void;
  onToggleKeyVisibility: (index: number, nextVisible: boolean) => void;
  onTest: (channel: ChannelConfig, index: number) => void;
  onDiscoverModels: (channel: ChannelConfig) => void;
  onToggleCapability: (channel: ChannelConfig, capability: LLMCapabilityCheck) => void;
  onCheckCapabilities: (channel: ChannelConfig) => void;
}

const LLM_CHANNEL_HELP_DOCS = [
  {
    label: 'LLM 配置指南',
    href: 'https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/LLM_CONFIG_GUIDE.md',
  },
  {
    label: 'LLM 服务商配置速查',
    href: 'https://github.com/ZhuLinsen/daily_stock_analysis/blob/main/docs/llm-providers.md',
  },
];

const LLM_CHANNEL_HELP_DOCS_KO = [
  { ...LLM_CHANNEL_HELP_DOCS[0], label: 'LLM 설정 가이드' },
  { ...LLM_CHANNEL_HELP_DOCS[1], label: 'LLM 서비스 업체 설정 요약' },
];

function getLlmChannelHelpDocs() {
  return isKoUi() ? LLM_CHANNEL_HELP_DOCS_KO : LLM_CHANNEL_HELP_DOCS;
}

function HelpLabel({
  htmlFor,
  label,
  fieldKey,
  helpKey,
  examples,
  compact = false,
}: {
  htmlFor?: string;
  label: string;
  fieldKey: string;
  helpKey: string;
  examples?: string[];
  compact?: boolean;
}) {
  return (
    <div className={compact ? 'mb-1 flex items-center gap-1.5' : 'mb-2 flex items-center gap-1.5'}>
      <label
        htmlFor={htmlFor}
        className={compact ? 'text-xs text-muted-text' : 'text-sm font-medium text-foreground'}
      >
        {label}
      </label>
      <SettingsHelpButton
        fieldKey={fieldKey}
        title={label}
        helpKey={helpKey}
        examples={examples}
        docs={getLlmChannelHelpDocs()}
      />
    </div>
  );
}

function parseChannelFieldKeys(channel: ChannelConfig): string[] {
  const upperName = channel.name.trim().toUpperCase();
  return [
    `LLM_${upperName}_PROTOCOL`,
    `LLM_${upperName}_API_SURFACE`,
    `LLM_${upperName}_BASE_URL`,
    `LLM_${upperName}_ENABLED`,
    `LLM_${upperName}_API_KEY`,
    `LLM_${upperName}_API_KEYS`,
    `LLM_${upperName}_MODELS`,
    `LLM_${upperName}_EXTRA_HEADERS`,
  ];
}

function parseChannelFieldKeysFromName(name: string): string[] {
  const upperName = name.trim().toUpperCase();
  return CHANNEL_FIELD_SUFFIXES.map((suffix) => `LLM_${upperName}_${suffix}`);
}

function isChannelSecretFieldKey(key: string): boolean {
  const match = CHANNEL_FIELD_KEY_PATTERN.exec(key.toUpperCase());
  return match?.[2] === 'API_KEY' || match?.[2] === 'API_KEYS';
}

function resolveInitialChannelApiKeySource(
  channelName: string,
  initialItemValueByKey: Map<string, string>,
  initialItemSourceByKey: Map<string, boolean>,
): boolean | undefined {
  const upperName = channelName.trim().toUpperCase();
  const apiKeysKey = `LLM_${upperName}_API_KEYS`;
  const apiKeyKey = `LLM_${upperName}_API_KEY`;

  const apiKeysValue = (initialItemValueByKey.get(apiKeysKey) || '').trim();
  const apiKeyValue = (initialItemValueByKey.get(apiKeyKey) || '').trim();

  if (channelName.trim().toLowerCase() === HERMES_CHANNEL_NAME && apiKeyValue && initialItemSourceByKey.has(apiKeyKey)) {
    return initialItemSourceByKey.get(apiKeyKey);
  }
  if (apiKeysValue && initialItemSourceByKey.has(apiKeysKey)) {
    return initialItemSourceByKey.get(apiKeysKey);
  }
  if (apiKeyValue && initialItemSourceByKey.has(apiKeyKey)) {
    return initialItemSourceByKey.get(apiKeyKey);
  }

  if (apiKeyValue) {
    return initialItemSourceByKey.get(apiKeyKey);
  }
  if (apiKeysValue) {
    return initialItemSourceByKey.get(apiKeysKey);
  }
  if (upperName === 'MODELFLARE' && initialItemValueByKey.get('MODELFLARE_KEY')) {
    return initialItemSourceByKey.get('MODELFLARE_KEY');
  }
  return initialItemSourceByKey.get(apiKeysKey) ?? initialItemSourceByKey.get(apiKeyKey);
}

function resolveInitialChannelApiKeyValue(
  channelName: string,
  itemValueByKey: Map<string, string>,
  itemSourceByKey: Map<string, boolean>,
): string {
  const upperName = channelName.trim().toUpperCase();
  const apiKeysKey = `LLM_${upperName}_API_KEYS`;
  const apiKeyKey = `LLM_${upperName}_API_KEY`;

  const apiKeysValue = (itemValueByKey.get(apiKeysKey) || '').trim();
  const apiKeyValue = (itemValueByKey.get(apiKeyKey) || '').trim();

  if (channelName.trim().toLowerCase() === HERMES_CHANNEL_NAME && apiKeyValue) {
    return apiKeyValue;
  }
  if (apiKeysValue && itemSourceByKey.has(apiKeysKey)) {
    return apiKeysValue;
  }
  if (apiKeyValue && itemSourceByKey.has(apiKeyKey)) {
    return apiKeyValue;
  }
  if (apiKeysValue) {
    return apiKeysValue;
  }
  if (apiKeyValue) {
    return apiKeyValue;
  }
  if (upperName === 'MODELFLARE') {
    return itemValueByKey.get('MODELFLARE_KEY') || '';
  }
  return itemValueByKey.get(apiKeysKey) || itemValueByKey.get(apiKeyKey) || '';
}

function buildChangedItemKeys(
  channels: ChannelConfig[],
  initialChannels: ChannelConfig[],
  initialItemSourceByKey: Map<string, boolean>,
  initialItemValueByKey: Map<string, string>,
): Set<string> {
  const changedKeys = new Set<string>();
  const nextChannelNames = channels.map((channel) => channel.name.trim().toLowerCase()).join(',');
  const previousChannelNames = initialChannels.map((channel) => channel.name.trim().toLowerCase()).join(',');

  if (nextChannelNames !== previousChannelNames) {
    changedKeys.add('LLM_CHANNELS');
  }

  const maxLength = Math.max(channels.length, initialChannels.length);
  for (let index = 0; index < maxLength; index += 1) {
    const current = channels[index];
    const previous = initialChannels[index];
    if (!current && !previous) {
      continue;
    }

    if (!current) {
      const previousKeys = parseChannelFieldKeys(previous);
      for (const key of previousKeys) {
        if (initialItemSourceByKey.get(key.toUpperCase()) !== false) {
          changedKeys.add(key);
        }
      }
      continue;
    }

    if (!previous) {
      for (const key of parseChannelFieldKeys(current)) {
        changedKeys.add(key);
      }
      continue;
    }

    const currentName = current.name.trim().toUpperCase();
    const previousName = previous.name.trim().toUpperCase();
    if (currentName !== previousName) {
      const previousApiKeySource = resolveInitialChannelApiKeySource(
        previous.name,
        initialItemValueByKey,
        initialItemSourceByKey,
      );
      const preserveRuntimeOnlySecret = previousApiKeySource === false && current.apiKey === previous.apiKey;
      const previousKeys = parseChannelFieldKeys(previous);
      for (const key of previousKeys) {
        if (initialItemSourceByKey.get(key.toUpperCase()) !== false) {
          changedKeys.add(key);
        }
      }

      for (const key of parseChannelFieldKeys(current)) {
        if (preserveRuntimeOnlySecret && isChannelSecretFieldKey(key)) {
          continue;
        }
        changedKeys.add(key);
      }
      continue;
    }

    const prefix = `LLM_${currentName}`;
    if (current.protocol !== previous.protocol) {
      changedKeys.add(`${prefix}_PROTOCOL`);
    }
    if (current.apiSurface !== previous.apiSurface) {
      changedKeys.add(`${prefix}_API_SURFACE`);
    }
    if (current.baseUrl !== previous.baseUrl) {
      changedKeys.add(`${prefix}_BASE_URL`);
    }
    if (current.enabled !== previous.enabled) {
      changedKeys.add(`${prefix}_ENABLED`);
    }
    if (current.apiKey !== previous.apiKey) {
      changedKeys.add(`${prefix}_API_KEY`);
      changedKeys.add(`${prefix}_API_KEYS`);
    }
    if (current.models !== previous.models) {
      changedKeys.add(`${prefix}_MODELS`);
    }
  }

  return changedKeys;
}

const ChannelRow: React.FC<ChannelRowProps> = ({
  channel,
  index,
  busy,
  visibleKey,
  expanded,
  testState,
  discoveryState,
  capabilityState,
  modelProviderPrefixes,
  onUpdate,
  onRemove,
  onToggleExpand,
  onToggleKeyVisibility,
  onTest,
  onDiscoverModels,
  onToggleCapability,
  onCheckCapabilities,
}) => {
  const preset = getProviderTemplate(channel.name);
  const showProviderTemplateDetails = isKnownProviderTemplate(channel.name);
  const koUi = isKoUi();
  const presetTextKo = koUi && preset ? LLM_PROVIDER_TEMPLATE_TEXT_KO[preset.channelId] : undefined;
  const displayName = presetTextKo?.label || preset?.label || channel.name;
  const providerCapabilities = showProviderTemplateDetails ? (preset?.capabilities || []) : [];
  const providerSources = showProviderTemplateDetails ? (preset?.officialSources || []) : [];
  const providerHint = showProviderTemplateDetails
    ? (preset?.configHint && presetTextKo?.configHint) || preset?.configHint
    : undefined;
  const selectedModels = splitModels(channel.models);
  const runtimeCapabilityOptions = isHermesChannel(channel)
    ? RUNTIME_CAPABILITY_OPTIONS.filter((option) => option.value === 'json')
    : RUNTIME_CAPABILITY_OPTIONS;
  const discoveredModels = filterDiscoveredTextModels(discoveryState?.models || []);
  const manualOnlyModels = selectedModels.filter(
    (model) => !discoveredModels.some((discoveredModel) => (
      areModelsEquivalent(model, discoveredModel, channel.protocol, modelProviderPrefixes, channel.baseUrl)
    )),
  );
  const modelCount = selectedModels.length;
  const hasKey = channel.apiKey.length > 0;
  const statusVariant = testState?.status === 'success'
    ? 'success'
    : testState?.status === 'error'
      ? 'danger'
      : testState?.status === 'loading'
        ? 'warning'
        : 'default';
  const selectedCapabilities = capabilityState?.selected || [];
  const capabilityResults = capabilityState?.results || {};
  const capabilityBusy = capabilityState?.status === 'loading';
  const channelNameInputId = `llm-channel-${channel.id}-name`;
  const protocolInputId = `llm-channel-${channel.id}-protocol`;
  const apiSurfaceInputId = `llm-channel-${channel.id}-api-surface`;
  const baseUrlInputId = `llm-channel-${channel.id}-base-url`;
  const apiKeyInputId = `llm-channel-${channel.id}-api-key`;
  const modelsInputId = `llm-channel-${channel.id}-models`;
  const surfaceOptions = koUi ? API_SURFACE_OPTIONS_KO : API_SURFACE_OPTIONS;
  const apiSurfaceOptions = surfaceOptions.some((option) => option.value === channel.apiSurface)
    ? surfaceOptions
    : [
        { value: channel.apiSurface, label: koOrZh(`无效配置：${channel.apiSurface}`, `잘못된 설정: ${channel.apiSurface}`) },
        ...surfaceOptions,
      ];

  return (
    <div className="mb-2 overflow-hidden rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] shadow-soft-card transition-[background-color,border-color,box-shadow] duration-200 hover:border-[var(--settings-border-strong)] hover:bg-[var(--settings-surface-hover)]">
      <div
        className="flex cursor-pointer select-none items-center gap-2.5 px-4 py-3 transition-colors"
        onClick={() => onToggleExpand(index)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            onToggleExpand(index);
          }
        }}
        role="button"
        tabIndex={0}
      >
        <span className={`w-4 shrink-0 text-[11px] text-muted-text transition-transform ${expanded ? 'rotate-90' : ''}`}>▶</span>

        <input
          type="checkbox"
          checked={channel.enabled}
          disabled={busy}
          className="settings-input-checkbox h-4 w-4 shrink-0 rounded border-border/70 bg-base"
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onUpdate(index, 'enabled', e.target.checked)}
        />

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-semibold text-foreground">{displayName}</span>
            <Badge variant="info" className="hidden sm:inline-flex">
              {channel.protocol}
            </Badge>
          </div>
          <p className="mt-0.5 truncate text-[11px] text-secondary-text">
            {modelCount > 0 ? koOrZh(`${modelCount} 个模型已配置`, `모델 ${modelCount}개 설정됨`) : koOrZh('未配置模型', '설정된 모델 없음')}
          </p>
        </div>

        <span className="flex shrink-0 items-center gap-2">
          {testState?.status === 'success' ? (
            <Tooltip content={koOrZh('连接正常', '연결 정상')}>
              <span className="inline-flex">
                <StatusDot tone="success" />
              </span>
            </Tooltip>
          ) : null}
          {testState?.status === 'error' ? (
            <Tooltip content={koOrZh('连接失败', '연결 실패')}>
              <span className="inline-flex">
                <StatusDot tone="danger" />
              </span>
            </Tooltip>
          ) : null}
          {testState?.status === 'loading' ? (
            <Tooltip content={koOrZh('测试中', '테스트 중')}>
              <span className="inline-flex">
                <StatusDot tone="warning" pulse />
              </span>
            </Tooltip>
          ) : null}
          {!hasKey && channel.protocol !== 'ollama' ? <Badge variant="warning">{koOrZh('未填 Key', 'API 키 없음')}</Badge> : null}
          {testState?.status !== 'idle' ? (
            <Badge variant={statusVariant}>
              {testState?.status === 'success' ? koOrZh('连接正常', '연결 정상') : testState?.status === 'error' ? koOrZh('连接失败', '연결 실패') : koOrZh('测试中', '테스트 중')}
            </Badge>
          ) : null}
        </span>

        <Tooltip content={koOrZh('删除渠道', '채널 삭제')}>
          <span className="inline-flex">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 shrink-0 px-2 text-xs text-muted-text hover:text-rose-300"
              disabled={busy}
              onClick={(e) => {
                e.stopPropagation();
                onRemove(index);
              }}
            >
              ✕
            </Button>
          </span>
        </Tooltip>
      </div>

      {expanded ? (
        <div className="settings-surface-overlay-soft space-y-4 px-4 py-4">
          <div className="grid gap-2 sm:grid-cols-3">
            <div>
              <HelpLabel
                htmlFor={channelNameInputId}
                label={koOrZh('渠道名称', '채널 이름')}
                fieldKey="LLM_CHANNEL_NAME"
                helpKey="settings.llm_channel.channel_name"
                examples={['LLM_CHANNELS=deepseek,aihubmix', 'LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro']}
              />
            <Input
              id={channelNameInputId}
              value={channel.name}
              disabled={busy}
              onChange={(e) => onUpdate(index, 'name', e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
              placeholder="primary"
            />
            </div>
            <div className="space-y-2">
              <HelpLabel
                htmlFor={protocolInputId}
                label={koOrZh('协议', '프로토콜')}
                fieldKey="LLM_CHANNEL_PROTOCOL"
                helpKey="settings.llm_channel.protocol"
                examples={['LLM_DEEPSEEK_PROTOCOL=deepseek', 'LLM_OPENROUTER_PROTOCOL=openai']}
              />
              <Select
                id={protocolInputId}
                value={channel.protocol}
                onChange={(v) => onUpdate(index, 'protocol', normalizeProtocol(v))}
                options={PROTOCOL_OPTIONS}
                disabled={busy}
                placeholder={koOrZh('选择协议', '프로토콜 선택')}
              />
            </div>
            <div className="space-y-2">
              <HelpLabel
                htmlFor={apiSurfaceInputId}
                label="API Surface"
                fieldKey="LLM_CHANNEL_API_SURFACE"
                helpKey="settings.llm_channel.api_surface"
                examples={['LLM_ANSPIRE_API_SURFACE=responses', 'LLM_OPENAI_API_SURFACE=chat_completions']}
              />
              <Select
                id={apiSurfaceInputId}
                value={channel.apiSurface}
                onChange={(value) => onUpdate(index, 'apiSurface', value)}
                options={apiSurfaceOptions}
                disabled={busy || (isHermesChannel(channel) && channel.apiSurface === 'chat_completions')}
                placeholder={koOrZh('选择 API Surface', 'API Surface 선택')}
              />
            </div>
          </div>

          <div>
            <HelpLabel
              htmlFor={baseUrlInputId}
              label="Base URL"
              fieldKey="LLM_CHANNEL_BASE_URL"
              helpKey="settings.llm_channel.base_url"
              examples={['LLM_DEEPSEEK_BASE_URL=https://api.deepseek.com', 'LLM_OPENROUTER_BASE_URL=https://openrouter.ai/api/v1']}
            />
          <Input
            id={baseUrlInputId}
            value={channel.baseUrl}
            disabled={busy}
            onChange={(e) => onUpdate(index, 'baseUrl', e.target.value)}
            placeholder={
              channel.protocol === 'gemini' || channel.protocol === 'anthropic'
                ? koOrZh('官方接口可留空', '공식 API는 비워 둬도 돼요')
                : preset?.baseUrl || 'https://api.example.com/v1'
            }
          />
          </div>

          {showProviderTemplateDetails ? (
            <div className="space-y-2 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] p-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] font-medium text-muted-text">{koOrZh('配置参考', '설정 참고')}</span>
                {providerCapabilities.map((capability) => {
                  const capabilityMeta = koUi
                    ? LLM_PROVIDER_CAPABILITY_LABELS_KO[capability]
                    : LLM_PROVIDER_CAPABILITY_LABELS[capability];
                  return (
                    <Tooltip key={capability} content={capabilityMeta.hint}>
                      <span className="inline-flex">
                        <Badge variant="default" className="border-[var(--settings-border)] bg-[var(--settings-surface)] text-secondary-text">
                          {capabilityMeta.label}
                        </Badge>
                      </span>
                    </Tooltip>
                  );
                })}
              </div>
              {providerHint ? (
                <p className="text-[11px] leading-5 text-secondary-text">{providerHint}</p>
              ) : null}
              {providerSources.length > 0 ? (
                <p className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] leading-5 text-secondary-text">
                  <span>{koOrZh('官方来源：', '공식 자료:')}</span>
                  {providerSources.map((source) => (
                    <a
                      key={source.url}
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="settings-accent-text underline-offset-2 hover:underline"
                    >
                      {(koUi && LLM_PROVIDER_SOURCE_LABELS_KO[source.label]) || source.label}
                    </a>
                  ))}
                </p>
              ) : null}
              <p className="text-[11px] leading-5 text-muted-text">
                {koOrZh('能力标签仅用于配置参考，不代表运行时能力已验证通过。', '기능 태그는 설정 참고용이에요. 실제로 동작하는지 확인된 건 아니에요.')}
              </p>
            </div>
          ) : null}

          <div>
            <HelpLabel
              htmlFor={apiKeyInputId}
              label="API Key"
              fieldKey="LLM_CHANNEL_API_KEY"
              helpKey="settings.llm_channel.api_key"
              examples={['LLM_DEEPSEEK_API_KEY=sk-xxxx', 'LLM_OPENAI_API_KEYS=sk-key-1,sk-key-2']}
            />
          <Input
            id={apiKeyInputId}
            type="password"
            allowTogglePassword
            iconType="key"
            passwordVisible={visibleKey}
            onPasswordVisibleChange={(nextVisible) => onToggleKeyVisibility(index, nextVisible)}
            value={channel.apiKey}
            disabled={busy}
            onChange={(e) => onUpdate(index, 'apiKey', e.target.value)}
            placeholder={channel.protocol === 'ollama' ? koOrZh('本地 Ollama 可留空', '로컬 Ollama는 비워 둬도 돼요') : koOrZh('支持多个 Key 逗号分隔', '키가 여러 개면 쉼표로 구분해 주세요')}
          />
          </div>

          <div className="space-y-3 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] p-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="settings-secondary"
                size="sm"
                className="px-3 text-[11px] shadow-none"
                disabled={busy}
                onClick={() => onDiscoverModels(channel)}
              >
                {discoveryState?.status === 'loading' ? koOrZh('获取中...', '가져오는 중...') : koOrZh('获取模型', '모델 가져오기')}
              </Button>
              <span className={`text-xs ${
                discoveryState?.status === 'success'
                  ? 'text-success'
                  : discoveryState?.status === 'error'
                    ? 'text-danger'
                    : 'text-muted-text'
              }`}
              >
                {discoveryState?.text || koOrZh('支持 `/models` 的 OpenAI Compatible 渠道可自动拉取模型。', '`/models`를 지원하는 OpenAI Compatible 채널은 모델 목록을 자동으로 가져올 수 있어요.')}
              </span>
            </div>
            {discoveryState?.hint ? (
              <p className="text-[11px] text-secondary-text">
                {discoveryState.hint}
              </p>
            ) : null}

            {discoveredModels.length > 0 ? (
              <div>
                <HelpLabel
                  label={koOrZh('可选模型（可多选）', '선택할 수 있는 모델 (여러 개 선택 가능)')}
                  fieldKey="LLM_CHANNEL_DISCOVERED_MODELS"
                  helpKey="settings.llm_channel.models"
                  examples={['LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro']}
                />
                <div className="max-h-48 space-y-2 overflow-y-auto rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface)] p-3">
                  {discoveredModels.map((model) => (
                    <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
                      <input
                        type="checkbox"
                        checked={selectedModels.some((selectedModel) => (
                          areModelsEquivalent(selectedModel, model, channel.protocol, modelProviderPrefixes, channel.baseUrl)
                        ))}
                        disabled={busy}
                        onChange={() => onUpdate(
                          index,
                          'models',
                          toggleModelSelection(channel.models, model, channel.protocol, modelProviderPrefixes, channel.baseUrl),
                        )}
                        className="settings-input-checkbox h-4 w-4 rounded border-border/70 bg-base"
                      />
                      <span>{model}</span>
                    </label>
                  ))}
                </div>
              </div>
            ) : null}

            <div>
              <HelpLabel
                htmlFor={modelsInputId}
                label={discoveredModels.length > 0 ? koOrZh('手动模型（逗号分隔）', '직접 입력한 모델 (쉼표로 구분)') : koOrZh('模型（逗号分隔）', '모델 (쉼표로 구분)')}
                fieldKey="LLM_CHANNEL_MODELS"
                helpKey="settings.llm_channel.models"
                examples={['LLM_DEEPSEEK_MODELS=deepseek-v4-flash,deepseek-v4-pro', 'LLM_OLLAMA_MODELS=qwen3:8b,llama3.1:8b']}
              />
            <Input
              id={modelsInputId}
              value={channel.models}
              disabled={busy}
              onChange={(e) => onUpdate(index, 'models', e.target.value)}
              placeholder={preset?.placeholderModels || MODEL_PLACEHOLDERS_BY_PROTOCOL[channel.protocol]}
              hint={
                discoveredModels.length > 0
                  ? koOrZh('如有自定义模型名未出现在列表中，可继续手动补充，保存格式仍为逗号分隔。', '목록에 없는 모델 이름은 직접 추가할 수 있어요. 저장할 때도 쉼표로 구분해요.')
                  : koOrZh('若渠道不支持自动发现或请求失败，可直接手动填写模型列表。', '채널이 자동 조회를 지원하지 않거나 요청이 실패하면 모델 목록을 직접 입력해 주세요.')
              }
            />
            </div>

            {manualOnlyModels.length > 0 ? (
              <p className="text-[11px] text-secondary-text">
                {koOrZh('额外手动模型：', '직접 추가한 모델: ')}{manualOnlyModels.join(koOrZh('，', ', '))}
              </p>
            ) : null}
          </div>

          <div className="flex items-center gap-2 pt-1">
            <Button
              type="button"
              variant="settings-secondary"
              size="sm"
              className="px-3 text-[11px] shadow-none"
              disabled={busy}
              onClick={() => onTest(channel, index)}
            >
              {testState?.status === 'loading' ? koOrZh('测试中...', '테스트 중...') : koOrZh('测试连接', '연결 테스트')}
            </Button>
            {testState?.text ? (
              <div className="space-y-1">
                <span className={`block text-xs ${
                  testState.status === 'success'
                    ? 'text-success'
                    : testState.status === 'error'
                      ? 'text-danger'
                      : 'text-muted-text'
                }`}
                >
                  {testState.text}
                </span>
                {selectedModels[0] ? (
                  <p className="text-[11px] text-secondary-text">
                    {koOrZh('基础连接测试默认使用模型列表首项：', '기본 연결 테스트는 모델 목록의 첫 번째 모델을 써요: ')}{selectedModels[0]}
                  </p>
                ) : null}
                {testState.hint ? (
                  <p className="text-[11px] text-secondary-text">
                    {testState.hint}
                  </p>
                ) : null}
              </div>
            ) : null}
          </div>

          <div className="space-y-3 rounded-xl border border-[var(--settings-border)] bg-[var(--settings-surface-hover)] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div>
                <div className="flex items-center gap-1.5">
                  <p className="text-[11px] font-medium text-muted-text">{koOrZh('运行时能力检测（可选）', '기능 점검 (선택)')}</p>
                  <SettingsHelpButton
                    fieldKey="LLM_CHANNEL_CAPABILITY_CHECKS"
                    title={koOrZh('运行时能力检测', '기능 점검')}
                    helpKey="settings.llm_channel.capability_checks"
                    examples={['JSON / Tools / Stream / Vision']}
                    docs={getLlmChannelHelpDocs()}
                  />
                </div>
                <p className="mt-0.5 text-[11px] text-secondary-text">
                  {koOrZh('仅在手动触发时发起真实 LLM 请求；多选可能需要 20-40 秒。', '직접 누를 때만 실제 LLM 요청을 보내요. 여러 개를 고르면 20~40초 걸릴 수 있어요.')}
                </p>
              </div>
              <Button
                type="button"
                variant="settings-secondary"
                size="sm"
                className="px-3 text-[11px] shadow-none"
                disabled={busy || capabilityBusy || selectedCapabilities.length === 0}
                onClick={() => onCheckCapabilities(channel)}
              >
                {capabilityBusy ? koOrZh('检测中...', '점검 중...') : koOrZh('检测能力', '기능 점검')}
              </Button>
            </div>

            <div className="flex flex-wrap gap-2">
              {runtimeCapabilityOptions.map((option) => (
                <Tooltip key={option.value} content={koUi ? RUNTIME_CAPABILITY_HINTS_KO[option.value] : option.hint}>
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--settings-border)] bg-[var(--settings-surface)] px-2 py-1 text-[11px] text-secondary-text">
                    <input
                      type="checkbox"
                      checked={selectedCapabilities.includes(option.value)}
                      disabled={busy || capabilityBusy}
                      onChange={() => onToggleCapability(channel, option.value)}
                      className="settings-input-checkbox h-3.5 w-3.5 rounded border-border/70 bg-base"
                    />
                    <span>{option.label}</span>
                  </label>
                </Tooltip>
              ))}
            </div>

            {capabilityState?.text ? (
              <div className="space-y-1">
                <p className={`text-xs ${
                  capabilityState.status === 'success'
                    ? 'text-success'
                    : capabilityState.status === 'error'
                      ? 'text-danger'
                      : 'text-muted-text'
                }`}
                >
                  {capabilityState.text}
                </p>
                {capabilityState.hint ? (
                  <p className="text-[11px] text-secondary-text">{capabilityState.hint}</p>
                ) : null}
              </div>
            ) : null}

            {Object.keys(capabilityResults).length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {RUNTIME_CAPABILITY_OPTIONS.map((option) => {
                  const result = capabilityResults[option.value];
                  if (!result) return null;
                  return (
                    <Tooltip key={option.value} content={result.message}>
                      <span className="inline-flex">
                        <Badge variant={getCapabilityResultVariant(result.status)}>
                          {option.label} {(koUi ? CAPABILITY_STATUS_LABELS_KO : CAPABILITY_STATUS_LABELS)[result.status]}
                        </Badge>
                      </span>
                    </Tooltip>
                  );
                })}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
};

function normalizeProtocol(value: string): ChannelProtocol {
  const normalized = value.trim().toLowerCase().replace(/-/g, '_');
  if (normalized === 'vertex' || normalized === 'vertexai') {
    return 'vertex_ai';
  }
  if (normalized === 'claude') {
    return 'anthropic';
  }
  if (normalized === 'google') {
    return 'gemini';
  }
  if (normalized === 'deepseek') {
    return 'deepseek';
  }
  if (normalized === 'gemini') {
    return 'gemini';
  }
  if (normalized === 'anthropic') {
    return 'anthropic';
  }
  if (normalized === 'vertex_ai') {
    return 'vertex_ai';
  }
  if (normalized === 'ollama') {
    return 'ollama';
  }
  return 'openai';
}

function inferProtocol(protocol: string, baseUrl: string, models: string[]): ChannelProtocol {
  const explicit = normalizeProtocol(protocol);
  if (protocol.trim()) {
    return explicit;
  }

  if (isRequestyBaseUrl(baseUrl)) {
    return 'openai';
  }

  const firstPrefixedModel = models.find((model) => model.includes('/'));
  if (firstPrefixedModel) {
    return normalizeProtocol(firstPrefixedModel.split('/', 1)[0]);
  }

  if (baseUrl.includes('127.0.0.1') || baseUrl.includes('localhost')) {
    return 'openai';
  }

  return 'openai';
}

function parseEnabled(value: string | undefined): boolean {
  if (!value) {
    return true;
  }
  return !FALSEY_VALUES.has(value.trim().toLowerCase());
}

function splitModels(models: string): string[] {
  return models
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
}

interface ParsedModelRef {
  name: string;
  provider: string;
  hasProvider: boolean;
}

function parseModelRef(model: string): ParsedModelRef {
  const trimmed = model.trim();
  if (!trimmed) {
    return { name: '', provider: '', hasProvider: false };
  }

  const delimiterIndex = trimmed.indexOf('/');
  if (delimiterIndex < 0) {
    return { name: trimmed.toLowerCase(), provider: '', hasProvider: false };
  }

  const rawProvider = trimmed.slice(0, delimiterIndex).trim();
  const name = trimmed.slice(delimiterIndex + 1).trim();
  if (!rawProvider || !name) {
    return { name: '', provider: '', hasProvider: false };
  }

  const lowerProvider = rawProvider.toLowerCase();
  return {
    name: name.toLowerCase(),
    provider: PROTOCOL_ALIASES[lowerProvider] || lowerProvider,
    hasProvider: true,
  };
}

function getModelComparisonKey(
  model: string,
  protocol: ChannelProtocol,
  modelProviderPrefixes: ReadonlySet<string>,
  baseUrl = '',
): string {
  const normalizedModel = normalizeModelForRuntime(model, protocol, modelProviderPrefixes, baseUrl).trim();
  const parsed = parseModelRef(normalizedModel);
  if (!parsed.name) {
    return '';
  }
  return `${parsed.provider}/${parsed.name}`;
}

function areModelsEquivalent(
  a: string,
  b: string,
  protocol: ChannelProtocol,
  modelProviderPrefixes: ReadonlySet<string>,
  baseUrl = '',
): boolean {
  const left = getModelComparisonKey(a, protocol, modelProviderPrefixes, baseUrl);
  const right = getModelComparisonKey(b, protocol, modelProviderPrefixes, baseUrl);
  return left !== '' && left === right;
}

function toggleModelSelection(
  models: string,
  targetModel: string,
  protocol: ChannelProtocol,
  modelProviderPrefixes: ReadonlySet<string>,
  baseUrl = '',
): string {
  const selectedModels = splitModels(models);
  const index = selectedModels.findIndex((model) => (
    areModelsEquivalent(model, targetModel, protocol, modelProviderPrefixes, baseUrl)
  ));
  if (index >= 0) {
    return selectedModels.filter((_, itemIndex) => itemIndex !== index).join(',');
  }
  return [...selectedModels, targetModel].join(',');
}

const PROTOCOL_ALIASES: Record<string, string> = {
  vertexai: 'vertex_ai',
  vertex: 'vertex_ai',
  claude: 'anthropic',
  google: 'gemini',
  openai_compatible: 'openai',
  openai_compat: 'openai',
};

function isRequestyBaseUrl(baseUrl: string): boolean {
  const trimmed = baseUrl.trim();
  if (!trimmed) {
    return false;
  }
  try {
    const hostname = new URL(trimmed).hostname.toLowerCase();
    return hostname === 'requesty.ai' || hostname.endsWith('.requesty.ai');
  } catch {
    return false;
  }
}

function normalizeModelForRuntime(
  model: string,
  protocol: ChannelProtocol,
  modelProviderPrefixes: ReadonlySet<string>,
  baseUrl = '',
): string {
  const trimmedModel = model.trim();
  if (!trimmedModel) {
    return trimmedModel;
  }

  // Mirrors normalize_llm_channel_model: Requesty vendor IDs keep the gateway route.
  if (
    protocol === 'openai'
    && trimmedModel.includes('/')
    && trimmedModel.split('/', 1)[0].trim().toLowerCase() !== 'openai'
    && isRequestyBaseUrl(baseUrl)
  ) {
    return `openai/${trimmedModel}`;
  }

  if (trimmedModel.includes('/')) {
    const rawPrefix = trimmedModel.split('/', 1)[0].trim();
    const lowerPrefix = rawPrefix.toLowerCase();
    const canonicalPrefix = PROTOCOL_ALIASES[lowerPrefix] || lowerPrefix;
    const isProtocolPrefix = canonicalPrefix === protocol;
    if (isProtocolPrefix || modelProviderPrefixes.has(lowerPrefix) || modelProviderPrefixes.has(canonicalPrefix)) {
      if (canonicalPrefix !== lowerPrefix && (isProtocolPrefix || modelProviderPrefixes.has(canonicalPrefix))) {
        return `${canonicalPrefix}/${trimmedModel.split('/').slice(1).join('/')}`;
      }
      return trimmedModel;
    }
    return `${protocol}/${trimmedModel}`;
  }

  return `${protocol}/${trimmedModel}`;
}

function resolveModelPreview(
  models: string,
  protocol: ChannelProtocol,
  modelProviderPrefixes: ReadonlySet<string>,
  baseUrl = '',
): string[] {
  return splitModels(models).map((model) => (
    normalizeModelForRuntime(model, protocol, modelProviderPrefixes, baseUrl)
  ));
}

interface RouteProvenance {
  routeName: string;
  hasHermes: boolean;
  hasNonHermes: boolean;
}

function resolveChannelRouteModels(
  channel: ChannelConfig,
  modelProviderPrefixes: ReadonlySet<string>,
): string[] {
  if (isHermesChannel(channel)) {
    const models = splitModels(channel.models);
    return (models.length > 0 ? models : [HERMES_DEFAULT_MODEL]).map(canonicalizeHermesRouteModel);
  }
  return resolveModelPreview(channel.models, channel.protocol, modelProviderPrefixes, channel.baseUrl);
}

function buildRouteProvenanceMap(
  channels: ChannelConfig[],
  modelProviderPrefixes: ReadonlySet<string>,
): Map<string, RouteProvenance> {
  const provenance = new Map<string, RouteProvenance>();
  for (const channel of channels) {
    if (!channel.enabled || !channel.name.trim()) {
      continue;
    }
    const hermes = isHermesChannel(channel);
    for (const routeName of resolveChannelRouteModels(channel, modelProviderPrefixes)) {
      if (!routeName) continue;
      const existing = provenance.get(routeName) || {
        routeName,
        hasHermes: false,
        hasNonHermes: false,
      };
      provenance.set(routeName, {
        ...existing,
        hasHermes: existing.hasHermes || hermes,
        hasNonHermes: existing.hasNonHermes || !hermes,
      });
    }
  }
  return provenance;
}

function buildModelOptions(models: string[], selectedModel: string, autoLabel: string): Array<{ value: string; label: string }> {
  const options: Array<{ value: string; label: string }> = [{ value: '', label: autoLabel }];
  if (selectedModel && !models.includes(selectedModel)) {
    options.push({ value: selectedModel, label: koOrZh(`${selectedModel}（当前配置）`, `${selectedModel} (현재 설정)`) });
  }
  for (const model of models) {
    options.push({ value: model, label: model });
  }
  return options;
}

const LLM_STAGE_LABELS: Record<string, string> = {
  model_discovery: '模型发现',
  chat_completion: '聊天调用',
  responses: 'Responses 调用',
  response_parse: '响应解析',
  capability_json: 'JSON 能力',
  capability_tools: 'Tools 能力',
  capability_stream: 'Stream 能力',
  capability_vision: 'Vision 能力',
};

const LLM_STAGE_LABELS_KO: Record<string, string> = {
  model_discovery: '모델 조회',
  chat_completion: '채팅 호출',
  responses: 'Responses 호출',
  response_parse: '응답 해석',
  capability_json: 'JSON 기능',
  capability_tools: 'Tools 기능',
  capability_stream: 'Stream 기능',
  capability_vision: 'Vision 기능',
};

const LLM_ERROR_LABELS: Record<string, string> = {
  auth: '鉴权失败',
  timeout: '请求超时',
  quota: '额度或限流',
  model_not_found: '模型不可用',
  request_blocked: '请求被拦截',
  empty_response: '空响应',
  format_error: '格式异常',
  network_error: '网络异常',
  invalid_config: '配置无效',
  unsupported_protocol: '协议暂不支持',
  capability_unsupported: '能力不支持',
  skipped: '已跳过',
};

const LLM_ERROR_LABELS_KO: Record<string, string> = {
  auth: '인증 실패',
  timeout: '요청 시간 초과',
  quota: '한도 초과 또는 속도 제한',
  model_not_found: '모델 사용 불가',
  request_blocked: '요청 차단됨',
  empty_response: '빈 응답',
  format_error: '형식 오류',
  network_error: '네트워크 오류',
  invalid_config: '잘못된 설정',
  unsupported_protocol: '지원하지 않는 프로토콜',
  capability_unsupported: '지원하지 않는 기능',
  skipped: '건너뜀',
};

const LLM_TROUBLESHOOTING_HINTS: Record<string, string> = {
  auth: '请检查 API Key 是否正确、是否有多余空格，以及当前渠道是否需要额外组织/项目权限。',
  timeout: '可重试；若持续超时，请检查 Base URL、网络代理、服务商可用区或本地防火墙。',
  quota: '请检查余额、套餐额度、RPM/TPM 限流或并发设置，必要时稍后重试。',
  model_not_found: '请确认模型名与渠道协议匹配，并先用“获取模型”核对该渠道实际可用模型列表。',
  empty_response: '渠道已连通但未返回正文；可尝试切换兼容模型、关闭额外响应模式后再测试。',
  network_error: '请检查 Base URL、代理、TLS/证书、中转网关或本地网络策略，并可稍后重试。',
  invalid_config: '先补齐协议、Base URL、API Key 和模型配置，再执行一键测试。',
  unsupported_protocol: '当前仅对 OpenAI Compatible / DeepSeek 渠道提供自动模型发现，请改为手动维护模型列表。',
};

const LLM_TROUBLESHOOTING_HINTS_KO: Record<string, string> = {
  auth: 'API 키가 맞는지, 앞뒤에 공백이 없는지, 이 채널에 조직/프로젝트 권한이 더 필요한지 확인해 주세요.',
  timeout: '다시 시도해 보세요. 계속 시간이 초과되면 Base URL, 네트워크 프록시, 서비스 업체 리전, 로컬 방화벽을 확인해 주세요.',
  quota: '잔액, 요금제 한도, RPM/TPM 제한, 동시 요청 설정을 확인하고, 필요하면 잠시 뒤 다시 시도해 주세요.',
  model_not_found: '모델 이름이 채널 프로토콜과 맞는지 확인하고, 먼저 ‘모델 가져오기’로 이 채널에서 실제로 쓸 수 있는 모델 목록을 확인해 주세요.',
  empty_response: '채널에 연결은 됐지만 답변 내용이 없어요. 호환되는 다른 모델로 바꾸거나 추가 응답 모드를 끈 뒤 다시 테스트해 주세요.',
  network_error: 'Base URL, 프록시, TLS/인증서, 중계 게이트웨이, 로컬 네트워크 정책을 확인하고 잠시 뒤 다시 시도해 주세요.',
  invalid_config: '프로토콜, Base URL, API 키, 모델 설정을 먼저 채운 뒤 테스트해 주세요.',
  unsupported_protocol: '모델 자동 조회는 OpenAI Compatible / DeepSeek 채널만 지원해요. 모델 목록을 직접 입력해 주세요.',
};

const LLM_REASON_HINTS: Record<string, string> = {
  missing_api_key: 'API Key 为空，或逗号分隔后没有任何可用 Key；请填入至少一个有效 Key 后再测试。',
  api_key_rejected: '服务商拒绝了当前 API Key；请检查 Key、组织/项目权限、区域和账号状态。',
  rate_limit: '服务商触发 RPM/TPM 或并发限流；请降低请求频率或稍后重试。',
  insufficient_balance: '服务商返回余额、账单或额度不足；请检查账户余额和套餐状态。',
  quota_exceeded: '服务商返回配额已耗尽；请确认账号套餐、余量和项目额度。',
  provider_blocked: '请求被服务商或中转网关拦截；请检查账号风控、地域限制、模型权限、代理商网关策略、内容安全策略或请求来源限制。',
  dns_error: '域名解析失败；请检查 Base URL 域名、网络代理和 DNS 配置。',
  tls_error: 'TLS/证书握手失败；请检查 HTTPS 证书、中转网关或公司代理策略。',
  connection_refused: '目标服务拒绝连接；请确认 Base URL 端口、服务进程和防火墙配置。',
  model_access_denied: '当前账号无法使用该模型；请确认模型是否已开通、账号是否可见，或模型是否已被禁用。',
  provider_prefix_mismatch: '模型 provider 前缀与当前渠道不匹配；请确认模型名是否应使用该渠道的 OpenAI-compatible 路由。',
  capability_unsupported: '当前模型或兼容层不支持该能力；这不影响基础文本连接，可换模型或关闭该能力依赖。',
};

const LLM_REASON_HINTS_KO: Record<string, string> = {
  missing_api_key: 'API 키가 비어 있거나, 쉼표로 나눈 뒤 쓸 수 있는 키가 없어요. 올바른 키를 하나 이상 입력하고 다시 테스트해 주세요.',
  api_key_rejected: '서비스 업체가 이 API 키를 거부했어요. 키, 조직/프로젝트 권한, 리전, 계정 상태를 확인해 주세요.',
  rate_limit: '서비스 업체의 RPM/TPM 또는 동시 요청 제한에 걸렸어요. 요청 빈도를 줄이거나 잠시 뒤 다시 시도해 주세요.',
  insufficient_balance: '서비스 업체에서 잔액, 결제 또는 한도가 부족하다고 알려 왔어요. 계정 잔액과 요금제 상태를 확인해 주세요.',
  quota_exceeded: '서비스 업체의 사용 한도를 모두 썼어요. 계정 요금제, 남은 사용량, 프로젝트 한도를 확인해 주세요.',
  provider_blocked: '서비스 업체나 중계 게이트웨이가 요청을 막았어요. 계정 보안 정책, 지역 제한, 모델 권한, 중계 업체 게이트웨이 정책, 콘텐츠 안전 정책, 요청 출처 제한을 확인해 주세요.',
  dns_error: '도메인 주소를 찾지 못했어요. Base URL 도메인, 네트워크 프록시, DNS 설정을 확인해 주세요.',
  tls_error: 'TLS/인증서 연결에 실패했어요. HTTPS 인증서, 중계 게이트웨이, 회사 프록시 정책을 확인해 주세요.',
  connection_refused: '대상 서버가 연결을 거부했어요. Base URL 포트, 서비스 실행 여부, 방화벽 설정을 확인해 주세요.',
  model_access_denied: '이 계정으로는 이 모델을 쓸 수 없어요. 모델이 활성화됐는지, 계정에서 보이는지, 비활성화되지 않았는지 확인해 주세요.',
  provider_prefix_mismatch: '모델의 provider 접두어가 이 채널과 맞지 않아요. 모델 이름이 이 채널의 OpenAI-compatible route를 써야 하는지 확인해 주세요.',
  capability_unsupported: '이 모델이나 호환 계층은 이 기능을 지원하지 않아요. 기본 텍스트 연결에는 영향이 없으니 모델을 바꾸거나 이 기능을 쓰지 않도록 해 주세요.',
};

function getLlmStageLabel(stage?: string | null): string {
  return koOrZh(LLM_STAGE_LABELS[stage || ''] || '连接测试', LLM_STAGE_LABELS_KO[stage || ''] || '연결 테스트');
}

function getLlmErrorCodeLabel(code?: string | null): string {
  return koOrZh(LLM_ERROR_LABELS[code || ''] || '测试失败', LLM_ERROR_LABELS_KO[code || ''] || '테스트 실패');
}

function getLlmTroubleshootingHint(
  code?: string | null,
  stage?: string | null,
  context: 'test' | 'discovery' = 'test',
  details?: Record<string, unknown>,
): string | undefined {
  const reason = typeof details?.reason === 'string' ? details.reason : '';
  if (reason && LLM_REASON_HINTS[reason]) {
    return isKoUi() ? LLM_REASON_HINTS_KO[reason] || LLM_REASON_HINTS[reason] : LLM_REASON_HINTS[reason];
  }
  if (code === 'format_error') {
    return context === 'discovery' || stage === 'model_discovery'
      ? koOrZh('该渠道返回的 /models 响应格式不兼容，请改为手动填写模型列表。', '이 채널의 /models 응답 형식이 맞지 않아요. 모델 목록을 직접 입력해 주세요.')
      : koOrZh('返回结构与预期不一致，请确认该渠道兼容 Chat Completions 接口。', '응답 형식이 예상과 달라요. 이 채널이 Chat Completions API를 지원하는지 확인해 주세요.');
  }
  if (code === 'empty_response' && (context === 'discovery' || stage === 'model_discovery')) {
    return koOrZh('该渠道的 /models 接口未返回可用模型 ID；请检查 Base URL 是否指向兼容的模型列表接口，或改为手动填写模型列表。', '이 채널의 /models API가 쓸 수 있는 모델 ID를 돌려주지 않았어요. Base URL이 호환되는 모델 목록 API를 가리키는지 확인하거나 모델 목록을 직접 입력해 주세요.');
  }
  const hint = LLM_TROUBLESHOOTING_HINTS[code || ''];
  return hint && isKoUi() ? LLM_TROUBLESHOOTING_HINTS_KO[code || ''] || hint : hint;
}

function buildLlmTestHint(result: {
  errorCode?: string | null;
  stage?: string | null;
  details?: Record<string, unknown>;
  resolvedModel?: string | null;
}): string | undefined {
  const reason = typeof result.details?.reason === 'string' ? result.details.reason : '';
  const detailsModel = typeof result.details?.model === 'string' ? result.details.model : '';
  const testedModel = result.resolvedModel || detailsModel;
  const modelHint = testedModel ? koOrZh(`本次测试模型：${testedModel}。`, `이번에 테스트한 모델: ${testedModel}.`) : '';
  const scopeInfo = koOrZh('基础连接测试默认只测试模型列表中的第一个模型。', '기본 연결 테스트는 모델 목록의 첫 번째 모델만 확인해요.');
  const shouldSuggestModelListChange = reason === 'model_access_denied'
    || reason === 'model_not_found'
    || (result.errorCode === 'model_not_found' && !reason);
  const modelActionHint = shouldSuggestModelListChange
    ? koOrZh('若该模型不可用，请调整模型顺序或移除不可用模型后重试。', '이 모델을 쓸 수 없다면 모델 순서를 바꾸거나 쓸 수 없는 모델을 지운 뒤 다시 시도해 주세요.')
    : '';
  const troubleshootingHint = getLlmTroubleshootingHint(result.errorCode, result.stage, 'test', result.details);
  return [modelHint, scopeInfo, modelActionHint, troubleshootingHint].filter(Boolean).join(' ') || undefined;
}

function buildLlmFailureText(result: {
  message: string;
  error?: string | null;
  stage?: string | null;
  errorCode?: string | null;
}): string {
  const prefix = `${getLlmStageLabel(result.stage)} · ${getLlmErrorCodeLabel(result.errorCode)}`;
  const summary = result.message || koOrZh('测试失败', '테스트 실패');
  if (result.error && result.error !== result.message) {
    return koOrZh(`${prefix}：${summary}（原始摘要：${result.error}）`, `${prefix}: ${summary} (원본 요약: ${result.error})`);
  }
  return koOrZh(`${prefix}：${summary}`, `${prefix}: ${summary}`);
}

function getCapabilityResultVariant(status: LLMCapabilityCheckResult['status']): 'success' | 'danger' | 'warning' {
  if (status === 'passed') return 'success';
  if (status === 'skipped') return 'warning';
  return 'danger';
}

function summarizeCapabilityResults(results: Partial<Record<LLMCapabilityCheck, LLMCapabilityCheckResult>>): string {
  const values = Object.values(results);
  const passed = values.filter((result) => result?.status === 'passed').length;
  const failed = values.filter((result) => result?.status === 'failed').length;
  const skipped = values.filter((result) => result?.status === 'skipped').length;
  return koOrZh(`能力检测完成：${passed} 通过 / ${failed} 失败 / ${skipped} 跳过`, `기능 점검 완료: 통과 ${passed} / 실패 ${failed} / 건너뜀 ${skipped}`);
}

function getFirstCapabilityHint(
  results: Partial<Record<LLMCapabilityCheck, LLMCapabilityCheckResult>>,
): string | undefined {
  for (const result of Object.values(results)) {
    if (!result || result.status === 'passed') continue;
    const hint = getLlmTroubleshootingHint(result.errorCode, result.stage, 'test', result.details);
    if (hint) return hint;
  }
  return undefined;
}

const MANAGED_PROVIDERS = new Set(['gemini', 'vertex_ai', 'anthropic', 'openai', 'deepseek']);
const LEGACY_PROVIDER_KEYS: Record<string, string[]> = {
  gemini: ['GEMINI_API_KEYS', 'GEMINI_API_KEY'],
  vertex_ai: ['GEMINI_API_KEYS', 'GEMINI_API_KEY'],
  anthropic: ['ANTHROPIC_API_KEYS', 'ANTHROPIC_API_KEY'],
  openai: ['OPENAI_API_KEYS', 'AIHUBMIX_KEY', 'OPENAI_API_KEY'],
  deepseek: ['DEEPSEEK_API_KEYS', 'DEEPSEEK_API_KEY'],
};

function getRuntimeProvider(model: string): string {
  if (!model) return '';
  if (!model.includes('/')) return 'openai';
  return model.split('/', 1)[0].trim().toLowerCase();
}

function usesDirectEnvProvider(model: string): boolean {
  const provider = getRuntimeProvider(model);
  return Boolean(provider) && !MANAGED_PROVIDERS.has(provider);
}

function hasLegacyRuntimeSource(model: string, itemMap: Map<string, string>): boolean {
  const provider = PROTOCOL_ALIASES[getRuntimeProvider(model)] || getRuntimeProvider(model);
  if (!provider || !MANAGED_PROVIDERS.has(provider)) {
    return false;
  }
  return (LEGACY_PROVIDER_KEYS[provider] || []).some((key) => (itemMap.get(key) || '').trim().length > 0);
}

function isRuntimeModelAvailable(model: string, availableModels: string[], itemMap: Map<string, string>): boolean {
  const normalizedModel = model.trim();
  const matchesAvailableModel = normalizedModel.length > 0 && availableModels.includes(normalizedModel);
  return matchesAvailableModel
    || usesDirectEnvProvider(model)
    || (availableModels.length === 0 && hasLegacyRuntimeSource(model, itemMap));
}

function hasCanonicalRouteAliasMismatch(model: string, availableModels: string[]): boolean {
  const normalizedModel = model.trim();
  if (!normalizedModel || availableModels.includes(normalizedModel) || usesDirectEnvProvider(normalizedModel)) {
    return false;
  }
  for (const candidate of routeIdentityCandidates(normalizedModel)) {
    if (candidate !== normalizedModel && availableModels.includes(candidate)) {
      return true;
    }
  }
  return false;
}

function sanitizeRuntimeConfigForSave(
  runtimeConfig: RuntimeConfig,
  generationModels: string[],
  agentSafeModels: string[],
  visionSafeModels: string[],
  itemMap: Map<string, string>,
): RuntimeConfig {
  const primaryModel = runtimeConfig.primaryModel && !isRuntimeModelAvailable(runtimeConfig.primaryModel, generationModels, itemMap)
    ? ''
    : runtimeConfig.primaryModel;
  const agentPrimaryModel = runtimeConfig.agentPrimaryModel && !isRuntimeModelAvailable(runtimeConfig.agentPrimaryModel, agentSafeModels, itemMap)
    ? ''
    : runtimeConfig.agentPrimaryModel;
  const visionModel = runtimeConfig.visionModel && !isRuntimeModelAvailable(runtimeConfig.visionModel, visionSafeModels, itemMap)
    ? ''
    : runtimeConfig.visionModel;
  const fallbackModels = runtimeConfig.fallbackModels.filter((model) => isRuntimeModelAvailable(model, generationModels, itemMap));

  return {
    ...runtimeConfig,
    primaryModel,
    agentPrimaryModel,
    fallbackModels,
    visionModel,
  };
}

function runtimeConfigsAreEqual(left: RuntimeConfig, right: RuntimeConfig): boolean {
  return left.primaryModel === right.primaryModel
    && left.agentPrimaryModel === right.agentPrimaryModel
    && left.visionModel === right.visionModel
    && left.temperature === right.temperature
    && left.fallbackModels.join(',') === right.fallbackModels.join(',');
}

function runtimeConfigChangedKeys(left: RuntimeConfig, right: RuntimeConfig): Set<string> {
  const changed = new Set<string>();
  if (left.primaryModel !== right.primaryModel) {
    changed.add('LITELLM_MODEL');
  }
  if (left.agentPrimaryModel !== right.agentPrimaryModel) {
    changed.add('AGENT_LITELLM_MODEL');
  }
  if (left.fallbackModels.join(',') !== right.fallbackModels.join(',')) {
    changed.add('LITELLM_FALLBACK_MODELS');
  }
  if (left.temperature !== right.temperature) {
    changed.add('LLM_TEMPERATURE');
  }
  if (left.visionModel !== right.visionModel) {
    changed.add('VISION_MODEL');
  }
  return changed;
}

function resolveTemperatureFromItems(itemMap: Map<string, string>): string {
  const unified = itemMap.get('LLM_TEMPERATURE');
  if (unified) return unified;

  const primaryModel = itemMap.get('LITELLM_MODEL') || '';
  const provider = primaryModel.includes('/') ? primaryModel.split('/')[0] : (primaryModel ? 'openai' : '');
  const providerTemperatureEnv: Record<string, string> = {
    gemini: 'GEMINI_TEMPERATURE',
    vertex_ai: 'GEMINI_TEMPERATURE',
    anthropic: 'ANTHROPIC_TEMPERATURE',
    openai: 'OPENAI_TEMPERATURE',
    deepseek: 'OPENAI_TEMPERATURE',
  };
  const preferredEnv = providerTemperatureEnv[provider];
  if (preferredEnv) {
    const val = itemMap.get(preferredEnv);
    if (val) return val;
  }

  for (const envName of ['GEMINI_TEMPERATURE', 'ANTHROPIC_TEMPERATURE', 'OPENAI_TEMPERATURE']) {
    const val = itemMap.get(envName);
    if (val) return val;
  }

  return '0.7';
}

function normalizeAgentPrimaryModel(model: string): string {
  const trimmedModel = model.trim();
  if (!trimmedModel) {
    return '';
  }
  if (trimmedModel.includes('/')) {
    return trimmedModel;
  }
  return `openai/${trimmedModel}`;
}

function parseRuntimeConfigFromItems(items: Array<{ key: string; value: string }>): RuntimeConfig {
  const itemMap = new Map(items.map((item) => [item.key, item.value]));
  return {
    primaryModel: itemMap.get('LITELLM_MODEL') || '',
    agentPrimaryModel: normalizeAgentPrimaryModel(itemMap.get('AGENT_LITELLM_MODEL') || ''),
    fallbackModels: splitModels(itemMap.get('LITELLM_FALLBACK_MODELS') || ''),
    visionModel: itemMap.get('VISION_MODEL') || '',
    temperature: resolveTemperatureFromItems(itemMap),
  };
}

function normalizeApiSurface(value: string | undefined): string {
  const normalized = (value || '').trim().toLowerCase().replaceAll('-', '_');
  if (normalized === 'responses' || normalized === 'response' || normalized === 'responses_api') {
    return 'responses';
  }
  if (!normalized || normalized === 'chat' || normalized === 'chat_completion' || normalized === 'completions') {
    return 'chat_completions';
  }
  return normalized;
}

function parseChannelsFromItems(
  items: Array<{ key: string; value: string }>,
  itemSourceByKey: Map<string, boolean> = new Map(),
): ChannelConfig[] {
  const itemMap = new Map(items.map((item) => [item.key.toUpperCase(), item.value]));
  const implicitModelflare = splitModels(itemMap.get('MODELFLARE_KEY') || '').length > 0
    || splitModels(itemMap.get('LLM_MODELFLARE_API_KEY') || '').length > 0
    || splitModels(itemMap.get('LLM_MODELFLARE_API_KEYS') || '').length > 0;
  const channelNames = ((itemMap.get('LLM_CHANNELS') || '').trim()
    || (implicitModelflare ? 'modelflare' : ''))
    .split(',')
    .map((segment) => segment.trim())
    .filter(Boolean);

  return channelNames.map((name, index) => {
    const upperName = name.toUpperCase();
    const baseUrl = itemMap.get(`LLM_${upperName}_BASE_URL`) || '';
    const primaryModel = (itemMap.get('LITELLM_MODEL') || '').trim()
      || `openai/${MODELFLARE_DEFAULT_MODEL}`;
    const inheritedModels = channelNames.length === 1 && upperName === 'MODELFLARE'
      && primaryModel.startsWith('openai/') && primaryModel.slice(7).trim()
      ? [...new Set([primaryModel, ...splitModels(itemMap.get('LITELLM_FALLBACK_MODELS') || '')]
        .filter((model) => model.startsWith('openai/') && model.slice(7).trim()))]
      : [];
    const rawModels = (itemMap.get(`LLM_${upperName}_MODELS`) || '').trim() || inheritedModels.join(',');
    const models = splitModels(rawModels);

    return {
      id: `parsed:${index}:${upperName}`,
      name: name.toLowerCase(),
      protocol: inferProtocol(itemMap.get(`LLM_${upperName}_PROTOCOL`) || '', baseUrl, models),
      apiSurface: normalizeApiSurface(itemMap.get(`LLM_${upperName}_API_SURFACE`)),
      baseUrl,
      apiKey: resolveInitialChannelApiKeyValue(name, itemMap, itemSourceByKey),
      models: rawModels,
      enabled: parseEnabled(itemMap.get(`LLM_${upperName}_ENABLED`)),
    };
  });
}

function channelsToUpdateItems(
  channels: ChannelConfig[],
  previousChannelNames: string[],
  runtimeConfig: RuntimeConfig,
  includeRuntimeConfig: boolean,
): Array<{ key: string; value: string }> {
  const updates: Array<{ key: string; value: string }> = [];
  const activeNames = channels.map((channel) => channel.name.toUpperCase());

  updates.push({ key: 'LLM_CHANNELS', value: channels.map((channel) => channel.name).join(',') });
  if (includeRuntimeConfig) {
    updates.push({ key: 'LITELLM_MODEL', value: runtimeConfig.primaryModel });
    updates.push({ key: 'AGENT_LITELLM_MODEL', value: runtimeConfig.agentPrimaryModel });
    updates.push({ key: 'LITELLM_FALLBACK_MODELS', value: runtimeConfig.fallbackModels.join(',') });
    updates.push({ key: 'VISION_MODEL', value: runtimeConfig.visionModel });
    updates.push({ key: 'LLM_TEMPERATURE', value: runtimeConfig.temperature });
  }

  for (const channel of channels) {
    const prefix = `LLM_${channel.name.toUpperCase()}`;
    const isMultiKey = channel.apiKey.includes(',');
    updates.push({ key: `${prefix}_PROTOCOL`, value: channel.protocol });
    updates.push({ key: `${prefix}_API_SURFACE`, value: channel.apiSurface });
    updates.push({ key: `${prefix}_BASE_URL`, value: channel.baseUrl });
    updates.push({ key: `${prefix}_ENABLED`, value: channel.enabled ? 'true' : 'false' });
    if (isHermesChannel(channel)) {
      updates.push({ key: `${prefix}_API_KEY`, value: channel.apiKey });
      updates.push({ key: `${prefix}_API_KEYS`, value: '' });
      updates.push({ key: `${prefix}_EXTRA_HEADERS`, value: '' });
    } else {
      updates.push({ key: `${prefix}_API_KEY${isMultiKey ? 'S' : ''}`, value: channel.apiKey });
      updates.push({ key: `${prefix}_API_KEY${isMultiKey ? '' : 'S'}`, value: '' });
    }
    updates.push({ key: `${prefix}_MODELS`, value: channel.models });
  }

  for (const oldName of previousChannelNames) {
    const upperName = oldName.toUpperCase();
    if (activeNames.includes(upperName)) {
      continue;
    }

    const prefix = `LLM_${upperName}`;
    updates.push({ key: `${prefix}_PROTOCOL`, value: '' });
    updates.push({ key: `${prefix}_API_SURFACE`, value: '' });
    updates.push({ key: `${prefix}_BASE_URL`, value: '' });
    updates.push({ key: `${prefix}_ENABLED`, value: '' });
    updates.push({ key: `${prefix}_API_KEY`, value: '' });
    updates.push({ key: `${prefix}_API_KEYS`, value: '' });
    updates.push({ key: `${prefix}_MODELS`, value: '' });
    updates.push({ key: `${prefix}_EXTRA_HEADERS`, value: '' });
  }

  return updates;
}

function channelNamesAreSafe(channels: ChannelConfig[]): boolean {
  return channels.every((channel) => /^[a-z0-9_]+$/.test(channel.name.trim()));
}

function buildFilteredChannelUpdateItems({
  channels,
  initialChannels,
  initialNames,
  initialItemSourceByKey,
  savedItemMap,
  runtimeConfig,
  initialRuntimeConfig,
  managesRuntimeConfig,
}: {
  channels: ChannelConfig[];
  initialChannels: ChannelConfig[];
  initialNames: string[];
  initialItemSourceByKey: Map<string, boolean>;
  savedItemMap: Map<string, string>;
  runtimeConfig: RuntimeConfig;
  initialRuntimeConfig: RuntimeConfig;
  managesRuntimeConfig: boolean;
}): Array<{ key: string; value: string }> {
  const changedKeys = new Set<string>([
    ...buildChangedItemKeys(channels, initialChannels, initialItemSourceByKey, savedItemMap),
    ...runtimeConfigChangedKeys(runtimeConfig, initialRuntimeConfig),
  ]);
  const usesSimpleModelflare = Boolean(savedItemMap.get('MODELFLARE_KEY'))
    && !(savedItemMap.get('LLM_CHANNELS') || '').trim()
    && !(savedItemMap.get('LLM_MODELFLARE_API_KEY') || '').trim()
    && !(savedItemMap.get('LLM_MODELFLARE_API_KEYS') || '').trim();
  const updates = channelsToUpdateItems(channels, initialNames, runtimeConfig, managesRuntimeConfig).filter((item) => {
    const itemKey = item.key.toUpperCase();
    if (usesSimpleModelflare && !changedKeys.has(itemKey)) return false;
    const initialItemSource = initialItemSourceByKey.get(itemKey);
    if (initialItemSource === false) {
      return changedKeys.has(itemKey);
    }
    if (isChannelSecretFieldKey(itemKey) && initialItemSource === undefined) {
      return changedKeys.has(itemKey);
    }
    return true;
  });
  if (usesSimpleModelflare) {
    const current = channels.find((channel) => channel.name.toLowerCase() === 'modelflare');
    const previous = initialChannels.find((channel) => channel.name.toLowerCase() === 'modelflare');
    if (current?.apiKey !== previous?.apiKey) {
      updates.push({ key: 'MODELFLARE_KEY', value: current?.apiKey || '' });
    }
    return updates.filter((item) => item.key !== 'LLM_MODELFLARE_API_KEY' && item.key !== 'LLM_MODELFLARE_API_KEYS');
  }
  return updates;
}

function buildChannelDraftItems({
  hasChanges,
  channels,
  initialChannels,
  initialNames,
  initialItemSourceByKey,
  savedItemMap,
  runtimeConfig,
  initialRuntimeConfig,
  managesRuntimeConfig,
}: {
  hasChanges: boolean;
  channels: ChannelConfig[];
  initialChannels: ChannelConfig[];
  initialNames: string[];
  initialItemSourceByKey: Map<string, boolean>;
  savedItemMap: Map<string, string>;
  runtimeConfig: RuntimeConfig;
  initialRuntimeConfig: RuntimeConfig;
  managesRuntimeConfig: boolean;
}): Array<{ key: string; value: string }> {
  if (!hasChanges || !channelNamesAreSafe(channels)) {
    return [];
  }
  return buildFilteredChannelUpdateItems({
    channels,
    initialChannels,
    initialNames,
    initialItemSourceByKey,
    savedItemMap,
    runtimeConfig,
    initialRuntimeConfig,
    managesRuntimeConfig,
  });
}

function channelsAreEqual(left: ChannelConfig, right: ChannelConfig): boolean {
  return (
    left.name === right.name
    && left.protocol === right.protocol
    && left.apiSurface === right.apiSurface
    && left.baseUrl === right.baseUrl
    && left.apiKey === right.apiKey
    && left.models === right.models
    && left.enabled === right.enabled
  );
}

export const LLMChannelEditor: React.FC<LLMChannelEditorProps> = ({
  items,
  configVersion,
  maskToken,
  modelProviderPrefixes = [],
  onSaved,
  onDraftItemsChange,
  onDirtyChange,
  onSavingChange,
  draftResetToken = 0,
  disabled = false,
}) => {
  const initialItemSourceByKey = useMemo(() => {
    const sourceByKey = new Map<string, boolean>();
    for (const item of items) {
      sourceByKey.set(item.key.toUpperCase(), item.rawValueExists !== false);
    }
    for (const [key, hasSource] of sourceByKey) {
      if (hasSource) {
        continue;
      }
      const match = CHANNEL_FIELD_KEY_PATTERN.exec(key);
      if (!match) {
        continue;
      }
      const channelName = match[1];
      for (const channelKey of parseChannelFieldKeysFromName(channelName)) {
        if (!sourceByKey.has(channelKey)) {
          sourceByKey.set(channelKey, false);
        }
      }
    }
    return sourceByKey;
  }, [items]);
  const initialChannels = useMemo(
    () => parseChannelsFromItems(items, initialItemSourceByKey),
    [items, initialItemSourceByKey],
  );
  const initialNames = useMemo(() => initialChannels.map((channel) => channel.name), [initialChannels]);
  const initialRuntimeConfig = useMemo(() => parseRuntimeConfigFromItems(items), [items]);
  const savedItemMap = useMemo(() => new Map(items.map((item) => [item.key.toUpperCase(), item.value])), [items]);
  const hasPersistedHermesSecret = (channel: ChannelConfig): boolean => (
    isHermesChannel(channel) && initialItemSourceByKey.get('LLM_HERMES_API_KEY') === true
  );
  const hasLitellmConfig = useMemo(
    () => items.some((item) => item.key === 'LITELLM_CONFIG' && item.value.trim().length > 0),
    [items],
  );
  const managesRuntimeConfig = !hasLitellmConfig;
  const modelProviderPrefixSet = useMemo(
    () => new Set(modelProviderPrefixes.map((provider) => provider.trim().toLowerCase()).filter(Boolean)),
    [modelProviderPrefixes],
  );

  const channelsFingerprint = useMemo(() => JSON.stringify(initialChannels), [initialChannels]);
  const runtimeFingerprint = useMemo(() => JSON.stringify(initialRuntimeConfig), [initialRuntimeConfig]);

  const [channels, setChannels] = useState<ChannelConfig[]>(initialChannels);
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfig>(initialRuntimeConfig);
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<
    | { type: 'success'; text: string }
    | { type: 'error'; error: ParsedApiError }
    | { type: 'local-error'; text: string }
    | null
  >(null);
  const [saveWarnings, setSaveWarnings] = useState<string[]>([]);
  const [visibleKeys, setVisibleKeys] = useState<Record<number, boolean>>({});
  const [testStates, setTestStates] = useState<Record<number, ChannelTestState>>({});
  const [discoveryStates, setDiscoveryStates] = useState<Record<string, ChannelDiscoveryState>>({});
  const [capabilityStates, setCapabilityStates] = useState<Record<string, ChannelCapabilityState>>({});
  const [expandedRows, setExpandedRows] = useState<Record<number, boolean>>({});
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [addPreset, setAddPreset] = useState(LLM_PROVIDER_TEMPLATES[0].channelId);
  const addChannelIdRef = useRef(0);
  const lastDraftFingerprintRef = useRef<string | null>(null);
  const onDraftItemsChangeRef = useRef(onDraftItemsChange);

  const prevDraftResetTokenRef = useRef(draftResetToken);
  const prevChannelsRef = useRef(channelsFingerprint);
  const prevRuntimeRef = useRef(runtimeFingerprint);
  const pendingSaveFeedbackFingerprintRef = useRef<{ channels: string; runtime: string } | null>(null);
  const discoveryNonceRef = useRef<Record<string, number>>({});
  const discoveryRequestIdRef = useRef(0);
  const capabilityNonceRef = useRef<Record<string, number>>({});
  const capabilityRequestIdRef = useRef(0);

  useEffect(() => {
    if (prevChannelsRef.current === channelsFingerprint && prevRuntimeRef.current === runtimeFingerprint
      && prevDraftResetTokenRef.current === draftResetToken) {
      return;
    }
    prevDraftResetTokenRef.current = draftResetToken;
    prevChannelsRef.current = channelsFingerprint;
    prevRuntimeRef.current = runtimeFingerprint;
    const pendingSaveFeedbackFingerprint = pendingSaveFeedbackFingerprintRef.current;
    const preserveSaveFeedback = pendingSaveFeedbackFingerprint?.channels === channelsFingerprint
      && pendingSaveFeedbackFingerprint.runtime === runtimeFingerprint;
    pendingSaveFeedbackFingerprintRef.current = null;
    setChannels(initialChannels);
    setRuntimeConfig(initialRuntimeConfig);
    setVisibleKeys({});
    setTestStates({});
    setDiscoveryStates({});
    setCapabilityStates({});
    setExpandedRows({});
    discoveryNonceRef.current = {};
    capabilityNonceRef.current = {};
    if (!preserveSaveFeedback) {
      setSaveMessage(null);
      setSaveWarnings([]);
    }
    setIsCollapsed(false);
  }, [channelsFingerprint, runtimeFingerprint, initialChannels, initialRuntimeConfig, draftResetToken]);

  const routeProvenanceMap = useMemo(() => {
    if (!managesRuntimeConfig) {
      return new Map<string, RouteProvenance>();
    }
    return buildRouteProvenanceMap(channels, modelProviderPrefixSet);
  }, [channels, managesRuntimeConfig, modelProviderPrefixSet]);

  const availableModels = useMemo(
    () => Array.from(routeProvenanceMap.values())
      .filter((origin) => !(origin.hasHermes && origin.hasNonHermes))
      .map((origin) => origin.routeName),
    [routeProvenanceMap],
  );

  const agentSafeModels = useMemo(
    () => Array.from(routeProvenanceMap.values())
      .filter((origin) => !origin.hasHermes || origin.hasNonHermes)
      .map((origin) => origin.routeName),
    [routeProvenanceMap],
  );

  const visionSafeModels = useMemo(
    () => Array.from(routeProvenanceMap.values())
      .filter((origin) => !origin.hasHermes)
      .map((origin) => origin.routeName),
    [routeProvenanceMap],
  );

  const agentSelectedModelForOptions = useMemo(() => {
    if (!runtimeConfig.agentPrimaryModel || agentSafeModels.includes(runtimeConfig.agentPrimaryModel)) {
      return runtimeConfig.agentPrimaryModel;
    }
    const origin = getRouteProvenance(routeProvenanceMap, runtimeConfig.agentPrimaryModel);
    return origin?.hasHermes && !origin.hasNonHermes ? '' : runtimeConfig.agentPrimaryModel;
  }, [agentSafeModels, routeProvenanceMap, runtimeConfig.agentPrimaryModel]);

  const visionSelectedModelForOptions = useMemo(() => {
    if (!runtimeConfig.visionModel || visionSafeModels.includes(runtimeConfig.visionModel)) {
      return runtimeConfig.visionModel;
    }
    const origin = getRouteProvenance(routeProvenanceMap, runtimeConfig.visionModel);
    return origin?.hasHermes ? '' : runtimeConfig.visionModel;
  }, [routeProvenanceMap, runtimeConfig.visionModel, visionSafeModels]);

  const hasChanges = useMemo(() => {
    const runtimeChanged = (
      runtimeConfig.primaryModel !== initialRuntimeConfig.primaryModel
      || runtimeConfig.agentPrimaryModel !== initialRuntimeConfig.agentPrimaryModel
      || runtimeConfig.visionModel !== initialRuntimeConfig.visionModel
      || runtimeConfig.temperature !== initialRuntimeConfig.temperature
      || runtimeConfig.fallbackModels.join(',') !== initialRuntimeConfig.fallbackModels.join(',')
    );

    if (runtimeChanged || channels.length !== initialChannels.length) {
      return true;
    }
    return channels.some((channel, index) => !channelsAreEqual(channel, initialChannels[index]));
  }, [channels, initialChannels, initialRuntimeConfig, runtimeConfig]);

  useEffect(() => {
    onDirtyChange?.(hasChanges);
    return () => onDirtyChange?.(false);
  }, [hasChanges, onDirtyChange]);

  useEffect(() => {
    onSavingChange?.(isSaving);
    return () => onSavingChange?.(false);
  }, [isSaving, onSavingChange]);

  const draftItems = useMemo(() => buildChannelDraftItems({
    hasChanges,
    channels,
    initialChannels,
    initialNames,
    initialItemSourceByKey,
    savedItemMap,
    runtimeConfig,
    initialRuntimeConfig,
    managesRuntimeConfig,
  }), [
    channels,
    hasChanges,
    initialChannels,
    initialItemSourceByKey,
    initialNames,
    initialRuntimeConfig,
    managesRuntimeConfig,
    runtimeConfig,
    savedItemMap,
  ]);
  const draftFingerprint = useMemo(() => JSON.stringify(draftItems), [draftItems]);

  useEffect(() => {
    onDraftItemsChangeRef.current = onDraftItemsChange;
  }, [onDraftItemsChange]);

  useEffect(() => {
    if (!onDraftItemsChange || lastDraftFingerprintRef.current === draftFingerprint) {
      return;
    }
    lastDraftFingerprintRef.current = draftFingerprint;
    onDraftItemsChange(draftItems);
  }, [draftFingerprint, draftItems, onDraftItemsChange]);

  useEffect(() => () => {
    onDraftItemsChangeRef.current?.([]);
  }, []);

  const busy = disabled || isSaving;

  const updateChannel = (index: number, field: keyof ChannelConfig, value: string | boolean) => {
    const currentChannel = channels[index];
    setChannels((previous) => previous.map((channel, rowIndex) => {
      if (rowIndex !== index) return channel;
      const updated = { ...channel, [field]: value };

      if (field === 'name' && typeof value === 'string') {
        const newPreset = getProviderTemplate(value);
        if (newPreset) {
          const oldPreset = getProviderTemplate(channel.name);
          if (!updated.baseUrl || updated.baseUrl === (oldPreset?.baseUrl ?? '')) {
            updated.baseUrl = newPreset.baseUrl;
          }
          updated.protocol = newPreset.protocol;
          updated.apiSurface = 'chat_completions';
          if (!updated.models || updated.models === (oldPreset?.placeholderModels ?? '')) {
            updated.models = newPreset.placeholderModels;
          }
        }
      }

      return updated;
    }));
    setTestStates((previous) => {
      if (!(index in previous)) {
        return previous;
      }
      const next = { ...previous };
      delete next[index];
      return next;
    });
    if (field !== 'models' && field !== 'enabled') {
      setDiscoveryStates((previous) => {
        const channel = channels.find((_, itemIndex) => itemIndex === index);
        if (!channel || !(channel.id in previous)) {
          return previous;
        }
        const next = { ...previous };
        delete next[channel.id];
        delete discoveryNonceRef.current[channel.id];
        return next;
      });
    }
    if (currentChannel) {
      delete capabilityNonceRef.current[currentChannel.id];
      setCapabilityStates((previous) => {
        const current = previous[currentChannel.id];
        if (!current) {
          return previous;
        }
        return {
          ...previous,
          [currentChannel.id]: {
            ...current,
            status: 'idle',
            text: undefined,
            hint: undefined,
            results: {},
          },
        };
      });
    }
  };

  const removeChannel = (index: number) => {
    const removedChannelId = channels[index]?.id || '';
    setChannels((previous) => previous.filter((_, rowIndex) => rowIndex !== index));
    setVisibleKeys({});
    setTestStates({});
    setDiscoveryStates((previous) => {
      if (!removedChannelId) {
        return previous;
      }
      const next = { ...previous };
      delete next[removedChannelId];
      return next;
    });
    setCapabilityStates((previous) => {
      if (!removedChannelId || !(removedChannelId in previous)) {
        return previous;
      }
      const next = { ...previous };
      delete next[removedChannelId];
      return next;
    });
    if (removedChannelId) {
      const nextNonce = { ...discoveryNonceRef.current };
      delete nextNonce[removedChannelId];
      discoveryNonceRef.current = nextNonce;
      delete capabilityNonceRef.current[removedChannelId];
    }
    setExpandedRows({});
  };

  const addChannel = () => {
    const preset = getProviderTemplate(addPreset) || getProviderTemplate('custom');
    if (!preset) {
      return;
    }
    setChannels((previous) => {
      const existingNames = new Set(previous.map((channel) => channel.name));
      const baseName = addPreset === 'custom' ? 'custom' : addPreset;
      let nextName = baseName;
      let counter = 2;
      while (existingNames.has(nextName)) {
        nextName = `${baseName}${counter}`;
        counter += 1;
      }

      return [
        ...previous,
        {
          id: `added:${addChannelIdRef.current += 1}`,
          name: nextName,
          protocol: preset.protocol,
          apiSurface: 'chat_completions',
          baseUrl: preset.baseUrl,
          apiKey: '',
          models: preset.placeholderModels || '',
          enabled: true,
        },
      ];
    });
    setTestStates({});
    setDiscoveryStates({});
    setCapabilityStates({});
    discoveryNonceRef.current = {};
    capabilityNonceRef.current = {};
    setExpandedRows((prev) => ({ ...prev, [channels.length]: true }));
    setIsCollapsed(false);
  };

  const handleSave = async () => {
    const hasEmptyName = channels.some((channel) => !channel.name.trim());
    if (hasEmptyName) {
      setSaveMessage({ type: 'local-error', text: koOrZh('渠道名称不能为空，且只能包含字母、数字或下划线。', '채널 이름을 입력해 주세요. 영문, 숫자, 밑줄(_)만 쓸 수 있어요.') });
      return;
    }

    if (managesRuntimeConfig) {
      const mixedPrimary = runtimeConfig.primaryModel
        && getRouteProvenance(routeProvenanceMap, runtimeConfig.primaryModel)?.hasHermes
        && getRouteProvenance(routeProvenanceMap, runtimeConfig.primaryModel)?.hasNonHermes;
      const mixedFallback = runtimeConfig.fallbackModels.find((model) => {
        const origin = getRouteProvenance(routeProvenanceMap, model);
        return origin?.hasHermes && origin.hasNonHermes;
      });
      if (mixedPrimary || mixedFallback) {
        setSaveMessage({ type: 'local-error', text: koOrZh('Mixed Hermes/non-Hermes route 暂不支持作为主生成或备选模型，请选择纯 Hermes 或纯非 Hermes route。', 'Hermes와 비 Hermes가 섞인 route는 기본 모델이나 보조 모델로 쓸 수 없어요. Hermes만 쓰는 route나 Hermes가 없는 route를 골라 주세요.') });
        return;
      }

      const nonCanonicalRouteAlias = (
        hasCanonicalRouteAliasMismatch(runtimeConfig.primaryModel, availableModels)
        || hasCanonicalRouteAliasMismatch(runtimeConfig.agentPrimaryModel, agentSafeModels)
        || hasCanonicalRouteAliasMismatch(runtimeConfig.visionModel, visionSafeModels)
        || runtimeConfig.fallbackModels.some((model) => hasCanonicalRouteAliasMismatch(model, availableModels))
      );
      if (nonCanonicalRouteAlias) {
        setSaveMessage({ type: 'local-error', text: koOrZh('当前运行时模型使用非规范 route alias，请从下拉框重新选择规范模型。', '지금 설정된 모델이 비표준 route 별칭을 쓰고 있어요. 목록에서 표준 모델을 다시 골라 주세요.') });
        return;
      }
    }

    const runtimeConfigForSave = managesRuntimeConfig
      ? sanitizeRuntimeConfigForSave(runtimeConfig, availableModels, agentSafeModels, visionSafeModels, savedItemMap)
      : runtimeConfig;
    if (!runtimeConfigsAreEqual(runtimeConfigForSave, runtimeConfig)) {
      setRuntimeConfig(runtimeConfigForSave);
    }

    if (managesRuntimeConfig) {
      const invalidPrimaryModel = runtimeConfigForSave.primaryModel
        && !isRuntimeModelAvailable(runtimeConfigForSave.primaryModel, availableModels, savedItemMap);
      if (invalidPrimaryModel) {
        setSaveMessage({ type: 'local-error', text: koOrZh('当前主模型不在已启用渠道的模型列表中，请重新选择。', '기본 모델이 사용 중인 채널의 모델 목록에 없어요. 다시 골라 주세요.') });
        return;
      }

      const invalidAgentPrimaryModel = runtimeConfigForSave.agentPrimaryModel
        && !isRuntimeModelAvailable(runtimeConfigForSave.agentPrimaryModel, agentSafeModels, savedItemMap);
      if (invalidAgentPrimaryModel) {
        setSaveMessage({ type: 'local-error', text: koOrZh('当前 Agent 主模型没有 Agent-safe 非 Hermes deployment，请重新选择。', 'Agent 기본 모델에 Agent에서 쓸 수 있는 비 Hermes deployment가 없어요. 다시 골라 주세요.') });
        return;
      }

      const invalidFallbackModel = runtimeConfigForSave.fallbackModels.some(
        (model) => !isRuntimeModelAvailable(model, availableModels, savedItemMap),
      );
      if (invalidFallbackModel) {
        setSaveMessage({ type: 'local-error', text: koOrZh('存在无效的备选模型，请重新选择。', '잘못된 보조 모델이 있어요. 다시 골라 주세요.') });
        return;
      }

      const invalidVisionModel = runtimeConfigForSave.visionModel
        && !isRuntimeModelAvailable(runtimeConfigForSave.visionModel, visionSafeModels, savedItemMap);
      if (invalidVisionModel) {
        setSaveMessage({ type: 'local-error', text: koOrZh('当前 Vision 模型不能包含 Hermes deployment，请重新选择纯非 Hermes route。', 'Vision 모델에는 Hermes deployment를 넣을 수 없어요. Hermes가 없는 route를 다시 골라 주세요.') });
        return;
      }
    }

    setIsSaving(true);
    setSaveMessage(null);
    setSaveWarnings([]);

    try {
      const updateItems = buildFilteredChannelUpdateItems({
        channels,
        initialChannels,
        initialNames,
        initialItemSourceByKey,
        savedItemMap,
        runtimeConfig: runtimeConfigForSave,
        initialRuntimeConfig,
        managesRuntimeConfig,
      });
      const response = await systemConfigApi.update({
        configVersion,
        maskToken,
        reloadNow: true,
        items: updateItems,
      });
      const responseWarnings = response.warnings || [];
      await onSaved(updateItems);
      pendingSaveFeedbackFingerprintRef.current = {
        channels: JSON.stringify(parseChannelsFromItems(updateItems)),
        runtime: JSON.stringify(parseRuntimeConfigFromItems(updateItems)),
      };
      setSaveWarnings(responseWarnings);
      setSaveMessage({ type: 'success', text: managesRuntimeConfig ? koOrZh('AI 配置已保存', 'AI 설정을 저장했어요') : koOrZh('渠道配置已保存', '채널 설정을 저장했어요') });
    } catch (error: unknown) {
      setSaveWarnings([]);
      setSaveMessage({ type: 'error', error: getParsedApiError(error) });
    } finally {
      setIsSaving(false);
    }
  };

  const handleTest = async (channel: ChannelConfig, index: number) => {
    if (hasRuntimeOnlyMaskedHermesSecret(channel, maskToken, hasPersistedHermesSecret(channel))) {
      setTestStates((previous) => ({
        ...previous,
        [index]: { status: 'error', text: koOrZh(RUNTIME_ONLY_HERMES_SECRET_MESSAGE, RUNTIME_ONLY_HERMES_SECRET_MESSAGE_KO) },
      }));
      return;
    }

    setTestStates((previous) => ({
      ...previous,
      [index]: { status: 'loading', text: koOrZh('测试中...', '테스트 중...') },
    }));

    try {
      const result = await systemConfigApi.testLLMChannel({
        name: channel.name,
        protocol: channel.protocol,
        apiSurface: channel.apiSurface as LLMApiSurface,
        baseUrl: channel.baseUrl,
        apiKey: channel.apiKey,
        models: splitModels(channel.models),
        enabled: channel.enabled,
        useSavedSecret: shouldUseSavedHermesSecret(channel, maskToken, hasPersistedHermesSecret(channel)),
      });

      const text = result.success
        ? koOrZh(`连接成功${result.resolvedModel ? ` · ${result.resolvedModel}` : ''}${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`, `연결 성공${result.resolvedModel ? ` · ${result.resolvedModel}` : ''}${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`)
        : buildLlmFailureText(result);
      const hint = result.success ? undefined : buildLlmTestHint(result);

      setTestStates((previous) => ({
        ...previous,
        [index]: {
          status: result.success ? 'success' : 'error',
          text,
          hint,
        },
      }));
    } catch (error: unknown) {
      const parsed = getParsedApiError(error);
      setTestStates((previous) => ({
        ...previous,
        [index]: { status: 'error', text: parsed.message || koOrZh('测试失败', '테스트 실패') },
      }));
    }
  };

  const handleDiscoverModels = async (channel: ChannelConfig) => {
    if (hasRuntimeOnlyMaskedHermesSecret(channel, maskToken, hasPersistedHermesSecret(channel))) {
      setDiscoveryStates((previous) => ({
        ...previous,
        [channel.id]: {
          status: 'error',
          text: koOrZh(RUNTIME_ONLY_HERMES_SECRET_MESSAGE, RUNTIME_ONLY_HERMES_SECRET_MESSAGE_KO),
          hint: undefined,
          models: previous[channel.id]?.models || [],
        },
      }));
      return;
    }

    const requestId = discoveryRequestIdRef.current + 1;
    discoveryRequestIdRef.current = requestId;
    discoveryNonceRef.current[channel.id] = requestId;
    const nonce = requestId;

    setDiscoveryStates((previous) => ({
      ...previous,
      [channel.id]: {
        status: 'loading',
        text: koOrZh('正在获取模型列表...', '모델 목록을 가져오는 중...'),
        hint: undefined,
        models: previous[channel.id]?.models || [],
      },
    }));

    try {
      const result = await systemConfigApi.discoverLLMChannelModels({
        name: channel.name,
        protocol: channel.protocol,
        baseUrl: channel.baseUrl,
        apiKey: channel.apiKey,
        models: splitModels(channel.models),
        useSavedSecret: shouldUseSavedHermesSecret(channel, maskToken, hasPersistedHermesSecret(channel)),
      });

      if (discoveryNonceRef.current[channel.id] !== nonce) return;

      setDiscoveryStates((previous) => ({
        ...previous,
        [channel.id]: {
          status: result.success ? 'success' : 'error',
          text: result.success
            ? koOrZh(`已获取 ${result.models.length} 个模型${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`, `모델 ${result.models.length}개를 가져왔어요${result.latencyMs ? ` · ${result.latencyMs} ms` : ''}`)
            : buildLlmFailureText(result),
          hint: result.success ? undefined : getLlmTroubleshootingHint(result.errorCode, result.stage, 'discovery', result.details),
          models: result.success ? result.models : (previous[channel.id]?.models || []),
        },
      }));
    } catch (error: unknown) {
      if (discoveryNonceRef.current[channel.id] !== nonce) return;

      const parsed = getParsedApiError(error);
      setDiscoveryStates((previous) => ({
        ...previous,
        [channel.id]: {
          status: 'error',
          text: parsed.message || koOrZh('获取模型失败', '모델을 가져오지 못했어요'),
          hint: undefined,
          models: previous[channel.id]?.models || [],
        },
      }));
    }
  };

  const toggleCapability = (channel: ChannelConfig, capability: LLMCapabilityCheck) => {
    setCapabilityStates((previous) => {
      const current = previous[channel.id] || { selected: [], status: 'idle', results: {} };
      const selected = current.selected.includes(capability)
        ? current.selected.filter((item) => item !== capability)
        : [...current.selected, capability];
      return {
        ...previous,
        [channel.id]: {
          ...current,
          selected,
          status: current.status === 'loading' ? current.status : 'idle',
          text: current.status === 'loading' ? current.text : undefined,
          hint: current.status === 'loading' ? current.hint : undefined,
          results: current.status === 'loading' ? current.results : {},
        },
      };
    });
  };

  const handleCapabilityCheck = async (channel: ChannelConfig) => {
    const selected = (capabilityStates[channel.id]?.selected || []).filter(
      (capability) => !isHermesChannel(channel) || capability === 'json',
    );
    if (selected.length === 0) return;

    if (hasRuntimeOnlyMaskedHermesSecret(channel, maskToken, hasPersistedHermesSecret(channel))) {
      setCapabilityStates((previous) => ({
        ...previous,
        [channel.id]: {
          selected,
          status: 'error',
          text: koOrZh(RUNTIME_ONLY_HERMES_SECRET_MESSAGE, RUNTIME_ONLY_HERMES_SECRET_MESSAGE_KO),
          hint: undefined,
          results: {},
        },
      }));
      return;
    }

    const requestId = capabilityRequestIdRef.current + 1;
    capabilityRequestIdRef.current = requestId;
    capabilityNonceRef.current[channel.id] = requestId;
    const nonce = requestId;

    setCapabilityStates((previous) => ({
      ...previous,
      [channel.id]: {
        selected,
        status: 'loading',
        text: koOrZh('正在检测运行时能力...', '기능을 점검하는 중...'),
        hint: undefined,
        results: {},
      },
    }));

    try {
      const result = await systemConfigApi.testLLMChannel({
        name: channel.name,
        protocol: channel.protocol,
        apiSurface: channel.apiSurface as LLMApiSurface,
        baseUrl: channel.baseUrl,
        apiKey: channel.apiKey,
        models: splitModels(channel.models),
        enabled: channel.enabled,
        capabilityChecks: selected,
        useSavedSecret: shouldUseSavedHermesSecret(channel, maskToken, hasPersistedHermesSecret(channel)),
      });

      if (capabilityNonceRef.current[channel.id] !== nonce) return;

      const capabilityResults = result.capabilityResults || {};
      const hasFailure = Object.values(capabilityResults).some((item) => item?.status === 'failed');
      const hasSkipped = Object.values(capabilityResults).some((item) => item?.status === 'skipped');
      setCapabilityStates((previous) => ({
        ...previous,
        [channel.id]: {
          selected,
          status: hasFailure || hasSkipped || !result.success ? 'error' : 'success',
          text: Object.keys(capabilityResults).length > 0
            ? summarizeCapabilityResults(capabilityResults)
            : result.success
              ? koOrZh('未返回能力检测结果', '기능 점검 결과가 없어요')
              : buildLlmFailureText(result),
          hint: getFirstCapabilityHint(capabilityResults)
            || (!result.success ? buildLlmTestHint(result) : undefined),
          results: capabilityResults,
        },
      }));
    } catch (error: unknown) {
      if (capabilityNonceRef.current[channel.id] !== nonce) return;

      const parsed = getParsedApiError(error);
      setCapabilityStates((previous) => ({
        ...previous,
        [channel.id]: {
          selected,
          status: 'error',
          text: parsed.message || koOrZh('能力检测失败', '기능 점검 실패'),
          hint: undefined,
          results: {},
        },
      }));
    }
  };

  const toggleKeyVisibility = (index: number, nextVisible: boolean) => {
    setVisibleKeys((previous) => ({ ...previous, [index]: nextVisible }));
  };

  const toggleExpand = (index: number) => {
    setExpandedRows((previous) => ({ ...previous, [index]: !previous[index] }));
  };

  const setPrimaryModel = (value: string) => {
    setRuntimeConfig((previous) => ({
      ...previous,
      primaryModel: value,
      fallbackModels: previous.fallbackModels.filter((model) => model !== value),
    }));
  };

  const toggleFallbackModel = (model: string) => {
    setRuntimeConfig((previous) => {
      const alreadySelected = previous.fallbackModels.includes(model);
      return {
        ...previous,
        fallbackModels: alreadySelected
          ? previous.fallbackModels.filter((item) => item !== model)
          : [...previous.fallbackModels, model],
      };
    });
  };

  return (
    <div className="space-y-4">
      <button
        type="button"
        className="flex w-full items-center justify-between rounded-[1.35rem] border border-[var(--settings-border)] bg-[var(--settings-surface)] px-5 py-4 text-left shadow-soft-card transition-[background-color,border-color,box-shadow] duration-200 hover:border-[var(--settings-border-strong)] hover:bg-[var(--settings-surface-hover)]"
        onClick={() => setIsCollapsed((previous) => !previous)}
      >
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-foreground">{koOrZh('AI 模型配置', 'AI 모델 설정')}</h3>
            <Badge variant="info" className="settings-accent-badge">{koOrZh('渠道管理', '채널 관리')}</Badge>
          </div>
          <p className="text-xs text-muted-text">
            {koOrZh('添加服务商渠道后可自动获取模型列表并多选，也可继续手动填写。配置会自动同步到 .env 文件。', '서비스 업체 채널을 추가하면 모델 목록을 자동으로 가져와 여러 개 고를 수 있어요. 직접 입력해도 돼요. 설정은 .env 파일에 자동으로 저장돼요.')}
          </p>
        </div>
        <span className="text-xs text-muted-text">{isCollapsed ? koOrZh('▶ 展开', '▶ 펼치기') : koOrZh('▼ 收起', '▼ 접기')}</span>
      </button>

      {!isCollapsed ? (
        <div className="space-y-4 animate-in fade-in slide-in-from-top-2 duration-300">
          <div className="rounded-[1.35rem] border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4 shadow-soft-card">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h4 className="text-sm font-medium text-foreground">{koOrZh('快速添加渠道', '채널 빠르게 추가')}</h4>
                <p className="mt-1 text-xs text-secondary-text">{koOrZh('先选择预设服务商，再一键创建配置草稿。', '서비스 업체를 고르면 설정 초안을 바로 만들 수 있어요.')}</p>
              </div>
              <Badge variant="default" className="border-[var(--settings-border)] bg-[var(--settings-surface-hover)] text-muted-text">{koOrZh(`${channels.length} 个渠道`, `채널 ${channels.length}개`)}</Badge>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Button type="button" variant="settings-primary" className="whitespace-nowrap" disabled={busy} onClick={addChannel}>
                {koOrZh('+ 添加渠道', '+ 채널 추가')}
              </Button>
              <div className="flex w-full min-w-0 items-center gap-2 sm:w-auto sm:flex-1">
                <Select
                  value={addPreset}
                  onChange={setAddPreset}
                  options={LLM_PROVIDER_TEMPLATES.map((preset) => ({
                    value: preset.channelId,
                    label: (isKoUi() && LLM_PROVIDER_TEMPLATE_TEXT_KO[preset.channelId]?.label) || preset.label,
                  }))}
                  disabled={busy}
                  placeholder={koOrZh('选择服务商', '서비스 업체 선택')}
                  className="min-w-0 flex-1"
                />
                {addPreset === 'modelflare' ? (
                  <a
                    href={MODELFLARE_APP_REGISTRATION_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="settings-button-secondary inline-flex h-11 shrink-0 items-center justify-center whitespace-nowrap rounded-xl border px-3 text-sm font-medium transition-all duration-200 hover:translate-y-[-1px] focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-cyan/15"
                  >
                    {koOrZh('注册 Modelflare', 'Modelflare 가입하기')}
                  </a>
                ) : null}
              </div>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between px-1">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-text">{koOrZh('渠道列表', '채널 목록')}</span>
              {channels.length > 0 ? (
                <span className="text-[10px] text-muted-text">{channels.filter((c) => c.enabled).length}/{channels.length}{koOrZh(' 已启用', ' 사용 중')}</span>
              ) : null}
            </div>

            {channels.length === 0 ? (
              <div className="settings-surface-overlay-muted rounded-[1.35rem] border border-dashed settings-border-strong px-4 py-10 text-center">
                <p className="text-sm font-medium text-secondary-text">{koOrZh('还没有渠道', '아직 채널이 없어요')}</p>
                <p className="mt-1 text-xs text-muted-text">{koOrZh('选择服务商预设后点击“添加渠道”即可开始配置。', '서비스 업체를 고르고 ‘채널 추가’를 누르면 설정을 시작할 수 있어요.')}</p>
              </div>
            ) : channels.map((channel, index) => (
              <ChannelRow
                key={channel.id}
                channel={channel}
                index={index}
                busy={busy}
                visibleKey={Boolean(visibleKeys[index])}
                expanded={Boolean(expandedRows[index])}
                testState={testStates[index]}
                discoveryState={discoveryStates[channel.id]}
                capabilityState={capabilityStates[channel.id]}
                modelProviderPrefixes={modelProviderPrefixSet}
                onUpdate={updateChannel}
                onRemove={removeChannel}
                onToggleExpand={toggleExpand}
                onToggleKeyVisibility={toggleKeyVisibility}
                onTest={(ch, idx) => void handleTest(ch, idx)}
                onDiscoverModels={(channel) => void handleDiscoverModels(channel)}
                onToggleCapability={toggleCapability}
                onCheckCapabilities={(channel) => void handleCapabilityCheck(channel)}
              />
            ))}
          </div>

          {managesRuntimeConfig ? (
            <div className="rounded-[1.35rem] border border-[var(--settings-border)] bg-[var(--settings-surface)] p-4 shadow-soft-card">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <span className="settings-accent-text text-xs font-medium uppercase tracking-wider">{koOrZh('运行时参数', '실행 설정')}</span>
                  <p className="mt-1 text-[11px] text-muted-text">{koOrZh('主模型、备选模型、Vision 与 Temperature 会直接写入运行时配置。', '기본 모델, 보조 모델, Vision, Temperature는 실행 설정에 바로 반영돼요.')}</p>
                </div>
                <Badge variant="default" className="border-[var(--settings-border)] bg-[var(--settings-surface-hover)] text-muted-text">Runtime</Badge>
              </div>
              <div className="mb-4">
                <HelpLabel
                  label="Temperature"
                  fieldKey="LLM_TEMPERATURE"
                  helpKey="settings.llm_channel.temperature"
                  examples={['LLM_TEMPERATURE=0.2', 'LLM_TEMPERATURE=0.7']}
                  compact
                />
                <div className="flex items-center gap-3">
                  <input
                    type="range"
                    min="0"
                    max="2"
                    step="0.1"
                    value={runtimeConfig.temperature}
                    disabled={busy}
                    onChange={(event) => setRuntimeConfig((previous) => ({ ...previous, temperature: event.target.value }))}
                    className="settings-input-checkbox h-1.5 flex-1 cursor-pointer rounded-full bg-border/60"
                  />
                  <span className="w-8 text-right text-sm text-secondary-text">{runtimeConfig.temperature}</span>
                </div>
                <p className="mt-1 text-[11px] text-secondary-text">
                  {koOrZh('控制模型输出随机性，0 为确定性输出，2 为最大随机性，推荐 0.7。', '모델 답변이 얼마나 다양하게 나올지 정해요. 0이면 늘 같은 답, 2면 가장 다양한 답이에요. 0.7을 추천해요.')}
                </p>
              </div>

              {availableModels.length === 0 ? (
                <div className="rounded-xl border border-dashed settings-border-strong settings-surface-overlay-soft px-3 py-2 text-xs text-muted-text">
                  {koOrZh('先添加至少一个已启用渠道并填写模型，下面的主模型 / 备选模型 / Vision 选项才会出现。', '사용할 채널을 하나 이상 추가하고 모델을 입력하면 아래에 기본 모델 / 보조 모델 / Vision 선택이 나타나요.')}
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <HelpLabel
                      htmlFor="runtime-primary-model"
                      label={koOrZh('主模型', '기본 모델')}
                      fieldKey="LITELLM_MODEL"
                      helpKey="settings.llm_channel.primary_model"
                      examples={['LITELLM_MODEL=deepseek/deepseek-v4-flash']}
                      compact
                    />
                    <Select
                      id="runtime-primary-model"
                      value={runtimeConfig.primaryModel}
                      onChange={setPrimaryModel}
                      options={buildModelOptions(availableModels, runtimeConfig.primaryModel, koOrZh('自动（使用第一个可用模型）', '자동 (쓸 수 있는 첫 번째 모델)'))}
                      disabled={busy}
                      placeholder=""
                    />
                  </div>

                  <div>
                    <HelpLabel
                      htmlFor="runtime-agent-primary-model"
                      label={koOrZh('Agent 主模型', 'Agent 기본 모델')}
                      fieldKey="AGENT_LITELLM_MODEL"
                      helpKey="settings.llm_channel.agent_primary_model"
                      examples={['AGENT_LITELLM_MODEL=deepseek/deepseek-v4-pro']}
                      compact
                    />
                    <Select
                      id="runtime-agent-primary-model"
                      value={runtimeConfig.agentPrimaryModel}
                      onChange={(value) => setRuntimeConfig((previous) => ({
                        ...previous,
                        agentPrimaryModel: normalizeAgentPrimaryModel(value),
                      }))}
                      options={buildModelOptions(
                        agentSafeModels,
                        agentSelectedModelForOptions,
                        koOrZh('自动（继承普通分析主模型）', '자동 (일반 분석의 기본 모델을 따라요)'),
                      )}
                      disabled={busy}
                      placeholder=""
                    />
                  </div>

                  <div>
                    <HelpLabel
                      label={koOrZh('备选模型', '보조 모델')}
                      fieldKey="LITELLM_FALLBACK_MODELS"
                      helpKey="settings.llm_channel.fallback_models"
                      examples={['LITELLM_FALLBACK_MODELS=deepseek/deepseek-v4-pro,gemini/gemini-3-flash-preview']}
                      compact
                    />
                    <div className="space-y-2 rounded-xl border settings-border-strong settings-surface-overlay-soft p-3">
                      {availableModels.map((model) => (
                        <label key={model} className="flex items-center gap-2 text-sm text-secondary-text">
                          <input
                            type="checkbox"
                            checked={runtimeConfig.fallbackModels.includes(model)}
                            disabled={busy || model === runtimeConfig.primaryModel}
                            onChange={() => toggleFallbackModel(model)}
                            className="settings-input-checkbox h-4 w-4 rounded border-border/70 bg-base"
                          />
                          <span>{model}</span>
                        </label>
                      ))}
                    </div>
                    <p className="mt-1 text-[11px] text-secondary-text">
                      {koOrZh('备选模型只会在主模型失败时使用。主模型不会重复加入备选模型。', '보조 모델은 기본 모델이 실패할 때만 써요. 기본 모델은 보조 모델에 중복으로 들어가지 않아요.')}
                    </p>
                  </div>

                  <div>
                    <HelpLabel
                      htmlFor="runtime-vision-model"
                      label={koOrZh('Vision 模型', 'Vision 모델')}
                      fieldKey="VISION_MODEL"
                      helpKey="settings.llm_channel.vision_model"
                      examples={['VISION_MODEL=gemini/gemini-3.1-pro-preview']}
                      compact
                    />
                    <Select
                      id="runtime-vision-model"
                      value={runtimeConfig.visionModel}
                      onChange={(value) => setRuntimeConfig((previous) => ({ ...previous, visionModel: value }))}
                      options={buildModelOptions(
                        visionSafeModels,
                        visionSelectedModelForOptions,
                        koOrZh('自动（跟随 Vision 默认逻辑）', '자동 (Vision 기본 설정을 따라요)'),
                      )}
                      disabled={busy}
                      placeholder=""
                    />
                  </div>
                </div>
              )}
            </div>
          ) : (
            <InlineAlert
              variant="warning"
              message={koOrZh('检测到已配置高级模型路由 YAML：此处仅管理渠道条目和基础连接信息。运行时主模型 / 备选模型 / Vision / Temperature 仍由下方通用字段决定；若 YAML 解析成功，则以其中的路由与可用模型声明为准，本配置不会覆盖 YAML 文件本身。', '고급 모델 라우팅 YAML이 설정되어 있어요. 여기서는 채널 항목과 기본 연결 정보만 관리해요. 기본 모델 / 보조 모델 / Vision / Temperature는 아래 공통 항목에서 정해요. YAML을 제대로 읽으면 그 안의 route와 사용 가능한 모델 설정이 우선하고, 이 화면의 설정은 YAML 파일 자체를 덮어쓰지 않아요.')}
              className="rounded-[1.35rem] px-4 py-3 text-xs shadow-none"
            />
          )}

          <div className="flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="settings-primary"
              glow
              disabled={busy || !hasChanges}
              onClick={() => void handleSave()}
            >
              {isSaving ? koOrZh('保存中...', '저장 중...') : managesRuntimeConfig ? koOrZh('保存 AI 配置', 'AI 설정 저장') : koOrZh('保存渠道配置', '채널 설정 저장')}
            </Button>
            {!hasChanges ? <span className="text-xs text-muted-text">{koOrZh('当前没有未保存的改动', '저장하지 않은 변경 사항이 없어요')}</span> : null}
          </div>

          {saveMessage?.type === 'success' ? (
            <InlineAlert
              variant="success"
              message={saveMessage.text}
              className="rounded-lg px-3 py-2 text-sm shadow-none"
            />
          ) : null}

          {saveWarnings.length > 0 ? (
            <InlineAlert
              variant="warning"
              title={koOrZh('保存后提示', '저장 후 안내')}
              message={(
                <div className="space-y-1">
                  {saveWarnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              )}
              className="rounded-lg px-3 py-2 text-sm shadow-none"
            />
          ) : null}

          {saveMessage?.type === 'local-error' ? (
            <InlineAlert
              variant="danger"
              message={saveMessage.text}
              className="rounded-lg px-3 py-2 text-sm shadow-none"
            />
          ) : null}

          {saveMessage?.type === 'error' ? <ApiErrorAlert error={saveMessage.error} /> : null}
        </div>
      ) : null}
    </div>
  );
};

import { DEFAULT_UI_LANGUAGE, type UiLanguage } from '../i18n/uiText';

export const UI_LANGUAGE_STORAGE_KEY = 'dsa.uiLanguage';

export function normalizeUiLanguage(value?: string | null): UiLanguage | null {
  if (value === 'zh' || value === 'en' || value === 'ko') {
    return value;
  }
  return null;
}

function getStoredUiLanguage(storage?: Storage | null): UiLanguage | null {
  if (!storage) {
    return null;
  }

  try {
    return normalizeUiLanguage(storage.getItem(UI_LANGUAGE_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function getUiLanguageStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function persistUiLanguage(storage: Storage | null, language: UiLanguage): void {
  if (!storage) {
    return;
  }

  try {
    storage.setItem(UI_LANGUAGE_STORAGE_KEY, language);
  } catch {
    // Ignore storage failures; in-memory language still updates.
  }
}

function getBrowserUiLanguage(
  navigatorLike?: Pick<Navigator, 'language' | 'languages'> | null,
  fallback: UiLanguage = 'zh',
): UiLanguage {
  const languageCandidates = [
    ...(Array.isArray(navigatorLike?.languages) ? navigatorLike?.languages ?? [] : []),
    navigatorLike?.language,
  ].filter((language): language is string => Boolean(language));

  for (const candidate of languageCandidates) {
    const normalized = candidate.toLowerCase();
    if (normalized.startsWith('zh')) {
      return 'zh';
    }
    if (normalized.startsWith('en')) {
      return 'en';
    }
    if (normalized.startsWith('ko')) {
      return 'ko';
    }
  }

  return fallback;
}

export function resolveInitialUiLanguage({
  storage,
  navigatorLike,
  fallback = 'zh',
}: {
  storage?: Storage | null;
  navigatorLike?: Pick<Navigator, 'language' | 'languages'> | null;
  /** 저장된 선택도, 지원하는 브라우저 언어도 없을 때 쓰는 언어 (업스트림 기본값 zh) */
  fallback?: UiLanguage;
} = {}): UiLanguage {
  const stored = getStoredUiLanguage(storage);
  if (stored) {
    return stored;
  }

  return getBrowserUiLanguage(navigatorLike, fallback);
}

export function getRuntimeInitialLanguage(): UiLanguage {
  if (typeof window === 'undefined') {
    return DEFAULT_UI_LANGUAGE;
  }

  // 한국어 포크: 저장된 선택 → 브라우저 언어(zh/en/ko) → 한국어 순으로 정한다.
  return resolveInitialUiLanguage({
    storage: getUiLanguageStorage(),
    navigatorLike: window.navigator,
    fallback: DEFAULT_UI_LANGUAGE,
  });
}

/**
 * React 밖(스토어, API 오류 처리 등)에서 쓰는 문구 선택기.
 * 현재 UI 언어가 한국어일 때만 한국어를 돌려주고, 그 밖에는 기존 중국어 문구를 그대로 쓴다.
 */
export function koOrZh(zh: string, ko: string): string {
  // 브라우저 정보가 없는 환경(서버 렌더링·window를 갈아끼운 단위 테스트)에서는 화면이 없으므로 기존 문구를 유지한다.
  if (typeof window === 'undefined' || !window.navigator) {
    return zh;
  }
  return getRuntimeInitialLanguage() === 'ko' ? ko : zh;
}

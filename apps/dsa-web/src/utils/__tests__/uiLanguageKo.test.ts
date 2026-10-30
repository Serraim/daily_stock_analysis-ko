import { describe, expect, it } from 'vitest';
import { DEFAULT_UI_LANGUAGE, UI_TEXT } from '../../i18n/uiText';
import { getSettingsHelpContent } from '../../locales/settingsHelp';
import { normalizeUiLanguage, resolveInitialUiLanguage, UI_LANGUAGE_STORAGE_KEY } from '../uiLanguage';

function storageWith(value: string | null): Storage {
  const store = new Map<string, string>();
  if (value !== null) store.set(UI_LANGUAGE_STORAGE_KEY, value);
  return {
    get length() { return store.size; },
    clear: () => store.clear(),
    getItem: (key: string) => store.get(key) ?? null,
    key: (index: number) => Array.from(store.keys())[index] ?? null,
    removeItem: (key: string) => { store.delete(key); },
    setItem: (key: string, next: string) => { store.set(key, next); },
  };
}

describe('Korean UI language (fork default)', () => {
  it('uses Korean as the fork default language', () => {
    expect(DEFAULT_UI_LANGUAGE).toBe('ko');
  });

  it('accepts ko as a stored choice and from the browser language', () => {
    expect(normalizeUiLanguage('ko')).toBe('ko');
    expect(resolveInitialUiLanguage({ storage: storageWith('ko'), navigatorLike: { language: 'en-US', languages: ['en-US'] } })).toBe('ko');
    expect(resolveInitialUiLanguage({ storage: storageWith(null), navigatorLike: { language: 'ko-KR', languages: ['ko-KR'] } })).toBe('ko');
  });

  it('falls back to the given default when no supported language is found', () => {
    expect(resolveInitialUiLanguage({
      storage: storageWith(null),
      navigatorLike: { language: 'tr-TR', languages: ['tr-TR'] },
      fallback: DEFAULT_UI_LANGUAGE,
    })).toBe('ko');
  });

  it('has a non-empty Korean value for every UI text key', () => {
    const missing = Object.entries(UI_TEXT.ko).filter(([, value]) => !value.trim()).map(([key]) => key);
    expect(missing).toEqual([]);
    expect(UI_TEXT.ko['layout.nav.home']).toBe('홈');
    expect(UI_TEXT.ko['language.short.ko']).toBe('한');
  });

  it('serves Korean settings help and falls back to English instead of Chinese', () => {
    expect(getSettingsHelpContent('settings.base.STOCK_LIST', undefined, 'ko')?.title).toBe(
      getSettingsHelpContent('settings.base.STOCK_LIST', undefined, 'ko-KR')?.title,
    );
    expect(getSettingsHelpContent('settings.base.STOCK_LIST', undefined, 'ko')?.title).not.toBe(
      getSettingsHelpContent('settings.base.STOCK_LIST', undefined, 'zh')?.title,
    );
    expect(getSettingsHelpContent('unknown.key', '설명', 'ko')?.title).toBe('설정 도움말');
  });
});

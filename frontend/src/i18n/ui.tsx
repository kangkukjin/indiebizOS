import { createElement, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';
import { createUI } from '../../i18n/runtime.mjs';
import catalog from '../../i18n/catalog.json';

export const ui = createUI(catalog);
export function useLocale() {
  return useSyncExternalStore(ui.subscribe, ui.getLocale, () => 'ko');
}
/** Explicit registration for UI metadata outside JSX. Replaced with a stable id by the UI compiler. */
export function uiMessage(_context: string, source: string): string { return source; }
export function UiText({ id, values = [] }: { id: string; values?: unknown[] }) {
  useLocale();
  return ui.text(id, values);
}
export function UiElement({ as, uiAttrs, children, ...props }: {
  as: string; uiAttrs: Record<string, string>; children?: ReactNode; [key: string]: unknown;
}) {
  useLocale();
  const translated = Object.fromEntries(Object.entries(uiAttrs).map(([name, id]) => [name, ui.text(id)]));
  return createElement(as, { ...props, ...translated }, children);
}
export function LanguagePicker() {
  const locale = useLocale();
  return <select aria-label="Language / 언어" value={locale} onChange={event => ui.setLocale(event.target.value)}
    className="text-xs rounded-md border border-[#D5CCC0] bg-white px-2 py-1 text-[#4A4035] max-w-28">
    {Object.entries(ui.languages).map(([value, label]) => <option key={value} value={value}>{String(label)}</option>)}
  </select>;
}

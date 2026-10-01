import { createElement, useSyncExternalStore } from 'react';
import type { ReactNode, ElementType } from 'react';
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
export function UiChoice({ value, choices }: { value: string; choices: Record<string, string> }) {
  useLocale();
  return Object.hasOwn(choices, value) ? ui.text(choices[value]) : value;
}
export function UiSystemText({ value, fragments = false }: { value?: string; fragments?: boolean }) {
  useLocale();
  return ui.system(value ?? '', fragments);
}
export function UiElement({ as, uiAttrs, children, ...props }: {
  as: ElementType; uiAttrs: Record<string, string | {id: string; values: unknown[]} | {value: string; choices: Record<string,string>} | {resolve: () => unknown}>; children?: ReactNode; [key: string]: unknown;
}) {
  useLocale();
  const translated = Object.fromEntries(Object.entries(uiAttrs).map(([name, id]) => [name, typeof id === 'string' ? ui.text(id) : 'resolve' in id ? id.resolve() : 'id' in id ? ui.text(id.id, id.values) : Object.hasOwn(id.choices, id.value) ? ui.text(id.choices[id.value]) : id.value]));
  return createElement(as, { ...props, ...translated }, children);
}
export function LanguagePicker() {
  const locale = useLocale();
  return <select aria-label="Language / 언어" value={locale} onChange={event => ui.setLocale(event.target.value)}
    className="text-xs rounded-md border border-[#D5CCC0] bg-white px-2 py-1 text-[#4A4035] max-w-28">
    {Object.entries(ui.languages).map(([value, label]) => <option key={value} value={value}>{String(label)}</option>)}
  </select>;
}

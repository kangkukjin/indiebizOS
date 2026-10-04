import { createElement, useSyncExternalStore } from 'react';
import type { ReactNode, ElementType } from 'react';
import { Languages, ChevronDown } from 'lucide-react';
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
  return <div className="relative flex items-center text-[#6B5B4F]">
    <Languages size={15} aria-hidden="true" className="pointer-events-none absolute left-2.5" />
    <select aria-label="Language / 언어" value={locale} onChange={event => ui.setLocale(event.target.value)}
      className="appearance-none cursor-pointer rounded-lg border-0 bg-transparent pl-[31px] pr-7 py-1.5 text-[13px] leading-[19.5px] font-medium text-[#6B5B4F] transition-colors hover:bg-[#EAE4DA] active:bg-[#E0D9CC] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#A08060] focus-visible:ring-offset-1">
      {Object.entries(ui.languages).map(([value, label]) => <option key={value} value={value}>{String(label)}</option>)}
    </select>
    <ChevronDown size={12} aria-hidden="true" className="pointer-events-none absolute right-2.5" />
  </div>;
}

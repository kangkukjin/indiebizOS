/** Only our X-Ray page may receive the host UI locale; never inject into external browsing. */
export function isXrayURL(value: string, backendOrigin: string): boolean {
  try {
    const url = new URL(value);
    return url.origin === backendOrigin && url.pathname === '/xray/app';
  } catch { return false; }
}
export function xrayLocaleURL(value: string, backendOrigin: string, locale: string): string {
  if (!isXrayURL(value, backendOrigin)) return value;
  const url = new URL(value);
  url.searchParams.set('ui_locale', locale);
  return url.href;
}
export function xrayLocaleScript(backendOrigin: string, locale: string): string {
  return `if(location.origin===${JSON.stringify(backendOrigin)} && location.pathname==='/xray/app')window.__ui?.setLocale(${JSON.stringify(locale)});`;
}

import { LanguageService } from './language.service';
import { es } from './translations/es';
import { en } from './translations/en';

const DICTS: Record<string, any> = { es, en };

function lookup(dict: any, path: string[]): string | undefined {
  let cur = dict;
  for (const p of path) {
    if (cur == null) return undefined;
    cur = cur[p];
  }
  return typeof cur === 'string' ? cur : undefined;
}

/** Traduce una clave punteada (ej. 'common.save') al idioma activo, con
 * fallback a español y luego a la clave misma si no existe. Soporta
 * interpolación simple con {{variable}}. */
export function t(key: string, vars?: Record<string, string | number>): string {
  const path = key.split('.');
  let str = lookup(DICTS[LanguageService.current], path) ?? lookup(DICTS.es, path) ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      str = str.replace(new RegExp(`{{${k}}}`, 'g'), String(v));
    }
  }
  return str;
}

/** Suscribe un LitElement a los cambios de idioma para que se re-renderice.
 * Llamar en connectedCallback y ejecutar el retorno en disconnectedCallback. */
export function subscribeI18n(el: { requestUpdate: () => void }): () => void {
  const handler = () => el.requestUpdate();
  window.addEventListener('lang-change', handler);
  return () => window.removeEventListener('lang-change', handler);
}

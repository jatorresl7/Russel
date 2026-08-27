export type Lang = 'es' | 'en';

const STORAGE_KEY = 'lang';
const DEFAULT_LANG: Lang = 'es';

/** Idioma activo de la UI — mismo patrón singleton+evento que AuthService
 * ('auth-change'): cualquier componente puede escuchar 'lang-change' en
 * window para reaccionar sin acoplarse a este servicio. */
export class LanguageService {
  private static _lang: Lang = ((): Lang => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored === 'en' || stored === 'es' ? stored : DEFAULT_LANG;
  })();

  static get current(): Lang {
    return this._lang;
  }

  static set(lang: Lang) {
    if (lang === this._lang) return;
    this._lang = lang;
    localStorage.setItem(STORAGE_KEY, lang);
    window.dispatchEvent(new CustomEvent('lang-change'));
  }

  static toggle() {
    this.set(this._lang === 'es' ? 'en' : 'es');
  }
}

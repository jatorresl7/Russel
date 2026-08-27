import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { Router } from '@vaadin/router';
import { t, subscribeI18n } from './i18n/t';
import { LanguageService } from './i18n/language.service';

const NAV_ICONS: Record<string, TemplateResult> = {
  russ: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z"/>
  </svg>`,
  consola: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9-9h12a2.25 2.25 0 012.25 2.25v9a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15.75v-9A2.25 2.25 0 015.25 4.5z"/>
  </svg>`,
  gmail: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75"/>
  </svg>`,
  scripts: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M14.25 9.75L16.5 12l-2.25 2.25m-4.5 0L7.5 12l2.25-2.25M6 20.25h12A2.25 2.25 0 0020.25 18V6A2.25 2.25 0 0018 3.75H6A2.25 2.25 0 003.75 6v12A2.25 2.25 0 006 20.25z"/>
  </svg>`,
  tools: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M11.42 15.17L17.25 21A2.652 2.652 0 0021 17.25l-5.877-5.877M11.42 15.17l2.496-3.03c.317-.384.74-.626 1.208-.766M11.42 15.17l-4.655 5.653a2.548 2.548 0 11-3.586-3.586l6.837-5.63m5.108-.233c.55-.164 1.163-.188 1.743-.14a4.5 4.5 0 004.486-6.336l-3.276 3.277a3.004 3.004 0 01-2.25-2.25l3.276-3.276a4.5 4.5 0 00-6.336 4.486c.091 1.076-.071 2.264-.904 2.95l-.102.085m-1.745 1.437L5.909 7.5H4.5L2.25 3.75l1.5-1.5L7.5 4.5v1.409l4.26 4.26m-1.745 1.437l1.745-1.437"/>
  </svg>`,
  vision: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M6.827 6.175A2.31 2.31 0 015.186 7.23c-.38.054-.757.112-1.134.175C2.999 7.58 2.25 8.507 2.25 9.574V18a2.25 2.25 0 002.25 2.25h15A2.25 2.25 0 0021.75 18V9.574c0-1.067-.75-1.994-1.802-2.169a47.865 47.865 0 00-1.134-.175 2.31 2.31 0 01-1.64-1.055l-.822-1.316a2.192 2.192 0 00-1.736-1.039 48.774 48.774 0 00-5.232 0 2.192 2.192 0 00-1.736 1.039l-.821 1.316z"/>
    <path stroke-linecap="round" stroke-linejoin="round" d="M16.5 12.75a4.5 4.5 0 11-9 0 4.5 4.5 0 019 0z"/>
  </svg>`,
  robot: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v3m-4.5 0h9A2.25 2.25 0 0118.75 8.25v7.5A2.25 2.25 0 0116.5 18h-9a2.25 2.25 0 01-2.25-2.25v-7.5A2.25 2.25 0 017.5 6zM9.75 11.25h.008v.008H9.75v-.008zm4.5 0h.008v.008h-.008v-.008zM9 14.25h6M3.75 10.5v3m16.5-3v3M9 21h6"/>
  </svg>`,
  caras: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M15.182 15.182a4.5 4.5 0 01-6.364 0M9 9.75h.008v.008H9V9.75zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zm5.625 0h.008v.008H15V9.75zm.375 0a.375.375 0 11-.75 0 .375.375 0 01.75 0zM21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
  </svg>`,
  conocimiento: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"/>
  </svg>`,
  grafo: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <circle cx="6" cy="6" r="2.6"/><circle cx="18" cy="6" r="2.6"/><circle cx="12" cy="18" r="2.6"/>
    <path stroke-linecap="round" d="M8.6 6h6.8M7.3 8.3l3.4 7.4M16.7 8.3l-3.4 7.4"/>
  </svg>`,
  sistema: html`<svg class="w-5 h-5 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
    <path stroke-linecap="round" stroke-linejoin="round" d="M9 17.25v1.007a3 3 0 01-.879 2.122L7.5 21h9l-.621-.621A3 3 0 0115 18.257V17.25m6-12V15a2.25 2.25 0 01-2.25 2.25H5.25A2.25 2.25 0 013 15V5.25A2.25 2.25 0 015.25 3h13.5A2.25 2.25 0 0121 5.25z"/>
  </svg>`,
};

// Un ítem por vista. `group` decide en qué bloque del menú cae; el orden de
// `buildNavGroups` es el orden en que se pintan.
function buildNavItems() {
  return [
    { path: '/russ',    label: t('nav.russ'),    iconKey: 'russ',    group: 'asistente' },
    { path: '/consola', label: t('nav.consola'), iconKey: 'consola', group: 'asistente' },
    { path: '/conocimiento', label: t('nav.conocimiento'), iconKey: 'conocimiento', group: 'asistente' },
    { path: '/grafo',   label: t('nav.grafo'),   iconKey: 'grafo',   group: 'asistente' },
    { path: '/gmail',   label: t('nav.gmail'),   iconKey: 'gmail',   group: 'trabajo' },
    // Desactivadas a pedido: son las que ejecutan comandos en el PC.
    // { path: '/scripts', label: t('nav.scripts'), iconKey: 'scripts', group: 'trabajo' },
    // { path: '/tools',   label: t('nav.tools'),   iconKey: 'tools',   group: 'trabajo' },
    { path: '/vision',  label: t('nav.vision'),  iconKey: 'vision',  group: 'robot' },
    { path: '/robot',   label: t('nav.robot'),   iconKey: 'robot',   group: 'robot' },
    { path: '/caras',   label: t('nav.caras'),   iconKey: 'caras',   group: 'robot' },
    { path: '/sistema', label: t('nav.sistema'), iconKey: 'sistema', group: 'sistema' },
  ];
}

// Grupos del menú en orden. Solo se muestran los que tienen algún ítem.
function buildNavGroups() {
  const order = [
    { key: 'asistente', label: t('nav.group_asistente') },
    { key: 'trabajo',   label: t('nav.group_trabajo') },
    { key: 'robot',     label: t('nav.group_robot') },
    { key: 'sistema',   label: t('nav.group_sistema') },
  ];
  const items = buildNavItems();
  return order
    .map(g => ({ ...g, items: items.filter(i => i.group === g.key) }))
    .filter(g => g.items.length);
}

@customElement('app-root')
export class AppRoot extends LitElement {
  private router!: Router;

  @state() private collapsed = false;
  // Con cinco vistas el menú entero cabe en pantalla, así que los grupos
  // arrancan ABIERTOS (en el aeropuerto son once y arrancan cerrados). Se
  // respeta lo que se haya dejado en la sesión.
  @state() private _navClosed: Record<string, boolean> = JSON.parse(
    sessionStorage.getItem('nav-groups-closed') ?? '{}');

  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  disconnectedCallback() {
    this._unsubI18n();
    super.disconnectedCallback();
  }

  firstUpdated() {
    const outlet = this.querySelector('#outlet');
    if (!outlet) return;
    this.router = new Router(outlet);
    this.router.setRoutes([
      { path: '/',         redirect: '/russ' },
      { path: '/russ',     component: 'russ-page' },
      { path: '/consola',  component: 'consola-page' },
      { path: '/gmail',    component: 'gmail-page' },
      { path: '/conocimiento', component: 'conocimiento-page' },
      { path: '/grafo',    component: 'grafo-page' },
      // { path: '/scripts',  component: 'scripts-page' },
      // { path: '/tools',    component: 'tools-page' },
      { path: '/vision',   component: 'vision-page' },
      { path: '/robot',    component: 'robot-page' },
      { path: '/caras',    component: 'caras-page' },
      { path: '/sistema',  component: 'sistema-page' },
    ]);
  }

  private _toggleLang(e: Event) {
    e.stopPropagation();
    LanguageService.toggle();
  }

  private _toggleNavGroup(key: string) {
    this._navClosed = { ...this._navClosed, [key]: !this._navClosed[key] };
    sessionStorage.setItem('nav-groups-closed', JSON.stringify(this._navClosed));
  }

  render(): TemplateResult {
    const w = this.collapsed ? 'w-14' : 'w-[220px]';

    return html`
      <header class="fixed top-0 left-0 right-0 z-40 flex items-center h-14 px-4
                     bg-gradient-to-r from-[var(--color-primary-hover)] to-[var(--color-primary)]">

        <button @click="${() => { this.collapsed = !this.collapsed; }}"
          class="flex items-center justify-center w-8 h-8 rounded-[var(--radius-control)] flex-shrink-0
                 bg-white/10 hover:bg-white/20 border-0 text-white transition-colors mr-3">
          <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5M3.75 17.25h16.5"/>
          </svg>
        </button>

        <span class="text-base font-bold text-white mr-auto tracking-wide">
          ${t('nav.app_title')}
        </span>

        <button @click="${(e: Event) => this._toggleLang(e)}"
          title="${LanguageService.current === 'es' ? 'Switch to English' : 'Cambiar a español'}"
          class="flex items-center justify-center h-9 px-2.5 rounded-[var(--radius-control)] text-xs font-bold
                 text-white/70 hover:text-white hover:bg-white/10
                 transition-colors border-0 bg-transparent">
          ${LanguageService.current === 'es' ? 'EN' : 'ES'}
        </button>
      </header>

      <div class="flex flex-1 pt-14 h-screen min-w-0">
        <nav class="flex flex-col flex-shrink-0 overflow-hidden transition-[width] duration-200
                    bg-[var(--sidebar-bg)] border-r border-[var(--sidebar-border)] ${w}">
          <ul class="list-none p-0 py-2.5 flex-1">
            ${buildNavGroups().map((grupo, gi) => {
              const cerrado = !this.collapsed && !!this._navClosed[grupo.key];
              return html`
                ${this.collapsed
                  ? (gi > 0 ? html`<li class="mx-3 my-1.5 border-t border-[var(--sidebar-border)]"></li>` : '')
                  : html`<li>
                      <button @click="${() => this._toggleNavGroup(grupo.key)}"
                        class="w-full flex items-center gap-1.5 px-3.5 ${gi > 0 ? 'pt-3.5' : 'pt-1'} pb-1 bg-transparent border-0
                               cursor-pointer text-[11px] font-semibold uppercase tracking-wider select-none
                               text-[var(--sidebar-text)] hover:text-[var(--sidebar-text-hover)] transition-colors">
                        <svg class="w-3 h-3 flex-shrink-0 transition-transform ${cerrado ? '-rotate-90' : ''}"
                             viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M6 9l6 6 6-6" /></svg>
                        <span>${grupo.label}</span>
                      </button>
                    </li>`}
                ${cerrado ? '' : grupo.items.map(item => html`
                  <li>
                    <a href="${item.path}"
                       class="flex items-center gap-3 px-3.5 py-2.5 no-underline whitespace-nowrap overflow-hidden
                              transition-colors hover:bg-[var(--sidebar-active-bg)]
                              text-[var(--sidebar-text)] hover:text-[var(--sidebar-text-hover)]">
                      ${NAV_ICONS[item.iconKey]}
                      ${this.collapsed ? '' : html`<span class="text-sm font-medium">${item.label}</span>`}
                    </a>
                  </li>`)}`;
            })}
          </ul>
        </nav>
        <main id="outlet" class="flex-1 p-5 min-w-0 overflow-x-hidden bg-[var(--bg-page)]"></main>
      </div>`;
  }
}

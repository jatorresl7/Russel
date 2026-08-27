import { LitElement, html, TemplateResult } from 'lit';
import { property, state } from 'lit/decorators.js';
import { MessageBroker } from './broker';
import { CrudService } from './crud-service';
import { Column } from './types';
import { ICON_EYE, ICON_EDIT_16, ICON_DELETE_16 } from './icons';
import { t, subscribeI18n } from '../i18n/t';
import { Carga } from './carga';

export abstract class CrudTable<T> extends LitElement {
  abstract prefix: string;
  abstract service: CrudService<T>;
  abstract columns(): Column<T>[];

  @property({ type: Boolean }) canEdit   = true;
  @property({ type: Boolean }) canDelete = true;
  @property({ type: Boolean }) canDetail = false;

  // Ver `Carga`. Antes esto era `items = null` al empezar a cargar, y el render
  // devolvía "Cargando…" — o sea que CADA tecleada en la búsqueda desmontaba la
  // tabla entera Y la propia caja de búsqueda, que vive en el toolbar.
  private _datos = new Carga<{ items: T[]; total: number } | null>(this, null);
  @state() private _page = 0;
  protected get items(): T[] | null { return this._datos.valor?.items ?? null; }
  private get _total(): number { return this._datos.valor?.total ?? 0; }
  private get error(): boolean { return this._datos.error || this._vencido; }
  @state() private _vencido = false;
  // Paginación: solo se activa si hay más de `pageSize` filas (las listas
  // chicas se renderizan enteras, sin cambios). Evita pintar cientos de filas
  // de golpe (ej. 681 empleados) que hacía la tabla lentísima.
  protected pageSize = 50;
  private timeoutId?: number;

  // Modo server-side (opt-in por subclase): el backend pagina y filtra; la
  // tabla pide una página a la vez vía `service.findPage`. Por defecto false
  // → las demás tablas siguen bajando todo y paginando en cliente.
  protected get serverPaginated(): boolean { return false; }
  /** Término de búsqueda para el backend (solo en modo server). */
  protected searchTerm(): string { return ''; }
  /** Recarga desde la subclase (ej. al cambiar la búsqueda). */
  protected reloadPage(resetToFirst = false) {
    if (resetToFirst) this._page = 0;
    this.load();
  }

  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    // `update-list` llega DESPUÉS de crear, editar o borrar. Lo guardado ya no vale:
    // si no se limpia, la lista vuelve a pintar el estado anterior al cambio que la
    // persona acaba de hacer. Se limpia todo por lo mismo de siempre — un alta puede
    // cambiar más de una vista.
    MessageBroker.subscribe(this as any, `${this.prefix}-update-list`, () => {
      Carga.invalidar();
      this.load();
    });
    this.load();
  }

  disconnectedCallback() {
    MessageBroker.unsubscribeAll(this as any);
    clearTimeout(this.timeoutId);
    this._unsubI18n();
    super.disconnectedCallback();
  }

  firstUpdated() {
    // Perro guardián de la PRIMERA carga: si a los 8 segundos no ha llegado
    // nada, algo se colgó. No aplica a los refrescos, que ya muestran datos.
    this.timeoutId = window.setTimeout(() => {
      if (this.items === null) { this._vencido = true; }
    }, 8000);
  }

  /** Clave de caché de la lista. `prefix` distingue la tabla; en modo server hay que
   *  agregar la página y la búsqueda, que es lo que cambia el resultado. En modo
   *  cliente se trae todo de una, así que con el prefijo alcanza. */
  private _clave(): string {
    return this.serverPaginated
      ? `lista:${this.prefix}:${this._page}:${this.searchTerm()}`
      : `lista:${this.prefix}`;
  }

  private async load() {
    await this._datos.pedir(async () => {
      if (this.serverPaginated) {
        const pg = await this.service.findPage(this._page, this.pageSize, this.searchTerm());
        return { items: pg.items, total: pg.total };
      }
      const items = await this.service.findAll();
      return { items, total: items.length };
    }, this._clave());
    this._vencido = false;
  }

  // Hooks opcionales para el subcomponente — no-op por defecto, no afectan
  // a las tablas que no los usan.
  protected renderToolbar(): TemplateResult { return html``; }
  protected filterItems(items: T[]): T[] { return items; }

  private _resolve(item: any, key: string): any {
    return key.split('.').reduce((acc, k) => acc?.[k], item);
  }

  private _renderCell(item: T, col: Column<T>): any {
    if (col.renderer) return col.renderer(item);
    const val = this._resolve(item, col.key);
    if (col.slice && typeof val === 'string' && val.length > col.slice)
      return val.slice(0, col.slice) + '…';
    return val ?? '';
  }

  render(): TemplateResult {
    // El toolbar (donde vive la caja de búsqueda) se pinta SIEMPRE, también
    // mientras carga: si desaparece y vuelve, el navegador le quita el foco y
    // se pierde lo que la persona está escribiendo.
    const toolbar = this.renderToolbar();

    if (this.items === null)
      return html`
        ${toolbar}
        <div class="carga-contenido">
          ${this.error
            ? html`<p class="py-10 text-center text-red-400 bg-white rounded-[var(--radius-surface)] shadow-sm">${t('common.error_loading')}</p>`
            : html`<p class="py-10 text-center text-[var(--neutral-500)] bg-white rounded-[var(--radius-surface)] shadow-sm">${t('common.loading')}</p>`}
        </div>`;
    // En modo server el backend ya filtró; en cliente se filtra local.
    const filtered = this.serverPaginated ? this.items : this.filterItems(this.items);

    // Paginación. Modo server: `total` viene del backend, `items` ya es la
    // página. Modo cliente: se pagina sobre lo filtrado (slice local).
    const total      = this.serverPaginated ? this._total : filtered.length;
    const paginated  = total > this.pageSize;
    const totalPages = Math.ceil(total / this.pageSize);
    const page       = Math.min(Math.max(this._page, 0), Math.max(0, totalPages - 1));
    const start      = page * this.pageSize;
    const pageItems  = this.serverPaginated
      ? filtered
      : (paginated ? filtered.slice(start, start + this.pageSize) : filtered);
    const goTo = (p: number) => { this._page = p; if (this.serverPaginated) this.load(); };
    const chevron = (d: string) => html`<svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="${d}"/></svg>`;

    if (!pageItems.length)
      return html`${toolbar}<div class="carga-contenido"><p class="py-10 text-center text-[var(--neutral-500)] bg-white rounded-[var(--radius-surface)] shadow-sm">${t('common.no_results')}</p></div>`;

    const hasActions = this.canEdit || this.canDelete || this.canDetail;

    return html`
      ${toolbar}
      <div class="carga-contenido">
      <div class="w-full bg-white rounded-[var(--radius-surface)] overflow-hidden shadow-sm">
        <table class="w-full border-collapse">
          <thead class="bg-gray-50">
            <tr>
              ${this.columns().map(c => html`
                <th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 border-b border-gray-200">
                  ${c.label}
                </th>`)}
              ${hasActions ? html`<th class="text-left px-4 py-3 text-xs font-semibold uppercase tracking-wider text-gray-500 border-b border-gray-200">${t('common.actions')}</th>` : ''}
            </tr>
          </thead>
          <tbody>
            ${pageItems.map(item => html`
              <tr class="border-b border-gray-50 hover:bg-indigo-50/30 transition-colors">
                ${this.columns().map(c => html`
                  <td class="px-4 py-3 text-sm text-gray-700">${this._renderCell(item, c)}</td>`)}
                ${hasActions ? html`
                  <td class="px-4 py-2">
                    <div class="flex gap-1.5">
                      ${this.canDetail ? html`<button @click="${() => this._publish('detail', item)}" class="p-1.5 border border-gray-200 rounded-[var(--radius-control)] text-gray-500 hover:bg-gray-100 transition-colors" title="${t('common.view')}">${ICON_EYE}</button>` : ''}
                      ${this.canEdit   ? html`<button @click="${() => this._publish('edit',   item)}" class="p-1.5 border border-gray-200 rounded-[var(--radius-control)] text-gray-500 hover:bg-blue-50 hover:border-blue-200 hover:text-blue-500 transition-colors" title="${t('common.edit')}">${ICON_EDIT_16}</button>` : ''}
                      ${this.canDelete ? html`<button @click="${() => this._publish('delete', item)}" class="p-1.5 border border-gray-200 rounded-[var(--radius-control)] text-gray-500 hover:bg-red-50 hover:border-red-200 hover:text-red-500 transition-colors" title="${t('common.delete')}">${ICON_DELETE_16}</button>` : ''}
                    </div>
                  </td>` : ''}
              </tr>`)}
          </tbody>
        </table>
      </div>
      ${paginated ? html`
        <div class="flex items-center justify-end gap-3 mt-3 text-sm text-gray-500">
          <span>${start + 1}–${Math.min(start + this.pageSize, total)} / ${total}</span>
          <button ?disabled=${page === 0} @click=${() => goTo(page - 1)}
            class="p-1.5 border border-gray-200 rounded-[var(--radius-control)] disabled:opacity-40 hover:bg-gray-100 transition-colors" title="${t('common.back')}">
            ${chevron('M15.75 19.5L8.25 12l7.5-7.5')}
          </button>
          <button ?disabled=${page >= totalPages - 1} @click=${() => goTo(page + 1)}
            class="p-1.5 border border-gray-200 rounded-[var(--radius-control)] disabled:opacity-40 hover:bg-gray-100 transition-colors">
            ${chevron('M8.25 4.5l7.5 7.5-7.5 7.5')}
          </button>
        </div>` : ''}
      </div>`;
  }

  private _publish(action: string, item: T) {
    MessageBroker.publish(`${this.prefix}-${action}`, { element: item });
  }
}

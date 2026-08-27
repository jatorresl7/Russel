import { LitElement, html, TemplateResult } from 'lit';
import { state } from 'lit/decorators.js';
import { MessageBroker } from './broker';
import { CrudService } from './crud-service';
import { CrudForm } from './crud-form';
import { KanbanBoard } from './kanban-board';
import { Carga } from './carga';

export abstract class KanbanPage<T extends object> extends LitElement {
  abstract prefix: string;
  abstract label: string;
  abstract readonly service: CrudService<T>;
  abstract createBoard(): KanbanBoard<T>;
  abstract createForm(): CrudForm<T>;
  abstract moveItem(item: T, columnKey: string): Promise<void>;

  @state() protected items: T[] = [];
  /** Ver `Carga`: refrescar no vacía el tablero y una respuesta atrasada no
   *  pisa a una más nueva. `loading` es solo la PRIMERA carga. */
  protected _datos = new Carga<T[]>(this, [], () => this._reflejarEnTablero());
  protected get _rawItems(): T[] { return this._datos.valor; }
  protected get loading(): boolean { return this._datos.vacia; }
  @state() private panelOpen = false;
  @state() private panelTitle = '';
  @state() private deleteTarget: T | null = null;
  @state() private deleting = false;
  @state() private _detailItem: T | null = null;
  @state() private _detailOpen = false;

  protected _board!: KanbanBoard<T>;
  private _form!: CrudForm<T>;

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._board = this.createBoard();
    this._form  = this.createForm();

    MessageBroker.subscribe(this as any, `${this.prefix}-edit`,      ({ detail }) => this._openEdit(detail.element));
    MessageBroker.subscribe(this as any, `${this.prefix}-delete`,    ({ detail }) => { this.deleteTarget = detail.element; });
    MessageBroker.subscribe(this as any, `${this.prefix}-detail`,    ({ detail }) => { this._detailItem = detail.element; this._detailOpen = true; });
    MessageBroker.subscribe(this as any, `${this.prefix}-create-in`, ({ detail }) => this._openCreate(detail.estado));
    MessageBroker.subscribe(this as any, `${this.prefix}-move`,      ({ detail }) => this._move(detail.item, detail.estado));
    MessageBroker.subscribe(this as any, `${this.prefix}-created`,   () => this._afterSave());
    MessageBroker.subscribe(this as any, `${this.prefix}-edited`,    () => this._afterSave());

    this._load();
  }

  disconnectedCallback() {
    MessageBroker.unsubscribeAll(this as any);
    super.disconnectedCallback();
  }

  /** Clave de caché, o `undefined` para no cachear (por defecto). Tiene que llevar
   *  los filtros que van al backend — los que se resuelven en `filterItems` no, que
   *  esos no cambian lo que se pidió. */
  protected claveDeCarga(): string | undefined { return undefined; }

  /** Lo que se deriva de los datos, en cuanto llegan — venga de la caché o del
   *  backend. Ver el tercer argumento de `Carga`. */
  protected _reflejarEnTablero() {
    this.items = this.filterItems(this._rawItems);
    if (this._board) this._board.items = this.items;
  }

  protected async _load() {
    await this._datos.pedir(() => this.loadItems(), this.claveDeCarga());
    this._reflejarEnTablero();
  }

  protected loadItems(): Promise<T[]> {
    return this.service.findAll();
  }

  protected filterItems(items: T[]): T[] {
    return items;
  }

  protected renderFilters(): TemplateResult {
    return html``;
  }

  protected renderDetail(_item: T): TemplateResult {
    return html`<p class="text-sm text-gray-400">Sin vista de detalle configurada.</p>`;
  }

  protected closeDetail() { this._detailOpen = false; }

  protected _renderDetailPanel(): TemplateResult {
    const open = this._detailOpen;
    return html`
      <div class="fixed inset-0 z-40 flex items-center justify-center ${open ? '' : 'pointer-events-none'}">
        <div class="absolute inset-0 bg-black/40 transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}"
             @click="${() => { this._detailOpen = false; }}"></div>
        <div class="relative bg-white rounded-[var(--radius-surface)] shadow-2xl w-full max-w-lg mx-4 flex flex-col max-h-[90vh]
                    transition-all duration-200 ${open ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-shrink-0">
            <h3 class="text-base font-semibold text-gray-900">Detalle</h3>
            <button @click="${() => { this._detailOpen = false; }}"
              class="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600
                     hover:bg-gray-100 rounded-[var(--radius-control)] border-0 bg-transparent transition-colors text-lg">✕</button>
          </div>
          <div class="overflow-y-auto p-6">
            ${this._detailItem ? this.renderDetail(this._detailItem) : ''}
          </div>
        </div>
      </div>`;
  }

  protected _openCreate(estado = '') {
    this._form.resetForm(estado ? { estado } as unknown as Partial<T> : {});
    this.panelTitle = `Nuevo ${this.label.replace(/s$/, '').toLowerCase()}`;
    this.panelOpen = true;
  }

  private _openEdit(element: T) {
    MessageBroker.publish(`${this.prefix}-load-edit`, { element });
    this.panelTitle = `Editar ${this.label.replace(/s$/, '').toLowerCase()}`;
    this.panelOpen = true;
  }

  private async _move(item: T, estado: string) {
    try {
      await this.moveItem(item, estado);
      await this._load();
    } catch { /* ignore */ }
  }

  private _afterSave() {
    this.panelOpen = false;
    this._load();
  }

  private async _confirmDelete() {
    if (!this.deleteTarget) return;
    this.deleting = true;
    try {
      await this.service.delete(this.service.getKey(this.deleteTarget));
      this.deleteTarget = null;
      await this._load();
    } finally {
      this.deleting = false;
    }
  }

  protected _renderPanel(): TemplateResult {
    const open = this.panelOpen;
    return html`
      <div class="fixed inset-0 z-40 flex items-center justify-center ${open ? '' : 'pointer-events-none'}">
        <div class="absolute inset-0 bg-black/40 transition-opacity duration-200 ${open ? 'opacity-100' : 'opacity-0'}"
             @click="${() => { this.panelOpen = false; }}"></div>
        <div class="relative bg-white rounded-[var(--radius-surface)] shadow-2xl w-full max-w-lg mx-4 flex flex-col max-h-[90vh]
                    transition-all duration-200 ${open ? 'opacity-100 scale-100' : 'opacity-0 scale-95'}">
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-200 flex-shrink-0">
            <h3 class="text-base font-semibold text-gray-900">${this.panelTitle}</h3>
            <button @click="${() => { this.panelOpen = false; }}"
              class="w-8 h-8 flex items-center justify-center text-gray-400 hover:text-gray-600
                     hover:bg-gray-100 rounded-[var(--radius-control)] border-0 bg-transparent transition-colors text-lg">✕</button>
          </div>
          <div class="overflow-y-auto p-6">${this._form}</div>
        </div>
      </div>`;
  }

  protected _renderDeleteConfirm(): TemplateResult {
    if (!this.deleteTarget) return html``;
    return html`
      <div class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
        <div class="bg-white rounded-[var(--radius-surface)] px-8 py-7 shadow-2xl text-center min-w-[280px]">
          <p class="text-base font-medium text-gray-900 mb-5">¿Eliminar este elemento?</p>
          <button @click="${() => this._confirmDelete()}" ?disabled="${this.deleting}"
            class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-[var(--radius-control)] text-sm font-medium mr-2.5 transition-colors disabled:opacity-50">
            ${this.deleting ? 'Eliminando...' : 'Confirmar'}
          </button>
          <button @click="${() => { this.deleteTarget = null; }}"
            class="bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-[var(--radius-control)] text-sm font-medium transition-colors">
            Cancelar
          </button>
        </div>
      </div>`;
  }

  protected renderHeader(): TemplateResult {
    return html`
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-2xl font-semibold text-gray-900">${this.label}</h2>
        <button @click="${() => this._openCreate()}"
          class="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-[var(--radius-control)] text-sm font-medium transition-colors">
          + Nuevo
        </button>
      </div>`;
  }

  protected renderContent(): TemplateResult {
    return html`
      <div class="carga-contenido">
        ${this.loading
          ? html`<p class="py-10 text-center text-[var(--neutral-500)]">Cargando...</p>`
          : this._board}
      </div>`;
  }

  render(): TemplateResult {
    return html`
      ${this.renderHeader()}
      ${this.renderFilters()}
      ${this.renderContent()}
      ${this._renderPanel()}
      ${this._renderDeleteConfirm()}
      ${this._renderDetailPanel()}`;
  }
}

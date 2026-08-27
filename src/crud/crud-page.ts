import { LitElement, html, TemplateResult } from 'lit';
import { property, state } from 'lit/decorators.js';
import { MessageBroker } from './broker';
import { CrudTable } from './crud-table';
import { CrudForm } from './crud-form';
import { t, subscribeI18n } from '../i18n/t';

type CrudView = 'list' | 'create' | 'edit' | 'detail';

export abstract class CrudPage<T extends object> extends LitElement {
  abstract prefix: string;
  abstract label: string;
  abstract createTable(): CrudTable<T>;
  abstract createForm(): CrudForm<T>;

  protected get canCreate(): boolean { return true; }
  protected get canEdit():   boolean { return true; }
  protected get canDelete(): boolean { return true; }

  @state() private view: CrudView = 'list';
  @state() private deleteTarget: T | null = null;
  @state() private deleting = false;
  @state() protected detailElement: T | null = null;

  private _table!: CrudTable<T>;
  private _form!: CrudForm<T>;

  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._table = this.createTable();
    this._table.canEdit   = this.canEdit;
    this._table.canDelete = this.canDelete;
    this._form  = this.createForm();

    MessageBroker.subscribe(this as any, `${this.prefix}-edit`,    ({ detail }) => this._showEdit(detail.element));
    MessageBroker.subscribe(this as any, `${this.prefix}-delete`,  ({ detail }) => { this.deleteTarget = detail.element; this.requestUpdate(); });
    MessageBroker.subscribe(this as any, `${this.prefix}-detail`,  ({ detail }) => { this.detailElement = detail.element; this.view = 'detail'; this.requestUpdate(); });
    MessageBroker.subscribe(this as any, `${this.prefix}-created`, ({ detail }) => this.onCreated(detail.element));
    MessageBroker.subscribe(this as any, `${this.prefix}-edited`,  () => this._backToList());
  }

  disconnectedCallback() {
    MessageBroker.unsubscribeAll(this as any);
    this._unsubI18n();
    super.disconnectedCallback();
  }

  /** Qué hacer justo después de crear un elemento. Por defecto vuelve al listado;
   * sobreescribir para, por ejemplo, ir directo al detalle del recién creado
   * cuando el siguiente paso obvio es completarlo ahí (ej. contratos → SLAs). */
  protected onCreated(_element: T): void {
    this._backToList();
  }

  protected _showDetail(element: T) {
    this.detailElement = element;
    this.view = 'detail';
    this.requestUpdate();
  }

  private async _showEdit(element: T) {
    this.view = 'edit';
    this._form.mode = 'edit';
    this.requestUpdate();
    await this.updateComplete;
    MessageBroker.publish(`${this.prefix}-load-edit`, { element });
  }

  private _backToList() {
    this.view = 'list';
    this._form.mode = 'add';
    MessageBroker.publish(`${this.prefix}-update-list`, {});
    this.requestUpdate();
  }

  private async _confirmDelete() {
    if (!this.deleteTarget) return;
    this.deleting = true;
    try {
      await (this._form as any).service.delete(
        (this._form as any).service.getKey(this.deleteTarget)
      );
      MessageBroker.publish(`${this.prefix}-update-list`, {});
    } finally {
      this.deleteTarget = null;
      this.deleting = false;
    }
  }

  private _renderToolbar(): TemplateResult {
    return html`
      <div class="flex items-center justify-between mb-5">
        <h2 class="text-2xl font-semibold text-gray-900">${this.label}</h2>
        ${this.view === 'list' && this.canCreate
          ? html`<button @click="${() => { this.view = 'create'; this.requestUpdate(); }}"
              class="bg-primary hover:bg-primary-hover text-white px-4 py-2 rounded-[var(--radius-control)] text-sm font-medium transition-colors">
              ${t('common.new')}
            </button>`
          : html`<button @click="${() => this._backToList()}"
              class="bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-[var(--radius-control)] text-sm font-medium transition-colors">
              ${t('common.back')}
            </button>`}
      </div>`;
  }

  private _renderDeleteConfirm(): TemplateResult {
    if (!this.deleteTarget) return html``;
    return html`
      <div class="fixed inset-0 bg-black/40 flex items-center justify-center z-[100]">
        <div class="bg-white rounded-[var(--radius-surface)] px-8 py-7 shadow-2xl text-center min-w-[280px]">
          <p class="text-base font-medium text-gray-900 mb-5">${t('common.confirm_delete_title')}</p>
          <button @click="${() => this._confirmDelete()}" ?disabled="${this.deleting}"
            class="bg-red-500 hover:bg-red-600 text-white px-4 py-2 rounded-[var(--radius-control)] text-sm font-medium mr-2.5 transition-colors disabled:opacity-50">
            ${this.deleting ? t('common.deleting') : t('common.confirm')}
          </button>
          <button @click="${() => { this.deleteTarget = null; this.requestUpdate(); }}"
            class="bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-[var(--radius-control)] text-sm font-medium transition-colors">
            ${t('common.cancel')}
          </button>
        </div>
      </div>`;
  }

  protected renderDetail(_element: T): TemplateResult {
    return html`
      <div class="bg-white rounded-[var(--radius-surface)] p-7 shadow-sm max-w-2xl">
        <p class="text-sm text-gray-500">${t('common.no_detail_view')}</p>
      </div>`;
  }

  render(): TemplateResult {
    return html`
      ${this._renderToolbar()}
      ${this.view === 'list'   ? html`${this._table}` : ''}
      ${this.view === 'create' || this.view === 'edit' ? html`${this._form}` : ''}
      ${this.view === 'detail' && this.detailElement ? this.renderDetail(this.detailElement) : ''}
      ${this._renderDeleteConfirm()}`;
  }
}

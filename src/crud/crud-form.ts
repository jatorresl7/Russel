import { LitElement, html, TemplateResult } from 'lit';
import { property, state } from 'lit/decorators.js';
import { MessageBroker } from './broker';
import { CrudService } from './crud-service';
import { FormField } from './types';
import { t, subscribeI18n } from '../i18n/t';

export abstract class CrudForm<T extends object> extends LitElement {
  abstract prefix: string;
  abstract service: CrudService<T>;
  abstract fields(): FormField[];

  @property() mode: 'add' | 'edit' = 'add';
  @state() protected element: Partial<T> = {};
  @state() private errors: Record<string, string> = {};
  @state() private saving = false;

  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    MessageBroker.subscribe(this as any, `${this.prefix}-load-edit`, ({ detail }) => {
      this.element = { ...detail.element };
      this.mode = 'edit';
    });
  }

  disconnectedCallback() {
    MessageBroker.unsubscribeAll(this as any);
    this._unsubI18n();
    super.disconnectedCallback();
  }

  resetForm(initialValues: Partial<T> = {}) {
    this.mode = 'add';
    this.element = initialValues;
    this.errors = {};
  }

  private _readFormData(form: HTMLFormElement): Partial<T> {
    const dto: any = { ...this.element };
    new FormData(form).forEach((value, key) => { dto[key] = value; });
    return dto;
  }

  private _validate(dto: Partial<T>): Record<string, string> {
    const errs: Record<string, string> = {};
    this.fields().forEach(f => {
      const val = (dto as any)[f.key];
      if (f.required && (val === undefined || val === null || val === ''))
        errs[f.key] = t('common.required', { label: f.label });
      if (f.validator && val !== undefined && !f.validator(val))
        errs[f.key] = t('common.invalid', { label: f.label });
    });
    return errs;
  }

  private async _handleSubmit(e: SubmitEvent) {
    e.preventDefault();
    const dto = this._readFormData(e.target as HTMLFormElement);
    const errs = this._validate(dto);
    if (Object.keys(errs).length) { this.errors = errs; return; }

    this.saving = true;
    this.errors = {};
    try {
      const result = this.mode === 'add'
        ? await this.service.create(dto)
        : await this.service.update(dto as T);
      const event = this.mode === 'add' ? 'created' : 'edited';
      MessageBroker.publish(`${this.prefix}-${event}`, { element: result });
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (typeof detail === 'object' && detail.field_errors)
        this.errors = detail.field_errors;
      else
        this.errors['_global'] = typeof detail === 'string' ? detail : t('common.save_error');
    } finally {
      this.saving = false;
    }
  }

  private get _inputClass() {
    return 'w-full px-3 py-2 border border-gray-300 rounded-[var(--radius-control)] text-sm text-gray-900 bg-white outline-none focus:border-primary focus:ring-2 focus:ring-primary/10 transition-colors disabled:opacity-50 disabled:cursor-not-allowed';
  }

  private _renderField(f: FormField): TemplateResult {
    const err = this.errors[f.key];
    return html`
      <div class="flex flex-col gap-1.5 mb-4">
        <label for="${f.key}" class="text-sm font-medium text-gray-700">
          ${f.label}${f.required ? html`<span class="text-red-500 ml-0.5">*</span>` : ''}
        </label>
        ${f.renderer
          ? html`
              <input type="hidden" name="${f.key}" .value="${String((this.element as any)[f.key] ?? '')}">
              ${f.renderer(
                String((this.element as any)[f.key] ?? ''),
                (v: string) => { this.element = { ...this.element, [f.key]: v } as Partial<T>; }
              )}`
          : f.type === 'textarea'
          ? html`<textarea id="${f.key}" name="${f.key}" class="${this._inputClass} min-h-[90px] resize-y" ?disabled="${f.disabled || this.saving}"
                  .value="${String((this.element as any)[f.key] ?? '')}"></textarea>`
          : f.type === 'select'
          ? html`<select id="${f.key}" name="${f.key}" class="${this._inputClass}" ?disabled="${f.disabled || this.saving}"
                  .value="${String((this.element as any)[f.key] ?? '')}">
              <option value="">${t('common.select_placeholder')}</option>
              ${Object.entries(f.options ?? {}).map(([v, l]) => {
                const cur = String((this.element as any)[f.key] ?? '');
                return html`<option value="${v}" ?selected="${v === cur}">${l}</option>`;
              })}
            </select>`
          : html`<input id="${f.key}" name="${f.key}" type="${f.type ?? 'text'}" class="${this._inputClass}" ?disabled="${f.disabled || this.saving}"
                 .value="${String((this.element as any)[f.key] ?? '')}" />`}
        ${err ? html`<span class="text-xs text-red-500">${err}</span>` : ''}
      </div>`;
  }

  private _zone(zone: FormField['zone']) {
    return this.fields().filter(f => (f.zone ?? 'top') === zone);
  }

  render(): TemplateResult {
    const top    = this._zone('top');
    const left   = this._zone('left');
    const right  = this._zone('right');
    const bottom = this._zone('bottom');
    const hasLR  = left.length > 0 || right.length > 0;

    return html`
      <div class="bg-white rounded-[var(--radius-surface)] p-7 shadow-sm max-w-2xl">
        ${this.errors['_global'] ? html`
          <div class="mb-4 px-4 py-3 bg-red-50 border border-red-200 rounded-[var(--radius-control)] text-sm text-red-700">
            ${this.errors['_global']}
          </div>` : ''}
        <form @submit="${this._handleSubmit.bind(this)}">
          <div>${top.map(f => this._renderField(f))}</div>
          ${hasLR ? html`
            <div class="grid grid-cols-2 gap-x-5">
              <div>${left.map(f => this._renderField(f))}</div>
              <div>${right.map(f => this._renderField(f))}</div>
            </div>` : ''}
          <div>${bottom.map(f => this._renderField(f))}</div>
          <button type="submit" ?disabled="${this.saving}"
            class="mt-2 bg-primary hover:bg-primary-hover text-white px-5 py-2 rounded-[var(--radius-control)] text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
            ${this.saving ? t('common.saving') : t('common.save')}
          </button>
        </form>
      </div>`;
  }
}

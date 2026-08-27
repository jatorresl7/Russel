import { LitElement, html, TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';

@customElement('multi-select')
export class MultiSelect extends LitElement {
  @property({ type: Object })  options: Record<string, string> = {};
  @property({ type: Array })   selected: string[] = [];
  @property() placeholder = 'Seleccionar';
  @property({ type: Boolean }) single = false; // single=true → comportamiento de select normal

  @state() private open = false;

  createRenderRoot() { return this; }

  private _pick(key: string) {
    let next: string[];
    if (this.single) {
      next = this.selected[0] === key ? [] : [key];
      this.open = false;
    } else {
      next = this.selected.includes(key)
        ? this.selected.filter(k => k !== key)
        : [...this.selected, key];
    }
    this.selected = next;
    this.dispatchEvent(new CustomEvent('change', { detail: { selected: next }, bubbles: true }));
  }

  private _clear() {
    this.selected = [];
    this.open = false;
    this.dispatchEvent(new CustomEvent('change', { detail: { selected: [] }, bubbles: true }));
  }

  private get _label(): string {
    if (!this.selected.length) return this.placeholder;
    if (this.single || this.selected.length === 1) return this.options[this.selected[0]] ?? this.placeholder;
    return `${this.selected.length} seleccionados`;
  }

  render(): TemplateResult {
    const entries  = Object.entries(this.options);
    const hasItems = this.selected.length > 0;
    const showBadge = !this.single && this.selected.length > 1;

    return html`
      <div class="relative">

        <button type="button" @click="${() => { this.open = !this.open; }}"
          class="flex items-center gap-2 pl-3 pr-2 py-1.5 text-sm border rounded-[var(--radius-control)] bg-white transition-colors
                 ${this.open || hasItems
                   ? 'border-[var(--color-primary)] text-[var(--color-primary)]'
                   : 'border-gray-200 text-gray-700 hover:border-gray-300'}">
          <span class="whitespace-nowrap">${this._label}</span>
          ${showBadge ? html`
            <span class="flex items-center justify-center w-4 h-4 rounded-full text-[10px] font-bold
                         bg-[var(--color-primary)] text-white">
              ${this.selected.length}
            </span>` : ''}
          <span class="text-xs text-gray-400 transition-transform duration-150 ${this.open ? 'rotate-180' : ''}">▾</span>
        </button>

        ${this.open ? html`
          <div class="fixed inset-0 z-10" @click="${() => { this.open = false; }}"></div>

          <div class="absolute top-full left-0 mt-1 z-20 bg-white border border-gray-200 rounded-[var(--radius-surface)] shadow-lg
                      min-w-[190px] py-1 overflow-hidden">
            ${hasItems ? html`
              <button type="button" @click="${() => this._clear()}"
                class="w-full text-left px-3 py-2 text-xs text-gray-400 hover:bg-gray-50
                       border-0 bg-transparent border-b border-gray-100 transition-colors">
                ✕ ${this.single ? 'Quitar filtro' : 'Limpiar selección'}
              </button>` : ''}
            ${entries.map(([key, label]) => {
              const on = this.selected.includes(key);
              return html`
                <button type="button" @click="${() => this._pick(key)}"
                  class="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-left
                         hover:bg-gray-50 border-0 bg-transparent transition-colors
                         ${on ? 'text-[var(--color-primary)] font-medium' : 'text-gray-700'}">
                  <span class="w-4 h-4 rounded-[var(--radius-control)]${this.single ? '-full' : ''} border flex items-center justify-center
                               flex-shrink-0 transition-colors
                               ${on ? 'bg-[var(--color-primary)] border-[var(--color-primary)]' : 'border-gray-300'}">
                    ${on ? html`
                      <svg class="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 10 8">
                        <path stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" d="M1 4l2.5 2.5L9 1"/>
                      </svg>` : ''}
                  </span>
                  ${label}
                </button>`;
            })}
          </div>` : ''}
      </div>`;
  }
}

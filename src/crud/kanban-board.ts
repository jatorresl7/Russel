import { LitElement, html, TemplateResult } from 'lit';
import { property, state } from 'lit/decorators.js';
import { MessageBroker } from './broker';
import { KanbanColumn } from './types';
import { ICON_EDIT_14, ICON_DELETE_14 } from './icons';

export abstract class KanbanBoard<T extends object> extends LitElement {
  abstract prefix: string;
  abstract columns(): KanbanColumn[];
  abstract getColumnKey(item: T): string;
  abstract renderCard(item: T): TemplateResult;

  @property({ type: Array }) items: T[] = [];
  @state() private _dragging: T | null = null;
  @state() private _dragOverCol: string | null = null;

  createRenderRoot() { return this; }

  protected borderClass(_item: T): string {
    return 'border-l-gray-300';
  }

  private _publish(action: string, payload: object) {
    MessageBroker.publish(`${this.prefix}-${action}`, payload);
  }

  private _renderCardWrapper(item: T, _colKey: string): TemplateResult {
    const isDragging = this._dragging === item;

    return html`
      <div
        draggable="true"
        @dragstart="${(e: DragEvent) => { e.dataTransfer!.effectAllowed = 'move'; this._dragging = item; }}"
        @dragend="${() => { this._dragging = null; this._dragOverCol = null; }}"
        @click="${() => { if (!this._dragging) this._publish('detail', { element: item }); }}"
        class="group relative bg-white rounded-[var(--radius-control)] border border-gray-200 border-l-4 ${this.borderClass(item)}
               p-3.5 shadow-sm hover:shadow-md transition-all cursor-pointer
               ${isDragging ? 'opacity-40 scale-95' : 'opacity-100'}">
        ${this.renderCard(item)}
        <div class="flex justify-end gap-1 mt-2.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <button @click="${(e: Event) => { e.stopPropagation(); this._publish('edit', { element: item }); }}"
            class="p-1 text-gray-400 hover:text-blue-500 hover:bg-blue-50 rounded-[var(--radius-control)] border-0 bg-transparent transition-colors" title="Editar">${ICON_EDIT_14}</button>
          <button @click="${(e: Event) => { e.stopPropagation(); this._publish('delete', { element: item }); }}"
            class="p-1 text-red-300 hover:text-red-500 hover:bg-red-50 rounded-[var(--radius-control)] border-0 bg-transparent transition-colors" title="Eliminar">${ICON_DELETE_14}</button>
        </div>
      </div>`;
  }

  render(): TemplateResult {
    const cols = this.columns();
    return html`
      <div class="flex gap-4 overflow-x-auto pb-4">
        ${cols.map(col => {
          const colItems  = this.items.filter(i => this.getColumnKey(i) === col.key);
          const isOver    = this._dragOverCol === col.key;
          const isDragSrc = this._dragging && this.getColumnKey(this._dragging) === col.key;

          return html`
            <div
              class="flex flex-col flex-shrink-0 w-72 rounded-[var(--radius-surface)] overflow-hidden transition-colors
                     ${isOver && !isDragSrc ? 'ring-2 ring-[var(--color-primary)] bg-primary/5' : 'bg-gray-50'}"
              @dragover="${(e: DragEvent) => { e.preventDefault(); e.dataTransfer!.dropEffect = 'move'; this._dragOverCol = col.key; }}"
              @dragleave="${(e: DragEvent) => { if (!(e.currentTarget as Element).contains(e.relatedTarget as Node)) this._dragOverCol = null; }}"
              @drop="${(e: DragEvent) => {
                e.preventDefault();
                this._dragOverCol = null;
                if (this._dragging && this.getColumnKey(this._dragging) !== col.key)
                  this._publish('move', { item: this._dragging, estado: col.key });
                this._dragging = null;
              }}">
              <div class="flex items-center px-4 py-3 gap-2 ${col.headerClass}">
                <span class="w-2 h-2 rounded-full flex-shrink-0 ${col.dotClass}"></span>
                <span class="text-sm font-semibold">${col.label}</span>
                <span class="text-xs font-medium bg-white/60 px-1.5 py-0.5 rounded-full">${colItems.length}</span>
              </div>
              <div class="flex flex-col gap-2.5 p-3 flex-1 min-h-[120px]">
                ${colItems.length
                  ? colItems.map(item => this._renderCardWrapper(item, col.key))
                  : html`<p class="text-xs text-gray-400 text-center py-6 pointer-events-none">Sin elementos</p>`}
              </div>
            </div>`;
        })}
      </div>`;
  }
}

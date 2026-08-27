import { html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { CrudTable } from '../../crud/crud-table';
import { t } from '../../i18n/t';
import { ToolsService, Tool, Corrida } from './tools.service';

@customElement('tools-table')
export class ToolsTable extends CrudTable<Tool> {
  get prefix() { return 'tools'; }
  service = new ToolsService();

  // Sin PUT ni DELETE en el backend no hay editar ni borrar; lo que sí hay es
  // correr, que es para lo que existe una tool.
  canEdit = false;
  canDelete = false;

  @state() private _corriendo: number | null = null;
  @state() private _salida: { tool: Tool; corrida: Corrida } | null = null;

  private async _run(tool: Tool) {
    this._corriendo = tool.id;
    this._salida = null;
    try {
      this._salida = { tool, corrida: await this.service.run(tool.id) };
    } finally {
      this._corriendo = null;
    }
  }

  private _botonRun(tool: Tool): TemplateResult {
    const activo = this._corriendo === tool.id;
    return html`
      <button @click="${() => this._run(tool)}" ?disabled="${this._corriendo !== null}"
        class="px-2.5 py-1 text-xs font-medium rounded-[var(--radius-control)] border
               border-gray-200 bg-white hover:border-[var(--color-accent)]
               transition-colors disabled:opacity-40">
        ${activo ? t('tools.running') : t('tools.run')}
      </button>`;
  }

  columns = () => [
    { key: 'name',        label: t('tools.name') },
    { key: 'description', label: t('tools.description'), slice: 60 },
    { key: 'command',     label: t('tools.command'),     slice: 50 },
    { key: 'id',          label: t('tools.run'), renderer: (tool: Tool) => this._botonRun(tool) },
  ];

  /** La salida se pinta debajo del listado y no en un modal: es texto largo que
   *  se compara con lo que dice la fila, así que las dos cosas tienen que
   *  poderse ver a la vez. */
  render(): TemplateResult {
    return html`
      ${super.render()}
      ${this._salida ? html`
        <div class="mt-5 bg-white border border-gray-200 rounded-[var(--radius-surface)] overflow-hidden shadow-sm">
          <div class="flex items-center gap-2 px-4 py-2.5 border-b border-gray-100 bg-gray-50">
            <span class="text-sm font-semibold text-gray-800">${t('tools.output')} · ${this._salida.tool.name}</span>
            <span class="px-2 py-0.5 rounded-full text-[11px] font-medium
                         ${this._salida.corrida.status === 'success'
                            ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'}">
              ${this._salida.corrida.status}
            </span>
            <button @click="${() => { this._salida = null; }}"
              class="ml-auto text-xs text-gray-400 hover:text-gray-700 bg-transparent border-0">✕</button>
          </div>
          <pre class="px-4 py-3 text-xs text-gray-700 whitespace-pre-wrap break-words max-h-80 overflow-y-auto"
            >${this._salida.corrida.output || '—'}</pre>
        </div>` : ''}`;
  }
}

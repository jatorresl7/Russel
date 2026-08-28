import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { Carga } from '../../crud/carga';
import { t, subscribeI18n } from '../../i18n/t';
import { VozService, Voz, Sonido, EstadoTts, Robot, AjustesRobot, VozCatalogo, Parametros } from './voz.service';

/** Se sondea sólo mientras habla: el resto del tiempo esta pantalla es
 *  estática y no hay nada que refrescar. */
const MS_SONDEO = 1500;

/** La frase de prueba tiene tildes, una eñe y una pregunta a propósito: son
 *  las tres cosas donde las voces se diferencian de verdad. Con "hola" suenan
 *  todas iguales y no se puede elegir. */
/** Los presets, copiados del backend para poder pintar las perillas antes de
 *  que vuelva la primera respuesta. Si divergen, manda el backend: `efectivo`
 *  del endpoint es la verdad. */
const FRASE = 'Hola, soy Russ. ¿Qué estás mirando? Hoy vi algo que no conocía.';

@customElement('voz-page')
export class VozPage extends LitElement {
  private _svc = new VozService();
  private _voces = new Carga<Voz[]>(this, []);
  private _sonidos = new Carga<Sonido[]>(this, []);
  private _estado = new Carga<EstadoTts | null>(this, null);

  @state() private _frase = FRASE;
  @state() private _robot: Robot | null = null;
  /** Lo que el usuario está tocando ahora, sin guardar. Se guarda con el botón:
   *  mover una perilla y que se aplique sola haría imposible comparar. */
  @state() private _ajustes: Partial<AjustesRobot> = {};
  @state() private _preset = 'robot';
  @state() private _finos = false;
  @state() private _catalogo: VozCatalogo[] = [];
  @state() private _busqueda = '';
  @state() private _bajando: string | null = null;
  @state() private _verCatalogo = false;
  @state() private _par: Parametros | null = null;
  /** Lo que se está tocando sin guardar. Igual que con el timbre: mover una
   *  perilla y que se aplique sola haría imposible comparar. */
  @state() private _parEdit: Record<string, number> = {};
  @state() private _probando: string | null = null;
  @state() private _ocupado = false;

  private _sondeo?: number;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._cargar();
    this._sondeo = window.setInterval(() => this._estado.pedir(() => this._svc.estado()), MS_SONDEO);
  }

  disconnectedCallback() {
    clearInterval(this._sondeo);
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _cargar() {
    this._voces.pedir(() => this._svc.voces(), 'voz.voces');
    this._sonidos.pedir(() => this._svc.sonidos(), 'voz.sonidos');
    this._estado.pedir(() => this._svc.estado());
    this._svc.parametros().then(p => {
      this._par = p;
      this._parEdit = { ...p.actual };
    });
    this._svc.robot().then(r => {
      this._robot = r;
      this._preset = r.preset;
      this._ajustes = { ...r.ajustes };
    });
  }

  private async _probar(voz: string) {
    this._probando = voz;
    try { await this._svc.probar(voz, this._frase, this._preset, this._ajustes); }
    finally { setTimeout(() => { this._probando = null; }, 1200); }
  }

  /** Prueba el timbre con la voz activa. Igual que probar una voz: no guarda. */
  private async _probarRobot(preset: string) {
    this._probando = 'robot:' + preset;
    try { await this._svc.probar('', this._frase, preset, preset === this._preset ? this._ajustes : {}); }
    finally { setTimeout(() => { this._probando = null; }, 1200); }
  }

  private _elegirPreset(preset: string) {
    this._preset = preset;
    this._ajustes = {};           // el preset limpio; las perillas parten de él
    this._probarRobot(preset);
  }

  private _parVal(k: string): number {
    if (this._parEdit[k] !== undefined) return this._parEdit[k];
    const d = this._par?.spec[k]?.defecto;
    return d ?? this._par?.spec[k]?.min ?? 0;
  }

  private async _probarParams() {
    this._probando = 'params';
    try { await this._svc.probar('', this._frase, this._preset, this._ajustes, this._parEdit); }
    finally { setTimeout(() => { this._probando = null; }, 1200); }
  }

  private async _guardarParams() {
    if (!this._par?.voz) return;
    this._ocupado = true;
    try {
      await this._svc.guardarParametros(this._par.voz, this._parEdit);
      this._par = await this._svc.parametros();
    } finally { this._ocupado = false; }
  }

  private _resetParams() {
    this._parEdit = {};
    this._probarParams();
  }

  private _renderParam(k: string): TemplateResult {
    const sp = this._par?.spec[k];
    if (!sp) return html``;
    if (k === 'speaker_id' && (this._par?.hablantes ?? 1) < 2) return html``;
    const v = this._parVal(k);
    const tocado = this._parEdit[k] !== undefined;
    return html`
      <div class="py-2 border-b border-gray-50 last:border-0">
        <div class="flex items-center gap-3">
          <span class="text-sm w-32 flex-shrink-0 ${tocado ? 'font-semibold text-gray-900' : 'text-[var(--neutral-600)]'}">${k}</span>
          <input type="range" min="${sp.min}" max="${sp.max}" step="${sp.paso}" .value="${String(v)}"
            @input="${(e: Event) => { this._parEdit = { ...this._parEdit, [k]: Number((e.target as HTMLInputElement).value) }; }}"
            class="flex-1">
          <span class="text-xs font-medium text-gray-900 w-12 text-right">${v}</span>
        </div>
        <p class="text-xs text-[var(--neutral-500)] mt-1 ml-[8.5rem] leading-snug">${sp.que}</p>
      </div>`;
  }

  private async _abrirCatalogo() {
    this._verCatalogo = !this._verCatalogo;
    if (this._verCatalogo && !this._catalogo.length) {
      this._catalogo = await this._svc.catalogo();
    }
  }

  private async _bajar(nombre: string) {
    this._bajando = nombre;
    try {
      await this._svc.bajar(nombre);
      this._catalogo = await this._svc.catalogo();
      Carga.invalidar('voz.');
      this._cargar();
    } finally { this._bajando = null; }
  }

  private async _borrarVoz(nombre: string) {
    await this._svc.borrarVoz(nombre);
    this._catalogo = this._catalogo.map(v => v.nombre === nombre ? { ...v, bajada: false } : v);
    Carga.invalidar('voz.');
    this._cargar();
  }

  private _perilla(k: keyof AjustesRobot, v: number) {
    this._ajustes = { ...this._ajustes, [k]: v };
  }

  private async _guardarRobot() {
    this._ocupado = true;
    try {
      this._robot = await this._svc.guardarRobot(this._preset, this._ajustes);
      this._estado.pedir(() => this._svc.estado());
    } finally { this._ocupado = false; }
  }

  /** El valor a mostrar: lo tocado, o lo que trae el preset elegido. La tabla
   *  de presets viene del backend, así que no hay copia que se desincronice. */
  private _valor(k: keyof AjustesRobot): number {
    if (this._ajustes[k] !== undefined) return this._ajustes[k] as number;
    return this._robot?.base?.[this._preset]?.[k] ?? 0;
  }

  private _slider(k: keyof AjustesRobot, label: string, paso: number, suf = ''): TemplateResult {
    const lim = this._robot?.limites?.[k];
    const min = lim?.min ?? 0;
    const max = lim?.max ?? 1;
    const v = this._valor(k);
    return html`
      <div class="flex items-center gap-3 py-1.5">
        <span class="text-sm text-[var(--neutral-600)] w-32 flex-shrink-0">${label}</span>
        <input type="range" min="${min}" max="${max}" step="${paso}" .value="${String(v)}"
          @input="${(e: Event) => this._perilla(k, Number((e.target as HTMLInputElement).value))}"
          class="flex-1">
        <span class="text-xs font-medium text-gray-900 w-14 text-right">${v}${suf}</span>
      </div>`;
  }

  private async _elegir(voz: string) {
    this._ocupado = true;
    try {
      await this._svc.elegir(voz);
      Carga.invalidar('voz.');
      this._cargar();
    } finally { this._ocupado = false; }
  }

  private async _volumen(v: number) {
    await this._svc.volumen(v);
    this._estado.pedir(() => this._svc.estado());
  }

  private async _subir(evento: string, input: HTMLInputElement) {
    const f = input.files?.[0];
    if (!f) return;
    await this._svc.subirSonido(evento, f);
    input.value = '';
    Carga.invalidar('voz.');
    this._cargar();
  }

  private _renderVoz(v: Voz): TemplateResult {
    return html`
      <div class="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0">
        <button @click="${() => this._elegir(v.nombre)}" ?disabled="${this._ocupado || v.activa}"
          class="w-4 h-4 rounded-full border-2 flex-shrink-0 transition-colors
                 ${v.activa ? 'border-[var(--color-accent)] bg-[var(--color-accent)]' : 'border-gray-300 bg-white hover:border-gray-400'}"
          title="${t('voz.usar_esta')}"></button>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-gray-900">${v.quien}</div>
          <div class="text-xs ${v.rota ? 'text-red-600' : 'text-[var(--neutral-500)]'}">
            ${v.idioma} · ${v.calidad} · ${v.mb} MB${v.extranjera ? ' · ' + t('voz.extranjera') : ''}${v.rota ? ' · ' + t('voz.rota') : ''}
          </div>
        </div>
        <button @click="${() => this._probar(v.nombre)}" ?disabled="${this._probando !== null}"
          class="px-3 py-1.5 text-xs rounded-[var(--radius-control)] border border-gray-200
                 bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-40">
          ${this._probando === v.nombre ? t('voz.sonando') : t('voz.probar')}
        </button>
      </div>`;
  }

  private _renderSonido(s: Sonido): TemplateResult {
    return html`
      <div class="flex items-center gap-3 py-2.5 border-b border-gray-50 last:border-0">
        <span class="w-2 h-2 rounded-full flex-shrink-0 ${s.tiene ? 'bg-green-500' : 'bg-gray-300'}"></span>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-medium text-gray-900">${s.evento}</div>
          <div class="text-xs text-[var(--neutral-500)]">${s.cuando}</div>
        </div>
        ${s.tiene ? html`<span class="text-xs text-[var(--neutral-500)]">${s.kb} KB</span>` : ''}
        <button @click="${() => this._svc.probarSonido(s.evento)}" ?disabled="${!s.tiene}"
          class="px-2.5 py-1.5 text-xs rounded-[var(--radius-control)] border border-gray-200
                 bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-30">
          ${t('voz.probar')}
        </button>
        <label class="px-2.5 py-1.5 text-xs rounded-[var(--radius-control)] border border-gray-200
                      bg-white hover:border-[var(--color-accent)] transition-colors cursor-pointer">
          ${t('voz.cambiar')}
          <input type="file" accept="audio/wav,.wav" class="hidden"
            @change="${(e: Event) => this._subir(s.evento, e.target as HTMLInputElement)}">
        </label>
      </div>`;
  }

  render(): TemplateResult {
    const e = this._estado.valor;
    const voces = this._voces.valor ?? [];
    // Dos columnas desde `xl`. La izquierda lleva lo que se explora —estado y
    // el listado de voces, que con el catálogo abierto es lo más alto— y la
    // derecha lo que se ajusta. Antes era una sola columna estrecha: sobraba
    // media pantalla a la derecha y había que bajar hasta abajo para llegar a
    // los sonidos. `items-start` para que las columnas no se estiren a la
    // altura de la más larga.
    return html`
      <div class="grid grid-cols-1 xl:grid-cols-2 gap-5 items-start max-w-[1500px]">
        <div class="flex flex-col gap-5 min-w-0">
        <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-semibold text-gray-900">${t('voz.estado')}</h3>
            <div class="flex items-center gap-2">
              ${e?.hablando ? html`<span class="text-xs px-2 py-1 rounded-full bg-green-50 text-green-700">${t('voz.hablando')}</span>` : ''}
              ${(e?.en_cola ?? 0) > 0 ? html`<span class="text-xs px-2 py-1 rounded-full bg-gray-100 text-[var(--neutral-600)]">${t('voz.en_cola', { n: e!.en_cola })}</span>` : ''}
              <button @click="${() => this._svc.parar()}" ?disabled="${!e?.hablando && !(e?.en_cola ?? 0)}"
                class="px-3 py-1 text-xs rounded-[var(--radius-control)] border border-gray-200
                       bg-white hover:border-red-400 hover:text-red-600 transition-colors disabled:opacity-30">
                ${t('voz.parar')}
              </button>
            </div>
          </div>
          <div class="flex items-baseline justify-between gap-4 py-2 border-b border-gray-50">
            <span class="text-sm text-[var(--neutral-600)]">${t('voz.voz_activa')}</span>
            <span class="text-sm font-medium text-gray-900">${e?.voz ?? '—'}</span>
          </div>
          <div class="flex items-baseline justify-between gap-4 py-2 border-b border-gray-50">
            <span class="text-sm text-[var(--neutral-600)]">${t('voz.frases_dichas')}</span>
            <span class="text-sm font-medium text-gray-900">${e?.dichas ?? 0}</span>
          </div>
          <div class="flex items-baseline justify-between gap-4 py-2 border-b border-gray-50">
            <span class="text-sm text-[var(--neutral-600)]">${t('voz.sonados')}</span>
            <span class="text-sm font-medium text-gray-900">
              ${e?.sonados ?? 0}${e?.ultimo_sonido ? html` <span class="text-[var(--neutral-500)] font-normal">· ${e.ultimo_sonido}</span>` : ''}
            </span>
          </div>
          <div class="flex items-center justify-between gap-4 py-3">
            <span class="text-sm text-[var(--neutral-600)]">${t('voz.volumen')}</span>
            <div class="flex items-center gap-3 flex-1 max-w-xs">
              <input type="range" min="0" max="150" .value="${String(e?.volumen ?? 100)}"
                @change="${(ev: Event) => this._volumen(Number((ev.target as HTMLInputElement).value))}"
                class="flex-1">
              <span class="text-sm font-medium text-gray-900 w-12 text-right">${e?.volumen ?? 100}%</span>
            </div>
          </div>
          ${e?.error ? html`<p class="mt-2 px-3 py-2 bg-red-50 border border-red-200 rounded-[var(--radius-control)] text-xs text-red-700">${e.error}</p>` : ''}
        </section>

        <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
          <h3 class="text-sm font-semibold text-gray-900 mb-1">${t('voz.elegir_voz')}</h3>
          <p class="text-xs text-[var(--neutral-500)] mb-3">${t('voz.probar_ayuda')}</p>
          <input type="text" .value="${this._frase}"
            @input="${(ev: Event) => { this._frase = (ev.target as HTMLInputElement).value; }}"
            class="w-full px-3 py-2 mb-3 text-sm border border-gray-200 rounded-[var(--radius-control)]
                   focus:outline-none focus:border-[var(--color-accent)]">
          ${voces.length
            ? voces.map(v => this._renderVoz(v))
            : html`<p class="text-sm text-[var(--neutral-500)] py-3">${t('voz.sin_voces')}</p>`}

          <button @click="${() => this._abrirCatalogo()}"
            class="mt-4 px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-gray-200
                   bg-white hover:border-[var(--color-accent)] transition-colors">
            ${this._verCatalogo ? t('voz.cerrar_catalogo') : t('voz.mas_voces')}
          </button>

          ${this._verCatalogo ? html`
            <div class="mt-4 pt-4 border-t border-gray-100">
              <p class="text-xs text-[var(--neutral-500)] mb-3">${t('voz.catalogo_ayuda')}</p>
              <input type="text" placeholder="${t('voz.buscar')}" .value="${this._busqueda}"
                @input="${(e: Event) => { this._busqueda = (e.target as HTMLInputElement).value; }}"
                class="w-full px-3 py-2 mb-3 text-sm border border-gray-200 rounded-[var(--radius-control)]
                       focus:outline-none focus:border-[var(--color-accent)]">
              <div class="max-h-96 overflow-y-auto">
                ${this._catalogo
                  .filter(v => !this._busqueda || v.nombre.toLowerCase().includes(this._busqueda.toLowerCase()))
                  .map(v => html`
                    <div class="flex items-center gap-3 py-1.5 border-b border-gray-50 last:border-0">
                      <div class="flex-1 min-w-0">
                        <div class="text-sm text-gray-900 truncate">${v.nombre}</div>
                        <div class="text-xs text-[var(--neutral-500)]">${v.idioma} · ${v.calidad}</div>
                      </div>
                      ${v.bajada
                        ? html`<button @click="${() => this._borrarVoz(v.nombre)}"
                            class="px-2.5 py-1 text-xs rounded-[var(--radius-control)] border border-gray-200
                                   bg-white hover:border-red-400 hover:text-red-600 transition-colors">
                            ${t('voz.borrar')}</button>`
                        : html`<button @click="${() => this._bajar(v.nombre)}" ?disabled="${this._bajando !== null}"
                            class="px-2.5 py-1 text-xs rounded-[var(--radius-control)] border border-gray-200
                                   bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-40">
                            ${this._bajando === v.nombre ? t('voz.bajando') : t('voz.bajar')}</button>`}
                    </div>`)}
              </div>
            </div>` : ''}
        </section>
        </div>

        <div class="flex flex-col gap-5 min-w-0">
        <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
          <h3 class="text-sm font-semibold text-gray-900 mb-1">${t('voz.params')}</h3>
          <p class="text-xs text-[var(--neutral-500)] mb-3">
            ${t('voz.params_ayuda')}
            ${(this._par?.hablantes ?? 1) > 1
              ? html`<strong>${t('voz.hablantes', { n: this._par!.hablantes })}</strong>` : ''}
          </p>
          ${Object.keys(this._par?.spec ?? {}).map(k => this._renderParam(k))}
          <div class="flex gap-2 mt-4">
            <button @click="${() => this._probarParams()}" ?disabled="${this._probando !== null}"
              class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-gray-200
                     bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-40">
              ${t('voz.probar')}
            </button>
            <button @click="${() => this._guardarParams()}" ?disabled="${this._ocupado}"
              class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-[var(--color-accent)]
                     bg-[var(--color-accent)] text-white transition-colors disabled:opacity-40">
              ${t('voz.guardar')}
            </button>
            <button @click="${() => this._resetParams()}"
              class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-gray-200
                     bg-white hover:border-[var(--color-accent)] transition-colors">
              ${t('voz.reset')}
            </button>
          </div>
        </section>

        <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
          <h3 class="text-sm font-semibold text-gray-900 mb-1">${t('voz.timbre')}</h3>
          <p class="text-xs text-[var(--neutral-500)] mb-3">${t('voz.timbre_ayuda')}</p>
          <div class="flex flex-wrap gap-2 mb-4">
            ${(this._robot?.presets ?? []).map(p => html`
              <button @click="${() => this._elegirPreset(p)}"
                class="px-3 py-1.5 text-xs rounded-[var(--radius-control)] border transition-colors
                       ${this._preset === p
                         ? 'border-[var(--color-accent)] bg-[var(--color-accent)] text-white'
                         : 'border-gray-200 bg-white hover:border-[var(--color-accent)]'}">
                ${p}${this._probando === 'robot:' + p ? ' ♪' : ''}
              </button>`)}
          </div>
          <button @click="${() => { this._finos = !this._finos; }}"
            class="text-xs text-[var(--neutral-500)] hover:text-gray-900 transition-colors mt-2">
            ${this._finos ? '▾ ' : '▸ '}${t('voz.ajuste_fino')}
          </button>
          ${this._finos ? html`
            <div class="mt-2 pt-2 border-t border-gray-100">
              <p class="text-xs text-[var(--neutral-500)] mb-2">${t('voz.tono_ayuda')}</p>
              ${this._slider('voc_mix', t('voz.voc'), 0.05)}
              ${this._slider('voc_hz', t('voz.voc_hz'), 1, ' Hz')}
              ${this._slider('voc_tilt', t('voz.voc_tilt'), 0.5, ' dB')}
              ${this._slider('semitonos', t('voz.tono'), 0.5, ' st')}
              ${this._slider('formante', t('voz.formante'), 0.01)}
              ${this._slider('drive', t('voz.drive'), 0.01)}
              ${this._slider('eco_mix', t('voz.eco'), 0.01)}
              ${this._slider('anillo_mix', t('voz.anillo'), 0.02)}
              ${this._slider('bits', t('voz.bits'), 1)}
            </div>` : ''}
          <div class="flex gap-2 mt-4">
            <button @click="${() => this._probarRobot(this._preset)}" ?disabled="${this._probando !== null}"
              class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-gray-200
                     bg-white hover:border-[var(--color-accent)] transition-colors disabled:opacity-40">
              ${t('voz.probar')}
            </button>
            <button @click="${() => this._guardarRobot()}" ?disabled="${this._ocupado}"
              class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border border-[var(--color-accent)]
                     bg-[var(--color-accent)] text-white transition-colors disabled:opacity-40">
              ${t('voz.guardar')}
            </button>
          </div>
        </section>

        <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-5 shadow-sm">
          <h3 class="text-sm font-semibold text-gray-900 mb-1">${t('voz.sonidos')}</h3>
          <p class="text-xs text-[var(--neutral-500)] mb-3">${t('voz.sonidos_ayuda')}</p>
          ${(this._sonidos.valor ?? []).map(s => this._renderSonido(s))}
        </section>
        </div>
      </div>`;
  }
}

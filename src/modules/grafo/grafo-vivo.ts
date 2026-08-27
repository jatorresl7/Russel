import { LitElement, html, svg, TemplateResult, SVGTemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import { sseStore } from '../consola/sse.store';
import { SistemaService } from '../sistema/sistema.service';
import { GrafoService, EstadoGrafo, Paso } from './grafo.service';

/**
 * El grafo, moviéndose.
 *
 * Va por SSE y no por sondeo: el backend ya publica cada transición por
 * `/assistant/stream`, y un turno entero puede empezar y terminar en menos de
 * lo que tardaría la siguiente vuelta de un `setInterval`. Sondeando se pierden
 * los estados cortos — `actuando` dura lo que tarda una tool — y justamente
 * esos son los que hay que ver.
 *
 * El estado inicial sí se pide una vez: al montar hay que saber dónde está,
 * y el SSE solo cuenta lo que pasa a partir de ahora.
 */
@customElement('grafo-vivo')
export class GrafoVivo extends LitElement {
  /** En `/russ` va al lado de la cámara y del chat: entra chico y sin historia. */
  @property({ type: Boolean }) compacto = false;

  private _svc = new GrafoService();
  private _sistema = new SistemaService();
  @state() private _g: EstadoGrafo | null = null;
  @state() private _actual = 'latente';
  @state() private _ultimo: Paso | null = null;
  /** Hace cuánto entró al estado actual. Es lo que separa «pensando» de
   *  «colgado»: el nombre del estado es el mismo en los dos casos. */
  @state() private _desdeMs = 0;
  private _entro = Date.now();
  private _cronometro?: number;

  private _unsub?: () => void;
  /** El SSE trae las transiciones, pero `iniciativa` y el cooldown se cambian
   *  por HTTP desde otra vista (o desde /sistema) y no emiten nada. Sin este
   *  refresco, el panel seguia diciendo que la iniciativa estaba apagada
   *  minutos despues de prenderla. */
  private _refresco?: number;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._svc.estado().then(g => {
      this._g = g;
      this._actual = g.estado;
      this._ultimo = g.historia[0] ?? null;
      this._entro = Date.now() - g.desde_ms;
    }).catch(() => {});
    // Medio segundo: suficiente para que el numero se vea correr y no tanto
    // como para repintar el SVG sin motivo.
    this._cronometro = window.setInterval(
      () => { this._desdeMs = Date.now() - this._entro; }, 500);
    this._refresco = window.setInterval(
      () => this._svc.estado().then(g => {
        // Solo los campos que NO vienen por SSE: el estado y la historia los
        // manda el stream y son mas frescos que esta respuesta.
        if (this._g) this._g = { ...this._g, iniciativa: g.iniciativa,
                                 cooldown_restante_s: g.cooldown_restante_s,
                                 ultimo_motivo: g.ultimo_motivo };
      }).catch(() => {}), 5000);
    this._unsub = sseStore.suscribir(ev => {
      if (ev.tipo !== 'grafo') return;
      this._actual = ev.estado;
      this._ultimo = { de: ev.de, a: ev.a, motivo: ev.motivo,
                       at: ev.at, duro_ms: ev.duro_ms };
      this._entro = Date.now();
      this._desdeMs = 0;
      // La historia completa vive en el backend; acá se le pega adelante lo que
      // acaba de llegar para no tener que volver a pedirla en cada transición.
      if (this._g) this._g = { ...this._g, estado: ev.estado,
                               historia: [this._ultimo, ...this._g.historia].slice(0, 40) };
    });
  }

  disconnectedCallback() {
    clearInterval(this._refresco);
    clearInterval(this._cronometro);
    this._unsub?.();
    this._unsubI18n();
    super.disconnectedCallback();
  }

  // ── Dibujo ────────────────────────────────────────────────────────────────
  // Una sola geometría para los dos tamaños: el SVG escala solo por viewBox.
  private static NODOS: Record<string, { x: number; y: number; llm: boolean }> = {
    latente:      { x: 20,  y: 105, llm: false },
    atento:       { x: 200, y: 20,  llm: false },
    resolviendo:  { x: 380, y: 105, llm: true },
    actuando:     { x: 380, y: 195, llm: false },
    consolidando: { x: 200, y: 195, llm: true },
  };
  private static W = 118;
  private static H = 42;

  private _caja(nombre: string): SVGTemplateResult {
    const n = GrafoVivo.NODOS[nombre];
    const on = nombre === this._actual;
    const { W, H } = GrafoVivo;
    return svg`
      <g>
        <rect x="${n.x}" y="${n.y}" width="${W}" height="${H}" rx="5"
              fill="${on ? 'var(--color-accent)' : '#ffffff'}"
              stroke="${on ? 'var(--color-accent)' : '#cbd5e1'}"
              stroke-width="${on ? 2.5 : 1.4}"
              class="${on ? 'latiendo' : ''}"/>
        <text x="${n.x + W / 2}" y="${n.y + (n.llm ? 20 : 26)}" text-anchor="middle"
              font-size="12.5" font-weight="600"
              fill="${on ? '#ffffff' : '#334155'}"
              font-family="ui-monospace, monospace">${nombre}</text>
        ${n.llm ? svg`
          <text x="${n.x + W / 2}" y="${n.y + 33}" text-anchor="middle" font-size="9"
                fill="${on ? 'rgba(255,255,255,.8)' : '#94a3b8'}"
                font-family="ui-monospace, monospace">${t('grafo.usa_llm')}</text>` : ''}
      </g>`;
  }

  private _arista(puntos: string, punteada = false): SVGTemplateResult {
    return svg`<polyline points="${puntos}" fill="none" stroke="#94a3b8"
                 stroke-width="1.4" stroke-dasharray="${punteada ? '4 3' : ''}"
                 marker-end="url(#fl)"/>`;
  }

  private _renderSvg(): TemplateResult {
    return html`
      <svg viewBox="0 0 520 260" preserveAspectRatio="xMidYMid meet"
           class="block mx-auto ${this.compacto ? 'w-full h-full max-h-full' : 'w-full h-auto'}"
           role="img" aria-label="Grafo de estados. Estado actual: ${this._actual}">
        <defs>
          <marker id="fl" markerWidth="8" markerHeight="6" refX="7.5" refY="3" orient="auto">
            <polygon points="0 0, 8 3, 0 6" fill="#94a3b8"/>
          </marker>
        </defs>
        ${this._arista('79,105 79,41 192,41')}
        ${this._arista('200,55 134,55 134,101', true)}
        ${this._arista('318,41 439,41 439,101')}
        ${this._arista('380,126 116,126')}
        ${this._arista('424,147 424,191')}
        ${this._arista('454,191 454,151')}
        ${this._arista('79,147 79,216 192,216')}
        ${this._arista('200,206 110,206 110,151', true)}
        ${Object.keys(GrafoVivo.NODOS).map(n => this._caja(n))}
      </svg>`;
  }

  // ── Lo que está haciendo, en palabras ─────────────────────────────────────

  /** Cada estado con nombre y con explicación. El nombre del nodo —`latente`,
   *  `resolviendo`— es del código: dice dónde está parado el grafo, no qué está
   *  pasando. Para mirar esto y entender algo hace falta la traducción. */
  private _lectura(): { nombre: string; que: string; tono: string; vivo: boolean } {
    const e = this._actual;
    const ini = !!this._g?.iniciativa;
    const d = e === 'latente' && ini ? 'd_latente_ini' : 'd_' + e;
    const tonos: Record<string, string> = {
      latente:      'text-[var(--neutral-500)] bg-[var(--neutral-050)] border-gray-200',
      atento:       'text-amber-800 bg-amber-50 border-amber-200',
      resolviendo:  'text-[var(--color-accent)] bg-[#e8f1fd] border-[#bcd8ff]',
      actuando:     'text-amber-900 bg-amber-50 border-amber-300',
      consolidando: 'text-[var(--color-accent)] bg-[#e8f1fd] border-[#bcd8ff]',
    };
    return {
      nombre: t('grafo.n_' + e),
      que:    t('grafo.' + d),
      tono:   tonos[e] ?? tonos.latente,
      vivo:   e !== 'latente',
    };
  }

  /** Segundos mientras son pocos, minutos cuando ya no importan los segundos.
   *  Un `latente` de 40 minutos en milisegundos no se lee. */
  private _hace(ms: number): string {
    const s = ms / 1000;
    if (s < 60)   return `${s.toFixed(1)} s`;
    if (s < 3600) return `${Math.floor(s / 60)} min`;
    return `${Math.floor(s / 3600)} h`;
  }

  /** El bloque grande: qué hace, hace cuánto y por qué llegó ahí. Es la razón
   *  de ser de la pantalla; el dibujo del grafo queda abajo como mapa. */
  private _renderAhora(): TemplateResult {
    const l = this._lectura();
    const p = this._ultimo;
    return html`
      <div class="rounded-[var(--radius-control)] border px-3.5 py-3 flex-shrink-0 ${l.tono}">
        <div class="flex items-baseline gap-2">
          <span class="w-2 h-2 rounded-full bg-current flex-shrink-0
                       ${l.vivo ? 'latiendo' : ''}"></span>
          <span class="text-[15px] font-semibold leading-tight">${l.nombre}</span>
          <span class="ml-auto text-[11px] tabular-nums opacity-70 flex-shrink-0">
            ${this._hace(this._desdeMs)}
          </span>
        </div>
        <p class="text-[12.5px] leading-snug mt-1 opacity-90">${l.que}</p>
        ${p ? html`
          <p class="text-[11.5px] mt-1.5 pt-1.5 border-t border-black/10 opacity-75
                    flex items-baseline gap-1.5 flex-wrap">
            <span class="font-mono">${p.de}</span>
            <span>→</span>
            <span class="font-mono font-semibold">${p.a}</span>
            <span>· ${t('grafo.porque')}</span>
            <span class="italic">${p.motivo || t('grafo.sin_motivo')}</span>
          </p>` : ''}
      </div>`;
  }

  /** El interruptor de la iniciativa, acá y no solo en `/grafo`: es la
   *  pregunta que uno se hace mirando esta pantalla —«¿puede hablar solo?»— y
   *  tenerla a mano es lo que permite prenderla, verla fallar y apagarla. */
  private async _toggleIniciativa() {
    const on = !this._g?.iniciativa;
    await this._sistema.toggle('iniciativa', on).catch(() => {});
    this._svc.estado().then(g => { if (this._g) this._g = { ...this._g, iniciativa: g.iniciativa }; })
      .catch(() => {});
  }

  private _renderIniciativa(): TemplateResult {
    const on = !!this._g?.iniciativa;
    return html`
      <div class="flex items-center gap-2 flex-wrap text-[11.5px]">
        <span class="uppercase tracking-wider text-[var(--neutral-500)]">${t('grafo.iniciativa')}</span>
        <span class="${on ? 'text-amber-800 font-medium' : 'text-[var(--neutral-500)]'}">
          ${on ? t('grafo.ini_on_corto') : t('grafo.ini_off_corto')}
        </span>
        ${this._g && this._g.cooldown_restante_s > 0
          ? html`<span class="text-amber-700 tabular-nums">
                   ${t('grafo.cooldown', { s: this._g.cooldown_restante_s })}
                 </span>` : ''}
        <button @click="${() => this._toggleIniciativa()}"
          class="ml-auto px-2.5 py-1 rounded-full border transition-colors
                 ${on ? 'bg-amber-600 border-amber-600 text-white hover:bg-amber-700'
                      : 'bg-white border-gray-200 hover:border-[var(--color-accent)]'}">
          ${on ? t('grafo.solo_contesta') : t('grafo.dejar_hablar')}
        </button>
      </div>`;
  }

  render(): TemplateResult {
    const g = this._g;
    return html`
      <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)]
                      p-4 shadow-sm flex flex-col min-h-0
                      ${this.compacto ? 'h-full' : ''}">
        <div class="flex items-baseline gap-2 mb-2.5 flex-shrink-0">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)]">
            ${t('grafo.ahora')}
          </h3>
          <span class="text-[11px] font-mono text-[var(--neutral-500)]">${this._actual}</span>
        </div>

        ${this._renderAhora()}

        <!-- El dibujo pasa a ser el mapa: dice qué otros estados hay y por
             dónde se llega. Quien mira la pantalla ya leyó arriba qué pasa.
             Se queda con el alto sobrante en vez de flotar chico arriba. -->
        <div class="mt-3 pt-3 border-t border-gray-100 flex-1 min-h-0 flex items-center">
          ${this._renderSvg()}
        </div>

        <div class="mt-2.5 pt-2.5 border-t border-gray-100 flex-shrink-0">
          ${this._renderIniciativa()}
        </div>

        ${!this.compacto && g ? html`
          <div class="mt-4 pt-3 border-t border-gray-100">
            <h4 class="text-[10.5px] uppercase tracking-wider text-[var(--neutral-500)] mb-2">
              ${t('grafo.historia')}
            </h4>
            <ul class="list-none p-0 flex flex-col gap-0.5 max-h-[300px] overflow-y-auto">
              ${g.historia.map(p => html`
                <li class="flex items-baseline gap-2 text-[12px] py-1 border-b border-gray-50 last:border-0">
                  <span class="text-[var(--neutral-500)] tabular-nums">${p.at}</span>
                  <span class="font-mono text-gray-500">${p.de}</span>
                  <span class="text-[var(--neutral-500)]">→</span>
                  <span class="font-mono font-semibold text-gray-900">${p.a}</span>
                  <span class="text-[var(--neutral-600)] truncate">${p.motivo}</span>
                  <span class="ml-auto text-[var(--neutral-500)] tabular-nums flex-shrink-0">${p.duro_ms} ms</span>
                </li>`)}
            </ul>
          </div>` : ''}
      </section>`;
  }
}

import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import { RobotService, EstadoRobot, RUEDAS, Rueda } from './robot.service';
import '../vision/camara-panel';
import '../vision/control-stats';
import './robot-sim';

/** El lazo de control corre a 20 Hz en el backend. Se sondea un poco más lento
 *  para no pedir dos veces el mismo estado, pero rápido: acá se está mirando
 *  cómo se mueven las ruedas, y a 300 ms eso se ve a saltos. */
const MS_SONDEO = 70;

@customElement('robot-page')
export class RobotPage extends LitElement {
  private _svc = new RobotService();
  @state() private _s: EstadoRobot | null = null;

  private _sondeo?: number;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._leer();
    this._sondeo = window.setInterval(() => this._leer(), MS_SONDEO);
  }

  disconnectedCallback() {
    clearInterval(this._sondeo);
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _leer() {
    this._svc.state().then(s => { this._s = s; }).catch(() => {});
  }

  private async _seguir() {
    this._s = await this._svc.enable(!this._s?.enabled);
  }

  private async _parar() {
    this._s = await this._svc.stop();
  }

  /** Una barra por rueda, con el cero en el medio: hacia la derecha es hacia
   *  adelante, hacia la izquierda es marcha atrás. Es lo que deja ver de un
   *  golpe que está girando (dos ruedas para cada lado). */
  private _barra(w: Rueda, v: number): TemplateResult {
    const ancho = Math.abs(v) * 50;
    return html`
      <div class="flex items-center gap-2.5 my-1.5 text-sm">
        <b class="w-6 text-[var(--neutral-500)] font-medium uppercase">${w}</b>
        <div class="flex-1 h-3.5 bg-[var(--neutral-050)] border border-gray-200 rounded relative overflow-hidden">
          <div class="absolute top-0 bottom-0 w-px bg-gray-300 left-1/2 z-10"></div>
          <div class="absolute top-0 bottom-0 transition-[width,left] duration-75
                      ${v >= 0 ? 'bg-[var(--color-accent)]' : 'bg-red-500'}"
               style="width:${ancho}%; left:${v >= 0 ? 50 : 50 - ancho}%"></div>
        </div>
        <span class="w-11 text-right tabular-nums text-xs text-[var(--neutral-600)]">${v.toFixed(2)}</span>
      </div>`;
  }

  render(): TemplateResult {
    const s = this._s;
    const siguiendo = !!s?.enabled;

    return html`
      <h2 class="text-2xl font-semibold text-gray-900 mb-1">${t('robot.title')}</h2>
      <p class="text-sm text-[var(--neutral-600)] mb-5">
        ${s?.seen_ago != null ? t('robot.seen_ago', { s: s.seen_ago }) : t('robot.never_seen')}
      </p>

      <div class="grid gap-4 lg:grid-cols-[1fr_330px] max-w-5xl">
        <camara-panel></camara-panel>

        <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-4 shadow-sm">
          <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)] mb-3">
            ${t('robot.movement')}
          </h3>

          <robot-sim .wheels="${s?.wheels ?? null}"></robot-sim>
          <p class="text-[11px] text-[var(--neutral-500)] mt-2 leading-snug">${t('robot.sim_hint')}</p>

          <div class="mt-3">${RUEDAS.map(w => this._barra(w, s?.wheels?.[w] ?? 0))}</div>

          <div class="flex gap-2 mt-4">
            <button @click="${() => this._seguir()}"
              class="flex-1 px-3 py-2 text-sm font-medium rounded-[var(--radius-control)] border transition-colors
                     ${siguiendo ? 'bg-green-600 border-green-600 text-white'
                                 : 'bg-white border-gray-200 hover:border-green-500 text-gray-800'}">
              ${siguiendo ? t('robot.following') : t('robot.follow')}
            </button>
            <button @click="${() => this._parar()}"
              class="flex-1 px-3 py-2 text-sm font-bold rounded-[var(--radius-control)]
                     bg-red-600 hover:bg-red-700 border border-red-600 text-white transition-colors">
              ${t('robot.stop')}
            </button>
          </div>
        </section>
      </div>

      <div class="mt-4 max-w-5xl"><control-stats></control-stats></div>`;
  }
}

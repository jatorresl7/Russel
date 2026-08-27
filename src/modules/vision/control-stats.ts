import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import { VisionService, Control } from './vision.service';

/** Cada cuánto se pide el control. El lazo del robot corre a 20 Hz; 300 ms
 *  alcanza para leerlo y no ahoga la CPU, que acá es el recurso escaso. */
const MS_SONDEO = 300;

/**
 * Las señales que salen de visión: giro, avance, a quién está siguiendo.
 * Compartido entre `vision-page` y `robot-page` — son los mismos números y
 * tienen que leerse igual en los dos lados.
 */
@customElement('control-stats')
export class ControlStats extends LitElement {
  private _svc = new VisionService();
  @state() private _c: Control | null = null;

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
    this._svc.control().then(c => { this._c = c; }).catch(() => {});
  }

  private _tarjeta(k: string, v: string): TemplateResult {
    return html`
      <div class="bg-white border border-gray-200 rounded-[var(--radius-surface)] px-3 py-2.5">
        <div class="text-[10.5px] uppercase tracking-wider text-[var(--neutral-500)]">${k}</div>
        <div class="text-lg font-semibold tabular-nums text-gray-900">${v}</div>
      </div>`;
  }

  render(): TemplateResult {
    const c = this._c;
    const n = (v: number | null | undefined, d = 2) => v == null ? '—' : v.toFixed(d);

    return html`
      ${c?.stale ? html`
        <p class="mb-2.5 px-3 py-2 bg-amber-50 border border-amber-200
                  rounded-[var(--radius-control)] text-xs text-amber-800">
          ${t('vision.stale')}
        </p>` : ''}
      <div class="grid gap-2.5 grid-cols-2 sm:grid-cols-3 lg:grid-cols-5">
        ${this._tarjeta(t('vision.turn'),     n(c?.turn))}
        ${this._tarjeta(t('vision.forward'),  n(c?.forward))}
        ${this._tarjeta(t('vision.target'),   c?.has_target ? '#' + c.track_id : '—')}
        ${this._tarjeta(t('vision.distance'), n(c?.distance))}
        ${this._tarjeta(t('vision.fps'),      n(c?.fps, 1))}
      </div>`;
  }
}

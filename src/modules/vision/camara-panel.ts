import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import { SistemaService } from '../sistema/sistema.service';
import { VisionService, ConfigVision } from './vision.service';

/**
 * La cámara en vivo con sus interruptores. Es un elemento aparte y no parte de
 * `vision-page` porque la vista del robot muestra exactamente lo mismo al lado
 * de la simulación: sin esto habría dos copias del stream y de los toggles que
 * se irían separando con cada cambio.
 *
 * El stream NUNCA se recarga: hay un solo hilo leyendo /dev/video y los botones
 * solo cambian su configuración. Recargar el <img> reabriría la cámara.
 */
@customElement('camara-panel')
export class CamaraPanel extends LitElement {
  private _svc = new VisionService();
  private _sistema = new SistemaService();

  @state() private _cfg: ConfigVision | null = null;
  @state() private _encendida = true;

  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    // El server manda: se sincronizan los botones con su estado real al entrar,
    // si no la vista puede mostrar "apagado" con el modelo pesado corriendo.
    this._svc.config().then(c => { this._cfg = c; }).catch(() => {});
    this._sistema.estado()
      .then(s => { this._encendida = !!s.modulos['vision']?.activo; })
      .catch(() => {});
  }

  disconnectedCallback() {
    // Cortar el MJPEG a mano. El navegador suelta la conexión al quitar el
    // <img>, pero vaciar el src primero lo hace inmediato y determinista —
    // si no, el hilo de la cámara sigue empujando cuadros a nadie.
    const img = this.querySelector('img');
    if (img) img.src = '';
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private async _toggle(clave: 'seg' | 'all_classes') {
    if (!this._cfg) return;
    this._cfg = await this._svc.setConfig({ [clave]: !this._cfg[clave] });
  }

  private async _prenderVision() {
    await this._sistema.toggle('vision', true);
    this._encendida = true;
  }

  private _boton(texto: string, activo: boolean, onClick: () => void): TemplateResult {
    return html`
      <button @click="${onClick}"
        class="px-3 py-1.5 text-sm rounded-[var(--radius-control)] border transition-colors
               ${activo ? 'bg-[var(--color-accent)] border-[var(--color-accent)] text-white'
                        : 'bg-white border-gray-200 hover:border-[var(--color-accent)]'}">
        ${texto}
      </button>`;
  }

  render(): TemplateResult {
    const cfg = this._cfg;
    return html`
      <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-4 shadow-sm">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)] mb-3">
          ${t('vision.camera')}
        </h3>

        ${this._encendida
          ? html`<img src="${VisionService.STREAM}" alt="${t('vision.camera')}"
                   class="w-full rounded-[var(--radius-control)] bg-black block" />`
          : html`
              <div class="rounded-[var(--radius-control)] bg-[var(--neutral-050)] border border-gray-200
                          py-12 px-6 text-center">
                <p class="text-sm text-[var(--neutral-600)] mb-3">${t('vision.module_off')}</p>
                <button @click="${() => this._prenderVision()}"
                  class="bg-primary hover:bg-primary-hover text-white px-4 py-2
                         rounded-[var(--radius-control)] text-sm font-medium transition-colors">
                  ${t('vision.turn_on')}
                </button>
              </div>`}

        <div class="flex gap-2 mt-3 flex-wrap">
          ${this._boton(t('vision.seg'),         !!cfg?.seg,         () => this._toggle('seg'))}
          ${this._boton(t('vision.all_classes'), !!cfg?.all_classes, () => this._toggle('all_classes'))}
          ${this._boton(t('vision.reset'),       false,              () => this._svc.reset())}
        </div>
      </section>`;
  }
}

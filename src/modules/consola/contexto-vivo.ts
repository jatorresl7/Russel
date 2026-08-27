import { LitElement, html, TemplateResult } from 'lit';
import { customElement, state } from 'lit/decorators.js';
import { GlobalConfig } from '../../global-config';
import { t, subscribeI18n } from '../../i18n/t';
import { sseStore } from './sse.store';

interface Recuerdo { id: number; texto: string; sim: number; }

interface Contexto {
  visto: string | null;
  memorias: Recuerdo[];
  turnos: number;
  chars: number;
  para: string | null;
  decision: string | null;
}

const API = GlobalConfig.getInstance().apiUrl;

/**
 * Con qué está pensando Russ ahora mismo.
 *
 * Sin esto, desde afuera solo se ve entrar una frase y salir otra, y todo lo
 * que hay en el medio —qué tenía delante, qué se acordó, cuánto contexto
 * arrastraba, si decidió hablar o usar una herramienta— es invisible. Cuando
 * contesta algo raro, es acá donde se ve por qué.
 *
 * Llega por SSE: el backend publica el contexto DOS veces por turno, antes de
 * generar (ya sabe qué ve y qué recordó) y después (ya sabe qué decidió). Ver
 * la primera mientras el modelo escribe es media gracia del panel.
 */
@customElement('contexto-vivo')
export class ContextoVivo extends LitElement {
  @state() private _c: Contexto | null = null;

  private _unsub?: () => void;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    fetch(API + 'assistant/contexto').then(r => r.json())
      .then(c => { if (c && c.para) this._c = c; }).catch(() => {});
    this._unsub = sseStore.suscribir(ev => {
      if (ev.tipo === 'contexto') this._c = ev as Contexto;
    });
  }

  disconnectedCallback() {
    this._unsub?.();
    this._unsubI18n();
    super.disconnectedCallback();
  }

  private _fila(etiqueta: string, cuerpo: TemplateResult | string,
                atenuado = false): TemplateResult {
    return html`
      <div class="flex gap-2 py-1 border-b border-gray-50 last:border-0">
        <span class="text-[10.5px] uppercase tracking-wider text-[var(--neutral-500)]
                     w-[68px] flex-shrink-0 pt-0.5">${etiqueta}</span>
        <div class="flex-1 min-w-0 text-[12.5px] ${atenuado ? 'text-[var(--neutral-500)] italic' : 'text-gray-800'}">
          ${cuerpo}
        </div>
      </div>`;
  }

  render(): TemplateResult {
    const c = this._c;
    return html`
      <section class="bg-white border border-gray-200 rounded-[var(--radius-surface)] p-3.5 shadow-sm">
        <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)] mb-2">
          ${t('contexto.title')}
        </h3>

        ${!c
          ? html`<p class="text-[12.5px] text-[var(--neutral-500)] py-1">${t('contexto.esperando')}</p>`
          : html`
            ${this._fila(t('contexto.para'), html`<span class="break-words">${c.para}</span>`)}
            ${this._fila(t('contexto.ve'),
                c.visto ? c.visto : t('contexto.nada_ve'), !c.visto)}
            ${this._fila(t('contexto.recuerda'),
                c.memorias?.length
                  ? html`<ul class="list-none p-0 flex flex-col gap-0.5">
                           ${c.memorias.map(m => html`
                             <li class="flex gap-2 items-baseline">
                               <span class="flex-1 break-words">${m.texto}</span>
                               <code class="text-[10.5px] text-[var(--color-accent)] tabular-nums flex-shrink-0">${m.sim}</code>
                             </li>`)}
                         </ul>`
                  : t('contexto.nada_recuerda'),
                !c.memorias?.length)}
            ${this._fila(t('contexto.ventana'),
                html`<span class="tabular-nums">${t('contexto.turnos', { n: c.turnos })}
                     · ${t('contexto.tamano', { n: c.chars })}</span>`)}
            ${this._fila(t('contexto.decision'),
                c.decision
                  ? html`<span class="px-1.5 py-0.5 rounded text-[11px] font-mono
                                      ${c.decision === 'hablar'
                                        ? 'bg-gray-100 text-gray-700'
                                        : 'bg-[var(--accent-suave,#e8f1fd)] text-[var(--color-accent)]'}"
                         >${c.decision === 'hablar' ? t('contexto.hablar') : c.decision}</span>`
                  : '…', !c.decision)}`}
      </section>`;
  }
}

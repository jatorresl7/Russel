import { LitElement, html, TemplateResult } from 'lit';
import { customElement, property, state } from 'lit/decorators.js';
import { GlobalConfig } from '../../global-config';
import { t, subscribeI18n } from '../../i18n/t';
import { sseStore } from './sse.store';

/** Una burbuja del hilo. `pisado` es lo que el backend descartó por llegar algo
 *  más nuevo antes de atenderlo — se muestra tachado para que se entienda por
 *  qué nunca contestó eso. */
interface Burbuja {
  /** `nota` son los eventos que no dijo nadie: una tool que corrio, o que Russ
   *  arranco solo. Se ven distinto porque no son parte de la charla.
   *  `piensa` es el bloque <think>: tampoco lo dijo, lo penso. Va aparte y
   *  atenuado — es lo unico que Russ NO te esta diciendo a vos. */
  rol: 'user' | 'bot' | 'nota' | 'piensa';
  texto: string;
  meta?: string;
  pisado?: boolean;
  /** El LLM todavía está escribiendo en esta burbuja. */
  abierta?: boolean;
}

const API = GlobalConfig.getInstance().apiUrl;

/**
 * La charla con Russ: transcripción en vivo y caja de texto.
 *
 * Voz y teclado son el mismo camino. Lo que se escribe NO se pinta al enviarlo:
 * se pinta cuando el backend lo devuelve como evento, igual que lo que se dice
 * en voz alta. Un solo origen de verdad para las dos entradas.
 */
@customElement('chat-panel')
export class ChatPanel extends LitElement {
  /** En `/russ` la charla es una columna angosta al lado de todo lo demás, no
   *  la pantalla entera: sin esto las burbujas quedaban gigantes y el hilo se
   *  comía el espacio de lo que esa pantalla viene a mostrar. */
  @property({ type: Boolean }) compacto = false;

  @state() private _burbujas: Burbuja[] = [];
  @state() private _texto = '';

  private _unsub?: () => void;
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  connectedCallback() {
    super.connectedCallback();
    this._unsub = sseStore.suscribir(ev => this._evento(ev));
  }

  disconnectedCallback() {
    this._unsub?.();
    this._unsubI18n();
    super.disconnectedCallback();
  }

  /** La ultima burbuja abierta de un rol, si es que la hay. Cada canal tiene
   *  la suya: el pensamiento y la respuesta se escriben uno despues del otro
   *  pero son burbujas distintas. */
  private _abiertaDe(rol: Burbuja['rol']): Burbuja | undefined {
    const ultima = this._burbujas[this._burbujas.length - 1];
    return ultima?.abierta && ultima.rol === rol ? ultima : undefined;
  }

  private get _abierta(): Burbuja | undefined {
    return this._abiertaDe('bot');
  }

  /** Escribe en la burbuja abierta de ese rol, o abre una. Se muta en sitio y
   *  se pide el update a mano: crear un array nuevo por cada token a 4 tok/s
   *  esta bien, pero el patron ya estaba y no hay motivo para cambiarlo. */
  private _escribir(rol: Burbuja['rol'], texto: string) {
    const abierta = this._abiertaDe(rol);
    if (!abierta) { this._agregar({ rol, texto, abierta: true }); return; }
    abierta.texto += texto;
    this.requestUpdate();
  }

  private _cerrar(rol: Burbuja['rol']) {
    const abierta = this._abiertaDe(rol);
    if (abierta) { abierta.abierta = false; this.requestUpdate(); }
  }

  private _agregar(b: Burbuja) {
    this._burbujas = [...this._burbujas, b];
  }

  private _evento(ev: any) {
    switch (ev.tipo) {
      case 'user':
        this._agregar({
          rol: 'user',
          texto: ev.text,
          meta: `${ev.origen === 'voz' ? t('consola.voice') : t('consola.keyboard')} · ${ev.at}`,
        });
        break;

      // `start` ya no abre burbuja. Cuando piensa, lo primero que llega es el
      // <think>, y una burbuja de respuesta vacía esperando arriba se veía como
      // que ya había contestado. La abre el primer token de cada canal.
      case 'start':
        break;

      case 'piensa':
        this._escribir('piensa', ev.text);
        break;

      case 'token':
        this._cerrar('piensa');     // arrancó a hablar: dejó de pensar
        this._escribir('bot', ev.text);
        break;

      case 'end': {
        this._cerrar('piensa');
        const abierta = this._abierta;
        const meta = `${ev.tok_s} tok/s · ${(ev.ms / 1000).toFixed(1)}s`;
        if (abierta) {
          abierta.abierta = false;
          abierta.texto = ev.text;  // el texto final, ya sin cortes de token
          abierta.meta = meta;
          this.requestUpdate();
        } else if (ev.text) {
          // Pensó y contestó sin que pasara ningún token por el canal de
          // texto: pasa cuando la respuesta entera vino de una tool.
          this._agregar({ rol: 'bot', texto: ev.text, meta });
        }
        break;
      }

      case 'tool':
        this._agregar({ rol: 'nota', texto: t('consola.tool_used', { name: ev.name }) });
        break;

      case 'tool_result':
        this._agregar({ rol: 'nota', texto: t('consola.tool_result', { text: ev.text }) });
        break;

      case 'iniciativa':
        this._agregar({ rol: 'nota', texto: t('consola.initiative', { motivo: ev.motivo }) });
        break;

      case 'pisado':
        this._agregar({ rol: 'user', texto: ev.text, meta: t('consola.overridden'), pisado: true });
        break;

      case 'error':
        this._agregar({ rol: 'bot', texto: '⚠ ' + ev.text });
        break;

      case 'clear':
        this._burbujas = [];
        break;
    }
  }

  updated() {
    const hilo = this.querySelector('#hilo');
    if (hilo) hilo.scrollTop = hilo.scrollHeight;
  }

  private async _enviar() {
    const texto = this._texto.trim();
    if (!texto) return;
    this._texto = '';
    // El input nunca se bloquea: si está contestando, lo que se escriba pisa lo
    // que hubiera pendiente. La respuesta llega por SSE, no por acá.
    const r = await fetch(API + 'assistant/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: texto }),
    }).then(r => r.json()).catch(() => null);
    if (r && r.ok === false) this._agregar({ rol: 'bot', texto: `(${r.motivo})` });
  }

  private _renderBurbuja(b: Burbuja): TemplateResult {
    const c = this.compacto;

    // El pensamiento: ancho completo, atenuado y plegable. Abierto mientras
    // escribe —a 4 tok/s son decenas de segundos y es la única señal de que
    // está vivo— y plegado en cuanto empieza a contestar, que es cuando lo que
    // importa pasa a ser la respuesta.
    if (b.rol === 'piensa')
      return html`
        <details class="self-stretch rounded-[var(--radius-control)] border border-dashed
                        border-gray-300 bg-[var(--neutral-050)]"
                 ?open="${!!b.abierta}">
          <summary class="cursor-pointer select-none px-2.5 py-1.5 uppercase tracking-wider
                          text-[var(--neutral-500)] ${c ? 'text-[10px]' : 'text-[10.5px]'}
                          ${b.abierta ? 'latiendo' : ''}">
            ${b.abierta ? t('consola.pensando') : t('consola.penso')}
          </summary>
          <p class="px-2.5 pb-2.5 whitespace-pre-wrap break-words text-[var(--neutral-600)]
                    ${c ? 'text-[11.5px]' : 'text-[12.5px]'} leading-snug">${b.texto}</p>
        </details>`;

    if (b.rol === 'nota')
      return html`
        <div class="self-center max-w-[90%] text-[var(--neutral-600)]
                    bg-[var(--neutral-050)] border border-gray-200 rounded-full
                    break-words ${c ? 'text-[10.5px] px-2.5 py-0.5' : 'text-[11.5px] px-3 py-1'}"
        >${b.texto}</div>`;

    const propia = b.rol === 'user';
    const base = `max-w-[88%] whitespace-pre-wrap break-words ${
      c ? 'px-2.5 py-1.5 rounded-[10px] text-[12.5px] leading-snug'
        : 'px-3.5 py-2.5 rounded-[13px] text-sm'}`;
    const tono = propia
      ? 'self-end bg-[var(--color-primary)] text-white rounded-br-[4px]'
      : 'self-start bg-white border border-gray-200 text-gray-900 rounded-bl-[4px]';
    const tachado = b.pisado ? 'opacity-45 line-through' : '';
    return html`
      <div class="${base} ${tono} ${tachado} ${b.abierta ? 'caret' : ''}">${b.texto}</div>
      ${b.meta ? html`<div class="text-gray-500 mt-0.5 mx-0.5 ${c ? 'text-[10px]' : 'text-[11px]'}
                                  ${propia ? 'self-end' : 'self-start'}">${b.meta}</div>` : ''}`;
  }

  render(): TemplateResult {
    const c = this.compacto;
    return html`
      <div class="flex flex-col h-full min-h-0 bg-[var(--neutral-050)]
                  border border-gray-200 rounded-[var(--radius-surface)] overflow-hidden">
        ${c ? html`
          <div class="px-3 py-2 border-b border-gray-200 bg-white flex-shrink-0">
            <h3 class="text-xs font-semibold uppercase tracking-wider text-[var(--neutral-500)]">
              ${t('consola.charla')}
            </h3>
          </div>` : ''}

        <div id="hilo" class="flex-1 min-h-0 overflow-y-auto ${c ? 'p-3' : 'p-5'}">
          ${this._burbujas.length
            ? html`<div class="flex flex-col ${c ? 'gap-2' : 'gap-3 max-w-[760px] mx-auto'}">
                     ${this._burbujas.map(b => this._renderBurbuja(b))}
                   </div>`
            : html`<p class="text-center text-gray-500 ${c ? 'text-xs mt-8 px-2' : 'text-sm mt-[18vh]'}">
                     ${t('consola.empty')}
                   </p>`}
        </div>

        <div class="border-t border-gray-200 bg-white flex-shrink-0 ${c ? 'px-2.5 py-2' : 'px-4 py-3'}">
          <div class="flex gap-2 ${c ? '' : 'max-w-[760px] mx-auto'}">
            <input .value="${this._texto}"
              @input="${(e: Event) => { this._texto = (e.target as HTMLInputElement).value; }}"
              @keydown="${(e: KeyboardEvent) => { if (e.key === 'Enter') this._enviar(); }}"
              placeholder="${t('consola.placeholder')}" autocomplete="off"
              class="flex-1 min-w-0 rounded-[var(--radius-control)] border border-gray-200
                     focus:outline-none focus:border-[var(--color-accent)]
                     ${c ? 'px-2.5 py-1.5 text-[12.5px]' : 'px-3.5 py-2.5 text-sm'}" />
            <button @click="${() => this._enviar()}"
              class="font-medium rounded-[var(--radius-control)] flex-shrink-0
                     bg-primary hover:bg-primary-hover text-white transition-colors
                     ${c ? 'px-3 py-1.5 text-[12.5px]' : 'px-4 py-2 text-sm'}">
              ${t('consola.send')}
            </button>
          </div>
        </div>
      </div>`;
  }
}

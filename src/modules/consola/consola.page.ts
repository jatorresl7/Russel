import { LitElement, html, TemplateResult } from 'lit';
import { customElement } from 'lit/decorators.js';
import './chat-panel';
import './estado-barra';
import './escucha-viva';

/** La charla sola, a pantalla completa. Para hablar con Russ sin la cámara ni
 *  el robot delante — que es lo que querés cuando estás escribiendo. La vista
 *  con todo junto es `<russ-page>`. */
@customElement('consola-page')
export class ConsolaPage extends LitElement {
  createRenderRoot() { return this; }

  render(): TemplateResult {
    return html`
      <div class="flex flex-col gap-3 h-[calc(100vh-3.5rem-4rem)]">
        <div class="bg-white border border-gray-200 rounded-[var(--radius-surface)] px-4 py-3">
          <estado-barra></estado-barra>
        </div>
        <div class="flex-1 min-h-0 grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
          <div class="min-h-0"><chat-panel></chat-panel></div>
          <div class="min-h-0 overflow-y-auto"><escucha-viva></escucha-viva></div>
        </div>
      </div>`;
  }
}

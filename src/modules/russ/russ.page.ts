import { LitElement, html, TemplateResult } from 'lit';
import { customElement } from 'lit/decorators.js';
import { subscribeI18n } from '../../i18n/t';
import '../consola/chat-panel';
import '../consola/estado-barra';
import '../consola/escucha-viva';
import '../consola/contexto-vivo';
import '../vision/camara-panel';
import '../grafo/grafo-vivo';

/**
 * Russ entero en una pantalla, pero la pantalla tiene UN objetivo: entender
 * cómo piensa y cómo interactúa. Todo el reparto sale de ahí.
 *
 *   piensa    la columna ancha, la del medio: el grafo (qué está haciendo y
 *             por qué llegó ahí) y el contexto (con qué lo está pensando).
 *   percibe   riel izquierdo, angosto. La cámara va chica A PROPÓSITO: que
 *             YOLO funciona ya está probado. Las señales de control del robot
 *             —giro, avance, alto de caja, FPS— NO están: son de `/vision` y
 *             `/robot`, y no dicen nada de cómo piensa.
 *   habla     riel derecho, compacto. La charla es la evidencia de la
 *             interacción, no el sujeto: para hablar sin nada alrededor está
 *             `/consola`.
 *
 * SOBRE LAS ALTURAS, que es lo que estaba roto:
 *
 * No alcanza con `h-[calc(...)]` arriba y `overflow-y-auto` en las columnas.
 * Sin filas declaradas, el grid usa `grid-auto-rows: auto` y la fila crece
 * hasta donde llegue el contenido; con la fila creciendo, el `100%` de las
 * columnas no tiene contra qué resolverse y el `overflow` no se activa nunca.
 * Se desbordaba el grafo porque es lo más alto, no porque tuviera nada raro.
 *
 * Por eso las filas van declaradas y en `minmax(0,1fr)`: `1fr` solo ya frena
 * el crecimiento pero deja el mínimo automático puesto, que es del tamaño del
 * contenido — y eso es exactamente lo mismo otra vez. El `minmax(0,…)` es la
 * parte que importa.
 *
 * Debajo de `lg` la altura fija se suelta entera y la página scrollea como
 * cualquier otra: tres rieles independientes en un teléfono no se navegan.
 */
@customElement('russ-page')
export class RussPage extends LitElement {
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  disconnectedCallback() {
    this._unsubI18n();
    super.disconnectedCallback();
  }

  render(): TemplateResult {
    return html`
      <div class="flex flex-col gap-2.5 lg:h-[calc(100vh-3.5rem-2.5rem)]">
        <div class="bg-white border border-gray-200 rounded-[var(--radius-surface)]
                    px-3.5 py-2.5 flex-shrink-0">
          <estado-barra></estado-barra>
        </div>

        <div class="flex-1 min-h-0 grid gap-2.5
                    grid-cols-1
                    lg:grid-cols-[240px_minmax(0,1fr)]
                    lg:grid-rows-[minmax(0,1fr)_320px]
                    xl:grid-cols-[240px_minmax(0,1fr)_320px]
                    xl:grid-rows-[minmax(0,1fr)]">

          <!-- percibe. La cámara mide lo que mide (tiene proporción propia);
               la escucha se queda con todo lo que sobre. -->
          <div class="min-h-0 flex flex-col gap-2.5">
            <camara-panel class="flex-shrink-0"></camara-panel>
            <escucha-viva class="flex-1 min-h-0 flex flex-col"></escucha-viva>
          </div>

          <!-- piensa. El grafo se lleva el alto sobrante y el dibujo escala
               con él: es lo que se viene a mirar, y antes quedaba flotando
               chiquito en una tarjeta con medio metro de blanco abajo.
               El contexto mide lo que mide — son cinco filas de texto. -->
          <div class="min-h-0 flex flex-col gap-2.5">
            <grafo-vivo compacto class="flex-1 min-h-0 flex flex-col"></grafo-vivo>
            <contexto-vivo class="flex-shrink-0"></contexto-vivo>
          </div>

          <!-- habla. Va como item directo del grid y no envuelto en un div:
               su raiz es h-full, y un chat-panel sin display propio no le da
               contra que resolver ese 100%. Como flex item si. -->
          <chat-panel compacto
            class="min-h-0 flex flex-col lg:col-span-2 xl:col-span-1
                   max-lg:h-[420px]"></chat-panel>
        </div>
      </div>`;
  }
}

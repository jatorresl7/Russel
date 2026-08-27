import { LitElement } from 'lit';

/** Lo que se guardó de una carga anterior, con cuándo se guardó. */
interface Entrada { valor: unknown; en: number; }

/**
 * Caché compartida por todas las `Carga` del proceso, con la estrategia de
 * "mostrar lo guardado y revalidar": al volver a una vista se pinta al instante lo
 * que había y en paralelo se pide lo nuevo, que reemplaza en cuanto llega.
 *
 * Se muestra lo viejo A PROPÓSITO, aunque sean datos de operación: la alternativa es
 * una pantalla vacía durante un segundo, y una lista de hace diez segundos informa
 * más que un "Cargando…". Como SIEMPRE se revalida, lo viejo dura lo que tarde la
 * petición — y mientras tanto se ve atenuado, que es lo que dice que está
 * actualizándose.
 *
 * `MAX_EDAD_MS` es el límite de eso: pasado ese tiempo lo guardado ya no se pinta y
 * se espera a los datos frescos. Volver a una vista después de media hora y ver el
 * plan de la mañana sería peor que esperar.
 */
/** Cuánto dura el aviso de "esto cambió". Un solo número para el recuadro del dato
 *  y para el de la zona — estaban en 1,7 y 1,6 sin ninguna razón. La regla de
 *  `styles.css` lo repite en segundos; si se toca uno hay que tocar el otro. */
const DURACION_AVISO = 3000;

const CACHE = new Map<string, Entrada>();
const MAX_EDAD_MS = 5 * 60_000;
const MAX_ENTRADAS = 60;

function guardar(clave: string, valor: unknown) {
  // Map conserva el orden de inserción: el primero es el más viejo.
  if (CACHE.size >= MAX_ENTRADAS && !CACHE.has(clave)) {
    const masViejo = CACHE.keys().next().value;
    if (masViejo !== undefined) CACHE.delete(masViejo);
  }
  CACHE.set(clave, { valor, en: Date.now() });
}

function leer(clave: string): Entrada | undefined {
  const e = CACHE.get(clave);
  if (!e) return undefined;
  if (Date.now() - e.en > MAX_EDAD_MS) { CACHE.delete(clave); return undefined; }
  return e;
}

/**
 * Una sola definición de "estoy cargando" para todo el front.
 *
 * Hasta acá cada componente la resolvía por su cuenta con un booleano
 * `loading`, y todos cometían los mismos tres errores:
 *
 * 1. **Vaciaban la vista para refrescarla.** `loading = true` hace que el
 *    render devuelva un "Cargando…" en lugar del contenido, así que cambiar un
 *    filtro desmonta la tabla/el Gantt entero y lo vuelve a construir. Se pierde
 *    el scroll, parpadea, y se lee como si la página se hubiera recargado —
 *    cuando lo único que cambió fueron los datos. Solo la PRIMERA carga no tiene
 *    nada que mostrar; a partir de ahí siempre hay algo mejor que un vacío.
 *
 * 2. **Se creían la última respuesta, no la última petición.** Al pulsar dos
 *    filtros seguidos salen dos peticiones y no hay ninguna garantía de que
 *    lleguen en orden: si la primera tarda más, gana, y la vista termina
 *    mostrando el filtro que YA no está seleccionado. Acá cada petición lleva un
 *    número de orden y la respuesta de una que quedó atrás se descarta.
 *
 * 3. **Cada uno decidía distinto qué hacer con los datos si fallaba.** Unos los
 *    dejaban (y se veía el filtro anterior como si el nuevo no aplicara), otros
 *    los borraban. Acá se borran, que es lo honesto: no sabemos qué hay.
 *
 * Uso:
 * ```ts
 *   private _datos = new Carga<Fila[]>(this, []);
 *   await this._datos.pedir(() => this.loadData(this.fecha));
 *   // en render:
 *   this._datos.vacia   → placeholder (primera carga, todavía no hay nada)
 *   this._datos.error   → mensaje de error
 *   this._datos.valor   → los datos (siguen siendo los anteriores mientras refresca)
 * ```
 *
 * **El aviso de que está refrescando es automático.** Mientras hay una petición
 * en vuelo, `Carga` pone `data-refrescando` en el elemento del componente, y una
 * sola regla de `styles.css` atenúa lo que esté marcado con `.carga-contenido`.
 * Lo único que pone el componente es esa clase, alrededor de la zona de DATOS —
 * no de los filtros: atenuar el control que la persona acaba de pulsar lo hace
 * parecer deshabilitado, y además es lo único que en ese momento sigue estando
 * al día. Así el aviso es idéntico en todas las vistas en vez de depender de que
 * cada componente se acuerde de inventarlo.
 */
export class Carga<T> {
  private _valor: T;
  private _cargada = false;
  private _pendientes = 0;
  private _ultima = 0;
  private _error = false;
  /** Lo que se está mostrando salió de la caché, o sea que YA responde a lo que se
   *  pidió — solo que puede ser de hace unos segundos. */
  private _desdeCache = false;

  /** `alCambiar` se llama CADA vez que el valor cambia: al servirlo de la caché y
   *  al llegar el fresco. Hace falta para lo que se derive de los datos —el Gantt
   *  mapea sus filas— porque si eso se calcula solo al terminar la petición, el
   *  golpe de caché no se ve: los datos están y la vista sigue vacía. */
  constructor(private host: LitElement, private inicial: T,
              private alCambiar?: () => void) {
    this._valor = inicial;
  }

  private _poner(valor: T) {
    this._valor = valor;
    this._cargada = true;
    this._error = false;
    this.alCambiar?.();
  }

  /** Los datos actuales. Durante un refresco son todavía los anteriores: eso es
   *  justamente lo que evita el parpadeo. */
  get valor(): T { return this._valor; }

  /** Nunca ha llegado una carga con éxito — lo único que se puede mostrar es un
   *  placeholder. Ojo: NO es "está cargando"; una vez hay datos deja de ser true
   *  para siempre. */
  get vacia(): boolean { return !this._cargada && !this._error; }

  /** Hay una petición en vuelo. Nunca sirve para decidir si se pinta el
   *  contenido — para eso está `vacia`. El aviso visual sale solo, vía el
   *  atributo `data-refrescando` en el host. */
  get refrescando(): boolean { return this._pendientes > 0; }

  /** Marca el componente mientras hay una espera que la persona TIENE que ver.
   *
   *  No es lo mismo esperar con la pantalla en blanco que esperar con una respuesta
   *  válida delante:
   *
   *  - Si se cambió un filtro, lo que está en pantalla es la respuesta a OTRA
   *    pregunta. Ahí se atenúa: decir "esto todavía no es lo que pediste".
   *  - Si se volvió a una vista y la caché ya pintó, lo que se ve SÍ responde a lo
   *    que se pidió, solo que puede ser de hace unos segundos. Atenuar ahí es
   *    inventar una espera que no existe y regalar la sensación de instantáneo.
   *
   *  Lo que sí no puede pasar es que un dato cambie en silencio debajo de los ojos
   *  de alguien: para eso está `data-actualizado`, que solo aparece cuando lo que
   *  llegó es DISTINTO de lo que se estaba mostrando. */
  private _marcar() {
    const esperaVisible = this._pendientes > 0 && !this._desdeCache;
    this.host.toggleAttribute('data-refrescando', esperaVisible);
  }

  /** Marca la ZONA entera. Respaldo para cuando no se puede señalar el dato exacto
   *  —porque cambió la cantidad de filas y ya no hay con qué comparar uno a uno. */
  private _avisarCambioDeZona() {
    this.host.toggleAttribute('data-actualizado', true);
    window.setTimeout(() => this.host.removeAttribute('data-actualizado'), DURACION_AVISO + 100);
  }

  /** Todos los trozos de texto que se están mostrando, en orden.
   *
   *  Los datos que ve una persona son, al final, nodos de texto. Compararlos antes y
   *  después de revalidar dice EXACTAMENTE cuáles cambiaron, sin que cada componente
   *  tenga que declarar dónde vive cada valor. */
  private _nodosDeTexto(): Text[] {
    const out: Text[] = [];
    this.host.querySelectorAll('.carga-contenido').forEach(zona => {
      const w = document.createTreeWalker(zona, NodeFilter.SHOW_TEXT);
      let n: Node | null;
      while ((n = w.nextNode())) {
        if ((n.nodeValue ?? '').trim()) out.push(n as Text);
      }
    });
    return out;
  }

  /** Señala UNO POR UNO los datos que cambiaron.
   *
   *  Va por la API de animaciones y no por una clase: Lit es dueño del DOM y del
   *  atributo `class`, así que una clase puesta desde afuera se la lleva el próximo
   *  render. Una animación no toca atributos y no se la puede pisar.
   *
   *  Si cambió la CANTIDAD de nodos —se agregó o se quitó una fila— la comparación
   *  posición a posición deja de significar nada: todo lo que viene después se ve
   *  desplazado y se marcaría entero. Ahí se cae al aviso de zona, que es honesto:
   *  "esto cambió" sin mentir sobre qué. */
  private _resaltar(antes: string[]) {
    const nodos = this._nodosDeTexto();
    if (nodos.length !== antes.length) { this._avisarCambioDeZona(); return; }
    nodos.forEach((n, i) => {
      if ((n.nodeValue ?? '').trim() === antes[i]) return;
      const el = n.parentElement;
      el?.animate(
        [{ boxShadow: '0 0 0 2px rgba(242,132,68,0.95)', borderRadius: '3px' },
         { boxShadow: '0 0 0 2px rgba(242,132,68,0.85)', borderRadius: '3px', offset: 0.55 },
         { boxShadow: '0 0 0 2px rgba(242,132,68,0)',    borderRadius: '3px' }],
        { duration: DURACION_AVISO, easing: 'ease-out' },
      );
    });
  }

  private static _iguales(a: unknown, b: unknown): boolean {
    try { return JSON.stringify(a) === JSON.stringify(b); } catch { return false; }
  }

  /** La última carga terminó mal. */
  get error(): boolean { return this._error; }

  /** Vuelve al estado inicial porque lo cargado ya no corresponde (cambió el
   *  vuelo, el empleado, el contexto). Invalida también lo que esté en vuelo:
   *  esa respuesta es de lo anterior. */
  reiniciar() {
    this._ultima++;
    this._valor = this.inicial;
    this._cargada = false;
    this._error = false;
    this.host.requestUpdate();
  }

  /** Cambia los datos sin pedir nada (filtros que se resuelven en el cliente). */
  set(valor: T) {
    this._poner(valor);
    this.host.requestUpdate();
  }

  /** Pide datos nuevos sin vaciar lo que ya se está mostrando.
   *
   *  Con `clave`, además: si hay algo guardado de antes se pinta AL INSTANTE y la
   *  petición sigue en segundo plano para reemplazarlo. Es lo que hace que volver a
   *  una vista no empiece de cero.
   *
   *  ⚠️ La clave tiene que incluir todo lo que cambia el resultado (el vuelo, la
   *  fecha, los filtros). Una clave que se queda corta sirve los datos de otra cosa,
   *  que es peor que no tener caché. */
  async pedir(fuente: () => Promise<T>, clave?: string): Promise<void> {
    this._desdeCache = false;
    if (clave) {
      const guardado = leer(clave);
      if (guardado) {
        this._poner(guardado.valor as T);
        this._desdeCache = true;
      }
    }
    const orden = ++this._ultima;
    this._pendientes++;
    this._marcar();
    this.host.requestUpdate();
    let textoAntes: string[] | null = null;
    try {
      const valor = await fuente();
      if (orden !== this._ultima) return;   // llegó tarde: ya hay otra petición más nueva
      // Solo se avisa si de verdad cambió algo. Revalidar y que todo siga igual es
      // el caso normal, y ahí no hay nada que contarle a nadie.
      const cambio = this._desdeCache && !Carga._iguales(this._valor, valor);
      // El texto que la persona TIENE delante, antes de reemplazarlo.
      textoAntes = cambio ? this._nodosDeTexto().map(n => (n.nodeValue ?? '').trim()) : null;
      this._poner(valor);
      if (clave) guardar(clave, valor);
    } catch (e) {
      if (orden !== this._ultima) return;
      console.error('[Carga] falló:', e);
      this._valor = this.inicial;
      this._cargada = false;
      this._error = true;
    } finally {
      this._pendientes--;
      this._marcar();
      this.host.requestUpdate();
    }
    // Después del requestUpdate de arriba, no antes: hay que comparar contra lo que
    // Lit YA pintó. Puesto antes, `updateComplete` resolvía de una —no había ningún
    // render pendiente todavía— y se comparaba el texto viejo contra sí mismo, así
    // que nunca encontraba ninguna diferencia.
    if (textoAntes) {
      await this.host.updateComplete;
      this._resaltar(textoAntes);
    }
  }

  /** Trae algo que TODAVÍA no se está mostrando y lo deja listo en la caché.
   *
   *  Sirve para adelantarse a lo que la persona probablemente va a pedir después
   *  —el otro tramo del turno, la página siguiente— para que al pulsar ya esté.
   *  No toca el estado de ningún componente y se calla si falla: es trabajo
   *  especulativo, y que se caiga no puede romper la vista que sí se está viendo. */
  static async precargar<U>(clave: string, fuente: () => Promise<U>): Promise<void> {
    if (leer(clave)) return;            // ya está fresco, no se gasta el viaje
    try {
      guardar(clave, await fuente());
    } catch {
      /* silencio a propósito */
    }
  }

  /** Lee algo que se guardó con `recordar`, o `undefined` si no está o caducó.
   *
   *  Para los DATOS AUXILIARES de una vista: las opciones de un filtro, los
   *  catálogos. Esos no son "el contenido" —tienen su propia `Carga`— pero si
   *  llegan tarde el layout salta: las pastillas de aerolínea aparecen medio
   *  segundo después y empujan todo hacia abajo. Teniéndolas desde el primer
   *  render, la vista se dibuja una sola vez. */
  static guardado<U>(clave: string): U | undefined {
    return leer(clave)?.valor as U | undefined;
  }

  /** Guarda un dato auxiliar para que la próxima vez esté desde el primer render. */
  static recordar(clave: string, valor: unknown) {
    guardar(clave, valor);
  }

  /** Olvida lo guardado. **Obligatorio después de mutar**: si no, se vuelve a la
   *  vista y aparece el estado anterior al cambio que la persona acaba de hacer.
   *  Sin argumento borra todo; con `prefijo`, solo lo que empiece así. */
  static invalidar(prefijo?: string) {
    if (!prefijo) { CACHE.clear(); return; }
    for (const clave of [...CACHE.keys()]) {
      if (clave.startsWith(prefijo)) CACHE.delete(clave);
    }
  }
}

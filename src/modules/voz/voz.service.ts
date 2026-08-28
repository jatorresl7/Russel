import axios from 'axios';
import { GlobalConfig } from '../../global-config';

/** Una voz de Piper bajada en `voces/`. El nombre trae el idioma, quién la
 *  prestó y la calidad separados por guiones — `es_MX-ald-medium` — y así se
 *  desarma en el backend para poder agruparlas por idioma. */
export interface Voz {
  nombre: string;
  idioma: string;
  quien: string;
  calidad: string;
  mb: number;
  activa: boolean;
  /** No es `es_*`. Se marca para que se entienda de dónde sale el timbre, no
   *  como advertencia: habla español igual. */
  extranjera: boolean;
  /** Un .onnx cortado (descarga interrumpida) que onnxruntime no puede abrir.
   *  Se marca al intentar usarla, no al listar: abrir cada modelo para
   *  chequear costaria un segundo por voz cada vez que se pinta la pantalla. */
  rota: boolean;
}

/** Un momento en el que Russ suena sin hablar. `tiene` es si hay un wav
 *  cargado: los sonidos son opcionales, sin archivo el evento pasa en silencio. */
/** Una voz del catálogo de Piper, esté bajada o no. Todas sirven para español:
 *  la fonemización es un paso aparte del modelo, así que una voz japonesa
 *  igual pronuncia español correcto — con su timbre. */
export interface VozCatalogo {
  nombre: string;
  idioma: string;
  codigo: string;
  calidad: string;
  bajada: boolean;
}

export interface Sonido {
  evento: string;
  cuando: string;
  tiene: boolean;
  kb: number;
}

/** Las perillas del timbre robótico. `anillo_*` es la modulación en anillo —el
 *  efecto que más hace—, `bits` el bitcrush, `drive` la saturación y `eco_*` la
 *  caja metálica. Ver `app/services/robotico.py` para por qué son estos cuatro
 *  y en ese orden. */
export interface AjustesRobot {
  /** Vocoder: cuánto zumbido sintético reemplaza a la voz. Es lo único que
   *  suena a MÁQUINA — tono y formante solos dan otra persona, no otra cosa.
   *  No conviene llegar a 1.0: las consonantes sordas (s, f, j) no tienen tono
   *  y el zumbido no las representa. */
  voc_mix: number;
  /** Altura del zumbido. 90-110 Hz robot grande, 150-200 Hz robot chico. */
  voc_hz: number;
  /** Inclinación del zumbido en dB/octava. En 0 el espectro queda plano y eso
   *  es lo que raspa: da casi el doble de agudos que una voz real. 2 iguala el
   *  brillo natural. */
  voc_tilt: number;
  /** En semitonos, no en razón: nadie sabe si 1.18 es mucho, pero +3 semitonos
   *  sí. 12 = una octava. Subir el tono además acorta el audio. */
  semitonos: number;
  /** Mueve los formantes SIN mover el tono. Es el que hace el robot: agudo con
   *  formantes bajos = cuerpo chico. Solo subir el tono da ardilla. */
  formante: number;
  anillo_hz: number;
  anillo_mix: number;
  bits: number;
  drive: number;
  eco_ms: number;
  eco_mix: number;
}

/** Un parámetro de síntesis con su rango. El backend manda los rangos porque
 *  dependen del modelo: `speaker_id` va de 0 a `hablantes-1`, y ese número sale
 *  del .onnx cargado. */
export interface SpecParam {
  min: number;
  max: number;
  paso: number;
  defecto: number | null;
  que: string;
}

export interface Parametros {
  voz: string | null;
  /** Cuántas voces distintas trae el modelo. semaine trae 4. */
  hablantes: number;
  spec: Record<string, SpecParam>;
  actual: Record<string, number>;
}

export interface Robot {
  preset: string;
  ajustes: Partial<AjustesRobot>;
  efectivo: AjustesRobot;
  presets: string[];
  /** Los rangos los manda el backend y no los copia el front: son parte del
   *  contrato. Y son estrechos a propósito — los límites SON la franja que
   *  suena bien, así que cualquier posición del slider es defendible. */
  limites: Record<string, { min: number; max: number }>;
  base: Record<string, Record<string, number>>;
}

export interface EstadoTts {
  hablando: boolean;
  dichas: number;
  /** Blips de evento reproducidos. Separado de `dichas` porque son cosas
   *  distintas, y porque sin este contador no había forma de comprobar que un
   *  evento había sonado más que escucharlo. */
  sonados: number;
  ultimo_sonido: string;
  error: string | null;
  ultimo: string;
  voz: string | null;
  volumen: number;
  activo: boolean;
  en_cola: number;
  voces: number;
  robot: string;
  robot_ajustes: Partial<AjustesRobot>;
  presets: string[];
}

const API = GlobalConfig.getInstance().apiUrl;

export class VozService {
  estado = (): Promise<EstadoTts> => axios.get<EstadoTts>(API + 'tts/estado').then(r => r.data);
  voces  = (): Promise<Voz[]>     => axios.get<Voz[]>(API + 'tts/voces').then(r => r.data);
  sonidos = (): Promise<Sonido[]> => axios.get<Sonido[]>(API + 'tts/sonidos').then(r => r.data);

  elegir = (voz: string) => axios.post(API + 'tts/voz', { voz }).then(r => r.data);

  /** Prueba sin cambiar nada: se puede recorrer voces y timbres enteros y
   *  recién al final quedarse con uno. */
  probar = (voz: string, texto: string, robot?: string,
            ajustes?: Partial<AjustesRobot>, params?: Record<string, number>) =>
    axios.post(API + 'tts/probar', { voz, texto, robot, ajustes, params }).then(r => r.data);

  catalogo = (idioma = '', buscar = ''): Promise<VozCatalogo[]> =>
    axios.get<VozCatalogo[]>(API + 'tts/catalogo', { params: { idioma, buscar } }).then(r => r.data);

  bajar = (nombre: string) => axios.post(API + 'tts/catalogo/' + nombre).then(r => r.data);

  borrarVoz = (nombre: string) => axios.delete(API + 'tts/voces/' + nombre).then(r => r.data);

  parametros = (): Promise<Parametros> =>
    axios.get<Parametros>(API + 'tts/parametros').then(r => r.data);

  guardarParametros = (voz: string, params: Record<string, number>) =>
    axios.post(API + 'tts/parametros', { voz, params }).then(r => r.data);

  /** Corta lo que suene y vacía la cola. El probador ya lo hace solo en el
   *  backend; esto es para el botón manual. */
  parar = () => axios.post(API + 'tts/parar').then(r => r.data);

  robot = (): Promise<Robot> => axios.get<Robot>(API + 'tts/robot').then(r => r.data);

  guardarRobot = (preset: string, ajustes: Partial<AjustesRobot>) =>
    axios.post(API + 'tts/robot', { preset, ajustes }).then(r => r.data);

  volumen = (volumen: number) =>
    axios.post(API + 'tts/volumen', { volumen }).then(r => r.data);

  probarSonido = (evento: string) =>
    axios.post(API + `tts/sonidos/${evento}/probar`).then(r => r.data);

  borrarSonido = (evento: string) =>
    axios.delete(API + `tts/sonidos/${evento}`).then(r => r.data);

  subirSonido = (evento: string, archivo: File) => {
    const fd = new FormData();
    fd.append('archivo', archivo);
    return axios.post(API + `tts/sonidos/${evento}`, fd).then(r => r.data);
  };
}

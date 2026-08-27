import { GlobalConfig } from '../../global-config';

export interface Transcripcion {
  text: string;
  at: string;
  /** Duración del audio, en segundos. */
  dur: number;
  /** Lo que tardó whisper en transcribirlo. */
  took: number;
}

export interface EstadoAudio {
  listening: boolean;
  speaking: boolean;
  vad: number;
  /** Están cargando los modelos (silero, whisper, vosk). Tarda segundos. */
  cargando: boolean;
  /** La pasada final de whisper está corriendo AHORA. Tarda segundos y se
   *  come 9 hilos: es el momento en que la máquina parece colgada. */
  transcribiendo: boolean;
  /** Lo que LocalAgreement ya dio por firme. */
  committed: string;
  /** Lo que todavía puede cambiar en la próxima pasada. */
  pending: string;
  /** La capa instantánea: sale al momento, con errores. */
  vosk: string;
  buffer_s: number;
  pasadas: number;
  ultima_pasada_ms: number;
  dropped: number;
  model: string;
  loaded: boolean;
  error: string | null;
  transcripts: Transcripcion[];
}

export interface EstadoLlmBarra {
  activo: boolean; cargado: boolean; generando: boolean; modelo: string; tok_s: number;
}

const API = GlobalConfig.getInstance().apiUrl;

export const VACIO: EstadoAudio = {
  listening: false, speaking: false, vad: 0, cargando: false, transcribiendo: false,
  committed: '', pending: '', vosk: '', buffer_s: 0, pasadas: 0, ultima_pasada_ms: 0,
  dropped: 0, model: '', loaded: false, error: null, transcripts: [],
};

export class AudioService {
  audio = (): Promise<EstadoAudio> =>
    fetch(API + 'audio/status').then(r => r.json());

  llm = (): Promise<EstadoLlmBarra> =>
    fetch(API + 'assistant/status').then(r => r.json());

  post = (path: string, body?: unknown) =>
    fetch(API + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }).then(r => r.json());
}

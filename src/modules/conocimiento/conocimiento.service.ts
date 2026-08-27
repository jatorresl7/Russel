import axios from 'axios';
import { CrudService } from '../../crud/crud-service';
import { GlobalConfig } from '../../global-config';

export interface Memoria {
  id: number;
  texto: string;
  tipo: 'hecho' | 'episodio';
  /** `explicito` lo guardó Russ con la tool `recordar`; `consolidado` salió del
   *  trabajo de fondo releyendo la charla. */
  fuente: 'explicito' | 'consolidado';
  usos: number;
  vigente: boolean;
  modelo: string;
  ultimo_uso: string | null;
  created_at: string;
}

export interface Recuperada {
  id: number; texto: string; tipo: string; fuente: string; sim: number;
}

export interface EstadoMemoria {
  total: number;
  por_fuente: Record<string, number>;
  por_tipo: Record<string, number>;
  turnos_sin_leer: number;
  esperando: number;
  umbral: number;
  consolidando: boolean;
  ultima_consolidacion: string | null;
  consolidadas: number;
  error: string | null;
  embed: { cargado: boolean; activo: boolean; modelo: string; ultimo_ms: number };
}

const BASE = GlobalConfig.getInstance().apiUrl + 'memoria';

export class ConocimientoService extends CrudService<Memoria> {
  base = BASE;
  getKey = (m: Memoria) => m.id;

  estado = (): Promise<EstadoMemoria> =>
    axios.get<EstadoMemoria>(`${BASE}/estado`).then(r => r.data);

  /** Qué recuperaría Russ para esta frase, sin gastarle un turno. */
  probar = (texto: string): Promise<Recuperada[]> =>
    axios.post<Recuperada[]>(`${BASE}/buscar`, { texto }).then(r => r.data);

  /** Deja que Russ use una memoria, o se la saca sin borrarla. */
  aprobar = (id: number, vigente: boolean): Promise<{ ok: boolean }> =>
    axios.patch(`${BASE}/${id}/vigente`, { vigente }).then(r => r.data);

  consolidar = (): Promise<{ leidos: number; guardadas: number; textos?: string[] }> =>
    axios.post(`${BASE}/consolidar`).then(r => r.data);
}

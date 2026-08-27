import axios from 'axios';
import { GlobalConfig } from '../../global-config';

/** Un módulo del presupuesto de CPU. `peso` es lo que pide; `hilos` lo que le
 *  tocó una vez repartidos los del equipo entre los que están encendidos. */
export interface Modulo {
  activo: boolean;
  hilos: number;
  peso: number;
}

export interface EstadoSistema {
  device: string;
  gpu: boolean;
  compute_type: string;
  total_hilos: number;
  modulos: Record<string, Modulo>;
}

export interface EstadoLlm {
  modelo: string;
  tamano: string;
  motor: string;
  cargado: boolean;
  generando: boolean;
  tok_s: number;
  prefill_ms: number;
  turnos: number;
  activo: boolean;
  error: string | null;
}

const API = GlobalConfig.getInstance().apiUrl;

export class SistemaService {
  estado = (): Promise<EstadoSistema> =>
    axios.get<EstadoSistema>(API + 'system').then(r => r.data);

  toggle = (modulo: string, on: boolean): Promise<EstadoSistema> =>
    axios.post<EstadoSistema>(API + 'system/toggle', { modulo, on }).then(r => r.data);

  llm = (): Promise<EstadoLlm> =>
    axios.get<EstadoLlm>(API + 'assistant/status').then(r => r.data);

  cargarLlm   = (): Promise<EstadoLlm> => axios.post<EstadoLlm>(API + 'assistant/load').then(r => r.data);
  descargarLlm = (): Promise<EstadoLlm> => axios.post<EstadoLlm>(API + 'assistant/unload').then(r => r.data);
}

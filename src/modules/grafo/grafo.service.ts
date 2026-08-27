import axios from 'axios';
import { GlobalConfig } from '../../global-config';

export interface Paso {
  de: string; a: string; motivo: string; at: string; duro_ms: number;
}

export interface EstadoGrafo {
  estado: string;
  desde_ms: number;
  historia: Paso[];
  contadores: Record<string, number>;
  iniciativa: boolean;
  cooldown_s: number;
  cooldown_restante_s: number;
  ultimo_motivo: string;
  estados: string[];
}

const API = GlobalConfig.getInstance().apiUrl;

export class GrafoService {
  estado = (): Promise<EstadoGrafo> =>
    axios.get<EstadoGrafo>(API + 'grafo').then(r => r.data);
}

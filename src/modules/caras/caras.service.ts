import axios from 'axios';
import { GlobalConfig } from '../../global-config';

export interface Track {
  nombre: string | null;
  score: number;
}

export interface EstadoCaras {
  /** nombre -> cuántos vectores tiene guardados */
  conocidos: Record<string, number>;
  /** id de track -> a quién cree que está viendo */
  tracks: Record<string, Track>;
  umbral: number;
}

export interface Enrolamiento {
  ok?: boolean;
  guardadas?: number;
  fallos?: string[];
}

const API = GlobalConfig.getInstance().apiUrl;

export class CarasService {
  estado = (): Promise<EstadoCaras> =>
    axios.get<EstadoCaras>(API + 'faces/estado').then(r => r.data);

  fotos = (nombre: string): Promise<string[]> =>
    axios.get<string[]>(`${API}faces/${encodeURIComponent(nombre)}/fotos`).then(r => r.data);

  /** URL del recorte, para el src de un <img>. */
  static foto = (nombre: string, archivo: string): string =>
    `${API}faces/${encodeURIComponent(nombre)}/foto/${encodeURIComponent(archivo)}`;

  /** Toma `fotos` capturas seguidas de la cámara en vivo. Varias y no una: una
   *  sola vista no cubre los cambios de luz ni los ángulos. */
  enrolar = (nombre: string, fotos: number): Promise<Enrolamiento> =>
    axios.post<Enrolamiento>(API + 'faces/enrolar', { nombre, fotos }).then(r => r.data);

  olvidar = (nombre: string): Promise<{ ok: boolean; borradas: number }> =>
    axios.delete(`${API}faces/${encodeURIComponent(nombre)}`).then(r => r.data);
}

import axios from 'axios';
import { GlobalConfig } from '../../global-config';

export type Rueda = 'fl' | 'fr' | 'rl' | 'rr';

/** Vista desde arriba con el frente hacia arriba:  fl ── fr / rl ── rr */
export const RUEDAS: Rueda[] = ['fl', 'fr', 'rl', 'rr'];

export interface EstadoRobot {
  enabled: boolean;
  wheels: Record<Rueda, number>;
  smoothed: { turn: number; forward: number; strafe: number };
  /** Segundos desde la última vez que vio al objetivo. null = nunca. */
  seen_ago: number | null;
}

const API = GlobalConfig.getInstance().apiUrl;

export class RobotService {
  state = (): Promise<EstadoRobot> =>
    axios.get<EstadoRobot>(API + 'robot/state').then(r => r.data);

  enable = (on: boolean): Promise<EstadoRobot> =>
    axios.post<EstadoRobot>(API + 'robot/enable', { on }).then(r => r.data);

  /** Frena y además apaga el seguimiento: el botón rojo tiene que ser un
   *  final, no una pausa de la que el lazo salga solo en el próximo cuadro. */
  stop = (): Promise<EstadoRobot> =>
    axios.post<EstadoRobot>(API + 'robot/stop').then(r => r.data);
}

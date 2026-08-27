import axios from 'axios';
import { GlobalConfig } from '../../global-config';

export interface ConfigVision {
  cam: number;
  seg: boolean;
  all_classes: boolean;
  conf: number;
  imgsz: number;
}

/** Lo que vision_service le pasa al robot. `stale` es la cámara colgada: el
 *  backend devuelve neutro a propósito, porque mantener el último comando con
 *  el video caído deja al robot girando para siempre sobre una orden vieja. */
export interface Control {
  turn: number;
  forward: number;
  has_target: boolean;
  track_id: number | null;
  distance: number | null;
  fps: number;
  stale: boolean;
}

const API = GlobalConfig.getInstance().apiUrl;

export class VisionService {
  /** MJPEG. Va directo al src de un <img>, no por axios. */
  static readonly STREAM = API + 'vision/stream';

  config = (): Promise<ConfigVision> =>
    axios.get<ConfigVision>(API + 'vision/config').then(r => r.data);

  setConfig = (cambios: Partial<ConfigVision>): Promise<ConfigVision> =>
    axios.post<ConfigVision>(API + 'vision/config', cambios).then(r => r.data);

  control = (): Promise<Control> =>
    axios.get<Control>(API + 'vision/control').then(r => r.data);

  reset = (): Promise<void> =>
    axios.post(API + 'vision/reset').then(() => {});
}

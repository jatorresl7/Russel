import axios from 'axios';
import { CrudService } from '../../crud/crud-service';
import { GlobalConfig } from '../../global-config';

export interface WorkScript {
  id: number;
  name: string;
  title: string;
  filename: string;
  enabled: boolean;
  order: number;
}

export class ScriptsService extends CrudService<WorkScript> {
  base = GlobalConfig.getInstance().apiUrl + 'work-scripts';
  getKey = (s: WorkScript) => s.id;

  /** El backend no expone PUT: habilitar/deshabilitar es su propio endpoint. */
  toggle = (id: number): Promise<WorkScript> =>
    axios.patch<WorkScript>(`${this.base}/${id}/toggle`).then(r => r.data);

  /** Regenera ~/scripts/launch.sh con los habilitados, en orden. */
  generate = (): Promise<{ generated: string; scripts_included: string[] }> =>
    axios.post(`${this.base}/generate`).then(r => r.data);

  run = (): Promise<{ status: string }> =>
    axios.post(`${this.base}/run`).then(r => r.data);
}

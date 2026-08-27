import axios from 'axios';
import { CrudService } from '../../crud/crud-service';
import { GlobalConfig } from '../../global-config';

export interface Tool {
  id: number;
  name: string;
  description: string;
  command: string;
}

export interface Corrida {
  status: 'success' | 'error';
  output: string;
}

export class ToolsService extends CrudService<Tool> {
  base = GlobalConfig.getInstance().apiUrl + 'tools';
  getKey = (t: Tool) => t.id;

  /** Corre el comando en el PC y devuelve stdout+stderr. El backend le pone un
   *  timeout de 60s y guarda cada corrida en script_runs. */
  run = (id: number): Promise<Corrida> =>
    axios.post<Corrida>(`${this.base}/${id}/run`).then(r => r.data);
}

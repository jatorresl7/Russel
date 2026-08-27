import axios from 'axios';
import { GlobalConfig } from '../../global-config';

export interface ResumenGmail {
  id: number;
  date: string;
  email_count: number;
  summary: string;
}

const BASE = GlobalConfig.getInstance().apiUrl + 'gmail';

export class GmailService {
  /** Los últimos 30, del más nuevo al más viejo. */
  listar = (): Promise<ResumenGmail[]> =>
    axios.get<ResumenGmail[]>(`${BASE}/summaries`).then(r => r.data);

  /** Resume los correos de hoy y los guarda. Si ya hay resumen de hoy el
   *  backend devuelve el que existe en vez de gastar otra llamada al LLM. */
  resumirHoy = (): Promise<{ message?: string; summary?: string }> =>
    axios.post(`${BASE}/summarize`).then(r => r.data);
}

import axios from 'axios';

/** Envelope de paginación server-side (coincide con `Page` del backend). */
export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export abstract class CrudService<T> {
  abstract base: string;
  abstract getKey(element: T): string | number;

  findAll = (): Promise<T[]> =>
    axios.get<T[]>(this.base).then(r => r.data);

  /** Página server-side. Solo la usan las tablas con `serverPaginated=true`;
   *  requiere que el endpoint acepte ?page=&size=&search= y devuelva un Page. */
  findPage = (page: number, size: number, search = ''): Promise<Page<T>> =>
    axios.get<Page<T>>(
      `${this.base}?page=${page}&size=${size}${search ? `&search=${encodeURIComponent(search)}` : ''}`,
    ).then(r => r.data);

  findById = (id: string | number): Promise<T> =>
    axios.get<T>(`${this.base}/${id}`).then(r => r.data);

  create = (dto: Partial<T>): Promise<T> =>
    axios.post<T>(this.base, dto).then(r => r.data);

  update = (dto: T): Promise<T> =>
    axios.put<T>(`${this.base}/${this.getKey(dto)}`, dto).then(r => r.data);

  delete = (id: string | number): Promise<void> =>
    axios.delete(`${this.base}/${id}`).then(() => {});
}

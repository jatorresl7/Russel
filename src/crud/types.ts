import { TemplateResult } from 'lit';

export interface FormField {
  key: string;
  label: string;
  type?: 'text' | 'email' | 'number' | 'password' | 'textarea' | 'select' | 'checkbox';
  options?: Record<string, string>;
  required?: boolean;
  disabled?: boolean;
  zone?: 'top' | 'left' | 'right' | 'bottom';
  validator?: (value: any) => boolean;
  /** Renderizado completamente custom; se incluye un hidden input para que FormData lo recoja */
  renderer?: (value: string, onChange: (v: string) => void) => TemplateResult;
}

export interface KanbanColumn {
  key: string;
  label: string;
  headerClass: string;  // clases Tailwind para el header de la columna
  dotClass: string;     // clase Tailwind para el indicador de color
}

export interface Column<T> {
  key: string;                                  // soporta dot notation: 'user.name'
  label: string;
  renderer?: (item: T) => any;
  slice?: number;                               // truncar texto largo
}

import { customElement } from 'lit/decorators.js';
import { CrudForm } from '../../crud/crud-form';
import { t } from '../../i18n/t';
import { ConocimientoService, Memoria } from './conocimiento.service';

@customElement('conocimiento-form')
export class ConocimientoForm extends CrudForm<Memoria> {
  get prefix() { return 'conocimiento'; }
  service = new ConocimientoService();

  fields = () => [
    { key: 'texto', label: t('conocimiento.texto'), type: 'textarea' as const, required: true },
    { key: 'tipo', label: t('conocimiento.tipo'), type: 'select' as const,
      options: { hecho: t('conocimiento.hecho'), episodio: t('conocimiento.episodio') } },
  ];
}

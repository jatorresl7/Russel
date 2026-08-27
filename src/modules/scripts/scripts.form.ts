import { customElement } from 'lit/decorators.js';
import { CrudForm } from '../../crud/crud-form';
import { t } from '../../i18n/t';
import { ScriptsService, WorkScript } from './scripts.service';

@customElement('scripts-form')
export class ScriptsForm extends CrudForm<WorkScript> {
  get prefix() { return 'scripts'; }
  service = new ScriptsService();

  fields = () => [
    { key: 'name',     label: t('scripts.name'),     required: true },
    { key: 'title',    label: t('scripts.label'),    required: true },
    // El .sh vive en scripts/ con permisos 700; la DB guarda el nombre del
    // archivo, nunca el comando.
    { key: 'filename', label: t('scripts.filename'), required: true },
    { key: 'order',    label: t('scripts.order'),    type: 'number' as const, zone: 'left' as const },
    { key: 'enabled',  label: t('scripts.enabled'),  type: 'select' as const, zone: 'right' as const,
      options: { true: t('common.yes'), false: t('common.no') } },
  ];
}

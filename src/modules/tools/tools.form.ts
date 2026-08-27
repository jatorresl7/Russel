import { customElement } from 'lit/decorators.js';
import { CrudForm } from '../../crud/crud-form';
import { t } from '../../i18n/t';
import { ToolsService, Tool } from './tools.service';

@customElement('tools-form')
export class ToolsForm extends CrudForm<Tool> {
  get prefix() { return 'tools'; }
  service = new ToolsService();

  fields = () => [
    { key: 'name',        label: t('tools.name'),        required: true },
    { key: 'description', label: t('tools.description'), type: 'textarea' as const },
    { key: 'command',     label: t('tools.command'),     type: 'textarea' as const, required: true },
  ];
}

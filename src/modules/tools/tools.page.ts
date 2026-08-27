import { customElement } from 'lit/decorators.js';
import { CrudPage } from '../../crud/crud-page';
import { t } from '../../i18n/t';
import { Tool } from './tools.service';
import { ToolsTable } from './tools.table';
import { ToolsForm } from './tools.form';

@customElement('tools-page')
export class ToolsPage extends CrudPage<Tool> {
  get prefix() { return 'tools'; }
  get label()  { return t('tools.title'); }
  createTable = () => new ToolsTable();
  createForm  = () => new ToolsForm();
}

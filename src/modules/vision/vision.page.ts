import { LitElement, html, TemplateResult } from 'lit';
import { customElement } from 'lit/decorators.js';
import { t, subscribeI18n } from '../../i18n/t';
import './camara-panel';
import './control-stats';

@customElement('vision-page')
export class VisionPage extends LitElement {
  private _unsubI18n = subscribeI18n(this);

  createRenderRoot() { return this; }

  disconnectedCallback() {
    this._unsubI18n();
    super.disconnectedCallback();
  }

  render(): TemplateResult {
    return html`
      <h2 class="text-2xl font-semibold text-gray-900 mb-5">${t('vision.title')}</h2>
      <div class="max-w-4xl flex flex-col gap-4">
        <camara-panel></camara-panel>
        <control-stats></control-stats>
      </div>`;
  }
}

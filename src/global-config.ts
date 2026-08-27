export class GlobalConfig {
  private static instance: GlobalConfig;
  readonly apiUrl: string;

  private constructor() {
    this.apiUrl = (window as any).__APP_CONFIG__?.apiUrl ?? '/api/';
  }

  static getInstance(): GlobalConfig {
    if (!GlobalConfig.instance) GlobalConfig.instance = new GlobalConfig();
    return GlobalConfig.instance;
  }
}

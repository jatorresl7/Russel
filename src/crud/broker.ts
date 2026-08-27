type Subscriber = { element: HTMLElement; callback: (msg: any) => void };

export class MessageBroker {
  private static instance: MessageBroker;
  private subs: Map<string, Subscriber[]> = new Map();

  private constructor() {}

  static getInstance(): MessageBroker {
    if (!MessageBroker.instance) MessageBroker.instance = new MessageBroker();
    return MessageBroker.instance;
  }

  static publish(topic: string, detail: any = {}): void {
    const list = MessageBroker.getInstance().subs.get(topic) ?? [];
    list.forEach(({ callback }) => callback({ topic, detail }));
  }

  static subscribe(el: HTMLElement, topic: string, cb: (msg: any) => void): void {
    const inst = MessageBroker.getInstance();
    if (!inst.subs.has(topic)) inst.subs.set(topic, []);
    inst.subs.get(topic)!.push({ element: el, callback: cb });
  }

  static unsubscribeAll(el: HTMLElement): void {
    const inst = MessageBroker.getInstance();
    inst.subs.forEach((list, topic) =>
      inst.subs.set(topic, list.filter(s => s.element !== el))
    );
  }
}

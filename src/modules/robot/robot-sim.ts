import { LitElement, html, TemplateResult } from 'lit';
import { customElement, property } from 'lit/decorators.js';
import { Rueda } from './robot.service';

const ANCHO = 300;
const ALTO = 210;

/**
 * Dibuja lo que el robot HARÍA con las velocidades que tiene ahora.
 *
 * No es odometría: no hay encoders ni nada que diga dónde está de verdad. Se
 * integran las cuatro ruedas con la cinemática mecanum inversa y se mueve un
 * rectángulo. Sirve para una sola cosa, que es la que importa cuando estás
 * mirando la cámara: ver de un vistazo si los comandos que salen de visión
 * tienen sentido — si gira para el lado que debe, si avanza cuando debería.
 */
@customElement('robot-sim')
export class RobotSim extends LitElement {
  @property({ attribute: false }) wheels: Record<Rueda, number> | null = null;

  // Pose acumulada. Vive acá y no en el estado de Lit porque cambia 14 veces
  // por segundo y no hay nada que re-renderizar: se pinta sobre el canvas.
  private _x = ANCHO / 2;
  private _y = ALTO / 2;
  private _th = -Math.PI / 2;

  createRenderRoot() { return this; }

  updated() {
    if (this.wheels) this._dibujar(this.wheels);
  }

  private _dibujar(w: Record<Rueda, number>) {
    const cv = this.querySelector('canvas') as HTMLCanvasElement | null;
    const cx = cv?.getContext('2d');
    if (!cv || !cx) return;

    // Cinemática mecanum inversa: de las cuatro ruedas salen avance, deriva
    // lateral y giro.
    const vy = (w.fl + w.fr + w.rl + w.rr) / 4;
    const vx = (w.fl - w.fr - w.rl + w.rr) / 4;
    const om = (w.fl - w.fr + w.rl - w.rr) / 4;

    this._th += om * 0.06;
    this._x += (vy * Math.cos(this._th) - vx * Math.sin(this._th)) * 1.6;
    this._y += (vy * Math.sin(this._th) + vx * Math.cos(this._th)) * 1.6;
    // Se queda dentro del recuadro: es un indicador, no un mapa. Dejarlo salir
    // solo lograría perderlo de vista a los diez segundos.
    this._x = Math.max(20, Math.min(ANCHO - 20, this._x));
    this._y = Math.max(20, Math.min(ALTO - 20, this._y));

    cx.fillStyle = '#0d0f13';
    cx.fillRect(0, 0, ANCHO, ALTO);
    cx.strokeStyle = '#1e232c';
    for (let i = 0; i < ANCHO; i += 30) { cx.beginPath(); cx.moveTo(i, 0); cx.lineTo(i, ALTO); cx.stroke(); }
    for (let j = 0; j < ALTO; j += 30) { cx.beginPath(); cx.moveTo(0, j); cx.lineTo(ANCHO, j); cx.stroke(); }

    cx.save();
    cx.translate(this._x, this._y);
    cx.rotate(this._th);
    cx.fillStyle = '#4c9aff';
    cx.fillRect(-15, -11, 30, 22);
    // La punta blanca es el frente: sin ella un rectángulo girando no dice
    // hacia dónde mira.
    cx.fillStyle = '#e8e8ea';
    cx.beginPath(); cx.moveTo(15, 0); cx.lineTo(6, -6); cx.lineTo(6, 6); cx.closePath(); cx.fill();
    cx.fillStyle = '#11141a';
    ([[-11, -13], [7, -13], [-11, 9], [7, 9]] as const)
      .forEach(([x, y]) => cx.fillRect(x, y, 7, 4));
    cx.restore();
  }

  render(): TemplateResult {
    return html`<canvas width="${ANCHO}" height="${ALTO}"
                  class="w-full rounded-[var(--radius-control)] bg-black block"></canvas>`;
  }
}

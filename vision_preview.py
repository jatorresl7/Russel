#!/usr/bin/env python3
"""Preview de vision en ventana de escritorio (alternativa a /vision en el navegador).

  python3 vision_preview.py            # solo personas + control
  python3 vision_preview.py --all      # todas las clases COCO
  python3 vision_preview.py --seg      # mascaras de segmentacion

  q = salir     r = soltar el objetivo fijado
"""
import argparse
import time

import cv2

from app.services import vision_service as vs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cam", type=int, default=0)
    ap.add_argument("--all", action="store_true", help="detectar todas las clases")
    ap.add_argument("--seg", action="store_true", help="usar modelo de segmentacion")
    ap.add_argument("--conf", type=float, default=0.4)
    args = ap.parse_args()

    clases = None if args.all else [vs.PERSON_CLASS]

    cap = cv2.VideoCapture(args.cam)
    if not cap.isOpened():
        raise SystemExit(f"No pude abrir /dev/video{args.cam}")

    print("Cargando modelo (la primera vez lo descarga)...")
    vs.get_model(args.seg)
    print("Listo. q = salir, r = soltar objetivo")

    fps, t_prev = 0.0, time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            break

        frame = vs.process(frame, classes=clases, seg=args.seg, conf=args.conf, fps=fps)
        cv2.imshow("Jarvis - vision preview", frame)

        ahora = time.time()
        fps = 0.9 * fps + 0.1 / max(ahora - t_prev, 1e-6)
        t_prev = ahora

        k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k == ord("r"):
            vs.reset_target()
            print("objetivo soltado")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

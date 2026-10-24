"""Detección de dedos y control de cinco LED en Arduino UNO (D2..D6).

MediaPipe Hand Landmarker (21 landmarks). Ejecutar: python vision_mano.py
Opcional: python vision_mano.py --port /dev/cu.usbserial-21420
"""
import argparse
import math
import time
from pathlib import Path

import cv2
import mediapipe as mp
import serial
from serial.tools import list_ports

BASE = Path(__file__).resolve().parent
MODEL = BASE / "hand_landmarker.task"
NAMES = ["PULGAR", "INDICE", "MEDIO", "ANULAR", "MENIQUE"]
TIPS = [4, 8, 12, 16, 20]
JOINTS = [(2, 3, 4), (5, 6, 8), (9, 10, 12), (13, 14, 16), (17, 18, 20)]
EDGES = [(0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
         (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
         (13,17),(17,18),(18,19),(19,20),(0,17)]


def angle(a, b, c):
    u = (a.x-b.x, a.y-b.y)
    v = (c.x-b.x, c.y-b.y)
    denominator = math.hypot(*u) * math.hypot(*v)
    if denominator == 0:
        return 0
    cosine = max(-1, min(1, (u[0]*v[0] + u[1]*v[1])/denominator))
    return math.degrees(math.acos(cosine))


def fingers_up(points):
    states = []
    for i, (base, joint, tip) in enumerate(JOINTS):
        opened = angle(points[base], points[joint], points[tip]) > (150 if i == 0 else 155)
        if i > 0:
            d_tip = math.hypot(points[tip].x-points[base].x, points[tip].y-points[base].y)
            d_mid = math.hypot(points[joint].x-points[base].x, points[joint].y-points[base].y)
            opened = opened and d_tip > 1.35*d_mid
        states.append(opened)
    return states


def draw_hand(image, points, states):
    height, width = image.shape[:2]
    pixels = [(int(p.x*width), int(p.y*height)) for p in points]
    for a, b in EDGES:
        cv2.line(image, pixels[a], pixels[b], (255, 220, 0), 2, cv2.LINE_AA)
    for point in pixels:
        cv2.circle(image, point, 5, (255, 255, 255), -1)
        cv2.circle(image, point, 3, (255, 160, 0), -1)
    for i, tip in enumerate(TIPS):
        color = (0, 255, 100) if states[i] else (80, 80, 255)
        cv2.circle(image, pixels[tip], 12, color, 2)
        if states[i]:
            cv2.circle(image, pixels[tip], 5, color, -1)


def choose_port(explicit):
    if explicit:
        return explicit
    candidates = [p for p in list_ports.comports() if any(
        word in (p.device + " " + (p.description or "")).lower()
        for word in ("usbserial", "usbmodem", "arduino", "ch340", "wchusb", "ttyusb", "ttyacm"))]
    print("Puertos USB candidatos:", [p.device for p in candidates])
    if len(candidates) == 1:
        return candidates[0].device
    print("Indica --port para evitar elegir un dispositivo equivocado.")
    return None


def connect(port):
    if not port:
        print("Modo cámara sin Arduino. Usa --port para activar los LED.")
        return None
    try:
        board = serial.Serial(port, 115200, timeout=1)
        time.sleep(2)  # Arduino UNO puede reiniciarse al abrir el puerto
        board.write(bytes([0]))
        print("Arduino conectado:", port)
        return board
    except serial.SerialException as error:
        print("No se pudo abrir el puerto:", error)
        print("El reconocimiento de cámara continuará sin controlar LED.")
        return None


def main():
    parser = argparse.ArgumentParser(description="Control de 5 LED con gestos de mano")
    parser.add_argument("--port", help="Puerto serie: COM3, /dev/cu.usbserial-21420, /dev/ttyUSB0")
    parser.add_argument("--camera", type=int, default=0, help="Índice de cámara (por defecto 0)")
    args = parser.parse_args()
    if not MODEL.is_file():
        raise SystemExit("Falta hand_landmarker.task. Descárgalo como indica README.md")

    port = choose_port(args.port)
    board = connect(port)
    camera = cv2.VideoCapture(args.camera)
    if not camera.isOpened():
        if board:
            board.close()
        raise SystemExit("No se puede abrir la cámara. Revisa permisos o --camera 1")

    BaseOptions = mp.tasks.BaseOptions
    Vision = mp.tasks.vision
    options = Vision.HandLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL)),
        running_mode=Vision.RunningMode.VIDEO,
        num_hands=1,
        min_hand_detection_confidence=0.6,
        min_tracking_confidence=0.6,
    )
    start = time.monotonic()
    last_timestamp = -1
    last_mask = None
    last_sent = 0.0
    try:
        with Vision.HandLandmarker.create_from_options(options) as detector:
            while True:
                ok, frame = camera.read()
                if not ok:
                    break
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                timestamp = max(int((time.monotonic()-start)*1000), last_timestamp+1)
                last_timestamp = timestamp
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp)
                states = [False]*5
                if result.hand_landmarks:
                    points = result.hand_landmarks[0]
                    states = fingers_up(points)
                    draw_hand(frame, points, states)
                mask = sum(1 << i for i, state in enumerate(states) if state)
                now = time.monotonic()
                # Reenvío cada segundo: el watchdog del Arduino evita LED pegados.
                if board is not None and (mask != last_mask or now-last_sent >= 1.0):
                    try:
                        board.write(bytes([mask]))
                        last_sent = now
                    except serial.SerialException as error:
                        print("Comunicación serie interrumpida:", error)
                        try:
                            board.close()
                        except Exception:
                            pass
                        board = None
                last_mask = mask
                cv2.rectangle(frame, (10, 10), (365, 240), (18, 23, 35), -1)
                cv2.putText(frame, "VISION DE MANO + ARDUINO", (20, 37),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.60, (0, 220, 255), 2)
                cv2.putText(frame, f"DEDOS: {sum(states)}", (20, 68),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
                for i, name in enumerate(NAMES):
                    status = "ON" if states[i] else "OFF"
                    color = (0, 255, 100) if states[i] else (160, 160, 160)
                    cv2.putText(frame, f"{name}: D{i+2} {status}", (20, 98+i*26),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
                cv2.putText(frame, "ARDUINO: CONECTADO" if board else "ARDUINO: SIN CONEXION",
                            (15, frame.shape[0]-15), cv2.FONT_HERSHEY_SIMPLEX,
                            0.52, (0, 255, 100) if board else (0, 140, 255), 2)
                cv2.imshow("Vision artificial - Q para salir", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    finally:
        camera.release()
        cv2.destroyAllWindows()
        if board:
            try:
                board.write(bytes([0]))
                board.close()
            except serial.SerialException:
                pass


if __name__ == "__main__":
    main()

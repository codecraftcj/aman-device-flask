import serial
import cv2
import numpy as np
from flask import Flask, Response
import time

# Flask App
app = Flask(__name__)

# Set correct serial port for Raspberry Pi
SERIAL_PORT = "/dev/ttyUSB0"  # Change to "/dev/serial0" if using GPIO UART
BAUD_RATE = 115200

# Open Serial Connection to ESP32-CAM
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"Connected to {SERIAL_PORT}")
except serial.SerialException as e:
    print(f"Error: Could not open serial port {SERIAL_PORT}. {e}")
    exit(1)

def read_frame():
    """Reads a single JPEG frame from the serial stream."""
    buffer = bytearray()
    is_receiving = False  # Flag to check if we are inside a valid frame
    start_time = time.time()

    while True:
        byte = ser.read()
        if not byte:
            continue  # Ignore empty reads

        buffer.append(byte[0])

        # Detect Start of JPEG (0xFFD8)
        if len(buffer) >= 2 and buffer[-2] == 0xFF and buffer[-1] == 0xD8:
            is_receiving = True  # Start receiving a frame
            buffer = bytearray([0xFF, 0xD8])  # Reset buffer with JPEG start

        # Detect End of JPEG (0xFFD9)
        if is_receiving and len(buffer) > 2 and buffer[-2] == 0xFF and buffer[-1] == 0xD9:
            return np.asarray(buffer, dtype=np.uint8)  # Return completed frame

        # Timeout if frame takes too long
        if time.time() - start_time > 2:  # 2-second timeout
            print("Frame timeout, restarting capture...")
            return None

def generate_frames():
    """Flask generator function to serve the raw video stream."""
    while True:
        frame_data = read_frame()
        if frame_data is None:
            continue

        img = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
        if img is not None:
            # Encode frame as JPEG
            _, buffer = cv2.imencode(".jpg", img)
            frame = buffer.tobytes()

            # Yield frame data as multipart response for MJPEG stream
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")

@app.route("/video_feed")
def video_feed():
    """Flask route to serve the video feed."""
    return Response(generate_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8085, debug=False, threaded=True)

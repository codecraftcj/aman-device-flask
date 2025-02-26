import serial
import requests
import json
import threading
import socket
import time
import random
import serial.tools.list_ports
from flask import Flask, request, jsonify, Response
from sqlalchemy.orm import sessionmaker
from repository.database import db_session, init_db
from models.models import JobQueue
import cv2
import os
# Configuration
SERIAL_PORT_1 = "/dev/ttyACM0"  # First Arduino (receiving data)
SERIAL_PORT_2 = "/dev/ttyACM1"  # Second Arduino (controlling actuators)
BAUD_RATE = 9600
DEVICE_ID = "EMULATOR-001"  # Static ID for the emulator
TESTING = True  # Set this to True to enable testing mode
hostname = "simplegon-desktop"  # Get the device hostname

TERMINAL_API_URL = f"http://{hostname}.local:8080"
LOCAL_API_URL = "http://localhost:8082"
app = Flask(__name__)

# ========== CAMERA DETECTION ==========
def get_first_available_camera():
    """Find the first available camera on Ubuntu using v4l2."""
    try:
        output = os.popen("v4l2-ctl --list-devices").read()
        print(output)
        target_camera_section = output.split("HD Pro Webcam C920")[-1]
        lines = target_camera_section.split("\n")
        
        video_devices = [line.strip() for line in lines if "/dev/video" in line]
       
        if video_devices:
            print("VIDEO DEVICES")
            print(video_devices[0])
            return video_devices[0]  # Return first available camera device
    except Exception as e:
        print(f"❌ Error finding camera: {e}")

    return "/dev/video0"  # Fallback to /dev/video0

camera_device = get_first_available_camera()
print(f"FOUND CAMERA AT : {camera_device}")
camera = cv2.VideoCapture(camera_device)
print(camera.isOpened())
if camera.isOpened():
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    camera.set(cv2.CAP_PROP_FPS, 30)
    print(f"🎥 Using camera device: {camera_device}")
else:
    camera = None
    print("❌ No camera found!")

def generate_frames():
    """Continuously capture frames from the camera."""
    while camera and camera.isOpened():
        success, frame = camera.read()
        if not success:
            break
        else:
            _, buffer = cv2.imencode('.jpg', frame)
            frame = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

# ========== SERIAL DEVICE DETECTION ==========
def identify_arduino_ports():
    """Identify which serial port belongs to Uno R3 (actuators) and which to ATmega (sensors)."""
    ports = serial.tools.list_ports.comports()
    uno_port, atmega_port = None, None

    for port in ports:
        print("---------")
        print(port)
        print(port.device)
    
        device_name = port.device
        vid_pid = (port.vid, port.pid)
        print(vid_pid)
        # Arduino Uno R3 (Common VID:PID pairs)
        if vid_pid in [(0x2341, 0x0043), (0x2341, 0x0001), (0x2A03, 0x0043),(0x2341,0x0042)]:
            if(atmega_port is None):
                atmega_port = device_name
                print(f"✅ Found ATmega Arduino (Sensors) at {atmega_port}")
            else:
                uno_port = device_name
                print(f"✅ Found Arduino Uno R3 (Actuators) at {uno_port}")

        # ATmega-based Arduino (Common VID:PID pairs)
        elif vid_pid in [(0x2341, 0x003F), (0x2341, 0x0036), (0x1A86, 0x7523)]:
            uno_port = device_name
            print(f"✅ Found Arduino Uno R3 (Actuators) at {uno_port}")

    return uno_port, atmega_port

# if(TESTING == False):
#     SERIAL_PORT_1,SERIAL_PORT_2 = identify_arduino_ports()  # Uno R3 (Actuators) → SERIAL_PORT_2, ATmega (Sensors) → SERIAL_PORT_1

# if SERIAL_PORT_1 is None or SERIAL_PORT_2 is None:
#     print("⚠️ Warning: Could not identify both Arduino devices!")



class DeviceEmulator:
    def __init__(self, serial_port_1, serial_port_2, baud_rate, device_id, terminal_api_url, testing=False):
        self.serial_port_1 = serial_port_1
        self.serial_port_2 = serial_port_2
        self.baud_rate = baud_rate
        self.device_id = device_id
        self.terminal_api_url = terminal_api_url
        self.testing = testing
        self.serial_conn_1 = None
        self.serial_conn_2 = None
        self.running = False
        self.is_registered=False
        self.device_hostname = self.get_device_hostname()
        self.stop_event = threading.Event()
        self.handle_jobs_thread = None
        self.read_serial_data_thread = None
        self.threads_started = False
        init_db()
        
    def connect_serial(self):
        """Establish serial connections."""
        if not self.testing:
            try:
                self.serial_conn_1 = serial.Serial(self.serial_port_1, self.baud_rate, timeout=20)
                print(f"✅ Connected to serial port 1: {self.serial_port_1}")

            except serial.SerialException as e:
                print(f"❌ Error connecting to serial 1: {e}")
                self.serial_conn_1 = None

            try:
                self.serial_conn_2 = serial.Serial(self.serial_port_2, self.baud_rate, timeout=20)
                print(f"✅ Connected to serial port 2: {self.serial_port_2}")
            except serial.SerialException as e:
                print(f"❌ Error connecting to serial 2: {e}")
        else:
            print("🛠️ Running in TESTING mode: No serial connections established.")

    def read_serial_data(self):
        """Continuously reads serial data and forwards it to both local and cloud APIs."""
        self.running = True
        while self.running and self.is_registered:
            if self.testing:
                # Generate dummy data every second
                # required_fields = ['device_id', 'temperature', 'turbidity', 'ph_level', 'hydrogen_sulfide_level']
                sensor_data = {
                    "device_id": self.device_id,
                    "temperature": round(random.uniform(20, 30), 2),
                    "turbidity": round(random.uniform(1, 10), 2),
                    "ph_level": round(random.uniform(6, 9), 2),
                    "hydrogen_sulfide_level":round(random.uniform(2, 30), 2)
                }
                print(f"📥 [TEST MODE] Generated: {sensor_data}")
                self.forward_to_local_api(sensor_data)
                time.sleep(5)
            else:
                try:
                    if self.serial_conn_1 and self.serial_conn_1.in_waiting > 0:
                        raw_line = self.serial_conn_1.readline().decode('utf-8').strip()
                        print(f"📥 Received: {raw_line}")
                        
                        try:
                            raw_json = json.loads(raw_line)
                            sensor_data = {
                                "device_id": self.device_id,
                                "temperature": raw_json["temperature"],
                                "turbidity": raw_json["turbidity"],
                                "ph_level":  raw_json["ph_level"],
                                "hydrogen_sulfide_level": raw_json["hydrogen_sulfide_level"]
                            }

                            self.forward_to_local_api(sensor_data)
                        except json.JSONDecodeError:
                            print(f"❌ Error: Invalid JSON from serial - {raw_line}")
                except Exception as e:
                    print(f"❌ Error reading serial data: {e}")
                time.sleep(30)

    def forward_to_local_api(self, sensor_data):
        """Sends water parameters to the device terminal at `http://{self.terminal_api_url}:8080/set_water_parameters`."""
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(f"{self.terminal_api_url}/set-water-parameters", json=sensor_data, headers=headers, timeout=3)

            if response.status_code == 200 or response.status_code == 201:
                print(f"✅ Sent data to device terminal: {sensor_data} - Response: {response.json()}")
                time.sleep(5)
            else:
                print(f"⚠️ Failed to send data to terminal. HTTP {response.status_code}: {response.text}")
        except requests.RequestException as e:
            print(f"❌ Error sending to terminal: {e}")

    def send_command(self, command):
        """Writes the command to the database."""
        task_name = command["job_name"]
        job = JobQueue(device_id=self.device_id, task_name=task_name, status="pending")
        db_session.add(job)
        db_session.commit()
        print({"status": "queued", "command": command})
        return {"status": "queued", "command": command}

    def handle_jobs(self):
        """Fetches and executes jobs from the database."""
        print("HANDLING JOBS")
        while self.running and self.is_registered:
            session = db_session()
            jobs = session.query(JobQueue).filter_by(status="pending", device_id=self.device_id).all()
            for job in jobs:
                print("TEST")
                print(len(jobs))
                if self.testing:
                    print(f"🛠️ [TEST MODE] Job executed: {job.task_name}")
                else:
                    if job.task_name == "small open":
                        print("SMALL OPEN HANDLED")
                        self.serial_conn_2.write(b's')
                    elif job.task_name == "half open":
                        print("HALF OPEN HANDLED")
                        self.serial_conn_2.write(b'm')
                    elif job.task_name == "full open":
                        print("LARGE OPEN HANDLED")
                        self.serial_conn_2.write(b'l')
                    print(self.serial_conn_2)
                job.status = "completed"
                session.commit()
            session.close()

            
    def start(self):
        """Starts the serial reading thread."""
        self.stop_event.clear()
        response_status_code = 201
        while(response_status_code != 200):
            response_status_code = self.announce_to_terminal()
            time.sleep(2)
        self.connect_serial()
        self.running = True

    def start_threads(self):
        self.handle_jobs_thread = threading.Thread(target=self.handle_jobs, daemon=True)
        self.read_serial_data_thread = threading.Thread(target=self.read_serial_data, daemon=True)
        self.handle_jobs_thread.start()
        self.read_serial_data_thread.start()
        self.threads_started = True
        print("STARTING THREADS")
    def stop_threads(self):
        self.stop_event.set()
        if self.handle_jobs_thread:
            self.handle_jobs_thread.join()
        if self.read_serial_data_thread:
            self.read_serial_data_thread.join()
        self.handle_jobs_thread = None
        self.read_serial_data_thread = None
        self.threads_started = False
        print("STOPPING THREADS")
    def set_is_registered(self,bool):
        self.is_registered = bool
        # if(self.is_registered):
        #     self.start_threads()
        if(self.is_registered == True and self.threads_started == False ):
            self.start_threads()
        elif(self.is_registered == False and self.threads_started == True):
            self.stop_event.set()
            
    def stop(self):
        """Stops the emulator."""
        self.running = False
        if self.serial_conn_1:
            self.serial_conn_1.close()
        if self.serial_conn_2:
            self.serial_conn_2.close()
        print("🚪 Serial connections closed.")

    def get_device_hostname(self):
        """Get the local IP address of the device."""
        try:
            device_hostname = socket.gethostname()
            
            return device_hostname
        except Exception as e:
            print(f"❌ Error getting local IP: {e}")
            return "127.0.0.1"

    def announce_to_terminal(self):
        """Announces the device to the terminal as available."""
        try:
            url = f"{self.terminal_api_url}/register_device"
            
            payload = {
                "device_id": self.device_id,
                "device_hostname": self.device_hostname,
                "status": "available"
            }
            headers = {'Content-Type': 'application/json'}
            print("API TERMINAL URL"+ self.terminal_api_url)
            response = requests.post(url, json=payload, headers=headers, timeout=5)
            
            if response.status_code == 200:
                print(f"✅ Announced to terminal: {payload}")
                data = json.loads(response.content)
            else:
                print(f"⚠️ Failed to announce. HTTP {response.status_code}: {response.text}")
            return response.status_code
        except requests.RequestException as e:
            print(f"❌ Error announcing to terminal: {e}")
            time.sleep(1)
            return "Failed"
   
# Initialize the emulator
device = DeviceEmulator(SERIAL_PORT_1, SERIAL_PORT_2, BAUD_RATE, DEVICE_ID, TERMINAL_API_URL, testing=TESTING)
device.start()

@app.route('/register', methods=['POST'])
def register_device():
    device.set_is_registered(True)
    return jsonify({"status": "success", "message": "Device registered successfully."})

@app.route('/unregister', methods=['POST'])
def unregister_device():
    device.set_is_registered(False)
    return jsonify({"status": "success", "message": "Device unregistered successfully."})

@app.route('/send_command', methods=['POST'])
def send_command():
    """API endpoint for the terminal to send commands to the emulator."""
    data = request.json
    print(data)
    if not data:
        return jsonify({"error": "Invalid request, JSON required"}), 400
    response = device.send_command(data)
    return jsonify(response)

@app.route('/device_info', methods=['GET'])
def get_device_info():
    """Returns device information including its static ID."""
    return jsonify({"device_id": device.device_id, "status": "running" if device.running else "stopped"})

@app.route('/')
def home():
    return("HELLO THIS IS THE AMAN DEVICE")

@app.route("/get-jobs", methods=["GET"])
def get_jobs():
    try:
        jobs = db_session.query(JobQueue).all()
        serialized_jobs = [
            {
                "id": job.id,
                "job_name": job.task_name,
                "status": job.status,
                "issued_at": job.issued_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            for job in jobs
        ]
        return jsonify(serialized_jobs), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/update-job/<int:job_id>", methods=["PUT"])
def update_job(job_id):
    try:
        data = request.get_json()
        job = db_session.query(JobQueue).filter(JobQueue.id == job_id).first()

        if job is None:
            return jsonify({"message": "Job not found"}), 404

        if "job_name" in data:
            job.job_name = data['job_name']
        if "status" in data:
            job.status = data['status']

        db_session.commit()
        return jsonify({"message": "Job updated successfully"}), 200
    except Exception as e:
        db_session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db_session.close()
        
@app.route('/camera')
def video_feed():
    """Stream the camera feed as an MJPEG stream."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":

    app.run(host="0.0.0.0", port=8082, debug=False)


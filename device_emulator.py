import serial
import requests
import json
import threading
import socket
import time
import random
from flask import Flask, request, jsonify
from sqlalchemy.orm import sessionmaker
from repository.database import db_session, init_db
from models.models import JobQueue

# Configuration
SERIAL_PORT_1 = "COM4"  # First Arduino (receiving data)
SERIAL_PORT_2 = "COM5"  # Second Arduino (controlling actuators)
BAUD_RATE = 9600
DEVICE_ID = "EMULATOR-001"  # Static ID for the emulator
TESTING = True  # Set this to True to enable testing mode
hostname = "simplegon-desktop"  # Get the device hostname

TERMINAL_API_URL = f"http://{hostname}.local:8080"
LOCAL_API_URL = "http://localhost:8082"
app = Flask(__name__)

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
        self.local_ip = self.get_local_ip()
        self.stop_event = threading.Event()
        self.handle_jobs_thread = None
        self.read_serial_data_thread = None
        init_db()
        
    def connect_serial(self):
        """Establish serial connections."""
        if not self.testing:
            try:
                self.serial_conn_1 = serial.Serial(self.serial_port_1, self.baud_rate, timeout=1)
                print(f"✅ Connected to serial port 1: {self.serial_port_1}")
            except serial.SerialException as e:
                print(f"❌ Error connecting to serial 1: {e}")
                self.serial_conn_1 = None

            try:
                self.serial_conn_2 = serial.Serial(self.serial_port_2, self.baud_rate, timeout=1)
                print(f"✅ Connected to serial port 2: {self.serial_port_2}")
            except serial.SerialException as e:
                print(f"❌ Error connecting to serial 2: {e}")
                self.serial_conn_2 = None
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
                time.sleep(1)
            else:
                try:
                    if self.serial_conn_1 and self.serial_conn_1.in_waiting > 0:
                        raw_line = self.serial_conn_1.readline().decode('utf-8').strip()
                        print(f"📥 Received: {raw_line}")
                        
                        try:
                            sensor_data = json.loads(raw_line)
                            sensor_data["device_id"] = self.device_id  # Attach device ID
                            self.forward_to_local_api(sensor_data)
                        except json.JSONDecodeError:
                            print(f"❌ Error: Invalid JSON from serial - {raw_line}")
                except Exception as e:
                    print(f"❌ Error reading serial data: {e}")

    def forward_to_local_api(self, sensor_data):
        """Sends water parameters to the device terminal at `http://{self.terminal_api_url}:8080/set_water_parameters`."""
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(f"{self.terminal_api_url}/set-water-parameters", json=sensor_data, headers=headers, timeout=3)

            if response.status_code == 200 or response.status_code == 201:
                print(f"✅ Sent data to device terminal: {sensor_data} - Response: {response.json()}")
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
        return {"status": "queued", "command": command}

    def handle_jobs(self):
        """Fetches and executes jobs from the database."""
        while self.running and self.is_registered:
            session = db_session()
            jobs = session.query(JobQueue).filter_by(status="pending", device_id=self.device_id).all()
            for job in jobs:
                if self.testing:
                    print(f"🛠️ [TEST MODE] Job executed: {job.task_name}")
                else:
                    if job.task_name == "extend_motors":
                        self.serial_conn_2.write(b'o')
                    elif job.task_name == "retract_motors":
                        self.serial_conn_2.write(b'c')
                job.status = "completed"
                time.sleep(1.5)
                session.commit()
            session.close()
            time.sleep(1)
            
    def start(self):
        """Starts the serial reading thread."""
        self.stop_event.clear()
        response_status_code = self.announce_to_terminal()
        while(response_status_code != 200):
            response_status_code = self.announce_to_terminal()
        self.connect_serial()
        self.running = True

        
      
    def set_is_registered(self,bool):
        self.is_registered = bool
        if(self.is_registered == True):
            self.handle_jobs_thread = threading.Thread(target=self.handle_jobs, daemon=True)
            self.read_serial_data_thread = threading.Thread(target=self.read_serial_data, daemon=True)
            self.handle_jobs_thread.start()
            self.read_serial_data_thread.start()
        else:
            print("STOPPING THREADS")
            self.stop_event.set()
            if self.handle_jobs_thread:
                self.handle_jobs_thread.join()
            if self.read_serial_data_thread:
                self.read_serial_data_thread.join()
            self.handle_jobs_thread = None
            self.read_serial_data_thread = None
            
    def stop(self):
        """Stops the emulator."""
        self.running = False
        if self.serial_conn_1:
            self.serial_conn_1.close()
        if self.serial_conn_2:
            self.serial_conn_2.close()
        print("🚪 Serial connections closed.")

    def get_local_ip(self):
        """Get the local IP address of the device."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))  # Connect to external server
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception as e:
            print(f"❌ Error getting local IP: {e}")
            return "127.0.0.1"

    def announce_to_terminal(self):
        """Announces the device to the terminal as available."""
        try:
            url = f"{self.terminal_api_url}/register_device"
            payload = {
                "device_id": self.device_id,
                "local_ip": self.local_ip,
                "status": "available"
            }
            headers = {'Content-Type': 'application/json'}
            response = requests.post(url, json=payload, headers=headers, timeout=5)

            if response.status_code == 200:
                print(f"✅ Announced to terminal: {payload}")
                data = json.loads(response.content)
                message = data["message"]
                if "Device is already registered in the system" in message:
                    self.set_is_registered(True)
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
if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=8082, debug=True)
    except KeyboardInterrupt:
        device.stop()
        print("Shutting down...")

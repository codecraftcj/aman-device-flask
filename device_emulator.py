import serial
import requests
import json
import threading
import socket
from flask import Flask, request, jsonify
import time
# Configuration
SERIAL_PORT = "COM4"  # Change based on your system (e.g., "/dev/ttyUSB0" for Linux)
BAUD_RATE = 9600
CLOUD_API_URL = "https://amanrest-925084270691.asia-east2.run.app/set_water_parameters"
LOCAL_API_URL = "http://localhost:8080/set_water_parameters"  # Terminal endpoint
DEVICE_ID = "EMULATOR-001"  # Static ID for the emulator

hostname = "DESKTOP-FB8D1SN" # Get the device hostname

TERMINAL_API_URL = f"http://{hostname}.local:8080" 
app = Flask(__name__)

class DeviceEmulator:
    def __init__(self, serial_port, baud_rate, cloud_api_url, local_api_url, device_id,terminal_api_url):
        self.serial_port = serial_port
        self.baud_rate = baud_rate
        self.cloud_api_url = cloud_api_url
        self.local_api_url = local_api_url
        self.device_id = device_id
        self.serial_conn = None
        self.running = False
        self.terminal_api_url = terminal_api_url
        self.local_ip = self.get_local_ip()
    def connect_serial(self):
        """Establish serial connection."""
        try:
            self.serial_conn = serial.Serial(self.serial_port, self.baud_rate, timeout=1)
            print(f"✅ Connected to serial port: {self.serial_port}")
        except serial.SerialException as e:
            print(f"❌ Error connecting to serial: {e}")
            self.serial_conn = None

    def read_serial_data(self):
        """Continuously reads serial data and forwards it to both local and cloud APIs."""
        self.running = True
        while self.running:
            try:
                if self.serial_conn and self.serial_conn.in_waiting > 0:
                    raw_line = self.serial_conn.readline().decode('utf-8').strip()
                    print(f"📥 Received: {raw_line}")

                    # Parse JSON data from Serial
                    try:
                        sensor_data = json.loads(raw_line)
                        sensor_data["device_id"] = self.device_id  # Attach device ID

                        # Forward to the **device terminal** (localhost:8080)
                        self.forward_to_local_api(sensor_data)

                        # Forward to the **cloud API** (Google Cloud)
                        self.forward_to_cloud_api(sensor_data)

                    except json.JSONDecodeError:
                        print(f"❌ Error: Invalid JSON from serial - {raw_line}")

            except Exception as e:
                print(f"❌ Error reading serial data: {e}")

    def forward_to_local_api(self, sensor_data):
        """Sends water parameters to the device terminal at `http://localhost:8080/set_water_parameters`."""
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(self.local_api_url, json=sensor_data, headers=headers, timeout=3)

            if response.status_code == 200:
                print(f"✅ Sent data to device terminal: {sensor_data} - Response: {response.json()}")
            else:
                print(f"⚠️ Failed to send data to terminal. HTTP {response.status_code}: {response.text}")
        except requests.RequestException as e:
            print(f"❌ Error sending to terminal: {e}")

    def forward_to_cloud_api(self, sensor_data):
        """Sends water parameters to the cloud API."""
        try:
            headers = {'Content-Type': 'application/json'}
            response = requests.post(self.cloud_api_url, json=sensor_data, headers=headers, timeout=3)

            if response.status_code == 200:
                print(f"✅ Sent data to cloud API: {sensor_data} - Response: {response.json()}")
            else:
                print(f"⚠️ Failed to send data to cloud API. HTTP {response.status_code}: {response.text}")
        except requests.RequestException as e:
            print(f"❌ Error sending to cloud API: {e}")

    def send_command(self, command):
        """Sends a command to the serial device."""
        if self.serial_conn and self.serial_conn.is_open:
            command_json = json.dumps(command) + "\n"
            self.serial_conn.write(command_json.encode('utf-8'))
            return {"status": "sent", "command": command}
        return {"status": "failed", "error": "Serial connection not available"}

    def start(self):
        """Starts the serial reading thread."""
        response_status_code = self.announce_to_terminal()
        while(response_status_code != 200):
            response_status_code = self.announce_to_terminal()
        self.connect_serial()
        thread = threading.Thread(target=self.read_serial_data, daemon=True)
        thread.start()

    def stop(self):
        """Stops the emulator."""
        self.running = False
        if self.serial_conn:
            self.serial_conn.close()
            print("🚪 Serial connection closed.")

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
                
            else:
                print(f"⚠️ Failed to announce. HTTP {response.status_code}: {response.text}")
            return response.status_code
        except requests.RequestException as e:
            print(f"❌ Error announcing to terminal: {e}")
            return "Failed"

# Initialize the emulator
device = DeviceEmulator(SERIAL_PORT, BAUD_RATE, CLOUD_API_URL, LOCAL_API_URL, DEVICE_ID, TERMINAL_API_URL)
device.start()

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
if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=8082, debug=True)
    except KeyboardInterrupt:
        device.stop()
        print("Shutting down...")

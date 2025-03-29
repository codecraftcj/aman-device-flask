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
from models.models import JobQueue, FeedingSchedule
import cv2
import os
import schedule
from datetime import datetime, timezone

import threading
import sys
import os

def terminate_program():
    print("⏳ Exiting program after 3 minutes...")
    os._exit(0)  # Forcefully exit the script

# Configuration
SERIAL_PORT_1 = "/dev/ttyACM1"  # First Arduino (receiving data)
SERIAL_PORT_2 = "/dev/ttyACM0"  # Second Arduino (controlling actuators)
BAUD_RATE = 9600
DEVICE_ID = "EMULATOR-001"  # Static ID for the emulator
TESTING = False  # Set this to True to enable testing mode

hostname = "simplegon-desktop"  # Get the device hostname

TERMINAL_API_URL = f"http://{hostname}.local:8080"
if(TESTING):
    TERMINAL_API_URL = f"http://localhost:8080"
LOCAL_API_URL = "http://localhost:8082"

app = Flask(__name__)

# ========== CAMERA DETECTION ==========
def get_first_available_camera():
    """Find the first available camera on Ubuntu using v4l2."""
    try:
        output = os.popen("v4l2-ctl --list-devices").read()
        print(output)
        target_camera_section = output.split("WebCamera")[-1]
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

def validate_schedule(schedule):
    """Validate the structure of the feeding schedule."""
    required_keys = {"habit", "start_time", "end_time"}
    if not all(key in schedule for key in required_keys):
        return False

    habit = schedule.get("habit", {})
    if not isinstance(habit, dict) or "minute_interval" not in habit or "days" not in habit:
        return False
    
    if not isinstance(habit["minute_interval"], int) or habit["minute_interval"] <= 0:
        return False
    
    days = habit.get("days", {})
    if not isinstance(days, dict) or not all(isinstance(v, bool) for v in days.values()):
        return False
    
    if not isinstance(schedule["start_time"], str) or not isinstance(schedule["end_time"], str):
        return False

    return True


def get_current_time():
    """Returns the current time and timezone."""
    return datetime.now(timezone.utc).astimezone()

def is_within_time_range(start_time, end_time):
    """Check if the current time is within the feeding schedule."""
    current_time = get_current_time().time()
    return start_time <= current_time <= end_time
class FeedingScheduleManager:
    def __init__(self):
        self.running = True
        self.schedule_thread = threading.Thread(target=self.run_schedule_loop, daemon=True)
        self.update_thread = threading.Thread(target=self.check_and_update_schedule, daemon=True)
        self.schedule_thread.start()
        self.update_thread.start()

    def run_schedule_loop(self):
        """Continuously check and run scheduled jobs."""
        while self.running:
            schedule.run_pending()
            today = datetime.today().strftime('%A')
            # print(schedule.get_jobs(tag=today))
            time.sleep(1)  # Reduced sleep for better real-time execution

    def check_and_update_schedule(self):
        """Fetch feeding schedule from the database and update jobs accordingly."""
        while self.running:
            with db_session() as session:
                schedule_entry = session.query(FeedingSchedule).first()

                if schedule_entry:
                    schedule_data = schedule_entry.schedule
                    if validate_schedule(schedule_data):
                        self.update_cron_jobs(schedule_data)

            time.sleep(300)  # Check for updates every minute

    def update_cron_jobs(self, schedule_data):
        """Updates the cron jobs based on the provided feeding schedule."""
        habit = schedule_data["habit"]
        minute_interval = habit["minute_interval"]
        active_days = [day for day, is_active in habit["days"].items() if is_active]
        start_time = datetime.strptime(schedule_data["start_time"], "%I:%M %p").time()
        end_time = datetime.strptime(schedule_data["end_time"], "%I:%M %p").time()

        # Clear existing jobs before rescheduling
        schedule.clear()
        current_time_info = get_current_time()
        print(f"🕒 Current system time: {current_time_info.strftime('%Y-%m-%d %H:%M:%S %Z')}")

        #@DEMO: scheduled every 10 seconds to showcase scheduler
        #schedule.every(10).seconds.do(self.inspect_runs)

        for day in active_days:
            today = datetime.today().strftime('%A')
            if day == today:
                job = schedule.every(minute_interval).minutes.do(self.trigger_feeding_job, start_time=start_time, end_time=end_time)
                job.tag(day)
                print(f"✅ Scheduled feeding every {minute_interval} minutes on {day} from {start_time} to {end_time} (Timezone: {current_time_info.strftime('%Z')})")
    def inspect_runs(self):
        print("HELLO IM RUNNING")
        with db_session() as session:
                job = JobQueue(device_id=DEVICE_ID, task_name="small open", status="pending")
                session.add(job)
                session.commit()
            
        print("✅ Feeding job scheduled")
    def trigger_feeding_job(self, start_time, end_time):
        """Triggers a feeding job if within schedule."""
        if is_within_time_range(start_time, end_time):
            print("✅ Adding feeding job to queue")

            with db_session() as session:
                job = JobQueue(device_id=DEVICE_ID, task_name="small open", status="pending")
                session.add(job)
                session.commit()
            
            print("✅ Feeding job scheduled")
        else:
            print("⏳ Feeding skipped, outside scheduled time range")

# Start the scheduler
feeding_manager = FeedingScheduleManager()

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
            # if True:
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
                time.sleep(2)
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

@app.route('/feeding-schedule', methods=['POST'])
def create_or_update_feeding_schedule():
    try:
        data = request.get_json()
        schedule = data.get("schedule")

        if not schedule or not validate_schedule(schedule):
            return jsonify({"error": "Invalid schedule format"}), 400

        feeding_schedule = db_session.query(FeedingSchedule).first()
        
        if feeding_schedule:
            feeding_schedule.schedule = schedule  # Update existing schedule
        else:
            feeding_schedule = FeedingSchedule(schedule=schedule)
            db_session.add(feeding_schedule)

        db_session.commit()
        return jsonify({"message": "Feeding schedule updated successfully", "schedule_id": feeding_schedule.id}), 200
    except Exception as e:
        db_session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db_session.close()

@app.route('/feeding-schedule', methods=['GET'])
def get_feeding_schedule():
    try:
        schedule = db_session.query(FeedingSchedule).first()
        
        if not schedule:
            return jsonify({"message": "No schedule found"}), 404
        
        return jsonify({
            "id": schedule.id,
            "schedule": schedule.schedule,
            "last_updated": schedule.last_updated.strftime('%Y-%m-%d %H:%M:%S')
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        db_session.close()

@app.route('/feeding-schedule', methods=['DELETE'])
def delete_feeding_schedule():
    try:
        schedule = db_session.query(FeedingSchedule).first()

        if not schedule:
            return jsonify({"message": "Schedule not found"}), 404

        db_session.delete(schedule)
        db_session.commit()
        return jsonify({"message": "Feeding schedule deleted successfully"}), 200
    except Exception as e:
        db_session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        db_session.close()
        
if __name__ == "__main__":

    app.run(host="0.0.0.0", port=8082, debug=False)
    # Schedule program termination after 3 minutes (180 seconds)
    # shutdown_timer = threading.Timer(30, terminate_program)
    # shutdown_timer.start()


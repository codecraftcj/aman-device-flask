import serial
import time
import requests
import json

# Set up serial communication with Arduino
ser = serial.Serial('COM3', 9600, timeout=1)

time.sleep(2)  # Wait for the serial connection to initialize

API_ENDPOINT = "https://amanrest-925084270691.asia-east2.run.app"  # Replace with your actual API endpoint

# Function to get jobs from the queue
def get_job():
    try:
        response = requests.get(f"{API_ENDPOINT}/get-jobs")  # Assuming a GET request to fetch jobs
        if response.status_code == 200:
            job_data = response.json()
            for job in job_data:
                if not job['is_completed'] and job['job_name'] in ['extend_motors', 'retract_motors']:
                    return job
    except requests.exceptions.RequestException as e:
        print(f"Error fetching job: {e}")
    return None

# Function to report job completion to the API
def report_job_completion(job_id, status):
    try:
        payload = {
            "is_completed": status == "completed"
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.put(f"{API_ENDPOINT}/update-job/{job_id}", data=json.dumps(payload), headers=headers)  # Assuming a PUT request to report completion
        if response.status_code == 200:
            print(f"Successfully reported job {job_id} as {status}")
        else:
            print(f"Failed to report job {job_id}. Status code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"Error reporting job: {e}")

print("Waiting for jobs in the queue...")

try:
    while True:
        job = get_job()
        if job:
            command = job['job_name']
            job_id = job['id']
            if command == 'extend_motors':
                ser.write(b'o')
                print("Extending motors...")
            elif command == 'retract_motors':
                ser.write(b'c')
                print("Retracting motors...")
            else:
                print(f"Unknown command: {command}")
                report_job_completion(job_id, "unknown_command")
                continue

            time.sleep(0.5)  # Debounce delay
            report_job_completion(job_id, "completed")
        else:
            time.sleep(1)  # Wait before checking for new jobs again
except KeyboardInterrupt:
    print("Program terminated.")
finally:
    ser.close()

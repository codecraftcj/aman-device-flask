import serial
import requests
import json

# Configuration
SERIAL_PORT = "COM4"  # Replace with your Arduino's COM port (e.g., "COM3" for Windows, "/dev/ttyUSB0" for Linux)
BAUD_RATE = 9600      # Must match the Arduino Serial.begin() baud rate
API_URL = "https://amanrest-925084270691.asia-east2.run.app/set_water_parameters"

def main():
    try:
        # Initialize the serial connection
        print(f"Connecting to Arduino on {SERIAL_PORT} at {BAUD_RATE} baud...")
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print("Connected to Arduino!")

        while True:
            # Read line from Serial
            if ser.in_waiting > 0:
                raw_line = ser.readline().decode('utf-8').strip()
                print("---------")
                print(raw_line)
                print("---------")
                try:
                    # Parse JSON data from Arduino
                    sensor_data = json.loads(raw_line)

                    # Send POST request to the API
                    headers = {'Content-Type': 'application/json'}
                    response = requests.post(API_URL, json=sensor_data, headers=headers)

                    # Log the API response
                    print(f"Sent data to server: {sensor_data}")
                    print(f"Server Response: {response.status_code} - {response.text}")
                except json.JSONDecodeError:
                    print(f"Error: Could not parse JSON: {raw_line}")
                except requests.RequestException as e:
                    print(f"Error: Failed to send data to server: {e}")
    except serial.SerialException as e:
        print(f"Error: Could not connect to serial port: {e}")
    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Closed Serial connection.")

if __name__ == "__main__":
    main()
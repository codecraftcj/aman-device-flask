import serial

# Initialize the serial connection
serial_conn_2 = serial.Serial("/dev/ttyACM0", 9600, timeout=20)

def handle_input(task_name):
    """Handles input commands and sends data via serial."""
    if task_name == "small open":
        print("🛠️ SMALL OPEN HANDLED")
        serial_conn_2.write(b's')
    elif task_name == "half open":
        print("🛠️ HALF OPEN HANDLED")
        serial_conn_2.write(b'm')
    elif task_name == "full open":
        print("🛠️ LARGE OPEN HANDLED")
        serial_conn_2.write(b'l')
    print(f"Sent to serial: {task_name}")

print("🎧 Listening for commands. Type 'exit' to quit.")

while True:
    command = input("Enter command (s = small open, m = half open, l = full open, exit = quit): ").strip().lower()

    if command == "exit":
        print("\n❌ Exiting.")
        serial_conn_2.close()  # Close the serial connection before exiting
        break
    elif command == "s":
        handle_input("small open")
    elif command == "m":
        handle_input("half open")
    elif command == "l":
        handle_input("full open")
    else:
        print(f"⚠️ Unrecognized command: {command}")

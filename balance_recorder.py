#!/usr/bin/python3
import math
import re
import csv
import time
from datetime import datetime
from pathlib import Path
import serial
import serial.tools.list_ports
from serial import SerialException
import atexit


SECONDS_BETWEEN_MEASUREMENTS = 6

print(f"Seconds between measurements: {SECONDS_BETWEEN_MEASUREMENTS}")
if not isinstance(SECONDS_BETWEEN_MEASUREMENTS, int):
    raise Exception("SECONDS_BETWEEN_MEASUREMENTS needs to be an integer")
if SECONDS_BETWEEN_MEASUREMENTS > 3600:
    raise Exception("SECONDS_BETWEEN_MEASUREMENTS is too large. The largest acceptable value is 3600")
if SECONDS_BETWEEN_MEASUREMENTS < 1:
    raise Exception("SECONDS_BETWEEN_MEASUREMENTS is too large. The largest acceptable value is 3600")

csv_output_folder = Path(__file__).parent / "output_logs"

BALANCE_SERIAL_NUMS = {
    "C109240743": "Sylvester Scalelone",
    "C052778878": "Dweight Johnson",
    "C105085062": "Mass Damon"
}

usb_device_lock = Path(__file__).parent / "usb_device.lock"
usb_device = None


def main():
    balance = select_balance()
    lock_usb_device(balance["comport"])
    with serial.Serial(balance["comport"], baudrate=9600, timeout=0.1) as ser:
        # Create csv output file
        csv_filename = f"{balance['name']} {datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
        csv_path = csv_output_folder / csv_filename
        with open(str(csv_path), "w", newline='', buffering=1) as csv_file:
            fields = ["elapsed secs", "timestamp", "unix time", "gross", "net", "tare", "error", "unstable"]
            writer = csv.DictWriter(csv_file, fieldnames=fields)
            writer.writeheader()

            send_data(ser, f"{SECONDS_BETWEEN_MEASUREMENTS}P")  # Start the new stream of mass data over serial

            print(f"\nRecording balance measurements to {csv_path}\n")
            start_unix_time = None
            while True:
                rx = receive_data(ser)

                # Interpret received data
                unstable = False
                gross = None
                net = None
                tare = None
                for line in rx:
                    if line.startswith("SNR: "):
                        continue
                    elif line.startswith("Gross:"):
                        gross = get_number_from_string(line)
                        unstable = "?" in line
                    elif line.startswith("Net:"):
                        net = get_number_from_string(line)
                    elif line.startswith("Tare:"):
                        tare = get_number_from_string(line)

                if gross is None or net is None or tare is None:
                    error = True
                else:
                    error = False

                data_datetime = datetime.now()
                data_unix_time = data_datetime.timestamp()
                data_date_time = str(data_datetime.astimezone())
                if start_unix_time is None:
                    start_unix_time = data_unix_time
                elapsed_secs = round(data_unix_time - start_unix_time, 2)
                elapsed_time_hours = math.floor(elapsed_secs / 3600)
                remainder_seconds = elapsed_secs % 3600
                elapsed_time_mins = math.floor(remainder_seconds / 60)
                elapsed_time_secs = int(remainder_seconds % 60)

                print(f"{balance['name']}:    {elapsed_time_hours}h {elapsed_time_mins:02d}m {elapsed_time_secs:02d}s"
                      + f"    {data_date_time}    {net}g")

                # Write data to csv file
                data_point = {"elapsed secs": elapsed_secs,
                              "timestamp": data_date_time,
                              "unix time": data_unix_time,
                              "gross": gross,
                              "net": net,
                              "tare": tare,
                              "error": error,
                              "unstable": unstable}
                writer.writerow(data_point)
                time.sleep(0.1)


def select_balance():
    print("Balances available:")
    ports = serial.tools.list_ports.comports()
    balances = []
    for port in ports:
        # The USB<->RS232 cable has a specific vendor id (vid) and product id (pid)
        if port.vid == 1659 and port.pid == 8963:
            balance_serial_num = "Error"
            if is_usb_device_unlocked(port.device):
                with serial.Serial(port.device, baudrate=9600, timeout=0.1) as ser:
                    send_data(ser, "0P")  # Stop any old streams of data
                    time.sleep(0.2)
                    send_data(ser, "PSN")   # Request balance to 'Print Serial Number'
                    rx = receive_data(ser)
                for line in rx:
                    if line.startswith("SNR: "):
                        balance_serial_num = line.replace("SNR: ", "")
                balance = {"serial_num": balance_serial_num,
                           "name": BALANCE_SERIAL_NUMS.get(balance_serial_num, "?????"),
                           "comport": port.device}
                balances.append(balance)
                print(f'{len(balances)}. {balance["name"].ljust(6)} ({balance["serial_num"]} {balance["comport"]})')
            else:
                print("[Balance already in use]")
    if len(balances) == 0:
        print("  - No balances connected - ")
        input("\nPress enter to exit")
        exit()
    elif len(balances) == 1:
        balance_selected = balances[0]
        print(f"\n{balance_selected['name']} balance selected")
        input("Press enter to continue")
    else:
        number_list = list(range(1, len(balances) + 1))
        while True:
            balance_number_selected = input(f"\nSelect a balance to use {number_list}: ")
            try:
                balance_number_selected = int(balance_number_selected)
            except ValueError:
                pass
            else:
                if balance_number_selected in number_list:
                    balance_selected = balances[balance_number_selected - 1]
                    print(f"Selected {balance_selected['name']}")
                    break
            print("Invalid number selected")
    return balance_selected


def send_data(serial_connection, data):
    tx = f"{data}\r\n"
    serial_connection.write(tx.encode('ascii'))


def receive_data(serial_connection):
    # Waiting for data
    data_in = b''
    while data_in == b'':
        data_in = serial_connection.readline()

    # Start reading in data
    rx_raw_buffer = []
    while data_in != b'':
        rx_raw_buffer.append(data_in)
        data_in = serial_connection.readline()

    # Decode raw data in from bytes to text
    rx_buffer = [line.decode('ascii').strip() for line in rx_raw_buffer]
    return rx_buffer


def get_number_from_string(string):
    numbers = get_numbers_from_string(string)
    if len(numbers) == 1:
        return numbers[0]
    else:
        return None


def get_numbers_from_string(string):
    numbers_str = re.findall(r"[-+]?\d*\.\d+|\d+", string)
    numbers = [float(x) for x in numbers_str]
    return numbers


def is_usb_device_locked(device):
    if not usb_device_lock.exists():
        return False
    with open(str(usb_device_lock), "r") as usb_device_lock_file:
        data = usb_device_lock_file.read()
    if device in data:
        return True
    else:
        return False


def is_usb_device_unlocked(device):
    return not is_usb_device_locked(device)


def lock_usb_device(device):
    global usb_device
    usb_device = device
    if not is_usb_device_locked(device):
        with open(str(usb_device_lock), "a") as usb_device_lock_file:
            usb_device_lock_file.writelines(device + "\n")
            usb_device_lock_file.flush()


def unlock_usb_device(device):
    global usb_device
    usb_device = None
    if is_usb_device_locked(device):
        with open(str(usb_device_lock), "r") as usb_device_lock_file:
            data = usb_device_lock_file.read()
        data = data.replace(device + "\n", '')
        with open(str(usb_device_lock), "w") as usb_device_lock_file:
            usb_device_lock_file.writelines(data)
            usb_device_lock_file.flush()


def exit_handler():
    print(f"Unlocking {usb_device}")
    if usb_device is not None:
        unlock_usb_device(usb_device)


atexit.register(exit_handler)


if __name__ == '__main__':
    main()


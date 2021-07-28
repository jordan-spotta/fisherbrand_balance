#!/usr/bin/python3
import re
import csv
import time
from datetime import datetime
from pathlib import Path
import serial
import serial.tools.list_ports


SECONDS_BETWEEN_MEASUREMENTS = 10 * 60

print(f"{SECONDS_BETWEEN_MEASUREMENTS=}")
if not isinstance(SECONDS_BETWEEN_MEASUREMENTS, int):
    raise Exception("SECONDS_BETWEEN_MEASUREMENTS needs to be an integer")
if SECONDS_BETWEEN_MEASUREMENTS > 3600:
    raise Exception("SECONDS_BETWEEN_MEASUREMENTS is too large. The largest acceptable value is 3600")
if SECONDS_BETWEEN_MEASUREMENTS < 1:
    raise Exception("SECONDS_BETWEEN_MEASUREMENTS is too large. The largest acceptable value is 3600")

csv_filename = f"balance_readings_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.csv"
csv_path = Path(csv_filename)
# csv_path = Path.home() / "Desktop" / csv_filename


def main():
    # Open the COM port connection to the balance
    ports = serial.tools.list_ports.comports()
    comport = None
    for port in ports:
        # The USB<->RS232 cable has a specific vendor id (vid) and product id (pid)
        if port.vid == 1659 and port.pid == 8963:
            comport = port.device
            break
    if comport is None:
        raise Exception("Error: couldn't find COM port for USB<->RS232 cable")
    ser = serial.Serial(comport, baudrate=38400, timeout=0.1)

    if ser.isOpen() is False:
        ser.open()

    # Create csv output file
    with open(str(csv_path), "w", newline='', buffering=1) as csv_file:
        fields = ["elapsed secs", "timestamp", "unix time", "gross", "net", "tare", "error", "unstable"]
        writer = csv.DictWriter(csv_file, fieldnames=fields)
        writer.writeheader()

        # Stop any old streams of data
        tx = "0P\r\n"
        ser.write(tx.encode('ascii'))

        time.sleep(1)

        # Start the new stream of mass data over serial
        tx = f"{SECONDS_BETWEEN_MEASUREMENTS}P\r\n"
        ser.write(tx.encode('ascii'))

        print(f"Recording balance measurements to {csv_path}\n")
        start_unix_time = None
        while True:
            # Waiting for data
            data_in = b''
            while data_in == b'':
                data_in = ser.readline()

            # Start reading in data
            rx_raw_buffer = []
            while data_in != b'':
                rx_raw_buffer.append(data_in)
                data_in = ser.readline()

            # Decode raw data in from bytes to text
            rx_buffer = [line.decode('ascii').strip() for line in rx_raw_buffer]

            # Interpret received data
            unstable = False
            elapsed_secs = None
            timestamp = None
            unix_time = None
            gross = None
            net = None
            tare = None
            for line in rx_buffer:
                if line.startswith("Gross:"):
                    gross = get_number_from_string(line)
                    unstable = "?" in line
                elif line.startswith("Net:"):
                    net = get_number_from_string(line)
                elif line.startswith("Tare:"):
                    tare = get_number_from_string(line)
                elif len(line) > 6:
                    if line[2] == "/" and line[5] == "/":
                        timestamp = line
                        nums = get_numbers_from_string(line)
                        unix_time = datetime(int(nums[2]), int(nums[1]), int(nums[0]),
                                             int(nums[3]), int(nums[4]), int(nums[5])).timestamp()
                        if start_unix_time is None:
                            start_unix_time = unix_time
                        elapsed_secs = unix_time - start_unix_time

            if timestamp is None or gross is None or net is None or tare is None:
                error = True
            else:
                error = False

            # Write data to csv file
            data_point = {"elapsed secs": elapsed_secs,
                          "timestamp": timestamp,
                          "unix time": unix_time,
                          "gross": gross,
                          "net": net,
                          "tare": tare,
                          "error": error,
                          "unstable": unstable}
            print(data_point)
            writer.writerow(data_point)

            time.sleep(0.1)


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


if __name__ == '__main__':
    main()


import sys
import time
import serial

PORTS = [
    "/dev/ttyUSB3",
    "/dev/ttyUSB2",
]

BAUDRATE = 115200

# Replace with destination number
PHONE_NUMBER = "+6283849571919"

MESSAGE = "Test SMS from EFWS SIM7600E-H device."


def read_response(ser: serial.Serial, seconds: float = 2.0) -> str:
    deadline = time.time() + seconds
    data = bytearray()

    while time.time() < deadline:
        if ser.in_waiting:
            data.extend(ser.read(ser.in_waiting))
        time.sleep(0.05)

    return data.decode(errors="ignore")


def send_at(
    ser: serial.Serial,
    command: str,
    wait: float = 2.0,
) -> str:
    ser.reset_input_buffer()
    ser.write((command + "\r\n").encode())
    response = read_response(ser, wait)

    print(f"\n>>> {command}")
    print(response.strip() or "[NO RESPONSE]")

    return response


def find_at_port() -> str | None:
    for port in PORTS:
        try:
            with serial.Serial(port, BAUDRATE, timeout=1) as ser:
                response = send_at(ser, "AT", 1.5)

                if "OK" in response:
                    print(f"\nAT port found:{port}")
                    return port

        except serial.SerialException as error:
            print(f"{port}: {error}")

    return None


def main() -> int:
    port = find_at_port()

    if not port:
        print("There are no active AT ports.")
        return 1

    try:
        with serial.Serial(port, BAUDRATE, timeout=1) as ser:
            send_at(ser, "ATE0")
            send_at(ser, "AT+CPIN?")
            send_at(ser, "AT+CSQ")
            send_at(ser, "AT+CEREG?")
            send_at(ser, "AT+CMGF=1")
            send_at(ser, 'AT+CSCS="GSM"')
            send_at(ser, "AT+CSCA?")

            print(f"\n>>> AT+CMGS=\"{PHONE_NUMBER}\"")
            ser.reset_input_buffer()
            ser.write(f'AT+CMGS="{PHONE_NUMBER}"\r\n'.encode())

            prompt = read_response(ser, 5)
            print(prompt.strip() or "[NO PROMPT]")

            if ">" not in prompt:
                print("The modem does not provide SMS prompts.")
                return 1

            print(f"\nSend message:{MESSAGE}")

            # Ctrl+Z = byte 0x1A
            ser.write(MESSAGE.encode() + b"\x1A")

            result = read_response(ser, 30)
            print("\n=== RESULT ===")
            print(result.strip() or "[NO RESPONSE]")

            if "+CMGS:" in result and "OK" in result:
                print("\nSMS sent successfully.")
                return 0

            print("\nSMS failed or not confirmed modem.")
            return 1

    except serial.SerialException as error:
        print(f"Serial error: {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

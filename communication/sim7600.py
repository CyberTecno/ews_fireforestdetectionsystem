"""
SIM7600E-H 4G HAT controller via AT commands (serial diagnostics).

In practice, the simplest reliable way to get the Pi "online" through this
HAT is to let it register as a USB modem and bring it up with
ModemManager/NetworkManager (see docs/Deployment.md for the step-by-step).
This module is a lightweight fallback/diagnostic tool for checking signal
quality and network registration directly via AT commands.
Requires: pip install pyserial
"""
import time
import serial
from config import settings


class SIM7600:
    def __init__(self, port=settings.SIM7600_AT_PORT, baudrate=settings.SIM7600_BAUDRATE):
        self.ser = serial.Serial(port, baudrate, timeout=2)

    def send_at(self, command, wait=1):
        self.ser.write((command + "\r\n").encode())
        time.sleep(wait)
        return self.ser.read(self.ser.in_waiting or 1).decode(errors="ignore")

    def check_module(self):
        return "OK" in self.send_at("AT")

    def signal_quality(self):
        """AT+CSQ returns +CSQ: <rssi>,<ber>. rssi 0-31 (higher=better), 99=unknown."""
        return self.send_at("AT+CSQ")

    def network_registration(self):
        return self.send_at("AT+CREG?")

    def apn_setup(self, apn=settings.APN):
        self.send_at(f'AT+CGDCONT=1,"IP","{apn}"')
        return self.send_at("AT+CGATT=1")

    def get_ip(self):
        return self.send_at("AT+CGPADDR=1")

    def close(self):
        self.ser.close()


if __name__ == "__main__":
    modem = SIM7600()
    print("Module check:", modem.check_module())
    print("Signal:", modem.signal_quality())
    print("Registration:", modem.network_registration())

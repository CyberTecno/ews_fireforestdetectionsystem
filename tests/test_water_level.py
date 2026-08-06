from gpiozero import MCP3008
from statistics import mean
import time

# ============================================================
# KONFIGURASI MCP3008
# ============================================================

# Sensor terhubung ke CH4
ADC_CHANNEL = 4

# Resistor shunt yang digunakan
RESISTOR_OHM = 100.0

# Tegangan referensi MCP3008
VREF = 3.3

# ============================================================
# KONFIGURASI SENSOR 4–20 mA
# ============================================================

# Hasil pembacaan nol aktual dari sensor
ZERO_CURRENT_MA = 4.05

# Toleransi di sekitar titik nol
# Sampai 4.10 mA dianggap 0 mm
ZERO_TOLERANCE_MA = 0.05

# Arus maksimum sensor
MAX_CURRENT_MA = 20.0

# Rentang pengukuran sensor
MAX_LEVEL_MM = 4000.0

# Di bawah nilai ini dianggap sensor terputus
DISCONNECTED_LIMIT_MA = 3.5

# Di atas nilai ini dianggap over-range
OVERRANGE_LIMIT_MA = 21.0

# ============================================================
# FILTER PEMBACAAN
# ============================================================

# Jumlah sampel untuk dirata-ratakan
SAMPLE_COUNT = 20

# Jeda antar-sampel
SAMPLE_DELAY = 0.01

# Jeda antar-output
LOOP_DELAY = 1.0

adc = MCP3008(channel=ADC_CHANNEL)


def read_average_voltage() -> float:
    """
    Membaca tegangan MCP3008 beberapa kali,
    lalu mengembalikan nilai rata-rata.
    """
    samples = []

    for _ in range(SAMPLE_COUNT):
        voltage = adc.value * VREF
        samples.append(voltage)
        time.sleep(SAMPLE_DELAY)

    return mean(samples)


def voltage_to_current_ma(voltage: float) -> float:
    """
    Mengubah tegangan resistor menjadi arus mA.

    Rumus:
    I = V / R
    """
    return (voltage / RESISTOR_OHM) * 1000.0


def current_to_level_mm(current_ma: float) -> float:
    """
    Mengubah arus hasil kalibrasi menjadi level air.

    ZERO_CURRENT_MA = 0 mm
    MAX_CURRENT_MA  = 4000 mm
    """
    level_mm = (
        (current_ma - ZERO_CURRENT_MA)
        / (MAX_CURRENT_MA - ZERO_CURRENT_MA)
        * MAX_LEVEL_MM
    )

    return max(0.0, min(level_mm, MAX_LEVEL_MM))


def process_sensor(current_ma: float) -> tuple[float, str]:
    """
    Menentukan level air dan status sensor.
    """

    if current_ma < DISCONNECTED_LIMIT_MA:
        return 0.0, "SENSOR TERPUTUS / TIDAK ADA ARUS"

    zero_limit_ma = ZERO_CURRENT_MA + ZERO_TOLERANCE_MA

    if current_ma <= zero_limit_ma:
        return 0.0, "OK - ZERO"

    if current_ma > OVERRANGE_LIMIT_MA:
        return MAX_LEVEL_MM, "OVER-RANGE / PERIKSA WIRING"

    level_mm = current_to_level_mm(current_ma)

    return level_mm, "OK"


def main() -> None:
    print("=== TEST SENSOR LEVEL AIR 4–20 mA ===")
    print(f"Channel MCP3008   : CH{ADC_CHANNEL}")
    print(f"Resistor shunt    : {RESISTOR_OHM:.1f} ohm")
    print(f"Zero current      : {ZERO_CURRENT_MA:.2f} mA")
    print(
        f"Zero deadband     : sampai "
        f"{ZERO_CURRENT_MA + ZERO_TOLERANCE_MA:.2f} mA"
    )
    print(f"Level maksimum    : {MAX_LEVEL_MM:.0f} mm")
    print("Tekan Ctrl+C untuk berhenti.\n")

    try:
        while True:
            voltage = read_average_voltage()
            current_ma = voltage_to_current_ma(voltage)

            level_mm, status = process_sensor(current_ma)

            print(
                f"Volt: {voltage:.3f} V | "
                f"Arus: {current_ma:.2f} mA | "
                f"Level: {level_mm:.1f} mm | "
                f"Status: {status}"
            )

            time.sleep(LOOP_DELAY)

    except KeyboardInterrupt:
        print("\nProgram dihentikan oleh pengguna.")

    except Exception as error:
        print(f"\nTerjadi error: {error}")

    finally:
        adc.close()
        print("MCP3008 ditutup.")


if __name__ == "__main__":
    main()

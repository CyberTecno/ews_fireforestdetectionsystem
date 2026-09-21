from gpiozero import MCP3008
from statistics import mean
import time

# ============================================================
# MCP3008 CONFIGURATION
# ============================================================

# The sensor is connected to CH4
ADC_CHANNEL = 4

# Shunt resistor used
RESISTOR_OHM = 100.0

# Reference voltage MCP3008
VREF = 3.3

# ============================================================
# SENSOR CONFIGURATION 4–20 mA
# ============================================================

# The actual zero reading from the sensor
ZERO_CURRENT_MA = 4.05

# Tolerance around zero point
# Up to 4.10 mA is considered 0 mm
ZERO_TOLERANCE_MA = 0.05

# Maximum sensor current
MAX_CURRENT_MA = 20.0

# Sensor measuring range
MAX_LEVEL_MM = 4000.0

# Below this value is considered the sensor disconnected
DISCONNECTED_LIMIT_MA = 3.5

# Above this value is considered over-range
OVERRANGE_LIMIT_MA = 21.0

# ============================================================
# READING FILTERS
# ============================================================

# Number of samples to average
SAMPLE_COUNT = 20

# Delay between samples
SAMPLE_DELAY = 0.01

# Delay between output lines
LOOP_DELAY = 1.0

adc = MCP3008(channel=ADC_CHANNEL)


def read_average_voltage() -> float:
    """
Read the voltage MCP3008 several times,
then returns the average value.
    """
    samples = []

    for _ in range(SAMPLE_COUNT):
        voltage = adc.value * VREF
        samples.append(voltage)
        time.sleep(SAMPLE_DELAY)

    return mean(samples)


def voltage_to_current_ma(voltage: float) -> float:
    """
Converts resistor voltage to mA current.

    Rumus:
    I = V / R
    """
    return (voltage / RESISTOR_OHM) * 1000.0


def current_to_level_mm(current_ma: float) -> float:
    """
Converts the calibration result flow into water level.

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
Determines water level and sensor status.
    """

    if current_ma < DISCONNECTED_LIMIT_MA:
        return 0.0, "SENSOR DISCONNECTED / NO CURRENT"

    zero_limit_ma = ZERO_CURRENT_MA + ZERO_TOLERANCE_MA

    if current_ma <= zero_limit_ma:
        return 0.0, "OK - ZERO"

    if current_ma > OVERRANGE_LIMIT_MA:
        return MAX_LEVEL_MM, "OVER-RANGE / CHECK WIRING"

    level_mm = current_to_level_mm(current_ma)

    return level_mm, "OK"


def main() -> None:
    print("=== WATER LEVEL SENSOR TEST 4–20 mA ===")
    print(f"Channel MCP3008   : CH{ADC_CHANNEL}")
    print(f"Resistor shunt    : {RESISTOR_OHM:.1f} ohm")
    print(f"Zero current      : {ZERO_CURRENT_MA:.2f} mA")
    print(
        f"Zero deadband : until"
        f"{ZERO_CURRENT_MA + ZERO_TOLERANCE_MA:.2f} mA"
    )
    print(f"Maximum level :{MAX_LEVEL_MM:.0f} mm")
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            voltage = read_average_voltage()
            current_ma = voltage_to_current_ma(voltage)

            level_mm, status = process_sensor(current_ma)

            print(
                f"Volt: {voltage:.3f} V | "
                f"Current:{current_ma:.2f} mA | "
                f"Level: {level_mm:.1f} mm | "
                f"Status: {status}"
            )

            time.sleep(LOOP_DELAY)

    except KeyboardInterrupt:
        print("\nProgram terminated by user.")

    except Exception as error:
        print(f"\nTerjadi error: {error}")

    finally:
        adc.close()
        print("MCP3008 closed.")


if __name__ == "__main__":
    main()

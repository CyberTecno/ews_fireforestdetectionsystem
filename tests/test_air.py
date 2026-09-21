from gpiozero import MCP3008
import time

# We assume the yellow cable /hitam goes to channel 5 (CH4) on MCP3008
# If you plug it into CH1, change the number 0 to 1 below
adc = MCP3008(channel=4)

# Enter the value of the resistor you are using (eg 150 or 100)
RESISTOR_OHM = 100  
VREF = 3.3 # Reference voltage MCP3008 (Raspberry Pi standard)

print("=== WATER SENSOR TEST (4-20mA) ===")
print("Press Ctrl+C to stop\n")

while True:
    try:
        # adc.value gives percentage (0.0 to 1.0)
        # We convert it to real voltage (Volts)
        tegangan = adc.value * VREF
        
        # Calculate the electric current (Ohm's Law: I = V / R) in mA units
        arus_mA = (tegangan / RESISTOR_OHM) * 1000
        
        # Calculate the water level
        # This sensor: 4mA = 0 mm, 20mA = 4000 mm
        # Current range = 16mA (from 20 - 4), Water range = 4000 mm
        
        if arus_mA < 3.8:
            status = "SENSOR DISCONNECTED / DRY"
            level_air_mm = 0
        else:
            status = "OK"
            level_air_mm = ((arus_mA - 4.0) / 16.0) * 4000
            
            # Don't leave the number minus if the current is slightly below 4mA
            if level_air_mm < 0: level_air_mm = 0
            # Maksimal 4000 mm
            if level_air_mm > 4000: level_air_mm = 4000

        print(f"Volt: {tegangan:.2f}V | Current:{arus_mA:.2f}mA | Water Level:{level_air_mm:.1f} mm | Status: {status}")
        
    except Exception as e:
        print(f"Error: {e}")
        
    time.sleep(1)

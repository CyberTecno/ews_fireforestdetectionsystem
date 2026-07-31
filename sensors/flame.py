"""
IR Flame Sensor -- dibaca via AO (analog) di MCP3008 channel TERAKHIR (CH7).

Keputusan user: sensor ini dikabel HANYA lewat AO ke MCP3008, BUKAN lewat
GPIO digital DO -- jadi tidak perlu RPi.GPIO/level converter tambahan untuk
sensor ini, cukup lewat jalur analog yang sama seperti sensor MCP3008
lainnya (get_mcp3008()).

============================================================
KALIBRASI WAJIB SEBELUM DIPASANG DI LAPANGAN
============================================================
FLAME_AO_THRESHOLD_V di config/settings.py baru PERKIRAAN AWAL (setengah
VREF, 1.65V), BELUM diukur dari unit fisik Anda. Cara kalibrasi:
  1. Jalankan file ini langsung (`python sensors/flame.py`) di kondisi
     normal (tidak ada api) -- catat nilai "AO" yang tercetak.
  2. Dekatkan sumber api kecil yang aman (korek api / lilin, jarak wajar,
     JANGAN sampai merusak sensor) -- catat nilai "AO" yang tercetak.
  3. Set EFWS_FLAME_AO_THRESHOLD_V di .env ke nilai di antara keduanya.
  4. Kalau AO TURUN saat ada api (umum untuk banyak modul comparator IR),
     biarkan trigger_below=True (default). Kalau AO malah NAIK saat ada
     api pada modul Anda, panggil FlameSensor(trigger_below=False).
"""
from config import settings
from sensors.mcp3008 import get_mcp3008


class FlameSensor:
    def __init__(self, channel=None, threshold_v=None, trigger_below=True):
        self.channel     = channel     if channel     is not None else settings.ADC_CHANNEL_FLAME_AO
        self.threshold_v = threshold_v if threshold_v is not None else settings.FLAME_AO_THRESHOLD_V
        self.trigger_below = trigger_below
        self.adc = get_mcp3008()

    def read(self) -> dict:
        voltage = self.adc.read_voltage(self.channel)
        detected = (voltage < self.threshold_v) if self.trigger_below else (voltage > self.threshold_v)
        return {"analog_voltage": voltage, "flame_detected": bool(detected)}


if __name__ == "__main__":
    import time
    sensor = FlameSensor()
    print(f"=== EFWS Flame Sensor Test (CH{sensor.channel}, threshold={sensor.threshold_v}V) ===")
    print("Belum dikalibrasi -- gunakan angka AO di bawah untuk menentukan threshold yang benar.\n")
    while True:
        r = sensor.read()
        print(f"AO={r['analog_voltage']:.3f}V | flame_detected={r['flame_detected']}")
        time.sleep(1)

"""
Threshold resolver — prioritas AKTIF threshold untuk evaluasi alarm.

Aturan (sesuai requirement backend):
    1. Kalau backend (via response /sensors/telemetry) pernah mengirim
       'config' dan sebuah field di dalamnya TIDAK null -> pakai nilai itu.
    2. Kalau belum pernah ada 'config' sama sekali, ATAU field tertentu di
       config terakhir bernilai null/hilang -> pakai nilai hardcoded lokal
       (config/thresholds.json) UNTUK FIELD ITU SAJA.

Ini per-field, bukan all-or-nothing -- persis seperti contoh response API
yang mengirim "waterDangerThreshold": null sementara field lain terisi:
artinya HANYA water yang fallback ke lokal, field lain tetap pakai remote.

'remote_config' di sini adalah dict MENTAH terakhir yang diterima dari
field "config" pada response API (disimpan oleh APIPublisher.remote_config).
Modul ini tidak menyimpan state apa pun sendiri -- murni fungsi merge.
"""
from typing import Any, Optional


def _pick(remote_value: Any, local_value: Any) -> Any:
    """Remote menang kalau ada dan bukan None; selain itu pakai lokal."""
    return local_value if remote_value is None else remote_value


def resolve_active_thresholds(local: dict, remote_config: Optional[dict]) -> dict:
    """
    Gabungkan hardcoded local thresholds dengan remote config (kalau ada),
    field per field. Selalu mengembalikan dict lengkap dengan bentuk yang
    sama seperti `local` (jadi caller/_evaluate tidak perlu tahu asalnya).
    """
    remote = remote_config or {}

    resolved = dict(local)  # shallow copy cukup, semua field top-level scalar/dict kecil

    resolved["smokeDangerThreshold"] = _pick(
        remote.get("smokeDangerThreshold"), local["smokeDangerThreshold"]
    )
    resolved["temperatureDangerThreshold"] = _pick(
        remote.get("temperatureDangerThreshold"), local["temperatureDangerThreshold"]
    )
    resolved["humidityDangerThreshold"] = _pick(
        remote.get("humidityDangerThreshold"), local["humidityDangerThreshold"]
    )
    resolved["waterDangerThreshold"] = _pick(
        remote.get("waterDangerThreshold"), local["waterDangerThreshold"]
    )

    # soilMoistureDangerThreshold: nested dict {surface, deep} -- merge per sub-field juga,
    # karena API bisa saja suatu saat cuma mengisi salah satu (mis. surface saja).
    remote_soil = remote.get("soilMoistureDangerThreshold")
    if not isinstance(remote_soil, dict):
        remote_soil = {}
    local_soil = local["soilMoistureDangerThreshold"]
    resolved["soilMoistureDangerThreshold"] = {
        "surface": _pick(remote_soil.get("surface"), local_soil["surface"]),
        "deep":    _pick(remote_soil.get("deep"),    local_soil["deep"]),
    }

    # windDangerThreshold: TIDAK ADA di kontrak API sama sekali -- selalu lokal.
    resolved["windDangerThreshold"] = local["windDangerThreshold"]

    return resolved

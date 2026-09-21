"""
Threshold resolver — priority ON threshold for alarm evaluation.

Rules (according to backend requirements):
1. If the backend (via response /sensors/telemetry) ever sends
'config' and a field in it is NOT null -> use that value.
2. If there has never been any 'config' at all, OR certain fields in
last config value is null/hilang -> use local hardcoded value
(config/thresholds.json) FOR THAT FIELD ONLY.

This is per-field, not all-or-nothing -- just like the example response API
which sends "waterDangerThreshold": null while other fields are filled:
This means that ONLY water falls back to local, other fields still use remote.

'remote_config' here is the last dict MENTAH received from
"config" field in response API (stored by APIPublisher.remote_config).
This module does not store any state itself -- it is purely a merge function.
"""
from typing import Any, Optional


def _pick(remote_value: Any, local_value: Any) -> Any:
    """Remote wins if it is present and not None; Apart from that, use local."""
    return local_value if remote_value is None else remote_value


def resolve_active_thresholds(local: dict, remote_config: Optional[dict]) -> dict:
    """
Combine hardcoded local thresholds with remote config (if any),
field by field. Always returns a complete dict with that form
same as `local` (so caller/_evaluate doesn't need to know its origin).
    """
    remote = remote_config or {}

    resolved = dict(local)  # shallow copy is enough, all top-level scalar/dict fields are small

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
    resolved["pressureDangerThreshold"] = _pick(
        remote.get("pressureDangerThreshold"), local["pressureDangerThreshold"]
    )
    resolved["rainfallDangerThreshold"] = _pick(
        remote.get("rainfallDangerThreshold"), local["rainfallDangerThreshold"]
    )

    # soilMoistureDangerThreshold: nested dict {surface, deep} -- merge per sub-field too,
    # because API could at some point only fill one of them (eg surface only).
    remote_soil = remote.get("soilMoistureDangerThreshold")
    if not isinstance(remote_soil, dict):
        remote_soil = {}
    local_soil = local["soilMoistureDangerThreshold"]
    resolved["soilMoistureDangerThreshold"] = {
        "surface": _pick(remote_soil.get("surface"), local_soil["surface"]),
        "deep":    _pick(remote_soil.get("deep"),    local_soil["deep"]),
    }

    # windDangerThreshold: NONE in contract API at all -- always local.
    resolved["windDangerThreshold"] = local["windDangerThreshold"]

    return resolved

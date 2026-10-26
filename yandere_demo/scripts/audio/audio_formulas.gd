class_name AudioFormulas
extends RefCounted
## Presentation maths kept free of autoloads so unit tests can load it.

const HEARTBEAT_SILENT_SANITY: float = 60.0
const HEARTBEAT_QUIET_DB: float = -40.0
const HEARTBEAT_LOUD_DB: float = -6.0


static func heartbeat_is_audible(sanity: float) -> bool:
	return sanity < HEARTBEAT_SILENT_SANITY


static func heartbeat_volume_db(sanity: float) -> float:
	var loss: float = clampf((HEARTBEAT_SILENT_SANITY - sanity) / HEARTBEAT_SILENT_SANITY, 0.0, 1.0)
	return lerpf(HEARTBEAT_QUIET_DB, HEARTBEAT_LOUD_DB, loss)

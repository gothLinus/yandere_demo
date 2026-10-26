class_name UiFormulas
extends RefCounted
## Presentation maths kept free of autoloads so unit tests can load it.

const BASE_BPM: float = 60.0
const BPM_PER_LOST_SANITY: float = 0.8
const VIGNETTE_SANITY_START: float = 40.0
const VIGNETTE_SANITY_FULL: float = 0.0
const VIGNETTE_SUSPICION_START: float = 50.0
const VIGNETTE_SUSPICION_FULL: float = 100.0


static func beats_per_minute(sanity: float) -> float:
	return BASE_BPM + (100.0 - sanity) * BPM_PER_LOST_SANITY


static func vignette_intensity(sanity: float, suspicion: float) -> float:
	return maxf(
		smoothstep(VIGNETTE_SANITY_START, VIGNETTE_SANITY_FULL, sanity),
		smoothstep(VIGNETTE_SUSPICION_START, VIGNETTE_SUSPICION_FULL, suspicion),
	)

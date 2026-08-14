/** Earthzoom login cinema timing (seconds). Adjust here without touching JSX. */
export const EARTHZOOM_SRC = '/media/earthzoom.mp4';

/** Intro plays 0→this, then freezes under the login form. */
export const EARTHZOOM_INTRO_END = 9;

/**
 * Outro window after successful login (fake loading).
 * Start is aligned to the nearest video keyframe (~10.71s) so browsers
 * can seek/play reliably — seeking to exactly 10 often rewound to t=0.
 */
export const EARTHZOOM_OUTRO_START = 10.71;
export const EARTHZOOM_OUTRO_END = 14;

export type EarthzoomPhase = 'intro' | 'frozen' | 'outro';

/** Earthzoom login cinema timing (seconds). Adjust here without touching JSX. */
export const EARTHZOOM_SRC = '/media/earthzoom.mp4';

/** Intro plays 0→this, then freezes under the login form. */
export const EARTHZOOM_INTRO_END = 9;

/**
 * After successful login the same video resumes from the freeze (~INTRO_END)
 * and plays through to OUTRO_END (fake loading). We do not seek to 10s:
 * this MP4 only has keyframes at ~0 / 5.37 / 10.71 and seeking often failed
 * or flashed t=0, which made the outro disappear entirely.
 */
export const EARTHZOOM_OUTRO_START = 9;
export const EARTHZOOM_OUTRO_END = 14;

export type EarthzoomPhase = 'intro' | 'frozen' | 'outro';

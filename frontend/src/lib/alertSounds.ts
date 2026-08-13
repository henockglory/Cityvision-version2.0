export type AlertSoundDef = {
  id: string;
  labelFr: string;
  labelEn: string;
  src: string;
};

/** Bundled short alert tones under /sounds/alerts/*.wav */
export const ALERT_SOUND_CATALOG: AlertSoundDef[] = [
  { id: 'pulse_hi', labelFr: 'Pulse aigu', labelEn: 'High pulse', src: '/sounds/alerts/pulse_hi.wav' },
  { id: 'pulse_mid', labelFr: 'Pulse médium', labelEn: 'Mid pulse', src: '/sounds/alerts/pulse_mid.wav' },
  { id: 'pulse_lo', labelFr: 'Pulse grave', labelEn: 'Low pulse', src: '/sounds/alerts/pulse_lo.wav' },
  { id: 'double_beep', labelFr: 'Double bip', labelEn: 'Double beep', src: '/sounds/alerts/double_beep.wav' },
  { id: 'triple_beep', labelFr: 'Triple bip', labelEn: 'Triple beep', src: '/sounds/alerts/triple_beep.wav' },
  { id: 'siren_up', labelFr: 'Sirène montante', labelEn: 'Siren up', src: '/sounds/alerts/siren_up.wav' },
  { id: 'siren_down', labelFr: 'Sirène descendante', labelEn: 'Siren down', src: '/sounds/alerts/siren_down.wav' },
  { id: 'siren_sweep', labelFr: 'Sirène balayage', labelEn: 'Siren sweep', src: '/sounds/alerts/siren_sweep.wav' },
  { id: 'klaxon', labelFr: 'Klaxon', labelEn: 'Klaxon', src: '/sounds/alerts/klaxon.wav' },
  { id: 'horn_blast', labelFr: 'Corne', labelEn: 'Horn blast', src: '/sounds/alerts/horn_blast.wav' },
  { id: 'alarm_a', labelFr: 'Alarme A', labelEn: 'Alarm A', src: '/sounds/alerts/alarm_a.wav' },
  { id: 'alarm_b', labelFr: 'Alarme B', labelEn: 'Alarm B', src: '/sounds/alerts/alarm_b.wav' },
  { id: 'urgent_staccato', labelFr: 'Staccato urgent', labelEn: 'Urgent staccato', src: '/sounds/alerts/urgent_staccato.wav' },
  { id: 'sonar_ping', labelFr: 'Ping sonar', labelEn: 'Sonar ping', src: '/sounds/alerts/sonar_ping.wav' },
  { id: 'buzz_alert', labelFr: 'Buzz', labelEn: 'Buzz alert', src: '/sounds/alerts/buzz_alert.wav' },
  { id: 'two_tone', labelFr: 'Deux tons', labelEn: 'Two-tone', src: '/sounds/alerts/two_tone.wav' },
  { id: 'three_tone', labelFr: 'Trois tons', labelEn: 'Three-tone', src: '/sounds/alerts/three_tone.wav' },
  { id: 'impact', labelFr: 'Impact', labelEn: 'Impact', src: '/sounds/alerts/impact.wav' },
  { id: 'radar_blip', labelFr: 'Blip radar', labelEn: 'Radar blip', src: '/sounds/alerts/radar_blip.wav' },
  { id: 'critical_burst', labelFr: 'Rafale critique', labelEn: 'Critical burst', src: '/sounds/alerts/critical_burst.wav' },
  { id: 'gate_chime', labelFr: 'Carillon portail', labelEn: 'Gate chime', src: '/sounds/alerts/gate_chime.wav' },
  { id: 'perimeter', labelFr: 'Périmètre', labelEn: 'Perimeter', src: '/sounds/alerts/perimeter.wav' },
];

export const DEFAULT_ALERT_SOUND_ID = ALERT_SOUND_CATALOG[0]!.id;

export function isCustomAlertSoundId(id: string): boolean {
  return id.startsWith('custom:');
}

export function customAlertSoundKey(id: string): string | null {
  if (!isCustomAlertSoundId(id)) return null;
  return id.slice('custom:'.length) || null;
}

export function findBundledAlertSound(id: string): AlertSoundDef | undefined {
  return ALERT_SOUND_CATALOG.find((s) => s.id === id);
}

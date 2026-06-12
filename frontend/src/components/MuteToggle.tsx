import { Volume2, VolumeX } from 'lucide-react';
import { useUiStore } from '@/stores/uiStore';
import { useSound } from '@/hooks/useSound';

export default function MuteToggle() {
  const soundMuted = useUiStore((s) => s.soundMuted);
  const toggleSound = useUiStore((s) => s.toggleSound);
  const { playClick } = useSound();

  return (
    <button
      type="button"
      onClick={() => {
        if (!soundMuted) playClick();
        toggleSound();
      }}
      className="cv-btn-ghost p-2 rounded-lg"
      aria-label={soundMuted ? 'Unmute' : 'Mute'}
    >
      {soundMuted ? <VolumeX className="w-5 h-5" /> : <Volume2 className="w-5 h-5" />}
    </button>
  );
}

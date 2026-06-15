import { Sun, Moon } from 'lucide-react';
import { useUiStore } from '@/stores/uiStore';
import { useSound } from '@/hooks/useSound';
import Tooltip from '@/components/ui/Tooltip';

export default function ThemeToggle() {
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const { playClick } = useSound();

  return (
    <Tooltip content={theme === 'dark' ? 'Mode clair' : 'Mode sombre'}>
      <button
        id="theme-toggle"
        type="button"
        onClick={() => {
          playClick();
          toggleTheme();
        }}
        className="cv-btn-ghost p-2 rounded-lg shrink-0"
        aria-label="Toggle theme"
      >
        {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
      </button>
    </Tooltip>
  );
}

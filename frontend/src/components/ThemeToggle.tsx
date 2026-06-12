import { Moon, Sun } from 'lucide-react';
import { useUiStore } from '@/stores/uiStore';
import { useSound } from '@/hooks/useSound';

export default function ThemeToggle() {
  const theme = useUiStore((s) => s.theme);
  const toggleTheme = useUiStore((s) => s.toggleTheme);
  const { playClick } = useSound();

  return (
    <button
      id="theme-toggle"
      type="button"
      onClick={() => {
        playClick();
        toggleTheme();
      }}
      className="cv-btn-ghost p-2 rounded-lg"
      aria-label={theme === 'dark' ? 'Light mode' : 'Dark mode'}
    >
      {theme === 'dark' ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
    </button>
  );
}

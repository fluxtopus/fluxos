import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ThemeMode = 'system' | 'light' | 'dark';

interface ThemeStore {
  mode: ThemeMode;
  setMode: (mode: ThemeMode) => void;
}

export const useThemeStore = create<ThemeStore>()(
  persist(
    (set) => ({
      mode: 'system',
      setMode: (mode) => set({ mode }),
    }),
    {
      name: 'theme-store',
      // Migrate old { theme: 'light'|'dark' } to new { mode: ... }
      migrate: (persisted: unknown) => {
        const old = persisted as Record<string, unknown>;
        if (old && 'theme' in old && !('mode' in old)) {
          return { mode: old.theme as ThemeMode };
        }
        return old as { mode: ThemeMode };
      },
      version: 1,
    }
  )
);

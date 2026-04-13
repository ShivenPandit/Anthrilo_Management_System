'use client';

import dynamic from 'next/dynamic';
import { useState, useCallback, useEffect, memo } from 'react';
import { Search, Moon, Sun, Command, Menu } from 'lucide-react';
import { Breadcrumbs } from './Breadcrumbs';
import { NotificationDropdown } from './NotificationDropdown';
import { AvatarMenu } from './AvatarMenu';

const CommandPalette = dynamic(() => import('./CommandPalette'), {
  ssr: false,
});

// Theme Toggle
const ThemeToggle = memo(function ThemeToggle() {
  const [darkMode, setDarkMode] = useState(false);

  useEffect(() => {
    const isDark =
      localStorage.getItem('theme') === 'dark' ||
      (!localStorage.getItem('theme') &&
        window.matchMedia('(prefers-color-scheme: dark)').matches);
    setDarkMode(isDark);
    if (isDark) document.documentElement.classList.add('dark');
  }, []);

  const toggle = useCallback(() => {
    const next = !darkMode;
    setDarkMode(next);
    document.documentElement.classList.toggle('dark', next);
    localStorage.setItem('theme', next ? 'dark' : 'light');
  }, [darkMode]);

  return (
    <button
      onClick={toggle}
      aria-label={darkMode ? 'Switch to light mode' : 'Switch to dark mode'}
      title={darkMode ? 'Light mode' : 'Dark mode'}
      className="p-2 rounded-xl text-slate-400 hover:text-slate-600 dark:hover:text-slate-300
                 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
    >
      {darkMode
        ? <Sun className="w-[18px] h-[18px]" />
        : <Moon className="w-[18px] h-[18px]" />}
    </button>
  );
});

interface NavbarProps {
  onOpenSidebar?: () => void;
}

// Navbar
export function Navbar({ onOpenSidebar }: NavbarProps) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  // ⌘K / Ctrl+K global shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Scroll-shadow: follow whichever container owns page scrolling.
  useEffect(() => {
    const main = document.querySelector('main') as HTMLElement | null;
    const dashboardShell = document.querySelector('[data-dashboard-scroll-container]') as HTMLElement | null;

    const mainOverflowY = main ? window.getComputedStyle(main).overflowY : '';
    const shellOverflowY = dashboardShell ? window.getComputedStyle(dashboardShell).overflowY : '';

    const mainIsScrollable = !!main && /(auto|scroll|overlay)/.test(mainOverflowY);
    const shellIsScrollable = !!dashboardShell && /(auto|scroll|overlay)/.test(shellOverflowY);

    const scrollTarget: HTMLElement | Window =
      mainIsScrollable
        ? main!
        : (shellIsScrollable ? dashboardShell! : window);

    const readScrollTop = () =>
      scrollTarget === window
        ? window.scrollY
        : (scrollTarget as HTMLElement).scrollTop;

    const onScroll = () => setScrolled(readScrollTop() > 4);

    onScroll();

    if (scrollTarget === window) {
      window.addEventListener('scroll', onScroll, { passive: true });
      return () => window.removeEventListener('scroll', onScroll);
    }

    scrollTarget.addEventListener('scroll', onScroll, { passive: true });
    return () => scrollTarget.removeEventListener('scroll', onScroll);
  }, []);

  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  return (
    <>
      <header
        className={`h-14 2xl:h-16 flex-shrink-0 flex items-center justify-between px-3 sm:px-4 lg:px-5 2xl:px-7 gap-2 sm:gap-3 lg:gap-4
                    bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl
                    border-b border-slate-200/60 dark:border-slate-800/60
                    sticky top-0 z-30 transition-shadow duration-300
                    ${scrolled
                      ? 'shadow-[0_2px_12px_-2px_rgba(0,0,0,0.08)] dark:shadow-[0_2px_12px_-2px_rgba(0,0,0,0.4)]'
                      : 'shadow-none'
                    }`}
      >
        {/* Left */}
        <div className="flex items-center min-w-0 flex-1 gap-1.5 sm:gap-2">
          <button
            type="button"
            onClick={onOpenSidebar}
            aria-label="Open navigation"
            className="md:hidden p-2 rounded-xl text-slate-500 hover:text-slate-700 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>

          <Breadcrumbs />
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-0.5 sm:gap-1 flex-shrink-0">

          {/* Search / Command Palette trigger */}
          <button
            onClick={openPalette}
            aria-label="Open command palette"
            title="Search (⌘K)"
            className="flex items-center gap-1.5 sm:gap-2 px-2 py-1.5 rounded-xl
                       text-slate-400 hover:text-slate-600 dark:hover:text-slate-300
                       hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors group"
          >
            <Search className="w-[17px] h-[17px]" />
            {/* ⌘K hint badge */}
            <kbd
              className="hidden md:flex items-center gap-0.5 px-1.5 py-0.5 rounded-md text-[10px] font-medium
                         bg-slate-100 dark:bg-slate-800 text-slate-400
                         ring-1 ring-slate-200 dark:ring-slate-700
                         group-hover:ring-slate-300 dark:group-hover:ring-slate-600 transition-all"
            >
              <Command className="w-2.5 h-2.5" />
              K
            </kbd>
          </button>

          {/* Notifications */}
          <div className="hidden sm:block">
            <NotificationDropdown />
          </div>

          {/* Theme toggle */}
          <div className="hidden md:block">
            <ThemeToggle />
          </div>

          {/* Divider */}
          <div className="w-px h-5 bg-slate-200 dark:bg-slate-800 mx-1 hidden sm:block" aria-hidden />

          {/* Avatar + profile menu */}
          <AvatarMenu />
        </div>
      </header>

      {/* Command Palette */}
      <CommandPalette open={paletteOpen} onClose={closePalette} />
    </>
  );
}

import {
  type ComponentType,
  type ReactNode,
  type SVGProps,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { NavLink, useLocation } from "react-router";
import { isRunning, useCurrentJob } from "../api/queries";
import { type ThemePreference, useTheme } from "../lib/theme";
import { cx } from "./cx";
import {
  ArchiveIcon,
  HistoryIcon,
  HomeIcon,
  ListIcon,
  MenuIcon,
  MonitorIcon,
  MoonIcon,
  SettingsIcon,
  SunIcon,
  SyncIcon,
  XIcon,
} from "./icons";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  end?: boolean;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: HomeIcon, end: true },
  { to: "/sync", label: "Sync", icon: SyncIcon },
  { to: "/playlists", label: "Playlists", icon: ListIcon },
  { to: "/history", label: "History", icon: HistoryIcon },
  { to: "/backups", label: "Backups", icon: ArchiveIcon },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

function Logo() {
  return (
    <span className="flex items-center gap-2 font-semibold tracking-tight">
      <svg viewBox="0 0 32 32" className="size-6" aria-hidden="true">
        <rect x="3" y="7" width="26" height="20" rx="3" className="fill-accent" />
        <rect
          x="7"
          y="3"
          width="18"
          height="4"
          rx="1.5"
          className="fill-accent opacity-60"
        />
        <rect x="9" y="13" width="14" height="2.5" rx="1.25" className="fill-accent-fg" />
      </svg>
      Cratekeeper
    </span>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const currentJob = useCurrentJob();
  const jobRunning = isRunning(currentJob.data);
  return (
    <ul className="space-y-0.5">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <li key={to}>
          <NavLink
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-accent-soft text-accent"
                  : "text-muted hover:bg-surface-2 hover:text-fg",
              )
            }
          >
            <Icon className="size-4" />
            {label}
            {to === "/sync" && jobRunning && (
              <span className="ml-auto flex items-center gap-1.5 text-xs font-normal text-accent">
                <span
                  className="size-2 animate-pulse rounded-full bg-accent"
                  aria-hidden="true"
                />
                <span>running</span>
              </span>
            )}
          </NavLink>
        </li>
      ))}
    </ul>
  );
}

const THEMES: {
  value: ThemePreference;
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
}[] = [
  { value: "system", label: "System", icon: MonitorIcon },
  { value: "light", label: "Light", icon: SunIcon },
  { value: "dark", label: "Dark", icon: MoonIcon },
];

interface ThemeProps {
  theme: ThemePreference;
  setTheme: (value: ThemePreference) => void;
}

function ThemeSwitch({ theme, setTheme }: ThemeProps) {
  const name = useId();
  return (
    <fieldset>
      <legend className="mb-1.5 px-1 text-xs text-muted">Theme</legend>
      <div className="grid grid-cols-3 gap-1 rounded-md border border-line bg-surface-2 p-0.5">
        {THEMES.map(({ value, label, icon: Icon }) => (
          <label
            key={value}
            title={label}
            className={cx(
              "flex cursor-pointer items-center justify-center gap-1 rounded px-1.5 py-1 text-xs has-focus-visible:outline-2 has-focus-visible:outline-focus",
              theme === value
                ? "bg-surface text-fg shadow-xs"
                : "text-muted hover:text-fg",
            )}
          >
            <input
              type="radio"
              name={name}
              value={value}
              checked={theme === value}
              onChange={() => setTheme(value)}
              className="sr-only"
            />
            <Icon className="size-3.5 shrink-0" />
            <span>{label}</span>
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function MobileDrawer({
  open,
  onClose,
  onNavigate,
  ...theme
}: { open: boolean; onClose: () => void; onNavigate: () => void } & ThemeProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 md:hidden">
      <button
        type="button"
        aria-label="Close menu"
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        tabIndex={-1}
      />
      <div
        ref={panelRef}
        id="mobile-nav"
        role="dialog"
        aria-modal="true"
        aria-label="Menu"
        className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col gap-6 overflow-y-auto border-r border-line bg-surface p-4"
      >
        <div className="flex items-center justify-between">
          <Logo />
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-2 text-muted hover:bg-surface-2"
            aria-label="Close menu"
          >
            <XIcon className="size-5" />
          </button>
        </div>
        <nav aria-label="Main">
          <NavLinks onNavigate={onNavigate} />
        </nav>
        <div className="mt-auto">
          <ThemeSwitch {...theme} />
        </div>
      </div>
    </div>
  );
}

export function Layout({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const returnFocus = useRef(false);
  // Navigating moves focus to the page; dismissing returns it to the menu button.
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const dismissMenu = useCallback(() => {
    returnFocus.current = true;
    setMenuOpen(false);
  }, []);
  useEffect(() => {
    if (menuOpen || !returnFocus.current) return;
    returnFocus.current = false;
    menuButtonRef.current?.focus();
  }, [menuOpen]);
  const [theme, setTheme] = useTheme();
  const location = useLocation();

  // Move focus to the page on navigation, so keyboard and screen reader users land on the content.
  const mainRef = useRef<HTMLElement>(null);
  const firstRender = useRef(true);
  useEffect(() => {
    if (firstRender.current) {
      firstRender.current = false;
      return;
    }
    mainRef.current?.focus({ preventScroll: true });
    window.scrollTo(0, 0);
  }, [location.pathname]);

  return (
    <div className="min-h-dvh md:flex">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Skip to content
      </a>
      <aside className="sticky top-0 hidden h-dvh w-60 shrink-0 flex-col gap-6 border-r border-line bg-surface px-3 py-5 md:flex">
        <div className="px-3">
          <Logo />
        </div>
        <nav aria-label="Main">
          <NavLinks />
        </nav>
        <div className="mt-auto px-1">
          <ThemeSwitch theme={theme} setTheme={setTheme} />
        </div>
      </aside>

      <header
        inert={menuOpen}
        className="sticky top-0 z-30 flex items-center gap-2 border-b border-line bg-surface/95 px-2 py-2 backdrop-blur md:hidden"
      >
        <button
          ref={menuButtonRef}
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Open menu"
          aria-expanded={menuOpen}
          aria-controls="mobile-nav"
          className="rounded-md p-2 text-muted hover:bg-surface-2"
        >
          <MenuIcon className="size-5" />
        </button>
        <Logo />
      </header>
      <MobileDrawer
        open={menuOpen}
        onClose={dismissMenu}
        onNavigate={closeMenu}
        theme={theme}
        setTheme={setTheme}
      />

      <main
        id="main"
        ref={mainRef}
        tabIndex={-1}
        inert={menuOpen}
        className="min-w-0 flex-1 outline-none"
      >
        <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 md:px-8 md:py-8">
          {children}
        </div>
      </main>
    </div>
  );
}

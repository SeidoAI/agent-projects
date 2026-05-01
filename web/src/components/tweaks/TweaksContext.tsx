import { createContext, type ReactNode, useContext, useEffect, useMemo, useState } from "react";

/**
 * Six dimensions per spec §3.1 C0.6 — fine-tunes the design without
 * leaving the running app. Persisted to localStorage; the post-fine-tune
 * defaults can later be hard-baked back into `app.css` and the panel
 * stays for ongoing experiments.
 */
export type PaperWarmth = "cream" | "off-white" | "linen" | "parchment" | "notebook" | "graph";
export type RuleColour = "red" | "ochre" | "indigo";
export type Density = "compact" | "comfortable" | "loose";
export type StampShape = "rect" | "pill" | "ticket-cut";
export type SerifFamily = "Instrument Serif" | "EB Garamond" | "Iowan Old Style";
export type MonoFamily = "Geist Mono" | "JetBrains Mono" | "IBM Plex Mono";

export interface TweakValues {
  paperWarmth: PaperWarmth;
  ruleColour: RuleColour;
  density: Density;
  stampShape: StampShape;
  serifFamily: SerifFamily;
  monoFamily: MonoFamily;
}

export const TWEAK_DEFAULTS: TweakValues = {
  paperWarmth: "cream",
  ruleColour: "red",
  density: "comfortable",
  stampShape: "rect",
  serifFamily: "Instrument Serif",
  monoFamily: "Geist Mono",
};

export const STORAGE_KEY = "tripwire.tweaks.v1";

/**
 * Each tweak dimension maps to one or more CSS custom properties on
 * `<html>`. The Tweaks panel updates this map on every change, and
 * any token-driven consumer (paper bg, font face, stamp radius, etc.)
 * picks up the new value without a React re-render.
 *
 * The defaults already live in `app.css`; this map only needs entries
 * for non-default values. We always set the property — even on the
 * default — so that toggling back to the default visibly clears any
 * prior override.
 */
// Each variant sets the base `--color-paper` colour and an optional
// `--paper-image` background stack, applied at <html> by app.css.
// Solid variants set `--paper-image: none` so toggling between
// textured ↔ solid clears the previous texture cleanly.
const PAPER_VARS: Record<PaperWarmth, Record<string, string>> = {
  cream: { "--color-paper": "#f0eee9", "--paper-image": "none" },
  "off-white": { "--color-paper": "#f5f4ef", "--paper-image": "none" },
  linen: { "--color-paper": "#ece5d8", "--paper-image": "none" },
  parchment: { "--color-paper": "#ebe1d0", "--paper-image": "none" },
  // Field-notebook texture: light horizontal ruled lines every 32px
  // plus a single rule-red vertical margin line ~80px from the left.
  // Cards/panels (which use --color-paper-2/-3) sit on top and
  // occlude the texture inside them — texture is only visible in
  // gutters and empty page areas, which is the desired effect.
  notebook: {
    "--color-paper": "#f0eee9",
    "--paper-image":
      "repeating-linear-gradient(to bottom, transparent 0, transparent 31px, rgba(96, 110, 130, 0.22) 31px, rgba(96, 110, 130, 0.22) 32px), linear-gradient(to right, transparent 0, transparent 79px, rgba(200, 61, 46, 0.6) 79px, rgba(200, 61, 46, 0.6) 80px, transparent 80px)",
  },
  // Graph paper: faint grid every 24px in both axes. Reads as
  // engineering-pad rather than ruled-pad.
  graph: {
    "--color-paper": "#f0eee9",
    "--paper-image":
      "repeating-linear-gradient(to bottom, transparent 0, transparent 23px, rgba(96, 110, 130, 0.16) 23px, rgba(96, 110, 130, 0.16) 24px), repeating-linear-gradient(to right, transparent 0, transparent 23px, rgba(96, 110, 130, 0.16) 23px, rgba(96, 110, 130, 0.16) 24px)",
  },
};

const RULE_VARS: Record<RuleColour, Record<string, string>> = {
  red: { "--color-rule": "#c83d2e" },
  ochre: { "--color-rule": "#b8741a" },
  indigo: { "--color-rule": "#2d3a7c" },
};

const STAMP_VARS: Record<StampShape, Record<string, string>> = {
  rect: { "--radius-stamp": "4px" },
  pill: { "--radius-stamp": "9999px" },
  "ticket-cut": { "--radius-stamp": "2px" },
};

const SERIF_VARS: Record<SerifFamily, Record<string, string>> = {
  "Instrument Serif": {
    "--font-serif": "'Instrument Serif', 'EB Garamond', serif",
  },
  "EB Garamond": { "--font-serif": "'EB Garamond', 'Instrument Serif', serif" },
  "Iowan Old Style": {
    "--font-serif": "'Iowan Old Style', 'Instrument Serif', serif",
  },
};

const MONO_VARS: Record<MonoFamily, Record<string, string>> = {
  "Geist Mono": {
    "--font-mono": "'Geist Mono', ui-monospace, 'JetBrains Mono', monospace",
  },
  "JetBrains Mono": {
    "--font-mono": "'JetBrains Mono', ui-monospace, 'Geist Mono', monospace",
  },
  "IBM Plex Mono": {
    "--font-mono": "'IBM Plex Mono', ui-monospace, 'Geist Mono', monospace",
  },
};

const DENSITY_VARS: Record<Density, Record<string, string>> = {
  compact: { "--space-density": "0.75" },
  comfortable: { "--space-density": "1" },
  loose: { "--space-density": "1.25" },
};

function applyTweaks(t: TweakValues): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const all = {
    ...PAPER_VARS[t.paperWarmth],
    ...RULE_VARS[t.ruleColour],
    ...STAMP_VARS[t.stampShape],
    ...SERIF_VARS[t.serifFamily],
    ...MONO_VARS[t.monoFamily],
    ...DENSITY_VARS[t.density],
  };
  for (const [k, v] of Object.entries(all)) {
    root.style.setProperty(k, v);
  }
}

function loadFromStorage(): TweakValues {
  if (typeof window === "undefined") return TWEAK_DEFAULTS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return TWEAK_DEFAULTS;
    const parsed = JSON.parse(raw) as Partial<TweakValues>;
    // Defensive — a half-written value from an older version of the
    // panel shouldn't crash the app on next load. Spread defaults so
    // any missing key falls back, then trust the rest.
    return { ...TWEAK_DEFAULTS, ...parsed };
  } catch {
    return TWEAK_DEFAULTS;
  }
}

interface TweaksContextValue {
  values: TweakValues;
  setTweak: <K extends keyof TweakValues>(key: K, value: TweakValues[K]) => void;
  reset: () => void;
}

const TweaksContext = createContext<TweaksContextValue | null>(null);

export function TweaksProvider({ children }: { children: ReactNode }) {
  const [values, setValues] = useState<TweakValues>(() => loadFromStorage());

  // Apply the current tweaks to the DOM on mount and on every change.
  useEffect(() => {
    applyTweaks(values);
  }, [values]);

  // Persist after every change. Wrapped in a try/catch because a strict
  // browser profile (private mode, quota full) shouldn't break the UI.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(values));
    } catch {
      /* swallow */
    }
  }, [values]);

  const ctx = useMemo<TweaksContextValue>(
    () => ({
      values,
      setTweak: (key, value) => setValues((prev) => ({ ...prev, [key]: value })),
      reset: () => setValues(TWEAK_DEFAULTS),
    }),
    [values],
  );

  return <TweaksContext.Provider value={ctx}>{children}</TweaksContext.Provider>;
}

export function useTweaks(): TweaksContextValue {
  const ctx = useContext(TweaksContext);
  if (!ctx) throw new Error("useTweaks must be used inside <TweaksProvider>");
  return ctx;
}

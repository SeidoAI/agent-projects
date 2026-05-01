import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  type Density,
  type MonoFamily,
  type PaperWarmth,
  type RuleColour,
  type SerifFamily,
  type StampShape,
  useTweaks,
} from "./TweaksContext";

interface TweaksPanelProps {
  /** Forces the panel open at mount; otherwise closed until toggled. */
  defaultOpen?: boolean;
}

/**
 * Floating six-dimension fine-tune panel per spec §3.1 C0.6.
 *
 * Toggle: gear-icon button on the ScreenShell top bar OR `?tweaks=1`
 * URL flag (the latter is intentionally easy to share — "open the page
 * with the panel up" is the single workflow the user wants).
 */
export function TweaksPanel({ defaultOpen = false }: TweaksPanelProps) {
  const { values, setTweak } = useTweaks();
  const [searchParams] = useSearchParams();
  const [open, setOpen] = useState<boolean>(defaultOpen || searchParams.get("tweaks") === "1");

  // Sync the URL flag with the open state; if the URL changes
  // mid-session (e.g., user pastes a `?tweaks=1` link into the address
  // bar), reflect that without a remount.
  useEffect(() => {
    if (searchParams.get("tweaks") === "1") setOpen(true);
  }, [searchParams]);

  // Listen for the toolbar-style "open tweaks" event the ScreenShell
  // gear button dispatches. Keeping the wiring as a window event lets
  // any future surface (keyboard shortcut, command palette) flip the
  // panel without prop-threading state through the shell.
  useEffect(() => {
    const onOpen = () => setOpen(true);
    const onClose = () => setOpen(false);
    const onToggle = () => setOpen((prev) => !prev);
    window.addEventListener("tripwire:tweaks-open", onOpen);
    window.addEventListener("tripwire:tweaks-close", onClose);
    window.addEventListener("tripwire:tweaks-toggle", onToggle);
    return () => {
      window.removeEventListener("tripwire:tweaks-open", onOpen);
      window.removeEventListener("tripwire:tweaks-close", onClose);
      window.removeEventListener("tripwire:tweaks-toggle", onToggle);
    };
  }, []);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-label="Tweaks"
      className="fixed right-4 bottom-4 z-50 flex w-[280px] flex-col gap-3 rounded-(--radius-card) border border-(--color-edge) bg-(--color-paper-2) p-4 text-(--color-ink) shadow-lg"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-(--color-ink)">
          Tweaks
        </h2>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Close tweaks"
          className="font-mono text-[12px] text-(--color-ink-3) hover:text-(--color-ink)"
        >
          ✕
        </button>
      </div>

      <Field
        label="Paper warmth"
        value={values.paperWarmth}
        onChange={(v) => setTweak("paperWarmth", v as PaperWarmth)}
        options={["cream", "off-white", "linen", "parchment", "notebook", "graph"]}
      />
      <Field
        label="Rule colour"
        value={values.ruleColour}
        onChange={(v) => setTweak("ruleColour", v as RuleColour)}
        options={["red", "ochre", "indigo"]}
      />
      <Field
        label="Density"
        value={values.density}
        onChange={(v) => setTweak("density", v as Density)}
        options={["compact", "comfortable", "loose"]}
      />
      <Field
        label="Stamp shape"
        value={values.stampShape}
        onChange={(v) => setTweak("stampShape", v as StampShape)}
        options={["rect", "pill", "ticket-cut"]}
      />
      <Field
        label="Serif family"
        value={values.serifFamily}
        onChange={(v) => setTweak("serifFamily", v as SerifFamily)}
        options={["Instrument Serif", "EB Garamond", "Iowan Old Style"]}
      />
      <Field
        label="Mono family"
        value={values.monoFamily}
        onChange={(v) => setTweak("monoFamily", v as MonoFamily)}
        options={["Geist Mono", "JetBrains Mono", "IBM Plex Mono"]}
      />
    </div>
  );
}

interface FieldProps {
  label: string;
  value: string;
  options: string[];
  onChange: (next: string) => void;
}

function Field({ label, value, options, onChange }: FieldProps) {
  const id = `tweak-${label.replace(/\s+/g, "-").toLowerCase()}`;
  return (
    <label htmlFor={id} className="flex flex-col gap-1 text-[12px]">
      <span className="text-(--color-ink-2)">{label}</span>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-(--radius-stamp) border border-(--color-edge) bg-(--color-paper) px-2 py-1 font-mono text-[11px] text-(--color-ink)"
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}

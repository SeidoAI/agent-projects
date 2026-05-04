// theme.jsx — central theme system for all Tripwire screens.
//
// Exposes CSS variables on a wrapping <div data-theme-variant="..."> so screens
// inherit values without rewriting their inline-style literals. For colour
// swaps we ALSO emit a generated <style> block that uses attribute-substring
// selectors against the existing inline styles — ugly but effective for a
// design artefact.
//
// API:
//   <ThemeProvider value={tweaks}> wraps each screen.
//   useTheme() returns the current tweaks object.
//   THEME_OPTIONS exports the choice catalogue for the Tweaks panel.

const ThemeContext = React.createContext(null);

const THEME_OPTIONS = {
  paper: [
    { value: 'cream',      label: 'cream',      paper: '#f0eee9', paper2: '#faf8f3', paper3: '#e8e4dc', edge: '#c9bfae' },
    { value: 'bone',       label: 'bone',       paper: '#f5f1e8', paper2: '#fbf8f0', paper3: '#ebe5d6', edge: '#d4c7af' },
    { value: 'oat',        label: 'oat',        paper: '#ebe6da', paper2: '#f3eee2', paper3: '#dcd4c2', edge: '#bdb198' },
    { value: 'porcelain',  label: 'porcelain',  paper: '#f8f6f1', paper2: '#fefcf6', paper3: '#efebe2', edge: '#d3cbb9' },
  ],
  rule: [
    { value: 'red',     label: 'tripwire red',  hex: '#c83d2e', soft: 'rgba(200,61,46,0.06)' },
    { value: 'indigo',  label: 'india indigo',  hex: '#2d3a7c', soft: 'rgba(45,58,124,0.07)' },
    { value: 'ochre',   label: 'ochre',         hex: '#b8741a', soft: 'rgba(184,116,26,0.08)' },
    { value: 'forest',  label: 'forest',        hex: '#2d5a3d', soft: 'rgba(45,90,61,0.07)' },
  ],
  density: [
    { value: 'compact',     label: 'compact',     scale: 0.85 },
    { value: 'comfortable', label: 'comfortable', scale: 1.00 },
    { value: 'airy',        label: 'airy',        scale: 1.18 },
  ],
  stamp: [
    { value: 'rect',   label: 'rectangular' },
    { value: 'pill',   label: 'pill' },
    { value: 'ticket', label: 'ticket-cut' },
  ],
  serif: [
    { value: 'instrument', label: 'Instrument Serif',  stack: "'Instrument Serif', 'EB Garamond', serif" },
    { value: 'newsreader', label: 'Newsreader',        stack: "'Newsreader', 'Instrument Serif', serif" },
    { value: 'garamond',   label: 'EB Garamond',       stack: "'EB Garamond', 'Instrument Serif', serif" },
    { value: 'fraunces',   label: 'Fraunces',          stack: "'Fraunces', 'Instrument Serif', serif" },
  ],
  mono: [
    { value: 'geist',     label: 'Geist Mono',     stack: "'Geist Mono', 'JetBrains Mono', monospace" },
    { value: 'jetbrains', label: 'JetBrains Mono', stack: "'JetBrains Mono', 'Geist Mono', monospace" },
    { value: 'plex',      label: 'IBM Plex Mono',  stack: "'IBM Plex Mono', 'Geist Mono', monospace" },
    { value: 'commit',    label: 'Commit Mono',    stack: "'Commit Mono', 'Geist Mono', monospace" },
  ],
};

const THEME_DEFAULTS = {
  paper:   'cream',
  rule:    'red',
  density: 'comfortable',
  stamp:   'rect',
  serif:   'instrument',
  mono:    'geist',
};

const findOption = (dim, value) =>
  THEME_OPTIONS[dim].find(o => o.value === value) || THEME_OPTIONS[dim][0];

// Build a generated <style> block that overrides hard-coded inline-style
// colours from the original screens via attribute substring selectors.
// Only emitted when a non-default colour is selected.
const buildOverrides = (theme, scopeId) => {
  const paper = findOption('paper', theme.paper);
  const rule  = findOption('rule', theme.rule);

  const sel = `#${scopeId}`;
  const out = [];

  // Paper swaps — only if not the default cream
  if (theme.paper !== 'cream') {
    const swap = (from, to) => {
      out.push(`${sel} [style*="background: ${from}"] { background: ${to} !important; }`);
      out.push(`${sel} [style*="background:${from}"]  { background: ${to} !important; }`);
      out.push(`${sel} [style*="background-color: ${from}"] { background-color: ${to} !important; }`);
    };
    swap('#f0eee9', paper.paper);
    swap('#faf8f3', paper.paper2);
    swap('#e8e4dc', paper.paper3);
    out.push(`${sel} [style*="border: 1px solid #c9bfae"] { border-color: ${paper.edge} !important; }`);
    out.push(`${sel} [style*="border-bottom: 1px solid #c9bfae"] { border-bottom-color: ${paper.edge} !important; }`);
    out.push(`${sel} [style*="border-top: 1px solid #c9bfae"] { border-top-color: ${paper.edge} !important; }`);
    out.push(`${sel} [style*="border-right: 1px solid #c9bfae"] { border-right-color: ${paper.edge} !important; }`);
    out.push(`${sel} [style*="border-left: 1px solid #c9bfae"] { border-left-color: ${paper.edge} !important; }`);
  }

  // Rule colour swaps
  if (theme.rule !== 'red') {
    const swap = (from, to) => {
      out.push(`${sel} [style*="${from}"] { --tw-rule-tmp: 1; }`); // marker only
    };
    // exact background/color/stroke/border substitutions
    out.push(`${sel} [style*="background: #c83d2e"] { background: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="background:#c83d2e"]  { background: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="color: #c83d2e"]  { color: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="color:#c83d2e"]   { color: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="stroke: #c83d2e"] { stroke: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="stroke:#c83d2e"]  { stroke: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="fill: #c83d2e"]   { fill: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="fill:#c83d2e"]    { fill: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="border: 1px solid #c83d2e"] { border-color: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="border: 2px solid #c83d2e"] { border-color: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="border-left: 2px solid #c83d2e"] { border-left-color: ${rule.hex} !important; }`);
    out.push(`${sel} [style*="border-top: 2px solid #c83d2e"] { border-top-color: ${rule.hex} !important; }`);
    // SVG attributes
    out.push(`${sel} svg [stroke="#c83d2e"] { stroke: ${rule.hex} !important; }`);
    out.push(`${sel} svg [fill="#c83d2e"] { fill: ${rule.hex} !important; }`);
  }

  return out.join('\n');
};

let themeIdCounter = 0;
const makeScopeId = () => {
  themeIdCounter += 1;
  return `theme-scope-${themeIdCounter}`;
};

const ThemeProvider = ({ value, children }) => {
  const tweaks = { ...THEME_DEFAULTS, ...(value || {}) };
  const scopeIdRef = React.useRef(null);
  if (scopeIdRef.current === null) scopeIdRef.current = makeScopeId();
  const scopeId = scopeIdRef.current;

  const overrides = React.useMemo(() => buildOverrides(tweaks, scopeId),
    [tweaks.paper, tweaks.rule, scopeId]);

  const paper   = findOption('paper', tweaks.paper);
  const rule    = findOption('rule', tweaks.rule);
  const density = findOption('density', tweaks.density);
  const serif   = findOption('serif', tweaks.serif);
  const mono    = findOption('mono', tweaks.mono);

  return (
    <ThemeContext.Provider value={tweaks}>
      <div
        id={scopeId}
        data-theme-variant
        data-density={tweaks.density}
        data-stamp={tweaks.stamp}
        style={{
          '--tw-paper': paper.paper,
          '--tw-paper-2': paper.paper2,
          '--tw-paper-3': paper.paper3,
          '--tw-edge': paper.edge,
          '--tw-rule': rule.hex,
          '--tw-rule-soft': rule.soft,
          '--tw-density': density.scale,
          '--tw-serif': serif.stack,
          '--tw-mono': mono.stack,
          height: '100%', width: '100%',
        }}
      >
        {overrides && <style dangerouslySetInnerHTML={{ __html: overrides }} />}
        {children}
      </div>
    </ThemeContext.Provider>
  );
};

const useTheme = () => React.useContext(ThemeContext) || THEME_DEFAULTS;

window.ThemeProvider = ThemeProvider;
window.useTheme = useTheme;
window.THEME_OPTIONS = THEME_OPTIONS;
window.THEME_DEFAULTS = THEME_DEFAULTS;

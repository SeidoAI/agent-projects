// theme-tweaks.jsx — Tweaks panel for global theme controls.

const { TweaksPanel, TweakSection, TweakRadio, useTweaks } = window;
const { THEME_OPTIONS, THEME_DEFAULTS } = window;

// Atom-style global with subscriber callbacks
const themeAtom = (() => {
  let value = { ...THEME_DEFAULTS };
  const subs = new Set();
  return {
    get: () => value,
    set: (next) => {
      value = { ...value, ...next };
      subs.forEach(fn => fn(value));
    },
    subscribe: (fn) => { subs.add(fn); return () => subs.delete(fn); },
  };
})();
window.__themeAtom = themeAtom;

const useThemeAtom = () => {
  const [v, setV] = React.useState(themeAtom.get());
  React.useEffect(() => themeAtom.subscribe(setV), []);
  return v;
};
window.useThemeAtom = useThemeAtom;

const ThemeRoot = ({ children }) => {
  const tweaks = useThemeAtom();
  const { ThemeProvider } = window;
  return <ThemeProvider value={tweaks}>{children}</ThemeProvider>;
};
window.ThemeRoot = ThemeRoot;

const ThemeTweaksPanel = () => {
  const [tweaks, setTweak] = useTweaks(THEME_DEFAULTS);

  // Mirror tweaks state into the atom so all screens re-render
  React.useEffect(() => { themeAtom.set(tweaks); }, [
    tweaks.paper, tweaks.rule, tweaks.density, tweaks.stamp, tweaks.serif, tweaks.mono,
  ]);

  const opt = (dim) => THEME_OPTIONS[dim].map(o => ({ value: o.value, label: o.label }));

  return (
    <TweaksPanel title="Tweaks · theme">
      <TweakSection label="Paper">
        <TweakRadio label="warmth" value={tweaks.paper}
          options={opt('paper')} onChange={v => setTweak('paper', v)} />
      </TweakSection>
      <TweakSection label="Wire">
        <TweakRadio label="rule colour" value={tweaks.rule}
          options={opt('rule')} onChange={v => setTweak('rule', v)} />
      </TweakSection>
      <TweakSection label="Layout">
        <TweakRadio label="density" value={tweaks.density}
          options={opt('density')} onChange={v => setTweak('density', v)} />
        <TweakRadio label="stamp" value={tweaks.stamp}
          options={opt('stamp')} onChange={v => setTweak('stamp', v)} />
      </TweakSection>
      <TweakSection label="Type">
        <TweakRadio label="serif" value={tweaks.serif}
          options={opt('serif')} onChange={v => setTweak('serif', v)} />
        <TweakRadio label="mono" value={tweaks.mono}
          options={opt('mono')} onChange={v => setTweak('mono', v)} />
      </TweakSection>
    </TweaksPanel>
  );
};
window.ThemeTweaksPanel = ThemeTweaksPanel;

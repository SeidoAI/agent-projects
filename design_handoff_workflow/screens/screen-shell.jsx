// screen-shell.jsx — shared chrome for every Tripwire screen
// Browser-window wrapper (Field Notebook themed), left nav with the lifecycle wire,
// top bar with project crumb + global search + run pill.
//
// Usage:
//   <Screen tab="Process" url="tripwire.app/marlin/process" active="process">
//     <ScreenContent>...</ScreenContent>
//   </Screen>

// Field-Notebook-themed browser window — overrides the default dark Chrome
// with a cream paper surface that matches our palette.
const FNBrowser = ({ tab = 'Tripwire', url = 'tripwire.app/marlin', children, width = 1440, height = 900 }) => {
  const cBar = '#e0d8c6';   // tab bar — paper-dark
  const cTab = '#f0eee9';   // active tab
  const cText = '#3a342e';
  const cDim = '#9a9285';
  const cUrl = '#e8e4dc';

  return (
    <div style={{
      width, height, borderRadius: 10, overflow: 'hidden', position: 'relative',
      boxShadow: '0 30px 80px rgba(26,24,21,0.18), 0 0 0 1px rgba(26,24,21,0.08)',
      display: 'flex', flexDirection: 'column', background: cBar,
      fontFamily: "'Bricolage Grotesque', system-ui, sans-serif",
    }}>
      {/* tab bar */}
      <div style={{ display: 'flex', alignItems: 'center', height: 38, paddingRight: 10 }}>
        <div style={{ display: 'flex', gap: 8, padding: '0 14px' }}>
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#c83d2e' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#c8861f' }} />
          <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#436b4d' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'flex-end', height: '100%', paddingLeft: 4, flex: 1, gap: 2 }}>
          <FNTab title={tab} active />
          <FNTab title="Marlin · linear" />
          <FNTab title="prs · github" />
        </div>
      </div>
      {/* url bar */}
      <div style={{ height: 38, background: cTab, display: 'flex', alignItems: 'center', gap: 6, padding: '0 10px', borderBottom: '1px solid rgba(26,24,21,0.1)' }}>
        <FNNavBtn>‹</FNNavBtn>
        <FNNavBtn>›</FNNavBtn>
        <FNNavBtn>↻</FNNavBtn>
        <div style={{
          flex: 1, height: 26, borderRadius: 13, background: cUrl,
          display: 'flex', alignItems: 'center', gap: 8, padding: '0 14px', margin: '0 6px',
          fontFamily: "'Geist Mono', ui-monospace, monospace", fontSize: 12, color: cText,
        }}>
          <span style={{ color: '#436b4d', fontSize: 10 }}>●</span>
          <span>{url}</span>
        </div>
        <FNNavBtn>★</FNNavBtn>
        <FNNavBtn>↓</FNNavBtn>
        <div style={{ width: 22, height: 22, borderRadius: '50%', background: '#c83d2e', color: '#fff', fontSize: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Geist Mono', monospace", fontWeight: 600 }}>sk</div>
      </div>
      <div style={{ flex: 1, background: '#f0eee9', overflow: 'hidden', position: 'relative' }}>
        {children}
      </div>
    </div>
  );
};
const FNTab = ({ title, active }) => (
  <div style={{
    height: 30, alignSelf: 'flex-end', padding: '0 14px', display: 'flex',
    alignItems: 'center', gap: 8, background: active ? '#f0eee9' : 'transparent',
    borderRadius: '8px 8px 0 0', minWidth: 140, maxWidth: 220, fontSize: 12,
    color: active ? '#1a1815' : '#6b6359',
    fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: active ? 500 : 400,
    borderTop: active ? '1px solid rgba(26,24,21,0.08)' : '0',
    borderLeft: active ? '1px solid rgba(26,24,21,0.08)' : '0',
    borderRight: active ? '1px solid rgba(26,24,21,0.08)' : '0',
  }}>
    <span style={{ width: 12, height: 12, borderRadius: 2, background: active ? '#c83d2e' : '#9a9285', display: 'inline-block' }} />
    <span style={{ flex: 1, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{title}</span>
  </div>
);
const FNNavBtn = ({ children }) => (
  <button style={{
    width: 24, height: 24, borderRadius: 5, border: 0, background: 'transparent',
    color: '#6b6359', fontSize: 14, lineHeight: 1, cursor: 'default', padding: 0,
    fontFamily: "'Bricolage Grotesque', sans-serif",
  }}>{children}</button>
);

// ─── App chrome inside the browser ─────────────────────────────────────
const Screen = ({ tab, url, active, children }) => (
  <FNBrowser tab={tab} url={url}>
    <div style={{ display: 'flex', height: '100%', color: '#1a1815' }}>
      <SideNav active={active} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <TopBar />
        <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          {children}
        </div>
      </div>
    </div>
  </FNBrowser>
);

// Left rail — vertical wire with lifecycle stations + main nav
const SideNav = ({ active = 'process' }) => {
  const items = [
    { id: 'dashboard',     label: 'overview',     n: '01' },
    { id: 'board',         label: 'board',        n: '02' },
    { id: 'process',       label: 'process',      n: '03' },
    { id: 'graph',         label: 'graph',        n: '04' },
    { id: 'sessions',      label: 'sessions',     n: '05' },
    { id: 'monitor',       label: 'live',         n: '06' },
    { id: 'interventions', label: 'reviews',      n: '07' },
  ];
  return (
    <aside style={{
      width: 200, background: '#e8e4dc', borderRight: '1px solid #c9bfae',
      padding: '20px 0 16px', display: 'flex', flexDirection: 'column', gap: 0,
      flexShrink: 0,
    }}>
      <div style={{ padding: '0 18px 16px' }}>
        {/* mini wordmark */}
        <svg viewBox="-2 24 455 180" width="120" height="48" aria-label="tripwire">
          <path d="M 24 156 L 118 156 Q 133 144 148 156 L 428 156" stroke="#c83d2e" strokeWidth="3" fill="none" strokeLinecap="round" />
          <text x="24" y="132" fontFamily="'Bricolage Grotesque', sans-serif" fontWeight="700" fontSize="118" fill="#1a1815" letterSpacing="-4">tri</text>
          <g transform="rotate(8 133 156)">
            <text x="107" y="132" fontFamily="'Bricolage Grotesque', sans-serif" fontWeight="700" fontSize="118" fill="#1a1815" letterSpacing="-4">p</text>
          </g>
          <text x="159" y="132" fontFamily="'Bricolage Grotesque', sans-serif" fontWeight="700" fontSize="118" fill="#1a1815" letterSpacing="-4">wire</text>
        </svg>
      </div>

      {/* project switcher */}
      <div style={{
        margin: '0 14px 18px', padding: '8px 10px', borderRadius: 4,
        background: '#f0eee9', border: '1px solid #c9bfae',
        display: 'flex', alignItems: 'center', gap: 8,
        fontFamily: "'Geist Mono', monospace", fontSize: 11,
      }}>
        <span style={{
          padding: '1px 5px', border: '1px solid #1a1815', fontWeight: 600, fontSize: 10,
          letterSpacing: '0.06em',
        }}>MRLN</span>
        <span style={{ flex: 1, color: '#3a342e', fontWeight: 500 }}>Marlin</span>
        <span style={{ color: '#9a9285' }}>▾</span>
      </div>

      {/* nav with hairline wire down the side */}
      <div style={{ position: 'relative', flex: 1 }}>
        <div style={{ position: 'absolute', left: 22, top: 4, bottom: 60, width: 1, background: '#c83d2e', opacity: 0.55 }} />
        {items.map((it, i) => {
          const isActive = it.id === active;
          return (
            <div key={it.id} style={{
              padding: '7px 18px 7px 14px', display: 'flex', alignItems: 'center', gap: 10,
              position: 'relative',
              fontSize: 13, fontWeight: isActive ? 600 : 400,
              color: isActive ? '#1a1815' : '#3a342e',
              background: isActive ? '#f0eee9' : 'transparent',
              borderLeft: isActive ? '2px solid #c83d2e' : '2px solid transparent',
              cursor: 'default',
            }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: isActive ? '#c83d2e' : '#f0eee9',
                border: isActive ? '2px solid #c83d2e' : '1.5px solid #c83d2e',
                marginLeft: 0,
              }} />
              <span style={{ flex: 1 }}>{it.label}</span>
              <span style={{ fontFamily: "'Geist Mono', monospace", fontSize: 10, color: '#9a9285' }}>{it.n}</span>
            </div>
          );
        })}
      </div>

      {/* footer — status + help */}
      <div style={{ padding: '12px 18px', borderTop: '1px solid #c9bfae', fontFamily: "'Geist Mono', monospace", fontSize: 10, color: '#6b6359', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#436b4d' }} />
          <span>all systems</span>
        </div>
        <div style={{ color: '#9a9285' }}>v0.34.2 · field</div>
      </div>
    </aside>
  );
};

// Top bar — breadcrumb, search, ambient activity, run button
const TopBar = () => (
  <header style={{
    height: 48, padding: '0 22px', display: 'flex', alignItems: 'center', gap: 16,
    borderBottom: '1px solid #c9bfae', background: '#f0eee9', flexShrink: 0,
    fontFamily: "'Bricolage Grotesque', sans-serif",
  }}>
    {/* crumb */}
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12.5, color: '#3a342e' }}>
      <span style={{ color: '#9a9285' }}>pearl</span>
      <span style={{ color: '#c9bfae' }}>/</span>
      <span style={{ fontWeight: 500 }}>Marlin</span>
      <span style={{ color: '#c9bfae' }}>/</span>
      <span style={{ color: '#9a9285' }}>cross-border-rails</span>
    </div>

    {/* search */}
    <div style={{
      flex: 1, maxWidth: 480, height: 28, borderRadius: 4, padding: '0 10px',
      display: 'flex', alignItems: 'center', gap: 8,
      background: '#e8e4dc', border: '1px solid #c9bfae',
      fontFamily: "'Geist Mono', monospace", fontSize: 11.5, color: '#6b6359',
    }}>
      <span>⌕</span>
      <span style={{ flex: 1 }}>jump to · MRLN-… · concept · file · session</span>
      <span style={{ padding: '1px 5px', border: '1px solid #c9bfae', borderRadius: 3, fontSize: 10, color: '#9a9285' }}>⌘K</span>
    </div>

    <div style={{ flex: 1 }} />

    {/* ambient: sessions + open reviews */}
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, fontFamily: "'Geist Mono', monospace", fontSize: 11, color: '#3a342e' }}>
      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#c83d2e', boxShadow: '0 0 0 3px rgba(200,61,46,0.18)' }} />
        2 executing
      </span>
      <span style={{ color: '#c9bfae' }}>·</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#c8861f' }} />
        2 open reviews
      </span>
      <span style={{ color: '#c9bfae' }}>·</span>
      <span style={{ color: '#9a9285' }}>phase · executing</span>
    </div>

    {/* run / new session */}
    <button style={{
      height: 28, padding: '0 12px', borderRadius: 4, border: '1px solid #1a1815',
      background: '#1a1815', color: '#f0eee9',
      fontFamily: "'Bricolage Grotesque', sans-serif", fontSize: 12, fontWeight: 500,
      display: 'flex', alignItems: 'center', gap: 6, cursor: 'default',
    }}>
      <span style={{ color: '#c83d2e' }}>●</span>
      <span>spawn session</span>
      <span style={{ fontFamily: "'Geist Mono', monospace", fontSize: 10, opacity: 0.6, marginLeft: 4 }}>⇧⌘N</span>
    </button>
  </header>
);

// ─── tiny shared atoms ─────────────────────────────────────────────────
const Stamp = ({ children, kind = 'issue', tone }) => {
  const node = kind === 'node';
  const color = tone || (node ? '#c83d2e' : '#1a1815');
  return (
    <span style={{
      display: 'inline-block', fontFamily: "'Geist Mono', monospace",
      fontWeight: 600, fontSize: 10, letterSpacing: '0.06em',
      padding: '2px 6px', border: `1px solid ${color}`, color: node ? '#fff' : color,
      background: node ? color : 'transparent', textTransform: 'uppercase',
    }}>{children}</span>
  );
};

const Pill = ({ children, dot, variant }) => {
  const styles = {
    base: { display: 'inline-flex', alignItems: 'center', gap: 5, padding: '1px 8px',
      border: '1px solid #c9bfae', borderRadius: 999, fontFamily: "'Geist Mono', monospace",
      fontSize: 10.5, letterSpacing: '0.02em', color: '#3a342e', background: '#f0eee9' },
    ink:  { background: '#1a1815', color: '#f0eee9', borderColor: '#1a1815' },
    red:  { background: '#c83d2e', color: '#fff', borderColor: '#c83d2e' },
    amber:{ background: '#c8861f', color: '#fff', borderColor: '#c8861f' },
    jade: { background: '#436b4d', color: '#fff', borderColor: '#436b4d' },
    ghost:{ background: 'transparent' },
  };
  return (
    <span style={{ ...styles.base, ...(variant ? styles[variant] : {}) }}>
      {dot && <span style={{ width: 5, height: 5, borderRadius: '50%', background: dot }} />}
      {children}
    </span>
  );
};

const Eyebrow = ({ children, color }) => (
  <span style={{
    fontFamily: "'Geist Mono', monospace", fontSize: 10, letterSpacing: '0.18em',
    textTransform: 'uppercase', color: color || '#6b6359',
  }}>{children}</span>
);

const SectionTitle = ({ children, sub }) => (
  <div>
    <h2 style={{
      margin: 0, fontFamily: "'Bricolage Grotesque', sans-serif", fontWeight: 600,
      fontSize: 22, lineHeight: 1.05, letterSpacing: '-0.02em', color: '#1a1815',
    }}>{children}</h2>
    {sub && <div style={{ marginTop: 4, fontFamily: "'Instrument Serif', serif", fontStyle: 'italic', fontSize: 14, color: '#6b6359' }}>{sub}</div>}
  </div>
);

const Card = ({ children, style, flat, ink }) => (
  <div style={{
    background: ink ? '#1a1815' : (flat ? 'transparent' : '#faf8f3'),
    color: ink ? '#f0eee9' : 'inherit',
    border: `1px solid ${ink ? '#1a1815' : '#c9bfae'}`,
    borderRadius: 4, ...style,
  }}>{children}</div>
);

Object.assign(window, {
  FNBrowser, Screen, SideNav, TopBar, Stamp, Pill, Eyebrow, SectionTitle, Card,
});

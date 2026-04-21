# tripwire · asset kit

Brand assets for tripwire. Based on the **B · backward 8° · medium arc** direction:
a Times-Roman wordmark where the `p` has tripped over the red wire.

## Colors

| name  | hex       | use                           |
|-------|-----------|-------------------------------|
| ink   | `#1a1815` | warm near-black · primary      |
| cream | `#f0eee9` | warm off-white · canvas        |
| red   | `#c83d2e` | the wire · accent only         |

## Files

### Wordmarks
- `mark-light.svg` — ink on cream (default)
- `mark-dark.svg` — cream on ink
- `mark-mono-ink.svg` — no accent, transparent bg
- `mark-mono-cream.svg` — no accent, transparent, for dark backgrounds
- `mark-accent.svg` — ink + red wire, transparent bg
- `mark-print.svg` — pure black on white (print / grayscale)

### Icon (tripped p)
- `icon-light.svg` / `icon-dark.svg` — with background
- `icon-trans-ink.svg` / `icon-trans-cream.svg` — transparent
- `favicon.svg` — the canonical SVG favicon
- `favicon-{16,32,48,64,96,128,192,512}.png` — rasterized sizes
- `apple-touch-icon.png` — 180×180 with rounded cream bg
- `maskable-512.png` / `maskable-512-dark.png` — PWA maskable

### Lockups
- `stacked-light.svg` / `stacked-dark.svg` / `stacked-trans.svg` — icon above wordmark

### Social previews
- `social-light.svg` — 1280×640 cream
- `social-dark.svg` — 1280×640 ink

## README snippet (theme-aware)

```html
<picture>
  <source media="(prefers-color-scheme: dark)"  srcset="./docs/mark-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./docs/mark-light.svg">
  <img alt="tripwire" src="./docs/mark-light.svg" width="360">
</picture>
```

## HTML head

```html
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="icon" type="image/png" sizes="16x16" href="/favicon-16.png">
<link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
<link rel="manifest" href="/site.webmanifest">
```

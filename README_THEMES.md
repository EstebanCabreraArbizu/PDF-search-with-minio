# @richard-paredes-1/corp-style

**Liderman Cyber-Midnight** — CSS-only tokens, themes, and component styles with glassmorphism effects.

Framework-agnostic design system. Works with React, Vue, Svelte, Angular, or plain HTML. Zero JavaScript required.

![GitHub Packages](https://img.shields.io/badge/registry-GitHub_Packages-0c1620?style=flat-square&labelColor=050a0f&color=00e5ff)
![CSS only](https://img.shields.io/badge/core-CSS_only-0c1620?style=flat-square&labelColor=050a0f&color=00e5ff)
![30 components](https://img.shields.io/badge/components-30-0c1620?style=flat-square&labelColor=050a0f&color=00e676)
![4 themes](https://img.shields.io/badge/themes-4-0c1620?style=flat-square&labelColor=050a0f&color=7c3aed)

---

## Features

- **100+ Design Tokens** — Colors, typography, spacing, motion, shadows, all under `--fa-*`
- **4 Themes** — Dark, Light, Corp, Corp Dark — switched with a single `data-theme` attribute
- **Glassmorphism** — Acrylic surfaces with `backdrop-filter`, noise texture, and fallbacks
- **30 Components** — Buttons to calendars, all CSS-only
- **Accessible** — `:focus-visible` rings, WCAG AA contrast, `prefers-reduced-motion` support
- **Tree-shakable** — Import the full bundle or individual files

---

## Installation

This package is hosted on **GitHub Packages** (private registry).

### 1. Configure your `.npmrc`

Add this to your project's `.npmrc` (at the project root):

```ini
@richard-paredes-1:registry=https://npm.pkg.github.com
//npm.pkg.github.com/:_authToken=<YOUR_GITHUB_PAT_TOKEN>
```

> Your token needs `read:packages` scope.
> Generate one at: **GitHub → Settings → Developer settings → Personal access tokens**

### 2. Install

```bash
# pnpm
pnpm add @richard-paredes-1/corp-style

# npm
npm install @richard-paredes-1/corp-style

# yarn
yarn add @richard-paredes-1/corp-style
```

## Quick Start

### Import the full bundle

```js
// JS / framework entry file
import "@richard-paredes-1/corp-style";
```

```css
/* CSS entry file */
@import url("@richard-paredes-1/corp-style");
```

```html
<!-- HTML link tag -->
<link rel="stylesheet" href="node_modules/@richard-paredes-1/corp-style/dist/index.css" />
```

### Set a theme

```html
<!-- Dark (default) -->
<html data-theme="dark">

<!-- Light -->
<html data-theme="light">

<!-- Corporate -->
<html data-theme="corp">

<!-- Corporate Dark -->
<html data-theme="corp-dark">
```

### Switch theme at runtime

```js
const themes = ["dark", "light", "corp", "corp-dark"];

function cycleTheme() {
  const html = document.documentElement;
  const current = html.getAttribute("data-theme") || "dark";
  const next = themes[(themes.indexOf(current) + 1) % themes.length];
  html.setAttribute("data-theme", next);
}
```

---

## Components

### Button

```html
<button class="btn btn--primary">Deploy</button>
<button class="btn btn--ghost">Cancel</button>
<button class="btn btn--outline">View</button>
<button class="btn btn--danger btn--sm">Delete</button>
<button class="btn btn--primary btn--lg">Confirm</button>
```

### Input / Textarea / Select

```html
<label class="input-label">Username</label>
<input class="input" type="text" placeholder="Enter value..." />
<input class="input input--error" type="text" />
<input class="input input--success" type="text" />

<textarea class="textarea" rows="4" placeholder="Message..."></textarea>

<select class="select">
  <option>Option A</option>
  <option>Option B</option>
</select>
```

### Search Input

```html
<div class="search-input">
  <span class="search-input__icon">⌕</span>
  <input class="search-input__field" type="search" placeholder="Search..." />
</div>
```

### Checkbox & Toggle

```html
<label class="checkbox">
  <input type="checkbox" class="checkbox__input" />
  <span class="checkbox__box"></span>
  <span class="checkbox__label">Enable feature</span>
</label>

<label class="toggle">
  <input type="checkbox" class="toggle__input" />
  <span class="toggle__track"><span class="toggle__thumb"></span></span>
  <span class="toggle__label">Active</span>
</label>
```

### Card

```html
<div class="card">
  <div class="card__header">
    <span class="card__header-title">System Status</span>
  </div>
  <div class="card__body">Content here</div>
  <div class="card__footer">
    <button class="btn btn--primary btn--sm">Action</button>
  </div>
</div>

<!-- Glassmorphism variant -->
<div class="card card--acrylic">...</div>
```

### Badge & Tag

```html
<span class="badge">DEFAULT</span>
<span class="badge badge--success">ONLINE</span>
<span class="badge badge--warning">PENDING</span>
<span class="badge badge--danger">CRITICAL</span>
<span class="badge badge--info">INFO</span>

<span class="tag">JavaScript</span>
<span class="tag tag--blue">TypeScript</span>
<span class="tag tag--removable">
  CSS <button class="tag__remove">×</button>
</span>
```

### Notification Badge

```html
<div class="notif-badge-wrap">
  <button class="btn btn--ghost btn--icon">🔔</button>
  <span class="notif-badge">3</span>
</div>
```

### Tabs

```html
<div class="tabs" role="tablist">
  <button class="tab tab--active" role="tab">Overview</button>
  <button class="tab" role="tab">Analytics</button>
  <button class="tab" role="tab">Logs</button>
</div>
```

### Toast & Alert

```html
<div class="toast toast--success">
  <div class="toast__icon">✓</div>
  <div class="toast__content">
    <div class="toast__title">Success</div>
    <div class="toast__message">Operation completed.</div>
  </div>
  <button class="toast__close">×</button>
</div>

<div class="alert alert--warning">
  <div class="alert__icon">⚠</div>
  <div class="alert__content">
    <div class="alert__title">Warning</div>
    <div class="alert__message">Check your configuration.</div>
  </div>
</div>
```

### Progress

```html
<div class="progress">
  <div class="progress__bar" style="width: 72%"></div>
</div>

<div class="progress progress--success">
  <div class="progress__bar" style="width: 100%"></div>
</div>

<div class="progress progress--thin progress--striped progress--animated">
  <div class="progress__bar" style="width: 45%"></div>
</div>
```

### Modal

```html
<div class="modal" role="dialog" aria-modal="true">
  <div class="modal__backdrop"></div>
  <div class="modal__panel">
    <div class="modal__header">
      <span class="modal__title">Confirm Action</span>
      <button class="modal__close btn btn--ghost btn--icon">×</button>
    </div>
    <div class="modal__body">Are you sure?</div>
    <div class="modal__footer">
      <button class="btn btn--ghost">Cancel</button>
      <button class="btn btn--primary">Confirm</button>
    </div>
  </div>
</div>
```

### Topbar

```html
<header class="topbar">
  <div class="topbar__brand">MyApp</div>
  <nav class="topbar__nav">
    <a href="#" class="topbar__nav-link topbar__nav-link--active">Home</a>
    <a href="#" class="topbar__nav-link">About</a>
  </nav>
  <div class="topbar__actions">
    <button class="btn btn--ghost btn--sm">Sign In</button>
  </div>
</header>
```

### Breadcrumb

```html
<nav class="breadcrumb" aria-label="Breadcrumb">
  <ol class="breadcrumb__list">
    <li class="breadcrumb__item">
      <a href="#" class="breadcrumb__link">Home</a>
    </li>
    <li class="breadcrumb__item">
      <a href="#" class="breadcrumb__link">Settings</a>
    </li>
    <li class="breadcrumb__item breadcrumb__item--active" aria-current="page">
      Profile
    </li>
  </ol>
</nav>
```

### Nav Item (Sidebar)

```html
<nav class="sidebar">
  <div class="sidebar__header">
    <div class="sidebar__title">CORP_SYSTEM</div>
  </div>
  <ul class="nav-list">
    <li><a href="#" class="nav-item nav-item--active">Dashboard</a></li>
    <li><a href="#" class="nav-item">Reports</a></li>
    <li><a href="#" class="nav-item">Settings</a></li>
  </ul>
</nav>
```

### Toolbar

```html
<div class="toolbar">
  <div class="toolbar__group">
    <button class="toolbar__btn toolbar__btn--active">Bold</button>
    <button class="toolbar__btn">Italic</button>
  </div>
  <div class="toolbar__separator"></div>
  <div class="toolbar__group">
    <button class="toolbar__btn">Align Left</button>
  </div>
</div>
```

### Section Header

```html
<div class="section-header">
  <h2 class="section-header__title">User Management</h2>
  <p class="section-header__subtitle">Manage access and roles</p>
  <div class="section-header__actions">
    <button class="btn btn--primary btn--sm">Add User</button>
  </div>
</div>
```

### Divider

```html
<hr class="divider" />
<hr class="divider divider--accent" />

<div class="divider divider--labeled">
  <span class="divider__label">OR</span>
</div>
```

### Table

```html
<div class="table-wrap">
  <table class="table">
    <thead>
      <tr>
        <th class="table__th">Name</th>
        <th class="table__th">Status</th>
        <th class="table__th">Role</th>
      </tr>
    </thead>
    <tbody>
      <tr class="table__row">
        <td class="table__td">Alice</td>
        <td class="table__td"><span class="badge badge--success">Active</span></td>
        <td class="table__td">Admin</td>
      </tr>
    </tbody>
  </table>
</div>
```

### Pagination

```html
<nav class="pagination" aria-label="Pagination">
  <button class="pagination__btn" aria-label="Previous">‹</button>
  <button class="pagination__btn pagination__btn--active">1</button>
  <button class="pagination__btn">2</button>
  <button class="pagination__btn">3</button>
  <button class="pagination__btn" aria-label="Next">›</button>
</nav>
```

### Avatar

```html
<div class="avatar">
  <img class="avatar__img" src="photo.jpg" alt="Alice" />
</div>

<div class="avatar avatar--lg avatar--online">
  <span class="avatar__initials">AL</span>
  <span class="avatar__status"></span>
</div>

<div class="avatar-group">
  <div class="avatar"><img class="avatar__img" src="a.jpg" alt="A" /></div>
  <div class="avatar"><img class="avatar__img" src="b.jpg" alt="B" /></div>
  <div class="avatar"><span class="avatar__initials">+3</span></div>
</div>
```

### Tooltip

```html
<div class="tooltip-wrap">
  <button class="btn btn--ghost">Hover me</button>
  <div class="tooltip">This is a tooltip</div>
</div>

<div class="tooltip-wrap">
  <span>Target</span>
  <div class="tooltip tooltip--right">Right side</div>
</div>
```

### List Item

```html
<ul class="list">
  <li class="list-item list-item--active">
    <span class="list-item__icon">📁</span>
    <div class="list-item__content">
      <div class="list-item__title">Documents</div>
      <div class="list-item__subtitle">32 files</div>
    </div>
    <span class="list-item__meta">2h ago</span>
  </li>
</ul>
```

### Feed Post

```html
<article class="feed-post">
  <div class="feed-post__header">
    <div class="avatar avatar--sm"><span class="avatar__initials">RP</span></div>
    <div class="feed-post__meta">
      <span class="feed-post__author">Richard Paredes</span>
      <span class="feed-post__time">5 min ago</span>
    </div>
  </div>
  <div class="feed-post__body">Content of the post goes here.</div>
  <div class="feed-post__footer">
    <button class="feed-post__action">👍 Like</button>
    <button class="feed-post__action">💬 Comment</button>
  </div>
</article>
```

### Chat Bubble

```html
<div class="chat-bubble chat-bubble--outgoing">
  <div class="chat-bubble__text">Hello! How are you?</div>
  <span class="chat-bubble__time">10:30</span>
</div>

<div class="chat-bubble">
  <div class="chat-bubble__text">I'm good, thanks!</div>
  <span class="chat-bubble__time">10:31</span>
</div>
```

### Icon Button

```html
<button class="icon-btn">⚙</button>
<button class="icon-btn icon-btn--primary">✓</button>
<button class="icon-btn icon-btn--danger icon-btn--sm">✕</button>
```

### Calendar

```html
<div class="calendar">
  <div class="calendar__header">
    <button class="calendar__nav-btn">‹</button>
    <span class="calendar__title">February 2026</span>
    <button class="calendar__nav-btn">›</button>
  </div>
  <div class="calendar__grid">
    <div class="calendar__day-name">Mon</div>
    <div class="calendar__day">1</div>
    <div class="calendar__day calendar__day--today">25</div>
    <div class="calendar__day calendar__day--selected">26</div>
  </div>
</div>
```

### Acrylic (Glassmorphism)

```html
<div class="acrylic">Default glass surface</div>
<div class="acrylic acrylic--strong">Stronger blur</div>
<div class="acrylic acrylic--subtle">Subtle glass</div>
<div class="acrylic acrylic--noise">With noise texture</div>
<div class="acrylic acrylic--tint">With color tint</div>
```

---

## Granular Imports

Import only what you need for smaller bundles:

```css
@import url("@richard-paredes-1/corp-style/tokens");
@import url("@richard-paredes-1/corp-style/theme/dark");
@import url("@richard-paredes-1/corp-style/theme/light");
@import url("@richard-paredes-1/corp-style/acrylic");
```

Individual components:

```css
@import url("@richard-paredes-1/corp-style/components/button.css");
@import url("@richard-paredes-1/corp-style/components/card.css");
@import url("@richard-paredes-1/corp-style/components/modal.css");
```

---

## Token Reference

All tokens use the `--fa-` prefix.

| Category   | Example Token              | Description                  |
|------------|----------------------------|------------------------------|
| Color      | `--fa-color-accent`        | Primary accent color         |
| Color      | `--fa-color-bg-surface-1`  | Card / panel background      |
| Color      | `--fa-color-text-primary`  | Main text color              |
| Color      | `--fa-color-success`       | Success green                |
| Color      | `--fa-color-danger`        | Error / danger red           |
| Typography | `--fa-font-size-base`      | 1rem (16px)                  |
| Typography | `--fa-font-size-lg`        | 1.35rem                      |
| Typography | `--fa-font-family`         | UI font stack                |
| Spacing    | `--fa-space-2`             | 0.5rem (8px)                 |
| Spacing    | `--fa-space-4`             | 1rem (16px)                  |
| Shadow     | `--fa-shadow-md`           | Medium elevation shadow      |
| Shadow     | `--fa-glow-box`            | Accent glow effect           |
| Motion     | `--fa-duration-normal`     | 200ms transition             |
| Radius     | `--fa-radius-full`         | 9999px (pill shape)          |

---

## Accessibility

- **Focus rings** — All interactive elements use `:focus-visible` with a high-contrast ring
- **Contrast** — Dark theme text achieves ~14:1 contrast ratio against surfaces
- **Reduced motion** — `@media (prefers-reduced-motion: reduce)` disables all transitions and animations
- **Semantic HTML** — Components are designed around native elements: `<button>`, `<a>`, `<input>`, `role="tablist"`, `aria-selected`, `aria-current`

---

## Browser Support

| Browser        | Minimum version |
|----------------|-----------------|
| Chrome / Edge  | 76+             |
| Firefox        | 103+            |
| Safari         | 14+             |

`backdrop-filter` degrades gracefully to a solid background on unsupported browsers.

---

## Development

```bash
# Install dependencies (from monorepo root)
pnpm install

# Build the package
pnpm build

# Start the playground (Vite dev server)
pnpm dev
```

---

## Publishing a New Version

```bash
# 1. Bump the version
cd packages/core
npm version patch   # 1.0.0 → 1.0.1
npm version minor   # 1.0.0 → 1.1.0
npm version major   # 1.0.0 → 2.0.0

# 2. Build and publish
pnpm build
pnpm publish --no-git-checks
```

---

## License

MIT © Richard Paredes

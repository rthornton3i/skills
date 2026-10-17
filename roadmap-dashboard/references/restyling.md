# Restyling the dashboard

The look lives in the shell files, not in a template. The palette and functional tokens (`--bg`, `--surface`, `--accent`, `--status-*`, ...) are defined in the stub `index.html` and used by `styles.css`; rendering is in `app.js` (router) and `tab-plan.js`, `tab-flow.js`, `tab-map.js`, `tab-git.js`.

To reskin for a project: edit the shell files in the skill's `assets/shell/` (then `RM sync-shell --force` copies them into the project). Pick a new 4-6 color set, keep the token NAMES so light and dark theming keep working, and change fonts in `styles.css`. Check with `RM serve` in light, dark and at 375 px width, and run `node --check` on each `.js` file before publishing. Keep `index.html` small: it is read on every publish.

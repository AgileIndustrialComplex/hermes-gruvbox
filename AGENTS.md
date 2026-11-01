# AGENTS.md

Instructions for anyone (agent or human) changing this repo, plus the deeper
documentation that deliberately does not live in the README.

The README is intentionally minimal: what the pack is, the combined hero
screenshot, installation, usage, the six individual screenshots, and the credits
and license. Everything
else goes here or in `docs/`. Keep it that way.

## Repo layout

| Path | What it is |
|---|---|
| `plugin.yaml` | Manifest: id, `version`, description, `requires_hermes`, tags. |
| `__init__.py` | `register(ctx)` — the plugin entry point. |
| `installer.py` | Writes the skins and the receipt, handles uninstall/restore and user-edit protection. Holds `VERSION` (keep in step with `plugin.yaml`). |
| `skins/*.yaml` | The six skins. Each is a standalone Hermes skin file — no build step, no shared generator. |
| `skins/index.json` | Metadata per skin: `skin` (display name), `slug`, `label`, `mode`, `description`. |
| `desktop/plugin.js` | The Desktop half (generated — see below). |
| `tests/` | stdlib `unittest`, no Hermes needed to run. |
| `docs/` | `hero.png`, `screenshots/`, `social-preview.png`, `preview.html`. |

## Invariants — do not break these

* **The pack never edits `config.yaml` and never switches the active skin.** It
  writes only its own files in `<hermes home>/skins/` and its receipt.
* **Never overwrite a skin the user edited**, or a same-named file that was
  already there, and never follow a symlink out of the profile. Retiring an old
  name is only allowed while the file is still byte-for-byte ours; anything the
  user edited is left on disk and forgotten about.
* **Loading the plugin installs skins; it never selects one.** The theme a user
  sees is chosen in the Desktop app's picker.
* **Naming:** display-cased `<Family> <Mode> <Contrast>` (`Gruvbox Light Hard`), kebab slug in `index.json`. Keep colours in `#rrggbb` form. Never ship a
  built-in-style name (`default`, `mono`, `nous`, …).
* **No network access, background processes, hooks, middleware, tools,
  credentials or telemetry.** Nothing runs on a turn.
* **`desktop/plugin.js` must be regenerated** whenever a skin's palette, name or
  description changes — `tests/test_desktop_half.py` fails on drift, by design.
* **Version bumps touch two files together:** `plugin.yaml` and `VERSION` in
  `installer.py`.

## Tests and gates

```bash
python3 -m unittest discover -s tests      # stdlib only, no Hermes needed
hermes plugins validate .                  # the catalog CI gate
hermes plugins doctor . --ci               # real discovery + register(ctx)
```

A linked dev checkout (symlinked into `~/.hermes/plugins/`) hot-reloads like any
plugin; the six skins are then in `<hermes home>/skins/`.

Never leave the tester's active skin switched: restore `display.skin` to
`default` after exercising the pack.

## Adding a theme

Drop `skins/<Name>.yaml` (a full skin file with a `name:` and a `colors:` map) and
an entry in `skins/index.json`. The test suite reads the index, so a rename needs
no test edits. Regenerate the Desktop half afterwards.

## Regenerating the Desktop half

`desktop/plugin.js` embeds the six themes, so it must be regenerated whenever a
skin's palette, name or description changes. The palettes are not hand-written:
they are what the app's own converter produces for each skin, which is why they
cannot be derived in Python. With a Hermes checkout at hand:

1. Dump the six skin payloads — the exact object the Desktop receives:
   `<checkout>/venv/bin/python -c "from tui_gateway.change_watcher import skin_payload …"`
   over every `skins/<Name>.yaml`.
2. Run `skinToDesktopTheme` on them in the app (a throwaway vitest under
   `apps/desktop/`, importing `@/themes/skin`) and dump the resulting
   `DesktopTheme` objects as JSON.
3. Inline that JSON between the `BEGIN/END GENERATED THEMES` markers, taking
   `label` and `description` from `skins/index.json`, and keep the exports and the
   single `@hermes/plugin-sdk` import as they are.
4. `hermes plugins validate .` — the desktop-surface lint rejects `eval`, dynamic
   imports and app-DOM reach, so a half that steps outside the SDK fails review
   here rather than in someone's app.

## Documentation moved out of the README

### What it does on your system

* Writes `<hermes home>/skins/<Name>.yaml` for the six themes, plus a receipt
  at `<hermes home>/theme-packages/hermes-gruvbox.json`.
* Never overwrites a skin you edited, or a file of the same name that was already
  there, and never follows a symlink out of the profile.
* Renaming is handled: a skin an earlier version installed under another name is
  removed on the next load — but only while the file is still byte-for-byte ours.
  Anything you edited is left on disk and simply forgotten about.
* `uninstall()` removes only files that are still byte-for-byte the pack's,
  restores anything it replaced, and sets `disabled` in the receipt so the skins do
  not come back on the next load; `install()` reverses it. Nothing in the pack
  calls either of these — they are the library's cleanup path, covered by tests.
* Editing an installed skin file by hand is respected: the pack sees the file is
  no longer byte-for-byte its own and never overwrites it again.

### The Desktop half

The Desktop app's theme picker (Settings → Appearance, and ⌘K) is fed by a
different source than the pack's skins: it knows the built-in themes, anything a Desktop
plugin contributes, and **only the one skin the backend currently has active** —
so a pack of six skins shows up there as whatever you have activated so far,
and the app hard-codes `Hermes skin` as the description for a skin-derived entry
(`skinToDesktopTheme` in `apps/desktop/src/themes/skin.ts`).

`desktop/plugin.js` is the fix: it contributes all six as first-class Desktop
themes, so the picker lists `Gruvbox Dark Hard` … `Gruvbox Light Soft`
with the same descriptions `skins/index.json` carries, each with the palette the app's own
converter derives from the matching skin.

Install it from the app itself:

1. Open the app's **Capabilities → Plugins** page (older builds: Settings →
   Plugins) → **Install**, and paste `AgileIndustrialComplex/hermes-gruvbox`.
   (On a Desktop running on the same machine as Hermes, the half is also copied
   out of the installed agent package automatically.)
2. The same page then lists a **Gruvbox Themes** row, off by default (the app
   treats the half of a unified package as opt-in). Turn it on.
3. The six themes are in the picker immediately — no reload.

Notes:

* Picking one there changes the **Desktop** appearance, exactly like picking a
  built-in theme; it does not write `display.skin`. The Desktop is the only
  surface these themes paint.
* Turning the row off (or removing the plugin) takes the six back out of the
  picker.
* `/skin` in the app is the Desktop's own command — it lists the same themes.

#### Stale rows in the picker

The Desktop caches **every skin it has seen active** —
`hermes-desktop-backend-themes-v1` in the app's `localStorage` — and only prunes
built-ins, so a skin that later disappears keeps a row, showing its name and the
app's hard-coded `Hermes skin` description. That is what the 1.0.0 names
(`gruvbox-dark`, `gruvbox-light-soft`, …) do after the 1.1.0 rename. The ✕ in
Appearance only removes user-installed themes, so the cache itself is the way out:

1. **⌥⌘I** (macOS) / **Ctrl⇧I** (Linux, Windows) — or **View → Toggle Developer
   Tools**.
2. Console tab, paste:

   ```js
   const k = 'hermes-desktop-backend-themes-v1'
   console.log(Object.keys(JSON.parse(localStorage.getItem(k) || '{}'))) // what is cached
   localStorage.removeItem(k)
   ```

3. **View → Force Reload** (⌘⇧R). The six contributed themes stay — they come
   from this plugin, not the cache — and the app re-seeds the active skin on the
   next connect. Nothing is lost: the cache is fed by activations, so any skin you
   still have re-appears the moment you use it.

To drop individual names instead of the whole cache, delete those keys from the
parsed object and `setItem` it back before reloading.

### The palettes

| Role | Gruvbox dark | Gruvbox light |
|---|---|---|
| Background (medium) | `#282828` | `#fbf1c7` |
| Background (hard / soft) | `#1d2021` / `#32302f` | `#f9f5d7` / `#f2e5bc` |
| Body text | `#ebdbb2` | `#3c3836` |
| Accent (headings, links, tool `●`) | `#fabd2f` yellow | `#af3a03` orange |
| Success / warn / error | `#b8bb26` / `#fe8019` / `#fb4934` | `#79740e` / `#b57614` / `#9d0006` |
| Borders | `#665c54` | `#bdae93` |
| Syntax string / number / keyword / comment | `#b8bb26` / `#d3869b` / `#fb4934` / `#928374` | `#79740e` / `#8f3f71` / `#9d0006` / `#928374` |

Light skins use the faded accents rather than the bright ones — the bright set is
tuned for a dark background and fails WCAG AA on cream. Measured with the Desktop's
own converter (`skinToDesktopTheme`): every Gruvbox accent is painted exactly as
authored, in the 4.8–8.2:1 range, and every body text colour clears AA as shipped.

### Image assets

* `docs/hero.png` — the README banner. One window cut into six equal-area slanted
  strips at 15° (light hard → medium → soft, dark hard → medium → soft), each
  copied 1:1 from a screenshot of that skin at the place it occupies in the result.
  The six screenshots share one geometry (identical window bounds, scale 1.0, shift
  0 in both axes), so nothing is resampled and content crossing a cut line lines
  up. The window box is found from the alpha channel — `x=111 y=76 w=2582 h=1889`,
  which is also the `--bbox` to pass if detection ever guesses wrong — and every
  strip comes out at 812,899 px.
* `docs/screenshots/` — the six individual variants, 1600 px wide.
* `docs/social-preview.png` — 1280×640, the composite cropped to a 2:1 band; upload
  it under **Settings → Social preview**.

All of them are cropped tight to the window: no transparent margin, so the viewer's
page colour cannot show through as a frame. Only the rounded corners carry alpha
(0.2–0.4% of pixels). Screenshots come from the same session with the same window
size, which is what makes the strips line up.

### Changelog

**1.0.0** — first release: six Gruvbox themes for the Hermes Desktop app — dark and
light, each in hard, medium and soft — contributed to the app's own theme picker by
`desktop/plugin.js`, with the skins installed into `<hermes home>/skins/` on load.

### License

MIT — see [LICENSE](LICENSE). The palettes are Pavel Pertsev's
[morhetz/gruvbox](https://github.com/morhetz/gruvbox), also MIT.

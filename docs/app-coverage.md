# Which preinstalled apps needed an overlay, and which did not

"Theme all the system apps" turned out to mean something narrower than it
sounds, and the reason is worth writing down: **most preinstalled apps need
nothing.**

## The triage

Two questions decide whether an app needs a per-app overlay.

**Does it define its own surfaces at all?** Nearly every app that ships inside
`frameworks/base/packages` defines **zero** surface colours of its own. They use
platform `DeviceDefault` themes, so the framework overlay from Phase 1 already
reaches their dialogs, menus, backgrounds and accents. `PackageInstaller`,
`VpnDialogs`, `CredentialManager`, `PrintSpooler`, `SimAppDialog`, `SoundPicker`
and the rest of that list are already themed and were never going to need a file.

**Do its colours already follow the system palette?** An app whose surfaces
resolve to `@android:color/system_*` is wallpaper-driven, and every modern
LineageOS app is: Jelly, Glimpse, Twelve, Recorder and Aperture all parent from
`Theme.Material3.DayNight`, whose surfaces come from dynamic colour. Overriding
those with FacetUI's own values would make them *less* coherent, not more — it
would pin them to one hue and break their colour following on every wallpaper
that is not blue.

So a per-app overlay is only warranted where an app's **structural surfaces are
hardcoded** and follow nothing.

## What that leaves

| App | Package | Why |
|---|---|---|
| Settings | `com.android.settings` | Header, list and dialog surfaces on the neutral ramp; moved to the accent ramp |
| Files | `com.android.documentsui` | `@android:color/white` backgrounds and a fixed `#1E88E5` primary, both predating dynamic colour |
| Calendar | `org.lineageos.etar` | 234 hardcoded colours; the structural ones moved, the event colours left alone |
| Clock | `com.android.deskclock` | One hardcoded shortcut background, which sits next to the FacetUI icons in the launcher |

And what needed nothing:

| App | Why not |
|---|---|
| Dialer, Contacts, Messaging | Action bars and primaries already resolve to `@android:color/system_accent1_*` |
| Jelly, Glimpse, Twelve, Recorder, Aperture | Material3 `DayNight`, fully dynamic |
| Seedvault, SetupWizard, Updater | Accents already dynamic; the rest is incidental |
| Calculator | No surface colours; platform themed |
| Everything in `frameworks/base/packages` | Platform `DeviceDefault`, covered by the framework overlay |

## The rule this produced

> The FacetUI move is **neutral-to-accent**, not dynamic-to-fixed.

Stock puts large surfaces on `system_neutral1_*` — the grey ramp. FacetUI moves
them to `system_accent2_*`, the muted accent ramp. Same wallpaper-derived
palette, read off a tinted ramp instead of a grey one, so surfaces carry the
wallpaper's hue the way the shade already does. `accent2` rather than `accent1`
because large areas want the muted ramp; `accent1` at those weights is loud.

This was learned the hard way. The first Settings overlay in this repository
replaced those dynamic references with fixed hex, which pinned the app to one
blue. That is the opposite of FacetUI's founding rule — *pull the tint from the
system accent so the panel samples the wallpaper rather than flattening it* —
and `validate-overlays.py` now fails any override that does it, unless the
resource is in `LITERAL_INTENTIONAL` with a reason.

The only entries on that list are the keyboard's, where a surface has to be
translucent and resource XML cannot apply alpha to a colour *reference*. That
trade-off is real and is named where it is made.

## Why per-app work stops at colour

An app's header, cards and list backgrounds are **views inside the app's single
window**. Android has no backdrop blur for a view: a view can blur its own
content, not what is painted beneath it in the same window. Only windows blur
what is behind them — which is why dialogs, menus and the keyboard could be made
glass, and an app bar cannot.

Settings narrows it further: its dialogs are AppCompat, bundled into the APK
rather than inherited from the platform, so the framework dialog glass does not
reach them. Overriding a bundled AppCompat theme would mean restating every item
it declares, and its source is not in the tree to read — so it is left alone.

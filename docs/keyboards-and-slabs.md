# Physical keyboards and slabs, from one image

octagonOS targets two quite different phones:

| | |
|---|---|
| **keyboard** | A physical-keyboard slider or candybar, Titan-class. Often a near-square display. The framework suppresses the virtual keyboard whenever the hardware one is open, so the IME that matters is the physical-keyboard one |
| **slab** | An ordinary touchscreen phone. Tall display, virtual keyboard |

A GSI is by definition not built per device, and which of these it is running on
is not knowable at build time. So it is resolved at first boot instead.

## Detection

`product/octagonos/bin/octagonos-formfactor.sh` reads `/proc/bus/input/devices`
rather than asking the framework: it runs early, and the kernel populates that
table before any of Android is up.

Each device advertises a `KEY` capability bitmask, printed as whitespace-
separated 64-bit hex groups, most significant first. Every key that matters is
below bit 64, so only the **last** group is read:

| Row | Codes | Bits |
|---|---|---|
| Top | `KEY_Q` – `KEY_P` | 16–25 |
| Home | `KEY_A` – `KEY_L` | 30–38 |
| Bottom | `KEY_Z` – `KEY_M` | 44–50 |

**All three rows are required.** A volume rocker advertises `EV_KEY` too, as
does a headset button and a d-pad; requiring a full alphabet is what separates a
keyboard from them. Getting this wrong is bad in both directions and silent
either way — a slab misdetected as a keyboard phone gets the wrong default IME,
and a keyboard phone misdetected as a slab types into the wrong one on first
boot.

The result is recorded as `persist.octagonos.formfactor`.

## It is tested

```bash
tools/test-formfactor-detect.sh
```

Seven cases, extracted from the real script so the test cannot drift from the
code it tests:

| Case | Expected |
|---|---|
| Alphabetic keypad present | `keyboard` |
| Volume rocker and power only — bits 114–116, in the group *above* the one read | `slab` |
| Numeric keypad, no letter rows | `slab` |
| Top and home rows but no bottom row | `slab` |
| Alphabet plus bit 63 — wraps negative in 64-bit shell arithmetic | `keyboard` |
| Malformed bitmask | `slab`, no crash |
| No input table at all | `slab` |

The fixtures are **synthetic**: the bitmasks are constructed from the Linux
input event codes, not captured from hardware, because there is no device here
to capture from. They exercise the arithmetic, not the question of what a
particular phone actually reports. Confirming *that* is an open item in
[status.md](status.md).

## What differs between the two

Less than you might expect, which is deliberate — a shade is a shade.

| | keyboard | slab |
|---|---|---|
| FacetUI glass on shade, notifications, lockscreen, homescreen | yes | yes |
| Boot animation | yes — the square canvas is centred correctly on both, which is why it is square | yes |
| `FacetUIIME` keyboard glass | enabled | enabled |
| Default IME set to a physical-keyboard IME | yes, if one was injected | no |

The keyboard overlay is enabled on both. On a physical-keyboard phone the IME
window is suppressed while the hardware keyboard is open, but it still appears
when the slider is closed, so the glass is wanted there too — it is simply on
screen less often.

## Reading the IME component, if you inject one

A keyboard's `applicationId` and its IME class need not share a namespace;
`applicationIdSuffix` does not move the Java package. The short form expands to
a class that may not exist, and the keyboard then installs, flashes and boots
while **silently never activating**. Read it out of the APK:

```bash
aapt2 dump xmltree <keyboard.apk> --file AndroidManifest.xml | grep -A3 service
# with no SDK: python3 titan2e-eos/tools/axml.py <keyboard.apk>
```

## The SELinux gap

The first-boot service ships with no `seclabel`, deliberately: the obvious
choice, `u:r:su:s0`, exists only on userdebug and eng builds, and on a user
build init refuses to start a service whose label does not resolve.

With no label, init runs it in the domain the executable's file context maps to,
and on an enforcing build that domain will not hold the permissions the script
needs — `setprop` on `persist.octagonos.*`, `cmd overlay`, `ime`. **A proper
domain and policy are still owed.** The likeliest symptom if this is ignored is
that everything runs, is denied, and the system simply looks stock.

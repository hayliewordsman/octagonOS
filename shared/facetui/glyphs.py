"""
FacetUI icon glyphs, and what they map to.

Each glyph is SVG path data on a 100x100 viewport, drawn to sit inside the
adaptive-icon safe zone. They are deliberately geometric -- straight runs,
circles, single-weight strokes -- because that is what survives being rendered
in glass: a detailed glyph disappears under a specular highlight, and a
gradient-filled one fights the surface it sits on.

Everything here is authored as OUTLINES, not strokes: a stroked path scales by
line width and an outlined one does not, so the same data renders correctly as
a 48px launcher icon and a 512px preview.

`APPS` maps a component (or a bare package, which matches any activity in it)
to a glyph and a hue. The hue positions the glyph's own tint around FacetUI's
accent range; it does not recolour the glass, which is shared.
"""

# --- glyph library ----------------------------------------------------------
#
# Coordinates are on 0..100. The safe zone for an adaptive icon foreground is
# the middle ~66%, so glyphs are built inside roughly 20..80 and never assume
# the corners survive.

GLYPHS = {
    # A gear: eight teeth, because the system this is for has eight facets.
    "settings": (
        "M50,20 L56,21.2 L58.5,27.5 L64.8,25.8 L69.4,30.6 L66.5,36.4 "
        "L72.5,39.8 L73.5,46.2 L67.4,48.5 L67.4,51.5 L73.5,53.8 L72.5,60.2 "
        "L66.5,63.6 L69.4,69.4 L64.8,74.2 L58.5,72.5 L56,78.8 L50,80 "
        "L44,78.8 L41.5,72.5 L35.2,74.2 L30.6,69.4 L33.5,63.6 L27.5,60.2 "
        "L26.5,53.8 L32.6,51.5 L32.6,48.5 L26.5,46.2 L27.5,39.8 L33.5,36.4 "
        "L30.6,30.6 L35.2,25.8 L41.5,27.5 L44,21.2 Z "
        "M50,38 A12,12 0 1,0 50,62 A12,12 0 1,0 50,38 Z"
    ),
    # A handset, drawn as a thick diagonal bar with cradles at each end.
    "phone": (
        "M32.5,22 C28,22 22,28.5 22,35.5 C22,58 42,78 64.5,78 "
        "C71.5,78 78,72 78,67.5 C78,64.5 76.2,63.2 73.5,62 "
        "L64,57.8 C61.4,56.6 59.3,57.2 57.6,59.2 L53.6,64 "
        "C47.4,60.6 39.4,52.6 36,46.4 L40.8,42.4 "
        "C42.8,40.7 43.4,38.6 42.2,36 L38,26.5 C36.8,23.8 35.5,22 32.5,22 Z"
    ),
    # A head and shoulders.
    "contacts": (
        "M50,24 A13,13 0 1,1 50,50 A13,13 0 1,1 50,24 Z "
        "M50,55 C64,55 76,62.5 76,72 L76,78 L24,78 L24,72 C24,62.5 36,55 50,55 Z"
    ),
    # A speech bubble with a tail.
    "messaging": (
        "M26,26 L74,26 C77.3,26 80,28.7 80,32 L80,62 C80,65.3 77.3,68 74,68 "
        "L46,68 L30,80 L32,68 L26,68 C22.7,68 20,65.3 20,62 L20,32 "
        "C20,28.7 22.7,26 26,26 Z"
    ),
    # A camera body with a lens and a viewfinder hump.
    "camera": (
        "M40,24 L60,24 L65,32 L78,32 C81.3,32 84,34.7 84,38 L84,70 "
        "C84,73.3 81.3,76 78,76 L22,76 C18.7,76 16,73.3 16,70 L16,38 "
        "C16,34.7 18.7,32 22,32 L35,32 Z "
        "M50,40 A14,14 0 1,0 50,68 A14,14 0 1,0 50,40 Z "
        "M50,46 A8,8 0 1,1 50,62 A8,8 0 1,1 50,46 Z"
    ),
    # A frame with a horizon and a sun.
    "gallery": (
        "M22,24 L78,24 C81.3,24 84,26.7 84,30 L84,70 C84,73.3 81.3,76 78,76 "
        "L22,76 C18.7,76 16,73.3 16,70 L16,30 C16,26.7 18.7,24 22,24 Z "
        "M22,68 L40,46 L52,60 L62,50 L78,68 Z "
        "M33,32 A7,7 0 1,0 33,46 A7,7 0 1,0 33,32 Z"
    ),
    # A folder.
    "files": (
        "M20,28 L44,28 L50,36 L80,36 C83.3,36 86,38.7 86,42 L86,70 "
        "C86,73.3 83.3,76 80,76 L20,76 C16.7,76 14,73.3 14,70 L14,34 "
        "C14,30.7 16.7,28 20,28 Z"
    ),
    # A keypad: four rows of three.
    "calculator": (
        "M28,20 L72,20 C75.3,20 78,22.7 78,26 L78,74 C78,77.3 75.3,80 72,80 "
        "L28,80 C24.7,80 22,77.3 22,74 L22,26 C22,22.7 24.7,20 28,20 Z "
        "M30,28 L70,28 L70,40 L30,40 Z "
        "M32,47 A4.5,4.5 0 1,0 32,56 A4.5,4.5 0 1,0 32,47 Z "
        "M50,47 A4.5,4.5 0 1,0 50,56 A4.5,4.5 0 1,0 50,47 Z "
        "M68,47 A4.5,4.5 0 1,0 68,56 A4.5,4.5 0 1,0 68,47 Z "
        "M32,62 A4.5,4.5 0 1,0 32,71 A4.5,4.5 0 1,0 32,62 Z "
        "M50,62 A4.5,4.5 0 1,0 50,71 A4.5,4.5 0 1,0 50,62 Z "
        "M68,62 A4.5,4.5 0 1,0 68,71 A4.5,4.5 0 1,0 68,62 Z"
    ),
    # A month grid with two hanging rings.
    "calendar": (
        "M34,16 L34,28 M66,16 L66,28 "
        "M22,26 L78,26 C81.3,26 84,28.7 84,32 L84,76 C84,79.3 81.3,82 78,82 "
        "L22,82 C18.7,82 16,79.3 16,76 L16,32 C16,28.7 18.7,26 22,26 Z "
        "M16,44 L84,44 L84,50 L16,50 Z "
        "M30,14 L38,14 L38,30 L30,30 Z M62,14 L70,14 L70,30 L62,30 Z"
    ),
    # A clock face with hands.
    "clock": (
        "M50,16 A34,34 0 1,1 50,84 A34,34 0 1,1 50,16 Z "
        "M50,24 A26,26 0 1,0 50,76 A26,26 0 1,0 50,24 Z "
        "M47,32 L53,32 L53,52 L47,52 Z "
        "M50,47 L50,53 L68,53 L68,47 Z"
    ),
    # A globe: circle, equator, meridian.
    "browser": (
        "M50,16 A34,34 0 1,1 50,84 A34,34 0 1,1 50,16 Z "
        "M50,23 A27,27 0 1,0 50,77 A27,27 0 1,0 50,23 Z "
        "M23,47 L77,47 L77,53 L23,53 Z "
        "M50,16 C60,16 66,31 66,50 C66,69 60,84 50,84 C40,84 34,69 34,50 "
        "C34,31 40,16 50,16 Z "
        "M50,23 C56,23 60,35 60,50 C60,65 56,77 50,77 C44,77 40,65 40,50 "
        "C40,35 44,23 50,23 Z"
    ),
    # A quaver: note head and stem.
    "music": (
        "M66,18 L72,18 L72,60 L66,60 Z "
        "M66,18 C66,18 50,22 44,26 L44,34 C50,30 66,26 66,26 Z "
        "M56,52 A14,11 0 1,0 56,74 A14,11 0 1,0 56,52 Z "
        "M34,30 L40,30 L40,70 L34,70 Z "
        "M24,62 A14,11 0 1,0 24,84 A14,11 0 1,0 24,62 Z"
    ),
    # A microphone.
    "recorder": (
        "M50,18 C55.5,18 60,22.5 60,28 L60,50 C60,55.5 55.5,60 50,60 "
        "C44.5,60 40,55.5 40,50 L40,28 C40,22.5 44.5,18 50,18 Z "
        "M30,46 L36,46 C36,58 42,66 50,66 C58,66 64,58 64,46 L70,46 "
        "C70,61 60,70.5 53,71.8 L53,82 L47,82 L47,71.8 C40,70.5 30,61 30,46 Z"
    ),
    # An envelope.
    "email": (
        "M18,28 L82,28 C85.3,28 88,30.7 88,34 L88,68 C88,71.3 85.3,74 82,74 "
        "L18,74 C14.7,74 12,71.3 12,68 L12,34 C12,30.7 14.7,28 18,28 Z "
        "M18,34 L50,55 L82,34 L82,41 L50,62 L18,41 Z"
    ),
    # A prompt: chevron and a caret.
    "terminal": (
        "M20,24 L80,24 C83.3,24 86,26.7 86,30 L86,70 C86,73.3 83.3,76 80,76 "
        "L20,76 C16.7,76 14,73.3 14,70 L14,30 C14,26.7 16.7,24 20,24 Z "
        "M26,38 L31,33 L47,49 L31,65 L26,60 L37,49 Z "
        "M52,60 L74,60 L74,66 L52,66 Z"
    ),
    # A sun: one disc, with rays that never touch it. Drawn this way on
    # purpose -- the obvious cloud is several overlapping circles, and
    # overlapping subpaths under evenOdd fill punch holes in each other
    # instead of merging.
    "weather": (
        "M50,32 A18,18 0 1,1 50,68 A18,18 0 1,1 50,32 Z M74.00,54.00 L83.00,54.00 L83.00,46.00 L74.00,46.00 Z M64.14,69.80 L70.51,76.16 L76.16,70.51 L69.80,64.14 Z M46.00,74.00 L46.00,83.00 L54.00,83.00 L54.00,74.00 Z M30.20,64.14 L23.84,70.51 L29.49,76.16 L35.86,69.80 Z M26.00,46.00 L17.00,46.00 L17.00,54.00 L26.00,54.00 Z M35.86,30.20 L29.49,23.84 L23.84,29.49 L30.20,35.86 Z M54.00,26.00 L54.00,17.00 L46.00,17.00 L46.00,26.00 Z M69.80,35.86 L76.16,29.49 L70.51,23.84 L64.14,30.20 Z"
    ),
    # A shield.
    "security": (
        "M50,16 L80,28 L80,52 C80,68 66,80 50,86 C34,80 20,68 20,52 "
        "L20,28 Z M50,25 L29,33.5 L29,52 C29,63 39,72 50,77 "
        "C61,72 71,63 71,52 L71,33.5 Z"
    ),
    # A downward arrow into a tray.
    "updater": (
        "M46,16 L54,16 L54,50 L68,50 L50,70 L32,50 L46,50 Z "
        "M20,72 L80,72 L80,82 L20,82 Z"
    ),
    # A drum with two bands.
    "storage": (
        "M50,18 C66,18 80,22 80,28 L80,72 C80,78 66,82 50,82 "
        "C34,82 20,78 20,72 L20,28 C20,22 34,18 50,18 Z "
        "M50,24 C38,24 28,26.5 28,29 C28,31.5 38,34 50,34 "
        "C62,34 72,31.5 72,29 C72,26.5 62,24 50,24 Z "
        "M20,44 C20,50 34,54 50,54 C66,54 80,50 80,44 L80,52 "
        "C80,58 66,62 50,62 C34,62 20,58 20,52 Z"
    ),
    # A bag.
    "store": (
        "M32,32 C32,22 40,14 50,14 C60,14 68,22 68,32 L78,32 "
        "C81.3,32 84,34.7 84,38 L84,78 C84,81.3 81.3,84 78,84 L22,84 "
        "C18.7,84 16,81.3 16,78 L16,38 C16,34.7 18.7,32 22,32 Z "
        "M40,32 L60,32 C60,26.5 55.5,22 50,22 C44.5,22 40,26.5 40,32 Z"
    ),
    # A magnifier.
    "search": (
        "M44,16 A28,28 0 1,1 44,72 A28,28 0 1,1 44,16 Z "
        "M44,24 A20,20 0 1,0 44,64 A20,20 0 1,0 44,24 Z "
        "M62,62 L68,56 L86,74 L80,80 Z"
    ),
    # A play triangle.
    "video": (
        "M50,16 A34,34 0 1,1 50,84 A34,34 0 1,1 50,16 Z "
        "M42,34 L68,50 L42,66 Z"
    ),
    # A bookmark.
    "notes": (
        "M28,16 L72,16 C75.3,16 78,18.7 78,22 L78,84 L50,68 L22,84 L22,22 "
        "C22,18.7 24.7,16 28,16 Z "
        "M34,30 L66,30 L66,37 L34,37 Z M34,44 L58,44 L58,51 L34,51 Z"
    ),
    # A dialpad-free ring: a call log arc.
    "dialer": (
        "M50,20 A30,30 0 1,1 50,80 A30,30 0 1,1 50,20 Z "
        "M50,28 A22,22 0 1,0 50,72 A22,22 0 1,0 50,28 Z "
        "M36,36 A8,8 0 1,1 36,52 A8,8 0 1,1 36,36 Z "
        "M64,36 A8,8 0 1,1 64,52 A8,8 0 1,1 64,36 Z "
        "M50,58 A8,8 0 1,1 50,74 A8,8 0 1,1 50,58 Z"
    ),
    # The fallback: the octagonOS mark itself, as a ring with a table in the
    # middle -- the same crown-and-table reading as the glass beneath it.
    "generic": (
        "M31,14 L69,14 L86,31 L86,69 L69,86 L31,86 L14,69 L14,31 Z "
        "M35,24 L65,24 L76,35 L76,65 L65,76 L35,76 L24,65 L24,35 Z "
        "M42,38 L58,38 L62,42 L62,58 L58,62 L42,62 L38,58 L38,42 Z"
    ),
}

# --- hues -------------------------------------------------------------------
#
# Where a glyph's tint sits between FacetUI's two accents: 0.0 is the cyan-blue
# end, 1.0 the violet end. Only the glyph is tinted; the glass beneath it is
# the same on every icon, which is what makes a screen of these read as one
# material rather than as a palette.

HUE_COOL = 0.0
HUE_BLUE = 0.25
HUE_MID = 0.5
HUE_VIOLET = 0.75
HUE_WARM = 1.0

# --- component map ----------------------------------------------------------
#
# Key is either "package/activity" or a bare "package", which matches every
# activity in it. Longest match wins, so a specific activity overrides its own
# package's entry.
#
# These cover what an AOSP/LineageOS-derived Android 17 GSI actually ships.
# Anything NOT listed here is not left alone: it goes through the procedural
# glass treatment in patches/iconloader/0001 instead, which is what makes the
# coverage total rather than a list someone has to keep extending.

APPS = {
    "com.android.settings":                     ("settings",   HUE_MID),
    "com.android.dialer":                       ("phone",      HUE_BLUE),
    "com.android.contacts":                     ("contacts",   HUE_BLUE),
    "com.android.messaging":                    ("messaging",  HUE_COOL),
    "com.android.mms":                          ("messaging",  HUE_COOL),
    "com.android.camera2":                      ("camera",     HUE_VIOLET),
    "org.lineageos.aperture":                   ("camera",     HUE_VIOLET),
    "com.android.gallery3d":                    ("gallery",    HUE_VIOLET),
    "org.lineageos.glimpse":                    ("gallery",    HUE_VIOLET),
    "com.android.documentsui":                  ("files",      HUE_MID),
    "com.android.calculator2":                  ("calculator", HUE_BLUE),
    "com.android.calendar":                     ("calendar",   HUE_WARM),
    "ws.xsoh.etar":                              ("calendar",   HUE_WARM),
    "com.android.deskclock":                    ("clock",      HUE_COOL),
    "org.lineageos.jelly":                      ("browser",    HUE_BLUE),
    "com.android.browser":                      ("browser",    HUE_BLUE),
    "com.android.music":                        ("music",      HUE_VIOLET),
    "org.lineageos.twelve":                     ("music",      HUE_VIOLET),
    "com.android.soundrecorder":                ("recorder",   HUE_WARM),
    "org.lineageos.recorder":                   ("recorder",   HUE_WARM),
    "com.android.email":                        ("email",      HUE_COOL),
    "com.android.terminal":                     ("terminal",   HUE_MID),
    "com.android.traceur":                      ("terminal",   HUE_MID),
    "org.lineageos.eleven":                     ("music",      HUE_VIOLET),
    "foundation.e.weather":                     ("weather",    HUE_COOL),
    "com.stevesoltys.seedvault":                ("security",   HUE_MID),
    "org.lineageos.updater":                    ("updater",    HUE_BLUE),
    "com.android.settings.intelligence":        ("search",     HUE_MID),
    "com.android.vending":                      ("store",      HUE_WARM),
    "org.fdroid.fdroid":                        ("store",      HUE_WARM),
    "com.android.gallery":                      ("gallery",    HUE_VIOLET),
    "com.google.android.deskclock":             ("clock",      HUE_COOL),
    "com.android.storagemanager":               ("storage",    HUE_MID),
    "com.android.providers.downloads.ui":       ("updater",    HUE_BLUE),
    "org.lineageos.etar":                       ("calendar",   HUE_WARM),
    "com.android.quicksearchbox":               ("search",     HUE_MID),
    "com.android.gallery3d.app.Gallery":        ("gallery",    HUE_VIOLET),
    "com.android.bips":                         ("files",      HUE_MID),
    "org.lineageos.profiles":                   ("settings",   HUE_MID),
    "com.android.launcher3":                    ("generic",    HUE_MID),
}

#: Used for any component in APPS whose glyph is missing, and as the icon for
#: the pack itself.
FALLBACK_GLYPH = "generic"


def resolve(component):
    """Glyph and hue for a component string, or None if it is not curated.

    Tries the full "package/activity" first, then the bare package, so a
    specific activity can override its package without repeating the rest.
    """
    if component in APPS:
        return APPS[component]
    pkg = component.split("/", 1)[0]
    return APPS.get(pkg)

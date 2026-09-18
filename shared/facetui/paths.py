"""
Locating this package from tooling that lives elsewhere in the tree.

Generators sit under mobile/ and desktop/ and import from here, so each would
otherwise repeat the same three lines of sys.path juggling. Import this first:

    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "shared"))
    from facetui import palette
"""

import pathlib

#: The repository root, from this file.
ROOT = pathlib.Path(__file__).resolve().parents[2]

SHARED = ROOT / "shared"
MOBILE = ROOT / "mobile"
DESKTOP = ROOT / "desktop"

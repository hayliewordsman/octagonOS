# shared — the FacetUI core

Everything here is platform-neutral. Nothing in it knows about Android or about
Linux, because both editions import it.

| Path | What it is |
|---|---|
| [`facetui/facet_math.py`](facetui/facet_math.py) | The AGSL, transcribed to NumPy: the edge highlight and the rim darkening |
| [`facetui/palette.py`](facetui/palette.py) | The accents, the octagon geometry, and the four FacetUI parameters |
| [`facetui/glyphs.py`](facetui/glyphs.py) | Icon glyph path data, and the component map |
| [`docs/design-language.md`](docs/design-language.md) | The rule, the depth model, and the doctrine both editions follow |

## Why this is a directory and not a branch

`mobile/` and `desktop/` are two products, not two versions of one, so they were
never going to merge into each other. Keeping them as branches would have meant
cherry-picking this directory between them forever.

Here, `facet_math.py` is one file. When a shader constant changes, both editions
change with it — which is the claim this project keeps making about its own
coherence, and this is what makes it true rather than aspirational.

## The one thing that cannot be shared

The FacetUI parameters are also written down in Kotlin and Java, inside the
SystemUI patches, because a `RuntimeShader` subclass cannot import a Python
file. Those copies are cross-checked instead:

```bash
mobile/tools/validate-shaders.py
```

It compiles the AGSL with Skia's own SkSL compiler, and confirms that
`facet_math.py` still matches the shader's own literals and that every copy of
the four parameters agrees.

# octagonOS boot animation

```bash
./build.sh          # builds, then verifies
```

Produces `out/bootanimation.zip`: 8.9 MiB, 92 frames, 3.8s at 24fps.

| File | What it is |
|---|---|
| `make-bootanimation.py` | The generator |
| `facet_math.py` | FacetUI's AGSL, transcribed to NumPy — the same expressions in the same order, so the two can be read side by side |
| `build.sh` | Build and verify |
| `out/bootanimation.zip` | The built animation, committed |

Needs Pillow and NumPy. No Android SDK, no device.

Full design notes, including why the canvas is square, why the frame borders
must match the declared background exactly, and why the looping part is the
short one: **[../docs/bootanimation.md](../docs/bootanimation.md)**.

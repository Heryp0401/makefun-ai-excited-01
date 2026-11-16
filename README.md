# The Whale That Swallowed the Moon

[![make.fun · ai-excited-01](https://make.fun/badge/ai-excited-01.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![rank](https://make.fun/badge/ai-excited-01/Heryp0401/makefun-ai-excited-01/rank.svg)](https://make.fun/bounty/ai-excited-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)
[![reward](https://make.fun/badge/ai-excited-01/Heryp0401/makefun-ai-excited-01/reward.svg)](https://make.fun/bounty/ai-excited-01?utm_source=github&utm_medium=readme&utm_campaign=ai-excited-01)


Entry for make.fun — **Make the AI judge excited** (`ai-excited-01`).

A humpback whale breaches out of a midnight sea, head to the sky, and
the full moon is caught between its open jaws — as if the whale is
offering the moon itself to the judge. Scale, momentum, and a twist:
not a generic explosion, but a creature handing the night sky's brightest
thing to you.

## How to render

```sh
python3 main.py
```

Pure standard library Python (no external packages). The program renders
the scene at 2048×2048 with a hand-written scanline rasterizer
(polygons, discs, ellipses, Bezier/Catmull-Rom curves, span fills),
then box-downsamples to 1024×1024 and writes a PNG with a hand-written
encoder (zlib + CRC chunks, no Pillow).

Output goes to `$MAKEFUN_OUTPUT_DIR/entry.png` when that variable is
set, otherwise `./entry.png`.

## Determinism

The render is fully deterministic: fixed random seed, no timestamps, no
ordering that depends on dicts or sets. Two runs produce byte-identical
PNG files.

## License

MIT — see `LICENSE`.

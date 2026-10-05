# Getting a good input image

OpenFigura turns **one character, one view** into a 3D asset. The single
biggest quality lever is the reference image you feed it. This guide is for
humans; the machine-enforced version lives in
[`input-quality.md`](input-quality.md).

You don't need to draw anything. A commercial text-to-image model
(GPT Image, Grok Imagine, Doubao/Seedream, Midjourney, …) can produce a
perfect input if you ask it the right way. Copy a template below, swap the
bracketed description for your character, then follow the 30-second
finishing steps.

## The 6 properties of a great input

| # | property | why it matters |
|---|---|---|
| 1 | **One character, one pose, one view** | multi-view sheets get fused into one creature |
| 2 | **Full body visible, feet not cropped** | the model invents whatever it can't see |
| 3 | **Plain solid background** (white/light gray) | clean matting; busy edges become 3D noise |
| 4 | **Even, flat lighting — no dramatic shadows** | shadows get baked into geometry |
| 5 | **Face clear, eyes unobstructed** (no bangs over pupils, no glasses glare) | eyes are the first thing generation loses |
| 6 | **Tall aspect (~2:3), as large as the tool allows** | short edge ≥1024 px keeps real detail |

## Prompt templates (paste into your image model)

### A. Stylized 3D character (safest for generation)

```
Full-body character reference of [YOUR CHARACTER: e.g. "a young woman
with a chin-length chestnut bob, a small red flower clip on the left
side of her hair, wearing ivory satin pajamas with dark piping"],
single figure, standing in a relaxed neutral A-pose, facing the camera
straight on, full body visible including feet, plain solid white
background, soft even studio lighting, no shadows on the background,
no text, no watermark, cute stylized 3D render look, high detail on
face and eyes, 2:3 portrait composition
```

### B. Flat illustration / game-sprite style

```
Single game character sprite sheet of ONE pose only: [CHARACTER],
front view, full body, flat neutral colors, clean silhouette, plain
light gray background, no outlines glow or drop shadow, no text,
no background props, consistent lighting, 2:3 portrait
```

### C. Realistic human

```
Full-body portrait photograph of [PERSON DESCRIPTION], standing
straight facing camera, arms relaxed at sides, plain light-gray
studio backdrop, even softbox lighting with no harsh shadows,
shoes and feet fully in frame, no hat, hair out of the eyes,
85mm lens, neutral expression, 2:3 portrait
```

### D. Prop / object (weapons, furniture, food)

```
Single [OBJECT: e.g. "ornate tarot deck box, deep blue with gold
foil edging"], centered, three-quarter front view, entire object in
frame with margin around it, plain white background, soft even
product lighting, no cast shadow, no text or logo, high detail,
2:3 framing
```

### Negative lines (if your model supports them)

```
negative: multiple people, duplicated character, turnaround sheet,
grid, collage, text, watermark, signature, dramatic rim lighting,
strong ground shadow, cropped feet, cropped head, motion blur,
complex background
```

## 30-second finishing steps

1. **Mat it.** Remove the background → PNG with alpha. macOS Preview /
   any one-click tool works. Keep hair wisps, ears and dark piping on
   light clothing intact — zoom in and check those edges.
2. **Crop to one view.** If the model gave you four poses anyway, cut out
   the best front view as its own image.
3. **Check it.** `openfigura preflight my.png` (or ask your agent to run
   `figura_preflight`). Fix what it flags *before* generating.

## Common failure gallery (what "bad" looks like)

- ❌ A four-view sheet → one chimera with two faces.
- ❌ Feet at the frame edge → legs that end in the void.
- ❌ Sunset rim-light → a character permanently half black.
- ❌ JPEG at 30% quality → ringing artifacts as literal 3D bumps.
- ❌ Bangs covering both eyes → eyeless face, guaranteed.

## For project testing (golden cases)

When contributing a golden case, send 5 good inputs spanning difficulty
(front view / side view / fine hair or accessories / dark clothing /
non-human prop) **plus 3 deliberately broken ones** (≈256 px, a wide
multi-view strip, a heavily compressed JPEG) — the broken set proves the
preflight gate actually bites. Broken variants are easiest made by
downscaling/cropping a good image rather than prompting for them.

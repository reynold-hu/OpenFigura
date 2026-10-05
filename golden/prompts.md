# Golden-case fixture prompts (maintainer test suite)

**These are test fixtures, not user guidance.** User-facing prompt help
lives in [`../docs/input-guide.md`](../docs/input-guide.md). The cases
below deliberately span difficulty axes so regressions show up where they
hurt: fine hair, dark-on-light separation, non-frontal inference, props.

After generation, each image gets matted to transparent PNG, short edge
≥1024, then committed under `cases/<name>/input.png` with a `case.json`.

## 1. `xiaoman-front` — baseline front view

```
Full-body character reference of a young woman with a chin-length
chestnut bob, a small red flower clip on the left side of her hair,
wearing ivory satin pajamas with dark piping, single figure, standing
in a relaxed neutral A-pose, facing the camera straight on, full body
visible including feet, plain solid white background, soft even studio
lighting, no shadows on the background, no text, no watermark, cute
stylized 3D render look, high detail on face and eyes, 2:3 portrait
composition
```

## 2. `hoodie-side` — side view, single-image inference stress

```
Full-body character reference of a teenage boy in a green hoodie and
jeans, standing in a relaxed neutral pose, side profile view facing
left, full body visible including shoes, plain solid light gray
background, soft even studio lighting, no shadows, no text, no
watermark, stylized 3D render look, 2:3 portrait
```

## 3. `silver-scarf` — wisps and accessories, matte-edge stress

```
Full-body character reference of an elderly woman with long flowing
silver hair, dangling earrings and a scarf with fringe, standing
straight facing camera in a neutral A-pose, full body visible, plain
solid white background, soft even lighting, no shadows, no text, no
watermark, cute stylized 3D render, detailed hair strands, 2:3 portrait
```

## 4. `dark-knight` — dark subject on light ground, silhouette stress

```
Full-body character reference of a knight in dark matte armor with
subtle gold engravings, standing straight facing camera, arms relaxed
at sides, full body including boots visible, plain solid off-white
background, soft even studio lighting, no cast shadow, no text,
stylized 3D game render, 2:3 portrait
```

## 5. `tarot-box` — non-human prop, pipeline generality

```
Single ornate tarot deck box, deep blue velvet with gold foil edging
and a crescent moon emblem, centered, three-quarter front view, entire
object in frame with generous margin, plain white background, soft
even product lighting, no cast shadow, no text or logo, high detail,
2:3 framing
```

## Negative prompt (all cases, if supported)

```
multiple people, turnaround sheet, grid, collage, text, watermark,
cropped feet, dramatic lighting, complex background
```

## 6. `scifi-stride` — complex game character with pose (user-supplied)

```
Full-body stylized 3D game character of a female warrior in black and
white sci-fi armor with gold accents, long flowing white hair, horned
visor helmet, dark cape with torn gold-edged panels, mid-stride walking
pose facing camera, full body visible, plain white background, soft
even lighting, no text, no watermark, high detail, 2:3 portrait
```

## 7. `crouch-pose` — non-neutral pose + eyes covered (user-supplied)

```
Full-body stylized 3D game character render of a white-bobbed android
woman in a black-and-white gothic combat outfit with lace cutouts,
black visor covering the eyes, crouching pose, one hand raised, high
heel boots, plain white background, soft studio lighting, no text,
no watermark, 2:3 portrait
```

## 8. `head-sculpt` — photoreal bust, facial detail ceiling (user-supplied)

```
Photorealistic 3D head sculpt of a young bald man, three-quarter view,
intense gray eyes fully visible, detailed skin pores and brows, neutral
expression, clean white background, soft studio lighting, digital
sculpture render, no shoulders, no text, 2:3 portrait
```

Note: 6–8 deliberately break our own A-pose/full-body guidance (stride,
crouch, visor-over-eyes, bust-only). That is the point — they measure how
far the pipeline stretches when users ignore the guide, and the results
should feed back into input-guide wording.

## Making broken fixtures (maintainers)

Run `python3 make_broken.py` from `golden/`. It derives all three from
committed good cases with exactly one degradation each — see
`cases/broken-*/case.json` for the expected preflight verdict.

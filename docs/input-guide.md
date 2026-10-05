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

Prompts are bilingual. Chinese-native models (豆包/Doubao, 即梦, 通义万相,
可灵) generally follow the Chinese version best; GPT Image, Midjourney and
Grok usually follow the English one best. Swap the bracketed description
for your character. 提示词中英双语：中文模型（豆包、即梦、通义、可灵）用中文版，
英文模型（GPT Image、Midjourney、Grok）用英文版。

### 0. Master template / 万能母版（先会用这个）

The one template that covers 90% of needs. Replace the single bracket;
everything else is load-bearing — keep it. 只需替换一处【】，其余每个词都有作用，别删。

```
一张完整的角色参考图：【在这里写你的角色：身份、发型发色、服装颜色与材质、
标志性配饰】。单一人物，站姿自然放松，正面朝向镜头，全身完整入画包括脚部，
头顶留有余量。纯白色背景，柔和均匀的影棚光，背景无阴影，人物无夸张光影。
面部清晰，眼睛完整露出，头发不遮挡瞳孔。3D 动画电影渲染风格，脸部和眼睛
细节丰富。竖版 2:3 构图，无文字，无水印，无多姿势拼图。
```

```
A single full-body character reference of [your character: identity,
hairstyle and color, outfit colors and material, signature accessories].
One figure only, relaxed neutral A-pose, facing the camera straight on,
full body visible including feet with headroom. Plain solid white
background, soft even studio lighting, no cast shadows. Face clear, both
eyes fully visible, hair not covering pupils. Stylized 3D animated-movie
render, high detail on face and eyes. 2:3 portrait composition, no text,
no watermark, no multi-pose grid.
```

### A. Stylized 3D character (safest for generation) / 风格化 3D 角色（最稳）

Same as the master template; the example below fills the bracket once:
与母版相同，只是给【】一个填好的示例：

```
【年轻女性，齐肩栗色波波头，左侧头发别一朵红色小花发夹，穿米白色缎面睡衣，
衣服边缘有深色滚边】
```

```
[a young woman with a chin-length chestnut bob, a small red flower clip
on the left side of her hair, wearing ivory satin pajamas with dark
piping]
```

### B. Flat illustration / game-sprite style / 扁平插画·游戏精灵（单姿势）

```
单角色游戏参考图，仅一个姿势：【角色描述】。正面视角，全身，平涂中性配色，
轮廓干净，浅灰色纯色背景，无发光描边无投影，无文字，无背景道具，光照一致，
竖版 2:3。
```

```
Single game character sprite sheet of ONE pose only: [CHARACTER], front
view, full body, flat neutral colors, clean silhouette, plain light gray
background, no outline glow or drop shadow, no text, no background props,
consistent lighting, 2:3 portrait.
```

### C. Realistic human / 写实人像

```
全身人像摄影：【人物描述】，正面直立面向镜头，双臂自然下垂，纯浅灰影棚背景，
柔光箱均匀布光无硬阴影，鞋和脚完整入画，不戴帽子，头发不遮眼睛，85mm 镜头，
表情自然，竖版 2:3。
```

```
Full-body portrait photograph of [PERSON DESCRIPTION], standing straight
facing camera, arms relaxed at sides, plain light-gray studio backdrop,
even softbox lighting with no harsh shadows, shoes and feet fully in
frame, no hat, hair out of the eyes, 85mm lens, neutral expression,
2:3 portrait.
```

### D. Prop / object / 道具·物件（武器、家具、食物）

```
单个【物件：深蓝色天鹅绒塔罗牌盒，烫金描边，月牙徽标】，居中，四分之三正面
视角，物件完整入画且四周留白充足，纯白背景，柔和均匀的产品光，无投影，
无文字无 logo，高细节，竖版 2:3。
```

```
Single [OBJECT: e.g. "ornate tarot deck box, deep blue velvet with gold
foil edging and a crescent moon emblem"], centered, three-quarter front
view, entire object in frame with generous margin, plain white background,
soft even product lighting, no cast shadow, no text or logo, high detail,
2:3 framing.
```

### Negative lines (if your model supports them) / 负面词

```
negative: 多人，拼图，三视图，四视图，文字，水印，签名，戏剧性侧光，
地面投影，裁掉脚，裁掉头，运动模糊，复杂背景
```

```
negative: multiple people, duplicated character, turnaround sheet, grid,
collage, text, watermark, signature, dramatic rim lighting, strong ground
shadow, cropped feet, cropped head, motion blur, complex background
```

## 30-second finishing steps / 30 秒后处理

1. **Mat it / 抠图.** Remove the background → PNG with alpha. Keep hair
   wisps, ears and dark piping on light clothing intact — zoom in and
   check those edges. 抠掉背景存成透明 PNG，放大检查发丝、耳朵、浅色衣服上的
   深色滚边是否被误删。
2. **Crop to one view / 裁成单视图.** If the model gave you four poses
   anyway, cut out the best front view as its own image. 模型不听话给了
   多姿势，就把最好的正面单独裁出来。
3. **Check it / 跑检查.** `openfigura preflight my.png` (or ask your
   agent to run `figura_preflight`). Fix what it flags *before* generating.
   先跑 preflight，它报的问题在生成前解决。

## Common failure gallery / 常见失败对照（什么不能用）

- ❌ A four-view sheet → one chimera with two faces. 四视图条 → 嵌合体。
- ❌ Feet at the frame edge → legs that end in the void. 脚贴边 → 腿悬空。
- ❌ Sunset rim-light → a character permanently half black. 夕阳轮廓光 →
  半个身子烤进几何。
- ❌ JPEG at 30% quality → ringing artifacts as literal 3D bumps. 低质量
  JPEG → 压缩噪点变 3D 疙瘩。
- ❌ Bangs covering both eyes → eyeless face, guaranteed. 刘海遮眼 →
  必出无脸怪。

## For project testing (golden cases)

When contributing a golden case, send 5 good inputs spanning difficulty
(front view / side view / fine hair or accessories / dark clothing /
non-human prop) **plus 3 deliberately broken ones** (≈256 px, a wide
multi-view strip, a heavily compressed JPEG) — the broken set proves the
preflight gate actually bites. Broken variants are easiest made by
downscaling/cropping a good image rather than prompting for them.

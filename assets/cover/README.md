# README cover animation

`../cover.gif` is a 20-second, 1280 × 700, 24 fps loop. `../cover.mp4` is an
MP4 preview of the same animation. `../cover.png` is a still of the verified
tool-recovery outcome. The README consumes the animated GIF.

The blue block/ASCII title follows the supplied title reference. The navy,
blue, purple, teal and white palette follows the paper figures. The simple
terminal framing and restrained motion also refer to the
[Claude Code product page](https://claude.com/product/claude-code).

The paper-style white-and-blue robot has six expressions and poses: idle,
startled, thinking, typing, checking and celebrating. The built-in `image_gen`
tool generated the pose sheet from the paper's Figure 1 robot. The exact
generation and extraction prompts are saved in `imagegen-prompts.txt`.
`robot-poses.png` is the preserved generated source with alpha transparency.
`render.py` slices and animates this sheet and draws the other elements from
editable primitives. Rendering requires only the local assets.

The two scenes illustrate the paper's deployment behavior:

1. **Tool feedback:** a read call returns 503; the agent diagnoses a transient
   failure, retries with bounded backoff, then verifies the returned result.
2. **User correction:** the user asks for a missing ID check; the agent resolves
   the target, revises the action, and reads back the update to verify it.

These are illustrative interactions, not measured benchmark trajectories.
The footer describes training, separately from the deployed agent:
RSD discovers reusable recovery skills; ReSFT learns verified reflection;
ORPO combines noisy agentic RL with skill-guided on-policy distillation.
Skill prompts are used during training and are absent at inference.

## Render

Requires Python 3.10+, [Pillow](https://pillow.readthedocs.io/) and
[ffmpeg](https://ffmpeg.org/). The default typeface is Avenir Next on macOS,
with DejaVu Sans as a fallback. Use `--font /path/to/font.ttf` to override it.

From the repository root:

```bash
python assets/cover/render.py --preview --output /tmp/agent-reflex-cover
python assets/cover/render.py
```

The preview command writes a six-frame contact sheet and poster to its output
directory. The default export replaces `assets/cover.gif`, `assets/cover.mp4`,
`assets/cover.png`, and `assets/logo.png`. The logo uses the same paper-style
robot face. The export uses one global palette to avoid flickering stationary
text. The robot changes pose, breathes, reacts to failure, types, verifies and
celebrates; the title has a subtle scanning highlight, terminal lines type in,
and message packets travel along the connectors.

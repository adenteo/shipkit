# motionkit

A Claude Code plugin for making app animations as code. It bundles what worked, and what did not,
from building micro-interactions, loaders, mascots and celebration moments for shipped apps.

| Skill | What it covers |
|---|---|
| `rive` | Rive (`.riv`) authored as RML text with the official Rive CLI: generated UI pieces (toggle, pill button, loader), painted layers, real and fake 3D, state machines, data binding, events that drive haptics, headless rendering and verification, a list of silent failures, and a review bar. Bundles a small generator library (`uilib.py`, `rive_keys.py`, `shoot.py`). |
| `rive-character` | Rigging a 2D character in Rive: bones, skinning, IK, measuring motion off reference frames, per-feature quality gates, and a reader that takes apart any exported `.riv`. |
| `lottie` | Lottie (bodymovin JSON) drawn from Python with a standard-library kit: keyframes and eases, shapes, bezier paths, an art kit with gradients, glows and confetti, palette as parameters, a validator and key pruning. A headless preview (contact sheets, stills, video) with lottie-web. When to choose Lottie, Rive or native animation, size and frame rate rules, players per platform, web performance. |

## Install

```
/plugin marketplace add adenteo/shipkit
/plugin install motionkit@shipkit
```

Then ask for what you want ("make a loading animation as a Lottie", "build a Rive toggle with a
squash on press", "why does my rig read stiff") and the matching skill loads.

## Requirements

- `rive` and `rive-character`: the Rive CLI (`~/.rive/bin/rive`; see rive.app for the install
  command). The lessons were measured on CLI 1.2.0; newer CLIs may demand an update before they run.
  Python 3 for the generators; Pillow for `shoot.py`; numpy for the 3D phone example.
- `lottie`: Python 3 (standard library only). For previews, Node 18 or newer and a Chrome or
  Chromium (`CHROME_PATH` overrides the lookup); `ffmpeg` for video.

## Layout

```
.claude-plugin/plugin.json
skills/rive/             SKILL.md, reference files, scripts/ (uilib, rive_keys, shoot), examples/
skills/rive-character/   SKILL.md, readriv.py, schema.json
skills/lottie/           SKILL.md, scripts/ (lottie_kit, build), examples/, preview/
```

## What it is not

It does not make art for you. It makes the motion, the structure and the checks around art you
drew or generated, and it insists that you look at the result before you ship it.

## License

MIT

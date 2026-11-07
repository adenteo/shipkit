---
name: ship-images
description: >-
  Generate images for an app you are shipping, with whatever the user has: an
  OpenAI API key (gpt-image-2), the Codex CLI on a ChatGPT plan, or a Codex agent
  running in a Herdr pane next to Claude. Two modes. Explore: moodboards, vibe
  directions, icon concepts and screen ideas for inspiration, so the user picks a
  look before anything is built. Produce: a consistent set of in-app art
  (onboarding illustrations, empty states, mascots, badges, backgrounds, stickers)
  sized and cut out for the app. Also asks Codex for a second opinion on names,
  taglines or designs. Use when the user wants inspiration, a moodboard, a vibe,
  concept art, app illustrations or custom assets, says "ask codex", or when the
  ship skill reaches its vibe or assets step.
---

# ship-images

Images do two jobs while shipping an app, and they have different rules:

- **Explore** (inspiration). Cheap, fast, many options. The user is choosing a
  direction, so variety matters more than polish. These images are references:
  they never ship as UI and never stand in for real screenshots.
- **Produce** (assets that ship). Few images, consistent with each other and with
  the chosen vibe, checked one by one, cut out and sized for the app.

Everything goes through one script, which picks the backend:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/imagine.py" doctor          # what works here
python3 "${CLAUDE_SKILL_DIR}/scripts/imagine.py" gen BATCH.json  # make a batch
python3 "${CLAUDE_SKILL_DIR}/scripts/imagine.py" ask "..."       # ask Codex
```

All commands take `--ship path/to/ship.json` (default `./.ship/ship.json`).

## Backends

| Backend | Needs | Cost | Best for |
|---|---|---|---|
| `openai` | OpenAI API key | Paid per image | Exact sizes, reference-image edits, big batches |
| `codex` | `codex` CLI, logged in with ChatGPT | Uses the ChatGPT plan's limits | Exploring without an API key |
| `codex-herdr` | Codex + this session running inside Herdr | Same as `codex` | Exploring together: the user watches Codex in a pane beside you, can steer it directly, and it remembers earlier images in the set |

The backend is chosen at intake and stored in `ship.json` `images.backend`. If it
is empty, run `doctor` and ask the user which to use (AskUserQuestion, one option
per working backend, plus "no images"). Details, setup and failure modes are in
`references/backends.md`.

Never print an API key. The OpenAI key is read from `OPENAI_API_KEY` or from the
env file named in `secrets.openaiEnv`.

## Explore: find the vibe

1. Read `ship.json` `app` (name, oneLiner, audience). If the app has screens
   already, look at a couple of them.
2. Write **four distinct directions**. Each one gets: a two or three word name, the
   feeling in one line, a palette of five hex colours, a font pairing that is free
   to use (Google Fonts or system), a material or texture, two or three real
   products it borrows from (in words, as references, not to copy), and one thing
   it avoids. Make them genuinely different from each other: change the colour
   temperature, the type (serif, rounded, mono, grotesk), and the density, not just
   the accent colour.
3. Write a batch file at `.ship/inspiration/batch.json` with one moodboard per
   direction (portrait `1024x1536`, a 3x2 grid of textures, palette swatches, type
   samples and two small UI fragments) and, if useful, one hero screen idea per
   direction. Use `references/prompts.md` for the prompt shapes. Run `gen`.
   With `codex` the four run two at a time; with `codex-herdr` they run one by
   one in the visible pane.
4. Look at every image yourself (Read tool). Regenerate any that came out muddy,
   off-palette, or with fake text all over it: delete its PNG and run `gen` again.
5. Build a contact sheet the user can open: `.ship/inspiration/index.html` with the
   four boards side by side, each labelled with its direction name, palette chips
   and fonts. Tell the user the path.
6. Ask the user to pick one (AskUserQuestion, one option per direction, with the
   palette and fonts in the description). Accept "mix 2 and 4" and iterate.
7. Write the result into `ship.json` `vibe`: `direction`, `keywords`, `palette`,
   `fonts`, the chosen board paths in `references`, and anything they rejected in
   `avoid`. Tick the vibe line in `.ship/PROGRESS.md`.

Ask Codex for a second opinion when it would help, for example on names or on
which direction suits the audience:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/imagine.py" ask \
  "Here are four visual directions for <app>. Which fits <audience> best and why?" \
  --image .ship/inspiration/dir1.png --image .ship/inspiration/dir2.png
```

Treat its answer as one more opinion to weigh, not a decision.

## Produce: art that ships

First check `ship.json` `images.shipArt`. If it is `false`, generated images are
for inspiration only (some teams and some games have a no-AI-art rule); stop and
tell the user which assets they need to draw or source instead. If it is empty,
ask once.

1. List the assets the app needs and their sizes (for example: 3 onboarding
   illustrations at 1024x1024, 4 empty states, a mascot in 6 poses, achievement
   badges). Confirm the list with the user.
2. Pick a style anchor: the chosen moodboard, the app icon, or the best first
   asset. Put it in `reference_image` and set `use_reference: true` on every image
   so the set stays consistent. Put everything shared (medium, palette, line
   weight, lighting, "no text") in `style_preamble` and keep each prompt to what
   differs.
3. Make one image first, check it with the user, then the rest. A set is only as
   good as its weakest image.
4. For cut-out art (stickers, mascots, badges) set `transparent: true` and
   `crop: true`, and make every prompt ask for a plain flat background with a
   clear margin on all four sides. The cut-out is a flood fill from the corners; a
   subject touching an edge gets erased. Pillow is needed for this step.
5. Look at every result. Reject anything with these tells and regenerate: garbled
   or fake text, extra or melted fingers, plastic sheen, inconsistent line weight
   across the set, random symbols, a different character from the last image.
6. Copy finals into the app:
   - Xcode: `sips -Z <px> in.png --out App/Assets.xcassets/Name.imageset/Name.png`
     plus a `Contents.json`; template images get
     `"template-rendering-intent": "template"`.
   - Expo / React Native: `assets/images/name.png` with `@2x` and `@3x` copies.
   Keep the full-size originals in `.ship/assets/`.
7. Tick the assets line in `.ship/PROGRESS.md`.

Never put words inside a generated image that ships. Set the text in code with
the app's fonts, so it stays sharp, translatable and spelled right.

## Batch file

The batch format is shared by every backend:

```json
{
  "size": "1024x1024",
  "quality": "medium",
  "output_dir": ".",
  "reference_image": "",
  "style_preamble": "Soft gouache illustration, warm paper texture, palette #F4EDE4 #C8553D #2E4057, no text. The image shows ",
  "post_process": { "transparent_background": false, "crop_to_subject": false },
  "images": [
    { "name": "onboarding-1", "prompt": "...", "size": "1024x1536" },
    { "name": "badge-streak", "prompt": "...", "transparent": true, "crop": true, "use_reference": true }
  ]
}
```

Sizes the OpenAI backend accepts: `1024x1024`, `1536x1024`, `1024x1536`. The
Codex backends treat the size as an aspect ratio hint. Files already on disk are
skipped, so to redo one image delete just that file. `--dry-run` prints the exact
prompts without generating anything. See `references/example-batch.json`.

## Cost

The `openai` backend bills each image to the user's API account; tell the user
roughly how many images a batch will make before running a large one (more than
about 12). The Codex backends use the user's ChatGPT plan limits instead; a run
can fail when the plan's limit is reached, and the error says so.

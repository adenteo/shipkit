# Image backends

`imagine.py` hides the differences, but each backend has its own setup and its own
ways to fail.

## openai

- **Setup.** An OpenAI API key with image access. Put it in an env file outside the
  repo (for example `~/.config/openai/openai.env` containing `OPENAI_API_KEY=...`,
  `chmod 600`) and set `ship.json` `secrets.openaiEnv` to that path. Or export
  `OPENAI_API_KEY` in the shell.
- **Model.** `images.model` in `ship.json`, default `gpt-image-2`. Pin a dated
  snapshot or a newer model there. If the API rejects the id, try `gpt-image-1`.
- **Reference images.** `use_reference: true` sends the batch's `reference_image`
  through the edits endpoint so the result follows its style. This is the most
  reliable way to keep a set consistent.
- **Transparency.** `background: transparent` is not supported by gpt-image-2, so
  the script asks for a flat background and removes it afterwards (Pillow).
- **Failures.** Errors print per image with the API message. Unknown model,
  billing limits and content policy refusals are the usual ones. Re-running only
  retries the failed images.

## codex

- **Setup.** Install the Codex CLI and run `codex login` once with a ChatGPT
  account. No API key. Images come out of the user's plan.
- **How it runs.** One non-interactive `codex exec` per image, in the batch's output
  folder with `-s workspace-write`, the prompt on stdin. Codex uses its own image
  tool and saves the file into the folder. If it only leaves the image under
  `~/.codex/generated_images/`, the script copies the newest one across.
- **Model.** Some ChatGPT accounts reject the model set in `~/.codex/config.toml`
  for `codex exec` ("not supported when using Codex with a ChatGPT account"). Set
  `images.codexModel` in `ship.json` to a model the account accepts; the list is in
  `~/.codex/models_cache.json`.
- **Reference images.** Passed with `-i`. The script puts `-i` first because it
  takes several values and would swallow a trailing argument.
- **Speed.** About one to two minutes per image. `--jobs 2` (default) runs two at a
  time; more can hit plan rate limits.
- **Limits.** Exact pixel sizes are not guaranteed; the size is treated as the
  aspect ratio. Resize afterwards with `sips -z H W` or Pillow when exact pixels
  matter.

## codex-herdr

[Herdr](https://herdr.dev) is a terminal workspace for coding agents. When Claude
runs inside a Herdr pane (`HERDR_ENV=1`), this backend starts Codex as an agent
named `shipkit-images` in a new pane beside Claude and prompts it there.

- **Why use it.** The user sees Codex work and can talk to it directly ("make the
  second one warmer"). Codex keeps one conversation, so later images remember the
  earlier ones, which helps a set stay consistent.
- **How it runs.** `herdr pane split --current --no-focus` (right if the pane is
  wide, down if tall), `herdr agent start shipkit-images --kind codex`, then one
  `herdr agent prompt shipkit-images "..." --wait` per image. The agent is reused
  by later runs and by `imagine.py ask --herdr`.
- **Approvals.** If Codex stops to ask for permission (writing a file, for
  example), the script reports it and stops. Tell the user to approve it in the
  Codex pane, then run `gen` again; finished images are skipped.
- **Read its replies.** `herdr agent read shipkit-images`.
- **Clean up.** The pane stays open for more work. The user closes it when done,
  or ask before closing it for them.
- Only use Herdr commands when the user is in Herdr and chose this backend. Never
  start agents in panes the user is using.

## Asking Codex (second opinion)

`imagine.py ask "question" [--image path ...]` runs Codex read-only and prints its
answer. With `--herdr` (or when the backend is `codex-herdr`) it asks the agent in
the pane instead, so the conversation carries on there. Good uses: naming
shortlists, tagline variations, critique of a moodboard or screenshot, a check of
App Store copy. Weigh its answer; do not forward it as the decision.

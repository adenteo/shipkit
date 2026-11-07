# Motion: easing, springs, follow-through, haptics

The bars: no linear motion (everything needs "bezier touch"), Apple-level interactions, 60 fps
throughout, no idle pulses, characters never idling in step. Helpers are in `scripts/rive_keys.py`
(rigs) and `scripts/uilib.py` (pieces).

## Keys

- **Key poses at turning points, and let the eases do the work.** A key every frame or two is a
  sampled function and reads dead. Baked motion (exported from another tool) is usually keyed every
  2 frames: re-key it.
- Re-keying a baked track:
  1. `parse_track` reads the keys and `sample` resamples them per frame;
  2. `fit_hermite` keeps the turning points (where motion stops or reverses, or enters or leaves a
     plateau), plus whatever the error tolerance asks for;
  3. `hermite_track_body` writes `cubicValue` keys with handles at thirds, so each segment IS the
     Hermite cubic (full speed through a pass-through key, zero at a stop).
  Result on a real rig: 2,300 keys became about 150 per move, and the file got smaller.
- **An ease shapes the segment that LEAVES its key.** `interpolationType="cubic"` needs a
  `CubicEaseInterpolator` child, or it eases nothing. The last key is `linear`. `hold` snaps at the
  next key.
- Named eases (`rive_keys.EASES`, `uilib.CURVES`):

  | Name | Use |
  |---|---|
  | `io` | leave and arrive softly |
  | `sine` | swing between extremes |
  | `out` | fast start, long soft arrival |
  | `soft` | gentle ease out |
  | `in` | gathering speed |
  | `back` | overshoot a little, settle |
  | `pop` | a bigger overshoot |
  | `up` / `down` | the two halves of a parabola, for real jumps and arcs |

- `cubicValue` keys (`CubicValueInterpolator y1/y2` in VALUE units) let you write exact Hermite
  segments. `cubic` (`CubicEaseInterpolator`) is CSS-style timing on 0..1.

## Follow-through and overshoot: run tracks through a spring

`rive_keys.spring(values, freq, damping)` is a damped spring chasing the sampled curve, with
substeps for stability. The last eighth of a second eases onto the authored end, so the clip still
ends where it should. Then re-key the result with `fit_hermite`.

Starting values that worked on a mascot (frequency in Hz, damping ratio):

| Part | Freq | Damping |
|---|---|---|
| hat rotation | 4.0 | 0.38 (floppy) |
| hat slot x/y | 5.0 | 0.45 |
| accessory | 4.5 | 0.40 |
| face and eyes x/y | 6.0 | 0.55 |
| body lean | 7.0 | 0.60 |
| upper arms | 6.5 | 0.50 |
| forearms | 5.5 | 0.45 (trail more) |

- Parts that hang off the body lag a frame or two, swing past each stop and settle.
- Never spring loops (idle, breathing) or a run cycle. Their seams and stride must stay exact.

## A hand-authored move (a wave)

Every big gesture is built the same way:

1. anticipation: the body dips and leans away, and the arm pulls in;
2. a rise on an overshooting ease;
3. the first swing big and fast, a softer second, a small third;
4. a settle;
5. a drop with the wrist trailing and a small bounce at the bottom;
6. face and hat lag a few frames behind the body throughout.

- Keep the duration and the exit times, so the state machine is unchanged.
- **Mirror moves key for key** for the other side: rotations swap sides as negated deltas from each
  rest, other x values and rotations reflect about their setup values, and eases and `cubicValue`
  handles are copied. That way the springs carry over.
- Jumps follow the `up` and `down` parabola halves. A jump with a linear y reads as floating.
- Squash and stretch conserve volume: when scaleX goes up 16 percent, scaleY goes down about 16.

## Reactions that compose with anything

Wrap the body in new nodes, each keyed by one reaction only:

```
MotionRoot > Props > PoseRoot > DragRoot > TouchRoot > PokePivot > PokeUnpivot > BreathingRoot
```

Each touch reaction keys only its own node, so a poke plays over a wave. A squash about the FAR side
of a poke (pivot and unpivot nodes) makes the touched side give, like a dent.

## Idle life without loops

- **UI pieces:** steady states are one-frame one-shots, and the app fires an `idle`, `shine` or
  `twinkle` trigger every 9 to 16 s while the page is up. At rest nothing draws.
- **Characters:** the app owns blinking and idle beats on each character's own seeded clock (seeded
  by the look, a partner half a loop on).
  - Do not put blinks in the rig's Idle. Idle is entered with `reset="true"`, so every move restarts
    it from frame 0, and two characters blink in step whatever phase the app gave them.
  - A blink is a swap to a closed-eye arc for 120 ms, not the eye squashed to a line.
  - Occasional moves (yawn, stretch, nod off) come from a random pick, never within 6 s of a touch.
- **A looping mark** is a 6 s loop that never repeats a beat inside it: a heartbeat, a blink, a
  nuzzle, a hop, a glance. Its "asleep" variant breathes out of step. Never a plain pulse.

## Events to haptics and sounds

- Declare `<Event name="h:pop" id=.../>` on the artboard. Key it with a `KeyFrameCallback` on
  property 395 at the impact frame (`uilib.Anim.event`, `rive_keys.track_xml(ids, CALLBACK, ...)`).
- Name events for their meaning: `h:land`, `h:knock`, `h:coin`, `m:squish`, `m:bounce`. The app maps
  each name to a haptic or sound.
- Haptics from a mascot only within 1.6 s of a touch or a played moment. Sounds only after a touch.
  Idle life never buzzes.
- Lotties follow the same rule: the haptics are in the file as markers
  (`haptic:<kind>[@intensity]:<n>`, see the lottie skill), not guessed in app code.

## Frame rate rules (60 fps, measured)

- No live blur or material re-blurred under an animation, no per-frame shadows, no 60 fps
  `TimelineView` glare forever. Each was a measured hitch.
- Pause every player you cannot see. Play at 60 and pause, rather than 30.
- A Rive view inside a full-screen cover costs a view controller, a hosting controller and a new
  Rive view per open (visible lag). Keep the player mounted and toggle it.
- Keep haptic generators alive and prepared. A new generator per tick woke the engine on main.
- The simulator has no haptics and uses a Mac's GPU, so judge feel and frame rate on a device.

## UI piece motion vocabulary (tab icons, buttons, toggles)

| Moment | Motion |
|---|---|
| press | squish from the base while the finger is down, then a jelly rebound on release |
| select | full colour plus a 4 percent lift with a little pop, then rest |
| tap reaction | once per tap, and restartable (two copies alternated or a state-to-itself transition) |
| disabled | paper with quiet ink, a 180 ms mix. A dimmed saturated colour over a coloured ground can read as brown. |
| inactive tab colour | `uilib.muted`: saturation to 0.35, then 0.7 over the bar colour, keyed on every registered colour |

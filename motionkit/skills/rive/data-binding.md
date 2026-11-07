# Data binding and the app side

Rive's own `data.md` (1,400 lines) and `state-machines.md` are the reference. This file covers what
we use and what bit us.

## View models are the API between the file and the app

```xml
<ViewModel defaultInstanceId="0:202" name="Avatar" id="0:200">
  <ViewModelPropertyColor name="bodyColor" id="0:201"/>
  <ViewModelPropertyNumber name="eyeMood" id="0:203"/>
  <ViewModelPropertyTrigger name="wave" id="0:204"/>
  <ViewModelPropertyAssetImage name="hatImage" id="0:205"/>
  <ViewModelInstance exports="true" name="Default" id="0:202">
    <ViewModelInstanceNumber propertyValue="0" viewModelPropertyId="0:203"/>
    ...one value per property, in EVERY instance...
  </ViewModelInstance>
</ViewModel>
<Artboard viewModelId="0:200" ...>
```

- Adding a property means adding a value to every instance as well. `rive_keys.add_vm_properties`
  does both and asserts the count.
- A bind is a `DataBindContext` inside the target, naming the source path and the target property
  key:
  - `<DataBindContext sourcePathIds="0:200-0:201" propertyKey="37"/>` in a `SolidColor` binds its
    colour;
  - key 13 binds x, key 16 binds scaleX;
  - key 206 binds an `Image`'s assetId, for an image property;
  - a bound `Image` takes whatever picture the app hands it.
- Bind paths are absolute (view model id, then property id). Dangling paths compile. Check with
  `rive inspect . --json | jq '.problems'`.
- `--data=eyeMood=3 --data=bodyColor=FFF2A2B0` sets values headless.

## A view model as a pattern library (a character)

| Property | Kind | How it is used |
|---|---|---|
| `bodyColor` | colour | Bound to every body fill. Shading layers are white or black at low alpha, so every catalogue colour shades alike. |
| `clothingStyle` | number | A layer with one state per value. Each state plays a one-frame animation that sets the outfit Solo's `activeComponentId` (and sleeve occlusion widths). |
| `eyeMood`, `eyeStyle` | number | Each eye's drawings sit in a `Solo` (one child drawn at a time) under its open/close node, picked by a layer the same way. Highlights live inside the eye node, so blinks close them. |
| `hatImage`, `glassesImage`, `accessoryImage` | asset image | Bound to an `Image`'s assetId. Any piece drawn later in the canvas layout is a new item with no rig edit. |
| `lensFit` | number | Opacity and transform on NEW parent nodes that nothing else keys, so no mood, blink or action brings an eye back under dark lenses. |
| `lookX`, `lookY` | number | Bound through an eased `DataConverterInterpolator`, so the app feeds gaze at 30 Hz and the eyes still glide. |
| `dragLean`, `dragStretch`, `energy`, `blush` | number | Range mapper to radians or scale, then interpolator, as a `DataConverterGroup`. `energy` drives a 1D blend (0 droopy, 50 as drawn, 100 bouncy) eased over 1.2 s. |
| `pokeA`/`pokeB`, `boop`, `fling`, `wave` | trigger | Transition conditions (`rive_keys.trigger_condition`). Two triggers alternate because a layer will not re-enter its own state. |
| `waveSide`, `facing` | number | `waveSide` 1 takes key-for-key mirrored moves (AnyState transitions placed before the originals). |

## Converters

`rive_keys.py` writes them:

- `interpolator_converter`: `DataConverterInterpolator` with a cubic ease and a duration. The FILE
  eases a value the app sets in steps.
- `mapper_converter`: `DataConverterRangeMapper` from -1..1 to radians or a scale range.
- `group_converter`: chains converters.

Ease inside the file wherever the app would otherwise animate a property frame by frame. That is one
write instead of 60 a second, and it keeps the main thread free.

## Legacy inputs vs view model properties

- UI pieces (`uilib.Machine`) use legacy state-machine inputs (`bool`, `number`, `trigger`), because
  a runtime's `setInput` drives them simply.
- The headless `--data` flag cannot set them. `scripts/shoot.py` rewrites input defaults in a temp
  copy instead.
- New, richer pieces use view models. They are bindable, convertible and inspectable with
  `--data-dump`.

## Listeners writing back (no app code)

```xml
<StateMachineListenerSingle targetId="0:150" listenerTypeValue="click" name="Tap tab">
  <ListenerViewModelChange>
    <BindablePropertyNumber propertyValue="260">
      <DataBindContext sourcePathIds="0:200-0:201" propertyKey="636" direction="true"/>
    </BindablePropertyNumber>
  </ListenerViewModelChange>
</StateMachineListenerSingle>
```

- `direction="true"` makes it a write. Without it, the click does nothing and nothing reports it.
- To toggle or step a value, set `fromViewModelProperty="true"` and give the bindable property a read
  context plus the write (see `state-machines.md`, "A control that stays put").
- Every listener under the pointer fires, not just the top one.
- If the app wants to decide what a touch means (hello, wardrobe, ring), put a clear native layer
  over the view and drive view model inputs. Use Rive listeners when the file owns the interaction
  (the 3D phone's screen).

## Gotchas specific to binding

- `--data` is silently overridden by a two-way bind. The fix is `sourceToTargetRunsFirst="true"` on
  the `DataBindContext`.
- Probe a suspect bind with a number, not a string.
- A Luau `init` is called twice, and `context:viewModel()` is nil on the first call. Guard it or the
  handle stays nil forever.
- `ScriptInput*` match the Luau fields BY NAME, silently. A typo leaves the default.
- Script inputs: `ScriptInputNumber`, `Boolean`, `String`, `Color`, `Trigger`, `ViewModelProperty`
  and `Artboard` (`artboardId`, for the artboard-as-texture technique).
- `Image:view()` on an `ImageAsset` samples zeros on the GPU path. Draw it into a `context:canvas()`
  first.

## The app side (rive-ios)

- Set data, never rebuild views. Republishing an unchanged look (`@Published` fires on every set)
  whenever a character appeared rebuilt the whole screen. Compare before you set.
- Images for bound properties: `RiveRenderImage(data:)` from PNG bytes, decoded once and cached.
  Decode off main for big ones.
- Events come back by name (`onRiveEventReceived`), and the app maps them to haptics
  ([motion.md](motion.md)).

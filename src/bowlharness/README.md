# bowlharness

Records runs of the game under [xemu](https://xemu.app): played by a person, or driven along a request's route, with a
landing test, a control or an inject test at its target. A recording and a record run write nothing to the guest's
memory; a landing writes only the stale pointer and what goes with it, an inject test only the words its request names,
and every write is in the run's write ledger. Input is button
presses, which touch no game state.

## Setting up

- [uv](https://docs.astral.sh/uv/) and `uv sync` at the repository root.
- A gdb for the harness to run inside: `--gdb <gdb.exe>` before the command
  (`uv run python -m bowlharness --gdb <gdb.exe> drive ...`), or else the `BOWL_GDB` environment variable, or else the
  one on `PATH`. It needs Python scripting with an embedded Python of the version in `.python-version`, because the
  harness can't see a virtual environment from inside gdb, and the remote protocol, to talk to xemu's debugger stub as
  an x86 target. On Windows the MSYS2 UCRT64 gdb (`C:\msys64\ucrt64\bin\gdb.exe`) has both.
- The emulator, given with `--xemu <xemu.exe>` or else the `BOWL_XEMU` environment variable.
- xemu, with a controller bound to port 1 in the configuration you record with. Without one the game's first frame of
  play crashes in the input read, so the harness refuses to start.
- Close any running xemu first: the harness starts its own, which holds the storage image.

## How long a run takes

Live runs are slow, and what a run observes decides how slow. Heap logging stops the guest at every allocation of
every logged scene, which makes it about ten times slower, and each capture copies megabytes. Observe only what the run
is for:

- A recording something will replay (a recipe, the survey) needs `heap_events: all` and `cutoff_captures: all`:
  `place` replay-validates every load of a recipe, so a load logged without its heap events fails it.
- Anything else, such as a check of navigation, a result, a landing, a control or an inject test, needs `heap_events: none` and
  `cutoff_captures: none`, and a small `capture_budget`.

Before asking a person to run one, say how long it should take. Measured on the official disc:

| Run | Wall time |
|---|---|
| New game to `BB02`, one cheat, nothing logged | about 50 s |
| The six-step acceptance route, nothing logged | about 80 s |
| The six-step acceptance route, every heap event and cutoff capture | about 5.5 min |
| Each visit to the Options menu, on top | about 10 s for a 16-press entry, 7 s for an 8-press one |
| A landing, a control or an inject test at its target, nothing logged | the route to it, plus its windows (20 s of render and 15 s of reset by default); about 100 s at `B101`'s first visit, whose own reset ends the render window after about 10 s |

## Recording

```
uv run python -m bowlharness record --xemu <xemu.exe> --config <xemu.toml> --out <new folder>
```

`--out` must be an absolute path to a folder that does not exist. Each recording of the session gets a folder inside
it. A recording holds `manifest.json`, `events.jsonl` and, when asked, `captures/`; captures and event streams hold game
memory, so keep them off GitHub.

| Option | Meaning |
|---|---|
| `--heap all\|none\|BB02,B101` | which scenes log every heap event; a scene's init always logs its heap state |
| `--captures cutoff:all\|cutoff:none\|cutoff:BB02` | which scenes take a capture at the cutoff |
| `--budget <n>` | the most captures to take; a crash or hang capture is always taken |
| `--attach <port>` | attach to a running xemu started with `-gdb tcp::<port> -S`, instead of starting one |
| `--liveness <seconds>` | how long play may stall before it is a hang (default 5). While the guest is silent, gdb prints `Program received signal SIGINT` each time the watchdog looks at it; a longer window prints less |

Starting xemu runs it in its own console, so Ctrl-C in the gdb window can never reach it. The harness resets the machine
and the game boots as if freshly started. Play as usual; do not load xemu's own snapshots during a recording, since the
stream can't show one and the heap's continuity breaks silently.

## Driving

```
uv run python -m bowlharness drive --request <request.json> --xemu <xemu.exe> --config <xemu.toml> --out <new folder>
```

Follows a record request instead of waiting for a person to play: it takes the same `--out`, `--xemu`, `--config`,
`--port`, `--attach` and `--liveness` options as `record`, and the request owns what is observed. Hands off the
controller: a button pressed on it is logged as a person's press and marks the run attended. The run ends when the
route is done or a step fails, and closes the xemu the harness started. When the session ends it writes the run's
result, `result.json`, in `--out` beside the recordings, and prints its outcome.

A landing request also needs `--place <bowlbuster.exe>`, a copy of `bowlbuster` published outside the repository
(`dotnet publish src/BowlBuster.Cli -c Release -o <new folder>`), and `--recordings <folder>`, the folder its recipes
are named under. The harness pins the tool when it starts and records it in the result. A control and an inject test need neither.

A request that starts from a save (`"start": {"from": "save", "save": "<name>"}`) needs `--saves <folder>`, the save
library ("The save library", below). It is refused unless the library holds the save and the first step is the scene
the save loads into. The run plays on a fresh copy of the save's image in `<folder>/work/drive/`, with xemu started
on a copy of `--config` that differs only in `hdd_path`, and can't `--attach`. Loading a save through the main menu
isn't built yet, so such a run fails its first step as `unsupported`.

## Queueing

```
uv run python -m bowlharness queue --store <folder> --instance <name> --xemu <xemu.exe> --config <xemu.toml>
```

Runs a store's requests one after another, unattended: each pending request in `<folder>/requests/` is claimed, the
guest rebooted (for a request that starts from a save, xemu is closed and started again on a fresh copy of the save's
image, and again on the instance's own storage for the run after it), and the request run into `<folder>/runs/<request>-a<attempt>/`, with its result there. Progress goes to
`<folder>/progress.jsonl`. It takes `--place` and `--recordings` for landings and `--saves` for starts from a save, as `drive` does, and stops when nothing
is pending, the emulator is lost, or a person runs `bowl stop`. Started again, it reports the runs a lost session left
as `interrupted` and claims them again as new attempts.

## The save library

```
uv run python -m bowlharness saves add --saves <folder> --image <xbox_hdd.qcow2> --name <image>
    --save <slot>:<name>:<scene> [--save ...] [--about <name>:<text> ...]
uv run python -m bowlharness saves list --saves <folder>
```

The library holds xemu storage images with the game's saves in them, each under a name that is unique across the
library. `add` copies an image into `<folder>/<image>/`, with an `image.json` holding its SHA-256 and its saves: the
slot (1 to 3), the scene the save loads into, and what was played to make it. It never changes the image it copies,
refuses while xemu runs, and refuses a name the library already holds. A library image is never run: a run that
starts from a save plays on a fresh copy in `<folder>/work/<instance>/`, which the game writes to (it autosaves at
every token). These commands need no gdb.

## Requests and results

A request's and a result's spelling is the JSON schemas in `schema/` at the repository root. The types the harness
reads them into, in `contract/generated/`, are generated from those files and never edited by hand. After changing a
schema, run

```
uv run python scripts/generate_contract.py
```

and commit the schema and the generated files together; a test fails while they disagree.

## Taking control

Press Ctrl-C in the gdb window to pause the guest, then:

| Command | |
|---|---|
| `bowl capture <label>` | take a labelled capture |
| `bowl read <address> <length>` | print guest memory (the log keeps the range, not the bytes) |
| `bowl press <button> [<polls>]` | give the game a button on the next resume, for 6 polls unless told (`a`, `b`, `x`, `y`, `start`, `back`, `l`, `r`, `up`, `down`, `left`, `right`) |
| `bowl resume` | let the guest run again |
| `bowl stop` | end the session and close the xemu the harness started |

Each of these marks the run `attended` in its manifest. A reboot of the game ends the recording and opens another; a
crash or a hang ends the session; so does the emulator exiting.

# bowlharness

Records a run of the game under [xemu](https://xemu.app), as a person plays it. It only observes: it writes nothing to
the guest's memory, and its recording says so.

## Setting up

- [uv](https://docs.astral.sh/uv/) and `uv sync` at the repository root.
- A gdb for the harness to run inside, found through the `BOWL_GDB` environment variable or else `PATH`. It needs
  Python scripting with an embedded Python of the version in `.python-version`, because the harness can't see a virtual
  environment from inside gdb, and the remote protocol, to talk to xemu's debugger stub as an x86 target.
- xemu, with a controller bound to port 1 in the configuration you record with. Without one the game's first frame of
  play crashes in the input read, so the harness refuses to start.
- Close any running xemu first: the harness starts its own, which holds the storage image.

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

## Taking control

Press Ctrl-C in the gdb window to pause the guest, then:

| Command | |
|---|---|
| `bowl capture <label>` | take a labelled capture |
| `bowl read <address> <length>` | print guest memory (the log keeps the range, not the bytes) |
| `bowl resume` | let the guest run again |
| `bowl stop` | end the session and close the xemu the harness started |

Each of these marks the run `attended` in its manifest. A reboot of the game ends the recording and opens another; a
crash or a hang ends the session; so does the emulator exiting.

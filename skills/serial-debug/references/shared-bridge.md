# Shared Bridge Workflow

Use the bundled bridge when a human and agent need the same local serial port at the same time.

The bridge process owns the physical port. Human terminals and agent senders connect to `127.0.0.1:<tcp>`.

The bridge keeps its TCP listener alive across transient serial-port failures. It closes stale TCP clients, retries the physical port once per second, and resumes broadcasting after the port reopens. The interactive client reconnects automatically; commands typed while disconnected are discarded and must be entered again after the reconnect message.

## Manual Windows Menu

For a persistent bridge that the human can start and stop without an agent, double-click:

```powershell
windows\serial_console.cmd
```

The Chinese menu exposes release and detect/connect as separate operations. Menu item `4` only stops its managed bridge and releases the current COM handle. Menu item `5` requires that release first, then detects the next attached or reattached port, persists it in the ignored `windows/serial_config.local.psd1`, starts the bridge, and opens pySerial `miniterm` through the bridge's `socket://` endpoint. It does not terminate unrelated applications that may own a COM port.

## Start The Bridge

```bash
python scripts/shared_serial_bridge.py bridge --port COM10 --baud 57600 --tcp 8888 --chardelay 0.005
```

On Windows, launch the bridge hidden or in a separate terminal so it keeps running.

Append `--autobaud` to monitor the receive stream for sustained garbled output and re-scan the baud rate automatically (passive: no bytes are ever sent). Add `--autobaud-probe` to allow the re-scan to send Enter probes (for devices that go quiet after switching baud). `--autobaud-bauds 115200,921600` narrows the candidate list. While a scan runs, forwarding pauses for a few seconds and every terminal sees a Chinese status line; when a winner is found the bridge switches baud immediately and announces it.

## Process Terminal Bridges (proc://)

The same bridge can share a local Windows console process instead of a COM port. `--port proc://<preset>` spawns the child and owns its stdin/stdout; human terminals and agent senders connect exactly as they do for serial, so a human and an agent share one live CMD/PowerShell/REPL session.

```bash
python scripts/shared_serial_bridge.py bridge --port proc://powershell --tcp 8890
```

Presets:

| Endpoint | Child process | Notes |
| --- | --- | --- |
| `proc://cmd` | `cmd.exe /Q /K` | Prompt comes from cmd itself; console codepage stays ANSI (GBK on zh-CN), so use `--encoding gbk` on `connect`/`send` for Chinese output. |
| `proc://powershell` | `pwsh` if installed, else `powershell -NoProfile -NoLogo -Command -` | Output is forced to UTF-8 by the bridge. |
| `proc://python` | The bridge's own Python REPL (`-u -i`, UTF-8) | Prints `>>>` prompts. |
| `proc://<exe>` | Any executable found on PATH (or an absolute path) | Combine with `--proc-args "..."` and `--proc-cwd <dir>`. |

Behavior differences from a serial port:

- Line input only. The bridge assembles keystrokes into lines (backspace edits the pending line, Ctrl+C clears it), normalizes them to CRLF, and mirrors every completed line to all raw terminals and the session log — a piped shell echoes nothing itself, so typed characters do not appear until Enter is pressed. Ctrl+C cannot interrupt a running command in pipe mode; escape bytes are dropped.
- No baud rate. `--autobaud` is ignored at startup, and `serial.baud` / `serial.autobaud` control calls are refused with `unsupported`.
- When the child exits (including a typed `exit`), `status.error` reports the exit code and the bridge stays up in the released state — it never silently respawns a different shell session. `serial.open` (or a GUI reconnect) pulls the endpoint back up with a fresh child.
- The Qt workbench attaches to a `proc://` bridge like a serial one: pick the `proc://` endpoint in the service dialog (baud is ignored). Attaching never reopens the child, so the shared session survives GUI connects and disconnects.

## Online Baud Detection (bridge keeps running)

```bash
python scripts/shared_serial_bridge.py autobaud --control 8889 --mode passive
python scripts/shared_serial_bridge.py autobaud --control 8889 --mode active   # sends Enter probes
```

Runs the same scan on demand against a running bridge (`--control` defaults to raw TCP + 1). Exit codes: `0` detected or confirmed, `2` no signal, `3` ambiguous, `4` bridge unreachable/disconnected, `5` wait timeout, `6` busy or agent-owned. A final `autobaud_result:` line is printed for scripted use.

## Bridge Health (data-plane status fields)

A control-port `status` call reports the data plane, not just the control plane:

- `rx_bytes_total` / `tx_bytes_total`: bytes actually forwarded in each direction. A frozen `rx_bytes_total` while the device demonstrably transmits means the bridge read path is dead — do not trust `connected:true` alone.
- `last_rx_timestamp`: epoch seconds of the last forwarded RX byte (`null` until the first byte arrives).
- `error`: serial/device errors and worker-thread deaths. A reader thread that dies or wedges sets `error` immediately and the bridge then stops itself loudly within a few seconds — it never lingers as a healthy-looking half-dead shell. Restart the bridge to recover.
- Log files open with a `=== bridge session start <timestamp> pid=<pid> ===` line, so bytes left in the file from an earlier session can never masquerade as new output.

Baud scans never overlap the bridge reader: a scan waits for the reader to park outside its read loop before touching the port, and a scan that cannot get that acknowledgment aborts with `reason: reader_unavailable` in `autobaud.status`. This protects the Windows overlapped-I/O path, where a concurrent read from the scan thread and the reader thread (one shared OVERLAPPED per port object) could otherwise wedge the reader permanently.

## Human Terminal

```bash
python scripts/shared_serial_bridge.py connect --tcp 8888
```

The human can watch live output and type commands here.
By default, pressing Enter sends `CR` only. This matches many embedded shells better than `CRLF`.
If the bridge restarts or drops the connection, leave this client open. It prints a short status message and reconnects without a Python traceback.

## Agent Command

```bash
python scripts/shared_serial_bridge.py send "misc md 0x00000000 4" --tcp 8888 --newline
```

Use `--newline` for command shells that execute on Enter. The agent's command and device response are visible to other clients connected to the bridge.
If a device expects a different line ending, use `--line-ending crlf` or `--line-ending lf`.

Exit codes: `0` a response arrived (or `--expect` matched), `2` the connection dropped before the response settled (unknown outcome — inspect the bridge log and target prompt before retrying), `3` sent but nothing came back inside the response window, `4` output arrived but `--expect` never matched.

Empty output with exit 3 is not "device dead": the command was delivered, but slow boot chains (25s+ before the first banner) or a swallowed first byte can leave the 0.8s idle window empty. Verify the link by connecting a bare socket to the shared endpoint, draining ~1s, sending a bare CR, and waiting for the prompt. For scripted calls that must confirm an actual answer, add `--expect <pattern>` (substring match on the decoded stream; `--expect-timeout` caps the wait, default 10s) — with `--expect` a quiet gap no longer ends the read early, only the pattern, the deadline, or a disconnect does.

When the agent must hold the port exclusively, use the Windows controller's `-Exclusive` send or the managed `agent.acquire` / `agent.heartbeat` / `agent.release` lease (see SKILL.md → Agent Connection); tokenless control actions and raw writes are rejected with `occupied` while a lease is held.

## Coordination Rules

- Do not kill the human terminal to let the agent send a command.
- Do not open the physical COM port directly while the bridge owns it.
- If a command changes state, announce it first.
- Keep commands small and read the response before sending the next command.
- Use the bridge log when reconstructing what happened.

## Known Good Example

For `COM10` at `57600`:

```bash
python scripts/shared_serial_bridge.py bridge --port COM10 --baud 57600 --tcp 8888 --chardelay 0.005
python scripts/shared_serial_bridge.py connect --tcp 8888
python scripts/shared_serial_bridge.py send "misc md 0x00000000 4" --tcp 8888 --newline
```

Expected style of output:

```text
misc md 0x00000000 4
I/misc_TEST ... 0x00000000 :  0x342022f3
atom_io>>
```

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

## Online Baud Detection (bridge keeps running)

```bash
python scripts/shared_serial_bridge.py autobaud --control 8889 --mode passive
python scripts/shared_serial_bridge.py autobaud --control 8889 --mode active   # sends Enter probes
```

Runs the same scan on demand against a running bridge (`--control` defaults to raw TCP + 1). Exit codes: `0` detected or confirmed, `2` no signal, `3` ambiguous, `4` bridge unreachable/disconnected, `5` wait timeout, `6` busy or agent-owned. A final `autobaud_result:` line is printed for scripted use.

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

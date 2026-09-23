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
`send` exits nonzero if the bridge disconnects before the response becomes idle. Treat that as an unknown command outcome; inspect the bridge log and target prompt before deciding whether it is safe to retry.

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

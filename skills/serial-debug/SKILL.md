---
name: serial-debug
description: Shared serial console debugging for Codex and Claude Code. Use when a human and an agent need concurrent access to the same UART, RS-232, USB-serial, or COM port with live human viewing/input, agent command injection, logging, prompt synchronization, and safe recovery from desync or timeouts. Prefer the bundled TCP bridge on Windows/local setups; use Conserver when it is installed and already manages the serial console.
---

# Serial Debug

## Operating Rule

Use a shared middle layer whenever the human and agent both need the same live serial console. The middle layer owns the physical port; humans and agents connect to the middle layer. Do not close the human terminal just to let the agent send commands.

Use the bundled TCP bridge for local Windows/COM-port work. Use Conserver when it is already installed or the environment needs a managed multi-user console server.

## Workflow

1. For local Windows work where the human wants manual start/stop control, use the bundled menu:

```powershell
windows\serial_console.cmd
```

Configure `windows/serial_config.psd1`, then use the menu to start the bridge, open a terminal, inspect status, or stop and release the COM port. Exiting the menu does not stop an already-running bridge.

2. For command-line-only work, start the bundled bridge directly. The bridge owns the physical port and exposes a local TCP socket:

```bash
python scripts/shared_serial_bridge.py bridge --port COM10 --baud 57600 --tcp 8888 --chardelay 0.005
```

3. Open the human terminal against the bridge:

```bash
python scripts/shared_serial_bridge.py connect --tcp 8888
```

The bundled bridge defaults to `CR` for Enter because many embedded shells treat `CRLF` as two submissions and print the prompt twice.

4. For agent attachment and command execution after the bridge starts, follow **Agent Connection** below.

5. If Conserver is available, use its client instead of the bundled bridge:

```bash
conserver -V
console -V
console -s <CONSOLE>
console -a <CONSOLE>
```

6. Use prompt history and replay options to resynchronize after boot noise, resets, or missed output:

```bash
console -A <CONSOLE>
console -F <CONSOLE>
console -S <CONSOLE>
```

## Agent Connection

When the user says the bridge is running, preserve that bridge and the human terminal. The bridge remains the only owner of the physical COM port; the agent attaches to its local TCP endpoint.

1. Resolve the current endpoint before sending. Locate a Windows controller in the active workspace with `rg --files -g serial_console.ps1`. If one is available, use its status action so the physical port, baud rate, line ending, endpoint, and managed PID come from local configuration; when multiple copies exist, select the one whose status reports the running managed bridge and matches the user's endpoint:

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "<path>\serial_console.ps1" -Action Status
```

Otherwise use the endpoint explicitly supplied by the user or printed by the running bridge. Never guess an endpoint or open the physical COM port directly while the bridge owns it.

2. Prefer the controller for routine agent commands because it applies the configured encoding and line ending and verifies that the managed bridge is running:

```powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "<path>\serial_console.ps1" -Action Send -Command "help"
```

If the controller is unavailable, use a short-lived `send` client against the resolved endpoint:

```bash
python "<skill-dir>/scripts/shared_serial_bridge.py" send "help" --host 127.0.0.1 --tcp 8888 --newline --line-ending cr
```

Use `send` for ordinary agent command/response work. Use the persistent `connect` client only when the user explicitly asks the agent to maintain an interactive session.

3. Read the complete response and exit status before sending the next command. The human terminal should display the same command and device response. A nonzero exit after transmission means the device outcome is unknown: inspect the shared terminal, prompt, and log before deciding whether a retry is safe.

4. Read-only diagnostic commands are within an ordinary debugging request. Reset, erase, register or memory writes, flashing, boot-mode changes, and persistent configuration changes require an explicit user request that authorizes that state change; announce the change immediately before sending it.

## References

- Read `references/shared-bridge.md` for the bundled bridge workflow.
- Read `windows/README.md` for the user-controlled Windows menu.
- Read `references/conserver.md` for Conserver workflow, access modes, and coordination rules.
- Read `references/console-client.md` for Conserver client command details.
- Read `references/hardware-safety.md` before changing baud, wiring, voltage levels, RTS, DTR, reset/boot lines, or any access mode that can reset the target.
- Read `references/troubleshooting.md` when a command fails, times out, loses sync, or two users collide on write access.

## Reporting

Report the shared endpoint, physical port, baud rate, command, exit status, and relevant output excerpt. If no hardware is connected, say that only bridge/client discovery was verified and mark device round-trip validation as manual.

## Source Maintenance

The canonical source is `https://github.com/493935827/serial-debug`. When the user requests changes to this skill, keep completed scripts and documentation synchronized to that repository and report the pushed commit URL. Keep local configuration, logs, Python caches, and runtime PID files out of Git.

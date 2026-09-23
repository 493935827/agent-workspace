# Troubleshooting

## No Ports Found

Run:

```bash
python scripts/shared_serial_bridge.py bridge --port COM10 --baud 57600 --tcp 8888
console -x
console -w
```

Check cable, adapter driver, permissions, and whether another tool already owns the console or write access.

## COM Port Is Busy

- If using the bundled bridge, this is expected: the bridge owns the physical port.
- Do not start `miniterm` or another direct serial client against the same COM port.
- Connect to the bridge with `python scripts/shared_serial_bridge.py connect --tcp 8888`.
- Agents should use `python scripts/shared_serial_bridge.py send ... --tcp 8888 --newline`.

## Console Open Fails

- Verify the console name exactly matches discovery output.
- Close other console clients, flashing tools, or old sessions using the same console.
- Try the known protocol baud rate instead of the default.
- On Unix-like systems, check device permissions for `/dev/tty*` or `/dev/cu*`.

## Read Times Out

- Confirm the target firmware actually writes serial output.
- Increase `--timeout-ms`.
- Check line endings and whether the device expects a command terminator.
- For request/response protocols, ensure the agent has write access before typing.

## Serial Port Disconnects During A Session

- Keep the interactive client open. It reconnects to the bridge automatically.
- Wait for `serial_reconnected` in bridge output and `reconnected` in the interactive client before entering the command again.
- Commands typed while disconnected are discarded so stale input is not replayed after a target reboot.
- If `send` exits nonzero, inspect the serial log and prompt before retrying; the target may have received only part of the command.
- If the TCP listener is alive but a new `help` command produces no serial echo, the running bridge predates automatic serial recovery or is otherwise unhealthy. Verify its exact process command line, replace only that bridge process, and restart it without `--reset-dtr` unless a target reset was explicitly requested.

## Data Looks Wrong

- Recheck the console attachment mode.
- Confirm baud, parity, stop bits, and flow control.

## Write Access Collides

- For Conserver, check who currently has read-write access with `console -w`.
- For the bundled bridge, coordinate in chat before sending state-changing commands.
- Keep the human terminal open; the agent should use the shared TCP endpoint.

## Control Lines Do Not Behave As Expected

- Confirm adapter wiring for RTS and DTR.
- Check whether the target inverts or routes the lines through reset or boot circuitry.
- Treat the console response as requested state evidence, not as electrical measurement evidence.

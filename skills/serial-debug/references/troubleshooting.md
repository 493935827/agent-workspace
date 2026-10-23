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
- Increase the bundled `send` client's `--max-wait` (total wait) or `--idle` (quiet period that ends a read).
- Check line endings and whether the device expects a command terminator.
- For request/response protocols, ensure the agent has write access before typing.

## send Returns Nothing (empty output, exit 3)

- Exit 3 means the command was sent but no byte came back inside the response window. It does NOT mean the device is dead: boot chains can stay silent for 25s+ and some devices swallow the first bytes after a reload.
- Check whether the command still reached the device: the bridge log records what was written, and the human terminal shows the echo.
- Verify the link with a bare socket: connect to the shared TCP endpoint, drain ~1s, send a bare CR (`b"\r"`), and wait ~1s for the shell prompt. A prompt means link and board are both alive; then re-send the command with `--expect <prompt-pattern>` so the exit code reflects an actual answer instead of an idle-window guess.
- If even the bare CR gets no prompt, press the board reset once and watch the bridge log for a boot banner before assuming a dead link.
- Exit 4 (with `--expect`) means output arrived but never contained the pattern: raise `--expect-timeout` or fix the pattern.
- Exit 2 still means the connection dropped mid-response; treat the outcome as unknown.

## Serial Port Disconnects During A Session

- Keep the interactive client open. It reconnects to the bridge automatically.
- Wait for the interactive client to print `[串口桥] 已断开，正在重新连接` followed by `已重新连接 <host>:<port>` before entering the command again.
- Commands typed while disconnected are discarded so stale input is not replayed after a target reboot.
- If `send` exits nonzero, inspect the serial log and prompt before retrying; the target may have received only part of the command.
- If the TCP listener is alive but a new `help` command produces no serial echo, the running bridge predates automatic serial recovery or is otherwise unhealthy. Verify its exact process command line, replace only that bridge process, and start it again with the same configuration; the bundled bridge never toggles DTR/RTS on its own, so a restart does not reset the target unless the adapter wiring does.

## TCP Alive But No Device Output (silent RX death)

- `connected:true` with `error:null` is not proof the read path works. Check the data-plane counters in `status`: if `rx_bytes_total` stays frozen and `last_rx_timestamp` stops advancing while the device demonstrably transmits, the bridge's reader thread is dead or wedged regardless of what `connected` says.
- A current build surfaces a dead worker in `status.error` and then stops the whole bridge within a few seconds; replace the bridge process and start it again.
- A bridge older than that fix can look perfectly healthy in `status` while forwarding zero bytes. Replace it: stop the bridge, start a fresh one (skill venv python, without `--autobaud`), and only re-add `--autobaud` once the link is proven.
- The log file grows only with forwarded RX bytes and opens with a `=== bridge session start ... ===` header. A frozen file whose tail predates the header means the read path produced nothing — the board is not necessarily dead.

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

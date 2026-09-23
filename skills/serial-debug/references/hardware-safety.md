# Hardware Safety

Shared serial debugging can change device state. Be explicit about the console name, access mode, baud rate, and control-line intent before touching hardware.

## Checks Before Writing

- Confirm the selected console comes from Conserver status output.
- Confirm voltage compatibility between the adapter and target board. Do not assume 5 V tolerance.
- Confirm the protocol baud rate, data bits, parity, stop bits, and flow control.
- Automatic baud detection must be passive by default: listen for target output, do not send probe commands or toggle break/DTR/RTS. If the target is silent, report that detection needs target output instead of guessing. Tell the user before asking them to reset or power-cycle the target.
- Avoid sending reset, erase, bootloader, or firmware-update commands unless the user requested that operation.

## RTS and DTR

RTS and DTR are often wired to reset or boot mode on development boards.
Before any line-toggle operation, mention that the change can reset or reconfigure the target if the adapter wiring uses those pins.

## Evidence Boundaries

If no device is connected, only report Conserver/client availability and console status. Mark device round-trip validation as manual.

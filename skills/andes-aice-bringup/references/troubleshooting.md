# Andes AICE troubleshooting

Use the first matching symptom. Change one variable at a time and preserve the MI_00/MI_01 driver split.

## `Can not open usb`

Inspect `iceman_debug1.log` rather than relying on the short console banner.

- `libusb_open() failed with LIBUSB_ERROR_NOT_FOUND` followed by `unable to open ftdi device with vid 0403, pid 6010` means Windows enumerated the FT2232 but ICEman cannot claim MI_00.
- Confirm MI_00 uses `libusbK`; `USB Serial Converter A` with service `FTDIBUS` is the wrong binding for this ICEman build.
- Install the Andes-bundled INF that targets only `VID_0403&PID_6010&MI_00`. Keep MI_01 on FTDIBUS.
- Check for existing ICEman/OpenOCD processes and listeners on 2354, 4444, 6666, and 9901 before retrying.

## CPU-release registers are `0xFFFFFFFF`

This is an invalid all-high SPI response, even when the Python process exits zero.

1. Stop ICEman/OpenOCD.
2. Restart the FTDI parent USB device or physically unplug and reconnect AICE. Process termination alone may leave FT2232 MPSSE/GPIO state active.
3. Run CPU release before starting ICEman.
4. If D2XX reports only one channel after MI_00 moved to libusbK, use the unique channel described as `Dual RS232-HS B`; it is commonly renumbered from index 1 to index 0.

If reads remain all F after a USB restart, investigate physical target power/VREF, SPI MISO and chip-select wiring, and whether B is actually the intended SPI interface. Do not hide this condition or continue to ICEman.

## `JTAG scan chain interrogation failed: all ones`

The USB layer works, but TDO is high or the target TAP is unavailable.

- Run the required CPU-release sequence first.
- Check target power, JTAG VREF, ribbon orientation, TDO continuity, and reset state.
- Lower JTAG frequency only after power and wiring checks; a stable all-ones result more often indicates no target response than marginal timing.

## Python fails before hardware access

- `No module named typing_extensions`: Python 3.11+ can import `Self` from `typing`; otherwise install the dependency into the selected interpreter.
- `No module named numpy`: install NumPy into that exact interpreter, not a different global Python.
- `No module named atom_io_spi`: locate the sibling `IO_DIE/Validation/python/{drivers,usr}` directories and add them to the script's import path.
- Missing `libmpsse.dll`: locate the Windows library from the matching validation package; do not load the Linux `.so` on Windows.

## Success signals

Require all of these:

```text
Andes AICE-MICRO H/W R1.1
JTAG frequency ...
There is 1 core in tap
```

The ICEman process must remain alive, and the configured GDB port must listen. Burner 2354, Telnet 4444, and TCL 6666 normally listen as well.

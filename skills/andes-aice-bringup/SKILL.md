---
name: andes-aice-bringup
description: Bring up and diagnose Andes AICE/ICEman on Windows when USB cannot open, FTDI/libusbK channels are misbound, the CPU must be released over SPI before JTAG, registers read 0xFFFFFFFF, the JTAG scan returns all ones, or an Andes ADX must be downloaded to SRAM with LMA/VMA-aware GDB verification. Use for this specific Andes AICE sequence, not generic OpenOCD adapters or standalone serial-console work.
---

# Andes AICE Bring-up

Establish a working ICEman session in the required order: make the AICE USB state clean, release the target CPU over the FTDI B channel, and only then initialize JTAG.

## Discover the installation

Resolve these paths from the workspace and installed Andes package instead of assuming a particular drive:

- The target's CPU-release Python script, commonly `atom_die_ll_cmd.py`.
- The Python interpreter that has the script's dependencies.
- The directory containing `ICEman.exe` and `interface/jtagkey.cfg`.
- The Andes-bundled Cygwin `bash.exe` beside the ICE installation.

Run `scripts/diagnose_aice.ps1` first. Treat it as read-only evidence. The working FT2232 driver split is:

```text
VID_0403&PID_6010&MI_00  libusbK  A channel for ICEman/JTAG
VID_0403&PID_6010&MI_01  FTDIBUS  B channel for SPI/serial
```

If MI_00 still uses FTDIBUS, inspect the ICE package's `libusb-AICE-driver/FTDI_USB_device.inf`; it should match only `MI_00`. Obtain authorization before running its administrator installer. Re-read both interfaces after installation and preserve MI_01 as FTDIBUS.

## Bring-up invariant

Use `scripts/start_aice.ps1` for the deterministic sequence. Running the CPU-release script after ICEman has initialized JTAG is the wrong order.

1. Stop existing `ICEman` and `openocd` processes and verify ports 2354, 4444, 6666, and 9901 are free.
2. Restart the parent `VID_0403&PID_6010` USB device, or have the user physically unplug and reconnect it. Stopping ICEman alone does not clear retained FT2232 MPSSE/GPIO state.
3. Wait until MI_00 and MI_01 both report `OK` with the required driver split.
4. Run the CPU-release script through FTDI channel B. When A uses libusbK, D2XX may renumber B from channel 1 to channel 0; select the unique channel whose description ends in ` B` rather than changing drivers back.
5. Treat any hardware register read of `0xFFFFFFFF` as a failed release. Do not start ICEman in that state.
6. Start ICEman through the Andes-bundled Cygwin environment. Require `There is 1 core in tap`, a live ICEman process, and listening ports as the completion signal.

Example invocation:

```powershell
& '<skill-directory>\scripts\start_aice.ps1' `
    -ReleaseScript 'C:\path\to\atom_die_ll_cmd.py' `
    -PythonExe 'C:\path\to\python.exe' `
    -IceRoot 'D:\path\to\Andes\ice' `
    -CygwinBash 'D:\path\to\Andes\cygwin\bin\bash.exe'
```

The USB restart triggers Windows UAC. Explain that effect before executing the starter. Leave the final ICEman process running when the user intends to attach GDB or ICMMEN.

Python `SyntaxWarning` messages about legacy backslash escapes are not a bring-up failure. A traceback, nonzero exit, `0xFFFFFFFF`, `Can not open usb`, or `all ones` is a failure.

For symptom-specific branching, read [references/troubleshooting.md](references/troubleshooting.md).

## SRAM ADX Debug

After ICEman is healthy, read [references/sram-adx-debug.md](references/sram-adx-debug.md) when an `.adx` image must be downloaded directly to SRAM, a packed image has different load and run addresses, PC falls into an illegal-instruction path after `load`, or firmware execution must be distinguished from a wrong UART/COM mapping.

UART verification is an optional downstream check, not an AICE bring-up prerequisite. For a shared human/agent UART session, invoke `serial-debug` if it is available; otherwise use an ordinary terminal. `serial-debug` remains independently usable and does not depend on this skill.

## Completion

Report the selected Python, AICE interface drivers, CPU-release evidence, ICEman PID, detected core count, and listening ports. The workflow is complete only when USB opens, the release step avoids all-F reads, ICEman detects the TAP core, and the requested debug port accepts connections.

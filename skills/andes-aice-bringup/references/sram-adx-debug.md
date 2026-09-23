# Andes ADX SRAM Debug

Use this workflow after ICEman has detected the TAP core and its GDB port is listening. It covers direct SRAM execution of an Andes `.adx` image, packed-image LMA/VMA handling, CPU-state diagnosis, and optional UART verification.

This workflow does not require a serial console. GDB download and CPU verification stand on their own. When UART output is part of the requested acceptance check, use an existing terminal or invoke `serial-debug` for shared human/agent access; keep all bridge ownership, reconnect, logging, and command-sending mechanics inside that skill.

## Authorization Boundary

Treat these as separate operations:

- USB/COM discovery, process inspection, ELF metadata inspection, and listener checks are read-only.
- Attaching GDB halts or otherwise changes CPU execution. SRAM `load`, setting PC, reset, and resume require explicit authorization for target-state changes.
- SRAM download permission does not authorize external SPI Flash erase/program, boot-strap changes, or persistent configuration changes.
- Opening a UART candidate can assert the adapter's default DTR/RTS state. Announce that risk before opening it; reset-line changes require explicit authorization.

Preserve the user's AndeSight workspace, launch files, linker scripts, toolchain installation, system PATH, ICEman configuration, and project build products. Use process-local PATH changes and temporary artifacts.

## Inspect The ADX Before Loading

Use the matching Andes toolchain with its Cygwin runtime added only to the current process:

```powershell
$toolBin = '<andes-root>\toolchains\<toolchain>\bin'
$env:PATH = "$toolBin;<andes-root>\cygwin\bin;$env:PATH"

& "$toolBin\riscv32-elf-readelf.exe" -h -S -l '<image>.adx'
& "$toolBin\riscv32-elf-gdb.exe" -q -nx -batch '<image>.adx' `
  -ex 'set pagination off' -ex 'info files'
```

Record the entry point, section virtual addresses, program-header physical addresses, and expected SRAM ranges before connecting to ICEman.

### Packed-image warning

GDB `load` writes ELF segments to their physical addresses (`p_paddr`, normally the section LMA). A bootable packed image can deliberately assign different addresses:

- VMA/`VirtAddr`: where the section executes;
- LMA/`PhysAddr`: where a bootloader stores the packed bytes before relocation.

If `PhysAddr != VirtAddr`, loading the packed image and then setting PC directly to its VMA entry can execute overwritten or unrelated bytes. A characteristic signature is a correct entry immediately after `load`, followed by PC dropping to a low address and `mcause=2` (`Illegal instruction`).

Preserve the production linker script and original ADX. Create a temporary SRAM-debug ELF whose load addresses equal its runtime addresses:

```powershell
& "$toolBin\riscv32-elf-objcopy.exe" `
  --change-section-lma '.nds_vector=<its-vma>' `
  --change-section-lma '.vector_table=<its-vma>' `
  --change-section-lma '.text=<its-vma>' `
  --change-section-lma '.rodata=<its-vma>' `
  --change-section-lma '.data=<its-vma>' `
  '<original>.adx' '<temp>\image-sram-debug.adx'
```

Include every allocated, nonempty section needed at runtime, including target-specific init tables, small data, vectors, stacks, loaders, or compute regions. Copy every VMA from `readelf`; never infer it from neighboring sections. NOBITS sections normally need no file payload because startup code clears them.

Verify the temporary image with `readelf -l`. Require `PhysAddr == VirtAddr` for every LOAD segment that executes or supplies runtime data, while the entry point and symbols remain unchanged. Only then use it for direct SRAM execution.

## Download And Run Through ICEman

Prefer an already-running, matching ICEman instance. Verify its exact command line, listener, and absence of another GDB client:

```powershell
Get-CimInstance Win32_Process -Filter "Name='ICEman.exe'" |
  Select-Object ProcessId,CommandLine

Get-NetTCPConnection -State Listen |
  Where-Object LocalPort -in 9900,9901,9902
```

After explicit SRAM/run authorization, announce the write ranges and use the temporary normalized image:

```powershell
& "$toolBin\riscv32-elf-gdb.exe" -q -nx -batch '<temp>\image-sram-debug.adx' `
  -ex 'set pagination off' `
  -ex 'set confirm off' `
  -ex 'target extended-remote localhost:9902' `
  -ex 'load' `
  -ex 'set $pc = <elf-entry>' `
  -ex 'info registers pc' `
  -ex 'x/4i $pc' `
  -ex 'detach'
```

The download passes only when:

- GDB exits zero;
- `load` reports the expected section addresses and transfer size;
- PC equals the ELF entry;
- instructions at PC match the ELF disassembly;
- detach succeeds so the target resumes.

Do not add reset commands merely because an IDE launch sequence normally contains them. Use reset only when the target requires it and the user authorized that state change.

## Diagnose Execution Before Blaming UART

When expected output is absent, briefly attach GDB, inspect, and detach so the target resumes:

```gdb
info registers pc ra sp gp mstatus mcause mepc mtval
x/8i $pc-8
bt
```

Interpret the evidence before changing another variable:

- PC in an exception path, a low unmapped address, or `mcause=2`: recheck loaded bytes, LMA/VMA, entry, and disassembly.
- PC in early initialization or a polling loop: inspect that boundary before changing UART candidates.
- Backtrace reaches `main -> shell_task -> ... -> uart_getc(UART_BASE)`: firmware and UART initialization are alive; missing input/output now points to host COM mapping, cabling, or the RX/TX path.

An AICE dual-channel FTDI B interface is only a UART candidate. It may be reserved for the pre-JTAG CPU-release SPI path or not wired to the SoC console. Confirm a host COM mapping with a complete harmless shell round trip, such as command echo/response followed by the next prompt. A successful host-side write with no returned device bytes is not confirmation.

When shared access is needed, hand only the following facts to `serial-debug`: candidate COM ports, source-confirmed baud/framing, expected line ending, harmless probe command, and expected prompt. That skill owns bridge startup, human attachment, logs, retries, and candidate-port round-trip testing. The AICE workflow continues to own GDB and CPU-state interpretation.

## Completion

Report:

- ICEman endpoint and GDB exit status;
- original and temporary debug image paths;
- entry point, loaded ranges, and transfer size;
- relevant PC, exception, and backtrace evidence;
- whether UART verification was requested and, if so, the confirmed COM round trip;
- confirmation that external Flash and persistent configuration were untouched.

SRAM execution is complete when the loaded instructions match the ELF and the target reaches the expected runtime state. UART success is required only when it is part of the user's requested acceptance check.

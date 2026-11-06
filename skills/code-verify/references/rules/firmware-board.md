# Firmware / On-Board Validation Rules (code-verify bundled scenario ruleset)

This ruleset extends the generic baseline (`rules/generic.md`) with
firmware/on-board concerns: device state, protocol response parsing, hardware
timing and resource handling. Select it for repositories whose target
validation runs against real hardware via `.code-verify/config.json` →
`"review_rules": "firmware-board"`. A target repository can override or
extend these rules in its own `CLAUDE.md` (rules in CLAUDE.md win when they
conflict) — keep this file generic, project-specific rules belong to the
project.

Review the changed code ONLY against these rules. Do not flag generic code
quality issues. Every flagged issue must cite the changed file, the line, and
the rule.

## R1. Wrong PASS/FAIL verdicts

- Test verdicts computed from anything other than the actual observed device
  response (e.g. hardcoded PASS, PASS when an exception path is swallowed,
  PASS decided before the response arrives).
- PASS/FAIL derived from return codes of unrelated steps.
- FAIL conditions that can never trigger (dead assertions, unreachable
  branches, inverted conditions).
- Result variables overwritten before the verdict is recorded.

## R2. Missing or wrong assertions

- A test path that exercises the feature but asserts nothing.
- Assertions comparing against values that are always true (e.g. `assert
  response is not None` where any garbage response is not None).
- Expected values copied from the actual output instead of the spec.
- Assertions placed after cleanup or after the state being asserted is gone.

## R3. False PASS / False FAIL

- Retries that mask real failures until a pass happens (retry-until-pass
  without recording the failures).
- Timeout handled as success (e.g. `except TimeoutError: result = PASS`).
- Filtering or ignoring error frames/responses before the verdict.
- Tests whose PASS depends on leftover state from a previous test (order
  dependence that turns an independent FAIL into PASS).

## R4. Wrong timeout and retry logic

- Timeouts absent on blocking I/O (serial read, socket, subprocess, device
  wait).
- Retry loops without a bounded count, or retrying non-idempotent operations
  (reset, write to device) in a way that changes device state.
- Timeout values that exceed the test framework's own budget or hide
  firmware hangs.
- Sleeping fixed durations instead of waiting on the actual condition.

## R5. Device state pollution

- Test modifies persistent device state (registers, NVM, calibration,
  network config) without restoring it.
- Setup missing for state a previous test may have changed.
- Teardown missing or not guaranteed on failure paths (no try/finally, no
  fixture teardown, early return before release).
- Global/shared device handles reused across tests without reset.

## R6. Wrong protocol response parsing

- Parsing that accepts any response as valid (no length/checksum/echo/ID
  check).
- Byte order, encoding, or offset mismatches against the protocol spec.
- Error/status fields read but not checked, or checked with wrong constants.
- Partial reads treated as complete responses.

## R7. Setup / Teardown problems

- Setup steps performed in the wrong order for the hardware's requirements
  (power before enumerate, configure before open, etc.).
- Setup failure leaves the device in a partially configured state and the
  test continues.
- Teardown assumes setup completed even when setup failed.

## R8. Hardware resource release

- Serial ports, sockets, JTAG/debugger sessions, file locks, or child
  processes acquired but not closed on all paths.
- Resources closed in the wrong order (port closed before the reader thread
  stopped).
- Resources leaked inside retry loops.

## R9. Timing and synchronization

- Race conditions between device output and test reads (no synchronization
  on "device ready" signals).
- Shared state accessed from multiple threads/callbacks without locking.
- Assuming an operation completed because the command returned, when the
  device completes it asynchronously.

## R10. Verification logic vs test requirements

- The test verifies something other than what the requirement/change
  description says (when the requirement is visible in the change context).
- Assertions weaker than the requirement (checks "no crash" when the
  requirement specifies a response value).

## Output discipline for this agent

- Flag an issue only when the violating code path is visible in the changed
  code.
- If an issue depends on device state, hardware timing, serial ordering, or
  the physical environment and cannot be confirmed by reading the code, do
  not flag it as a finding — report it as a RISK with reason
  (device-state | timing | hardware-dependency | environment) and a concrete
  `what_to_check_on_target` note.
- Never propose or attempt to modify the code under review.

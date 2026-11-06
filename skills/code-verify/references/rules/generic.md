# Generic Validation Review Rules (code-verify Stage 1, default ruleset)

These rules extend the official Anthropic code review with validation-testing
concerns that apply to ANY repository: how test/validation code can produce
wrong PASS/FAIL verdicts or damage test credibility, independent of what the
target is (a test suite, a simulator, a device farm, a CI pipeline). They are
injected into the "project validation rules" reviewer agent (agent 5) when
the repository does not select another rules file.

Select rules via `.code-verify/config.json` → `"review_rules"`: a bundled
name (`generic`, `firmware-board`), or a repo-relative/absolute path to your
own rules file. A repository can also override or extend rules in its own
`CLAUDE.md` (rules in CLAUDE.md win when they conflict) — keep this file
generic, project-specific rules belong to the project.

Review the changed code ONLY against these rules. Do not flag generic code
quality issues. Every flagged issue must cite the changed file, the line, and
the rule.

## G1. Wrong PASS/FAIL verdicts

- Test verdicts computed from anything other than the actual observed
  response (e.g. hardcoded PASS, PASS when an exception path is swallowed,
  PASS decided before the response arrives).
- PASS/FAIL derived from return codes of unrelated steps.
- FAIL conditions that can never trigger (dead assertions, unreachable
  branches, inverted conditions).
- Result variables overwritten before the verdict is recorded.

## G2. Missing or wrong assertions

- A test path that exercises the feature but asserts nothing.
- Assertions comparing against values that are always true (e.g. `assert
  response is not None` where any garbage response is not None).
- Expected values copied from the actual output instead of the spec.
- Assertions placed after cleanup or after the state being asserted is gone.

## G3. False PASS / False FAIL

- Retries that mask real failures until a pass happens (retry-until-pass
  without recording the failures).
- Timeout handled as success (e.g. `except TimeoutError: result = PASS`).
- Filtering or ignoring error outputs/responses before the verdict.
- Tests whose PASS depends on leftover state from a previous test (order
  dependence that turns an independent FAIL into PASS).

## G4. Wrong timeout and retry logic

- Timeouts absent on blocking I/O (sockets, subprocesses, queues, device
  waits).
- Retry loops without a bounded count, or retrying non-idempotent operations
  in a way that changes persistent state.
- Timeout values that exceed the test framework's own budget or hide real
  hangs.
- Sleeping fixed durations instead of waiting on the actual condition.

## G5. State pollution

- A test modifies persistent state (databases, files, caches, configuration,
  device registers, NVM) without restoring it.
- Setup missing for state a previous test may have changed.
- Teardown missing or not guaranteed on failure paths (no try/finally, no
  fixture teardown, early return before release).
- Global/shared handles or sessions reused across tests without reset.

## G6. Unvalidated external responses

- Parsing that accepts any response as valid (no structure/status/ID check).
- Encoding, byte-order, or offset mismatches against the interface spec.
- Error/status fields read but not checked, or checked with wrong constants.
- Partial reads treated as complete responses.

## G7. Setup / Teardown problems

- Setup steps performed in the wrong order for the target's requirements.
- Setup failure leaves the target in a partially configured state and the
  test continues.
- Teardown assumes setup completed even when setup failed.

## G8. Resource release

- Connections, ports, debugger/debug sessions, file locks, or child
  processes acquired but not closed on all paths.
- Resources closed in the wrong order (consumer closed before producer
  stopped).
- Resources leaked inside retry loops.

## G9. Timing and synchronization

- Race conditions between the target's output and the test's reads (no
  synchronization on "ready" signals).
- Shared state accessed from multiple threads/callbacks without locking.
- Assuming an operation completed because the command returned, when the
  target completes it asynchronously.

## G10. Verification logic vs test requirements

- The test verifies something other than what the requirement/change
  description says (when the requirement is visible in the change context).
- Assertions weaker than the requirement (checks "no crash" when the
  requirement specifies a response value).

## Output discipline for this agent

- Flag an issue only when the violating code path is visible in the changed
  code.
- If an issue depends on runtime state, timing, ordering, or the execution
  environment and cannot be confirmed by reading the code, do not flag it as
  a finding — report it as a RISK with the workflow's risk reason (e.g.
  environment | timing | external-state) and a concrete
  `what_to_check_on_target` note.
- Never propose or attempt to modify the code under review.

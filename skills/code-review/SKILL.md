---
name: code-review
description: Structured code review for diffs and PRs - correctness, edge cases, error handling, concurrency and resources, test coverage, style. Use when the user asks to review code, a diff, a commit, a pull request, or another agent's change, or as the closing pass after tdd/implement work.
---

# code-review

Structured review pass over a code change, tuned for embedded/C/Python codebases: the checklist targets the failure classes that matter in firmware and tool code (unchecked returns, unbounded buffers, race windows, silent truncation).

## When to use

- The user asks to review a diff, commit, PR, or uncommitted changes.
- A closing review is requested after `tdd` / `implement` finished work.
- Before merging — decide what must be fixed now vs. what becomes a ticket.

Read the whole diff first, then the surrounding code it touches. Never judge a hunk in isolation.

## Review checklist

Work through every category; skip nothing, but only check what the diff can actually affect.

### Correctness
- Does the change do what the commit message/task claims — and nothing extra?
- Integer issues (C): signed/unsigned mixing, overflow on narrow types (`uint8_t` accumulation), truncating division, shift count >= width.
- Integer issues (Python): no wraparound exists — add `& 0xFF` explicitly where a byte-width wrap is intended; `is` compared to literals; `==` vs identity on objects.
- Off-by-one on loops and range checks (`<` vs `<=`, `range(n)` vs `range(n + 1)`).
- Floating point used where fixed-point/integer arithmetic was intended (thresholds, accumulators, money, sample counts).
- Logic inverted or duplicated from a nearby branch that should have been unified.

### Boundary conditions
- Empty input: zero-length buffer, empty list/str/bytes, `None`/`NULL` handled before use.
- Maximum input: full buffer (truncate, wrap, or reject — which one?), string with no room for a terminator, `memcpy` length derived from wire-controlled data.
- Single-element and exactly-at-limit cases (the two classic off-by-one homes).
- C: bounds checked before the write, not after; `strlen` on non-terminated input; loop unrolled past `sizeof`.
- Python: indexing a possibly-short sequence without a guard; `dict[key]` where `.get(key, default)` is safer.

### Error handling
- C: every fallible call checked (`malloc`/`read`/`write`/HAL returns); error paths release what was already taken; errno captured before it is clobbered.
- Python: no bare `except:`; `except Exception` only at boundaries that can genuinely recover; nothing swallowed silently — at minimum log it.
- Partial failure: if step 3 of 5 fails, is the device/file/protocol state left consistent (half-written record, half-configured peripheral)?
- Error style consistent with the module (return codes vs exceptions — do not mix in one layer).

### Concurrency & resources
- Shared state protected: ISR vs main loop (C), threads vs asyncio (Python); a named owner for each lock; lock not held across blocking calls.
- C: `volatile`/atomics correct for ISR-shared flags and cross-thread counters.
- Every acquire has a release on all paths — early returns and exceptions included: RAII in C++, `with` in Python, matched `free`/`close` in C.
- Timeouts on anything that can block forever: I2C/SPI/UART transaction, socket read, `Queue.get()`.
- No busy-wait where an event/notify primitive exists; no blocking call inside an ISR or an async event loop.

### Test coverage
- New behavior has a test; a bug fix has a test that fails before the fix and passes after.
- At least one boundary case from this checklist is exercised (empty, max, error path).
- Tests assert outcomes, not implementation details; no test passes only because it mocks the thing under test.
- Hardware-dependent code either runs without the board (fake/mock transport) or is explicitly marked on-target only.

### Style
- Matches surrounding code: naming, brace/indent style, comment language, log/error message format.
- No dead code, commented-out blocks, or leftover debug `printf`s/`print`s that are not intentional logging.
- Public functions/types carry a doc comment: what they do and what happens on failure.
- Magic numbers replaced by named constants that carry the unit (`TIMEOUT_MS`, not `500`).

## Severity levels

| Level | Meaning | Action |
|---|---|---|
| blocker | Breaks a stated requirement, corrupts data, crashes, security/memory bug, or breaks build/tests. | Must fix before merge. |
| major | Wrong on a realistic input, resource leak, race, or missing test for new core behavior. | Fix before merge, or file a follow-up ticket with an owner. |
| minor | Style drift, unclear naming, missing doc comment, correct but suboptimal. | Fix now if trivial; otherwise note it. |
| nit | Preference-level polish (wording, ordering). | Author's choice; prefix with "nit:" or leave out. |

Report what is actually wrong, with evidence — file, line, and why. Do not pad the review with nits to look thorough.

## Output format

For each file that has findings:

```text
### path/to/file.c
- [blocker] L42: `memcpy(dst, src, len)` — `len` comes from the frame header and is never bounded
  by `sizeof(dst)`. Fix: reject frames larger than the buffer and clamp `len` before the copy.
- [major] L87: return value of `i2c_write()` ignored; a NACK leaves the sensor config half-applied.
  Fix: check the return and retry or abort with an error log.
- [nit] L12: `#define TMO 500` — rename to `TMO_MS` to carry the unit.
```

Close with a one-line verdict — **approve** / **approve with comments** (majors only, all ticketed) / **request changes** (any blocker or un-ticketed major) — plus a one-sentence overall assessment.

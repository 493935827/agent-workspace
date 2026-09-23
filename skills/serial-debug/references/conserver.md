# Conserver Workflow

Conserver is the shared-console layer for this skill.
It lets multiple users watch the same serial console at once, logs console traffic, and gives one user write access at a time.

## Why Use It

- Keep the human able to watch output continuously.
- Let the agent attach without stealing the line.
- Preserve a transcript for debugging and review.
- Switch write access deliberately instead of racing over the raw UART.

## Operating Model

- Start in spy/read-only mode when the agent only needs to observe.
- Request read-write only when the agent needs to send a command.
- If another user already has write access, expect the agent to fall back to spy mode.
- Use logging as the source of truth when the device output matters.

## Coordination Rules

- Announce before taking write access.
- Release write access when the agent is done typing.
- Do not send destructive commands unless the human explicitly asked for them.
- If the human is actively driving the console, prefer spy mode and narrate what the agent sees.

## Useful Status Checks

- Show connected consoles.
- Show current users.
- Show whether the console is up, down, or initializing.
- Check whether logs are being written.

## When To Escalate

- The console is already held by another writer.
- The target is booting, resetting, or producing noisy startup text.
- The prompt changes after mode switches.
- The output suggests the device is hung or the serial settings are wrong.

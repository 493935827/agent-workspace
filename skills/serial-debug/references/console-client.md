# Console Client

Use the `console` client to interact with Conserver.

## Common Forms

```bash
console -V
console -x
console -w
console -i
console -s <CONSOLE>
console -a <CONSOLE>
console -A <CONSOLE>
console -F <CONSOLE>
console -S <CONSOLE>
```

## Semantics To Remember

- `-s` requests read-only spy mode.
- `-a` requests two-way read-write access.
- `-w` reports who is attached and from where.
- `-i` reports console status in machine-parseable form.
- `-x` lists consoles and devices.
- `-A`, `-F`, and `-S` connect and then show recent console output.

## Practical Use

- Use `-s` first if the goal is only to observe.
- Use `-a` only when the agent must type into the console.
- Use `-A` or `-F` when you need immediate context after connecting to a noisy console.
- Use the status commands before and after a session to confirm attachment state.

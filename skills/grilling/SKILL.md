---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Before sending a round, inventory the known unresolved decisions across the design tree. Classify each as **ready** or **blocked**, naming the specific unanswered decision or pending fact that blocks it. Include every ready decision in this round. A topic being more detailed, less urgent, or intended for a later section is not a dependency.

Size the round by the frontier, not by a fixed question count or a preference for short replies. Use the permitted question interface that can present the complete frontier; if its per-call limit requires multiple batches and the environment permits them, submit all batches before waiting. If higher-priority interaction constraints prevent a complete round, state that limitation and keep the remaining ready questions pending rather than relabeling them as blocked.

End the round with a concise list of deferred branches and their actual prerequisites, or state that no known branches are deferred. Check that every known unresolved decision is either asked or explicitly blocked before handing control back. This is **all currently answerable questions at once**, not all possible future questions: answers may reveal new branches for the next round.

Each question should be formatted like so:

```
❓ **Q1** - **<question title>**: <question body, might be multiple paragraphs, including multiple choices>

➡️ <your recommended answer>
```

Each round the user answers reshapes the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it — don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. The _decisions_ are the user's — put each to them and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.

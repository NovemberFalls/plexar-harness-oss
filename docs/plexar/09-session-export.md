# `plexar-harness export` — session transcripts

`plexar-harness export <session-id>` prints one harness session as plain text. The Plexar Framework's `plexar slice <file>` reads this shape directly (agreed in `plexar-coord/SKILLS-VALUE-REVIEW.md`, Turn 3, item H3).

Source: `packages/bundle/plexar/cli/export.ts`, run under the harness's tsx loader by `plexar-harness.mjs`.

## Usage

```
plexar-harness export <session-id>            USER / ASSISTANT turns
plexar-harness export <session-id> --tools    also TOOL and COMMAND lines
plexar-harness export <session-id> > s.txt && plexar slice s.txt
```

The session is found by id under `$DSH_HOME/sessions/*/<session-id>/` (default `~/.dsh`), whatever folder it ran in. Session ids come from the CLI's `resume with:` line, `/sessions`, or `DSH_SESSION_ID` inside a harness shell command.

## Output

```
# plexar-export-1 session <session-id>

USER: <what the user typed>

ASSISTANT: <the model's answer text>
```

| Line | Source event | Included |
|---|---|---|
| `# plexar-export-1 session <id>` | — | Always the first line. Readers refuse an unknown version. |
| `USER: …` | `user/message` whose `source.kind` is `user` | Always |
| `ASSISTANT: …` | text blocks of `assistant/message` | Always, when the message has text |
| `TOOL: <name> <arguments JSON>` | `tool-call` blocks of `assistant/message` | `--tools` only |
| `COMMAND: /<name> <args>` | `command/run` (slash commands, including the CLI's automatic `/permission` switches) | `--tools` only |

Turns are separated by one blank line and appear in log order. Text the harness injects is excluded: runtime-context snapshots, the skills list, and loaded skill bodies are `user/message` events with a non-user source, or tool results. Thinking and tool results are not exported.

## Format ownership

The log is read through the harness's own `scanZstdFrames` and `scanLog` (`@deepseek-ai/dsh-session-persistence-jsonl`). Log format versions and migrations therefore stay the harness's concern; readers depend only on this text format and its `plexar-export-1` version line. A change to the lines above bumps the version.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Transcript printed |
| `1` | No log for that id, or the log could not be read (message on stderr) |
| `2` | No session id given |

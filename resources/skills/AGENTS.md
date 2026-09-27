# Skills folder conventions

Every skill lives directly under this `skills/` folder — `skills/<skill-name>/`.
Any grouping subfolder you see on disk right now (`AWS/`, `PYTHON-Suite/`,
`Frontend-skills/skills/`, etc.) is incidental, not part of the convention, and
may be flattened away at any time.

## Relative paths between skills

When a skill references a file that belongs to another skill (a `SKILL.md`, a
`references/*.md`, etc.), always write the relative path as if every skill
were a direct sibling under `skills/` — skip any grouping subfolder entirely,
even if the referenced skill currently sits inside one.

- Correct: `../deploy-scripts/references/split-repo-releases.md`
- Wrong: `../AWS/deploy-scripts/references/split-repo-releases.md`

This applies from any depth inside a skill (e.g. from a file under a skill's
own `references/`, add one more `../` to first reach that skill's own root,
then the same flat sibling path).

Prefer invoking another skill by name (`$skill-name`, `/skill-name`, or
whatever the host's skill-invocation syntax is) over reading a file path
directly. Use a literal relative path only as the documented fallback when
invocation isn't available.

## Rule ownership

State each normative rule once, in the skill and file that owns the topic.
Other skills link to it with one line (``See `../<skill>/<file>#<section>` ``)
instead of restating or paraphrasing it. When a rule moves, leave a pointer
behind, not a copy.

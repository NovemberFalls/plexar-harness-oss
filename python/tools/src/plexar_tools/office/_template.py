"""Document TEMPLATES — a shape a document can be asked to have (C78).

══ WHY THIS IS NOT A PARAGRAPH IN THE PROMPT ════════════════════════════════
Len's target SOP has numbered sections, a running header and footer, and two
heading tiers in two colours. **Every one of those was already expressible**
after C77 — and the model produced none of them, because expressible is not the
same as reached. `Block.colour` had been available since T72 for exactly the
"color-coded step headings" Len asked for, and the model went on emitting one
colour three times.

The standing measurement in this repo is that **prohibitions and instructions
are 0-for-9 across T81 and T87-T94**. Adding *"an SOP should have a Purpose and
a Scope"* to a tool description would be the tenth. What has worked every time
is changing the space of the possible: the chart block, the `=?` marker, the
callout, the tolerant artifact detector.

So a template is not advice. **It is a transformation that runs.** Ask for
`sop` and the numbering happens, the furniture appears and the second heading
tier exists, whether or not the model remembered to ask for any of them.

══ AND IT MUST NOT CONSTRAIN ═══════════════════════════════════════════════
Len, standing rule: *"we shouldnt constrain it."* So:

* **Templates are opt-in.** No template is the default and a spec that names
  none is transformed not at all -- byte-identical to what it produced before
  this module existed. That is asserted, not assumed.
* **Every default is overridable.** A template supplies what the model did NOT
  say. It never overwrites what it did say, in either direction: a model that
  set its own header keeps it, and a model that set `"header": {}` deliberately
  is not given one.
* **Nothing is refused.** A template the writer does not know is ignored and
  the document is still produced. A document that fails to exist because its
  shape was misspelled would be the worst possible trade.

══ THE NUMBERING IS THE ONE REAL TRANSFORMATION ════════════════════════════
`heading2` is the section tier and `heading3` the step tier -- which is exactly
the split C77e gave a second colour to, so the two features describe the same
structure and cannot disagree about it. An SOP's sections get `1.`, `2.`, `3.`
prepended; its steps do not.

**Skipped when the model already numbered them.** A heading reading
`"1. PURPOSE"` must not become `"1. 1. PURPOSE"`, and the check is on the
rendered TEXT rather than on a flag, because the model is the one producing
both spellings and it does not know which branch it took.
"""

from __future__ import annotations

import re
from typing import Any

#: A heading that already carries its own number. **Matched loosely on
#: purpose**: `1.`, `1)`, `Section 1 -`, `Paso 2:` all mean "the author
#: numbered this", and adding a second number to any of them is worse than
#: adding none. Over-matching here costs a missing number, which the model can
#: see and fix; under-matching produces `1. 1. PURPOSE`, which reads as a bug
#: in the product.
_NUMBERED = re.compile(r"^\s*(?:[A-Za-zÀ-ɏ]+\s+)?\d+\s*[.):–—-]")

#: Templates this package knows. **One, and it is the one that was measured.**
#: A `memo` and a `report` would each be a shape nobody has compared against a
#: real document, and an unmeasured template is a guess with a name on it --
#: which is how a product ends up looking like a form somebody forgot to fill
#: in (T51's own words about inventing three colours).
TEMPLATES: tuple[str, ...] = ("sop",)

#: What `sop` supplies when the spec is silent. Read as: the running furniture
#: of a controlled document, and a palette with two heading tiers.
_SOP: dict[str, Any] = {
    "header": {"right": "SOP"},
    "footer": {"pages": "Page {n} of {of}"},
    "style": {"heading": "#c2410c", "subheading": "#15803d",
              "rule_width": 1.4},
}


def name_of(value: object) -> str:
    """A model-authored template name, normalised. `""` means "none of them".

    **An unknown name is not an error**, here or anywhere downstream. See the
    module docstring: a document that fails because its shape was misspelled is
    the worst available outcome, and the model gets a plain document it can
    still describe truthfully.
    """
    key = str(value or "").strip().lower()
    return key if key in TEMPLATES else ""


def _numbered(text: str) -> bool:
    return bool(_NUMBERED.match(text or ""))


def apply(name: object, spec: dict) -> dict:
    """`spec` with the template's shape applied, or `spec` itself.

    **Returned by identity when no template was named**, so the default path
    allocates nothing and a document written before this module is unchanged.
    """
    key = name_of(name)
    if not key or not isinstance(spec, dict):
        return spec
    out = dict(spec)

    # ── THE DEFAULTS: SUPPLIED, NEVER IMPOSED ────────────────────────────────
    # `key in spec` rather than a truthiness test, deliberately. A model that
    # wrote `"header": {}` said something -- "no header" -- and a template that
    # read the empty dict as silence would overrule it. The distinction between
    # ABSENT and EMPTY is the same one this repo insists on everywhere else.
    for slot, value in _SOP.items():
        if slot in spec:
            if slot == "style" and isinstance(spec.get("style"), dict):
                # The one MERGE, because a palette is a set of independent
                # fields: a model naming only an accent should still get the
                # two heading tiers rather than losing them for having spoken.
                merged = dict(value)
                merged.update(spec["style"])
                out["style"] = merged
            continue
        out[slot] = dict(value)

    # ── THE TRANSFORMATION ───────────────────────────────────────────────────
    blocks = spec.get("blocks")
    if not isinstance(blocks, list):
        return out
    numbered: list[Any] = []
    section = 0
    for block in blocks:
        if not isinstance(block, dict):
            numbered.append(block)
            continue
        kind = str(block.get("type") or block.get("kind") or "").strip().lower()
        text = str(block.get("text") or "")
        if kind != "heading2" or not text.strip():
            numbered.append(block)
            continue
        section += 1
        if _numbered(text):
            # Counted but not rewritten: an author who numbered section 1
            # themselves and left 2 bare should get `2.`, not `1.`.
            numbered.append(block)
            continue
        numbered.append({**block, "text": f"{section}. {text}"})
    out["blocks"] = numbered
    return out

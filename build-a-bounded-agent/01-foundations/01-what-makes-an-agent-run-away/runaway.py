"""Watch an unbounded agent loop run away.

A scripted model keeps asking for the same search, which never finds what it
wants, and the loop keeps obliging. Nothing in the loop says "enough": the only
thing that stops it is SAFETY_NET, which exists so this demo ends.

    uv run python runaway.py

No model, no key, no network. Token counts are scripted to grow the way a real
conversation does (every step resends the whole history); cost uses Claude
Opus 5.5 list prices so the numbers mean something.
"""

from __future__ import annotations

from dataclasses import dataclass

SAFETY_NET = 25  # not a design: only here so the demo terminates
PRICE_IN, PRICE_OUT = 4.00, 20.00  # USD per million tokens, claude-opus-5-5


@dataclass
class Step:
    number: int
    tool: str
    arguments: str
    input_tokens: int
    output_tokens: int

    @property
    def cost(self) -> float:
        return (self.input_tokens * PRICE_IN + self.output_tokens * PRICE_OUT) / 1_000_000


def stuck_model(step: int) -> tuple[str, str, int, int]:
    """A model that is sure the answer is one more search away."""
    history = 1_800 + 420 * (step - 1)  # the prompt grows by each call and its result
    return "search_tickets", '{"query": "invoice export"}', history, 90


def search_tickets(arguments: str) -> str:
    return '{"tickets": [], "total": 0}'  # never finds anything


def run_unbounded() -> list[Step]:
    steps = []
    number = 0
    while True:  # the bug: nothing in here ever decides to stop
        number += 1
        if number > SAFETY_NET:
            break
        tool, arguments, tokens_in, tokens_out = stuck_model(number)
        search_tickets(arguments)
        steps.append(Step(number, tool, arguments, tokens_in, tokens_out))
    return steps


def main() -> None:
    steps = run_unbounded()
    total = 0.0
    for s in steps:
        total += s.cost
        if s.number in (1, 2, 3, 10, 25):
            print(
                f"step {s.number:>2}  {s.tool}({s.arguments})  in={s.input_tokens:>6,}  "
                f"out={s.output_tokens}  step=${s.cost:.4f}  total=${total:.4f}"
            )
    distinct = {(s.tool, s.arguments) for s in steps}
    print(
        f"\n{len(steps)} steps, {len(distinct)} distinct call, ${total:.4f} spent, nothing found."
    )
    print(f"Step 25 cost {steps[-1].cost / steps[0].cost:.1f}x step 1.")


if __name__ == "__main__":
    main()

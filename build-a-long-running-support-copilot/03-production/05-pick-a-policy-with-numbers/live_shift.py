"""Run one real shift with Claude under a policy, with a hard spend cap.
Needs ANTHROPIC_API_KEY; costs money (Haiku: about 2 cents per shift).

    uv run python live_shift.py trim --cap 0.50
"""

import argparse

import anyio
from copilot.grading import grade
from copilot.model import AnthropicModel
from copilot.shift import run_shift
from copilot.summariser import ClaudeSummariser


async def main(policy: str, model: str, cap: float) -> None:
    summariser = ClaudeSummariser() if policy.startswith("summary") else None
    r = await run_shift(AnthropicModel(model), policy=policy, summariser=summariser, max_usd=cap)
    u = r.usage
    hit = u.cache_read_tokens / u.prompt_tokens
    print(f"{policy} on {model}: {len(r.requests)} requests, ${r.usd:.4f}, cache hit {hit:.1%}")
    print(grade(r.tools))
    if r.stopped_at_cap:
        print(f"stopped at the ${cap:.2f} cap")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("policy", default="trim", nargs="?")
    p.add_argument("--model", default="claude-haiku-5-5")
    p.add_argument("--cap", type=float, default=0.50)
    a = p.parse_args()
    anyio.run(main, a.policy, a.model, a.cap)

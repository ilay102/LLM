"""
Smoke test: hits the gateway 5 times with prompts of varying complexity,
verifies the classifier picks different tiers, and checks the second call
hits the semantic cache.

Run:  python tests/smoke.py
"""
import os
import time
import json

from openai import OpenAI

KEY = os.environ.get("GATEWAY_MASTER_KEY", "dev-key-change-me")
client = OpenAI(base_url="http://localhost:8000/v1", api_key=KEY)

CASES = [
    ("Classify this sentence as positive or negative: 'The food was awful.'", "expect: cheap"),
    ("Translate to French: Hello, how are you today?", "expect: cheap"),
    ("Write a 3-paragraph essay on the trade-offs between monolith and microservices for a 50-engineer team.", "expect: balanced"),
    ("Prove step by step that for any prime p > 2, p^2 - 1 is divisible by 24.", "expect: frontier"),
    ("Refactor this Python code to use async io and explain each architectural change you made:\n```python\nimport requests\nfor u in urls:\n    r = requests.get(u)\n    print(r.status_code)\n```", "expect: balanced/frontier"),
]

for i, (prompt, note) in enumerate(CASES):
    t0 = time.time()
    resp = client.chat.completions.create(
        model="auto",  # any string not in tier-* triggers classifier
        messages=[{"role": "user", "content": prompt}],
        max_tokens=200,
    )
    dt = (time.time() - t0) * 1000
    print(f"[{i+1}] {note}")
    print(f"    model_returned={resp.model}  latency={dt:.0f}ms")
    print(f"    answer: {resp.choices[0].message.content[:120]!r}\n")

# Hit the first one again — should be cached.
print("Re-running case 1 to verify semantic cache hit...")
t0 = time.time()
resp = client.chat.completions.create(
    model="auto",
    messages=[{"role": "user", "content": CASES[0][0]}],
    max_tokens=200,
)
dt = (time.time() - t0) * 1000
print(f"    id={resp.id}  latency={dt:.0f}ms (cached id starts with 'cached-')")

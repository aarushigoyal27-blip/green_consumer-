import os, time, statistics
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")
client = OpenAI(base_url=os.getenv("LLM_BASE_URL"), api_key=os.getenv("LLM_API_KEY"))
p_in, p_out = float(os.getenv("PRICE_IN_PER_M", 0)), float(os.getenv("PRICE_OUT_PER_M", 0))

latencies, cost = [], 0.0
for i in range(5):
    t = time.perf_counter()
    r = client.chat.completions.create(
        model=os.getenv("LLM_MODEL"),
        messages=[{"role": "user", "content": "Explain a Green Home Score of 38/100 in two sentences."}],
        max_tokens=150,
    )
    latencies.append(time.perf_counter() - t)
    u = r.usage
    cost += u.prompt_tokens / 1e6 * p_in + u.completion_tokens / 1e6 * p_out
    if i == 0:
        print(r.choices[0].message.content, "\n")

print(f"p50 latency: {statistics.median(latencies):.2f}s  max: {max(latencies):.2f}s")
print(f"tokens/call ≈ {u.prompt_tokens} in / {u.completion_tokens} out")
print(f"cost for 5 calls: ${cost:.5f}  → per call ${cost/5:.6f}")
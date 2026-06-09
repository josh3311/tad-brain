import os, json, re
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()

client = OpenAI(
    api_key=os.getenv("KIMI_API_KEY", ""),
    base_url="https://api.moonshot.ai/v1",
)

# Test different prompt styles to find what Kimi K2 responds to
prompts = [
    # Style 1 — conversational
    "List 3 profitable AI business ideas for small businesses. For each give: name, problem it solves, and a score from 1-10 for demand and competition.",
    
    # Style 2 — direct JSON request  
    'Return a JSON array of 3 AI business opportunities. Each object must have: name, problem, demand (1-10), competition (1-10). Example: [{"name":"test","problem":"test","demand":8,"competition":7}]',
    
    # Style 3 — system + user split
    None,
]

for i, prompt in enumerate(prompts[:2], 1):
    print(f"\n=== Test {i} ===")
    try:
        resp = client.chat.completions.create(
            model="kimi-k2.6",
            messages=[
                {"role": "system", "content": "You are a market research assistant. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            temperature=1,
            max_tokens=500,
        )
        raw = resp.choices[0].message.content or ""
        print(f"Response ({len(raw)} chars): {raw[:300]}")
        
        # Try parse
        try:
            clean = re.sub(r"```json|```", "", raw).strip()
            # Find JSON array in response
            match = re.search(r'\[.*\]', clean, re.DOTALL)
            if match:
                data = json.loads(match.group())
                print(f"✓ Parsed: {len(data)} items")
            else:
                print("✗ No JSON array found")
        except Exception as e:
            print(f"✗ Parse error: {e}")
    except Exception as e:
        print(f"✗ API error: {e}")
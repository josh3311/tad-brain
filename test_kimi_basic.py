"""
TAD — Switch to Claude API
Run this to test Claude API is working then we update all agents.
"""
import os
import anthropic
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY", "")
print(f"API Key found: {bool(api_key)}")

client = anthropic.Anthropic(api_key=api_key)

# Test 1 — basic response
print("\nTest 1 — basic response...")
try:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": "Say hello in one sentence"}]
    )
    print(f"✓ Response: {msg.content[0].text}")
except Exception as e:
    print(f"✗ Failed: {e}")

# Test 2 — JSON response
print("\nTest 2 — JSON response...")
try:
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": 'Return a JSON array of 2 AI business opportunities. Each must have: name, problem, demand (1-10), competition (1-10). Example: [{"name":"test","problem":"test","demand":8,"competition":7}]'
        }]
    )
    print(f"✓ Response: {msg.content[0].text[:300]}")
except Exception as e:
    print(f"✗ Failed: {e}")

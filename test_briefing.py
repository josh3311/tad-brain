"""
TAD — Quick test: generate a morning briefing right now.
Run this from C:\\TAD\\ to verify scheduler + briefing pipeline work.

Usage:
    cd C:\\TAD
    .venv\\Scripts\\activate
    python test_briefing.py
"""
import json
from scheduler import build_morning_briefing

print("Generating morning briefing now...")
briefing = build_morning_briefing()
print("\n=== BRIEFING OUTPUT ===")
print(f"Date:      {briefing['date']} {briefing['time']}")
print(f"Night ran: {briefing['night_mode_ran']}")
print(f"Built:     {briefing['built_count']} items")
print(f"\nAction:    {briefing['action_today']}")
print(f"\nFull text:\n{briefing['full_text']}")
print("\n✓ Saved to memory/morning_briefing.json")
print("Restart tad_gui.py to see it in the popup.")
"""
List Gemini Models
===================
Run this anytime you get a "model not found" error.
It shows exactly which model names your API key can use right now.

USAGE:
  python list_gemini_models.py
"""

import urllib.request, json

# Paste the same key from sora_organizer_desktop.py
GEMINI_API_KEY = "AQ.Ab8RN6Jj5JK887rFGBT6pqy8ECjEO-P5KlFAkZk28NVjwG-tlg"

if "YOUR-GEMINI-KEY" in GEMINI_API_KEY:
    print("\n  Edit this file and paste your Gemini API key first.\n")
    input("Press Enter to exit...")
    exit()

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={GEMINI_API_KEY}"

try:
    with urllib.request.urlopen(url, timeout=15) as resp:
        data = json.loads(resp.read())

    print("\n" + "=" * 55)
    print("  Models available to your API key")
    print("=" * 55 + "\n")

    for model in data.get("models", []):
        name    = model.get("name", "").replace("models/", "")
        methods = model.get("supportedGenerationMethods", [])
        if "generateContent" in methods:
            print(f"  ✓  {name}")

    print("\n  Copy one of the names above into GEMINI_MODEL")
    print("  in sora_organizer_desktop.py\n")

except urllib.error.HTTPError as e:
    print(f"\n  HTTP Error {e.code}: {e.read().decode()[:300]}\n")
except Exception as e:
    print(f"\n  Error: {e}\n")

input("Press Enter to exit...")

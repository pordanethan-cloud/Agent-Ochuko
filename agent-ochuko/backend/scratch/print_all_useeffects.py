import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r"useEffect\(", text)]
for idx, pos in enumerate(matches):
    snippet = text[pos:pos+250]
    # Remove unicode characters or print safely
    clean_snippet = snippet.encode('ascii', 'ignore').decode('ascii')
    print(f"Match {idx+1} at index {pos}:\n{clean_snippet}\n" + "-"*40)

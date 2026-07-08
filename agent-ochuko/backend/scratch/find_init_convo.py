import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "activeconversationid" in line.lower() or "currentconvo" in line.lower() or "session" in line.lower() or "localstorage" in line.lower():
        if "useeffect" in line.lower() or "const [" in line.lower() or "setactive" in line.lower() or "parse" in line.lower():
            print(f"Line {i+1}: {line.strip()}")

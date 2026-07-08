with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "fetchconversations" in line.lower() and ("const" in line or "function" in line or "useeffect" in line):
        print(f"Line {i+1}: {line.strip()}")

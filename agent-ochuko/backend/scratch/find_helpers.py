with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "function isbinaryfile" in line.lower() or "const isbinaryfile" in line.lower() or "function isimage" in line.lower() or "const isimage" in line.lower():
        print(f"Line {i+1}: {line.strip()}")

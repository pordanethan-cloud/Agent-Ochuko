with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "useref(" in line.lower() or "useref<" in line.lower():
        print(f"Line {i+1}: {line.strip()}")

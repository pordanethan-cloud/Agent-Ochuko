with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "fetchconversations()" in line.lower():
        # print context
        print(f"Line {i+1}: {line.strip()}")
        for j in range(max(0, i-5), min(len(lines), i+6)):
            print(f"  {j+1}: {lines[j].strip()}")
        print("-" * 20)

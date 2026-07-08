with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "fetchconversations(" in line.lower() or "activeconversationid" in line.lower():
        if "useeffect" in line.lower() or "useeffect(() => {" in lines[i-1].lower() or "useeffect(() => {" in lines[i-2].lower():
            print(f"Line {i+1}: {line.strip()}")

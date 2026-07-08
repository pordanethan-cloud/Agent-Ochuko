with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "fetchmessages" in line.lower() or "/conversations/" in line.lower():
        if "id/files" not in line and "id/suspend" not in line and "id/activate" not in line:
            print(f"Line {i+1}: {line.strip()}")

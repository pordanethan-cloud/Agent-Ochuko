with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "imageurl" in line.lower() or "image_url" in line.lower():
        if "google.com/s2/favicons" not in line:
            print(f"Line {i+1}: {line.strip()}")

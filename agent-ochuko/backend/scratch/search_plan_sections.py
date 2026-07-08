import sys

# Ensure UTF-8 stdout encoding for printing unicode characters in Windows shell
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

with open("docs/IMPLEMENTATION_PLAN.md", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "image_gen" in line or "image generation" in line.lower() or "job" in line.lower():
        if "description" in line.lower() or "section" in line.lower() or "table" in line.lower() or "##" in line:
            print(f"Line {i+1}: {line.strip()}")

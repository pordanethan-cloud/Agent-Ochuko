with open("docs/IMPLEMENTATION_PLAN.md", "r", encoding="utf-8") as f:
    text = f.read()

print("image count:", text.lower().count("image"))
print("job count:", text.lower().count("job"))

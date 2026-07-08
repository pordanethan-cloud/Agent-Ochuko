with open("agent-ochuko/frontend/src/pages/Dashboard.tsx", "r", encoding="utf-8") as f:
    text = f.read()

print("isImage count:", text.count("isImage"))
print("isMarkdown count:", text.count("isMarkdown"))

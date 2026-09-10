p = r"C:\Users\T14 GEN 5\Documents\WORK AND PLAN\vergent-worktree\agent-ochuko\backend\app\core\skills.py"
raw = open(p, encoding="utf-8-sig").read()
open(p, "w", encoding="utf-8", newline="").write(raw)
print("BOM stripped, chars:", len(raw))

import sys
sys.path.insert(0, r"C:\Users\T14 GEN 5\Documents\WORK AND PLAN\vergent-worktree\agent-ochuko\backend")
import app.core.skills as s
print("import OK; ULTRA_IDENTITY words:", len(s.ULTRA_IDENTITY.split()))
print("est tokens:", int(len(s.ULTRA_IDENTITY.split()) * 1.3))

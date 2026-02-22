import re

js = open("/app/static/app.js").read()
lines = js.split("\n")

# Find top-level statements (brace depth 0)
depth = 0
top_level = []
for i, line in enumerate(lines):
    stripped = line.strip()
    if not stripped or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        continue
    
    old_depth = depth
    depth += line.count("{") - line.count("}")
    
    if old_depth == 0 and not stripped.startswith("function ") and not stripped.startswith("async function ") and stripped != "}":
        top_level.append((i+1, stripped[:120]))

print(f"Top-level statements: {len(top_level)}")
for ln, code in top_level:
    print(f"  L{ln}: {code}")

import os
from pathlib import Path

main_path = "v2/backend/app/main.py"
lines = Path(main_path).read_text(encoding="utf-8").splitlines()

templates_dir = Path("v2/backend/app/templates")
templates_dir.mkdir(exist_ok=True)

# Format: (name, start_line (0-indexed), end_line, filename)
blocks = [
    ("output", 486, 1876, "output.html"),
    ("stage", 1887, 2026, "stage.html"),
    ("follow", 2053, 2186, "follow.html")
]

new_lines = []
skip_until = -1

for i, line in enumerate(lines):
    if i < skip_until:
        continue
    
    matched = False
    for name, start, end, filename in blocks:
        if i == start:
            content = "\n".join(lines[start+1:end])
            (templates_dir / filename).write_text(content, encoding="utf-8")
            
            new_lines.append(f'    html_content = (Path(__file__).parent / "templates" / "{filename}").read_text(encoding="utf-8")')
            if name == "follow":
                new_lines[-1] += '.replace("__OPTIONS__", options)'
                
            skip_until = end + 1
            matched = True
            break
            
    if not matched:
        new_lines.append(line)

has_path = any("from pathlib import Path" in l for l in new_lines)
if not has_path:
    for i, l in enumerate(new_lines):
        if l.startswith("from fastapi import"):
            new_lines.insert(i + 1, "from pathlib import Path")
            break

Path(main_path).write_text("\n".join(new_lines) + "\n", encoding="utf-8")
print("Extraction terminée avec succès.")

import re
import os

MAIN_PY = "/Users/gafardgnane/Downloads/VersePro/v2/backend/app/main.py"

with open(MAIN_PY, "r") as f:
    content = f.read()

# 1. Output page
output_pattern = re.compile(r'async def get_output_page\(\):.*?html_content\s*=\s*"""(.*?)"""\s*return HTMLResponse\(content=html_content\)', re.DOTALL)
output_replacement = """async def get_output_page():
    \"\"\"
    Écran d'affichage universel v2 — « Lecture vivante ».
    Le texte est rendu mot à mot : pendant que le prédicateur lit, chaque mot
    s'illumine au rythme de sa voix (événements reading_progress). La traduction
    simultanée IA s'affiche en sous-titre live. Thèmes : presentation (défaut),
    broadcast (lower-third), confidence, dual. Params : ?theme= ?bg= ?scale= ?subtitle=off
    \"\"\"
    with open("templates/output.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)"""

content = re.sub(r'async def get_output_page\(\):.*?return HTMLResponse\(content=html_content\)', output_replacement, content, flags=re.DOTALL)

# 2. Stage page
stage_pattern = re.compile(r'async def get_stage_display\(\):.*?html_content\s*=\s*"""(.*?)"""\s*return HTMLResponse\(content=html_content\)', re.DOTALL)
stage_replacement = """async def get_stage_display():
    \"\"\"
    Moniteur prédicateur (« stage display ») : verset courant avec lecture
    vivante, horloge, et verset SUIVANT pré-affiché. Ce que ProPresenter vend
    en option, en mieux : l'écran sait où en est la lecture.
    \"\"\"
    with open("templates/stage.html", "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)"""

content = re.sub(r'async def get_stage_display\(\):.*?return HTMLResponse\(content=html_content\)', stage_replacement, content, flags=re.DOTALL)


# 3. Follow page
follow_pattern = re.compile(r'async def get_follow_page\(\):.*?html_content\s*=\s*""".*?""".replace\("__OPTIONS__", options\)\s*return HTMLResponse\(content=html_content\)', re.DOTALL)
follow_replacement = """async def get_follow_page():
    \"\"\"
    Page « assemblée » : suit en direct les versets projetés, sur mobile,
    dans la traduction choisie par chacun. Publique et en lecture seule.
    \"\"\"
    versions = []
    if verse_parser and verse_parser.bible_loader:
        versions = list(verse_parser.bible_loader.versions.keys())
    options = "".join(f'<option value="{v}">{v}</option>' for v in versions) or '<option value="">Par défaut</option>'

    with open("templates/follow.html", "r", encoding="utf-8") as f:
        html_content = f.read().replace("__OPTIONS__", options)
    return HTMLResponse(content=html_content)"""

content = re.sub(r'async def get_follow_page\(\):.*?return HTMLResponse\(content=html_content\)', follow_replacement, content, flags=re.DOTALL)

with open(MAIN_PY, "w") as f:
    f.write(content)

print("Done replacing.")

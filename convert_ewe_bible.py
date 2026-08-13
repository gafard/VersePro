import zipfile
import re
import json
import os
from pathlib import Path

USFM_MAP = [
    ("GEN", "Genèse", "Gen"), ("EXO", "Exode", "Ex"), ("LEV", "Lévitique", "Lév"),
    ("NUM", "Nombres", "Nb"), ("DEU", "Deutéronome", "Dt"), ("JOS", "Josué", "Jos"),
    ("JDG", "Juges", "Jg"), ("RUT", "Ruth", "Rt"), ("1SA", "1 Samuel", "1 S"),
    ("2SA", "2 Samuel", "2 S"), ("1KI", "1 Rois", "1 R"), ("2KI", "2 Rois", "2 R"),
    ("1CH", "1 Chroniques", "1 Ch"), ("2CH", "2 Chroniques", "2 Ch"), ("EZR", "Esdras", "Esd"),
    ("NEH", "Néhémie", "Neh"), ("EST", "Esther", "Est"), ("JOB", "Job", "Job"),
    ("PSA", "Psaumes", "Ps"), ("PRO", "Proverbes", "Pr"), ("ECC", "Ecclésiaste", "Ec"),
    ("SNG", "Cantique des cantiques", "Ct"), ("ISA", "Ésaïe", "És"), ("JER", "Jérémie", "Jér"),
    ("LAM", "Lamentations", "Lm"), ("EZK", "Ézéchiel", "Éz"), ("DAN", "Daniel", "Dn"),
    ("HOS", "Osée", "Os"), ("JOL", "Joël", "Jl"), ("AMO", "Amos", "Am"),
    ("OBA", "Abdias", "Abd"), ("JON", "Jonas", "Jon"), ("MIC", "Michée", "Mi"),
    ("NAM", "Nahum", "Na"), ("HAB", "Habacuc", "Hab"), ("ZEP", "Sophonie", "So"),
    ("HAG", "Aggée", "Ag"), ("ZEC", "Zacharie", "Za"), ("MAL", "Malachie", "Ml"),
    ("MAT", "Matthieu", "Mt"), ("MRK", "Marc", "Mc"), ("LUK", "Luc", "Lc"),
    ("JHN", "Jean", "Jn"), ("ACT", "Actes", "Ac"), ("ROM", "Romains", "Rm"),
    ("1CO", "1 Corinthiens", "1 Co"), ("2CO", "2 Corinthiens", "2 Co"), ("GAL", "Galates", "Ga"),
    ("EPH", "Éphésiens", "Éph"), ("PHP", "Philippiens", "Ph"), ("COL", "Colossiens", "Col"),
    ("1TH", "1 Thessaloniciens", "1 Th"), ("2TH", "2 Thessaloniciens", "2 Th"),
    ("1TI", "1 Timothée", "1 Tm"), ("2TI", "2 Timothée", "2 Tm"), ("TIT", "Tite", "Tt"),
    ("PHM", "Philémon", "Phm"), ("HEB", "Hébreux", "He"), ("JAS", "Jacques", "Jc"),
    ("1PE", "1 Pierre", "1 P"), ("2PE", "2 Pierre", "2 P"), ("1JN", "1 Jean", "1 Jn"),
    ("2JN", "2 Jean", "2 Jn"), ("3JN", "3 Jean", "3 Jn"), ("JUD", "Jude", "Jude"),
    ("REV", "Apocalypse", "Ap")
]

zip_path = "/tmp/ewe_sample_usfm.zip"
zf = zipfile.ZipFile(zip_path, 'r')
namelist = zf.namelist()

def clean_usfm_text(text: str) -> str:
    # Remove footnotes \f ...\f*
    text = re.sub(r'\\f\s+.*?(?:\\f\*|$)', '', text, flags=re.DOTALL)
    # Remove cross-refs \x ...\x*
    text = re.sub(r'\\x\s+.*?(?:\\x\*|$)', '', text, flags=re.DOTALL)
    # Remove character formatting tags like \wj, \+wj, \add, \+add, \nd, \qs, \q1, \q2, \p, etc.
    text = re.sub(r'\\[a-z0-9\+\*]+', '', text)
    # Normalize whitespaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text

books_result = []
total_verses = 0

for code, fr_name, abbr in USFM_MAP:
    match_file = next((f for f in namelist if code in f.upper() and f.endswith(".usfm")), None)
    if not match_file:
        print(f"Warning: file for {code} ({fr_name}) not found!")
        continue
    
    content = zf.read(match_file).decode('utf-8')
    lines = content.splitlines()
    
    chapters = []
    current_chapter_num = None
    current_verses = []
    current_verse_num = None
    current_verse_text_parts = []
    
    for line in lines:
        line_s = line.strip()
        if not line_s:
            continue
        
        # Check for chapter \c <num>
        c_match = re.match(r'^\\c\s+(\d+)', line_s)
        if c_match:
            if current_verse_num is not None:
                cleaned = clean_usfm_text(" ".join(current_verse_text_parts))
                if cleaned:
                    current_verses.append({"verse": current_verse_num, "text": cleaned})
                    total_verses += 1
                current_verse_num = None
                current_verse_text_parts = []
            if current_chapter_num is not None and current_verses:
                chapters.append({"chapter": current_chapter_num, "verses": current_verses})
            current_chapter_num = int(c_match.group(1))
            current_verses = []
            continue
            
        # Check for verse \v <num>
        v_match = re.match(r'^\\v\s+(\d+)(?:-\d+)?\s*(.*)', line_s)
        if v_match:
            if current_verse_num is not None:
                cleaned = clean_usfm_text(" ".join(current_verse_text_parts))
                if cleaned:
                    current_verses.append({"verse": current_verse_num, "text": cleaned})
                    total_verses += 1
            current_verse_num = int(v_match.group(1))
            current_verse_text_parts = []
            rem = v_match.group(2)
            if rem:
                current_verse_text_parts.append(rem)
            continue
            
        # Text continuation inside a verse
        if current_verse_num is not None:
            if line_s.startswith('\\'):
                tag_content = re.sub(r'^\\[a-z0-9\+]+\s*', '', line_s)
                if tag_content:
                    current_verse_text_parts.append(tag_content)
            else:
                current_verse_text_parts.append(line_s)
                
    if current_verse_num is not None:
        cleaned = clean_usfm_text(" ".join(current_verse_text_parts))
        if cleaned:
            current_verses.append({"verse": current_verse_num, "text": cleaned})
            total_verses += 1
    if current_chapter_num is not None and current_verses:
        chapters.append({"chapter": current_chapter_num, "verses": current_verses})
    
    books_result.append({
        "name": fr_name,
        "abbreviation": abbr,
        "chapters": chapters
    })

bible_json = {
    "version": "EWE",
    "language": "ee",
    "title": "Biblica® Agbenya La™ (Éwé)",
    "books": books_result
}

# Destinations:
# 1. In Simulation folder next to the PDF
dest_sim = Path("/Users/gafardgnane/Downloads/Simulation/EWE.json")
with open(dest_sim, "w", encoding="utf-8") as f:
    json.dump(bible_json, f, ensure_ascii=False, indent=2)

# 2. In VersePro bibles_cache folder
cache_dir = Path("/Users/gafardgnane/Downloads/VersePro/v2/backend/data/bibles_cache")
cache_dir.mkdir(parents=True, exist_ok=True)
dest_cache = cache_dir / "EWE.json"
with open(dest_cache, "w", encoding="utf-8") as f:
    json.dump(bible_json, f, ensure_ascii=False, indent=2)

print(f"✅ Conversion réussie !")
print(f"Livres: {len(books_result)}")
print(f"Versets totaux: {total_verses}")
print(f"Fichier créé dans Simulation: {dest_sim} ({os.path.getsize(dest_sim)/1024/1024:.2f} Mo)")
print(f"Fichier créé dans VersePro: {dest_cache} ({os.path.getsize(dest_cache)/1024/1024:.2f} Mo)")

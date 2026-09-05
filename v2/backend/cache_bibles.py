import os
import json
import re
import yaml

def cache_bibles():
    src_dir = "/Users/gafardgnane/Downloads/g/Selah_app/selah_app/assets/bibles"
    dest_dir = "v2/backend/data/bibles_cache"
    os.makedirs(dest_dir, exist_ok=True)
    
    if not os.path.exists(src_dir):
        print(f"Directory {src_dir} does not exist.")
        return
        
    for filename in os.listdir(src_dir):
        if not filename.endswith(".json") or "lsg1910" in filename:
            continue
            
        src_path = os.path.join(src_dir, filename)
        dest_path = os.path.join(dest_dir, filename)
        
        if os.path.exists(dest_path):
            print(f"Already cached: {filename}")
            continue
            
        print(f"Caching {filename}...")
        try:
            with open(src_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
                
            # Attempt regex + standard json loads first
            try:
                quoted = re.sub(r'(?<={|,)\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'"\1":', content)
                data = json.loads(quoted)
            except Exception:
                # Fallback to PyYAML spaced method (extremely robust for JS objects)
                print(f"  Fallback to PyYAML for {filename}")
                spaced = re.sub(r':(?!\s)', ': ', content)
                data = yaml.safe_load(spaced)
                
            with open(dest_path, 'w', encoding='utf-8') as f_out:
                json.dump(data, f_out, ensure_ascii=False, indent=2)
            print(f"✓ Successfully cached {filename}")
        except Exception as e:
            print(f"✗ Error caching {filename}: {e}")

if __name__ == "__main__":
    cache_bibles()

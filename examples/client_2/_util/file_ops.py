import os
import json
import tempfile
from typing import Tuple

def prepare_output_dir(cf_repo_prefix : str) -> str:
    try:
        cf_repo = tempfile.mkdtemp(prefix = cf_repo_prefix)
    
    except Exception as e:
        print(f"Exception in prepare_output_dir function: {e}")
        cf_repo = ""
    
    finally:
        return cf_repo

def write_json(json_value, json_file_name):
    try:
        temp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "_temp")
        os.makedirs(temp_dir, exist_ok=True)
        json_path = os.path.join(temp_dir, json_file_name)
        
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_value, f, indent=4)

    except Exception as e:
        print(f"Exception in write_json function: {e}")

    finally:
        pass

def gather_repo_files(neo_repo: str, max_chars=2000) -> Tuple[list, dict]:
    try:
        filenames = []
        snippets = {}
        exclude_dirs = [".git", "node_modules", "__pycache__", ".venv", ".idea"]
        exclude_files = [".jar"]

        for root, dirs, files in os.walk(neo_repo):
            dirs[:] = [d for d in dirs if d not in exclude_dirs]
            for f in files:
                if any(f.endswith(ext) for ext in exclude_files):
                    continue

                rel_path = os.path.relpath(os.path.join(root, f), neo_repo)
                filenames.append(rel_path)
                try:
                    snippets[rel_path] = read_text_file(rel_path = os.path.join(root, f))[:max_chars]
                    
                except Exception as e:
                    print(f"Exception reading file {rel_path}: {e}")
                    snippets[rel_path] = "<unreadable>"
                    
        json_value = {"filenames": filenames, "snippets": snippets}
        write_json(json_value = json_value, json_file_name = "gather_repo_files.json")
        
    except Exception as e:
        print(f"Exception in gather_repo_files function: {e}")
        filenames = []
        snippets = {}    
    
    finally:
        return filenames, snippets

def read_text_file(rel_path: str) -> str:
    try:
        with open(rel_path, "r", encoding="utf-8", errors="ignore") as f:
            read_file = f.read()
        
    except Exception as e:
        print(f"Exception in read_text_file function: {e}")
        read_file = ""
    
    finally:
        return read_file

def write_text_file(dest_path: str, content: str) -> None:
    try:
        with open(dest_path, "w", encoding="utf-8", errors="ignore") as f:
            f.write(content)
            
    except Exception as e:
        print(f"Exception in write_text_file function: {e}")
        
    finally:
        pass
    
def write_zip_file(dest_path: str, content: str) -> None:
    try:
        with open(dest_path, "wb") as f:
            f.write(content)
            
    except Exception as e:
        print(f"Exception in write_zip_file function: {e}")
        
    finally:
        pass

def write_txt(txt_value, txt_file_name):
    try:
        base_dir = os.getcwd()
        temp_dir = os.path.join(base_dir, "_temp")
        os.makedirs(temp_dir, exist_ok=True)
        txt_path = os.path.join(temp_dir, txt_file_name)
        
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(txt_value)

    except Exception as e:
        print(f"Exception in write_txt function: {e}")

    finally:
        pass
import os
import sys
import json
import shutil
from pathlib import Path

def main():
    print("=== MinerU Diagnostic and Fix Tool ===")
    
    # 1. Detect User Home and Paths
    user_home = Path.home()
    print(f"[INFO] User Home: {user_home}")
    
    # Check for .cache/modelscope
    base_model_dir = user_home / ".cache" / "modelscope" / "hub" / "models" / "OpenDataLab"
    
    # Check for the valid '1.0' directory
    valid_cache = base_model_dir / "PDF-Extract-Kit-1.0"
    # Check for the problematic '1___0' directory
    bad_cache = base_model_dir / "PDF-Extract-Kit-1___0"
    
    modelscope_cache = None

    if bad_cache.exists():
        print(f"[WARN] Found potentially problematic model directory: {bad_cache}")
        if valid_cache.exists():
            print(f"[INFO] A valid '1.0' directory also exists: {valid_cache}")
            print(f"[ACTION] You should DELETE the '{bad_cache.name}' directory to avoid conflicts.")
            print(f"Run: Remove-Item -Path \"{bad_cache}\" -Recurse -Force")
            # We will prefer the valid one for config
            modelscope_cache = valid_cache
        else:
            print(f"[WARN] No standard '1.0' directory found. Using '{bad_cache.name}' but it might be corrupted.")
            modelscope_cache = bad_cache
    elif valid_cache.exists():
        modelscope_cache = valid_cache
    
    if modelscope_cache:
        print(f"[INFO] Selected Model Path: {modelscope_cache}")
        
        # Check if 'models' subdir exists (common in ModelScope downloads)
        if (modelscope_cache / "models").exists():
            print(f"[INFO] Found 'models' subdirectory. Using it as model root.")
            modelscope_cache = modelscope_cache / "models"

        print("[OK] Model directory exists.")
        # Check for required subdirectories
        required_subs = ["MFD", "MFR", "Layout", "Table"]
        missing_subs = []
        for sub in required_subs:
            # Case insensitive check
            found = False
            for p in modelscope_cache.iterdir():
                if p.name.lower() == sub.lower() and p.is_dir():
                    found = True
                    break
            if not found:
                missing_subs.append(sub)
        
        if missing_subs:
            print(f"[ERROR] Incomplete model directory! Missing components: {missing_subs}")
            print("[ACTION] You must re-download the models. Delete the directory and run MinerU download command again.")
            print(f"Directory to delete: {modelscope_cache.parent if modelscope_cache.name == 'models' else modelscope_cache}")
            # If Layout is missing, MinerU will definitely fail
            if "Layout" in missing_subs:
                print("[CRITICAL] 'Layout' model is missing. This causes the 'ModelWrapper' error.")
    else:
        print("[WARN] Model directory not found. Please run MinerU to download models first.")
        # Try to find if it is in a different location or partially downloaded
        if base_model_dir.exists():
            print(f"[INFO] Found parent directory: {base_model_dir}")
            print(f"[INFO] Contents: {[p.name for p in base_model_dir.iterdir()]}")

    # 2. Check/Create magic-pdf.json
    config_path = user_home / "magic-pdf.json"
    print(f"[INFO] Checking Config Path: {config_path}")
    
    # Define standard config
    config_data = {
        "bucket_info": {
            "bucket-name": "bucket-name-1",
            "access-key": "access-key-1",
            "secret-key": "secret-key-1",
            "endpoint": "endpoint-1"
        },
        "models-dir": str(modelscope_cache).replace("\\", "/"),
        "device-mode": "cuda",
        "layout-config": {
            "model": "doclayout_yolo"
        },
        "formula-config": {
            "model": "unimernet_small",
            "enable": True
        },
        "table-config": {
            "model": "rapid_table",
            "enable": True
        }
    }
    
    if config_path.exists():
        print("[INFO] Found existing magic-pdf.json.")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                existing_config = json.load(f)
            print("[INFO] Existing config loaded.")
            # Verify models-dir
            if existing_config.get("models-dir") != config_data["models-dir"]:
                print(f"[WARN] Existing models-dir '{existing_config.get('models-dir')}' does not match expected '{config_data['models-dir']}'.")
                print("[ACTION] Updating magic-pdf.json with correct model path...")
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config_data, f, indent=4, ensure_ascii=False)
                print("[OK] Updated magic-pdf.json.")
            else:
                print("[OK] magic-pdf.json points to the correct model directory.")
        except Exception as e:
            print(f"[ERROR] Failed to read magic-pdf.json: {e}")
            print("[ACTION] Recreating magic-pdf.json...")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=4, ensure_ascii=False)
            print("[OK] Recreated magic-pdf.json.")
    else:
        print("[INFO] magic-pdf.json not found.")
        print("[ACTION] Creating magic-pdf.json...")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        print("[OK] Created magic-pdf.json.")

    # 3. Check for conflicting or corrupted files in Model Directory
    # The error 'untagged enum ModelWrapper' suggests a bad config file inside the model dir
    if modelscope_cache.exists():
        print("[INFO] Checking for potential corrupted config files in model directory...")
        # Check for any huge json files or weird files
        for p in modelscope_cache.rglob("*.json"):
            try:
                size = p.stat().st_size
                if size > 10 * 1024 * 1024: # 10MB
                    print(f"[WARN] Found large JSON file: {p} ({size/1024/1024:.2f} MB). This might be causing issues.")
            except Exception:
                pass

    # 4. Check Pydantic Version
    try:
        import pydantic
        print(f"[INFO] Pydantic version: {pydantic.VERSION}")
    except ImportError:
        print("[WARN] Pydantic not found.")
    except AttributeError:
        print(f"[INFO] Pydantic version: {pydantic.__version__}")

    print("\n=== Diagnosis Complete ===")
    print("If the error persists, try the following:")
    print("1. Delete the model directory: " + str(modelscope_cache))
    print("2. Re-run MinerU to download models again.")
    print("3. Ensure you are using the latest version of MinerU.")

if __name__ == "__main__":
    main()
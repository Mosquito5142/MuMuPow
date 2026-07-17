import json
import os
import sys

# Configure stdout/stderr to use UTF-8 to prevent encoding crashes in Windows console
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def multiply_delays(steps, multiplier=1.5):
    modified_count = 0
    for step in steps:
        if "delay" in step:
            try:
                old_val = float(step["delay"])
                new_val = round(old_val * multiplier, 3)
                # Keep the same type if it was an int, else float
                if isinstance(step["delay"], int) and new_val.is_integer():
                    step["delay"] = int(new_val)
                elif isinstance(step["delay"], str):
                    step["delay"] = str(new_val)
                else:
                    step["delay"] = new_val
                modified_count += 1
            except (ValueError, TypeError):
                pass
        
        # Recursively handle sub-steps in if_image blocks
        if "then" in step and isinstance(step["then"], list):
            modified_count += multiply_delays(step["then"], multiplier)
        if "else" in step and isinstance(step["else"], list):
            modified_count += multiply_delays(step["else"], multiplier)
            
    return modified_count

def main():
    file_path = r"e:\MuMuPow\dist\macros\กำลังทำรับของ.json"
    if not os.path.exists(file_path):
        print(f"Error: File {file_path} does not exist.")
        return
        
    print(f"Reading macro file...")
    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    if "steps" not in data:
        print("Error: 'steps' key not found in the macro JSON.")
        return
        
    count = multiply_delays(data["steps"], 1.5)
    print(f"Multiplied delays by 1.5 in {count} steps.")
    
    # Save the modified file back
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("Saved modified macro file successfully.")

if __name__ == "__main__":
    main()

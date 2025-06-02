#!/usr/bin/env python3
"""
CPU Fallback Configuration Script

This script shows how to modify vertex_gpu_service.py to force CPU-only mode
as a temporary workaround while waiting for GPU quota approval.
"""

import sys
import re
import os
from datetime import datetime

def backup_file(file_path):
    """Create a backup of the original file"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{file_path}.backup_{timestamp}"
    
    try:
        with open(file_path, 'r') as src, open(backup_path, 'w') as dst:
            dst.write(src.read())
        print(f"✅ Created backup at: {backup_path}")
        return True
    except Exception as e:
        print(f"❌ Error creating backup: {str(e)}")
        return False

def modify_gpu_service_file(file_path):
    """Modify vertex_gpu_service.py to force CPU-only mode"""
    try:
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Pattern 1: Modify the generate_fallback_configs method to only use CPU
        cpu_only_pattern = re.compile(
            r'(def _generate_fallback_configs.*?)(return fallback_configs)',
            re.DOTALL
        )
        
        if cpu_only_pattern.search(content):
            modified_content = cpu_only_pattern.sub(
                r'\1# TEMPORARY: Force CPU-only mode while waiting for GPU quota\n'
                r'        fallback_configs = [config for config in fallback_configs if "gpu_type" not in config or config.get("gpu_type") == "CPU"]\n'
                r'        logger.info("⚠️ USING CPU-ONLY MODE: GPU quotas not available")\n'
                r'        \2',
                content
            )
            
            # Pattern 2: Add a comment at the top of the file
            header_comment = (
                "# TEMPORARY CPU-ONLY MODE\n"
                "# This file has been modified to force CPU-only mode as a workaround\n"
                "# while waiting for GPU quota approval. Remove this modification\n"
                "# once GPU quotas are approved.\n"
                "# Modified: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "\n\n"
            )
            
            modified_content = header_comment + modified_content
            
            # Write the modified content back
            with open(file_path, 'w') as f:
                f.write(modified_content)
                
            print("✅ Successfully modified file to force CPU-only mode")
            print("⚠️ Note: CPU-only mode will be significantly slower")
            print("🔄 Once GPU quotas are approved, restore from the backup")
            return True
        else:
            print("❌ Could not find the pattern to modify in the file")
            return False
            
    except Exception as e:
        print(f"❌ Error modifying file: {str(e)}")
        return False

def main():
    """Main function"""
    file_path = "vertex_gpu_service.py"
    
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return 1
        
    print(f"🔍 Found file: {file_path}")
    
    # Confirm with user
    confirm = input("⚠️ This will modify your code to force CPU-only mode. Proceed? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled")
        return 0
        
    # Create backup
    if not backup_file(file_path):
        print("Aborting due to backup failure")
        return 1
        
    # Modify the file
    if modify_gpu_service_file(file_path):
        print("\n✅ Modification complete! You can now generate videos using CPU-only mode.")
        print("🔧 To apply changes, redeploy your application")
        return 0
    else:
        print("\n❌ Modification failed. Please restore from the backup")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 
#!/usr/bin/env python3
"""Helper script to list and view saved transcript files."""
import os
import glob

def list_transcripts():
    """List all transcript files in the current directory."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    transcript_files = glob.glob(os.path.join(script_dir, "transcript_*.txt"))
    
    if not transcript_files:
        print("📭 No transcript files found in:", script_dir)
        return
    
    # Sort by modification time (newest first)
    transcript_files.sort(key=os.path.getmtime, reverse=True)
    
    print(f"📁 Found {len(transcript_files)} transcript file(s) in:")
    print(f"   {script_dir}\n")
    
    for i, filepath in enumerate(transcript_files, 1):
        filename = os.path.basename(filepath)
        size = os.path.getsize(filepath)
        mtime = os.path.getmtime(filepath)
        import time
        from datetime import datetime
        mod_time = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"{i}. {filename}")
        print(f"   Size: {size} bytes | Modified: {mod_time}")
        print(f"   Path: {filepath}\n")
    
    # Ask if user wants to view the latest one
    if transcript_files:
        latest = transcript_files[0]
        print(f"📄 Latest transcript: {os.path.basename(latest)}")
        print(f"\nTo view it, run: cat {latest}")
        print(f"Or open it in your editor.")

if __name__ == "__main__":
    list_transcripts()


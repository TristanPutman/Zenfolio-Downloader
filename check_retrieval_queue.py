#!/usr/bin/env python3
"""Check the contents of the Zenfolio retrieval queue."""

import json
from pathlib import Path
from datetime import datetime

def check_retrieval_queue():
    """Check and display the contents of the retrieval queue."""
    queue_file = Path("zenfolio_retrieval_queue.json")
    
    print(f"Checking for retrieval queue file: {queue_file}")
    print(f"File exists: {queue_file.exists()}")
    
    if queue_file.exists():
        try:
            with open(queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            print(f"\nRetrieval queue contains {len(data)} items:")
            print("=" * 80)
            
            for i, item in enumerate(data, 1):
                print(f"\n{i}. Photo ID: {item.get('photo_id')}")
                print(f"   File: {item.get('file_name')}")
                print(f"   Gallery: {item.get('gallery_title')}")
                print(f"   Added: {item.get('added_at')}")
                print(f"   Attempts: {item.get('attempt_count')}")
                print(f"   Error: {item.get('error_message')}")
                print(f"   Local path: {item.get('local_path')}")
                
            # Check for the specific photo from the user's log
            target_photo_id = 2708273748930399452
            target_file = "IMG_8491.JPG"
            
            found_item = None
            for item in data:
                if item.get('photo_id') == target_photo_id or item.get('file_name') == target_file:
                    found_item = item
                    break
            
            print("\n" + "=" * 80)
            if found_item:
                print(f"✅ FOUND the specific item from the log:")
                print(f"   Photo ID: {found_item.get('photo_id')}")
                print(f"   File: {found_item.get('file_name')}")
                print(f"   Added to queue: {found_item.get('added_at')}")
            else:
                print(f"❌ Did NOT find the specific item:")
                print(f"   Looking for Photo ID: {target_photo_id}")
                print(f"   Looking for File: {target_file}")
                
        except Exception as e:
            print(f"Error reading retrieval queue: {e}")
    else:
        print("\n❌ No retrieval queue file found.")
        print("This could mean:")
        print("1. No items have been added to the retrieval queue yet")
        print("2. There was an error creating the queue file")
        print("3. The queue file is in a different location")

if __name__ == "__main__":
    check_retrieval_queue()
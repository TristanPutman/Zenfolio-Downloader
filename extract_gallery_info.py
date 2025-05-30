#!/usr/bin/env python3
"""
Extract actual gallery information from user's Zenfolio account for debugging examples.
This script will get real gallery IDs, folder IDs, and photo IDs to update the debug guide.
"""

import asyncio
import json
from pathlib import Path
from typing import Dict, List, Any

from config.settings import get_settings
from logs.logger import setup_logging, get_logger
from api.zenfolio_client import ZenfolioClient
from api.models import InformationLevel

logger = get_logger(__name__)


async def extract_gallery_info():
    """Extract real gallery information from the user's account."""
    
    settings = get_settings()
    settings.log_level = "INFO"
    setup_logging(settings)
    
    print("🔍 Extracting Gallery Information for Debug Examples")
    print("=" * 60)
    
    async with ZenfolioClient(settings) as client:
        try:
            # Authenticate
            print("🔐 Authenticating...")
            auth_success = await client.authenticate(settings.zenfolio_username, settings.zenfolio_password)
            
            if not auth_success:
                print("❌ Authentication failed")
                return
            
            print("✅ Authentication successful")
            
            # Load user profile
            print("👤 Loading user profile...")
            user_profile = await client.load_private_profile()
            print(f"✅ User: {user_profile.login_name}")
            
            # Load gallery hierarchy
            print("📁 Loading gallery hierarchy...")
            root_group = await client.load_group_hierarchy(user_profile.login_name, force_refresh=False)
            print("✅ Gallery hierarchy loaded")
            
            # Extract gallery information
            gallery_info = {
                "user": {
                    "login_name": user_profile.login_name,
                    "display_name": user_profile.display_name,
                    "id": user_profile.id
                },
                "folders": [],
                "galleries": [],
                "sample_photos": []
            }
            
            # Collect folder and gallery information
            await collect_structure_info(root_group, gallery_info, "", max_galleries=5)
            
            # Get sample photos from first few galleries
            await collect_sample_photos(client, gallery_info, max_photos_per_gallery=3)
            
            # Save to file
            output_file = Path("gallery_info_extracted.json")
            with open(output_file, 'w') as f:
                json.dump(gallery_info, f, indent=2, default=str)
            
            print(f"\n📄 Gallery information saved to: {output_file}")
            
            # Display summary
            print_summary(gallery_info)
            
            return gallery_info
            
        except Exception as e:
            print(f"❌ Error extracting gallery info: {e}")
            logger.exception("Gallery info extraction failed")
            return None


async def collect_structure_info(group, gallery_info: Dict, path: str, max_galleries: int = 5):
    """Recursively collect folder and gallery structure information."""
    
    # Add folder info if not root
    if group.title and group.title != "Root":
        folder_path = f"{path}/{group.title}" if path else group.title
        gallery_info["folders"].append({
            "id": group.id,
            "title": group.title,
            "path": folder_path,
            "subgroup_count": len(group.subgroups),
            "gallery_count": len(group.galleries)
        })
        path = folder_path
    
    # Add gallery info (limit to max_galleries to avoid too much data)
    for gallery in group.galleries[:max_galleries]:
        gallery_path = f"{path}/{gallery.title}" if path else gallery.title
        gallery_info["galleries"].append({
            "id": gallery.id,
            "title": gallery.title,
            "path": gallery_path,
            "type": gallery.type.value,
            "photo_count": gallery.photo_count,
            "created_on": gallery.created_on,
            "last_updated": gallery.last_updated
        })
        
        # Stop if we have enough galleries
        if len(gallery_info["galleries"]) >= max_galleries:
            break
    
    # Recursively process subgroups
    for subgroup in group.subgroups:
        await collect_structure_info(subgroup, gallery_info, path, max_galleries)
        if len(gallery_info["galleries"]) >= max_galleries:
            break


async def collect_sample_photos(client: ZenfolioClient, gallery_info: Dict, max_photos_per_gallery: int = 3):
    """Collect sample photo information from galleries."""
    
    print("🖼️  Collecting sample photo information...")
    
    for gallery in gallery_info["galleries"][:3]:  # Only check first 3 galleries
        try:
            print(f"   Loading photos from: {gallery['title']}")
            full_gallery = await client.load_photo_set(
                gallery["id"], 
                InformationLevel.LEVEL2, 
                include_photos=True
            )
            
            for photo in full_gallery.photos[:max_photos_per_gallery]:
                gallery_info["sample_photos"].append({
                    "id": photo.id,
                    "title": photo.title,
                    "file_name": photo.file_name,
                    "gallery_id": gallery["id"],
                    "gallery_title": gallery["title"],
                    "size": photo.size,
                    "is_video": photo.is_video,
                    "mime_type": photo.mime_type,
                    "is_downloadable": photo.is_downloadable,
                    "download_url": photo.download_url,
                    "width": photo.width,
                    "height": photo.height
                })
                
        except Exception as e:
            print(f"   ⚠️  Failed to load photos from {gallery['title']}: {e}")
            # Continue with other galleries


def print_summary(gallery_info: Dict):
    """Print a summary of extracted information."""
    
    print("\n📊 EXTRACTED INFORMATION SUMMARY")
    print("=" * 50)
    
    print(f"User: {gallery_info['user']['login_name']} (ID: {gallery_info['user']['id']})")
    print(f"Folders found: {len(gallery_info['folders'])}")
    print(f"Galleries found: {len(gallery_info['galleries'])}")
    print(f"Sample photos: {len(gallery_info['sample_photos'])}")
    
    if gallery_info['folders']:
        print(f"\n📁 Sample Folders:")
        for folder in gallery_info['folders'][:3]:
            print(f"   • {folder['title']} (ID: {folder['id']}) - {folder['gallery_count']} galleries")
    
    if gallery_info['galleries']:
        print(f"\n📸 Sample Galleries:")
        for gallery in gallery_info['galleries'][:3]:
            print(f"   • {gallery['title']} (ID: {gallery['id']}) - {gallery['photo_count']} photos")
    
    if gallery_info['sample_photos']:
        print(f"\n🖼️  Sample Photos:")
        for photo in gallery_info['sample_photos'][:5]:
            print(f"   • {photo['file_name']} (ID: {photo['id']}) from {photo['gallery_title']}")


if __name__ == '__main__':
    asyncio.run(extract_gallery_info())
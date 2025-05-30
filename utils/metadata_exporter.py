"""Metadata export utilities for complete hierarchical structure verification."""

import json
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from api.models import Group, PhotoSet, Photo, User
from config.settings import Settings
from logs.logger import get_logger

logger = get_logger(__name__)


class MetadataExporter:
    """Exports complete metadata for verification and backup purposes."""
    
    def __init__(self, settings: Settings):
        """Initialize metadata exporter.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
    
    def export_complete_structure(
        self,
        user: User,
        root_group: Group,
        output_dir: Path,
        export_format: str = "json"
    ) -> Path:
        """Export complete hierarchical structure with all metadata.
        
        Args:
            user: User information
            root_group: Root group containing all galleries
            output_dir: Output directory for metadata files
            export_format: Export format ('json', 'csv', or 'both')
            
        Returns:
            Path to the main metadata file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        metadata_dir = output_dir / "metadata" / timestamp
        metadata_dir.mkdir(parents=True, exist_ok=True)
        
        # Collect complete structure
        structure_data = self._collect_complete_structure(user, root_group)
        
        # Export in requested format(s)
        main_file = None
        
        if export_format in ["json", "both"]:
            main_file = self._export_json(structure_data, metadata_dir)
            
        if export_format in ["csv", "both"]:
            self._export_csv(structure_data, metadata_dir)
        
        # Export summary statistics
        self._export_summary(structure_data, metadata_dir)
        
        logger.info(f"Metadata exported to: {metadata_dir}")
        return main_file or metadata_dir / "structure.json"
    
    def _collect_complete_structure(self, user: User, root_group: Group) -> Dict[str, Any]:
        """Collect complete hierarchical structure with all metadata.
        
        Args:
            user: User information
            root_group: Root group
            
        Returns:
            Complete structure data
        """
        structure = {
            "export_info": {
                "timestamp": datetime.now().isoformat(),
                "zenfolio_user": user.login_name,
                "user_display_name": user.display_name,
                "total_galleries": user.gallery_count,
                "total_photos": user.photo_count,
                "export_version": "1.0"
            },
            "user_metadata": self._serialize_user(user),
            "hierarchy": self._collect_group_hierarchy(root_group),
            "statistics": self._calculate_statistics(root_group)
        }
        
        return structure
    
    def _serialize_user(self, user: User) -> Dict[str, Any]:
        """Serialize user information.
        
        Args:
            user: User object
            
        Returns:
            Serialized user data
        """
        return {
            "id": user.id,
            "login_name": user.login_name,
            "display_name": user.display_name,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "primary_email": user.primary_email,
            "bio": user.bio,
            "views": user.views,
            "gallery_count": user.gallery_count,
            "collection_count": user.collection_count,
            "photo_count": user.photo_count,
            "created_on": user.created_on.isoformat() if user.created_on else None,
            "last_updated": user.last_updated.isoformat() if user.last_updated else None
        }
    
    def _collect_group_hierarchy(self, group: Group, path: str = "") -> Dict[str, Any]:
        """Recursively collect group hierarchy with all metadata.
        
        Args:
            group: Group to process
            path: Current path in hierarchy
            
        Returns:
            Group hierarchy data
        """
        current_path = f"{path}/{group.title}" if path else group.title
        
        group_data = {
            "id": group.id,
            "title": group.title,
            "caption": group.caption,
            "path": current_path,
            "created_on": group.created_on.isoformat(),
            "last_updated": group.last_updated.isoformat() if group.last_updated else None,
            "access_descriptor": group.access_descriptor,
            "galleries": [],
            "subgroups": []
        }
        
        # Process galleries in this group
        for gallery in group.galleries:
            gallery_data = self._serialize_gallery(gallery, current_path)
            group_data["galleries"].append(gallery_data)
        
        # Process subgroups recursively
        for subgroup in group.subgroups:
            subgroup_data = self._collect_group_hierarchy(subgroup, current_path)
            group_data["subgroups"].append(subgroup_data)
        
        return group_data
    
    def _serialize_gallery(self, gallery: PhotoSet, parent_path: str) -> Dict[str, Any]:
        """Serialize gallery with all metadata and photos.
        
        Args:
            gallery: Gallery to serialize
            parent_path: Parent path in hierarchy
            
        Returns:
            Serialized gallery data
        """
        gallery_path = f"{parent_path}/{gallery.title}"
        
        gallery_data = {
            "id": gallery.id,
            "title": gallery.title,
            "caption": gallery.caption,
            "type": gallery.type.value,
            "path": gallery_path,
            "created_on": gallery.created_on.isoformat(),
            "last_updated": gallery.last_updated.isoformat() if gallery.last_updated else None,
            "photo_count": gallery.photo_count,
            "access_descriptor": gallery.access_descriptor,
            "photos": []
        }
        
        # Serialize all photos
        for photo in gallery.photos:
            photo_data = self._serialize_photo(photo, gallery_path)
            gallery_data["photos"].append(photo_data)
        
        return gallery_data
    
    def _serialize_photo(self, photo: Photo, gallery_path: str) -> Dict[str, Any]:
        """Serialize photo with all metadata.
        
        Args:
            photo: Photo to serialize
            gallery_path: Gallery path
            
        Returns:
            Serialized photo data
        """
        return {
            "id": photo.id,
            "title": photo.title,
            "file_name": photo.file_name,
            "gallery_path": gallery_path,
            "uploaded_on": photo.uploaded_on.isoformat(),
            "taken_on": photo.taken_on.isoformat() if photo.taken_on else None,
            "width": photo.width,
            "height": photo.height,
            "size": photo.size,
            "is_video": photo.is_video,
            "mime_type": photo.mime_type,
            "original_url": photo.original_url,
            "video_url": photo.video_url,
            "download_url": photo.download_url,
            "sequence": photo.sequence,
            "duration": photo.duration,
            "is_downloadable": photo.is_downloadable,
            "access_descriptor": photo.access_descriptor
        }
    
    def _calculate_statistics(self, root_group: Group) -> Dict[str, Any]:
        """Calculate comprehensive statistics for the hierarchy.
        
        Args:
            root_group: Root group
            
        Returns:
            Statistics data
        """
        stats = {
            "total_groups": 0,
            "total_galleries": 0,
            "total_photos": 0,
            "total_videos": 0,
            "total_size_bytes": 0,
            "downloadable_files": 0,
            "non_downloadable_files": 0,
            "galleries_by_type": {"Gallery": 0, "Collection": 0},
            "file_types": {},
            "size_distribution": {
                "under_1mb": 0,
                "1mb_to_10mb": 0,
                "10mb_to_100mb": 0,
                "over_100mb": 0
            }
        }
        
        self._collect_statistics_recursive(root_group, stats)
        return stats
    
    def _collect_statistics_recursive(self, group: Group, stats: Dict[str, Any]) -> None:
        """Recursively collect statistics from group hierarchy.
        
        Args:
            group: Group to process
            stats: Statistics dictionary to update
        """
        stats["total_groups"] += 1
        
        # Process galleries
        for gallery in group.galleries:
            stats["total_galleries"] += 1
            stats["galleries_by_type"][gallery.type.value] += 1
            
            # Process photos in gallery
            for photo in gallery.photos:
                stats["total_photos"] += 1
                
                if photo.is_video:
                    stats["total_videos"] += 1
                
                if photo.size > 0:
                    stats["total_size_bytes"] += photo.size
                    
                    # Size distribution
                    if photo.size < 1024 * 1024:  # < 1MB
                        stats["size_distribution"]["under_1mb"] += 1
                    elif photo.size < 10 * 1024 * 1024:  # < 10MB
                        stats["size_distribution"]["1mb_to_10mb"] += 1
                    elif photo.size < 100 * 1024 * 1024:  # < 100MB
                        stats["size_distribution"]["10mb_to_100mb"] += 1
                    else:  # >= 100MB
                        stats["size_distribution"]["over_100mb"] += 1
                
                if photo.is_downloadable:
                    stats["downloadable_files"] += 1
                else:
                    stats["non_downloadable_files"] += 1
                
                # File type statistics
                if photo.mime_type:
                    stats["file_types"][photo.mime_type] = stats["file_types"].get(photo.mime_type, 0) + 1
        
        # Process subgroups recursively
        for subgroup in group.subgroups:
            self._collect_statistics_recursive(subgroup, stats)
    
    def _export_json(self, structure_data: Dict[str, Any], output_dir: Path) -> Path:
        """Export structure data as JSON.
        
        Args:
            structure_data: Complete structure data
            output_dir: Output directory
            
        Returns:
            Path to JSON file
        """
        json_file = output_dir / "complete_structure.json"
        
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(structure_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"JSON metadata exported to: {json_file}")
        return json_file
    
    def _export_csv(self, structure_data: Dict[str, Any], output_dir: Path) -> None:
        """Export structure data as CSV files.
        
        Args:
            structure_data: Complete structure data
            output_dir: Output directory
        """
        # Export galleries CSV
        galleries_file = output_dir / "galleries.csv"
        self._export_galleries_csv(structure_data["hierarchy"], galleries_file)
        
        # Export photos CSV
        photos_file = output_dir / "photos.csv"
        self._export_photos_csv(structure_data["hierarchy"], photos_file)
        
        logger.info(f"CSV metadata exported to: {output_dir}")
    
    def _export_galleries_csv(self, hierarchy: Dict[str, Any], output_file: Path) -> None:
        """Export galleries to CSV.
        
        Args:
            hierarchy: Hierarchy data
            output_file: Output CSV file
        """
        galleries = []
        self._collect_galleries_for_csv(hierarchy, galleries)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'id', 'title', 'path', 'type', 'photo_count', 'created_on', 'last_updated'
            ])
            writer.writeheader()
            writer.writerows(galleries)
    
    def _export_photos_csv(self, hierarchy: Dict[str, Any], output_file: Path) -> None:
        """Export photos to CSV.
        
        Args:
            hierarchy: Hierarchy data
            output_file: Output CSV file
        """
        photos = []
        self._collect_photos_for_csv(hierarchy, photos)
        
        with open(output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'id', 'title', 'file_name', 'gallery_path', 'size', 'width', 'height',
                'is_video', 'mime_type', 'uploaded_on', 'taken_on', 'is_downloadable'
            ])
            writer.writeheader()
            writer.writerows(photos)
    
    def _collect_galleries_for_csv(self, group_data: Dict[str, Any], galleries: List[Dict[str, Any]]) -> None:
        """Recursively collect galleries for CSV export.
        
        Args:
            group_data: Group data
            galleries: List to append galleries to
        """
        for gallery in group_data.get("galleries", []):
            galleries.append({
                'id': gallery['id'],
                'title': gallery['title'],
                'path': gallery['path'],
                'type': gallery['type'],
                'photo_count': gallery['photo_count'],
                'created_on': gallery['created_on'],
                'last_updated': gallery['last_updated']
            })
        
        for subgroup in group_data.get("subgroups", []):
            self._collect_galleries_for_csv(subgroup, galleries)
    
    def _collect_photos_for_csv(self, group_data: Dict[str, Any], photos: List[Dict[str, Any]]) -> None:
        """Recursively collect photos for CSV export.
        
        Args:
            group_data: Group data
            photos: List to append photos to
        """
        for gallery in group_data.get("galleries", []):
            for photo in gallery.get("photos", []):
                photos.append({
                    'id': photo['id'],
                    'title': photo['title'],
                    'file_name': photo['file_name'],
                    'gallery_path': photo['gallery_path'],
                    'size': photo['size'],
                    'width': photo['width'],
                    'height': photo['height'],
                    'is_video': photo['is_video'],
                    'mime_type': photo['mime_type'],
                    'uploaded_on': photo['uploaded_on'],
                    'taken_on': photo['taken_on'],
                    'is_downloadable': photo['is_downloadable']
                })
        
        for subgroup in group_data.get("subgroups", []):
            self._collect_photos_for_csv(subgroup, photos)
    
    def _export_summary(self, structure_data: Dict[str, Any], output_dir: Path) -> None:
        """Export summary statistics.
        
        Args:
            structure_data: Complete structure data
            output_dir: Output directory
        """
        summary_file = output_dir / "summary.txt"
        stats = structure_data["statistics"]
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            f.write("ZENFOLIO METADATA EXPORT SUMMARY\n")
            f.write("=" * 50 + "\n\n")
            
            f.write(f"Export Date: {structure_data['export_info']['timestamp']}\n")
            f.write(f"Zenfolio User: {structure_data['export_info']['zenfolio_user']}\n")
            f.write(f"Display Name: {structure_data['export_info']['user_display_name']}\n\n")
            
            f.write("HIERARCHY STATISTICS:\n")
            f.write(f"  Total Groups: {stats['total_groups']:,}\n")
            f.write(f"  Total Galleries: {stats['total_galleries']:,}\n")
            f.write(f"  Total Photos: {stats['total_photos']:,}\n")
            f.write(f"  Total Videos: {stats['total_videos']:,}\n")
            f.write(f"  Total Size: {stats['total_size_bytes']:,} bytes ({stats['total_size_bytes'] / (1024**3):.2f} GB)\n\n")
            
            f.write("DOWNLOADABILITY:\n")
            f.write(f"  Downloadable Files: {stats['downloadable_files']:,}\n")
            f.write(f"  Non-downloadable Files: {stats['non_downloadable_files']:,}\n\n")
            
            f.write("GALLERY TYPES:\n")
            for gallery_type, count in stats['galleries_by_type'].items():
                f.write(f"  {gallery_type}: {count:,}\n")
            
            f.write("\nFILE SIZE DISTRIBUTION:\n")
            for size_range, count in stats['size_distribution'].items():
                f.write(f"  {size_range.replace('_', ' ').title()}: {count:,}\n")
            
            f.write("\nFILE TYPES:\n")
            for mime_type, count in sorted(stats['file_types'].items()):
                f.write(f"  {mime_type}: {count:,}\n")
        
        logger.info(f"Summary exported to: {summary_file}")
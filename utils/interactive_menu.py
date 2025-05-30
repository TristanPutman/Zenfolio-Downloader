"""Interactive menu system for Zenfolio downloader."""

import sys
from typing import List, Dict, Any, Optional, Tuple
from api.models import Group, PhotoSet


class InteractiveMenu:
    """Interactive command-line menu system."""
    
    def __init__(self):
        self.folders: List[Dict[str, Any]] = []
        self.current_selection: Optional[int] = None
        
    def display_main_menu(self, folders: List[Dict[str, Any]]) -> str:
        """Display the main menu and get user selection.
        
        Args:
            folders: List of folder/gallery information
            
        Returns:
            User's menu choice
        """
        self.folders = folders
        
        print("\n" + "="*60)
        print("🖼️  ZENFOLIO DOWNLOADER")
        print("="*60)
        print("\nAvailable folders/galleries:")
        print("-" * 40)
        
        # Display numbered list of folders
        for i, folder in enumerate(folders, 1):
            gallery_count = folder.get('gallery_count', 0)
            folder_type = "📁" if folder.get('type') == 'group' else "🖼️"
            print(f"{i:2d}. {folder_type} {folder['title']} ({gallery_count} galleries)")
        
        print("-" * 40)
        print("\nOptions:")
        print("  a - Download ALL folders")
        print("  v - Verify ALL folders")
        print("  r - Process retrieval queue")
        print("  s - Show retrieval queue status")
        print("  q - Quit")
        print("  1-{} - Select specific folder".format(len(folders)))
        
        while True:
            try:
                choice = input("\nEnter your choice: ").strip().lower()
                
                if choice in ['q', 'quit', 'exit']:
                    return 'quit'
                elif choice in ['a', 'all']:
                    return 'download_all'
                elif choice in ['v', 'verify']:
                    return 'verify_all'
                elif choice in ['r', 'retrieval']:
                    return 'process_retrieval_queue'
                elif choice in ['s', 'status']:
                    return 'show_retrieval_status'
                elif choice.isdigit():
                    num = int(choice)
                    if 1 <= num <= len(folders):
                        self.current_selection = num - 1
                        return 'select_folder'
                    else:
                        print(f"❌ Please enter a number between 1 and {len(folders)}")
                else:
                    print("❌ Invalid choice. Please try again.")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                return 'quit'
            except EOFError:
                print("\n\n👋 Goodbye!")
                return 'quit'
    
    def display_folder_menu(self) -> str:
        """Display the folder-specific menu and get user selection.
        
        Returns:
            User's menu choice
        """
        if self.current_selection is None:
            return 'back'
            
        folder = self.folders[self.current_selection]
        folder_type = "📁" if folder.get('type') == 'group' else "🖼️"
        
        print("\n" + "="*60)
        print(f"Selected: {folder_type} {folder['title']}")
        print("="*60)
        
        # Show folder details
        gallery_count = folder.get('gallery_count', 0)
        total_photos = folder.get('total_photos', 'Unknown')
        
        print(f"📊 Galleries: {gallery_count}")
        if total_photos != 'Unknown':
            print(f"📷 Total Photos: {total_photos}")
        
        print("\nOptions:")
        print("  d - Download this folder")
        print("  v - Verify this folder")
        print("  b - Back to main menu")
        print("  q - Quit")
        
        while True:
            try:
                choice = input("\nEnter your choice: ").strip().lower()
                
                if choice in ['q', 'quit', 'exit']:
                    return 'quit'
                elif choice in ['b', 'back']:
                    return 'back'
                elif choice in ['d', 'download']:
                    return 'download_folder'
                elif choice in ['v', 'verify']:
                    return 'verify_folder'
                else:
                    print("❌ Invalid choice. Please try again.")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Goodbye!")
                return 'quit'
            except EOFError:
                print("\n\n👋 Goodbye!")
                return 'quit'
    
    def get_selected_folder(self) -> Optional[Dict[str, Any]]:
        """Get the currently selected folder.
        
        Returns:
            Selected folder information or None
        """
        if self.current_selection is None:
            return None
        return self.folders[self.current_selection]
    
    def confirm_action(self, action: str, target: str) -> bool:
        """Confirm an action with the user.
        
        Args:
            action: Action to perform (e.g., "download", "verify")
            target: Target description (e.g., "ALL folders", "folder 'Photos'")
            
        Returns:
            True if user confirms, False otherwise
        """
        print(f"\n⚠️  You are about to {action} {target}")
        
        while True:
            try:
                choice = input("Are you sure? (y/n): ").strip().lower()
                
                if choice in ['y', 'yes']:
                    return True
                elif choice in ['n', 'no']:
                    return False
                else:
                    print("❌ Please enter 'y' for yes or 'n' for no.")
                    
            except KeyboardInterrupt:
                print("\n\n👋 Cancelled!")
                return False
            except EOFError:
                print("\n\n👋 Cancelled!")
                return False
    
    def show_completion_message(self, action: str, success: bool, details: str = "") -> None:
        """Show completion message.
        
        Args:
            action: Action that was performed
            success: Whether the action was successful
            details: Additional details to show
        """
        status = "✅ Completed" if success else "❌ Failed"
        print(f"\n{status}: {action}")
        
        if details:
            print(f"📋 {details}")
        
        input("\nPress Enter to continue...")


def prepare_folder_list(root_group: Group) -> List[Dict[str, Any]]:
    """Prepare a list of folders for the interactive menu.
    
    Args:
        root_group: Root group from Zenfolio
        
    Returns:
        List of folder information dictionaries
    """
    folders = []
    
    # Add top-level galleries
    if root_group.galleries:
        for gallery in root_group.galleries:
            folders.append({
                'title': gallery.title,
                'id': gallery.id,
                'type': 'gallery',
                'gallery_count': 1,
                'total_photos': gallery.photo_count,
                'object': gallery
            })
    
    # Add subgroups
    for subgroup in root_group.subgroups:
        gallery_count = len(subgroup.galleries)
        total_photos = sum(g.photo_count for g in subgroup.galleries)
        
        # Recursively count galleries in nested subgroups
        def count_nested_galleries(group: Group) -> Tuple[int, int]:
            count = len(group.galleries)
            photos = sum(g.photo_count for g in group.galleries)
            
            for sub in group.subgroups:
                sub_count, sub_photos = count_nested_galleries(sub)
                count += sub_count
                photos += sub_photos
                
            return count, photos
        
        nested_count, nested_photos = count_nested_galleries(subgroup)
        
        folders.append({
            'title': subgroup.title,
            'id': subgroup.id,
            'type': 'group',
            'gallery_count': nested_count,
            'total_photos': nested_photos,
            'object': subgroup
        })
    
    return folders
"""Main entry point for Zenfolio downloader application."""

import asyncio
import sys
from pathlib import Path
from typing import Optional
from datetime import datetime

import click
from config.settings import get_settings, Settings
from logs.logger import setup_logging, get_logger
from api.zenfolio_client import ZenfolioClient
from api.models import InformationLevel, Group
from download.download_manager import DownloadManager
from progress.checkpoint_manager import CheckpointManager
from progress.statistics import StatisticsTracker
from cache.cache_manager import CacheManager
from utils.metadata_exporter import MetadataExporter
from utils.interactive_menu import InteractiveMenu, prepare_folder_list
from utils.first_time_setup import should_run_setup, run_first_time_setup

logger = get_logger(__name__)


@click.command()
@click.option(
    '--output-dir', '-o',
    type=click.Path(path_type=Path),
    help='Output directory for downloads (overrides config)'
)
@click.option(
    '--concurrent-downloads', '-c',
    type=int,
    help='Number of concurrent downloads (overrides config)'
)
@click.option(
    '--resume/--no-resume',
    default=True,
    help='Resume interrupted downloads (default: enabled)'
)
@click.option(
    '--overwrite/--no-overwrite',
    default=False,
    help='Overwrite existing files (default: disabled)'
)
@click.option(
    '--galleries',
    type=str,
    help='Download specific galleries (regex pattern)'
)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    help='Logging level (overrides config)'
)
@click.option(
    '--dry-run',
    is_flag=True,
    help='Show what would be downloaded without downloading'
)
@click.option(
    '--stats-only',
    is_flag=True,
    help='Show download statistics without downloading'
)
@click.option(
    '--verify-integrity',
    is_flag=True,
    help='Verify integrity of existing files'
)
@click.option(
    '--verify',
    is_flag=True,
    help='Verify that a previous download completed successfully'
)
@click.option(
    '--clear-checkpoint',
    is_flag=True,
    help='Clear existing checkpoint and start fresh'
)
@click.option(
    '--list-galleries',
    is_flag=True,
    help='List all available galleries'
)
@click.option(
    '--list-details',
    is_flag=True,
    help='Include detailed information when listing galleries'
)
@click.option(
    '--list-folders',
    is_flag=True,
    help='List only folders/groups (not individual galleries)'
)
@click.option(
    '--folder',
    type=str,
    help='Download or list contents of a specific folder (regex pattern)'
)
@click.option(
    '--folder-id',
    type=int,
    help='Download or list contents of a specific folder by ID'
)
@click.option(
    '--gallery-id',
    type=int,
    help='Download a specific gallery by ID'
)
@click.option(
    '--folder-depth',
    type=int,
    default=1,
    help='Maximum depth to show when listing folders (default: 1 for top-level only)'
)
@click.option(
    '--show-ids',
    is_flag=True,
    help='Show folder and gallery IDs in listings'
)
@click.option(
    '--refresh-cache',
    is_flag=True,
    help='Refresh gallery hierarchy cache'
)
@click.option(
    '--cache-info',
    is_flag=True,
    help='Show cache information and exit'
)
@click.option(
    '--clear-cache',
    is_flag=True,
    help='Clear gallery hierarchy cache and exit'
)
@click.option(
    '--debug-download',
    type=int,
    help='Debug download a single photo by ID with verbose logging'
)
@click.option(
    '--debug-gallery',
    type=int,
    help='Debug download first photo from gallery ID with verbose logging'
)
@click.option(
    '--export-metadata',
    is_flag=True,
    help='Export complete metadata structure for verification (JSON and CSV)'
)
@click.option(
    '--metadata-format',
    type=click.Choice(['json', 'csv', 'both'], case_sensitive=False),
    default='both',
    help='Format for metadata export (default: both)'
)
@click.option(
    '--setup',
    is_flag=True,
    help='Run first-time setup to configure username, password, and download directory'
)
def main(
    output_dir: Optional[Path],
    concurrent_downloads: Optional[int],
    resume: bool,
    overwrite: bool,
    galleries: Optional[str],
    log_level: Optional[str],
    dry_run: bool,
    stats_only: bool,
    verify_integrity: bool,
    verify: bool,
    clear_checkpoint: bool,
    list_galleries: bool,
    list_details: bool,
    list_folders: bool,
    folder: Optional[str],
    folder_id: Optional[int],
    gallery_id: Optional[int],
    folder_depth: int,
    show_ids: bool,
    refresh_cache: bool,
    cache_info: bool,
    clear_cache: bool,
    debug_download: Optional[int],
    debug_gallery: Optional[int],
    export_metadata: bool,
    metadata_format: str,
    setup: bool
):
    """Zenfolio photo and video downloader.
    
    Downloads original quality photos and videos from Zenfolio.com with
    comprehensive error handling, resume capabilities, and progress tracking.
    
    If run without any arguments, launches interactive menu mode.
    """
    try:
        # Handle setup command
        if setup:
            success = run_first_time_setup(force=True)
            if success:
                print("\n🎉 Setup completed! You can now run the downloader.")
            else:
                print("\n❌ Setup failed. Please check the errors above.")
            return
        
        # Check if first-time setup is needed
        if should_run_setup():
            print("🔧 First-time setup required!")
            print("It looks like this is your first time running the Zenfolio downloader.")
            print("Let's configure your username, password, and download directory.\n")
            
            success = run_first_time_setup()
            if not success:
                print("\n❌ Setup failed. Please run 'python main.py --setup' to try again.")
                return
            
            print("\n🎉 Setup completed! Starting downloader...\n")
        
        # Load settings
        settings = get_settings()
        
        # Override settings with command line arguments
        if output_dir:
            settings.default_output_dir = output_dir
        if concurrent_downloads:
            settings.concurrent_downloads = concurrent_downloads
        if overwrite:
            settings.overwrite_existing = overwrite
        if log_level:
            settings.log_level = log_level.upper()
        
        # Setup logging
        setup_logging(settings)
        
        # Handle cache operations early
        if cache_info or clear_cache:
            cache_manager = CacheManager(
                cache_dir=Path(settings.cache_dir),
                cache_ttl_hours=settings.cache_ttl_hours
            )
            
            if clear_cache:
                cache_manager.clear_cache()
                click.echo("Cache cleared successfully")
                return
            
            if cache_info:
                cache_info_data = cache_manager.get_cache_info()
                if cache_info_data:
                    click.echo("\n=== CACHE INFORMATION ===")
                    click.echo(f"User: {cache_info_data['user_login']}")
                    click.echo(f"Created: {cache_info_data['created_at'].strftime('%Y-%m-%d %H:%M:%S')}")
                    click.echo(f"Expires: {cache_info_data['expires_at'].strftime('%Y-%m-%d %H:%M:%S')}")
                    click.echo(f"Status: {'Valid' if cache_info_data['is_valid'] else 'Expired'}")
                    click.echo(f"Entries: {cache_info_data['entry_count']}")
                    click.echo(f"Size: {cache_info_data['cache_size_mb']} MB")
                else:
                    click.echo("No cache found")
                return
        
        # Check if no meaningful arguments were provided (launch interactive mode)
        no_action_specified = not any([
            # Download/verify actions
            dry_run, stats_only, verify_integrity, verify, export_metadata,
            # Listing actions
            list_galleries, list_folders,
            # Specific targets
            folder, folder_id, gallery_id, galleries,
            # Debug actions
            debug_download, debug_gallery,
            # Already handled cache actions
            cache_info, clear_cache,
            # Checkpoint action
            clear_checkpoint
        ])
        
        if no_action_specified:
            # Launch interactive mode
            logger.debug("No action specified, launching interactive mode")
            asyncio.run(interactive_mode(settings))
            return
        
        logger.debug("Starting Zenfolio downloader")
        logger.debug(f"Output directory: {settings.default_output_dir}")
        logger.debug(f"Concurrent downloads: {settings.concurrent_downloads}")
        
        # Run the async main function
        asyncio.run(async_main(
            settings=settings,
            resume=resume,
            galleries=galleries,
            dry_run=dry_run,
            stats_only=stats_only,
            verify_integrity=verify_integrity,
            verify=verify,
            clear_checkpoint=clear_checkpoint,
            list_galleries=list_galleries,
            list_details=list_details,
            list_folders=list_folders,
            folder=folder,
            folder_id=folder_id,
            gallery_id=gallery_id,
            folder_depth=folder_depth,
            show_ids=show_ids,
            refresh_cache=refresh_cache,
            debug_download=debug_download,
            debug_gallery=debug_gallery,
            export_metadata=export_metadata,
            metadata_format=metadata_format
        ))
        
    except KeyboardInterrupt:
        logger.info("Download interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)


async def interactive_mode(settings: Settings):
    """Run the interactive menu mode."""
    # Initialize components
    checkpoint_manager = CheckpointManager(settings)
    checkpoint_manager.set_auto_save(True)  # Enable auto-save for checkpoint tracking
    statistics_tracker = StatisticsTracker()
    cache_manager = CacheManager(
        cache_dir=Path(settings.cache_dir),
        cache_ttl_hours=settings.cache_ttl_hours
    ) if settings.cache_enabled else None
    
    # Validate and repair cache if enabled
    if cache_manager:
        cache_manager.validate_and_repair_cache()
    
    # Initialize Zenfolio client
    async with ZenfolioClient(settings) as client:
        # Authenticate
        print("🔐 Authenticating with Zenfolio...")
        auth_success = await client.authenticate(
            settings.zenfolio_username,
            settings.zenfolio_password
        )
        
        if not auth_success:
            print("❌ Authentication failed")
            return
        
        print("✅ Authentication successful")
        
        # Load user profile and hierarchy
        print("📂 Loading gallery structure...")
        user_profile = await client.load_private_profile()
        root_group = await client.load_group_hierarchy(user_profile.login_name, force_refresh=False)
        
        # Prepare folder list for menu
        folders = prepare_folder_list(root_group)
        
        # Initialize menu and download manager
        menu = InteractiveMenu()
        download_manager = DownloadManager(
            settings=settings,
            client=client,
            checkpoint_manager=checkpoint_manager,
            statistics_tracker=statistics_tracker
        )
        
        # Main menu loop
        while True:
            choice = menu.display_main_menu(folders)
            
            if choice == 'quit':
                print("\n👋 Goodbye!")
                break
                
            elif choice == 'download_all':
                if menu.confirm_action("download", "ALL folders"):
                    print("\n🚀 Starting download of all folders...")
                    try:
                        checkpoint_manager.start_session()
                        await download_manager.download_all_galleries(
                            root_group=root_group,
                            output_dir=settings.default_output_dir
                        )
                        menu.show_completion_message("Download all folders", True)
                    except Exception as e:
                        menu.show_completion_message("Download all folders", False, str(e))
                        
            elif choice == 'verify_all':
                if menu.confirm_action("verify", "ALL folders"):
                    print("\n🔍 Verifying all folders...")
                    try:
                        success = await verify_download_completion(
                            download_manager, root_group, None, None, None, settings.default_output_dir
                        )
                        menu.show_completion_message("Verify all folders", success)
                    except Exception as e:
                        menu.show_completion_message("Verify all folders", False, str(e))
                        
            elif choice == 'process_retrieval_queue':
                print("\n⏳ Processing Zenfolio retrieval queue...")
                try:
                    results = await download_manager.process_retrieval_queue()
                    print(f"\n📊 Retrieval Queue Results:")
                    print(f"   Total items processed: {results['total_items']}")
                    print(f"   ✅ Successful: {results['successful']}")
                    print(f"   ❌ Failed: {results['failed']}")
                    print(f"   ⏳ Still pending: {results['still_pending']}")
                    
                    if results['successful'] > 0:
                        print(f"\n🎉 Successfully downloaded {results['successful']} items from retrieval queue!")
                    if results['still_pending'] > 0:
                        print(f"\n⏰ {results['still_pending']} items are still in Zenfolio's retrieval queue")
                        
                except Exception as e:
                    print(f"❌ Error processing retrieval queue: {e}")
                    
            elif choice == 'show_retrieval_status':
                print("\n📋 Retrieval Queue Status:")
                try:
                    summary = download_manager.retrieval_queue.get_queue_summary()
                    
                    if summary['total_items'] == 0:
                        print("   ✅ No items in retrieval queue")
                    else:
                        print(f"   📊 Total items: {summary['total_items']}")
                        print(f"\n   📁 By Gallery:")
                        for gallery_name, gallery_data in summary['galleries'].items():
                            total_size_mb = gallery_data['total_size'] / (1024 * 1024)
                            print(f"      • {gallery_name}: {gallery_data['count']} items ({total_size_mb:.1f} MB)")
                        
                        if summary['oldest_item']:
                            print(f"\n   ⏰ Oldest item: {summary['oldest_item']['file_name']}")
                            print(f"      Added: {summary['oldest_item']['added_at'][:19]}")
                            print(f"      Attempts: {summary['oldest_item']['attempt_count']}")
                            
                except Exception as e:
                    print(f"❌ Error getting retrieval queue status: {e}")
                    
            elif choice == 'select_folder':
                # Folder-specific menu loop
                while True:
                    folder_choice = menu.display_folder_menu()
                    
                    if folder_choice == 'quit':
                        print("\n👋 Goodbye!")
                        return
                    elif folder_choice == 'back':
                        break
                    elif folder_choice == 'download_folder':
                        selected_folder = menu.get_selected_folder()
                        if selected_folder and menu.confirm_action("download", f"folder '{selected_folder['title']}'"):
                            print(f"\n🚀 Starting download of folder: {selected_folder['title']}")
                            try:
                                checkpoint_manager.start_session()
                                if selected_folder['type'] == 'gallery':
                                    # Single gallery
                                    from api.models import Group
                                    temp_group = Group(
                                        id=0,
                                        title="Temp",
                                        created_on=selected_folder['object'].created_on,
                                        elements=[selected_folder['object']]
                                    )
                                    await download_manager.download_all_galleries(
                                        root_group=temp_group,
                                        output_dir=settings.default_output_dir
                                    )
                                else:
                                    # Folder/group
                                    folder_base_path = download_manager.directory_manager.sanitize_filename(selected_folder['title'])
                                    await download_manager.download_all_galleries(
                                        root_group=selected_folder['object'],
                                        output_dir=settings.default_output_dir,
                                        base_path=folder_base_path
                                    )
                                menu.show_completion_message(f"Download folder '{selected_folder['title']}'", True)
                            except Exception as e:
                                menu.show_completion_message(f"Download folder '{selected_folder['title']}'", False, str(e))
                                
                    elif folder_choice == 'verify_folder':
                        selected_folder = menu.get_selected_folder()
                        if selected_folder and menu.confirm_action("verify", f"folder '{selected_folder['title']}'"):
                            print(f"\n🔍 Verifying folder: {selected_folder['title']}")
                            try:
                                if selected_folder['type'] == 'gallery':
                                    success = await verify_download_completion(
                                        download_manager, root_group, None, selected_folder['id'], None, settings.default_output_dir
                                    )
                                else:
                                    success = await verify_download_completion(
                                        download_manager, root_group, selected_folder['id'], None, None, settings.default_output_dir
                                    )
                                menu.show_completion_message(f"Verify folder '{selected_folder['title']}'", success)
                            except Exception as e:
                                menu.show_completion_message(f"Verify folder '{selected_folder['title']}'", False, str(e))


async def async_main(
    settings: Settings,
    resume: bool,
    galleries: Optional[str],
    dry_run: bool,
    stats_only: bool,
    verify_integrity: bool,
    verify: bool,
    clear_checkpoint: bool,
    list_galleries: bool,
    list_details: bool,
    list_folders: bool,
    folder: Optional[str],
    folder_id: Optional[int],
    gallery_id: Optional[int],
    folder_depth: int,
    show_ids: bool,
    refresh_cache: bool,
    debug_download: Optional[int],
    debug_gallery: Optional[int],
    export_metadata: bool,
    metadata_format: str
):
    """Async main function for the downloader."""
    
    # Initialize components
    checkpoint_manager = CheckpointManager(settings)
    checkpoint_manager.set_auto_save(True)  # Enable auto-save for checkpoint tracking
    statistics_tracker = StatisticsTracker()
    cache_manager = CacheManager(
        cache_dir=Path(settings.cache_dir),
        cache_ttl_hours=settings.cache_ttl_hours
    ) if settings.cache_enabled else None
    
    # Validate and repair cache if enabled
    if cache_manager:
        cache_manager.validate_and_repair_cache()
    
    # Handle checkpoint operations
    if clear_checkpoint:
        checkpoint_manager.clear_checkpoint()
        logger.info("Checkpoint cleared")
        return
    
    if resume:
        checkpoint_loaded = checkpoint_manager.load_checkpoint()
        if checkpoint_loaded:
            resume_info = checkpoint_manager.get_resume_info()
            logger.debug(f"Resuming previous session: {resume_info}")
    
    # Initialize Zenfolio client
    async with ZenfolioClient(settings) as client:
        
        # Authenticate
        logger.debug("Authenticating with Zenfolio...")
        auth_success = await client.authenticate(
            settings.zenfolio_username,
            settings.zenfolio_password
        )
        
        if not auth_success:
            logger.error("Authentication failed")
            return
        
        logger.debug("Authentication successful")
        
        # Load user profile first (needed for cache key)
        logger.debug("Loading user profile...")
        user_profile = await client.load_private_profile()
        
        # Always rebuild processed hierarchy from raw API cache (fast local processing)
        # Only hit the API if raw cache is missing or refresh is requested
        root_group = await client.load_group_hierarchy(user_profile.login_name, force_refresh=refresh_cache)
        
        # Save processed hierarchy to cache for reference (optional, since we rebuild each time)
        if cache_manager:
            cache_manager.save_hierarchy_cache(user_profile, root_group)
        
        # Handle debug download commands first
        if debug_download or debug_gallery:
            await handle_debug_download(
                client=client,
                settings=settings,
                debug_download=debug_download,
                debug_gallery=debug_gallery,
                user_profile=user_profile,
                root_group=root_group
            )
            return
        
        # Handle metadata export
        if export_metadata:
            logger.info("Exporting complete metadata structure...")
            metadata_exporter = MetadataExporter(settings)
            
            try:
                metadata_file = metadata_exporter.export_complete_structure(
                    user=user_profile,
                    root_group=root_group,
                    output_dir=settings.default_output_dir,
                    export_format=metadata_format.lower()
                )
                
                logger.info(f"Metadata export completed successfully: {metadata_file}")
                print(f"\n✅ Metadata exported to: {metadata_file}")
                print(f"📊 Export format: {metadata_format.upper()}")
                print(f"📁 Output directory: {settings.default_output_dir}")
                
            except Exception as e:
                logger.error(f"Metadata export failed: {e}")
                print(f"\n❌ Metadata export failed: {e}")
                return
            
            return
        
        # Initialize download manager
        download_manager = DownloadManager(
            settings=settings,
            client=client,
            checkpoint_manager=checkpoint_manager,
            statistics_tracker=statistics_tracker
        )
        
        if list_galleries:
            # List galleries
            await show_gallery_list(user_profile, root_group, galleries, list_details, list_folders, show_ids)
            return
        
        if list_folders:
            # List only folders
            await show_folder_list(user_profile, root_group, folder, folder_depth, show_ids)
            return
        
        if stats_only:
            # Show statistics only
            await show_statistics(download_manager, root_group)
            return
        
        if verify_integrity:
            # Verify existing files
            await verify_existing_files(download_manager, settings.default_output_dir)
            return
        
        if verify:
            # Verify download completion
            await verify_download_completion(download_manager, root_group, folder_id, gallery_id, galleries, settings.default_output_dir)
            return
        
        if dry_run:
            # Apply folder filtering for dry-run if specified
            target_group = root_group
            folder_base_path = ""
            if folder_id:
                target_group = await _filter_group_by_id(root_group, folder_id)
                folder_base_path = download_manager.directory_manager.sanitize_filename(target_group.title)
                logger.info(f"Filtered to folder: {target_group.title} (ID: {target_group.id})")
                logger.info(f"Folder contains {len(target_group.subgroups)} subfolders and {len(target_group.galleries)} direct galleries")
            elif gallery_id:
                # For single gallery, create a minimal group containing just that gallery
                target_gallery = await _find_gallery_by_id(root_group, gallery_id)
                if target_gallery:
                    from api.models import Group
                    target_group = Group(
                        id=0,
                        title="Single Gallery",
                        created_on=datetime.now(),
                        elements=[target_gallery]
                    )
            
            # Show what would be downloaded
            await show_dry_run(download_manager, target_group, galleries, folder_base_path)
            return
        
        # Start the download process
        checkpoint_manager.start_session()
        
        try:
            # Handle ID-based filtering
            if folder_id:
                filtered_group = await _filter_group_by_id(root_group, folder_id)
                # Use the folder name as the base path to preserve hierarchy
                folder_base_path = download_manager.directory_manager.sanitize_filename(filtered_group.title)
                await download_manager.download_all_galleries(
                    root_group=filtered_group,
                    output_dir=settings.default_output_dir,
                    gallery_filter=galleries,
                    base_path=folder_base_path
                )
            elif gallery_id:
                # For gallery ID, we need to find the specific gallery and download just that
                gallery = await _find_gallery_by_id(root_group, gallery_id)
                if gallery:
                    # Create a temporary group containing just this gallery
                    from api.models import Group
                    temp_group = Group(
                        id=0,
                        title="Temp",
                        created_on=gallery.created_on,
                        elements=[gallery]
                    )
                    await download_manager.download_all_galleries(
                        root_group=temp_group,
                        output_dir=settings.default_output_dir,
                        gallery_filter=galleries
                    )
                else:
                    click.echo(f"Gallery with ID {gallery_id} not found")
                    return
            elif folder:
                filtered_group = await _filter_group_by_folder(root_group, folder)
                await download_manager.download_all_galleries(
                    root_group=filtered_group,
                    output_dir=settings.default_output_dir,
                    gallery_filter=galleries
                )
            else:
                await download_manager.download_all_galleries(
                    root_group=root_group,
                    output_dir=settings.default_output_dir,
                    gallery_filter=galleries
                )
            
            # Show final statistics
            logger.info("Download completed!")
            human_summary = statistics_tracker.get_human_readable_summary()
            logger.info(f"\n{human_summary}")
            
            # Clear checkpoint on successful completion
            if not dry_run:
                checkpoint_manager.clear_checkpoint()
                
        except Exception as e:
            logger.error(f"Download failed: {e}")
            # Save checkpoint on failure
            checkpoint_manager.save_checkpoint(force=True)
            raise


async def show_statistics(download_manager, root_group):
    """Show download statistics without downloading."""
    logger.info("Analyzing galleries for statistics...")
    
    # This would analyze the galleries and show statistics
    # Implementation would depend on the download_manager methods
    stats = await download_manager.analyze_galleries(root_group)
    
    click.echo("\n=== DOWNLOAD STATISTICS ===")
    click.echo(f"Total galleries: {stats.get('total_galleries', 0)}")
    click.echo(f"Total photos: {stats.get('total_photos', 0)}")
    click.echo(f"Total videos: {stats.get('total_videos', 0)}")
    click.echo(f"Total size: {stats.get('total_size_mb', 0):.2f} MB")
    click.echo(f"Estimated download time: {stats.get('estimated_time', 'Unknown')}")


async def verify_existing_files(download_manager, output_dir: Path):
    """Verify integrity of existing files."""
    logger.info(f"Verifying files in {output_dir}...")
    
    # This would verify existing files
    verification_results = await download_manager.verify_existing_files(output_dir)
    
    click.echo("\n=== FILE VERIFICATION RESULTS ===")
    click.echo(f"Files checked: {verification_results.get('total_checked', 0)}")
    click.echo(f"Valid files: {verification_results.get('valid_files', 0)}")
    click.echo(f"Invalid files: {verification_results.get('invalid_files', 0)}")
    click.echo(f"Missing files: {verification_results.get('missing_files', 0)}")


async def verify_download_completion(download_manager, root_group, folder_id: Optional[int], gallery_id: Optional[int], gallery_filter: Optional[str], output_dir: Path):
    """Verify that a previous download completed successfully."""
    from pathlib import Path
    import os
    
    try:
        # Determine what should have been downloaded
        target_group = root_group
        folder_base_path = ""
        
        if folder_id:
            target_group = await _filter_group_by_id(root_group, folder_id)
            folder_base_path = download_manager.directory_manager.sanitize_filename(target_group.title)
        elif gallery_id:
            # For single gallery, create a minimal group containing just that gallery
            target_gallery = await _find_gallery_by_id(root_group, gallery_id)
            if target_gallery:
                from api.models import Group
                target_group = Group(
                    id=0,
                    title="Single Gallery",
                    created_on=datetime.now(),
                    elements=[target_gallery]
                )
        
        # Get expected galleries
        expected_galleries = await download_manager._collect_galleries(target_group, gallery_filter, folder_base_path)
        
        # Check what actually exists on disk
        total_expected = len(expected_galleries)
        total_found = 0
        missing_galleries = []
        
        for gallery_info in expected_galleries:
            local_path = gallery_info['local_path']
            full_path = output_dir / local_path
            
            if full_path.exists() and any(full_path.iterdir()):
                total_found += 1
            else:
                missing_galleries.append(gallery_info['full_title'])
        
        # Generate result
        success = total_found == total_expected
        
        if success:
            click.echo(f"✅ Download verification PASSED: {total_found}/{total_expected} galleries found")
        else:
            click.echo(f"❌ Download verification FAILED: {total_found}/{total_expected} galleries found")
            if missing_galleries:
                click.echo("\nMissing galleries:")
                for missing in missing_galleries[:10]:  # Show first 10
                    click.echo(f"  - {missing}")
                if len(missing_galleries) > 10:
                    click.echo(f"  ... and {len(missing_galleries) - 10} more")
        
        return success
        
    except Exception as e:
        click.echo(f"❌ Verification failed with error: {e}")
        return False


async def show_dry_run(download_manager, root_group, gallery_filter: Optional[str], base_path: str = ""):
    """Show what would be downloaded without actually downloading."""
    logger.info("Performing dry run analysis...")
    
    # This would analyze what would be downloaded
    dry_run_results = await download_manager.dry_run_analysis(
        root_group,
        gallery_filter,
        base_path
    )
    
    click.echo("\n=== DRY RUN RESULTS ===")
    click.echo(f"Galleries to process: {dry_run_results.get('galleries_count', 0)}")
    click.echo(f"Files to download: {dry_run_results.get('files_to_download', 0)}")
    click.echo(f"Files to skip: {dry_run_results.get('files_to_skip', 0)}")
    click.echo(f"Total download size: {dry_run_results.get('total_size_mb', 0):.2f} MB")
    
    if dry_run_results.get('galleries'):
        click.echo("\nGalleries to process:")
        for gallery in dry_run_results['galleries']:
            click.echo(f"  - {gallery['name']} ({gallery['file_count']} files)")


async def show_gallery_list(user_profile, root_group, gallery_filter: Optional[str], show_details: bool, folders_only: bool = False, show_ids: bool = False):
    """Show list of available galleries in hierarchical tree structure."""
    try:
        # Display header
        if folders_only:
            click.echo(f"\n=== ZENFOLIO FOLDER STRUCTURE ===")
        else:
            click.echo(f"\n=== ZENFOLIO GALLERY STRUCTURE ===")
        click.echo(f"Account: {user_profile.login_name}")
        if gallery_filter:
            click.echo(f"Filter: {gallery_filter}")
        if show_ids:
            click.echo("Format: Item Name [ID: item_id] (details)")
        click.echo()
        
        # Display the hierarchical structure
        await _display_group_tree(root_group, "", gallery_filter, show_details, True, folders_only, show_ids)
        
    except Exception as e:
        logger.error(f"Failed to list galleries: {e}")
        click.echo(f"Error listing galleries: {e}")


async def show_folder_list(user_profile, root_group, folder_filter: Optional[str], max_depth: int = 1, show_ids: bool = False):
    """Show list of available folders only."""
    try:
        # Display header
        click.echo(f"\n=== ZENFOLIO FOLDERS ===")
        click.echo(f"Account: {user_profile.login_name}")
        if folder_filter:
            click.echo(f"Filter: {folder_filter}")
        if max_depth > 1:
            click.echo(f"Depth: {max_depth} levels")
        if show_ids:
            click.echo("Format: Folder Name [ID: folder_id] (counts)")
        click.echo()
        
        # Display only folders
        await _display_folders_only(root_group, "", folder_filter, True, max_depth, 0, show_ids)
        
    except Exception as e:
        logger.error(f"Failed to list folders: {e}")
        click.echo(f"Error listing folders: {e}")


async def _display_group_tree(group, indent: str, gallery_filter: Optional[str], show_details: bool, is_root: bool = True, folders_only: bool = False, show_ids: bool = False):
    """Display group and gallery structure in tree format."""
    
    # Don't show the root group title if it's just "Root"
    if not is_root or (group.title and group.title != "Root"):
        title_with_id = f"{group.title} [ID: {group.id}]" if show_ids else group.title
        click.echo(f"{indent}{title_with_id}")
        child_indent = indent + "  "
    else:
        child_indent = indent
    
    # Display subgroups first (folders)
    for subgroup in group.subgroups:
        await _display_group_tree(subgroup, child_indent, gallery_filter, show_details, False, folders_only, show_ids)
    
    # Display galleries in this group (unless folders_only is True)
    if not folders_only:
        for gallery in group.galleries:
            # Apply filter if specified
            if gallery_filter:
                try:
                    import re
                    if not re.search(gallery_filter, gallery.title, re.IGNORECASE):
                        continue
                except re.error as e:
                    logger.warning(f"Invalid gallery filter regex: {e}")
            
            # Display gallery
            gallery_title_with_id = f"{gallery.title} [ID: {gallery.id}]" if show_ids else gallery.title
            if show_details:
                # Show basic details from cached data (detailed loading would require additional API calls)
                click.echo(f"{child_indent}{gallery_title_with_id} ({gallery.photo_count} items)")
            else:
                click.echo(f"{child_indent}{gallery_title_with_id}")


async def _display_folders_only(group, indent: str, folder_filter: Optional[str], is_root: bool = True, max_depth: int = 1, current_depth: int = 0, show_ids: bool = False):
    """Display folders/groups and root-level galleries in tree format with depth limiting."""
    
    # Show the current group (unless it's the unnamed root)
    if not is_root or (group.title and group.title != "Root"):
        # Apply filter if specified
        if folder_filter:
            try:
                import re
                if not re.search(folder_filter, group.title, re.IGNORECASE):
                    return
            except re.error as e:
                logger.warning(f"Invalid folder filter regex: {e}")
        
        # Count galleries in this folder
        gallery_count = len(group.galleries)
        subgroup_count = len(group.subgroups)
        
        # Format the title with optional ID
        title_with_id = f"{group.title} [ID: {group.id}]" if show_ids else group.title
        
        if subgroup_count > 0 and gallery_count > 0:
            click.echo(f"{indent}{title_with_id} ({subgroup_count} folders, {gallery_count} galleries)")
        elif subgroup_count > 0:
            click.echo(f"{indent}{title_with_id} ({subgroup_count} folders)")
        elif gallery_count > 0:
            click.echo(f"{indent}{title_with_id} ({gallery_count} galleries)")
        else:
            click.echo(f"{indent}{title_with_id} (empty)")
    
    # Only show children if we haven't reached the maximum depth
    # For max_depth=1: show root (depth 0) and immediate children (depth 1), stop there
    if current_depth < max_depth:
        child_indent = indent + "  " if (not is_root or (group.title and group.title != "Root")) else indent
        next_depth = current_depth + 1
        
        # Show subgroups (folders)
        for subgroup in group.subgroups:
            await _display_folders_only(subgroup, child_indent, folder_filter, False, max_depth, next_depth, show_ids)
        
        # For root level only (depth 0), also show galleries that appear in sidebar
        if current_depth == 0:
            for gallery in group.galleries:
                # Apply filter if specified
                if folder_filter:
                    try:
                        import re
                        if not re.search(folder_filter, gallery.title, re.IGNORECASE):
                            continue
                    except re.error as e:
                        logger.warning(f"Invalid folder filter regex: {e}")
                        continue
                
                # Format the title with optional ID and indicate it's a gallery
                title_with_id = f"{gallery.title} [ID: {gallery.id}]" if show_ids else gallery.title
                click.echo(f"{child_indent}{title_with_id} ({gallery.photo_count} photos) [GALLERY]")


async def _filter_group_by_folder(root_group: Group, folder_name: str) -> Group:
    """Filter the root group to only include the specified folder and its contents."""
    def find_folder_recursive(group: Group, target_name: str) -> Optional[Group]:
        """Recursively search for a folder by name."""
        if group.title and group.title.lower() == target_name.lower():
            return group
        
        if group.subgroups:
            for sub_group in group.subgroups:
                result = find_folder_recursive(sub_group, target_name)
                if result:
                    return result
        return None
    
    # Find the target folder
    target_folder = find_folder_recursive(root_group, folder_name)
    if not target_folder:
        raise click.ClickException(f"Folder '{folder_name}' not found in the gallery structure")
    
    return target_folder


async def _filter_group_by_id(root_group: Group, folder_id: int) -> Group:
    """Filter the root group to only include the specified folder ID and its contents."""
    def find_folder_by_id_recursive(group: Group, target_id: int) -> Optional[Group]:
        """Recursively search for a folder by ID."""
        if group.id == target_id:
            return group
        
        if group.subgroups:
            for sub_group in group.subgroups:
                result = find_folder_by_id_recursive(sub_group, target_id)
                if result:
                    return result
        return None
    
    # Find the target folder
    target_folder = find_folder_by_id_recursive(root_group, folder_id)
    if not target_folder:
        raise click.ClickException(f"Folder with ID {folder_id} not found in the gallery structure")
    
    return target_folder


async def _find_gallery_by_id(root_group: Group, gallery_id: int):
    """Find a specific gallery by ID in the hierarchy."""
    def find_gallery_recursive(group: Group, target_id: int):
        """Recursively search for a gallery by ID."""
        # Check galleries in this group
        for gallery in group.galleries:
            if gallery.id == target_id:
                return gallery
        
        # Check subgroups
        if group.subgroups:
            for sub_group in group.subgroups:
                result = find_gallery_recursive(sub_group, target_id)
                if result:
                    return result
        return None
    
    return find_gallery_recursive(root_group, gallery_id)


async def handle_debug_download(
    client: ZenfolioClient,
    settings: Settings,
    debug_download: Optional[int],
    debug_gallery: Optional[int],
    user_profile,
    root_group: Group
):
    """Handle debug download commands with verbose logging."""
    import json
    from pathlib import Path
    
    # Force debug logging
    original_log_level = settings.log_level
    settings.log_level = "DEBUG"
    
    try:
        click.echo("\n=== DEBUG DOWNLOAD MODE ===")
        click.echo("Enhanced logging enabled for debugging 500 server errors")
        
        target_photo = None
        gallery_context = None
        
        if debug_download:
            # Find photo by ID across all galleries
            click.echo(f"Searching for photo ID: {debug_download}")
            target_photo, gallery_context = await find_photo_by_id(client, root_group, debug_download)
            
        elif debug_gallery:
            # Get first photo from specific gallery
            click.echo(f"Loading gallery ID: {debug_gallery}")
            try:
                gallery = await client.load_photo_set(debug_gallery, InformationLevel.LEVEL2, include_photos=True)
                if gallery.photos:
                    target_photo = gallery.photos[0]
                    gallery_context = gallery
                    click.echo(f"Using first photo from gallery: {gallery.title}")
                else:
                    click.echo(f"Gallery {debug_gallery} has no photos")
                    return
            except Exception as e:
                click.echo(f"Failed to load gallery {debug_gallery}: {e}")
                return
        
        if not target_photo:
            click.echo("No photo found for debugging")
            return
        
        # Display photo debug information
        click.echo(f"\n=== PHOTO DEBUG INFO ===")
        debug_info = target_photo.debug_info()
        for key, value in debug_info.items():
            click.echo(f"{key}: {value}")
        
        if gallery_context:
            click.echo(f"\nGallery: {gallery_context.title} (ID: {gallery_context.id})")
        
        # Check if photo is downloadable
        if not target_photo.is_downloadable:
            click.echo("\n❌ Photo is not downloadable (no download URL available)")
            return
        
        # Create download info
        debug_output_dir = Path("./debug_downloads")
        debug_output_dir.mkdir(exist_ok=True)
        
        download_info = client.get_download_info(target_photo, str(debug_output_dir))
        
        click.echo(f"\n=== DOWNLOAD INFO ===")
        click.echo(f"Download URL: {download_info.url}")
        click.echo(f"Local path: {download_info.local_path}")
        click.echo(f"Expected size: {download_info.expected_size}")
        
        # Attempt download with enhanced debugging
        click.echo(f"\n=== ATTEMPTING DOWNLOAD ===")
        
        from download.concurrent_downloader import ConcurrentDownloader
        from progress.statistics import StatisticsTracker
        
        downloader = ConcurrentDownloader(settings, client)
        stats_tracker = StatisticsTracker()
        
        try:
            # Perform single file download
            result = await downloader._download_single_file(
                download_info,
                gallery_context.title if gallery_context else "Debug",
                stats_tracker,
                None  # No progress callback for single file debug downloads
            )
            
            click.echo(f"\n=== DOWNLOAD RESULT ===")
            click.echo(f"Success: {result['success']}")
            if result['success']:
                click.echo(f"Bytes downloaded: {result['bytes_downloaded']:,}")
                click.echo(f"Duration: {result['duration_seconds']:.2f}s")
                click.echo(f"Speed: {result.get('download_speed_mbps', 0):.2f} MB/s")
                click.echo(f"File saved to: {result['file_path']}")
            else:
                click.echo(f"Error: {result['error']}")
                
                # Additional debugging for 500 errors
                if "500" in str(result['error']):
                    click.echo(f"\n=== 500 SERVER ERROR ANALYSIS ===")
                    click.echo("This indicates a server-side issue. Possible causes:")
                    click.echo("1. Photo file is corrupted or missing on Zenfolio's servers")
                    click.echo("2. Photo access permissions have changed")
                    click.echo("3. Photo has been moved or deleted")
                    click.echo("4. Temporary server issue")
                    click.echo("5. Authentication token has insufficient permissions")
                    
                    # Try to get more info about the photo
                    click.echo(f"\n=== ADDITIONAL PHOTO ANALYSIS ===")
                    if target_photo.access_descriptor:
                        click.echo(f"Access descriptor: {target_photo.access_descriptor}")
                    
                    # Check if URL is accessible with different methods
                    click.echo(f"\nTesting URL accessibility...")
                    await test_url_accessibility(client, download_info.url)
        
        except Exception as e:
            click.echo(f"\n❌ Download failed with exception: {e}")
            logger.exception("Debug download failed")
    
    finally:
        # Restore original log level
        settings.log_level = original_log_level


async def find_photo_by_id(client: ZenfolioClient, root_group: Group, photo_id: int):
    """Find a photo by ID across all galleries."""
    async def search_group(group: Group):
        # Search galleries in this group
        for gallery in group.galleries:
            try:
                full_gallery = await client.load_photo_set(gallery.id, InformationLevel.LEVEL2, include_photos=True)
                for photo in full_gallery.photos:
                    if photo.id == photo_id:
                        return photo, full_gallery
            except Exception as e:
                logger.warning(f"Failed to search gallery {gallery.title}: {e}")
        
        # Search subgroups
        for subgroup in group.subgroups:
            result = await search_group(subgroup)
            if result:
                return result
        
        return None, None
    
    return await search_group(root_group)


async def test_url_accessibility(client: ZenfolioClient, url: str):
    """Test URL accessibility with different methods."""
    try:
        # Test with HEAD request first
        async with client.session.head(url, headers=client.auth.get_auth_headers()) as response:
            click.echo(f"HEAD request status: {response.status}")
            click.echo(f"HEAD response headers: {dict(response.headers)}")
            
        # Test with GET request (first few bytes)
        async with client.session.get(
            url,
            headers={**client.auth.get_auth_headers(), 'Range': 'bytes=0-1023'}
        ) as response:
            click.echo(f"GET (partial) request status: {response.status}")
            click.echo(f"GET response headers: {dict(response.headers)}")
            if response.status != 200:
                response_text = await response.text()
                click.echo(f"GET response body: {response_text[:500]}")
                
    except Exception as e:
        click.echo(f"URL accessibility test failed: {e}")


if __name__ == '__main__':
    main()
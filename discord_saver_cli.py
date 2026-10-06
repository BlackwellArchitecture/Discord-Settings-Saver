import argparse
import sys
import os
import json
import settings_manager

def main():
    parser = argparse.ArgumentParser(
        description="Discord Settings Saver & Restorer (CLI)\nSave and load Discord voice, appearance, and client settings without losing logins."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Save command
    save_parser = subparsers.add_parser("save", help="Save current Discord settings to a backup file")
    save_parser.add_argument("--krisp-off", action="store_true", default=True, help="Force disable Krisp noise suppression in backup (default: True)")
    save_parser.add_argument("--keep-krisp", dest="krisp_off", action="store_false", help="Do not force disable Krisp")
    save_parser.add_argument("--output", type=str, default=None, help="Custom output JSON path")

    # Restore command
    restore_parser = subparsers.add_parser("restore", help="Restore Discord settings from a backup file")
    restore_parser.add_argument("--file", type=str, default=None, help="Path to backup JSON file (defaults to latest_backup.json)")
    restore_parser.add_argument("--krisp-off", action="store_true", default=True, help="Force disable Krisp during restore")
    restore_parser.add_argument("--relaunch", action="store_true", default=True, help="Relaunch Discord after restore (default: True)")
    restore_parser.add_argument("--no-relaunch", dest="relaunch", action="store_false", help="Do not relaunch Discord after restore")

    # List command
    subparsers.add_parser("list", help="List all available backups")

    # Status command
    subparsers.add_parser("status", help="Show Discord process and settings directory status")

    args = parser.parse_args()
    mgr = settings_manager.DiscordSettingsManager()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "status":
        running = mgr.is_discord_running()
        print("=== Discord Settings Saver Status ===")
        print(f"Discord Process:    {'RUNNING' if running else 'CLOSED'}")
        print(f"AppData Directory:  {mgr.discord_dir}")
        print(f"LevelDB Directory:  {mgr.leveldb_dir} ({'Found' if os.path.exists(mgr.leveldb_dir) else 'Not Found'})")
        print(f"settings.json:      {mgr.settings_json_path} ({'Found' if os.path.exists(mgr.settings_json_path) else 'Not Found'})")
        backups = mgr.list_backups()
        print(f"Saved Backups:      {len(backups)}")

    elif args.command == "list":
        backups = mgr.list_backups()
        if not backups:
            print("No saved backups found in backups/ directory.")
            return
        print(f"Found {len(backups)} backup(s):")
        print("-" * 75)
        print(f"{'Filename':<38} {'Date/Time':<20} {'Stores':<8} {'Size (KB)':<8}")
        print("-" * 75)
        for b in backups:
            created = b.get("created_at", "")[:19].replace("T", " ")
            print(f"{b['filename']:<38} {created:<20} {b['stores_count']:<8} {b['size_kb']:<8}")
        print("-" * 75)

    elif args.command == "save":
        print(f"Exporting Discord settings (Krisp Off={args.krisp_off})...")
        success, path, data = mgr.export_settings(
            force_disable_krisp=args.krisp_off,
            output_filepath=args.output
        )
        if success:
            stores_count = len(data.get("stores", {}))
            print(f"[SUCCESS] Exported {stores_count} settings stores to:")
            print(f"  -> {path}")
            print("  Note: User authentication tokens were excluded for safety.")
        else:
            print(f"[ERROR] Failed to save settings: {path}")
            sys.exit(1)

    elif args.command == "restore":
        target_file = args.file
        if not target_file:
            latest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_backup.json")
            if os.path.exists(latest):
                target_file = latest
            else:
                backups = mgr.list_backups()
                if backups:
                    target_file = backups[0]["filepath"]
                else:
                    print("[ERROR] No backups found to restore! Please run 'save' first.")
                    sys.exit(1)

        print(f"Restoring settings from: {target_file}")
        if mgr.is_discord_running():
            print("Discord is currently running. Closing Discord gracefully...")
            if not mgr.close_discord():
                print("[ERROR] Failed to close Discord. Please close Discord manually.")
                sys.exit(1)

        success, msg = mgr.restore_settings(
            backup_filepath=target_file,
            force_disable_krisp=args.krisp_off
        )

        if success:
            print(f"[SUCCESS] {msg}")
            if args.relaunch:
                print("Relaunching Discord with restored settings...")
                mgr.launch_discord()
        else:
            print(f"[ERROR] Restore failed: {msg}")
            sys.exit(1)

if __name__ == "__main__":
    main()

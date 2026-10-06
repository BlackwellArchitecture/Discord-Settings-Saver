import os
import json
import shutil
import time
import subprocess
import glob
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
import leveldb_engine

DISCORD_ORIGIN_PREFIX = b'_https://discord.com\x00\x01'

# Keys that belong to authentication, account credentials, or ephemeral sessions
# These are NEVER exported to backup files, and NEVER overwritten on restore if present!
AUTH_AND_SESSION_KEYS = {
    'token',
    'tokens',
    'user_id_cache',
    'MultiAccountStore',
    'LAST_CLIENT_HEARTBEAT_SESSION',
    'installation_id_v3',
    'app_native_crashStorage'
}

# Large cache/telemetry keys that don't represent user settings and should be omitted to keep backups lean
CACHE_KEYS_TO_SKIP = {
    'GameStore',  # ~10MB detectable games registry
    'FrecencyStore',
    'UserAffinitiesStoreV2',
    'GuildAffinitiesStore',
    'NonGameStore',
    'scientist:triggered',
    'apexTrackedExposures'
}

class DiscordSettingsManager:
    def __init__(self, discord_path: Optional[str] = None):
        if discord_path:
            self.discord_dir = discord_path
        else:
            self.discord_dir = os.path.expandvars(r"%APPDATA%\discord")
        self.leveldb_dir = os.path.join(self.discord_dir, "Local Storage", "leveldb")
        self.settings_json_path = os.path.join(self.discord_dir, "settings.json")
        self.backups_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
        os.makedirs(self.backups_dir, exist_ok=True)

    def is_discord_running(self) -> bool:
        """Checks if Discord process is currently active."""
        try:
            output = subprocess.check_output(
                'tasklist /FI "IMAGENAME eq Discord.exe" /NH',
                shell=True,
                stderr=subprocess.DEVNULL
            ).decode('utf-8', errors='ignore')
            return "Discord.exe" in output
        except Exception:
            return False

    def close_discord(self, timeout_sec: int = 5) -> bool:
        """Closes Discord processes cleanly or forcibly."""
        if not self.is_discord_running():
            return True
        try:
            subprocess.run('taskkill /IM Discord.exe /T', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        
        start = time.time()
        while time.time() - start < timeout_sec:
            if not self.is_discord_running():
                return True
            time.sleep(0.3)
            
        # Force kill if still running
        try:
            subprocess.run('taskkill /F /IM Discord.exe /T', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass
        time.sleep(0.5)
        return not self.is_discord_running()

    def launch_discord(self) -> bool:
        """Finds and starts Discord desktop app."""
        local_app = os.path.expandvars(r"%LOCALAPPDATA%\Discord")
        # Find latest app-* directory
        exe_paths = glob.glob(os.path.join(local_app, "app-*", "Discord.exe"))
        if not exe_paths:
            # Fallback to Update.exe --processStart Discord.exe
            update_exe = os.path.join(local_app, "Update.exe")
            if os.path.exists(update_exe):
                subprocess.Popen([update_exe, "--processStart", "Discord.exe"])
                return True
            return False
            
        # Sort by version
        latest_exe = sorted(exe_paths)[-1]
        subprocess.Popen([latest_exe], start_new_session=True)
        return True

    def export_settings(self,
                        force_disable_krisp: bool = True,
                        output_filepath: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Reads Discord settings from disk, filters out credentials, applies requested overrides,
        and saves to a JSON backup file.
        """
        try:
            # 1. Read settings.json
            client_settings = {}
            if os.path.exists(self.settings_json_path):
                with open(self.settings_json_path, 'r', encoding='utf-8') as f:
                    client_settings = json.load(f)

            # 2. Read LevelDB records
            raw_records = leveldb_engine.read_all_leveldb_records(self.leveldb_dir)
            stores_data = {}

            for k, val_bytes in raw_records.items():
                if not k.startswith(DISCORD_ORIGIN_PREFIX):
                    continue
                store_name = k[len(DISCORD_ORIGIN_PREFIX):].decode('utf-8', errors='ignore')
                
                # NEVER export auth or session keys
                if store_name in AUTH_AND_SESSION_KEYS:
                    continue
                # Skip massive cache stores
                if store_name in CACHE_KEYS_TO_SKIP:
                    continue

                # Parse value: first byte \x01 is UTF-8 string prefix, \x00 is UTF-16
                text = ""
                if val_bytes.startswith(b'\x01'):
                    text = val_bytes[1:].decode('utf-8', errors='replace')
                elif val_bytes.startswith(b'\x00'):
                    text = val_bytes[1:].decode('utf-16le', errors='replace')
                else:
                    text = val_bytes.decode('utf-8', errors='replace')

                # Try parsing as JSON object/array
                try:
                    parsed_val = json.loads(text)
                    stores_data[store_name] = parsed_val
                except Exception:
                    stores_data[store_name] = text

            # 3. Apply overrides if requested
            overrides_applied = {}
            if force_disable_krisp and "MediaEngineStore" in stores_data:
                self._apply_krisp_disable(stores_data["MediaEngineStore"])
                overrides_applied["vadUseKrisp"] = False

            # 4. Construct backup payload
            timestamp_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            backup_data = {
                "schema_version": 1,
                "created_at": datetime.now().isoformat(),
                "created_timestamp": timestamp_str,
                "computer_name": os.environ.get("COMPUTERNAME", "UNKNOWN"),
                "overrides_applied": overrides_applied,
                "client_settings": client_settings,
                "stores": stores_data
            }

            # 5. Save to file
            if not output_filepath:
                output_filepath = os.path.join(self.backups_dir, f"discord_settings_{timestamp_str}.json")
            
            with open(output_filepath, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            # Also maintain a "latest_backup.json" symlink/copy in the workspace folder
            latest_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_backup.json")
            with open(latest_path, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)

            return True, output_filepath, backup_data

        except Exception as e:
            return False, f"Failed to export settings: {str(e)}", {}

    def restore_settings(self,
                         backup_filepath: str,
                         force_disable_krisp: bool = True) -> Tuple[bool, str]:
        """
        Restores settings from backup_filepath into Discord.
        Preserves active login session / tokens.
        """
        if self.is_discord_running():
            closed = self.close_discord(timeout_sec=5)
            if not closed:
                return False, "Could not close Discord. Please close Discord manually before restoring."

        if not os.path.exists(backup_filepath):
            return False, f"Backup file not found: {backup_filepath}"

        try:
            with open(backup_filepath, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
        except Exception as e:
            return False, f"Invalid backup file: {str(e)}"

        try:
            # 1. Create a safety backup of existing LevelDB & settings.json before overwriting!
            safety_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_backup_dir = os.path.join(self.backups_dir, f"safety_pre_restore_{safety_ts}")
            if os.path.exists(self.leveldb_dir):
                shutil.copytree(self.leveldb_dir, os.path.join(safety_backup_dir, "leveldb"))
            if os.path.exists(self.settings_json_path):
                os.makedirs(safety_backup_dir, exist_ok=True)
                shutil.copy2(self.settings_json_path, os.path.join(safety_backup_dir, "settings.json"))

            # 2. Read CURRENT live keys from disk (to preserve active login tokens!)
            current_live = leveldb_engine.read_all_leveldb_records(self.leveldb_dir)
            preserved_auth = {}
            for k, v in current_live.items():
                if k.startswith(DISCORD_ORIGIN_PREFIX):
                    sub = k[len(DISCORD_ORIGIN_PREFIX):].decode('utf-8', errors='ignore')
                    if sub in AUTH_AND_SESSION_KEYS:
                        preserved_auth[k] = v

            # 3. Prepare target KV dictionary
            new_kv: Dict[bytes, bytes] = {}

            # Keep any preserved auth tokens
            for k, v in preserved_auth.items():
                new_kv[k] = v

            # 4. Prepare stores from backup
            stores = backup_data.get("stores", {})

            # Apply requested overrides to the restored data
            if force_disable_krisp and "MediaEngineStore" in stores:
                self._apply_krisp_disable(stores["MediaEngineStore"])

            for store_name, store_val in stores.items():
                # Never overwrite auth from backup
                if store_name in AUTH_AND_SESSION_KEYS:
                    continue

                full_key = DISCORD_ORIGIN_PREFIX + store_name.encode('utf-8')

                # Serialize value with \x01 prefix (Chromium LocalStorage format)
                if isinstance(store_val, (dict, list, bool, int, float)):
                    encoded_str = json.dumps(store_val, separators=(',', ':'))
                else:
                    encoded_str = str(store_val)
                    
                val_bytes = b'\x01' + encoded_str.encode('utf-8')
                new_kv[full_key] = val_bytes

            # Also ensure META origin key exists
            meta_key = b'META:https://discord.com'
            if meta_key in current_live:
                new_kv[meta_key] = current_live[meta_key]
            else:
                new_kv[meta_key] = b'\x01' + json.dumps({"origin": "https://discord.com"}).encode('utf-8')

            # 5. Write fresh LevelDB database cleanly
            temp_target = os.path.join(self.discord_dir, "Local Storage", "leveldb_new")
            leveldb_engine.write_complete_leveldb(temp_target, new_kv)

            # Atomic swap
            old_temp = os.path.join(self.discord_dir, "Local Storage", "leveldb_old")
            if os.path.exists(old_temp):
                shutil.rmtree(old_temp)
            if os.path.exists(self.leveldb_dir):
                os.rename(self.leveldb_dir, old_temp)
            os.rename(temp_target, self.leveldb_dir)
            if os.path.exists(old_temp):
                shutil.rmtree(old_temp)

            # 6. Restore settings.json
            client_settings = backup_data.get("client_settings")
            if client_settings and isinstance(client_settings, dict):
                # Preserve existing devtools or custom hardware switches if already set, or overwrite
                with open(self.settings_json_path, 'w', encoding='utf-8') as f:
                    json.dump(client_settings, f, indent=2)

            return True, f"Settings successfully restored! (Safety backup saved to {os.path.basename(safety_backup_dir)})"

        except Exception as e:
            return False, f"Restore failed: {str(e)}"

    def _apply_krisp_disable(self, media_engine_data: Any):
        """Recursively walks media engine store and forces Krisp noise suppression off."""
        if not isinstance(media_engine_data, dict):
            return
            
        def walk_and_disable(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("vadUseKrisp", "noiseCancellationKrisp", "ncUseKrisp"):
                        obj[k] = False
                    elif isinstance(v, (dict, list)):
                        walk_and_disable(v)
            elif isinstance(obj, list):
                for item in obj:
                    walk_and_disable(item)

        walk_and_disable(media_engine_data)

    def list_backups(self) -> list[dict]:
        """Lists all existing backups with metadata."""
        backups = []
        pattern = os.path.join(self.backups_dir, "*.json")
        for fpath in glob.glob(pattern):
            fname = os.path.basename(fpath)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                backups.append({
                    "filename": fname,
                    "filepath": fpath,
                    "created_at": data.get("created_at", "Unknown"),
                    "stores_count": len(data.get("stores", {})),
                    "size_kb": round(os.path.getsize(fpath) / 1024, 1)
                })
            except Exception:
                pass
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        return backups

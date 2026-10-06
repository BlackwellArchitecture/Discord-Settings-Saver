import os
import sys
import threading
import json
import subprocess
from datetime import datetime
import customtkinter as ctk
from tkinter import messagebox, filedialog
import settings_manager

# Set CustomTkinter theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# Discord brand colors
COLOR_DISCORD_BG = "#1e1f22"
COLOR_PANEL_BG = "#2b2d31"
COLOR_CARD_BG = "#313338"
COLOR_BURPLE = "#5865F2"
COLOR_BURPLE_HOVER = "#4752C4"
COLOR_GREEN = "#23a55a"
COLOR_GREEN_HOVER = "#1d874a"
COLOR_RED = "#da373c"
COLOR_RED_HOVER = "#b82e32"
COLOR_TEXT_MUTED = "#949ba4"

class DiscordSettingsSaverApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Discord Settings Saver & Restorer")
        self.geometry("860x680")
        self.minsize(780, 600)
        self.configure(fg_color=COLOR_DISCORD_BG)

        self.manager = settings_manager.DiscordSettingsManager()

        # Variables
        self.krisp_var = ctk.BooleanVar(value=True)       # Always disable Krisp
        self.relaunch_discord_var = ctk.BooleanVar(value=True)

        self._build_ui()
        self._refresh_backups_list()
        self._update_discord_status()

        # Auto-refresh Discord status every 3 seconds
        self.after(3000, self._periodic_status_check)

    def _build_ui(self):
        # Grid layout
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # 1. Header Frame
        header_frame = ctk.CTkFrame(self, fg_color=COLOR_PANEL_BG, corner_radius=12)
        header_frame.grid(row=0, column=0, padx=16, pady=(16, 10), sticky="ew")
        header_frame.grid_columnconfigure(1, weight=1)

        # App Icon / Title
        title_box = ctk.CTkFrame(header_frame, fg_color="transparent")
        title_box.grid(row=0, column=0, padx=16, pady=14, sticky="w")

        title_lbl = ctk.CTkLabel(
            title_box,
            text="🛡️ Discord Settings Saver",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#ffffff"
        )
        title_lbl.pack(anchor="w")

        subtitle_lbl = ctk.CTkLabel(
            title_box,
            text="Preserves voice configuration, layout, small text & Krisp rules without touching logins",
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED
        )
        subtitle_lbl.pack(anchor="w")

        # Discord Status Badge & Controls
        status_box = ctk.CTkFrame(header_frame, fg_color=COLOR_CARD_BG, corner_radius=8)
        status_box.grid(row=0, column=1, padx=16, pady=12, sticky="e")

        self.status_dot = ctk.CTkLabel(status_box, text="●", font=ctk.CTkFont(size=14), text_color=COLOR_GREEN)
        self.status_dot.pack(side="left", padx=(10, 4), pady=6)

        self.status_label = ctk.CTkLabel(status_box, text="Discord Running", font=ctk.CTkFont(size=12, weight="bold"))
        self.status_label.pack(side="left", padx=(0, 10), pady=6)

        self.btn_toggle_discord = ctk.CTkButton(
            status_box,
            text="Close Discord",
            width=100,
            height=28,
            fg_color=COLOR_RED,
            hover_color=COLOR_RED_HOVER,
            command=self._on_toggle_discord_click
        )
        self.btn_toggle_discord.pack(side="left", padx=(0, 8), pady=6)

        # 2. Main Action Card & Rules Card
        middle_container = ctk.CTkFrame(self, fg_color="transparent")
        middle_container.grid(row=1, column=0, padx=16, pady=6, sticky="ew")
        middle_container.grid_columnconfigure((0, 1), weight=1)

        # Left Card: Quick Actions (Save & Restore)
        action_card = ctk.CTkFrame(middle_container, fg_color=COLOR_PANEL_BG, corner_radius=12)
        action_card.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="nsew")

        act_title = ctk.CTkLabel(action_card, text="Quick Operations", font=ctk.CTkFont(size=15, weight="bold"))
        act_title.pack(anchor="w", padx=16, pady=(12, 6))

        # Save Button
        self.btn_save = ctk.CTkButton(
            action_card,
            text="💾 Save Discord Settings Now",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLOR_BURPLE,
            hover_color=COLOR_BURPLE_HOVER,
            height=40,
            command=self._on_save_clicked
        )
        self.btn_save.pack(fill="x", padx=16, pady=(4, 6))

        # Restore Button
        self.btn_restore = ctk.CTkButton(
            action_card,
            text="⚡ Restore Saved Settings",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=COLOR_GREEN,
            hover_color=COLOR_GREEN_HOVER,
            height=40,
            command=self._on_restore_clicked
        )
        self.btn_restore.pack(fill="x", padx=16, pady=(4, 8))

        relaunch_chk = ctk.CTkCheckBox(
            action_card,
            text="Automatically relaunch Discord after restore",
            variable=self.relaunch_discord_var,
            font=ctk.CTkFont(size=12),
            text_color=COLOR_TEXT_MUTED
        )
        relaunch_chk.pack(anchor="w", padx=16, pady=(2, 12))

        # Right Card: Permanent Rule Overrides (Krisp, Small Text, etc.)
        rules_card = ctk.CTkFrame(middle_container, fg_color=COLOR_PANEL_BG, corner_radius=12)
        rules_card.grid(row=0, column=1, padx=(8, 0), pady=0, sticky="nsew")

        rules_title = ctk.CTkLabel(rules_card, text="⚙️ Permanent Rules & Overrides", font=ctk.CTkFont(size=15, weight="bold"))
        rules_title.pack(anchor="w", padx=16, pady=(12, 6))

        # Krisp Toggle
        krisp_switch = ctk.CTkSwitch(
            rules_card,
            text="ALWAYS Disable Krisp Noise Suppression",
            variable=self.krisp_var,
            font=ctk.CTkFont(size=13, weight="bold"),
            progress_color=COLOR_BURPLE
        )
        krisp_switch.pack(anchor="w", padx=16, pady=(8, 4))

        krisp_sub = ctk.CTkLabel(
            rules_card,
            text="Prevents Discord from silently enabling Krisp after resets",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED
        )
        krisp_sub.pack(anchor="w", padx=36, pady=(0, 10))

        # Backup Info Label
        info_sub = ctk.CTkLabel(
            rules_card,
            text="✓ Saves & restores your exact custom appearance, voice levels & keybinds as configured.",
            font=ctk.CTkFont(size=11),
            text_color=COLOR_TEXT_MUTED,
            wraplength=350,
            justify="left"
        )
        info_sub.pack(anchor="w", padx=16, pady=(4, 12))

        # 3. Bottom Section: Backups List & Live Status Log
        bottom_container = ctk.CTkFrame(self, fg_color=COLOR_PANEL_BG, corner_radius=12)
        bottom_container.grid(row=2, column=0, padx=16, pady=(8, 16), sticky="nsew")
        bottom_container.grid_columnconfigure((0, 1), weight=1)
        bottom_container.grid_rowconfigure(1, weight=1)

        # Headers
        b_hdr = ctk.CTkLabel(bottom_container, text="Saved Backups", font=ctk.CTkFont(size=14, weight="bold"))
        b_hdr.grid(row=0, column=0, padx=16, pady=(10, 4), sticky="w")

        l_hdr = ctk.CTkLabel(bottom_container, text="Activity Log", font=ctk.CTkFont(size=14, weight="bold"))
        l_hdr.grid(row=0, column=1, padx=16, pady=(10, 4), sticky="w")

        # Backups Scrollable List
        self.backups_scroll = ctk.CTkScrollableFrame(bottom_container, fg_color=COLOR_CARD_BG, corner_radius=8)
        self.backups_scroll.grid(row=1, column=0, padx=(16, 8), pady=(0, 12), sticky="nsew")

        # Activity Log Textbox
        self.log_box = ctk.CTkTextbox(
            bottom_container,
            fg_color=COLOR_CARD_BG,
            corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#dcddde"
        )
        self.log_box.grid(row=1, column=1, padx=(8, 16), pady=(0, 12), sticky="nsew")
        self.log_box.configure(state="disabled")

        self._log("System initialized. Discord data directory: " + self.manager.discord_dir)

    def _log(self, text: str):
        """Appends timestamped message to log box."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        msg = f"[{timestamp}] {text}\n"
        self.log_box.configure(state="normal")
        self.log_box.insert("end", msg)
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _periodic_status_check(self):
        self._update_discord_status()
        self.after(3000, self._periodic_status_check)

    def _update_discord_status(self):
        running = self.manager.is_discord_running()
        if running:
            self.status_dot.configure(text_color=COLOR_GREEN)
            self.status_label.configure(text="Discord Running")
            self.btn_toggle_discord.configure(
                text="Close Discord",
                fg_color=COLOR_RED,
                hover_color=COLOR_RED_HOVER
            )
        else:
            self.status_dot.configure(text_color=COLOR_TEXT_MUTED)
            self.status_label.configure(text="Discord Closed")
            self.btn_toggle_discord.configure(
                text="Open Discord",
                fg_color=COLOR_GREEN,
                hover_color=COLOR_GREEN_HOVER
            )

    def _on_toggle_discord_click(self):
        running = self.manager.is_discord_running()
        if running:
            self._log("Closing Discord...")
            closed = self.manager.close_discord()
            if closed:
                self._log("Discord closed successfully.")
            else:
                self._log("Failed to close Discord.")
        else:
            self._log("Launching Discord...")
            launched = self.manager.launch_discord()
            if launched:
                self._log("Discord launched.")
            else:
                self._log("Could not find Discord executable.")
        self._update_discord_status()

    def _refresh_backups_list(self):
        # Clear existing children
        for widget in self.backups_scroll.winfo_children():
            widget.destroy()

        backups = self.manager.list_backups()
        if not backups:
            empty_lbl = ctk.CTkLabel(
                self.backups_scroll,
                text="No backups saved yet.\nClick 'Save Discord Settings Now' above!",
                text_color=COLOR_TEXT_MUTED,
                font=ctk.CTkFont(size=12)
            )
            empty_lbl.pack(pady=40)
            return

        for b in backups:
            item = ctk.CTkFrame(self.backups_scroll, fg_color=COLOR_PANEL_BG, corner_radius=6)
            item.pack(fill="x", padx=4, pady=3)
            item.grid_columnconfigure(0, weight=1)

            # Details
            info_frame = ctk.CTkFrame(item, fg_color="transparent")
            info_frame.grid(row=0, column=0, padx=8, pady=6, sticky="w")

            created = b.get("created_at", "")[:19].replace("T", " ")
            fn_lbl = ctk.CTkLabel(info_frame, text=created, font=ctk.CTkFont(size=12, weight="bold"))
            fn_lbl.pack(anchor="w")

            meta_lbl = ctk.CTkLabel(
                info_frame,
                text=f"{b.get('stores_count')} stores • {b.get('size_kb')} KB",
                font=ctk.CTkFont(size=11),
                text_color=COLOR_TEXT_MUTED
            )
            meta_lbl.pack(anchor="w")

            # Buttons
            btn_frame = ctk.CTkFrame(item, fg_color="transparent")
            btn_frame.grid(row=0, column=1, padx=6, pady=6, sticky="e")

            fpath = b.get("filepath")

            res_btn = ctk.CTkButton(
                btn_frame,
                text="Restore",
                width=65,
                height=26,
                fg_color=COLOR_GREEN,
                hover_color=COLOR_GREEN_HOVER,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda p=fpath: self._restore_specific_backup(p)
            )
            res_btn.pack(side="left", padx=2)

            del_btn = ctk.CTkButton(
                btn_frame,
                text="✕",
                width=26,
                height=26,
                fg_color="#4f545c",
                hover_color=COLOR_RED,
                font=ctk.CTkFont(size=11),
                command=lambda p=fpath: self._delete_backup(p)
            )
            del_btn.pack(side="left", padx=2)

    def _on_save_clicked(self):
        self.btn_save.configure(state="disabled")
        self._log("Saving Discord settings...")

        def run_save():
            krisp_rule = self.krisp_var.get()

            success, path, data = self.manager.export_settings(
                force_disable_krisp=krisp_rule
            )

            def finish():
                self.btn_save.configure(state="normal")
                if success:
                    stores_count = len(data.get("stores", {}))
                    self._log(f"SUCCESS: Saved {stores_count} setting stores to {os.path.basename(path)}")
                    self._log(f"Login credentials omitted for safety. Krisp Off: {krisp_rule}")
                    self._refresh_backups_list()
                    messagebox.showinfo("Settings Saved", f"Successfully saved Discord settings!\n\nLocation:\n{path}")
                else:
                    self._log(f"ERROR: {path}")
                    messagebox.showerror("Error", f"Failed to save settings:\n{path}")

            self.after(0, finish)

        threading.Thread(target=run_save, daemon=True).start()

    def _on_restore_clicked(self):
        latest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "latest_backup.json")
        if not os.path.exists(latest):
            backups = self.manager.list_backups()
            if not backups:
                messagebox.showwarning("No Backups", "No saved settings found! Please click 'Save Discord Settings Now' first.")
                return
            latest = backups[0]["filepath"]

        self._restore_specific_backup(latest)

    def _restore_specific_backup(self, backup_filepath: str):
        if not os.path.exists(backup_filepath):
            messagebox.showerror("Error", "Backup file does not exist!")
            return

        confirm = messagebox.askyesno(
            "Confirm Restore",
            "This will restore your voice, appearance, and configuration settings.\n\n"
            "• Active login session will be PRESERVED\n"
            "• Discord will be closed automatically during restore\n"
            "• A safety rollback point will be created\n\n"
            "Do you want to proceed?"
        )
        if not confirm:
            return

        self.btn_restore.configure(state="disabled")
        self._log(f"Restoring from: {os.path.basename(backup_filepath)}...")

        def run_restore():
            krisp_rule = self.krisp_var.get()

            success, msg = self.manager.restore_settings(
                backup_filepath=backup_filepath,
                force_disable_krisp=krisp_rule
            )

            # Relaunch if requested
            if success and self.relaunch_discord_var.get():
                time.sleep(1)
                self.manager.launch_discord()

            def finish():
                self.btn_restore.configure(state="normal")
                self._update_discord_status()
                if success:
                    self._log(f"RESTORE COMPLETE: {msg}")
                    if self.relaunch_discord_var.get():
                        self._log("Discord relaunched with restored settings!")
                    messagebox.showinfo("Restore Complete", f"Discord settings restored successfully!\n\n{msg}")
                else:
                    self._log(f"RESTORE FAILED: {msg}")
                    messagebox.showerror("Restore Failed", f"Failed to restore settings:\n{msg}")

            self.after(0, finish)

        threading.Thread(target=run_restore, daemon=True).start()

    def _delete_backup(self, filepath: str):
        confirm = messagebox.askyesno("Delete Backup", f"Are you sure you want to delete {os.path.basename(filepath)}?")
        if confirm:
            try:
                os.remove(filepath)
                self._log(f"Deleted backup: {os.path.basename(filepath)}")
                self._refresh_backups_list()
            except Exception as e:
                self._log(f"Error deleting: {e}")

if __name__ == "__main__":
    app = DiscordSettingsSaverApp()
    app.mainloop()

import sys
import os

if __name__ == "__main__":
    # If command line arguments were passed (like save, restore, list, status), run CLI
    if len(sys.argv) > 1:
        import discord_saver_cli
        discord_saver_cli.main()
    else:
        # Otherwise launch the modern GUI
        import discord_saver_gui
        app = discord_saver_gui.DiscordSettingsSaverApp()
        app.mainloop()

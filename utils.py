import tomllib

def load_settings():
    try:
        # Load settings from TOML file
        with open("settings.TOML", "rb") as f:
            settings = tomllib.load(f)
        return settings
    except FileNotFoundError:
        print("settings.TOML not found.")
        return None
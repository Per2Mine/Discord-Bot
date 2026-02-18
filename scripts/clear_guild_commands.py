import tomllib
import requests
import sys
import time

def load_settings(path="settings.TOML"):
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        print("settings.TOML not found.")
        sys.exit(1)


def main():
    settings = load_settings()
    bot_cfg = settings.get("bot", {})
    token = bot_cfg.get("token")
    app_id = bot_cfg.get("application_id")
    guild_id = bot_cfg.get("test_guild_id")

    if not token or not app_id or not guild_id:
        print("Required values missing in settings.TOML: token, application_id, test_guild_id")
        sys.exit(1)

    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    base = f"https://discord.com/api/v10/applications/{app_id}/guilds/{guild_id}/commands"

    try:
        r = requests.get(base, headers=headers)
        r.raise_for_status()
    except Exception as e:
        print("Failed to list commands:", e)
        sys.exit(1)

    commands = r.json()
    print(f"Found {len(commands)} command(s) in guild {guild_id}")

    session = requests.Session()
    for cmd in commands:
        cid = cmd.get("id")
        if not cid:
            continue
        url = f"{base}/{cid}"
        retries = 0
        while True:
            try:
                d = session.delete(url, headers=headers)
            except Exception as e:
                print("Error deleting", cid, e)
                break

            if d.status_code in (200, 204):
                print("Deleted", cid)
                break
            if d.status_code == 429:
                # Respect Discord's retry_after
                try:
                    body = d.json()
                    retry = float(body.get("retry_after", 1.0))
                except Exception:
                    retry = 1.0
                wait = retry + 0.5
                print(f"Rate limited on {cid}, sleeping {wait:.2f}s and retrying...")
                time.sleep(wait)
                retries += 1
                if retries > 5:
                    print("Too many retries for", cid)
                    break
                continue
            else:
                print("Failed to delete", cid, d.status_code, d.text)
                break

    print("Done.")


if __name__ == "__main__":
    main()

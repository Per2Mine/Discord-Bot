# Discord Music Bot (No AI)

Ein schlanker Musikbot für Discord mit Slash-Commands, Prefix-Aliases, Warteschlange, Playlist-Unterstützung und interaktiven Player-Buttons.

Dieses Repository enthält den Bot-Code, Konfiguration und Hilfsskripte. Die wichtigsten Dateien:

- `bot.py` – Hauptlogik, Slash-Commands, Prefix-Handling und Wiedergabe-Loop.
- `settings.TOML` – Konfiguration: Token, Prefix, Zeitlimits, Alias-Definitionen.
- `services/` – Hilfsfunktionen zur Track-/Playlist-Extraktion (YouTube, Spotify).
- `scripts/clear_guild_commands.py` – Hilfsskript zum Löschen von Guild-Slash-Commands (bei Signaturkonflikten).
- `requirements.txt` – Python-Abhängigkeiten.

**Inhalt**

- **Voraussetzungen**
- **Installation & Setup**
- **Konfiguration (`settings.TOML`)**
- **Starten**
- **Commands (Slash & Prefix)**
- **Player-Buttons**
- **Playlist-Support**
- **Skript: Guild-Command-Cleanup**
- **Troubleshooting**
- **Docker / Deployment Hinweise**

## Voraussetzungen

- Python 3.11+ (oder kompatibel mit den verwendeten Typen)
- Systempakete:
  - `ffmpeg` (wichtig für Audio-Streaming)
  - Opus-Bibliothek (z. B. `libopus`/`libopus-dev`) – benötigt für Discord-Voice
- Ein Discord-Bot-Token und (optional) `application_id` / `test_guild_id` für schnelles Command-Sync.

Die Python-Abhängigkeiten sind in `requirements.txt` aufgeführt. Installiere sie in einer virtuellen Umgebung:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Auf Debian/Ubuntu beispielsweise:

```bash
sudo apt update
sudo apt install ffmpeg libopus0
```

Auf Arch/Manjaro:

```bash
sudo pacman -S ffmpeg opus
```

Hinweis: Je nach Distribution kann das Paket anders heißen. In Container-Umgebungen muss `ffmpeg` im Image vorhanden sein.

## Installation & Setup

1. Repository klonen oder in deinen Projektordner kopieren.
2. In `settings.TOML` deinen Bot-Token eintragen:

```toml
[bot]
token = "<DEIN_BOT_TOKEN>"
prefix = "/"                # Prefix für on_message Befehle
test_guild_id = "<DEV_GUILD_ID>" # optional: schneller Slash-Sync
application_id = "<APP_ID>"
idle_timeout = 120           # Sekunden: Trennen bei Leerlauf (Queue leer)
pause_idle_timeout = 300     # Sekunden: Trennen nach zu langer Pause
skip_required = 1
skip_use_majority = false
```

3. Alias-Befehle anpassen (unter `[commands]`) – Beispiel:

```toml
[commands]
play = ["play","p","spielen"]
pause = ["pause","pausieren"]
skip = ["skip","next"]
playlist = ["playlist","pl"]
```

4. (Optional) Setze `test_guild_id` für schnellen lokalen Slash-Command-Sync während der Entwicklung.

## Starten

Starte den Bot mit deiner Python-Umgebung:

```bash
.venv/bin/python bot.py
# oder
# python3 bot.py
```

Beim `on_ready` wird der Command-Tree automatisch synchronisiert. Wenn du auf Signatur-Fehler stößt (z. B. CommandSignatureMismatch), benutze das Cleanup-Skript (siehe weiter unten).

## Konfiguration (`settings.TOML`) — wichtige Einstellungen

- `token`: Bot-Token (erforderlich)
- `prefix`: String, der Prefix für `on_message`-Befehle ist (z. B. `/` oder `!`)
- `test_guild_id`: Optional; wenn gesetzt, werden Slash-Commands nur in diesem Guild synchronisiert (schneller)
- `application_id`: optional, App-ID
- `idle_timeout`: Sekunden vor automatischem Trennen wenn die Queue leer ist (-1 = nie)
- `pause_idle_timeout`: Sekunden vor Trennen wenn der Player pausiert ist (-1 = nie)
- `skip_required`: Anzahl Stimmen (falls `skip_use_majority` false)
- `skip_use_majority`: Wenn true, wird die Mehrheit non-bot Mitglieder als Schwelle genutzt

Unter `[commands]` definierst du Prefix-Aliase für die internen Commands.

## Commands

Slash-Commands (verfügbar via `/`):

- `/play <query>` — Suche oder URL abspielen (wartet in der Queue)
- `/playlist <url>` — Alle Tracks einer YouTube-Playlist in die Queue legen
- `/queue` — Zeigt aktuelle Queue
- `/skip` — Überspringt aktuellen Track
- `/pause` — Pausiert Wiedergabe (startet Pause-Idle-Timer)
- `/resume` — Setzt Wiedergabe fort (bricht Pause-Idle-Timer ab)
- `/help` — Basis-Hilfe
- `/hello` — Grußnachricht

Prefix-Befehle (falls `prefix` gesetzt):

- `/<alias>` (z. B. `/play` oder `/p`) — funktionieren genauso wie die Slash-Äquivalente, werden in `settings.TOML` unter `[commands]` definiert.

## Player-Buttons

Der Bot sendet eine einzelne Player-Message mit einem `PlayerView` (Buttons):

- **Play/Pause** — Pausiert oder setzt fort (stummes Defer, keine sichtbare Interaktion). Pausieren startet den `pause_idle_timeout`.
- **Skip** — Fügt eine Stimme hinzu; bei Erreichen der Schwelle wird geskippt und öffentlich angekündigt.
- **Queue** — Zeigt die Queue als ephemeren Text (nur für dem Anfragenden sichtbar).
- **Repeat** — Toggle: Wiederholt aktuellen Track (setzt Track wieder an den Anfang der Queue).
- **Stop** — Stoppt Playback, leert Queue, löscht Player-Nachricht und verlässt Channel.

Button-Antworten sind bewusst nicht-intrusiv (deferred), um keine Ephemeralen beim Drücken zu hinterlassen.

## Playlist-Unterstützung

`/playlist <YouTube-Playlist-URL>` extrahiert die Playlist-Einträge (via `yt-dlp`) und legt die Tracks in die Queue.

## Skript: Guild-Slash-Command Cleanup

Wenn Discord eine `CommandSignatureMismatch`-Fehlermeldung anzeigt (z. B. wegen veralteter Slash-Commands), benutze das Skript:

```bash
python3 scripts/clear_guild_commands.py
```

Das Skript liest `settings.TOML` und entfernt Slash-Commands aus dem konfigurierten `test_guild_id` (sicherstellen, dass Token korrekt ist). Es behandelt Rate-Limits durch sleeps/retries.

## Troubleshooting

- Keine Audioausgabe
  - Stelle sicher, dass `ffmpeg` im PATH ist und `libopus` installiert ist.
  - Prüfe Bot-Logs auf `Failed to play` oder `Player error` Meldungen.
- Slash-Commands erscheinen nicht / Signaturfehler
  - Setze `test_guild_id` in `settings.TOML` auf eine Entwickler-Guild-ID und starte den Bot neu.
  - Falls Probleme bleiben, führe `scripts/clear_guild_commands.py` aus und starte neu.
- Bot verlässt Channel nicht
  - Prüfe `idle_timeout` und `pause_idle_timeout` in `settings.TOML`. `-1` deaktiviert automatisches Trennen.

## Docker / Deployment Hinweise

Für Container-Images stelle sicher, dass `ffmpeg` und `opus` verfügbar sind. Beispiel `Dockerfile`-Snippet (Debian/Ubuntu base):

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y ffmpeg libopus0 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . /app
RUN python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
CMD [".venv/bin/python","bot.py"]
```

Passe das Image an dein Deployment und Secrets-Management an (do not hardcode tokens in images).

## Weiterentwicklung

- `services/` ist so aufgebaut, dass weitere Extractor (z. B. für andere Quellen) hinzugefügt werden können.
- Verbesserungsideen: Persistente Queue (DB), Admin-Commands, verbesserte Fehlerbehandlung für große Playlists.

## Sicherheit & Hinweise

- Lege niemals deinen Bot-Token öffentlich frei (z. B. in öffentlichen Repositories).
- Bewahre `settings.TOML` sicher auf; nutze Umgebungsvariablen/Secrets beim Deployment.

---

Wenn du willst, füge ich noch ein kurzes Beispiel-`settings.TOML` (ohne Token) ins Repo oder passe das `Dockerfile` an und schreibe ein kleines Start-Skript für Systemd/PM2.

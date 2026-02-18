# Nutze ein offizielles Python-Image
FROM python:3.11-slim

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Kopiere die Liste der Bibliotheken und installiere sie
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \ 
    ffmpeg libopus0 && rm -rf /var/lib/apt/lists/*

# Kopiere deinen restlichen Code (bot.py)
COPY . .

# Befehl, der ausgeführt wird, wenn der Container startet
CMD ["python", "bot.py"]
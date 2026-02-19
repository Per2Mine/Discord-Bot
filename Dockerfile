# Nutze ein offizielles Python-Image
FROM python:3.13-slim

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Installiere System-Abhängigkeiten
RUN apt-get update && apt-get install -y --no-install-recommends \ 
    ffmpeg libopus0 && rm -rf /var/lib/apt/lists/*

# Kopiere die Liste der Bibliotheken und installiere sie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere deinen restlichen Code (bot.py)
COPY . .

# Befehl, der ausgeführt wird, wenn der Container startet
CMD ["python", "bot.py"]
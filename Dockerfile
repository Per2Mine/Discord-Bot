# Nutze ein offizielles Python-Image
FROM python:3.11-slim

# Arbeitsverzeichnis im Container festlegen
WORKDIR /app

# Kopiere die Liste der Bibliotheken und installiere sie
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiere deinen restlichen Code (bot.py)
COPY . .

# Befehl, der ausgeführt wird, wenn der Container startet
CMD ["python", "bot.py"]
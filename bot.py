# This example requires the 'message_content' intent.

import discord
from utils import load_settings

settings = load_settings()
BOT_TOKEN = settings["bot"]["token"] if settings else ""

class MyClient(discord.Client):
    async def on_ready(self):
        print(f'Logged on as {self.user}!')

    async def on_message(self, message):
        print(f'Message from {message.author}: {message.content}')

# Die Berechtigungen für den Bot
intents = discord.Intents.default()
intents.message_content = True

client = MyClient(intents=intents)
client.run(BOT_TOKEN)

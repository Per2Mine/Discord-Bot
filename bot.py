# This example requires the 'message_content' intent.

from unittest import case
import discord
from discord import app_commands
from discord.ui import View, button
import re
import asyncio
from utils import load_settings
from services.youtube import extract_youtube, extract_playlist
from services.spotify import is_spotify_url, resolve_spotify_title

settings = load_settings()
BOT_TOKEN = settings["bot"]["token"] if settings else ""
PREFIX = "/"
COMMANDS = {}
if settings:
    PREFIX = settings.get("bot", {}).get("prefix", PREFIX)
    COMMANDS = settings.get("commands", {})

# normalize command aliases: produce mapping of internal command -> list of aliases
COMMAND_ALIASES: dict[str, list[str]] = {}
for k, v in (COMMANDS or {}).items():
    if isinstance(v, str):
        COMMAND_ALIASES[k] = [v.lower()]
    elif isinstance(v, list):
        COMMAND_ALIASES[k] = [str(x).lower() for x in v]
    else:
        # fallback: use key itself
        COMMAND_ALIASES[k] = [k]

# Die Berechtigungen für den Bot
intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


class PlayerView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Play/Pause", style=discord.ButtonStyle.primary)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        # acknowledge silently (no visible message)
        await interaction.response.defer()
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            return
        gid = interaction.guild.id
        if vc.is_playing():
            vc.pause()
            # schedule pause-idle disconnect
            bot_cfg = settings.get('bot', {}) if settings else {}
            pause_idle = int(bot_cfg.get('pause_idle_timeout', 300))
            if pause_idle != -1:
                async def pause_wait():
                    try:
                        await asyncio.sleep(pause_idle)
                        vc2 = interaction.guild.voice_client
                        if vc2 and vc2.is_connected() and getattr(vc2, 'is_paused', lambda: False)() and not vc2.is_playing():
                            try:
                                msg = now_playing_message.pop(gid, None)
                                if msg:
                                    try:
                                        await msg.delete()
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                            try:
                                await vc2.disconnect()
                                print(f"[pause-idle] Disconnected from guild {gid} after {pause_idle}s paused")
                            except Exception as e:
                                print('Pause-idle disconnect error:', e)
                    finally:
                        pause_idle_tasks.pop(gid, None)

                # cancel existing pause-idle task
                t = pause_idle_tasks.get(gid)
                if t:
                    t.cancel()
                pause_idle_tasks[gid] = asyncio.create_task(pause_wait())
        elif getattr(vc, 'is_paused', lambda: False)():
            # resume -> cancel any pause-idle
            t = pause_idle_tasks.pop(gid, None)
            if t:
                try:
                    t.cancel()
                except Exception:
                    pass
            vc.resume()

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        # silently register skip vote and update player message
        await interaction.response.defer()
        gid = interaction.guild.id
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            return
        user_id = interaction.user.id
        votes = skip_votes.setdefault(gid, set())
        if user_id in votes:
            # already voted; ignore duplicate
            return
        votes.add(user_id)

        # determine required count
        bot_cfg = settings.get('bot', {}) if settings else {}
        use_majority = bool(bot_cfg.get('skip_use_majority', False))
        required = int(bot_cfg.get('skip_required', 1))
        if use_majority:
            # count non-bot members in the voice channel
            ch = vc.channel
            nonbots = [m for m in ch.members if not m.bot]
            required = (len(nonbots) // 2) + 1

        # update player message embed with votes
        msg = now_playing_message.get(gid)
        current = len(votes)
        if msg:
            try:
                embed = msg.embeds[0] if msg.embeds else discord.Embed()
                desc = embed.description or ''
                # replace or append skip line
                lines = [l for l in (desc.splitlines()) if not l.startswith('Skip votes:')]
                lines.append(f'Skip votes: {current}/{required}')
                embed.description = '\n'.join(lines)
                await msg.edit(embed=embed)
            except Exception:
                pass

        # if threshold reached, perform skip and notify publicly
        if current >= required:
            # announce skip
            if msg and getattr(msg, 'channel', None):
                try:
                    await msg.channel.send(f'Skip passed ({current}/{required}) — skipping.')
                except Exception:
                    pass
            try:
                if vc.is_playing() or getattr(vc, 'is_paused', lambda: False)():
                    vc.stop()
            except Exception:
                pass

    # volume buttons removed

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        # show queue as ephemeral message
        await interaction.response.defer(ephemeral=True)
        q = queues.get(interaction.guild.id, [])
        if not q:
            await interaction.followup.send('Queue is empty.', ephemeral=True)
            return
        lines = []
        for i, t in enumerate(q, start=1):
            lines.append(f'{i}. {t.get("title")}')
        msg = '\n'.join(lines[:50])
        await interaction.followup.send(f'Queue:\n{msg}', ephemeral=True)

    @discord.ui.button(label="Repeat", style=discord.ButtonStyle.secondary)
    async def repeat_toggle(self, interaction: discord.Interaction, button: discord.ui.Button):
        # toggle repeat for the guild; silent
        await interaction.response.defer()
        gid = interaction.guild.id
        cur = bool(repeat_flags.get(gid, False))
        repeat_flags[gid] = not cur
        # update player message to indicate repeat status
        msg = now_playing_message.get(gid)
        if msg:
            try:
                embed = msg.embeds[0] if msg.embeds else discord.Embed()
                footer_text = f"Repeat: {'ON' if repeat_flags[gid] else 'OFF'}"
                embed.set_footer(text=footer_text)
                await msg.edit(embed=embed, view=PlayerView())
            except Exception:
                pass

    @discord.ui.button(label="Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        # silently stop and leave
        await interaction.response.defer()
        vc = interaction.guild.voice_client
        if not vc or not vc.is_connected():
            return
        try:
            if vc.is_playing() or getattr(vc, 'is_paused', lambda: False)():
                vc.stop()
        except Exception:
            pass
        queues.pop(interaction.guild.id, None)
        # remove stored player message if exists
        try:
            gid = interaction.guild.id
            msg = now_playing_message.pop(gid, None)
            if msg:
                try:
                    await msg.delete()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            await vc.disconnect()
        except Exception:
            pass
        # cancel any pause-idle task
        try:
            t2 = pause_idle_tasks.pop(interaction.guild.id, None)
            if t2:
                try:
                    t2.cancel()
                except Exception:
                    pass
        except Exception:
            pass


# --- Audio / playback helpers ---
FFMPEG_BEFORE_OPTIONS = '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
FFMPEG_OPTIONS = '-vn'

# simple per-guild queue
queues: dict[int, list] = {}
# skip vote tracking and current player message
skip_votes: dict[int, set] = {}
now_playing_message: dict[int, discord.Message] = {}
# idle disconnect tasks per guild
idle_tasks: dict[int, asyncio.Task] = {}
# pause-idle tasks (when player is paused for too long)
pause_idle_tasks: dict[int, asyncio.Task] = {}
# repeat flag per guild (repeat current track)
repeat_flags: dict[int, bool] = {}



async def extract_track_info(query: str):
    if not query:
        return None

    # if spotify, resolve to title and search youtube
    if is_spotify_url(query):
        title = resolve_spotify_title(query)
        search = f'ytsearch1:{title}' if title else f'ytsearch1:{query}'
    else:
        # if a youtube URL, pass directly, otherwise treat as search
        if re.search(r'(youtube\.com|youtu\.be)', query):
            search = query
        else:
            search = f'ytsearch1:{query}'

    info = await extract_youtube(search)
    if not info:
        return None

    try:
        print(f'[extract] Found track: {info.get("title")} -> {info.get("url")}')
    except Exception:
        pass

    return info


async def ensure_player_message(channel: discord.abc.Messageable, gid: int, embed: discord.Embed, view: View):
    """Ensure there is exactly one player message in the channel for guild `gid`."""
    stored = now_playing_message.get(gid)
    if stored:
        try:
            # ensure it still exists and edit it in place
            await stored.edit(embed=embed, view=view)
            return stored
        except discord.NotFound:
            # stored was deleted, send new
            new = await channel.send(embed=embed, view=view)
            now_playing_message[gid] = new
            return new
        except Exception:
            # on any other failure, attempt to recreate
            try:
                new = await channel.send(embed=embed, view=view)
                now_playing_message[gid] = new
                return new
            except Exception:
                return stored
    else:
        new = await channel.send(embed=embed, view=view)
        now_playing_message[gid] = new
        return new


async def ensure_voice(interaction: discord.Interaction):
    channel = None
    if interaction.user and getattr(interaction.user, 'voice', None):
        channel = interaction.user.voice.channel
    if not channel:
        return None, 'You are not in a voice channel.'

    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        try:
            vc = await channel.connect()
            print(f"[voice] Connected to {channel} in guild {interaction.guild.id}")
        except Exception as e:
            return None, f'Failed to join voice channel: {e}'
    return vc, None


async def play_next_for_guild(guild: discord.Guild):
    q = queues.get(guild.id, [])
    if not q:
        # schedule idle disconnect
        bot_cfg = settings.get('bot', {}) if settings else {}
        idle = int(bot_cfg.get('idle_timeout', 120))
        if idle == -1:
            return

        async def idle_wait():
            try:
                await asyncio.sleep(idle)
                vc = guild.voice_client
                q2 = queues.get(guild.id, [])
                if (not q2 or len(q2) == 0) and vc and vc.is_connected() and not vc.is_playing():
                    try:
                        # delete player message if present
                        try:
                            msg = now_playing_message.pop(guild.id, None)
                            if msg:
                                try:
                                    await msg.delete()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        await vc.disconnect()
                        print(f"[idle] Disconnected from guild {guild.id} after {idle}s idle")
                    except Exception as e:
                        print('Idle disconnect error:', e)
            finally:
                idle_tasks.pop(guild.id, None)

        # cancel existing task
        t = idle_tasks.get(guild.id)
        if t:
            t.cancel()
        idle_tasks[guild.id] = asyncio.create_task(idle_wait())
        return
    track = q.pop(0)
    vc = guild.voice_client
    if not vc or not vc.is_connected():
        return

    source_url = track.get('url')
    if not source_url:
        # skip if no source
        await play_next_for_guild(guild)
        return

    # cancel idle task if present
    t = idle_tasks.pop(guild.id, None)
    if t:
        try:
            t.cancel()
        except Exception:
            pass
    # cancel pause-idle task if present (we are starting playback)
    t2 = pause_idle_tasks.pop(guild.id, None)
    if t2:
        try:
            t2.cancel()
        except Exception:
            pass

    print(f"[play] Guild {guild.id} playing: {track.get('title')} ({source_url})")

    # reset skip votes and update player message
    skip_votes[guild.id] = set()
    embed = discord.Embed(title='Now Playing', description=f"{track.get('title')}\n\nSkip votes: 0/{int(settings.get('bot', {}).get('skip_required', 1))}")
    # footer: repeat status
    try:
        if repeat_flags.get(guild.id, False):
            embed.set_footer(text='Repeat: ON')
        else:
            embed.set_footer(text='Repeat: OFF')
    except Exception:
        pass
    try:
        # update or recreate player message (moves to bottom if needed)
        msg = await ensure_player_message(now_playing_message[guild.id].channel, guild.id, embed, PlayerView()) if now_playing_message.get(guild.id) else await ensure_player_message(guild.text_channels[0], guild.id, embed, PlayerView())
    except Exception:
        pass

    def after_play(error):
        if error:
            print('Player error:', error)
        # handle repeat: if enabled, re-insert the same track at front
        try:
            if repeat_flags.get(guild.id, False):
                queues.setdefault(guild.id, []).insert(0, track)
        except Exception:
            pass
        # schedule next
        fut = asyncio.run_coroutine_threadsafe(play_next_for_guild(guild), client.loop)
        try:
            fut.result()
        except Exception:
            pass

    player = discord.FFmpegPCMAudio(source_url, before_options=FFMPEG_BEFORE_OPTIONS, options=FFMPEG_OPTIONS)
    try:
        vc.play(player, after=after_play)
    except Exception as e:
        print('Failed to play:', e)


@tree.command(name='skip', description='Skip current track')
async def slash_skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        await interaction.response.send_message('Bot is not in voice channel.', ephemeral=True)
        return
    if vc.is_playing():
        vc.stop()
        await interaction.response.send_message('Skipped.', ephemeral=True)
    else:
        await interaction.response.send_message('Nothing is playing.', ephemeral=True)


@tree.command(name='queue', description='Show the current queue')
async def slash_queue(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    q = queues.get(interaction.guild.id, [])
    if not q:
        await interaction.followup.send('Queue is empty.')
        return
    lines = []
    for i, t in enumerate(q, start=1):
        lines.append(f'{i}. {t.get("title")}')
    msg = '\n'.join(lines[:50])
    await interaction.followup.send(f'Queue:\n{msg}')


@tree.command(name='help', description='Show basic help')
async def slash_help(interaction: discord.Interaction):
    await interaction.response.send_message('Available slash commands: /play, /pause, /resume, /skip, /queue, /help', ephemeral=True)


@tree.command(name='hello', description='Say hello')
async def slash_hello(interaction: discord.Interaction):
    await interaction.response.send_message(f'Hello, {interaction.user.display_name}!')


@tree.command(name='pause', description='Pause playback')
async def slash_pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        await interaction.response.send_message('Bot is not in voice channel.', ephemeral=True)
        return
    if vc.is_playing():
        vc.pause()
        # schedule pause-idle disconnect
        bot_cfg = settings.get('bot', {}) if settings else {}
        pause_idle = int(bot_cfg.get('pause_idle_timeout', 300))
        gid = interaction.guild.id
        if pause_idle != -1:
            async def pause_wait():
                try:
                    await asyncio.sleep(pause_idle)
                    vc2 = interaction.guild.voice_client
                    if vc2 and vc2.is_connected() and getattr(vc2, 'is_paused', lambda: False)() and not vc2.is_playing():
                        try:
                            msg = now_playing_message.pop(gid, None)
                            if msg:
                                try:
                                    await msg.delete()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        try:
                            await vc2.disconnect()
                            print(f"[pause-idle] Disconnected from guild {gid} after {pause_idle}s paused")
                        except Exception as e:
                            print('Pause-idle disconnect error:', e)
                finally:
                    pause_idle_tasks.pop(gid, None)

            t = pause_idle_tasks.get(gid)
            if t:
                t.cancel()
            pause_idle_tasks[gid] = asyncio.create_task(pause_wait())
        await interaction.response.send_message('Paused.', ephemeral=True)
    else:
        await interaction.response.send_message('Nothing is playing.', ephemeral=True)


@tree.command(name='resume', description='Resume playback')
async def slash_resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if not vc or not vc.is_connected():
        await interaction.response.send_message('Bot is not in voice channel.', ephemeral=True)
        return
    if getattr(vc, 'is_paused', lambda: False)():
        vc.resume()
        # cancel any pause-idle task
        t = pause_idle_tasks.pop(interaction.guild.id, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass
        await interaction.response.send_message('Resumed.', ephemeral=True)
    else:
        await interaction.response.send_message('Player is not paused.', ephemeral=True)

@client.event
async def on_ready():
    print(f'We have logged in as {client.user}')
    try:
        # If you set a test_guild_id in settings.TOML the bot will sync commands
        # to that guild (fast). Otherwise it will sync globally (can take minutes).
        test_guild = None
        if settings:
            tg = settings.get("bot", {}).get("test_guild_id")
            if tg:
                try:
                    test_guild = discord.Object(id=int(tg))
                except Exception:
                    test_guild = None

        if test_guild:
            await tree.sync(guild=test_guild)
            print(f'Slash commands synced to guild {test_guild.id}.')
        else:
            await tree.sync()
            print('Slash commands synced.')
    except Exception as e:
        print('Failed to sync slash commands:', e)


# Example slash command for music play (stub)
@tree.command(name="play", description="Play a song or URL")
@app_commands.describe(query="Song name or URL")
async def slash_play(interaction: discord.Interaction, query: str | None = None):
    # send an immediate ephemeral acknowledgement to avoid the "thinking" indicator
    query_text = (query or "").strip()
    if not query_text:
        await interaction.response.send_message('Please provide a search term or URL.', ephemeral=True)
        return
    # quick ack
    await interaction.response.send_message(f'Queued: {query_text}', ephemeral=True)

    info = await extract_track_info(query_text)
    if not info:
        try:
            await interaction.followup.send('Could not find the requested track.', ephemeral=True)
        except Exception:
            pass
        return

    gid = interaction.guild.id
    queues.setdefault(gid, [])
    queues[gid].append(info)

    # cancel idle disconnect if scheduled
    t = idle_tasks.pop(gid, None)
    if t:
        try:
            t.cancel()
        except Exception:
            pass

    # ensure voice connection
    vc, err = await ensure_voice(interaction)
    if err:
        await interaction.followup.send(err, ephemeral=True)
        return

    # if nothing is playing, start
    if not vc.is_playing() and not (getattr(vc, 'is_paused', lambda: False)()):
        await play_next_for_guild(interaction.guild)


@tree.command(name="playlist", description="Queue all tracks from a YouTube playlist URL")
@app_commands.describe(url="YouTube playlist URL")
async def slash_playlist(interaction: discord.Interaction, url: str):
    await interaction.response.defer(ephemeral=True)
    if not url:
        await interaction.followup.send('Please provide a playlist URL.', ephemeral=True)
        return

    # extract playlist entries
    tracks = await extract_playlist(url)
    if not tracks:
        await interaction.followup.send('No tracks found in playlist.', ephemeral=True)
        return

    gid = interaction.guild.id
    queues.setdefault(gid, [])
    queues[gid].extend(tracks)

    # cancel idle disconnect if scheduled
    t = idle_tasks.pop(gid, None)
    if t:
        try:
            t.cancel()
        except Exception:
            pass

    # ensure voice connection
    vc, err = await ensure_voice(interaction)
    if err:
        await interaction.followup.send(err, ephemeral=True)
        return

    # create/update player message
    embed = discord.Embed(title="Playlist queued", description=f"Queued {len(tracks)} tracks from playlist")
    view = PlayerView()
    channel = interaction.channel
    try:
        await ensure_player_message(channel, gid, embed, view)
    except Exception:
        pass

    # start playback if idle
    if not vc.is_playing() and not (getattr(vc, 'is_paused', lambda: False)()):
        await play_next_for_guild(interaction.guild)

    await interaction.followup.send(f'Queued {len(tracks)} tracks.', ephemeral=True)

    embed = discord.Embed(title="Queued", description=f"{info.get('title')}")
    view = PlayerView()
    channel = interaction.channel
    try:
        msg = await ensure_player_message(channel, gid, embed, view)
    except Exception:
        # fallback to followup send
        msg = await interaction.followup.send(embed=embed, view=view)
        now_playing_message[gid] = msg

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    # handle prefix commands using aliases from settings
    if not message.content.startswith(PREFIX):
        return

    parts = message.content[len(PREFIX):].strip().split()
    if not parts:
        return
    cmd = parts[0].lower()
    args = parts[1:]

    # find which internal command this alias maps to
    matched = None
    for internal, aliases in COMMAND_ALIASES.items():
        if cmd in aliases:
            matched = internal
            break

    if not matched:
        return

    # implement a few simple prefix-command handlers
    if matched == 'hello':
        await message.channel.send('Hello!')
    elif matched == 'help':
        available = []
        for k, v in COMMAND_ALIASES.items():
            available.append(f"{PREFIX}{v[0]}")
        await message.channel.send('Available commands: ' + ', '.join(available))
    elif matched == 'play':
        query = ' '.join(args).strip()
        if not query:
            await message.channel.send('Bitte suche nach einem Song oder gib eine URL an.')
            return
        await message.channel.send(f'Queued: {query}')
        info = await extract_track_info(query)
        if not info:
            await message.channel.send('Konnte Track nicht finden.')
            return
        gid = message.guild.id
        queues.setdefault(gid, [])
        queues[gid].append(info)

        # cancel idle disconnect if scheduled
        t = idle_tasks.pop(gid, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass

        # ensure voice connection using message context
        channel = None
        if message.author and getattr(message.author, 'voice', None):
            channel = message.author.voice.channel
        if not channel:
            await message.channel.send('Du musst in einem Voice-Channel sein.')
            return
        vc = message.guild.voice_client
        if not vc or not vc.is_connected():
            try:
                vc = await channel.connect()
                print(f"[voice] Connected to {channel} in guild {message.guild.id}")
            except Exception as e:
                await message.channel.send(f'Fehler beim Joinen des Voice-Channels: {e}')
                return
        # send a player message with controls (store for updates)
        try:
            embed = discord.Embed(title='Queued', description=f"{info.get('title')}")
            msg = await ensure_player_message(message.channel, gid, embed, PlayerView())
        except Exception:
            pass

        if not vc.is_playing() and not (getattr(vc, 'is_paused', lambda: False)()):
            await play_next_for_guild(message.guild)

client.run(BOT_TOKEN)

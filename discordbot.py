import asyncio
import discord
from discord.ext import commands
import os
import traceback
import urllib.parse
import re

prefix = os.getenv('DISCORD_BOT_PREFIX', default='🦑')
lang = os.getenv('DISCORD_BOT_LANG', default='ja')
token = os.environ['DISCORD_BOT_TOKEN']
max_len_text = int(os.getenv('DISCORD_BOT_TEXT_LEN', default=40))

intents = discord.Intents.default()
intents.members = True
client = commands.Bot(command_prefix=prefix, intents=intents)

@client.event
async def on_ready():
    await change_presence()

@client.event
async def on_guild_join(guild):
    await change_presence()

@client.event
async def on_guild_remove(guild):
    await change_presence()

@client.command()
async def c(ctx):
    await delete_command_safety(ctx.message)
    if ctx.author.voice is None:
        await ctx.send('ボイスチャンネルに接続してから呼び出してください。')
        return

    async def voice_connect(ctx):
        try:
            await ctx.author.voice.channel.connect(timeout=5)
        except asyncio.TimeoutError:
            await ctx.send('接続に失敗しました。')

    if ctx.guild.voice_client is None:
        await voice_connect(ctx)
    elif ctx.author.voice.channel != ctx.guild.voice_client.channel:
        await ctx.voice_client.disconnect()
        await asyncio.sleep(0.5)
        await voice_connect(ctx)
    else:
        await ctx.send('接続済みです。')

@client.command()
async def d(ctx):
    await delete_command_safety(ctx.message)
    if ctx.voice_client is None:
        await ctx.send('ボイスチャンネルに接続していません。')
    else:
        await ctx.voice_client.disconnect()

@client.command()
async def conf(ctx, command, *args):
    if command == 'allow':
        await allow(ctx, *args)
    else:
        raise commands.errors.CommandNotFound(f"Command 'conf {command}' is Not Found")
    await delete_command_safety(ctx.message)

async def allow(ctx, *targets):
    guild_data = await fetch_guild_data(ctx.guild)
    minus = False
    message = ""

    if targets[0] == 'show':
        message = "現在のステータスは以下です\n```\n"
        for speaker, toggle in guild_data.speakable_status().items():
            if isinstance(speaker, discord.abc.User) or isinstance(speaker, discord.abc.Role):
                speaker_name = speaker.name
            else:
                speaker_name = speaker
            status = "ok" if toggle else "ng"
            message += f"{speaker_name}: {status}\n"
        message += "```"
        await ctx.send(message)
        return
    
    if targets[0] == 'reset':
        guild_data.reset_speakable()
    else:
        for target in targets:
            if target == '-':
                minus = True
            else:
                if re.match(r'^-', target):
                    target = re.sub(r'^-', '', target)
                    minus = True

                guild_data.set_speakable(target, not minus)
                minus = False
    message = "ステータスを更新しました\n```\n"
    for speaker, toggle in guild_data.speakable_status().items():
        if isinstance(speaker, discord.User) or isinstance(speaker, discord.Role):
            speaker_name = speaker.name
        else:
            speaker_name = speaker
        status = "ok" if toggle else "ng"
        message += f"{speaker_name}: {status}\n"
    message += "```"
    await ctx.send(message)

@client.listen()
async def on_message(message):
    voice_client = message.guild.voice_client
    if voice_client is None:
        return
    if message.author.voice is None or message.author.voice.channel != voice_client.channel:
        return
    if message.author.bot:
        return
    if message.content.startswith(prefix):
        return
    guild_data = await fetch_guild_data(message.guild, refresh=False)
    if not guild_data.is_speakable(message.author):
        return

    text = message.content
    text = text.replace('\n', '、')

    # メンションユーザー名
    while True:
        m = re.search(r'\s*<@!(\d*)>(?:\s+<@!(\d*)>)*\s*', text)
        if m is None:
            break
        member = await voice_client.guild.fetch_member(m.group(1))
        replacement = (member.nick or member.name)[:12] if member else ''
        text = replace_text_by_match(text, m, replacement)
    # URL
    text = re.sub(r'https?://[\w/:%#\$&\?\(\)~\.=\+\-]+', '', text)
    # カスタムスタンプ
    text = re.sub(r'<a?\:([^\:]+)\:\d+>', '\\1、', text)
    # コードブロック
    text = re.sub(r'```(?:`(?!```)|[^`])*```', '、', text)
    text = re.sub(r'`[^`]*`', '、', text)
    # www
    while True:
        m = re.search(r'([wW])+(?=\s|$)|([wW]){3,}', text)
        if m is None:
            break
        text = replace_text_by_match(text, m, "ワラ" * min(len(m.groups()), 1), last_sep="。")

    text = re.sub(r'[、。]{2,}', '、', text)
    text = re.sub(r'\s+', ' ', text)
    if text == '、':
        text = ''

    if len(text) <= 0:
        print('Nothing to read')
    elif len(text) < max_len_text:
        print(f'{text}({len(text)})')
        await speak(voice_client, text)
    else:
        print(f'Cannot read: {text[:max_len_text]}...({len(text)})')
        await message.channel.send(f'{max_len_text}文字以上は読み上げできません。')

@client.event
async def on_voice_state_update(member, before, after):
    if member.id == client.user.id:
        await change_presence()
        return
    if member.bot:
        return

    voice_client = member.guild.voice_client
    if voice_client is None:
        return

    b_channel, vc_channel, a_channel = before.channel, voice_client.channel, after.channel
    if b_channel != vc_channel and a_channel == vc_channel:
        await speak(voice_client, member.name + 'が入室')
    elif b_channel == vc_channel and a_channel != vc_channel:
        if len(voice_client.channel.members) > 1:
            await speak(voice_client, member.name + 'が退室')
        else:
            await asyncio.sleep(0.5)
            await voice_client.disconnect()

@client.listen()
async def on_command_error(ctx, error):
    orig_error = getattr(error, 'original', error)
    print(''.join(traceback.TracebackException.from_exception(orig_error).format()))

    if isinstance(error, commands.errors.CommandNotFound):
        await ctx.send('このコマンドは利用できません')
    else:
        await ctx.send(orig_error)

@client.command()
async def h(ctx):
    await delete_command_safety(ctx.message)
    message = f'''
```
{client.user.name}の使い方
{prefix}c：ボイスチャンネルに接続します。
{prefix}d：ボイスチャンネルから切断します。
{prefix}h：ヘルプを表示します。
```
'''
    await ctx.send(message)


class GuildData:
    def __init__(self, guild):
        self._guild = guild
        self.reset_speakable()

    async def refresh_guild(self):
        async for member in self._guild.fetch_members():
            pass
        await self._guild.fetch_roles()

    def is_speakable(self, user):
        for speaker in [user, *user.roles, "everyone"]:
            speaker_id = self._speaker2id(speaker)
            if speaker_id in self._speakable_ids:
                return self._speakable_ids[speaker_id]
        raise Exception
    
    def set_speakable(self, speaker, toggle=True):
        self._reset_speakable_ids()
        self._speakable[self._speaker2id(speaker)] = toggle

    def speakable_status(self):
        status = {}

        for speaker, toggle in self._speakable.items():
            status[self._id2speaker(speaker)] = toggle
        return status

    def reset_speakable(self):
        self._speakable = { "everyone" : True }
        self._reset_speakable_ids()

    @property
    def _speakable_ids(self):
        if self.___speakable_ids:
            return self.___speakable_ids
        hsh = {}
        for speaker, toggle in self._speakable.items():
            hsh[self._speaker2id(speaker)] = toggle
        self.___speakable_ids = hsh
        return hsh

    ___speakable_ids = None
    def _reset_speakable_ids(self):
        self.___speakable_ids = None

    def _speaker2id(self, speaker):
        if isinstance(speaker, discord.abc.User):
            return f"<@!{speaker.id}>"
        elif isinstance(speaker, discord.abc.Role):
            return f"<@&{speaker.id}>"
        elif isinstance(speaker, str) and re.fullmatch(r"<@[!&](\d*)>", speaker):
            return speaker
        elif speaker in ['all', 'everyone', '@everyone']:
            return 'everyone'
        else:
            raise Exception(f'{speaker} is not valid speaker')

    def _id2speaker(self, speaker_id):
        if isinstance(speaker_id, str):
            m = re.fullmatch(r"<@!(\d*)>", speaker_id)
            if m:
                member = self._guild.get_member(int(m.group(1)))
                if member:
                    return (member.nick or member.name)
            m = re.fullmatch(r"<@&(\d*)>", speaker_id)
            if m:
                role = self._guild.get_role(int(m.group(1)))
                if role:
                    return role
        
        if isinstance(speaker_id, discord.abc.User) or isinstance(speaker_id, discord.abc.Role):
            return speaker_id
        elif speaker_id in ['all', 'everyone', '@everyone']:
            return 'everyone'
        else:
            raise Exception(f'{speaker_id} is not valid speaker_id')

guild_datas = {}
async def fetch_guild_data(guild, refresh=True):
    if not guild.id in guild_datas:
        guild_datas[guild.id] = GuildData(guild)
    if refresh:
        await guild_datas[guild.id].refresh_guild()
    return guild_datas[guild.id]

async def delete_command_safety(message):
    try:
        await message.delete()
    except discord.errors.DiscordException as e:
        print(''.join(traceback.TracebackException.from_exception(e).format()))

async def change_presence():
    presence = f'{prefix}h | {len(client.voice_clients)}/{len(client.guilds)}サーバー'
    await client.change_presence(activity=discord.Game(name=presence))

async def speak(voice_client, text, volume=0.8):
    s_quote = urllib.parse.quote(text)
    mp3url = f'http://translate.google.com/translate_tts?ie=UTF-8&q={s_quote}&tl={lang}&client=tw-ob'
    while voice_client.is_playing():
        await asyncio.sleep(0.5)
    voice_client.play(discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(mp3url), volume=volume))

def replace_text_by_match(text, match, replacement, first_sep="、", last_sep="、"):
    first, last = text[:match.start()], text[match.end():]
    return first + (first_sep if first else '') + replacement + (last_sep if last else '') + last


client.run(token)

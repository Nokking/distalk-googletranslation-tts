import asyncio
import functools
import itertools
import math
import random
import static_ffmpeg
import discord
from discord.ext import commands
import os
import traceback
import urllib.parse
import re
from server import keep_alive

# # You must include this line for it to work

# discord.opus.load_opus("./libopus.so.0.8.0")

# ffmpeg installed on first call to add_paths(), threadsafe.
static_ffmpeg.add_paths()  # blocks until files are downloaded
prefix = os.getenv('DISCORD_BOT_PREFIX', default='🦑')
lang = os.getenv('DISCORD_BOT_LANG', default='ja')
botname = os.getenv('DISCORD_BOT_NAME', default='Bot')
token = os.environ['DISCORD_BOT_TOKEN']
max_len_text = int(os.getenv('DISCORD_BOT_TEXT_LEN', default=40))

intents = discord.Intents.all()
intents.members = True
intents.messages = True
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
    await asyncio.sleep(1.0)
    await speak(ctx.guild.voice_client, f'{botname}が入室しました。')
  elif ctx.author.voice.channel != ctx.guild.voice_client.channel:
    await ctx.voice_client.disconnect()
    await asyncio.sleep(0.5)
    await voice_connect(ctx)
    await asyncio.sleep(1.0)
    await speak(ctx.guild.voice_client, f'{botname}が入室しました。')
  else:
    await ctx.send('接続済みです。')


@client.command()
async def d(ctx):
  await delete_command_safety(ctx.message)
  if ctx.voice_client is None:
    await ctx.send('ボイスチャンネルに接続していません。')
  else:
    await speak(ctx.guild.voice_client, f'{botname}を終了します。')
    await asyncio.sleep(3.5)
    await ctx.voice_client.disconnect()


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

  text = message.content
  text = text.replace('\n', '、')

  # メンションユーザー名
  while True:
    m = re.search(r'<@!?(\d+)>', text)
    if m is None:
      break
    member = await voice_client.guild.fetch_member(m.group(1))
    replacement = (member.nick or member.name)[:12] if member else ''
    text = replace_text_by_match(text, m, replacement)
  # URL
  text = re.sub(r'https?://[\w/:%#,\$&\?\(\)~\.=\+\-]+', '', text)
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
    text = replace_text_by_match(text,
                                 m,
                                 "ワラ" * min(len(m.groups()), 1),
                                 last_sep="。")

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
  error_msg = ''.join(
    traceback.TracebackException.from_exception(orig_error).format())
  await ctx.send(error_msg)


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


async def delete_command_safety(message):
  try:
    await message.delete()
  except discord.errors.DiscordException as e:
    print(''.join(traceback.TracebackException.from_exception(e).format()))


async def change_presence():
  presence = f'接続 {prefix}c 切断 {prefix}d | ヘルプ{prefix}h 稼働{len(client.voice_clients)}/{len(client.guilds)}サーバー'
  await client.change_presence(activity=discord.Game(name=presence))


async def speak(voice_client, text, volume=0.8):
  s_quote = urllib.parse.quote(text)
  mp3url = f'http://translate.google.com/translate_tts?ie=UTF-8&q={s_quote}&tl={lang}&client=tw-ob'
  while voice_client.is_playing():
    await asyncio.sleep(0.5)
  voice_client.play(
    discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(mp3url),
                                 volume=volume))


def replace_text_by_match(text,
                          match,
                          replacement,
                          first_sep="、",
                          last_sep="、"):
  first, last = text[:match.start()], text[match.end():]
  return first + (first_sep if first else '') + replacement + (last_sep if last
                                                               else '') + last


# ウェブサーバーを起動する
keep_alive()

client.run(token)

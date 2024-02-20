import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv('DISCORD_BOT_TOKEN')

intents = discord.Intents.default() 
intents.message_content = True 

bot = commands.Bot(command_prefix="/", intents=intents)

user_keywords = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    for user_id, keywords in user_keywords.items():
        if any(keyword.lower() in message.content.lower() for keyword in keywords):
            user = await bot.fetch_user(user_id)
            if user:
                await user.send(f'Keyword found in message: "{message.content}"\nChannel: {message.channel.name}')
    await bot.process_commands(message)

@bot.command(name='add')
async def add_keyword(ctx, *, keyword):
    user_id = ctx.author.id
    if user_id not in user_keywords:
        user_keywords[user_id] = set()
    user_keywords[user_id].add(keyword)
    await ctx.send(f'Keyword "{keyword}" added to your notifications list! You will now receive alerts whenever "{keyword}" is mentioned.')

@bot.command(name='remove')
async def remove_keyword(ctx, *, keyword):
    user_id = ctx.author.id
    if user_id in user_keywords and keyword in user_keywords[user_id]:
        user_keywords[user_id].remove(keyword)
        await ctx.send(f'Keyword "{keyword}" removed from your notifications list.')
    else:
        await ctx.send('Keyword not found in your notifications list.')

@bot.command(name='list')
async def list_keywords(ctx):
    user_id = ctx.author.id
    if user_id in user_keywords and user_keywords[user_id]:
        keywords = ', '.join(user_keywords[user_id])
        await ctx.send(f'Your tracked keywords: {keywords}')
    else:
        await ctx.send('You are not tracking any keywords.')

@bot.command(name='listhelp')
async def show_help(ctx):
    help_text = ('/add <keyword> - Add a keyword to track\n'
                 '/remove <keyword> - Remove a keyword to track\n'
                 '/list - List all keywords you are tracking\n'
                 '/summarize #channel-name - Summarize messages in a channel\n'
                 '/bookmark username - Bookmark messages from a specific user\n'
                 '/remove bookmark - Stop bookmarking messages from specific users\n'
                 # add alarm commands later on 
                 'Use /bothelp to view this message again.')
    await ctx.send(help_text)

bot.run(token)

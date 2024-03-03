import discord
from discord.ext import commands
import asyncio
import os
from dotenv import load_dotenv
import dateparser
from datetime import datetime, timezone
import pytz
import openai
import pymongo
from pymongo import MongoClient

# set timezone to PST for alarm functionality
pacific_tz = pytz.timezone('America/Los_Angeles')

# loading our environment variables
load_dotenv()
token = os.getenv('DISCORD_BOT_TOKEN')
openai.api_key = os.getenv("OPENAI_API_KEY")

# configure bot intents and instance
intents = discord.Intents.default() 
intents.message_content = True 
bot = commands.Bot(command_prefix="/", intents=intents)

# temporary storages
user_keywords = {}
user_reminders = {}

mongo_url = "mongodb+srv://sathshr:<password>@prioritizebotcluster.qn8j3o2.mongodb.net/"
# navigating to cluster
cluster = MongoClient(mongo_url)
# connecting to database
db = cluster["prioritize_bot"]
# connecting to collection
collection = db["keywords"]

@bot.event
async def on_ready():
    """Indicates that the bot has successfully connected and online on Discord!"""
    print(f'Logged in as {bot.user.name}')
    bot.loop.create_task(reminder_task())

@bot.event
async def on_message(message):
    """
    Handles our incoming messages and checks them for user-specified keywords ;)
    
    :param message: discord.Message object which represents the received message.
    """
    if message.author == bot.user:
        return
    for user_id, keywords in user_keywords.items():
        if any(keyword.lower() in message.content.lower() for keyword in keywords):
            user = await bot.fetch_user(user_id)
            if user:
                await user.send(f'Keyword found in message: "{message.content}"\nChannel: {message.channel.name}')
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    """Sends a welcome message to new users introducing them to the bot's features.

    :param member: The member who just joined the server.
    """
    welcome_text = (
        f"Welcome to the server, {member.mention}! I'm Prioritize Bot, here to make your experience better!! 🎉\n\n"
        "Here's what I can do for you:\n\n"
        "• `/add <keyword>` - Get notified for mentions of specific keywords.\n"
        "• `/remove <keyword>` - Stop notifications for a keyword.\n"
        "• `/list` - View all keywords you're tracking.\n"
        "• `/summarize #channel-name` - Summarize messages in a channel.\n"
        "• `/bookmark @username` - Bookmark messages from a specific user.\n"
        "• `/remove bookmark` - Stop bookmarking messages from specific users.\n"
        "• `/alarm_add \"time\" \"label\"` - Add a reminder for a specific time with a label.\n"
        "• `/remove_reminder \"label\"` - Remove a reminder by its label.\n"
        "• `/showhelp` - Show this help message again."
    )
    try:
        # send the welcome message to the new member's DM!
        await member.send(welcome_text)
    except discord.Forbidden:
        # in case the bot cannot send DMs to the user, send the message to a public channel (currently setting it to general)
        general_channel = discord.utils.get(member.guild.channels, name='general')
        if general_channel:
            await general_channel.send(f"{member.mention}, welcome! Please check your DMs for more information on how to use me.")

@bot.command(name='add')
async def add_keyword(ctx, *, keyword):
    """Allows a user to add a keyword to their tracking list.

    When a message containing this keyword is detected, the bot sends a notification to the user through
    private messages.

    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :param keyword: The keyword that the user wants to track.
    :return: None. It''ll send a confirmation message to the user's channel.
    """
    user_id = ctx.author.id
    if user_id not in user_keywords:
        user_keywords[user_id] = set()
    user_keywords[user_id].add(keyword)
    await ctx.send(f'Keyword "{keyword}" added to your notifications list! You will now receive alerts whenever "{keyword}" is mentioned.')

@bot.command(name='remove')
async def remove_keyword(ctx, *, keyword):
    """Allows a user to remove a keyword from their personal tracking list.

    Stops the bot from sending notifications to the user for messages containing this keyword.

    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :param keyword: The keyword that the user wants to stop tracking.
    :return: None. It sends a confirmation or error message to the user's channel.
    """
    user_id = ctx.author.id
    if user_id in user_keywords and keyword in user_keywords[user_id]:
        user_keywords[user_id].remove(keyword)
        await ctx.send(f'Keyword "{keyword}" removed from your notifications list.')
    else:
        await ctx.send('Keyword not found in your notifications list.')

@bot.command(name='list')
async def list_keywords(ctx):
    """Lists all the keywords a user is currently tracking.

    :param ctx: Discord bot commands represents the "context" of the command. 
            It basically provides the details about the message, channel, server, and user
            that "invoked" the command.
    :return: None. Just sends a message to the user's channel with all their tracked keywords.
    """
    user_id = ctx.author.id
    if user_id in user_keywords and user_keywords[user_id]:
        keywords = ', '.join(user_keywords[user_id])
        await ctx.send(f'Your tracked keywords: {keywords}')
    else:
        await ctx.send('You are not tracking any keywords.')

@bot.command(name='showhelp')
async def show_help(ctx):
    """Displays a help message listing all available bot commands and their descriptions.

    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :return: None. Just sends a help message to the user's channel.
    """
    help_text = (
        "Need help? Here's what I can do for you:\n\n"
        "• `/add <keyword>` - Get notified for mentions of specific keywords.\n"
        "• `/remove <keyword>` - Stop notifications for a keyword.\n"
        "• `/list` - View all keywords you're tracking.\n"
        "• `/summarize #channel-name` - Summarize messages in a channel.\n"
        "• `/bookmark @username` - Bookmark messages from a specific user.\n"
        "• `/remove bookmark` - Stop bookmarking messages from specific users.\n"
        "• `/alarm_add \"time\" \"label\"` - Add a reminder for a specific time with a label.\n"
        "• `/remove_reminder \"label\"` - Remove a reminder by its label.\n"
        "• `/list_reminders` - List reminders by its timestamp and label.\n"
        "• `/showhelp` - Show this help message again."
    )
    await ctx.send(help_text)

@bot.command(name='alarm_add')
async def add_reminder(ctx, time, *, label):
    """Adds a reminder for the user at a specified time with a given label.

    We parse the provided time in PST and schedule a reminder!
    When the time arrives, we sends a message to the user with the reminder's label.
    User's can use the label to describe what the reminder will contain.

    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :param time: A string representing the time when the reminder should be sent. 
    :param label: The label or message associated with the reminder.
    :return: None. Just sends a confirmation message to the invoking channel about the scheduled reminder.
    """
    reminder_time = dateparser.parse(time, settings={'TIMEZONE': 'America/Los_Angeles'})
    if reminder_time is None:
        await ctx.send('Invalid time format. Please try again.')
        return
    reminder_time = reminder_time.astimezone(pacific_tz)
    if ctx.author.id not in user_reminders:
        user_reminders[ctx.author.id] = []
    user_reminders[ctx.author.id].append((reminder_time, label))
    reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M:%S %Z')
    await ctx.send(f'Reminder set for {reminder_time_str} with label "{label}".')

@bot.command(name='remove_reminder')
async def remove_reminder(ctx, label):
    """Removes a previously set reminder by its label.

    This allows users to cancel reminders that they don't want anymore.

    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :param label: The label of the reminder to remove.
    :return: None. Just sends a confirmation or error message to the user's channel.
    """
    if ctx.author.id in user_reminders:
        reminders_to_keep = []
        for reminder in user_reminders[ctx.author.id]:
            if reminder[1] != label:
                reminders_to_keep.append(reminder)
        user_reminders[ctx.author.id] = reminders_to_keep
        await ctx.send(f'Reminder with label "{label}" removed.')
    else:
        await ctx.send('No such reminder found.')

async def reminder_task():
    """This is our background task that checks for and sends our reminders every minute.

    This task runs indefinitely once the bot is ready, checking if there are any reminders
    set for the current time or earlier, and then sends them to the appropriate users via private messages.

    :return: None. It just sends reminders directly to users :D
    """
    while True:
        now = datetime.now(pacific_tz)
        for user_id, reminders in list(user_reminders.items()):
            reminders_to_send = []
            for reminder_time, label in reminders:
                if reminder_time <= now:
                    reminders_to_send.append((reminder_time, label))
            
            for reminder_time, label in reminders_to_send:
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f'Reminder: {label}')
                user_reminders[user_id].remove((reminder_time, label))
        await asyncio.sleep(60)

@bot.command(name='list_reminders')
async def list_reminders(ctx):
    """Lists all the reminders set by the requesting user.

    This provides users with an overview of all their upcoming reminders.
    
    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :return: None. It just sends a message to the user's channel with all their upcoming reminders.
    """
    user_id = ctx.author.id
    if user_id in user_reminders and user_reminders[user_id]:
        reminders_list = []
        for reminder_time, label in user_reminders[user_id]:
            reminder_time_pt = reminder_time.astimezone(pacific_tz)
            reminder_time_str = reminder_time_pt.strftime('%Y-%m-%d %H:%M:%S %Z') # testing pst format because idk utc
            reminders_list.append(f'{reminder_time_str}: {label}')
        reminders_text = '\n'.join(reminders_list)
        await ctx.send(f'Your reminders:\n{reminders_text}')
    else:
        await ctx.send('You have no reminders set.')

@bot.command(name='summarize')
async def summarize(ctx, channel: discord.TextChannel, num_messages: int = 100):
    """
    Summarizes the last 100 messages in the specified channel.

    :param ctx: The context under which the command is executed.
    :param channel: The target channel to summarize messages from.
    :param num_messages: The number of messages to fetch and summarize (default is 5).
    """
    if not channel:
        await ctx.send("Channel not found.")
        return

    # fetch last 100 messages from the channel
    messages = await channel.history(limit=num_messages).flatten()
    
    text = ""
    for message in messages:
        text += message.content + "\n"

    # use OpenAI API to summarize the messages
    response = openai.Completion.create(
        engine="davinci", # this is not working :(
        prompt=f"Summarize the following messages:\n\n{text}",
        temperature=0.7,
        max_tokens=150,
        top_p=1.0,
        frequency_penalty=0.0,
        presence_penalty=0.0
    )

    summary = response.choices[0].text.strip()
    await ctx.send(f"Summary of the last {num_messages} messages in {channel.mention}:\n\n{summary}")

bot.run(token)

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

mongo_url = ""
# navigating to cluster
cluster = MongoClient(mongo_url)
# connecting to database
db = cluster["prioritize_bot"]
# connecting to collection
collection = db["keywords"]

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')
    bot.loop.create_task(reminder_task())
    global user_keywords
    user_keywords.clear()
    for doc in collection.find({}):
        user_keywords[doc["user_id"]] = set(doc["keywords"])

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
    user_id = str(ctx.author.id)
    # Check if the user already has keywords stored
    user_doc = collection.find_one({"user_id": user_id})
    if user_doc:
        # If the user exists, add the new keyword to their list (if it's not already there!)
        if keyword not in user_doc['keywords']:
            collection.update_one({"user_id": user_id}, {"$push": {"keywords": keyword}})
            await ctx.send(f'Keyword "{keyword}" added to your notifications list!')
        else:
            await ctx.send(f'Keyword "{keyword}" is already in your notifications list.')
    else:
        # If the user doesn't exist, create a new document for them
        collection.insert_one({"user_id": user_id, "keywords": [keyword]})
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
    user_id = str(ctx.author.id)
    result = collection.find_one_and_update(
        {"user_id": user_id},
        {"$pull": {"keywords": keyword}},
        return_document=pymongo.ReturnDocument.AFTER
    )
    if result and keyword in result.get('keywords', []):
        await ctx.send(f'Keyword "{keyword}" was not found in your notifications list.')
    else:
        await ctx.send(f'Keyword "{keyword}" removed from your notifications list.')

@bot.command(name='list')
async def list_keywords(ctx):
    """Lists all the keywords a user is currently tracking.

    :param ctx: Discord bot commands represents the "context" of the command. 
            It basically provides the details about the message, channel, server, and user
            that "invoked" the command.
    :return: None. Just sends a message to the user's channel with all their tracked keywords.
    """
    user_id = str(ctx.author.id)

    user_doc = collection.find_one({"user_id": user_id})

    if user_doc and user_doc.get("keywords"):
        keywords = ', '.join(user_doc["keywords"])
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

@bot.command(name='add_reminder')
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
    user_id = str(ctx.author.id)
    reminders_collection = db["reminders"]
    reminders_collection.insert_one({
        "user_id": user_id,
        "reminder_time": reminder_time,
        "label": label
    })
    await ctx.send(f'Reminder set for {reminder_time.strftime("%Y-%m-%d %H:%M:%S %Z")} with label "{label}".')

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
    user_id = str(ctx.author.id)
    reminders_collection = db["reminders"]
    result = reminders_collection.delete_one({"user_id": user_id, "label": label})
    if result.deleted_count > 0:
        await ctx.send(f'Reminder with label "{label}" removed.')
    else:
        await ctx.send('No such reminder found.')

async def reminder_task():
    """This is our background task that checks for and sends our reminders every minute.

    This task runs indefinitely once the bot is ready, checking if there are any reminders
    set for the current time or earlier, and then sends them to the appropriate users via private messages.

    :return: None. It just sends reminders directly to users :D
    """
    reminders_collection = db["reminders"]
    while True:
        now = datetime.now(pacific_tz)
        due_reminders = reminders_collection.find({"reminder_time": {"$lte": now}})
        
        for reminder in due_reminders:
            user_id = reminder["user_id"]
            label = reminder["label"]
            user = await bot.fetch_user(int(user_id))
            if user:
                await user.send(f'Reminder: {label}')
                reminders_collection.delete_one({"_id": reminder["_id"]})
        
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
    user_id = str(ctx.author.id)
    reminders_collection = db["reminders"]
    user_reminders = reminders_collection.find({"user_id": user_id})
    
    reminders_list = []
    for reminder in user_reminders: 
        reminder_time = reminder["reminder_time"].astimezone(pacific_tz)
        label = reminder["label"]
        reminder_time_str = reminder_time.strftime('%Y-%m-%d %H:%M:%S %Z')
        reminders_list.append(f'{reminder_time_str}: {label}')
    
    if reminders_list:
        reminders_text = '\n'.join(reminders_list)
        await ctx.send(f'Your reminders:\n{reminders_text}')
    else:
        await ctx.send('You have no reminders set.')

@bot.command(name='summarize')
async def summarize(ctx, channel: discord.TextChannel, num_messages: int = 50):
    """
    Summarizes the specified number of the latest messages in the given channel.

    :param ctx: The context under which the command is executed.
    :param channel: The Discord TextChannel to summarize messages from.
    :param num_messages: The number of messages to fetch and summarize. Defaults to 50 if not specified.
    """
    if not channel:
        await ctx.send("Channel not found.")
        return

    messages = []
    async for message in channel.history(limit=num_messages):
        messages.append(message.content)

    text = " ".join(messages)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Summarize the following messages:"},
                {"role": "user", "content": text}
            ],
            temperature=0.5,
            max_tokens=1024,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )
        summary = response.choices[0].message['content']
        await ctx.send(f"Summary of the last {num_messages} messages in {channel.mention}:\n\n{summary}")
    except Exception as e:
        await ctx.send(f"Error summarizing messages: {str(e)}")


@bot.command(name='add_bookmark')
async def add_bookmark(ctx, user: discord.Member):

    """Allows a user to add a bookmark to keep track of messages from a specific mentioned user.

    When a message is sent from this user, the bot sends a notification to the user through
    private messages.

    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :param user:discord.Member: The mentioned user to add a bookmark for.
    :return: None. It'll send a confirmation message to the user's channel.
    """

    user_id = str(ctx.author.id)
    # user ID of mentioned user to bookmark
    user_id_bookmark = str(user.id)

    bookmarks_collection = db["bookmarks"]

    try:
        # If the user exists, add the new bookmark to their list (if it's not already there!)
        user_doc = bookmarks_collection.find_one({"user_id": user_id})

        if user_doc:
            # If the mentioned user is not bookmarked, add new bookmark to document
            if user_id_bookmark not in user_doc.get('bookmarks', []):
                bookmarks_collection.update_one(
                    {"user_id": user_id},
                    {"$push": {"bookmarks": user_id_bookmark}}
                )
                await ctx.send(f'{user.display_name} has been added to your bookmarks!')
            else:
                # If the mentioned user is already bookmarked
                await ctx.send(f'{user.display_name} is already in your bookmarks.')
        else:
            # If the user doesn't exist, create a new document for them
            bookmarks_collection.insert_one({"user_id": user_id, "bookmarks": [user_id_bookmark]})
            await ctx.send(f'{user.display_name} is added to your bookmarks! You will receive notifications when {user.display_name} sends messages.')

    except Exception as e:
        print(f"Error adding a bookmark: {e}")
        await ctx.send("An error occurred while adding a new bookmark.")

@bot.command(name='list_bookmarks')
async def list_bookmarks(ctx):
    """Lists all the bookmarks for the user.

    :param ctx: Discord bot commands represents the "context" of the command.
    :return: None. It sends a message to the user's channel with all their bookmarks.
    """
    user_id = str(ctx.author.id)
    
    bookmarks_collection = db["bookmarks"]

    try:
        # Retrieve the user's bookmarks
        user_bookmarks = bookmarks_collection.find_one({"user_id": user_id})

        if user_bookmarks:
            bookmarks_list = user_bookmarks.get("bookmarks", [])
            if bookmarks_list:
                # Convert user IDs to mention strings
                bookmark_mentions = [f"<@{bookmark}>" for bookmark in bookmarks_list]
                bookmarks_text = '\n'.join(bookmark_mentions)
                await ctx.send(f'Your bookmarks:\n{bookmarks_text}')
            else:
                await ctx.send('You do not have any bookmarks.')
        else:
            await ctx.send('You do not have any bookmarks.')

    except Exception as e:
        print(f"Error listing bookmarks: {e}")
        await ctx.send("An error occurred while listing bookmarks.")


bot.run(token)
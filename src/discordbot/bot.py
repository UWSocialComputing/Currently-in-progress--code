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
mongo_url = os.getenv('MONGODB_URL')

# configure bot intents and instance
intents = discord.Intents.default() 
intents.message_content = True 
bot = commands.Bot(command_prefix="/", intents=intents)

# temporary storages
user_keywords = {}
user_bookmarks = {}
user_reminders = {}
user_private_channels = {}

# navigating to cluster
cluster = MongoClient(mongo_url)
# connecting to database
db = cluster["prioritize_bot"]
# connecting to collection
keyword_collection = db["keywords"]
bookmarks_collection = db["bookmarks"]
reminders_collection = db["reminders"]
private_channels_collection = db["private_channels"]

@bot.event
async def on_ready():
    """
    Initializes bot, clearing any existing user-specific data and repopulating it from the database.
    This includes user keywords, bookmarks, reminders, and now private channels, so that our bot starts with the current data
    when logging in.
    """
    print(f'Logged in as {bot.user.name}')
    bot.loop.create_task(reminder_task())
    global user_keywords, user_bookmarks, user_reminders, user_private_channels
    user_keywords.clear()
    user_bookmarks.clear()
    user_reminders.clear()
    user_private_channels.clear() 
    for doc in keyword_collection.find({}):
        user_keywords[doc["user_id"]] = set(doc["keywords"])
    for doc in bookmarks_collection.find({}): 
        user_bookmarks[doc["user_id"]] = set(doc.get("bookmarks", []))
    for doc in db["reminders"].find({}):
        user_reminders[doc["user_id"]] = doc.get("reminders", [])
    for doc in db["private_channels"].find({}):
        user_private_channels[doc["user_id"]] = doc["channel_id"]

@bot.command(name='create_private_channel')
async def create_private_channel(ctx):
    guild = ctx.guild
    member = ctx.author

    if str(member.id) in user_private_channels:
        await ctx.send(f"{member.mention}, you already have a private channel.")
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        member: discord.PermissionOverwrite(read_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True)
    }

    channel_name = f"private-{member.display_name}"
    private_channel = await guild.create_text_channel(channel_name, overwrites=overwrites)

    private_channels_collection.insert_one({
        "user_id": str(member.id),
        "channel_id": str(private_channel.id)
    })

    user_private_channels[str(member.id)] = str(private_channel.id)

    await ctx.send(f"{member.mention}, your private channel has been created!")
    await private_channel.send(f"Welcome, {member.mention}! This is your private channel with me.")
    embed = discord.Embed(title=f"Welcome to your private channel, {member.display_name}!", description="Here's what I can do for you:", color=discord.Color.purple())
    embed.add_field(name="**☀️ Getting started**", value="", inline=False)
    embed.add_field(name="**`/onboard_user`**", value="- Enter this command for guidance on how to get set up with the bot!", inline=False)
    embed.add_field(name="**`/create_private_channel`**", value="- Creates a private channel so you can interact with the bot.", inline=False)
    embed.add_field(name="**🔑 Keyword Features**", value="", inline=False)
    embed.add_field(name="**`/add <keyword>`**\n", value="- Get notified for mentions of specific keywords.\n", inline=False)
    embed.add_field(name="**`/remove <keyword>`**\n", value="- Stop notifications for a keyword.\n", inline=False)
    embed.add_field(name="**`/list`**", value="- View all keywords you're tracking.\n", inline=False)
    embed.add_field(name="**🔖 Bookmark Features**", value="", inline=False)
    embed.add_field(name="**`/bookmark <discord_username>`**", value="- Bookmark messages from a specific user.\n", inline=False)
    embed.add_field(name="**`/remove_bookmark <discord_username>`**", value="- Stop bookmarking messages from specific users.\n", inline=False)
    embed.add_field(name="**`/list_bookmarks`**", value="- Lists all the bookmarked users for the user.\n", inline=False)
    embed.add_field(name="**♻️ Summarize Feature**", value="", inline=False)
    embed.add_field(name="**`/summarize #channel-name <# of messages>`**", value="- Summarize messages in a channel.\n", inline=False)
    embed.add_field(name="**🔔 Reminder Features**", value="", inline=False)
    embed.add_field(name="**`/add_reminder \"time\" \"label\"`**", value="- Add a reminder for a specific time with a label.\n", inline=False)
    embed.add_field(name="**`/remove_reminder \"label\"`**", value="- Remove a reminder by its label.\n", inline=False)
    embed.add_field(name="**`/list_reminders`**", value="- List reminders by its timestamp and label.\n", inline=False)
    embed.add_field(name="**❓ Need Help?**", value="", inline=False)
    embed.add_field(name="**`/showhelp`**", value="- Show this help message again.", inline=False)
    embed.add_field(name="**`/examples`**", value="- Displays example commands you can enter.", inline=False)
    # send the welcome message to the new member's DM!
    await private_channel.send(embed = embed)


@bot.event
async def on_message(message):
    """
    Handles our incoming messages and checks them for user-specified keywords ;)
    
    :param message: discord.Message object which represents the received message.
    """
    if message.author == bot.user:
        return
    
    # Keyword notification
    for user_id, keywords in user_keywords.items():
        for keyword in keywords:
            if keyword.lower() in message.content.lower():
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f'Keyword "{keyword}" found in message from {message.author.display_name}: "{message.content}"\nChannel: {message.channel.name}')
                    print(f"Keyword '{keyword}' message sent to {user.name}'s DM")
    
    # Bookmark notification
    for user_id, bookmarks in user_bookmarks.items():
        for bookmark in bookmarks:
            if str(message.author.id) == bookmark:
                user = await bot.fetch_user(user_id)
                if user:
                    await user.send(f'Bookmark notification from {message.author.display_name}:\n{message.content}')
                    print("Bookmark message sent to dm")
    
    await bot.process_commands(message)

@bot.event
async def on_member_join(member):
    """Sends a welcome message to new users introducing them to the bot's features.

    :param member: The member who just joined the server.
    """
    embed = discord.Embed(title=f"Welcome to the server, {member.mention}! I'm Prioritize Bot, here to make your experience better!! 🎉\n\n", description="Here's what I can do for you:\n\n", color=discord.Color.purple())
    embed.add_field(name="**☀️ Getting started**", value="", inline=False)
    embed.add_field(name="**`/onboard_user`**", value="- Enter this command for guidance on how to get set up with the bot!", inline=False)
    embed.add_field(name="**`/create_private_channel`**", value="- Creates a private channel so you can interact with the bot.", inline=False)
    embed.add_field(name="**🔑 Keyword Features**", value="", inline=False)
    embed.add_field(name="**`/add <keyword>`**\n", value="- Get notified for mentions of specific keywords.\n", inline=False)
    embed.add_field(name="**`/remove <keyword>`**\n", value="- Stop notifications for a keyword.\n", inline=False)
    embed.add_field(name="**`/list`**", value="- View all keywords you're tracking.\n", inline=False)
    embed.add_field(name="**🔖 Bookmark Features**", value="", inline=False)
    embed.add_field(name="**`/bookmark <discord_username>`**", value="- Bookmark messages from a specific user.\n", inline=False)
    embed.add_field(name="**`/remove_bookmark <discord_username>`**", value="- Stop bookmarking messages from specific users.\n", inline=False)
    embed.add_field(name="**`/list_bookmarks`**", value="- Lists all the bookmarked users for the user.\n", inline=False)
    embed.add_field(name="**♻️ Summarize Feature**", value="", inline=False)
    embed.add_field(name="**`/summarize #channel-name <# of messages>`**", value="- Summarize messages in a channel.\n", inline=False)
    embed.add_field(name="**🔔 Reminder Features**", value="", inline=False)
    embed.add_field(name="**`/add_reminder \"time\" \"label\"`**", value="- Add a reminder for a specific time with a label.\n", inline=False)
    embed.add_field(name="**`/remove_reminder \"label\"`**", value="- Remove a reminder by its label.\n", inline=False)
    embed.add_field(name="**`/list_reminders`**", value="- List reminders by its timestamp and label.\n", inline=False)
    embed.add_field(name="**❓ Need Help?**", value="", inline=False)
    embed.add_field(name="**`/showhelp`**", value="- Show this help message again.", inline=False)
    embed.add_field(name="**`/examples`**", value="- Displays example commands you can enter.", inline=False)

    try:
        # send the welcome message to the new member's DM!
        await member.send(embed = embed)
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
    user_doc = keyword_collection.find_one({"user_id": user_id})
    if user_doc:
        # If the user exists, add the new keyword to their list (if it's not already there!)
        if keyword not in user_doc['keywords']:
            keyword_collection.update_one({"user_id": user_id}, {"$push": {"keywords": keyword}})
            await ctx.send(f'Keyword "{keyword}" added to your notifications list!')
        else:
            await ctx.send(f'Keyword "{keyword}" is already in your notifications list.')
    else:
        # If the user doesn't exist, create a new document for them
        keyword_collection.insert_one({"user_id": user_id, "keywords": [keyword]})
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
    result = keyword_collection.find_one_and_update(
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

    user_doc = keyword_collection.find_one({"user_id": user_id})

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
    user = ctx.author
    embed = discord.Embed(title=f"Welcome to the server, {user.display_name}! I'm Prioritize Bot, here to make your experience better!! 🎉\n\n", description="Here's what I can do for you:\n\n", color=discord.Color.purple())
    embed.add_field(name="**☀️ Getting started**", value="", inline=False)
    embed.add_field(name="**`/onboard_user`**", value="- Enter this command for guidance on how to get set up with the bot!", inline=False)
    embed.add_field(name="**`/create_private_channel`**", value="- Creates a private channel so you can interact with the bot.", inline=False)
    embed.add_field(name="**🔑 Keyword Features**", value="", inline=False)
    embed.add_field(name="**`/add <keyword>`**\n", value="- Get notified for mentions of specific keywords.\n", inline=False)
    embed.add_field(name="**`/remove <keyword>`**\n", value="- Stop notifications for a keyword.\n", inline=False)
    embed.add_field(name="**`/list`**", value="- View all keywords you're tracking.\n", inline=False)
    embed.add_field(name="**🔖 Bookmark Features**", value="", inline=False)
    embed.add_field(name="**`/bookmark <discord_username>`**", value="- Bookmark messages from a specific user.\n", inline=False)
    embed.add_field(name="**`/remove_bookmark <discord_username>`**", value="- Stop bookmarking messages from specific users.\n", inline=False)
    embed.add_field(name="**`/list_bookmarks`**", value="- Lists all the bookmarked users for the user.\n", inline=False)
    embed.add_field(name="**♻️ Summarize Feature**", value="", inline=False)
    embed.add_field(name="**`/summarize #channel-name <# of messages>`**", value="- Summarize messages in a channel.\n", inline=False)
    embed.add_field(name="**🔔 Reminder Features**", value="", inline=False)
    embed.add_field(name="**`/add_reminder \"time\" \"label\"`**", value="- Add a reminder for a specific time with a label.\n", inline=False)
    embed.add_field(name="**`/remove_reminder \"label\"`**", value="- Remove a reminder by its label.\n", inline=False)
    embed.add_field(name="**`/list_reminders`**", value="- List reminders by its timestamp and label.\n", inline=False)
    embed.add_field(name="**❓ Need Help?**", value="", inline=False)
    embed.add_field(name="**`/showhelp`**", value="- Show this help message again.", inline=False)
    embed.add_field(name="**`/examples`**", value="- Displays example commands you can enter.", inline=False)

    await ctx.send(embed = embed)

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
    
    # Check if the reminder label already exists for the user
    existing_reminder = reminders_collection.find_one({"user_id": user_id, "label": label})
    if existing_reminder:
        await ctx.send('You already have a reminder with this label.')
        return
    
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

@bot.command(name='bookmark')
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
            await ctx.send(f'{user.mention} is added to your bookmarks! You will receive notifications when {user.mention} sends messages.')

    except Exception as e:
        print(f"Error adding a bookmark: {e}")
        await ctx.send("An error occurred while adding a new bookmark.")

@bot.command(name='remove_bookmark')
async def remove_bookmark(ctx, user: discord.Member):
    """Allows a user to remove a bookmark from their bookmarks.

    Stops the bot from sending notifications to the user for messages from bookmarked user.

    :param ctx: Discord bot commands represents the "context" of the command. 
                It basically provides the details about the message, channel, server, and user
                that "invoked" the command.
    :param user:discord.Member: The mentioned user to add a bookmark for.
    :return: None. It sends a confirmation or error message to the user's channel.
    """
    user_id = str(ctx.author.id)
    # user ID of mentioned user to bookmark
    user_id_bookmark = str(user.id)

    try:
        # Remove user bookmark from list of bookmarks
        result = bookmarks_collection.update_one(
            {"user_id": user_id},
            {"$pull": {"bookmarks": user_id_bookmark}}
        )
        
        # Successfully removed user bookmark
        if result.modified_count > 0:
            await ctx.send(f'{user.mention} has been removed from your bookmarks.')
        else:
            await ctx.send('No such bookmark found.')
    except Exception as e:
        print(f"Error removing a bookmark: {e}")

@bot.command(name='list_bookmarks')
async def list_bookmarks(ctx):
    """Lists all the bookmarks for the user.

    :param ctx: Discord bot commands represents the "context" of the command.
    :return: None. It sends a message to the user's channel with all their bookmarks.
    """
    user_id = str(ctx.author.id)
    
    try:
        # Retrieve the user's bookmarks
        user_bookmarks = bookmarks_collection.find_one({"user_id": user_id})

        if user_bookmarks:
            bookmarks_list = user_bookmarks.get("bookmarks", [])
            if bookmarks_list:
                unique_bookmarks = list(set(bookmarks_list))
                bookmark_mentions = [f"<@{bookmark}>" for bookmark in unique_bookmarks]
                bookmarks_text = '\n'.join(bookmark_mentions)
                await ctx.send(f'Your bookmarks:\n{bookmarks_text}')
            else:
                await ctx.send('You do not have any bookmarks.')
        else:
            await ctx.send('You do not have any bookmarks.')

    except Exception as e:
        print(f"Error listing bookmarks: {e}")
        await ctx.send("An error occurred while listing bookmarks.")

@bot.command(name='examples')
async def examples(ctx):
    """Lists example commands to the user.

    :param ctx: Discord bot commands represents the "context" of the command.
    :return: None. It sends a message to the user's channel with example commands they can enter.
    """
    embed = discord.Embed(title="Examples of Commands", color=discord.Color.purple())
    embed.add_field(name="🔑 Keyword Tracking", value="• `/add keyword` - Adds a keyword to track\n• `/remove keyword` - Removes a keyword from tracking", inline=False)
    embed.add_field(name="🔖 Bookmarking Messages", value="• `/bookmark discorduser1` - Bookmark messages from discorduser1\n• `/remove_bookmark discorduser1` - Removes a bookmark", inline=False)
    embed.add_field(name="🔔 Setting Reminders", value="• `/add_reminder \"2023-01-01 12:00\" \"New Year\"` - Sets a reminder for a specific time.\n• `/add_reminder \"in 1 hour\" \"Quick Meeting\"` - Sets a reminder for 1 hour from now.\n• `/remove_reminder \"New Year\"` - Removes a reminder with the label 'New Year'.", inline=False)
    embed.add_field(name="📩 Summarizing Messages", value="• `/summarize #general 100` - Summarizes the last 100 messages in the general channel", inline=False)
    embed.add_field(name="🖨️ Listing Commands", value="• `/list` - Lists all keywords you are tracking\n• `/list_bookmarks` - Lists all your bookmarks\n• `/list_reminders` - Lists all your reminders", inline=False)
    await ctx.send(embed=embed)

@bot.command(name='onboard_user')
async def onboard_user(ctx):
    """
    Onboards a new user by guiding them through setting up a private channel and introducing other bot features!
    """
    member = ctx.author
    if str(member.id) in user_private_channels:
        await ctx.send(f"{member.mention}, you already have a private channel set up! Feel free to enter /showhelp to see all commands available to use.")
    else:
        await ctx.send(f"{member.mention}, welcome! Before you can use the full features of this bot, you need to set up a private channel. Please enter `/create_private_channel` to do this.")

    embed = discord.Embed(title="Getting Started with the Bot", description="Once you have your private channel set up, you can explore the bot's features:", color=discord.Color.purple())
    embed.add_field(name="🔑 Keyword Notifications", value="Use `/add <keyword>` to get notified for mentions of specific keywords.", inline=False)
    embed.add_field(name="🔖 Bookmark Messages", value="Use `/bookmark <discord_username>` to bookmark messages from a specific user.", inline=False)
    embed.add_field(name="🔔 Set Reminders", value="Use `/add_reminder \"time\" \"label\"` to set a reminder for yourself.", inline=False)
    embed.add_field(name="💬 Get Help", value="Use `/showhelp` to see all commands available to you.", inline=False)
    embed.set_footer(text="Start by creating your private channel to make the most out of these features!")

    await ctx.send(embed=embed)
    
bot.run(token)
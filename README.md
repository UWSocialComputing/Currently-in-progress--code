# Prioritize Bot for Discord

Prioritize Bot is designed to enhance your Discord experience by providing keyword notifications, bookmarking user messages, setting reminders, summarizing channel messages, and more, all through simple commands :)

## Setup

To get started with Prioritize Bot in your server, follow these steps:

### Requirements

- Python version required
- Discord account and a server where you have permission to add bots
- OpenAI API key (for summarizing messages)
- MongoDB database (for storing user data)

### Installation

1. Clone the repository to your local machine or server.
2. Create a Discord account and an application with Discord's developer portal! To create a Discord bot and obtain a bot token, visit [Discord's developer portal](https://discord.com/developers/applications) and [this resource](https://discordpy.readthedocs.io/en/stable/discord.html).
3. Install the required Python packages by running `pip install -r requirements.txt`.
4. Set up your `.env` file with your Discord bot token, OpenAI API key, and MongoDB URL as shown below:

```plaintext
# .env file
DISCORD_BOT_TOKEN=your_discord_bot_token_here
OPENAI_API_KEY=your_openai_api_key_here
MONGODB_URL=your_mongodb_url_here
```

### Run the bot with python bot.py.

After inviting the bot to your server and running it with `python bot.py`, you can start using its features! Here's how to get started:

## Onboarding + Help

- **/onboard_user**: Enter this command for guidance on how to get set up with the bot!
- **/create_private_channel**: Enter this command to create a private channel where you can interact with the bot!
- **/showhelp**: Displays all available commands.

## Keyword Notifications

- **/add `<keyword>`**: Get notified for mentions of specific keywords.
- **/remove `<keyword>`**: Stop notifications for a keyword.
- **/list**: View all keywords you're tracking.

## Bookmarking Messages

- **/bookmark `<discord_username>`**: Bookmark messages from a specific user.
- **/remove_bookmark `<discord_username>`**: Stop bookmarking messages from specific users.
- **/list_bookmarks**: Lists all the bookmarked users.

## Setting Reminders

- **/add_reminder `"time" "label"`**: Add a reminder for a specific time with a label. Time format examples: `"2023-01-01 12:00"`, `"in 1 hour"`.
- **/remove_reminder `"label"`**: Remove a reminder by its label.
- **/list_reminders**: List reminders by its timestamp and label.

## Summarizing Messages

- **/summarize `#channel-name <# of messages>`**: Summarize messages in a channel.

## Commands

Here are some example commands to get you started!

```plaintext
/add keyword - Adds a keyword to track
/remove keyword - Removes a keyword from tracking
/bookmark @username - Bookmark messages from a specific user
/remove_bookmark @username - Removes a bookmarked user
/add_reminder "2023-01-01 12:00" "New Year" - Sets a reminder for New Year
/summarize #general 100 - Summarizes the last 100 messages in the #general channel
```
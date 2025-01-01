import discord
from discord.ext import commands, tasks
import requests
import asyncio
from dotenv import load_dotenv
import os
import logging
import time

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))  # Replace with the Discord channel ID where notifications should be sent

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True  # Enable message content intent
bot = commands.Bot(command_prefix="!", intents=intents)

API_URL = "https://backend.numenex.com/questions/"
HEALTH_CHECK_URL = "https://backend.numenex.com/health-check"

# Helper function to send a message to the Discord channel
async def notify_discord(message):
    logging.debug(f"Attempting to send message to channel {CHANNEL_ID}: {message}")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(message)
    else:
        logging.error(f"Channel with ID {CHANNEL_ID} not found.")

# Function to check questions API
async def check_questions():
    logging.info("Checking questions API...")
    start_time = time.time()
    try:
        response = requests.get(API_URL, headers={"accept": "application/json"})
        response_time = time.time() - start_time
        logging.debug(f"Questions API Response: {response.status_code} - {response.text}")
        if response.status_code == 200:
            questions = response.json()
            if not questions:
                logging.warning("No questions found in the API response.")
                return f"⚠️ No questions found in the API response!\n**Server Host URL:** {API_URL}\n**Time Taken:** {response_time:.2f} seconds", None
            else:
                # Create a table-like format for questions
                table_header = "| ID | Question | Type |\n| --- | --- | --- |"
                table_rows = "\n".join([
                    f"| {q['id']} | {q['question']} | {q['question_type']} |"
                    for q in questions
                ])
                table_content = f"{table_header}\n{table_rows}"
                return (f"✅ Questions fetched successfully:\n\n{table_content}\n\n"
                        f"**Server Host URL:** {API_URL}\n**Time Taken:** {response_time:.2f} seconds"), questions
        else:
            logging.error(f"Error fetching questions: {response.status_code} - {response.text}")
            return f"❌ Error fetching questions: {response.status_code} - {response.text}\n**Server Host URL:** {API_URL}\n**Time Taken:** {response_time:.2f} seconds", None
    except Exception as e:
        logging.exception("Exception occurred while checking questions API.")
        response_time = time.time() - start_time
        return f"❌ Exception occurred while checking questions: {e}\n**Server Host URL:** {API_URL}\n**Time Taken:** {response_time:.2f} seconds", None

# Function to check server health
async def check_server_health():
    logging.info("Checking server health...")
    try:
        response = requests.get(HEALTH_CHECK_URL)
        logging.debug(f"Server Health Response: {response.status_code} - {response.text}")
        if response.status_code == 200:
            return "✅ Server is healthy.", response.text
        else:
            logging.error("Server health check failed: Server is down!")
            return "❌ Server health check failed: Server is down!", None
    except Exception as e:
        logging.exception("Exception occurred during server health check.")
        return f"❌ Exception occurred during server health check: {e}", None

# Command to manually check questions API
@bot.command(name="check_questions")
async def manual_check_questions(ctx):
    logging.info("Received command: check_questions")
    logging.debug(f"Command invoked by user: {ctx.author} in channel: {ctx.channel}")
    try:
        status, _ = await check_questions()
        await ctx.send(status)
    except Exception as e:
        logging.exception("Error while executing check_questions command.")
        await ctx.send(f"❌ Error executing command: {e}")

# Command to manually check server health
@bot.command(name="check_server")
async def manual_check_server(ctx):
    logging.info("Received command: check_server")
    logging.debug(f"Command invoked by user: {ctx.author} in channel: {ctx.channel}")
    try:
        status, _ = await check_server_health()
        await ctx.send(status)
    except Exception as e:
        logging.exception("Error while executing check_server command.")
        await ctx.send(f"❌ Error executing command: {e}")

# Bot events
@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user}")
    await notify_discord("✅ Bot is online and monitoring!")

@bot.event
async def on_message(message):
    logging.debug(f"Message received: {message.content} from {message.author}")
    await bot.process_commands(message)

# Run the bot
logging.info("Starting the bot...")
bot.run(TOKEN)

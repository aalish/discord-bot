import discord
from discord.ext import tasks
from discord import app_commands
import requests
from dotenv import load_dotenv
import os
import logging
import time
# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
TIME_INTERVAL = int(os.getenv("TIME_INTERVAL"))

intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

API_URL = "https://backend.numenex.com/questions/"
HEALTH_CHECK_URL = "https://backend.numenex.com/health-check"

class MonitoringBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()

# Initialize the bot
bot = MonitoringBot()

# Helper function for auto-completion
async def question_type_autocomplete(interaction: discord.Interaction, current: str):
    question_types = ["type1", "type2", "type3"]  # Replace with actual types or fetch dynamically
    return [
        app_commands.Choice(name=qt, value=qt)
        for qt in question_types if current.lower() in qt.lower()
    ]

# Function to fetch questions from API
async def fetch_questions():
    try:
        response = requests.get(API_URL, headers={"accept": "application/json"})
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Error fetching questions: {response.status_code}")
            return []
    except Exception as e:
        logging.exception("Exception while fetching questions")
        return []
@bot.tree.command(name="check_questions", description="Fetch and display questions from the server.")
async def check_questions(interaction: discord.Interaction):
    # logging.info("Received slash command: check_questions")
    start_time = time.time()
    await interaction.response.defer()
    questions = await fetch_questions()
    response_time = time.time() - start_time
    if not questions:
        
        await interaction.followup.send(f"{'-' * 40}\n⚠️ No questions found in the server response.\n**Server Host URL:** {API_URL}\n**Time Taken:** {response_time:.2f} seconds\n{'-' * 40}")
        return

    formatted_questions = "\n\n".join(
        [
            f"{'-' * 40}\n**ID:** {q['id']}\n**Question:** {q['question']}\n**Type:** {q['question_type']}"
            for q in questions
        ]
    )
    await interaction.followup.send(f"**Server Host URL:** {API_URL}\n**Time Taken:** {response_time:.2f} seconds\n\n{'-' * 40}\nFetched Questions:\n\n{formatted_questions}\n{'-' * 40}\n")

# Slash command for server health check
@bot.tree.command(name="check_server", description="Check server health status.")
async def check_server(interaction: discord.Interaction):
    # logging.info("Received slash command: check_server")
    await interaction.response.defer()
    try:
        response = requests.get(HEALTH_CHECK_URL, timeout=10)
        if response.status_code == 200:
            await interaction.followup.send(f"{'-' * 40}\n✅ Server is healthy.\n{'-' * 40}")
        else:
            await interaction.followup.send(f"{'-' * 40}\n❌ Server health issue! Status Code: {response.status_code}\n{'-' * 40}")
    except requests.exceptions.Timeout:
        await interaction.followup.send(f"{'-' * 40}\n❌ Server health check timed out!\n{'-' * 40}\n")
    except Exception as e:
        logging.exception("Error during server health check")
        await interaction.followup.send(f"{'-' * 40}\n❌ Error checking server health: {e}\n{'-' * 40}")

# Background task to continuously monitor server health
@tasks.loop(minutes=TIME_INTERVAL)
async def continuous_monitoring():
    # logging.info("Performing continuous monitoring...")
    
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        # logging.error(f"Channel with ID {CHANNEL_ID} not found. Skipping monitoring.")
        return

    # Check server health
    try:
        start_time = time.time()
        response = requests.get(HEALTH_CHECK_URL, timeout=10)
        response_time = time.time() - start_time
        if response.status_code != 200:
            await channel.send(f"{'-' * 40}\n❌ Server health issue!\n**Server Host URL:** {HEALTH_CHECK_URL}\n**Time Taken:** {response_time:.2f} seconds\n**Status Code:** {response.status_code}\n{'-' * 40}\n")
    except requests.exceptions.Timeout:
        await channel.send(f"{'-' * 40}\n❌ Server health check timed out!\n**Server Host URL:** {HEALTH_CHECK_URL}\n{'-' * 40}")
    except Exception as e:
        await channel.send(f"{'-' * 40}\n❌ Error checking server health: {e}\n**Server Host URL:** {HEALTH_CHECK_URL}\n{'-' * 40}")

    # Check questions API
    questions = await fetch_questions()
    if not questions:
        await channel.send(f"{'-' * 40}\n⚠️ No questions found in the API response!\n**Server Host URL:** {HEALTH_CHECK_URL}\n{'-' * 40}")

@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user}")
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.send(f"{'-' * 40}\n✅ Bot is online and monitoring!\n{'-' * 40}")
    continuous_monitoring.start()

# Run the bot
logging.info("Starting the bot...")
bot.run(TOKEN)

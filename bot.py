import discord
from discord.ext import tasks
from discord import app_commands
import requests
import os
import logging
import json
from dotenv import load_dotenv
from enum import Enum
import time
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
TIME_INTERVAL = int(os.getenv("TIME_INTERVAL"))
WAIT_TIME = 15 * 60
# Load server configurations
with open("./config.json", "r") as file:
    SERVERS = json.load(file)

# Define intents
intents = discord.Intents.default()
intents.message_content = True


class MonitoringBot(discord.Client):
    def __init__(self):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync()


# Dynamically create the Enum for application names
ApplicationName = Enum(
    "ApplicationName",
    {server["Name"]: server["Name"] for server in SERVERS}
)

# Initialize the bot
bot = MonitoringBot()


# Slash command to check a specific application's health
@bot.tree.command(name="check_single_application_health", description="Check health status of a specific application.")
@app_commands.describe(application_name="Name of the application to check")
async def check_single_application_health(interaction: discord.Interaction, application_name: ApplicationName):
    formatter = "----------------------------------------------"
    await interaction.response.defer()

    # Get the application from SERVERS
    application = next((app for app in SERVERS if app["Name"] == application_name.value), None)

    if not application:
        await interaction.followup.send(f"❌ Application with name '{application_name.value}' not found in the configuration.")
        return

    try:
        healthcheck_endpoint = application["URL"] + application["Healthcheck Route"]
        response = requests.get(healthcheck_endpoint, timeout=10)

        if response.status_code == 200:
            response_message = (
                f"{formatter}\n**Application Name:** {application['Name']}\n✅ Server is healthy.\n{formatter}"
            )
        else:
            response_message = (
                f"{formatter}\n❌ Server health issue!\n**Application Name:** {application['Name']}\n"
                f"**Status Code:** {response.status_code}\n{formatter}"
            )
    except requests.exceptions.Timeout:
        response_message = (
            f"{formatter}\n❌ Server health check timed out!\n**Application Name:** {application['Name']}\n{formatter}"
        )
    except Exception as e:
        logging.exception("Error during specific application health check")
        response_message = (
            f"{formatter}\n❌ Error checking server health: {e}\n**Application Name:** {application['Name']}\n{formatter}"
        )

    await interaction.followup.send(response_message)


# Slash command to check all applications' health
@bot.tree.command(name="check_applications_health", description="Check health status of all configured applications.")
async def check_applications_health(interaction: discord.Interaction):
    formatter = "----------------------------------------------"
    await interaction.response.defer()
    response_message = ""

    for each in SERVERS:
        try:
            healthcheck_endpoint = each["URL"] + each["Healthcheck Route"]
            response = requests.get(healthcheck_endpoint, timeout=10)

            if response.status_code == 200:
                response_message += f"{formatter}\n**Application Name:** {each['Name']}\n✅ Server is healthy.\n{formatter}\n"
            else:
                response_message += f"{formatter}\n❌ Server health issue!\n**Application Name:** {each['Name']}\n**Status Code:** {response.status_code}\n{formatter}\n"
        except requests.exceptions.Timeout:
            response_message += f"{formatter}\n❌ Server health check timed out!\n**Application Name:** {each['Name']}\n{formatter}\n"
        except Exception as e:
            logging.exception("Error during server health check")
            response_message += f"{formatter}\n❌ Error checking server health: {e}\n**Application Name:** {each['Name']}\n{formatter}\n"

    await interaction.followup.send(response_message)


# Background task for continuous monitoring
@tasks.loop(minutes=TIME_INTERVAL)
async def continuous_monitoring():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        logging.error(f"Channel with ID {CHANNEL_ID} not found. Skipping monitoring.")
        return

    for each in SERVERS:
        try:
            healthcheck_endpoint = each["URL"] + each["Healthcheck Route"]
            start_time = time.time()
            response = requests.get(healthcheck_endpoint, timeout=10)
            response_time = time.time() - start_time

            if response.status_code != 200:
                await channel.send(
                    f"{'-' * 40}\n❌ Server health issue!\n**Server Host URL:** {healthcheck_endpoint}\n"
                    f"**Time Taken:** {response_time:.2f} seconds\n**Status Code:** {response.status_code}\nSleeping for {WAIT_TIME} minutes\n{'-' * 40}\n"
                )
                time.sleep(WAIT_TIME)
        except requests.exceptions.Timeout:
            await channel.send(f"{'-' * 40}\n❌ Server health check timed out!\n**Server Host URL:** {healthcheck_endpoint}\nSleeping for {WAIT_TIME} minutes\n{'-' * 40}")
            time.sleep(WAIT_TIME)
        except Exception as e:
            await channel.send(f"{'-' * 40}\n❌ Error checking server health: {e}\n**Server Host URL:** {healthcheck_endpoint}\nSleeping for {WAIT_TIME} minutes\n{'-' * 40}")
            time.sleep(WAIT_TIME)

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

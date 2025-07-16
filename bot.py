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
import apscheduler.schedulers.asyncio
from sheets_utils import append_update, export_and_backup_spreadsheet, push_local_updates_to_gsheets, upload_file_to_other_folder
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pandas as pd
from openpyxl import load_workbook
import asyncio
from discord import ui, Interaction
import traceback
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
TOKEN = os.getenv("DISCORD_BOT_TOKEN")
CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))
TIME_INTERVAL = int(os.getenv("TIME_INTERVAL"))
SLEEP_MINUTES = 15
WAIT_TIME = SLEEP_MINUTES * 60
# Load server configurations
with open("./config.json", "r") as file:
    SERVERS = json.load(file)
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
UPDATE_CHANNEL_ID = int(os.getenv("DISCORD_UPDATE_CHANNEL_ID"))
MONITOR_CHANNEL_ID = int(os.getenv("DISCORD_MONITOR_CHANNEL_ID"))

# Define intents
intents = discord.Intents.default()
# Enable message content intent (required for slash commands and message content)
# Make sure to enable "MESSAGE CONTENT INTENT" in the Discord developer portal for your bot.
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


# Helper to append update to local Excel file
def append_update_local(username, update_text):
    from datetime import datetime
    import os
    now = datetime.now()
    row = {
        'Date': now.strftime('%Y-%m-%d'),
        'Time': now.strftime('%H:%M:%S'),
        'Update Text': update_text
    }
    file_exists = os.path.exists('local_updates.xlsx')
    if file_exists:
        try:
            df = pd.read_excel('local_updates.xlsx', sheet_name=username)
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        except ValueError:
            # Sheet does not exist
            df = pd.DataFrame([row])
        with pd.ExcelWriter('local_updates.xlsx', engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name=username, index=False)
    else:
        df = pd.DataFrame([row])
        with pd.ExcelWriter('local_updates.xlsx', engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=username, index=False)

class UpdateModal(ui.Modal, title="Submit an Update"):
    update_message = ui.TextInput(
        label="Your update (multi-line supported)",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000,
        placeholder="Type your update here. Use multiple lines as needed."
    )

    async def on_submit(self, interaction: Interaction):
        # Use display name for saving and echoing
        display_name = interaction.user.display_name
        message = self.update_message.value
        import asyncio
        await asyncio.to_thread(append_update_local, display_name, message)
        await interaction.response.send_message(f"✅ Update from **{display_name}**:\n{message}")

@bot.tree.command(name="update", description="Submit an update to local Excel file (multi-line supported)")
async def update(interaction: discord.Interaction):
    await interaction.response.send_modal(UpdateModal())

# Scheduled backup task
async def scheduled_backup():
    notify = os.getenv("NOTIFY_AFTER_EXPORT", "true").lower() == "true"
    notify_channel_id = os.getenv("DISCORD_UPDATE_CHANNEL_ID")
    try:
        # Push local updates to Google Sheets first
        push_local_updates_to_gsheets()
        backup_filename = export_and_backup_spreadsheet()
        if notify and notify_channel_id:
            channel = bot.get_channel(int(notify_channel_id))
            if channel:
                await channel.send(f"Backup complete: `{backup_filename}` (local updates pushed)")
    except Exception as e:
        logging.error(f"Backup/notification failed: {e}")
        traceback.print_exc()

# Setup APScheduler for cron job
scheduler = AsyncIOScheduler()
cron_schedule = os.getenv("CRON_SCHEDULE", "0 1 * * *")
minute, hour, day, month, day_of_week = cron_schedule.split()
scheduler.add_job(scheduled_backup, CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week))


# Background task for continuous monitoring
@tasks.loop(minutes=TIME_INTERVAL)
async def continuous_monitoring():
    channel = bot.get_channel(MONITOR_CHANNEL_ID)
    if not channel:
        logging.error(f"Channel with ID {MONITOR_CHANNEL_ID} not found. Skipping monitoring.")
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
                    f"**Time Taken:** {response_time:.2f} seconds\n**Status Code:** {response.status_code}\nSleeping for {SLEEP_MINUTES} minutes\n{'-' * 40}\n"
                )
                await asyncio.sleep(WAIT_TIME)
        except requests.exceptions.Timeout:
            await channel.send(f"{'-' * 40}\n❌ Server health check timed out!\n**Server Host URL:** {healthcheck_endpoint}\nSleeping for {SLEEP_MINUTES} minutes\n{'-' * 40}")
            await asyncio.sleep(WAIT_TIME)
        except Exception as e:
            await channel.send(f"{'-' * 40}\n❌ Error checking server health: {e}\n**Server Host URL:** {healthcheck_endpoint}\nSleeping for {SLEEP_MINUTES} minutes\n{'-' * 40}")
            await asyncio.sleep(WAIT_TIME)

@bot.tree.command(name="backup_now", description="Manually trigger the backup and upload to Google Drive.")
async def backup_now(interaction: discord.Interaction):
    await interaction.response.send_message("⏳ Running backup now...", ephemeral=True)
    async def run_backup():
        try:
            await scheduled_backup()
            # Upload local Excel file to the 'other' folder after backup
            upload_file_to_other_folder(
                'local_updates.xlsx',
                filename='TeamUpdates.xlsx',
                mime_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            await interaction.followup.send("✅ Backup completed and TeamUpdates.xlsx uploaded to folder!", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"❌ Backup failed: {e}", ephemeral=True)
    import asyncio
    asyncio.create_task(run_backup())

@bot.event
async def on_ready():
    logging.info(f"Bot logged in as {bot.user}")
    logging.info(f"GUILD_ID from .env: {GUILD_ID}")
    if GUILD_ID:
        try:
            guild = discord.Object(id=int(GUILD_ID))
            synced = await bot.tree.sync(guild=guild)
            logging.info(f"Commands synced to guild {GUILD_ID}")
            logging.info(f"Registered commands: {[cmd.name for cmd in synced]}")
        except Exception as e:
            logging.error(f"Failed to sync commands to guild: {e}")
    else:
        synced = await bot.tree.sync()
        logging.info("Commands synced globally (may take up to 1 hour to appear)")
        logging.info(f"Registered commands: {[cmd.name for cmd in synced]}")
    monitor_channel = bot.get_channel(MONITOR_CHANNEL_ID)
    if monitor_channel:
        await monitor_channel.send(f"{'-' * 40}\n✅ Bot is online and monitoring!\n{'-' * 40}")
    continuous_monitoring.start()
    if not scheduler.running:
        scheduler.start()


# Run the bot
logging.info("Starting the bot...")
bot.run(TOKEN)

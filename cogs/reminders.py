import disnake
from disnake.ext import commands
import asyncio
import json
import logging

from utils.tools.settings import settings
from utils.tools.helpers import safe_defer
from utils.command.botdatatypes import UserError
from cogs.mangocog import MangoCog

logger = logging.getLogger(__name__)

def read_json(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

class Reminders(MangoCog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.scheduled_tasks = {}  # Store tasks by guild_id for cancellation

    async def send_reminder_after_delay(self, guild: disnake.Guild, message: str, delay: int):
        """Sleep and then send the reminder via TTS."""
        await asyncio.sleep(delay)
        try:
            audio_cog = self.bot.get_cog("Audio")
            await audio_cog.do_tts(message, guild)
        except Exception as e:
            logger.error(f"Failed to send reminder: {e}")

    @commands.slash_command(
        name="startreminders",
        description="Start in-game event reminders from the current match time."
    )
    async def start_reminders(
        self,
        inter: disnake.ApplicationCommandInteraction,
        current_time: str = commands.Param(default="00:00", description="Current match time (MM:SS)"),
        time_before: int = commands.Param(default=0, description="Optional time ahead in seconds to adjust reminders")
    ):
        """
        Parameters
        ----------
        current_time: The current time in the match, in MM:SS format
        """
        await safe_defer(inter) # Defer the response to allow time for processing

        # ---- Load JSON -------------------------------------------------
        match_timings_path = settings.resource("json/match_timings.json")
        try:
            match_timings = read_json(match_timings_path)
        except Exception as e:
            logger.error(f"Failed to read match_timings.json: {e}")
            raise UserError("Could not load match timings data.")

        # ---- Parse user input -----------------------------------------
        if ":" not in current_time or current_time.count(":") != 1:
            raise UserError("Current time must be in **MM:SS** format.")

        try:
            mm, ss = map(int, current_time.split(":"))
        except ValueError:
            raise UserError("Minutes and seconds must be integers.")

        current_total = mm * 60 + ss

        # ---- Play startup TTS -----------------------------------------
        try:
            audio_cog = self.bot.get_cog("Audio")
            if audio_cog:
                await audio_cog.do_tts(f"Starting reminders at {current_time}", inter.guild)
        except Exception as e:
            logger.error(f"Failed to play startup TTS: {e}")

        # ---- Flatten events from JSON structure -----------------------
        events = []
        
        # Handle bounty runes
        if "bounty_runes" in match_timings and isinstance(match_timings["bounty_runes"], list):
            for time_str in match_timings["bounty_runes"]:
                events.append({"time": time_str, "message": f"Bounty runes in {time_before} seconds"})
        
        # Handle power runes
        if "power_runes" in match_timings and isinstance(match_timings["power_runes"], list):
            for time_str in match_timings["power_runes"]:
                events.append({"time": time_str, "message": f"Power runes in {time_before} seconds"})
        
        # Handle wisdom runes
        if "wisdom_runes" in match_timings and isinstance(match_timings["wisdom_runes"], list):
            for time_str in match_timings["wisdom_runes"]:
                events.append({"time": time_str, "message": f"Wisdom runes in {time_before} seconds"})
        
        # Handle torghast lotus
        if "torghast_lotus" in match_timings and isinstance(match_timings["torghast_lotus"], dict):
            if "spawn" in match_timings["torghast_lotus"] and isinstance(match_timings["torghast_lotus"]["spawn"], list):
                for time_str in match_timings["torghast_lotus"]["spawn"]:
                    events.append({"time": time_str, "message": f"Lotus in {time_before} seconds"})
        
        # Handle water runes
        if "water_runes" in match_timings and isinstance(match_timings["water_runes"], dict):
            if "spawn" in match_timings["water_runes"] and isinstance(match_timings["water_runes"]["spawn"], list):
                for time_str in match_timings["water_runes"]["spawn"]:
                    events.append({"time": time_str, "message": f"Water rune in {time_before} seconds"})
        
        # ---- Schedule future events ------------------------------------
        scheduled = 0
        if inter.guild.id not in self.scheduled_tasks:
            self.scheduled_tasks[inter.guild.id] = []
        
        for ev in events:
            try:
                ev_mm, ev_ss = map(int, ev["time"].split(":"))
                ev_total = ev_mm * 60 + ev_ss

                if ev_total > current_total:
                    delay = ev_total - current_total - time_before
                    task = self.bot.loop.create_task(
                        self.send_reminder_after_delay(inter.guild, ev["message"], delay)
                    )
                    self.scheduled_tasks[inter.guild.id].append(task)
                    scheduled += 1
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed event entry: {e}")
                continue

        await inter.followup.send(f"Scheduled **{scheduled}** reminder(s).")

    @commands.slash_command(
        name="cancelreminders",
        description="Cancel all queued reminders for this server."
    )
    async def cancel_reminders(self, inter: disnake.ApplicationCommandInteraction):
        """Cancel all pending reminders."""
        await safe_defer(inter)

        guild_id = inter.guild.id
        if guild_id not in self.scheduled_tasks or not self.scheduled_tasks[guild_id]:
            raise UserError("No reminders are currently scheduled.")

        cancelled = 0
        for task in self.scheduled_tasks[guild_id]:
            if not task.done():
                task.cancel()
                cancelled += 1

        self.scheduled_tasks[guild_id] = []
        await inter.followup.send(f"Cancelled **{cancelled}** reminder(s).")

# ----------------------------------------------------------------------
def setup(bot: commands.Bot):
    bot.add_cog(Reminders(bot))
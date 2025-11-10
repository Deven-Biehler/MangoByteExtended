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

    async def send_reminder_after_delay(self, channel: disnake.TextChannel, message: str, delay: int):
        """Sleep and then send the reminder."""
        await asyncio.sleep(delay)
        try:
            await channel.send(message)
        except disnake.HTTPException as e:
            logger.error(f"Failed to send reminder: {e}")

    @commands.slash_command(
        name="startreminders",
        description="Start in-game event reminders from the current match time."
    )
    async def start_reminders(
        self,
        inter: disnake.ApplicationCommandInteraction,
        current_time: str = commands.Param(description="Current match time (MM:SS)")
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

        # ---- Schedule future events ------------------------------------
        scheduled = 0
        for ev in match_timings:
            try:
                ev_mm, ev_ss = map(int, ev["time"].split(":"))
                ev_total = ev_mm * 60 + ev_ss

                if ev_total > current_total:
                    delay = ev_total - current_total
                    self.bot.loop.create_task(
                        self.send_reminder_after_delay(inter.channel, ev["message"], delay)
                    )
                    scheduled += 1
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed event entry: {e}")
                continue

        await inter.followup.send(f"Scheduled **{scheduled}** reminder(s).")

# ----------------------------------------------------------------------
def setup(bot: commands.Bot):
    bot.add_cog(Reminders(bot))
# arena.py

from datetime import timedelta
import re

import discord
from discord.ext import commands

from database import errors, reminders, users
from resources import exceptions, functions, settings, strings


class ArenaCog(commands.Cog):
    """Cog that contains the arena detection commands"""
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message_edit(self, message_before: discord.Message, message_after: discord.Message) -> None:
        """Runs when a message is edited in a channel."""
        for row in message_after.components:
            for component in row.children:
                if component.disabled:
                    return
        await self.on_message(message_after)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Runs when a message is sent in a channel."""
        if message.author.id != settings.EPIC_RPG_ID: return
        if not message.embeds: return
        embed: discord.Embed = message.embeds[0]
        message_author = message_title = icon_url = ''
        if embed.author:
            message_author = str(embed.author.name)
            icon_url = embed.author.icon_url
        if embed.title: message_title = str(embed.title)

        # Arena cooldown
        search_strings = [
            'you have started an arena recently', #English
            'empezaste una arena recientemente', #Spanish
            'você recentemente iniciou uma arena', #Portuguese
        ]
        if any(search_string in message_title.lower() for search_string in search_strings):
            user_id = user_name = user_command_message = None
            user = await functions.get_interaction_user(message)
            if user is None:
                user_id_match = re.search(strings.REGEX_USER_ID_FROM_ICON_URL, icon_url)
                if user_id_match:
                    user_id = int(user_id_match.group(1))
                    user = await message.guild.fetch_member(user_id)
                else:
                    user_name_match = re.search(strings.REGEX_USERNAME_FROM_EMBED_AUTHOR, message_author)
                    if user_name_match:
                        user_name = user_name_match.group(1)
                        user_command_message = (
                            await functions.get_message_from_channel_history(
                                message.channel, strings.REGEX_COMMAND_ARENA,
                                user_name=user_name
                            )
                        )
                    if not user_name_match or user_command_message is None:
                        await functions.add_warning_reaction(message)
                        await errors.log_error('User not found in arena cooldown message.', message)
                        return
                    user = user_command_message.author
            try:
                user_settings: users.User = await users.get_user(user.id)
            except exceptions.FirstTimeUserError:
                return
            if not user_settings.bot_enabled or not user_settings.alert_arena.enabled: return
            user_command = await functions.get_slash_command(user_settings, 'arena')
            timestring_match = await functions.get_match_from_patterns(strings.PATTERNS_COOLDOWN_TIMESTRING,
                                                                       message_title)
            if not timestring_match:
                    await functions.add_warning_reaction(message)
                    await errors.log_error('Timestring not found in arena cooldown message.', message)
                    return
            timestring = timestring_match.group(1)
            time_left = await functions.calculate_time_left_from_timestring(message, timestring)
            if time_left < timedelta(0): return
            reminder_message = user_settings.alert_arena.message.replace('{command}', user_command)
            reminder: reminders.Reminder = (
                await reminders.insert_user_reminder(user.id, 'arena', time_left,
                                                     message.channel.id, reminder_message)
            )
            await functions.add_reminder_reaction(message, reminder, user_settings)


# Initialization
def setup(bot):
    bot.add_cog(ArenaCog(bot))
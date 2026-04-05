import discord
from discord.ext import commands
from discord import app_commands

LOCK_ROLE = 1481395435297046709

class Lockdown(commands.Cog):

    def __init__(self,bot):
        self.bot=bot

    @app_commands.command(name="lock")
    async def lock(self,interaction:discord.Interaction):

        if LOCK_ROLE not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True
            )
            return

        await interaction.channel.set_permissions(
            interaction.guild.default_role,
            send_messages=False
        )

        await interaction.response.send_message(
            "🔒 Channel locked"
        )

    @app_commands.command(name="unlock")
    async def unlock(self,interaction:discord.Interaction):

        if LOCK_ROLE not in [r.id for r in interaction.user.roles]:
            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True
            )
            return

        await interaction.channel.set_permissions(
            interaction.guild.default_role,
            send_messages=True
        )

        await interaction.response.send_message(
            "🔓 Channel unlocked"
        )

async def setup(bot):
    await bot.add_cog(Lockdown(bot))
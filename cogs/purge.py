import discord
from discord.ext import commands
from discord import app_commands
import asyncio

PURGE_ROLE = 1481395435297046709

class Purge(commands.Cog):

    def __init__(self,bot):
        self.bot=bot

    @app_commands.command(name="purge")
    async def purge(self,interaction,amount:int):

        if PURGE_ROLE not in [r.id for r in interaction.user.roles]:

            await interaction.response.send_message(
                "You do not have permission to use this command.",
                ephemeral=True
            )
            return

        if amount<10 or amount>1000:

            await interaction.response.send_message(
                "Range 10-1000",
                ephemeral=True
            )
            return

        channel = interaction.channel

        await channel.set_permissions(
            interaction.guild.default_role,
            send_messages=False
        )

        await interaction.response.send_message("Starting purge")

        progress = await interaction.original_response()

        deleted=0

        async for msg in channel.history(limit=amount+10):

            if msg.id==progress.id:
                continue

            try:
                await msg.delete()
                deleted+=1
            except:
                pass

            percent=int((deleted/amount)*20)

            bar="█"*percent+"░"*(20-percent)

            await progress.edit(
                content=f"[{bar}] {deleted}/{amount}"
            )

            await asyncio.sleep(0.05)

            if deleted>=amount:
                break

        await channel.set_permissions(
            interaction.guild.default_role,
            send_messages=True
        )

        await progress.edit(content="Purge complete")

async def setup(bot):
    await bot.add_cog(Purge(bot))
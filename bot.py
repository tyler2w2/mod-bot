import discord
from discord.ext import commands
import config
import os
import asyncio

intents = discord.Intents.all()

bot = commands.Bot(command_prefix="!", intents=intents)

async def load_cogs():
    cogs_path = "./cogs"
    for file in os.listdir(cogs_path):
        if file.endswith(".py"):
            await bot.load_extension(f"cogs.{file[:-3]}")
            print(f"Loaded {file}")

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")
    await bot.tree.sync()

async def main():
    async with bot:
        await load_cogs()
        await bot.start(config.TOKEN)

asyncio.run(main())

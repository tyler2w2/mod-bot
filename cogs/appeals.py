import discord
from discord.ext import commands
import config
import random
from datetime import timedelta

appeal_logs = {}

# Stores role IDs the user had before the timeout so we can restore them
user_role_backup = {}


class CloseTicket(discord.ui.View):

    def staff(self, interaction):
        return any(r.id in config.STAFF_ROLES for r in interaction.user.roles)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.red)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.staff(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return
        await interaction.response.send_message("Closing ticket...", ephemeral=True)
        await interaction.channel.delete()


class StaffControls(discord.ui.View):

    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    def staff(self, interaction):
        return any(r.id in config.STAFF_ROLES for r in interaction.user.roles)

    @discord.ui.button(label="Open Chat For User", style=discord.ButtonStyle.green)
    async def open(self, interaction, button):

        if not self.staff(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return

        # 1. Remove ALL current roles from the user (except @everyone and managed roles)
        roles_to_remove = [
            r for r in self.user.roles
            if r != interaction.guild.default_role and not r.managed
        ]
        if roles_to_remove:
            await self.user.remove_roles(*roles_to_remove, reason="Appeal — stripping roles before open chat")

        # 2. Remove the timeout so they can read the channel
        await self.user.timeout(None)

        # 3. Give ONLY the appeal/timeout role (id: config.APPEAL_ROLE)
        appeal_role = interaction.guild.get_role(config.APPEAL_ROLE)
        if appeal_role:
            await self.user.add_roles(appeal_role, reason="Appeal — granting appeal role")

        # 4. Allow them to type in this channel
        await interaction.channel.set_permissions(
            self.user,
            send_messages=True
        )

        await interaction.response.send_message(
            f"All roles removed. User given <@&{config.APPEAL_ROLE}> and can now speak.",
            ephemeral=True
        )

    @discord.ui.button(label="Hold Timeout", style=discord.ButtonStyle.red)
    async def hold(self, interaction, button):

        if not self.staff(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return

        # 1. Remove the appeal role
        appeal_role = interaction.guild.get_role(config.APPEAL_ROLE)
        if appeal_role and appeal_role in self.user.roles:
            await self.user.remove_roles(appeal_role, reason="Appeal denied — removing appeal role")

        # 2. Restore backed-up roles
        backed_up = user_role_backup.get(self.user.id, [])
        restored = []
        for role_id in backed_up:
            role = interaction.guild.get_role(role_id)
            if role and role not in self.user.roles:
                try:
                    await self.user.add_roles(role, reason="Appeal denied — restoring original roles")
                    restored.append(role.name)
                except Exception:
                    pass

        # 3. Re-apply the timeout (appeal denied)
        await self.user.timeout(
            timedelta(days=1),
            reason="Appeal denied — timeout held"
        )

        await interaction.channel.set_permissions(
            self.user,
            send_messages=False
        )

        restored_text = ", ".join(restored) if restored else "none"
        await interaction.response.send_message(
            f"Appeal denied. Timeout re-applied. Appeal role removed. Roles restored: {restored_text}",
            ephemeral=True
        )

        await interaction.channel.send(
            "Staff decision recorded — appeal denied. User has been re-timed out.",
            view=CloseTicket()
        )

    @discord.ui.button(label="Untimeout", style=discord.ButtonStyle.grey)
    async def untimeout(self, interaction, button):

        if not self.staff(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return

        # 1. Remove the appeal role
        appeal_role = interaction.guild.get_role(config.APPEAL_ROLE)
        if appeal_role and appeal_role in self.user.roles:
            await self.user.remove_roles(appeal_role, reason="Appeal accepted — removing appeal role")

        # 2. Remove the timeout
        await self.user.timeout(None)

        # 3. Restore backed-up roles
        backed_up = user_role_backup.get(self.user.id, [])
        restored = []
        for role_id in backed_up:
            role = interaction.guild.get_role(role_id)
            if role and role not in self.user.roles:
                try:
                    await self.user.add_roles(role, reason="Appeal accepted — restoring original roles")
                    restored.append(role.name)
                except Exception:
                    pass

        # 4. Clear the backup
        user_role_backup.pop(self.user.id, None)

        restored_text = ", ".join(restored) if restored else "none"
        await interaction.response.send_message(
            f"User unmuted. Appeal role removed. Roles restored: {restored_text}",
            ephemeral=True
        )

        await interaction.channel.send(
            "User unmuted by staff. Original roles restored.",
            view=CloseTicket()
        )


class AppealButton(discord.ui.View):

    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="Appeal", style=discord.ButtonStyle.blurple)
    async def appeal(self, interaction, button):

        # Disable the button so it can't be clicked twice
        button.disabled = True
        await interaction.message.edit(view=self)

        guild = self.user.guild
        category = guild.get_channel(config.APPEAL_CATEGORY)

        channel = await guild.create_text_channel(
            f"appeal-{self.user.name}-{random.randint(1000, 9999)}",
            category=category
        )

        # User cannot send messages until staff clicks "Open Chat For User"
        await channel.set_permissions(
            self.user,
            send_messages=False
        )

        pings = " ".join(f"<@&{r}>" for r in config.STAFF_ROLES)

        await channel.send(
            f"{pings}\nAppeal for {self.user.mention}",
            view=StaffControls(self.user)
        )

        log_text = appeal_logs.get(self.user.id)
        if log_text:
            embed = discord.Embed(
                title="Moderation Evidence",
                color=discord.Color.orange()
            )
            embed.add_field(name="User",     value=self.user.mention)
            embed.add_field(name="Reason",   value="Timeout Appeal")
            embed.add_field(name="Messages", value=f"```{log_text}```", inline=False)
            await channel.send(embed=embed)

        # Acknowledge the interaction
        await interaction.response.send_message(
            f"Your appeal channel has been created: {channel.jump_url}",
            ephemeral=True
        )

        # DM the user the direct link to their appeal channel
        try:
            dm_embed = discord.Embed(
                title="📬 Your Appeal Has Been Created",
                description=(
                    f"Your appeal channel is ready. Click the link below to go there:\n\n"
                    f"**[→ Go to your appeal channel]({channel.jump_url})**\n\n"
                    "Please wait for a staff member to open the chat for you before you can type."
                ),
                color=discord.Color.blurple()
            )
            await self.user.send(embed=dm_embed)
        except discord.Forbidden:
            # User has DMs closed — not a critical failure
            pass


class Appeals(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(Appeals(bot))

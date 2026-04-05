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

        guild = interaction.guild

        # 1. Back up roles if not already done by moderation.py
        if self.user.id not in user_role_backup:
            user_role_backup[self.user.id] = [
                r.id for r in self.user.roles
                if r != guild.default_role and not r.managed
                and r.id != config.APPEAL_ROLE
            ]

        # 2. Strip all non-managed roles
        roles_to_remove = [
            r for r in self.user.roles
            if r != guild.default_role and not r.managed
        ]
        if roles_to_remove:
            await self.user.remove_roles(
                *roles_to_remove,
                reason="Appeal — stripping roles before open chat"
            )

        # 3. Remove Discord timeout so user isn't silenced by Discord itself
        await self.user.timeout(None)

        # 4. Give the appeal role
        appeal_role = guild.get_role(config.APPEAL_ROLE)
        if appeal_role:
            await self.user.add_roles(
                appeal_role,
                reason="Appeal — granting appeal role"
            )

        # 5. Explicitly allow the appeal role AND the user to view + send in this channel.
        #    This overrides any deny the role may have elsewhere in the server.
        if appeal_role:
            await interaction.channel.set_permissions(
                appeal_role,
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        await interaction.channel.set_permissions(
            self.user,
            view_channel=True,
            send_messages=True,
            read_message_history=True
        )

        await interaction.response.send_message(
            f"✅ Roles stripped. {self.user.mention} given <@&{config.APPEAL_ROLE}> "
            f"and can now view and speak in this channel.",
            ephemeral=True
        )

    @discord.ui.button(label="Hold Timeout", style=discord.ButtonStyle.red)
    async def hold(self, interaction, button):

        if not self.staff(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return

        guild = interaction.guild

        # 1. Remove appeal role
        appeal_role = guild.get_role(config.APPEAL_ROLE)
        if appeal_role and appeal_role in self.user.roles:
            await self.user.remove_roles(
                appeal_role,
                reason="Appeal denied — removing appeal role"
            )

        # 2. Restore original roles
        backed_up = user_role_backup.get(self.user.id, [])
        restored = []
        for role_id in backed_up:
            role = guild.get_role(role_id)
            if role and role not in self.user.roles:
                try:
                    await self.user.add_roles(
                        role,
                        reason="Appeal denied — restoring original roles"
                    )
                    restored.append(role.name)
                except Exception:
                    pass

        # 3. Re-apply timeout
        await self.user.timeout(
            timedelta(days=1),
            reason="Appeal denied — timeout held"
        )

        # 4. Remove channel overrides so user/appeal role lose access again
        await interaction.channel.set_permissions(self.user, overwrite=None)
        if appeal_role:
            await interaction.channel.set_permissions(appeal_role, overwrite=None)

        # 5. Clear backup
        user_role_backup.pop(self.user.id, None)

        restored_text = ", ".join(restored) if restored else "none"
        await interaction.response.send_message(
            f"❌ Appeal denied. Timeout re-applied. Appeal role removed. "
            f"Roles restored: {restored_text}",
            ephemeral=True
        )

        await interaction.channel.send(
            "**Staff decision: Appeal Denied.**\n"
            "User has been re-timed out and original roles restored.",
            view=CloseTicket()
        )

    @discord.ui.button(label="Untimeout", style=discord.ButtonStyle.green)
    async def untimeout(self, interaction, button):

        if not self.staff(interaction):
            await interaction.response.send_message("Staff only.", ephemeral=True)
            return

        guild = interaction.guild

        # 1. Remove appeal role
        appeal_role = guild.get_role(config.APPEAL_ROLE)
        if appeal_role and appeal_role in self.user.roles:
            await self.user.remove_roles(
                appeal_role,
                reason="Appeal accepted — removing appeal role"
            )

        # 2. Remove Discord timeout
        await self.user.timeout(None)

        # 3. Restore original roles
        backed_up = user_role_backup.get(self.user.id, [])
        restored = []
        for role_id in backed_up:
            role = guild.get_role(role_id)
            if role and role not in self.user.roles:
                try:
                    await self.user.add_roles(
                        role,
                        reason="Appeal accepted — restoring original roles"
                    )
                    restored.append(role.name)
                except Exception:
                    pass

        # 4. Remove channel overrides
        await interaction.channel.set_permissions(self.user, overwrite=None)
        if appeal_role:
            await interaction.channel.set_permissions(appeal_role, overwrite=None)

        # 5. Clear backup
        user_role_backup.pop(self.user.id, None)

        restored_text = ", ".join(restored) if restored else "none"
        await interaction.response.send_message(
            f"✅ Appeal accepted. User unmuted. Appeal role removed. "
            f"Roles restored: {restored_text}",
            ephemeral=True
        )

        await interaction.channel.send(
            "**Staff decision: Appeal Accepted.**\n"
            "User has been unmuted and original roles restored.",
            view=CloseTicket()
        )


class AppealButton(discord.ui.View):

    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="Appeal", style=discord.ButtonStyle.blurple)
    async def appeal(self, interaction, button):

        # Disable button so it can't be clicked twice
        button.disabled = True
        await interaction.message.edit(view=self)

        guild       = self.user.guild
        category    = guild.get_channel(config.APPEAL_CATEGORY)
        appeal_role = guild.get_role(config.APPEAL_ROLE)

        # Build permission overwrites at channel creation time:
        # - @everyone: cannot see
        # - user: can VIEW + READ but NOT send (until staff opens chat)
        # - appeal role: can VIEW + READ but NOT send (until staff opens chat)
        # - each staff role: full access
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            self.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                read_message_history=True
            ),
        }

        if appeal_role:
            overwrites[appeal_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=False,
                read_message_history=True
            )

        for role_id in config.STAFF_ROLES:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True
                )

        channel = await guild.create_text_channel(
            f"appeal-{self.user.name}-{random.randint(1000, 9999)}",
            category=category,
            overwrites=overwrites
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

        await interaction.response.send_message(
            f"Your appeal channel has been created: {channel.jump_url}",
            ephemeral=True
        )

        # DM the user the direct link
        try:
            dm_embed = discord.Embed(
                title="📬 Your Appeal Has Been Created",
                description=(
                    f"Your appeal channel is ready. Click the link below to go there:\n\n"
                    f"**[→ Go to your appeal channel]({channel.jump_url})**\n\n"
                    "Please wait for a staff member to open the chat before you can type."
                ),
                color=discord.Color.blurple()
            )
            await self.user.send(embed=dm_embed)
        except discord.Forbidden:
            pass


class Appeals(commands.Cog):

    def __init__(self, bot):
        self.bot = bot


async def setup(bot):
    await bot.add_cog(Appeals(bot))

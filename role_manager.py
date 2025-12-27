# role_manager.py
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Your Discord ID
YOUR_USER_ID = 1187380593516879942

def is_owner_check(ctx: commands.Context) -> bool:
    """Top-level predicate for owner-only commands."""
    return ctx.author.id == YOUR_USER_ID

class RoleManager(commands.Cog):
    """Role management commands for bot owner"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ==================== ROLE MANAGEMENT COMMANDS ====================

    @commands.command(name="roleall", aliases=["giveroleall", "allroles"])
    @commands.guild_only()
    @commands.check(is_owner_check)
    async def roleall(self, ctx: commands.Context, member: discord.Member):
        """
        Add every role below bot's highest role to a user (Owner only)
        Usage: $roleall @user
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Get bot's highest role
        bot_member = ctx.guild.get_member(self.bot.user.id) or ctx.guild.me
        if not bot_member:
            await ctx.send("❌ Bot member not found.", delete_after=5)
            return

        bot_highest_role = bot_member.top_role

        # Get all roles below bot's highest role
        eligible_roles = [role for role in ctx.guild.roles
                          if role.position < bot_highest_role.position and not role.is_default()]

        if not eligible_roles:
            await ctx.send("❌ No eligible roles found.", delete_after=5)
            return

        # Start adding roles
        message = await ctx.send(f"⏳ Adding {len(eligible_roles)} roles to {member.mention}...")

        added_count = 0
        failed_count = 0

        for role in eligible_roles:
            try:
                # Check if member already has the role
                if role not in member.roles:
                    await member.add_roles(role, reason=f"Added by {ctx.author} via $roleall")
                    added_count += 1
                    await asyncio.sleep(0.5)  # Rate limit protection
            except discord.Forbidden:
                failed_count += 1
            except Exception as e:
                logger.error(f"Error adding role {role.name}: {e}")
                failed_count += 1

        # Update message
        success_embed = discord.Embed(
            title="✅ Role Assignment Complete",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        success_embed.add_field(name="User", value=member.mention, inline=True)
        success_embed.add_field(name="Total Roles", value=str(len(eligible_roles)), inline=True)
        success_embed.add_field(name="Added", value=str(added_count), inline=True)
        success_embed.add_field(name="Failed", value=str(failed_count), inline=True)
        success_embed.add_field(name="Already Had", value=str(len(eligible_roles) - added_count - failed_count), inline=True)
        success_embed.set_footer(text=f"Executed by {ctx.author.name}", icon_url=getattr(ctx.author.display_avatar, "url", ""))

        await message.edit(content=None, embed=success_embed)

    @commands.command(name="roleadd", aliases=["giverole"])
    @commands.guild_only()
    @commands.check(is_owner_check)
    async def roleadd(self, ctx: commands.Context, member: discord.Member, *, role_name: str):
        """
        Add a specific role to a user (Owner only)
        Usage: $roleadd @user Admin or $roleadd @user "Pro Middleman"
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Get bot's highest role
        bot_member = ctx.guild.get_member(self.bot.user.id) or ctx.guild.me
        if not bot_member:
            await ctx.send("❌ Bot member not found.", delete_after=5)
            return

        bot_highest_role = bot_member.top_role

        # Find the role
        role = None

        # Try exact match first
        for guild_role in ctx.guild.roles:
            if guild_role.name.lower() == role_name.lower() and guild_role.position < bot_highest_role.position:
                role = guild_role
                break

        # If not found, try partial match
        if not role:
            for guild_role in ctx.guild.roles:
                if role_name.lower() in guild_role.name.lower() and guild_role.position < bot_highest_role.position:
                    role = guild_role
                    break

        if not role:
            await ctx.send(f"❌ Role '{role_name}' not found or bot doesn't have permission.", delete_after=5)
            return

        # Check if member already has the role
        if role in member.roles:
            embed = discord.Embed(
                title="ℹ️ Role Already Assigned",
                description=f"{member.mention} already has the {role.mention} role.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        try:
            await member.add_roles(role, reason=f"Added by {ctx.author} via $roleadd")

            embed = discord.Embed(
                title="✅ Role Added",
                description=f"Successfully added {role.mention} to {member.mention}",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Added by {ctx.author.name}", icon_url=getattr(ctx.author.display_avatar, "url", ""))

            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot doesn't have permission to add this role.", delete_after=5)
        except Exception as e:
            logger.error(f"Error adding role: {e}")
            await ctx.send(f"❌ Error adding role: {str(e)[:100]}", delete_after=5)

    @commands.command(name="roleremove", aliases=["remrole", "takerole"])
    @commands.guild_only()
    @commands.check(is_owner_check)
    async def roleremove(self, ctx: commands.Context, member: discord.Member, *, role_name: str):
        """
        Remove a specific role from a user (Owner only)
        Usage: $roleremove @user Admin
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Find the role
        role = None

        # Try exact match first
        for guild_role in ctx.guild.roles:
            if guild_role.name.lower() == role_name.lower():
                role = guild_role
                break

        # If not found, try partial match
        if not role:
            for guild_role in ctx.guild.roles:
                if role_name.lower() in guild_role.name.lower():
                    role = guild_role
                    break

        if not role:
            await ctx.send(f"❌ Role '{role_name}' not found.", delete_after=5)
            return

        # Check if member has the role
        if role not in member.roles:
            embed = discord.Embed(
                title="ℹ️ Role Not Assigned",
                description=f"{member.mention} doesn't have the {role.mention} role.",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed, delete_after=10)
            return

        try:
            await member.remove_roles(role, reason=f"Removed by {ctx.author} via $roleremove")

            embed = discord.Embed(
                title="✅ Role Removed",
                description=f"Successfully removed {role.mention} from {member.mention}",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"Removed by {ctx.author.name}", icon_url=getattr(ctx.author.display_avatar, "url", ""))

            await ctx.send(embed=embed)
        except discord.Forbidden:
            await ctx.send("❌ Bot doesn't have permission to remove this role.", delete_after=5)
        except Exception as e:
            logger.error(f"Error removing role: {e}")
            await ctx.send(f"❌ Error removing role: {str(e)[:100]}", delete_after=5)

    @commands.command(name="viewroles", aliases=["roles", "listroles"])
    @commands.guild_only()
    @commands.check(is_owner_check)
    async def viewroles(self, ctx: commands.Context, member: discord.Member = None):
        """
        View roles of a user or all roles in server
        Usage: $viewroles @user or $viewroles (shows all server roles)
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if member:
            # Show member's roles
            roles = [role.mention for role in member.roles if not role.is_default()]

            embed = discord.Embed(
                title=f"👤 Roles for {member.display_name}",
                color=member.color,
                timestamp=datetime.utcnow()
            )

            if roles:
                embed.description = "\n".join(roles)
                embed.add_field(name="Total Roles", value=str(len(roles)), inline=True)
            else:
                embed.description = "No roles"
                embed.add_field(name="Total Roles", value="0", inline=True)

            embed.set_thumbnail(url=getattr(member.display_avatar, "url", ""))
            embed.set_footer(text=f"User ID: {member.id}")

            await ctx.send(embed=embed)
        else:
            # Show all server roles
            roles = [role for role in ctx.guild.roles if not role.is_default()]
            roles.reverse()  # Show highest roles first

            # Get bot's highest role for reference
            bot_member = ctx.guild.get_member(self.bot.user.id) or ctx.guild.me
            bot_highest_role = bot_member.top_role if bot_member else None

            embed = discord.Embed(
                title="🏷️ Server Roles",
                color=discord.Color.blue(),
                timestamp=datetime.utcnow()
            )

            # Group roles by category
            managed_roles = []
            bot_assignable_roles = []
            unassignable_roles = []

            for role in roles:
                if role.managed:  # Bot/managed roles
                    managed_roles.append(role)
                elif bot_highest_role and role.position < bot_highest_role.position:
                    bot_assignable_roles.append(role)
                else:
                    unassignable_roles.append(role)

            # Format role lists
            def format_role_list(role_list, max_length=1000):
                text = ""
                for role in role_list:
                    role_text = f"{role.mention} (Position: {role.position})\n"
                    if len(text + role_text) > max_length:
                        text += "...\n"
                        break
                    text += role_text
                return text

            if bot_assignable_roles:
                embed.add_field(
                    name=f"✅ Bot Assignable ({len(bot_assignable_roles)})",
                    value=format_role_list(bot_assignable_roles),
                    inline=False
                )

            if unassignable_roles:
                embed.add_field(
                    name=f"⚠️ Above Bot ({len(unassignable_roles)})",
                    value=format_role_list(unassignable_roles[:10]),
                    inline=False
                )

            if managed_roles:
                embed.add_field(
                    name=f"🤖 Managed Roles ({len(managed_roles)})",
                    value=", ".join([role.name for role in managed_roles[:5]]),
                    inline=False
                )

            embed.add_field(name="Total Server Roles", value=str(len(roles)), inline=True)

            if bot_highest_role:
                embed.add_field(name="Bot's Highest Role", value=bot_highest_role.mention, inline=True)
                embed.add_field(name="Bot Role Position", value=str(bot_highest_role.position), inline=True)

            await ctx.send(embed=embed)

    @commands.command(name="roleinfo", aliases=["inforole"])
    @commands.guild_only()
    @commands.check(is_owner_check)
    async def roleinfo(self, ctx: commands.Context, *, role_name: str):
        """
        Get detailed information about a role
        Usage: $roleinfo Admin or $roleinfo "Pro Middleman"
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Find the role
        role = None

        # Try exact match first
        for guild_role in ctx.guild.roles:
            if guild_role.name.lower() == role_name.lower():
                role = guild_role
                break

        # If not found, try partial match
        if not role:
            for guild_role in ctx.guild.roles:
                if role_name.lower() in guild_role.name.lower():
                    role = guild_role
                    break

        if not role:
            await ctx.send(f"❌ Role '{role_name}' not found.", delete_after=5)
            return

        # Get bot's highest role for comparison
        bot_member = ctx.guild.get_member(self.bot.user.id) or ctx.guild.me
        bot_highest_role = bot_member.top_role if bot_member else None
        can_assign = bot_highest_role and role.position < bot_highest_role.position

        # Count members with this role
        member_count = len([member for member in ctx.guild.members if role in member.roles])

        embed = discord.Embed(
            title=f"🏷️ Role Info: {role.name}",
            color=role.color,
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="ID", value=f"`{role.id}`", inline=True)
        embed.add_field(name="Position", value=f"`{role.position}`", inline=True)
        embed.add_field(name="Members", value=f"`{member_count}`", inline=True)
        embed.add_field(name="Color", value=f"`{str(role.color)}`", inline=True)
        embed.add_field(name="Mentionable", value="✅" if role.mentionable else "❌", inline=True)
        embed.add_field(name="Hoisted", value="✅" if role.hoist else "❌", inline=True)
        embed.add_field(name="Managed", value="✅" if role.managed else "❌", inline=True)
        embed.add_field(name="Bot Can Assign", value="✅" if can_assign else "❌", inline=True)
        embed.add_field(name="Created At", value=f"<t:{int(role.created_at.timestamp())}:R>", inline=True)

        # Add permissions if available (defensive)
        try:
            perms = [perm[0] for perm in role.permissions if perm[1]]
        except Exception:
            perms = []
        if perms:
            perms_text = ", ".join(perms[:8])
            if len(perms) > 8:
                perms_text += f" (+{len(perms)-8} more)"
            embed.add_field(name="Key Permissions", value=f"`{perms_text}`", inline=False)

        embed.set_footer(text=f"Role ID: {role.id}")

        await ctx.send(embed=embed)

    @commands.command(name="rolemass", aliases=["massrole", "giveeveryone"])
    @commands.guild_only()
    @commands.check(is_owner_check)
    async def rolemass(self, ctx: commands.Context, *, role_name: str):
        """
        Add a role to EVERYONE in the server (Owner only)
        Usage: $rolemass Admin or $rolemass "Member"
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Find the role
        role = None

        # Get bot's highest role
        bot_member = ctx.guild.get_member(self.bot.user.id) or ctx.guild.me
        bot_highest_role = bot_member.top_role if bot_member else None

        # Try exact match first
        for guild_role in ctx.guild.roles:
            if guild_role.name.lower() == role_name.lower():
                role = guild_role
                break

        # If not found, try partial match
        if not role:
            for guild_role in ctx.guild.roles:
                if role_name.lower() in guild_role.name.lower():
                    role = guild_role
                    break

        if not role:
            await ctx.send(f"❌ Role '{role_name}' not found.", delete_after=5)
            return

        # Check if bot can assign this role
        if bot_highest_role and role.position >= bot_highest_role.position:
            await ctx.send("❌ Bot cannot assign this role (role is equal or higher than bot's highest role).", delete_after=5)
            return

        # Confirmation
        confirm_msg = await ctx.send(
            f"⚠️ **WARNING:** This will add {role.mention} to **EVERYONE** in the server ({len(ctx.guild.members)} members).\n"
            f"Type `CONFIRM` in the next 10 seconds to proceed."
        )

        def check(m: discord.Message):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.upper() == "CONFIRM"

        try:
            await self.bot.wait_for('message', timeout=10.0, check=check)
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Operation cancelled (timeout).")
            return

        await confirm_msg.edit(content=f"⏳ Adding {role.mention} to all members...")

        # Add role to all members
        success_count = 0
        failed_count = 0
        already_had_count = 0

        for member in ctx.guild.members:
            try:
                if role not in member.roles:
                    await member.add_roles(role, reason=f"Mass role assignment by {ctx.author}")
                    success_count += 1
                    await asyncio.sleep(0.3)  # Rate limit protection
                else:
                    already_had_count += 1
            except discord.Forbidden:
                failed_count += 1
            except Exception as e:
                logger.error(f"Error adding role to {member}: {e}")
                failed_count += 1

        # Results
        embed = discord.Embed(
            title="✅ Mass Role Assignment Complete",
            color=discord.Color.green(),
            timestamp=datetime.utcnow()
        )
        embed.add_field(name="Role", value=role.mention, inline=True)
        embed.add_field(name="Total Members", value=str(len(ctx.guild.members)), inline=True)
        embed.add_field(name="Successfully Added", value=str(success_count), inline=True)
        embed.add_field(name="Already Had Role", value=str(already_had_count), inline=True)
        embed.add_field(name="Failed", value=str(failed_count), inline=True)
        embed.set_footer(text=f"Executed by {ctx.author.name}", icon_url=getattr(ctx.author.display_avatar, "url", ""))

        await confirm_msg.edit(content=None, embed=embed)

    @commands.command(name="rolestrip", aliases=["stripall", "removeallroles"])
    @commands.guild_only()
    @commands.check(is_owner_check)
    async def rolestrip(self, ctx: commands.Context, member: discord.Member):
        """
        Remove ALL roles from a specific user (Owner only)
        Usage: $rolestrip @user
        """
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Get bot's highest role
        bot_member = ctx.guild.get_member(self.bot.user.id) or ctx.guild.me
        if not bot_member:
            await ctx.send("❌ Bot member not found.", delete_after=5)
            return

        bot_highest_role = bot_member.top_role

        # Get all roles the user has (excluding @everyone)
        user_roles = [role for role in member.roles if not role.is_default()]

        if not user_roles:
            await ctx.send(f"❌ {member.mention} has no roles to remove.", delete_after=5)
            return

        # Separate removable and non-removable roles
        removable_roles = []
        non_removable_roles = []

        for role in user_roles:
            if role.position < bot_highest_role.position:
                removable_roles.append(role)
            else:
                non_removable_roles.append(role)

        if not removable_roles:
            await ctx.send(f"❌ Cannot remove any roles from {member.mention} (all roles are above bot's role).", delete_after=5)
            return

        # Confirmation
        confirm_msg = await ctx.send(
            f"⚠️ **WARNING**: This will remove **ALL {len(removable_roles)} role(s)** from {member.mention}!\n\n"
            f"**Roles to be removed:**\n" +
            "\n".join([f"• {role.mention}" for role in removable_roles[:10]]) +
            (f"\n*...and {len(removable_roles) - 10} more*" if len(removable_roles) > 10 else "") +
            f"\n\nReact with ✅ to confirm or ❌ to cancel."
        )
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")

        def reaction_check(reaction: discord.Reaction, user: discord.Member):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id

        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=reaction_check)

            if str(reaction.emoji) == "❌":
                await confirm_msg.edit(content="❌ Operation cancelled.")
                return

            # Remove all roles
            await confirm_msg.edit(content=f"⏳ Removing {len(removable_roles)} role(s) from {member.mention}...")

            try:
                await member.remove_roles(*removable_roles, reason=f"All roles stripped by {ctx.author}")

                embed = discord.Embed(
                    title="✅ All Roles Removed",
                    description=f"Successfully removed **{len(removable_roles)}** role(s) from {member.mention}",
                    color=discord.Color.red(),
                    timestamp=datetime.utcnow()
                )

                # Show removed roles (limited to 10)
                removed_list = "\n".join([f"• {role.name}" for role in removable_roles[:10]])
                if len(removable_roles) > 10:
                    removed_list += f"\n*...and {len(removable_roles) - 10} more*"

                embed.add_field(name="Removed Roles", value=removed_list, inline=False)

                if non_removable_roles:
                    embed.add_field(
                        name="⚠️ Could Not Remove",
                        value="\n".join([f"• {role.name}" for role in non_removable_roles]),
                        inline=False
                    )

                embed.set_footer(text=f"Executed by {ctx.author.name}", icon_url=getattr(ctx.author.display_avatar, "url", ""))

                await confirm_msg.edit(content=None, embed=embed)

            except discord.Forbidden:
                await confirm_msg.edit(content="❌ Bot doesn't have permission to remove roles from this user.")
            except Exception as e:
                logger.error(f"Error removing roles: {e}")
                await confirm_msg.edit(content=f"❌ Error removing roles: {str(e)[:100]}")

        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Operation cancelled (timeout).")

    @rolestrip.error
    async def rolestrip_error(self, ctx: commands.Context, error: Exception):
        """Error handler for rolestrip command"""
        if isinstance(error, commands.CheckFailure):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Usage: `$rolestrip @user`", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ User not found. Please mention a valid user.", delete_after=5)
        else:
            logger.error(f"Error in rolestrip: {error}")
            await ctx.send(f"❌ An error occurred: {str(error)[:100]}", delete_after=5)

    # ==================== ERROR HANDLERS ====================

    @roleall.error
    @roleadd.error
    @roleremove.error
    @viewroles.error
    @roleinfo.error
    @rolemass.error
    async def role_commands_error(self, ctx: commands.Context, error: Exception):
        """Error handler for role commands"""
        if isinstance(error, commands.CheckFailure):
            # Silently ignore if not owner
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Missing argument. Example: `{ctx.prefix}{ctx.command.name} @user role_name`", delete_after=5)
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Invalid argument. Please mention a valid user or provide a valid role name.", delete_after=5)
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("❌ User not found. Please mention a valid user.", delete_after=5)
        else:
            logger.error(f"Error in {getattr(ctx.command, 'name', 'unknown')}: {error}")
            await ctx.send(f"❌ An error occurred: {str(error)[:100]}", delete_after=5)


async def setup(bot: commands.Bot):
    """Add the cog to the bot"""
    await bot.add_cog(RoleManager(bot))

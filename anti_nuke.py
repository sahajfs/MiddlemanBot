# anti_nuke.py
import discord
from discord.ext import commands, tasks
import asyncio
from datetime import datetime, timedelta
import logging
import json
import os

logger = logging.getLogger(__name__)

# Get owner role IDs from environment (comma-separated)
OWNER_ROLE_IDS = [int(rid.strip()) for rid in os.getenv('OWNER_ROLE_IDS', '').split(',') if rid.strip()]
ANTINUKE_LOG_CHANNEL_ID = int(os.getenv('ANTINUKE_LOG_CHANNEL_ID', 0))

class AntiNuke(commands.Cog):
    """Anti-nuke protection for channels and roles"""
    
    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db
        self.channel_protection_enabled = {}  # guild_id: bool
        self.mention_cooldown = {}  # user_id: [timestamps]
        self.cleanup_task.start()
    
    def cog_unload(self):
        self.cleanup_task.cancel()
    
    def has_owner_role(self, member: discord.Member) -> bool:
        """Check if member has any owner role"""
        return any(role.id in OWNER_ROLE_IDS for role in member.roles)
    
    def is_owner_or_admin(self, member: discord.Member) -> bool:
        """Check if member is owner role holder or admin"""
        return self.has_owner_role(member) or member.guild_permissions.administrator
    
    def has_bot_role_or_higher(self, member: discord.Member, bot_member: discord.Member) -> bool:
        """Check if member has bot role or higher"""
        return member.top_role.position >= bot_member.top_role.position
    
    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Clean up old mention records daily"""
        try:
            await self.db.cleanup_old_mentions(days=7)
            logger.info("Cleaned up old mention records")
        except Exception as e:
            logger.error(f"Error cleaning up mentions: {e}")
    
    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()
    
    async def log_antinuke_action(self, guild: discord.Guild, action: str, details: dict):
        """Log anti-nuke action to database and channel"""
        try:
            # Log to database
            await self.db.log_antinuke_action(
                guild.id,
                action,
                details.get('target_id'),
                details.get('executor_id'),
                details
            )
            
            # Log to channel if configured
            if ANTINUKE_LOG_CHANNEL_ID:
                channel = guild.get_channel(ANTINUKE_LOG_CHANNEL_ID)
                if channel:
                    embed = discord.Embed(
                        title=f"🛡️ Anti-Nuke: {action}",
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow()
                    )
                    for key, value in details.items():
                        if key not in ['target_id', 'executor_id']:
                            embed.add_field(name=key.replace('_', ' ').title(), value=str(value), inline=True)
                    await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Error logging anti-nuke action: {e}")
    
    # ==================== CHANNEL PROTECTION ====================
    
    @commands.command(name="scanchannels")
    @commands.guild_only()
    async def scan_channels(self, ctx):
        """Scan and backup all channels (Owner/Admin only)"""
        if not self.is_owner_or_admin(ctx.author):
            await ctx.send("❌ You need owner/admin permissions.", delete_after=5)
            return
        
        await ctx.message.delete()
        msg = await ctx.send("⏳ Scanning channels...")
        
        try:
            guild = ctx.guild
            backed_up = 0
            
            # Backup all channels except tickets
            for channel in guild.channels:
                # Skip ticket channels
                if 'ticket' in channel.name.lower():
                    continue
                
                # Skip categories (we'll handle them separately)
                if isinstance(channel, discord.CategoryChannel):
                    continue
                
                # Prepare channel data
                channel_data = {
                    'name': channel.name,
                    'type': channel.type.value,
                    'position': channel.position,
                    'parent_id': channel.category_id if channel.category else None,
                    'topic': getattr(channel, 'topic', None),
                    'nsfw': getattr(channel, 'nsfw', False),
                    'rate_limit_per_user': getattr(channel, 'slowmode_delay', 0),
                    'bitrate': getattr(channel, 'bitrate', None),
                    'user_limit': getattr(channel, 'user_limit', None),
                    'permission_overwrites': {}
                }
                
                # Backup permission overwrites
                for target, overwrite in channel.overwrites.items():
                    channel_data['permission_overwrites'][str(target.id)] = {
                        'type': 'role' if isinstance(target, discord.Role) else 'member',
                        'allow': str(overwrite.pair()[0].value),
                        'deny': str(overwrite.pair()[1].value)
                    }
                
                # Convert to JSON string for storage
                channel_data['permission_overwrites'] = json.dumps(channel_data['permission_overwrites'])
                
                await self.db.backup_channel(guild.id, channel.id, channel_data)
                backed_up += 1
            
            # Enable protection
            self.channel_protection_enabled[guild.id] = True
            
            embed = discord.Embed(
                title="✅ Channel Protection Active",
                description=f"Successfully backed up **{backed_up}** channels",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Protection Status", value="🟢 **ACTIVE**", inline=True)
            embed.add_field(name="Channels Protected", value=f"`{backed_up}`", inline=True)
            embed.set_footer(text=f"Activated by {ctx.author}")
            
            await msg.edit(content=None, embed=embed)
            
            await self.log_antinuke_action(guild, "channels_scanned", {
                'executor_id': ctx.author.id,
                'channels_backed_up': backed_up
            })
            
        except Exception as e:
            logger.error(f"Error scanning channels: {e}")
            await msg.edit(content=f"❌ Error: {str(e)[:100]}")
    
    @commands.command(name="delete")
    @commands.guild_only()
    async def delete_channel(self, ctx, channel: discord.TextChannel = None):
        """Safely delete a protected channel (Owner role only)"""
        if not self.has_owner_role(ctx.author):
            await ctx.send("❌ Only users with owner role can delete protected channels.", delete_after=5)
            return
        
        await ctx.message.delete()
        
        if not channel:
            await ctx.send("❌ Please mention a channel: `$delete #channel`", delete_after=5)
            return
        
        try:
            # Remove from backup first
            await self.db.delete_channel_backup(channel.id)
            
            channel_name = channel.name
            await channel.delete(reason=f"Deleted by {ctx.author} via $delete")
            
            embed = discord.Embed(
                title="🗑️ Channel Deleted",
                description=f"**#{channel_name}** was safely deleted",
                color=discord.Color.orange()
            )
            embed.set_footer(text=f"Deleted by {ctx.author}")
            
            await ctx.send(embed=embed, delete_after=10)
            
            await self.log_antinuke_action(ctx.guild, "channel_deleted", {
                'executor_id': ctx.author.id,
                'channel_name': channel_name,
                'channel_id': channel.id
            })
            
        except Exception as e:
            logger.error(f"Error deleting channel: {e}")
            await ctx.send(f"❌ Error: {str(e)[:100]}", delete_after=5)
    
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """Auto-restore deleted channels"""
        guild = channel.guild
        
        # Skip if protection not enabled
        if not self.channel_protection_enabled.get(guild.id, False):
            return
        
        # Skip ticket channels
        if 'ticket' in channel.name.lower():
            return
        
        try:
            # Get channel backup
            backup = await self.db.get_channel_backup(channel.id)
            if not backup:
                return
            
            # Get audit log to find who deleted it
            await asyncio.sleep(1)  # Wait for audit log
            deleter = None
            async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
                if entry.target.id == channel.id:
                    deleter = entry.user
                    break
            
            # Check if deleter has owner role
            if deleter:
                member = guild.get_member(deleter.id)
                if member and self.has_owner_role(member):
                    # Owner role deleted it via command, don't restore
                    return
            
            # Restore the channel
            await self.restore_channel(guild, backup, channel.id)
            
            # Log the restoration
            await self.log_antinuke_action(guild, "channel_restored", {
                'channel_name': backup['channel_name'],
                'deleted_by': deleter.id if deleter else None,
                'deleted_by_name': str(deleter) if deleter else 'Unknown'
            })
            
        except Exception as e:
            logger.error(f"Error restoring channel: {e}")
    
    async def restore_channel(self, guild: discord.Guild, backup: dict, old_channel_id: int):
        """Restore a deleted channel from backup"""
        try:
            # Parse permission overwrites
            overwrites_data = json.loads(backup['permission_overwrites'])
            overwrites = {}
            
            for target_id, perm_data in overwrites_data.items():
                target_id = int(target_id)
                if perm_data['type'] == 'role':
                    target = guild.get_role(target_id)
                else:
                    target = guild.get_member(target_id)
                
                if target:
                    overwrites[target] = discord.PermissionOverwrite.from_pair(
                        discord.Permissions(int(perm_data['allow'])),
                        discord.Permissions(int(perm_data['deny']))
                    )
            
            # Get category if exists
            category = None
            if backup['parent_id']:
                category = guild.get_channel(backup['parent_id'])
            
            # Determine channel type and create
            channel_type = discord.ChannelType(backup['channel_type'])
            
            if channel_type == discord.ChannelType.text:
                new_channel = await guild.create_text_channel(
                    name=backup['channel_name'],
                    category=category,
                    position=backup['position'],
                    topic=backup['topic'],
                    slowmode_delay=backup['rate_limit_per_user'],
                    nsfw=backup['nsfw'],
                    overwrites=overwrites,
                    reason="Anti-nuke: Channel restored"
                )
            elif channel_type == discord.ChannelType.voice:
                new_channel = await guild.create_voice_channel(
                    name=backup['channel_name'],
                    category=category,
                    position=backup['position'],
                    bitrate=backup['bitrate'] if backup['bitrate'] else 64000,
                    user_limit=backup['user_limit'] if backup['user_limit'] else 0,
                    overwrites=overwrites,
                    reason="Anti-nuke: Channel restored"
                )
            else:
                logger.warning(f"Unknown channel type: {channel_type}")
                return
            
            # Update backup with new channel ID
            await self.db.delete_channel_backup(old_channel_id)
            backup['permission_overwrites'] = json.dumps(overwrites_data)
            await self.db.backup_channel(guild.id, new_channel.id, backup)
            
            # Send notification
            embed = discord.Embed(
                title="🔄 Channel Restored",
                description=f"**#{backup['channel_name']}** was automatically restored",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Protection", value="✅ Anti-Nuke Active", inline=True)
            await new_channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error restoring channel: {e}")
    
    # ==================== ANTI-SPAM (@everyone/@here) ====================
    
    @commands.Cog.listener()
    async def on_message(self, message):
        """Monitor for @everyone/@here spam"""
        if message.author.bot or not message.guild:
            return
        
        # Check if message mentions everyone or here
        if not message.mention_everyone:
            return
        
        guild = message.guild
        member = message.author
        bot_member = guild.get_member(self.bot.user.id)
        
        # Skip if user has bot role or higher
        if self.has_bot_role_or_higher(member, bot_member):
            return
        
        # Check mention history
        try:
            recent_mentions = await self.db.get_recent_mentions(guild.id, member.id, minutes=1)
            
            # Add current mention
            await self.db.add_mention_record(guild.id, member.id)
            
            # If more than 1 mention in 1 minute, kick
            if len(recent_mentions) >= 1:
                try:
                    # Delete the message
                    await message.delete()
                    
                    # Kick the user
                    await member.kick(reason="Spamming @everyone/@here mentions")
                    
                    # Log action
                    await self.db.add_mention_record(guild.id, member.id, action_taken="kicked")
                    
                    # Send notification
                    embed = discord.Embed(
                        title="🔨 Anti-Spam Action",
                        description=f"{member.mention} was kicked for spamming @everyone/@here",
                        color=discord.Color.red(),
                        timestamp=datetime.utcnow()
                    )
                    embed.add_field(name="Mentions in 1 min", value=f"`{len(recent_mentions) + 1}`", inline=True)
                    embed.add_field(name="Action", value="**Kicked**", inline=True)
                    await message.channel.send(embed=embed, delete_after=10)
                    
                    await self.log_antinuke_action(guild, "user_kicked_spam", {
                        'user_id': member.id,
                        'user_name': str(member),
                        'mentions_count': len(recent_mentions) + 1,
                        'reason': '@everyone/@here spam'
                    })
                    
                except discord.Forbidden:
                    logger.error(f"Cannot kick {member} - insufficient permissions")
                except Exception as e:
                    logger.error(f"Error kicking user for spam: {e}")
                    
        except Exception as e:
            logger.error(f"Error checking mention spam: {e}")
    
    # ==================== ROLE MANAGEMENT ====================
    
    @commands.command(name="roleremoveall")
    @commands.guild_only()
    async def roleremoveall(self, ctx):
        """Remove all roles below bot's role from everyone (Owner only)"""
        if not self.has_owner_role(ctx.author):
            await ctx.send("❌ Only users with owner role can use this.", delete_after=5)
            return
        
        await ctx.message.delete()
        
        # Confirmation
        confirm_msg = await ctx.send(
            "⚠️ **WARNING**: This will remove ALL roles below bot's role from EVERYONE!\n"
            "React with ✅ to confirm or ❌ to cancel."
        )
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                await confirm_msg.edit(content="❌ Operation cancelled.")
                return
            
            # Proceed with removal
            await confirm_msg.edit(content="⏳ Removing roles from all members...")
            
            guild = ctx.guild
            bot_member = guild.get_member(self.bot.user.id)
            bot_role_position = bot_member.top_role.position
            
            total_removed = 0
            members_affected = 0
            
            for member in guild.members:
                if member.bot:  # Skip bots
                    continue
                
                roles_to_remove = [
                    role for role in member.roles
                    if role.position < bot_role_position and role != guild.default_role
                ]
                
                if roles_to_remove:
                    try:
                        await member.remove_roles(*roles_to_remove, reason=f"Mass role removal by {ctx.author}")
                        total_removed += len(roles_to_remove)
                        members_affected += 1
                        await asyncio.sleep(0.3)  # Rate limit protection
                    except Exception as e:
                        logger.error(f"Error removing roles from {member}: {e}")
            
            # Result
            embed = discord.Embed(
                title="✅ Role Removal Complete",
                color=discord.Color.green(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Roles Removed", value=f"`{total_removed}`", inline=True)
            embed.add_field(name="Members Affected", value=f"`{members_affected}`", inline=True)
            embed.set_footer(text=f"Executed by {ctx.author}")
            
            await confirm_msg.edit(content=None, embed=embed)
            
            await self.log_antinuke_action(guild, "mass_role_removal", {
                'executor_id': ctx.author.id,
                'roles_removed': total_removed,
                'members_affected': members_affected
            })
            
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Operation cancelled (timeout).")
    
    @commands.command(name="demote")
    @commands.guild_only()
    async def demote(self, ctx, member: discord.Member):
        """Remove all admin roles from a specific user (Owner only)"""
        if not self.has_owner_role(ctx.author):
            await ctx.send("❌ Only users with owner role can use this.", delete_after=5)
            return
        
        await ctx.message.delete()
        
        guild = ctx.guild
        bot_member = guild.get_member(self.bot.user.id)
        bot_role_position = bot_member.top_role.position
        
        # Find admin roles
        admin_roles = [
            role for role in member.roles
            if role.permissions.administrator 
            and role.position < bot_role_position
            and role != guild.default_role
        ]
        
        if not admin_roles:
            await ctx.send(f"❌ {member.mention} has no admin roles to remove.", delete_after=5)
            return
        
        try:
            await member.remove_roles(*admin_roles, reason=f"Demoted by {ctx.author}")
            
            embed = discord.Embed(
                title="✅ User Demoted",
                description=f"Removed **{len(admin_roles)}** admin role(s) from {member.mention}",
                color=discord.Color.orange(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(
                name="Roles Removed",
                value="\n".join([f"• {role.mention}" for role in admin_roles]),
                inline=False
            )
            embed.set_footer(text=f"Demoted by {ctx.author}")
            
            await ctx.send(embed=embed)
            
            await self.log_antinuke_action(guild, "user_demoted", {
                'executor_id': ctx.author.id,
                'target_id': member.id,
                'target_name': str(member),
                'roles_removed': len(admin_roles)
            })
            
        except Exception as e:
            logger.error(f"Error demoting user: {e}")
            await ctx.send(f"❌ Error: {str(e)[:100]}", delete_after=5)
    
    @commands.command(name="demoteeverymod")
    @commands.guild_only()
    async def demoteeverymod(self, ctx):
        """Remove all admin roles from everyone (Owner only)"""
        if not self.has_owner_role(ctx.author):
            await ctx.send("❌ Only users with owner role can use this.", delete_after=5)
            return
        
        await ctx.message.delete()
        
        # Confirmation
        confirm_msg = await ctx.send(
            "⚠️ **CRITICAL WARNING**: This will remove ALL admin roles from EVERYONE!\n"
            "This includes:\n"
            "• All users with administrator permission\n"
            "• Does NOT affect bots\n"
            "• Does NOT remove non-admin roles\n\n"
            "React with ✅ to confirm or ❌ to cancel."
        )
        await confirm_msg.add_reaction("✅")
        await confirm_msg.add_reaction("❌")
        
        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"] and reaction.message.id == confirm_msg.id
        
        try:
            reaction, user = await self.bot.wait_for('reaction_add', timeout=30.0, check=check)
            
            if str(reaction.emoji) == "❌":
                await confirm_msg.edit(content="❌ Operation cancelled.")
                return
            
            # Proceed
            await confirm_msg.edit(content="⏳ Demoting all moderators...")
            
            guild = ctx.guild
            bot_member = guild.get_member(self.bot.user.id)
            bot_role_position = bot_member.top_role.position
            
            total_removed = 0
            users_affected = 0
            
            for member in guild.members:
                if member.bot:  # Skip ALL bots
                    continue
                
                # Find admin roles
                admin_roles = [
                    role for role in member.roles
                    if role.permissions.administrator
                    and role.position < bot_role_position
                    and role != guild.default_role
                ]
                
                if admin_roles:
                    try:
                        await member.remove_roles(*admin_roles, reason=f"Mass demotion by {ctx.author}")
                        total_removed += len(admin_roles)
                        users_affected += 1
                        await asyncio.sleep(0.3)  # Rate limit
                    except Exception as e:
                        logger.error(f"Error demoting {member}: {e}")
            
            # Result
            embed = discord.Embed(
                title="✅ Mass Demotion Complete",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )
            embed.add_field(name="Admin Roles Removed", value=f"`{total_removed}`", inline=True)
            embed.add_field(name="Users Affected", value=f"`{users_affected}`", inline=True)
            embed.set_footer(text=f"Executed by {ctx.author}")
            
            await confirm_msg.edit(content=None, embed=embed)
            
            await self.log_antinuke_action(guild, "mass_demotion", {
                'executor_id': ctx.author.id,
                'admin_roles_removed': total_removed,
                'users_affected': users_affected
            })
            
        except asyncio.TimeoutError:
            await confirm_msg.edit(content="❌ Operation cancelled (timeout).")

async def setup(bot):
    """Load the cog"""
    await bot.add_cog(AntiNuke(bot))

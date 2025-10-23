import discord
from discord.ext import commands
from discord import app_commands
import os
from dotenv import load_dotenv
import logging
from database import Database
from datetime import datetime
import asyncio
import re

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID'))
REQUEST_CHANNEL_ID = int(os.getenv('REQUEST_CHANNEL_ID'))
LOG_CHANNEL_ID = int(os.getenv('LOG_CHANNEL_ID'))
PROOF_CHANNEL_ID = int(os.getenv('PROOF_CHANNEL_ID'))
TICKET_CATEGORY_ID = int(os.getenv('TICKET_CATEGORY_ID'))

TIER_ROLES = {
    'trial': int(os.getenv('TRIAL_MIDDLEMAN_ROLE_ID')),
    'middleman': int(os.getenv('MIDDLEMAN_ROLE_ID')),
    'pro': int(os.getenv('PRO_MIDDLEMAN_ROLE_ID')),
    'head': int(os.getenv('HEAD_MIDDLEMAN_ROLE_ID')),
    'owner': int(os.getenv('OWNER_ROLE_ID'))
}

TIER_NAMES = {
    'trial': 'Trial Middleman',
    'middleman': 'Middleman',
    'pro': 'Pro Middleman',
    'head': 'Head Middleman',
    'owner': 'Owner'
}

TIER_LIMITS = {
    'trial': 'Trades up to 2k Robux (No Fee)',
    'middleman': 'Trades up to 6k Robux (No Fee)',
    'pro': 'Trades up to 10k Robux (No Fee)',
    'head': 'Trades up to 20k Robux (No Fee)',
    'owner': 'Trades 20k+ Robux (Fee: 100 Robux or 20M Brainrot)'
}

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.presences = False
intents.typing = False

bot = commands.Bot(
    command_prefix='!',
    intents=intents,
    chunk_guilds_at_startup=False,
    max_messages=100
)
db = Database()

ticket_counter = 0
URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')
_role_cache = {}
_member_cache = {}


async def get_member_cached(guild, user_id):
    cache_key = f"{guild.id}_{user_id}"
    if cache_key in _member_cache:
        cache_time, member = _member_cache[cache_key]
        if datetime.utcnow().timestamp() - cache_time < 300:
            return member
    try:
        member = guild.get_member(user_id)
        if not member:
            member = await guild.fetch_member(user_id)
        _member_cache[cache_key] = (datetime.utcnow().timestamp(), member)
        return member
    except discord.NotFound:
        return None
    except Exception as e:
        logger.error(f"Error fetching member {user_id}: {e}")
        return None


def has_middleman_role(member: discord.Member) -> bool:
    cache_key = f"{member.id}_{member.guild.id}"
    cache_time = _role_cache.get(cache_key, {}).get('time', 0)
    if datetime.utcnow().timestamp() - cache_time < 30:
        return _role_cache[cache_key]['result']
    user_roles = [role.id for role in member.roles]
    result = any(role_id in user_roles for role_id in TIER_ROLES.values())
    _role_cache[cache_key] = {'result': result, 'time': datetime.utcnow().timestamp()}
    return result


def is_admin(member: discord.Member) -> bool:
    return member.guild_permissions.administrator


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if message.channel.category_id == TICKET_CATEGORY_ID:
        if not has_middleman_role(message.author):
            if URL_PATTERN.search(message.content):
                try:
                    await message.delete()
                    await message.channel.send(f"❌ {message.author.mention} Only middlemen can send links in this ticket.", delete_after=5)
                except discord.Forbidden:
                    logger.error(f"Missing permissions to delete message in {message.channel.name}")
    await bot.process_commands(message)


@bot.event
async def on_ready():
    logger.info(f'Logged in as {bot.user}')
    logger.info(f'Bot ID: {bot.user.id}')
    logger.info(f'Connected to {len(bot.guilds)} guild(s)')
    await db.init_db()
    for guild in bot.guilds:
        if guild.id != GUILD_ID:
            logger.warning(f"Bot is in unauthorized server: {guild.name} ({guild.id}). Leaving...")
            await guild.leave()
            logger.info(f"Left unauthorized server: {guild.name}")
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        logger.info(f"Synced {len(synced)} command(s) to guild")
    except Exception as e:
        logger.error(f"Failed to sync commands: {e}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    if guild.id != GUILD_ID:
        logger.warning(f"Bot was added to unauthorized server: {guild.name} ({guild.id}). Leaving immediately...")
        await guild.leave()
        logger.info(f"Successfully left unauthorized server: {guild.name}")
    else:
        logger.info(f"Bot joined authorized server: {guild.name}")


class TierSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
    
    @discord.ui.select(
        placeholder="Select middleman tier based on your trade value",
        options=[
            discord.SelectOption(label="Trial Middleman", value="trial", description="Up to 2k Robux (No Fee)", emoji="🌱"),
            discord.SelectOption(label="Middleman", value="middleman", description="Up to 6k Robux (No Fee)", emoji="💼"),
            discord.SelectOption(label="Pro Middleman", value="pro", description="Up to 10k Robux (No Fee)", emoji="⚡"),
            discord.SelectOption(label="Head Middleman", value="head", description="Up to 20k Robux (No Fee)", emoji="👑"),
            discord.SelectOption(label="Owner", value="owner", description="20k+ Robux (Fee: 100 Robux/20M Brainrot)", emoji="💎")
        ]
    )
    async def tier_select_callback(self, interaction: discord.Interaction, select: discord.ui.Select):
        selected_tier = select.values[0]
        modal = TradeDetailsModal(selected_tier)
        await interaction.response.send_modal(modal)


class TradeDetailsModal(discord.ui.Modal, title="Fill out the Format"):
    def __init__(self, tier):
        super().__init__()
        self.tier = tier
        if tier == 'owner':
            self.title = "Owner Tier (Fee Required)"
    
    trader = discord.ui.TextInput(label="Who's your Trader?", placeholder="EX: 9cv or 705256895711019041", required=True, max_length=100)
    giving = discord.ui.TextInput(label="What are you giving?", placeholder="EX: Frost Dragon (BE SPECIFIC)", required=True, max_length=200)
    receiving = discord.ui.TextInput(label="What is the other trader giving?", placeholder="EX: 4k Robux (BE SPECIFIC)", required=True, max_length=200)
    
    async def on_submit(self, interaction: discord.Interaction):
        has_duplicate = await db.check_duplicate_ticket(interaction.user.id, str(self.trader.value), self.tier)
        if has_duplicate:
            await interaction.response.send_message("❌ You already have an open ticket for the same trader and tier. Please wait for your current ticket to be processed.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            guild = interaction.guild
            category = guild.get_channel(TICKET_CATEGORY_ID)
            global ticket_counter
            ticket_counter += 1
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True)
            }
            owner_role = guild.get_role(TIER_ROLES['owner'])
            if owner_role:
                overwrites[owner_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True)
            tier_hierarchy = ['trial', 'middleman', 'pro', 'head', 'owner']
            tier_index = tier_hierarchy.index(self.tier)
            for tier_key in tier_hierarchy[tier_index:]:
                role_id = TIER_ROLES.get(tier_key)
                if role_id:
                    role = guild.get_role(role_id)
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
            channel = await category.create_text_channel(name=f"mm-{self.tier}-{ticket_counter}", overwrites=overwrites)
            ticket_id = await db.create_ticket(channel.id, interaction.user.id, str(self.trader.value), str(self.giving.value), str(self.receiving.value), self.tier)
            embed = discord.Embed(title="Middleman Request", description=f"✅ By creating a ticket you have read & agreed to our [terms](https://discord.com/channels/{GUILD_ID})", color=discord.Color.blue(), timestamp=datetime.utcnow())
            embed.add_field(name="Requester", value=interaction.user.mention, inline=True)
            embed.add_field(name="Trader", value=f"{self.trader.value}", inline=True)
            embed.add_field(name="Tier", value=f"{TIER_NAMES.get(self.tier, self.tier.title())}\n*{TIER_LIMITS.get(self.tier)}*", inline=False)
            embed.add_field(name=f"{interaction.user.display_name} is giving", value=f"{self.giving.value}", inline=False)
            embed.add_field(name="Other trader is giving", value=f"{self.receiving.value}", inline=False)
            if self.tier == 'owner':
                embed.add_field(name="⚠ Important", value="This trade requires a middleman fee payment before processing.\nPlease wait for the Owner to provide payment details.", inline=False)
            embed.set_footer(text=f"Ticket #{ticket_counter}")
            view = TicketActionsView()
            role_id = TIER_ROLES.get(self.tier)
            role_mention = f"<@&{role_id}>" if role_id else ""
            mm_note = "mm use only:\n┕ want more info on your mm? run $mminfo (mm)"
            await channel.send(content=f"{role_mention}\n\n{mm_note}", embed=embed, view=view)
            vouch_embed = discord.Embed(description="❗ Vouching your middleman after the trade is required ❗", color=discord.Color.red())
            await channel.send(embed=vouch_embed)
            asyncio.create_task(db.log_action(ticket_id, "created", interaction.user.id))
            log_channel = guild.get_channel(LOG_CHANNEL_ID)
            if log_channel:
                log_embed = discord.Embed(title="📝 New Ticket Created", color=discord.Color.green(), timestamp=datetime.utcnow())
                log_embed.add_field(name="Ticket", value=f"#{ticket_counter}", inline=True)
                log_embed.add_field(name="Channel", value=channel.mention, inline=True)
                log_embed.add_field(name="Requester", value=interaction.user.mention, inline=True)
                log_embed.add_field(name="Tier", value=TIER_NAMES.get(self.tier), inline=True)
                asyncio.create_task(log_channel.send(embed=log_embed))
            await interaction.followup.send(f"✅ Ticket created! Please head to {channel.mention}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error creating ticket: {e}")
            await interaction.followup.send("❌ An error occurred while creating your ticket. Please contact an administrator.", ephemeral=True)


class TicketActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="claim_ticket")
    async def claim_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = await db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("❌ Ticket not found.", ephemeral=True)
            return
        has_permission = False
        tier_hierarchy = ['trial', 'middleman', 'pro', 'head', 'owner']
        tier_index = tier_hierarchy.index(ticket['tier'])
        user_roles = [role.id for role in interaction.user.roles]
        for tier_key in tier_hierarchy[tier_index:]:
            role_id = TIER_ROLES.get(tier_key)
            if role_id and role_id in user_roles:
                has_permission = True
                break
        if not has_permission:
            required_tier = TIER_NAMES.get(ticket['tier'])
            await interaction.response.send_message(f"❌ You need {required_tier} role or higher to claim this ticket.\nThis ticket requires: {TIER_LIMITS.get(ticket['tier'])}", ephemeral=True)
            return
        if ticket['claimed_by']:
            claimer = await get_member_cached(interaction.guild, ticket['claimed_by'])
            claimer_mention = claimer.mention if claimer else f"<@{ticket['claimed_by']}>"
            await interaction.response.send_message(f"❌ This ticket has already been claimed by {claimer_mention}", ephemeral=True)
            return
        await db.claim_ticket(interaction.channel.id, interaction.user.id)
        claim_embed = discord.Embed(description=f"✅ @{interaction.user.name} will be your middleman", color=discord.Color.green())
        requester = await get_member_cached(interaction.guild, ticket['requester_id'])
        requester_mention = requester.mention if requester else f"<@{ticket['requester_id']}>"
        trader_text = ticket['trader_username']
        claim_embed.add_field(name="Participants", value=f"{requester_mention} {trader_text}", inline=False)
        if ticket['tier'] == 'owner':
            claim_embed.add_field(name="💰 Fee Payment Required", value="Please ensure the middleman fee is paid before proceeding with the trade.", inline=False)
        await interaction.response.send_message(embed=claim_embed)
        message = await interaction.original_response()
        try:
            await message.pin()
        except discord.HTTPException:
            pass
        asyncio.create_task(db.log_action(ticket['ticket_id'], "claimed", interaction.user.id))
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(title="✅ Ticket Claimed", color=discord.Color.green(), timestamp=datetime.utcnow())
            log_embed.add_field(name="Ticket", value=interaction.channel.mention, inline=True)
            log_embed.add_field(name="Claimed by", value=interaction.user.mention, inline=True)
            log_embed.add_field(name="Tier", value=TIER_NAMES.get(ticket['tier']), inline=True)
            asyncio.create_task(log_channel.send(embed=log_embed))


class CreateTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label="Create Middleman Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket_button")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = TierSelectView()
        await interaction.response.send_message("Please select the middleman tier for your trade:", view=view, ephemeral=True)


@bot.tree.command(name="setup", description="Setup the middleman request button (Admin only)")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def setup(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You need Administrator permissions to use this command.", ephemeral=True)
        return
    embed = discord.Embed(title="🛡 Middleman Services", description=("Click the button below to request a middleman for your trade.\n\nAvailable Tiers:\n🌱 Trial Middleman - Up to 2k Robux (No Fee)\n💼 Middleman - Up to 6k Robux (No Fee)\n⚡ Pro Middleman - Up to 10k Robux (No Fee)\n👑 Head Middleman - Up to 20k Robux (No Fee)\n💎 Owner - 20k+ Robux (Fee: 100 Robux or 20M Brainrot)\n\nSelect the appropriate tier based on your trade value."), color=discord.Color.blue())
    view = CreateTicketView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Setup complete!", ephemeral=True)


@bot.tree.command(name="proof", description="Mark trade as complete and send proof (Middleman only)")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def proof(interaction: discord.Interaction):
    ticket = await db.get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
        return
    if not has_middleman_role(interaction.user):
        await interaction.response.send_message("❌ Only middlemen can use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        proof_channel = interaction.guild.get_channel(PROOF_CHANNEL_ID)
        if not proof_channel:
            await interaction.followup.send("❌ Proof channel not found. Please contact an administrator.", ephemeral=True)
            return
        requester = await get_member_cached(interaction.guild, ticket['requester_id'])
        requester_mention = requester.mention if requester else f"<@{ticket['requester_id']}>"
        requester_name = requester.display_name if requester else "Unknown User"
        proof_embed = discord.Embed(title="✅ Trade Completed", description=f"Trade successfully completed by {interaction.user.mention}", color=discord.Color.green(), timestamp=datetime.utcnow())
        proof_embed.add_field(name="Middleman", value=interaction.user.mention, inline=True)
        proof_embed.add_field(name="Requester", value=requester_mention, inline=True)
        proof_embed.add_field(name="Trader", value=f"{ticket['trader_username']}", inline=True)
        proof_embed.add_field(name="Tier", value=TIER_NAMES.get(ticket['tier']), inline=True)
        proof_embed.add_field(name="Ticket Channel", value=interaction.channel.mention, inline=True)
        proof_embed.add_field(name=f"{requester_name} gave", value=f"{ticket['giving']}", inline=False)
        proof_embed.add_field(name="Other trader gave", value=f"{ticket['receiving']}", inline=False)
        proof_embed.set_footer(text=f"Ticket #{ticket['ticket_id']}")
        await proof_channel.send(embed=proof_embed)
        asyncio.create_task(db.log_action(ticket['ticket_id'], "proof_submitted", interaction.user.id))
        await interaction.followup.send("✅ Trade proof has been sent to the proof channel!", ephemeral=True)
        success_embed = discord.Embed(description=f"✅ Trade marked as complete by {interaction.user.mention}\nProof has been submitted!", color=discord.Color.green())
        await interaction.channel.send(embed=success_embed)
    except Exception as e:
        logger.error(f"Error submitting proof: {e}")
        await interaction.followup.send("❌ An error occurred while submitting proof.", ephemeral=True)


@bot.tree.command(name="close", description="Close the current ticket instantly (Middleman only)")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def close_ticket_cmd(interaction: discord.Interaction):
    ticket = await db.get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
        return
    if not has_middleman_role(interaction.user):
        await interaction.response.send_message("❌ Only middlemen can close tickets.", ephemeral=True)
        return
    await interaction.response.send_message("🔒 Closing ticket now...", ephemeral=True)
    await db.close_ticket(interaction.channel.id)
    asyncio.create_task(db.log_action(ticket['ticket_id'], "closed", interaction.user.id))
    log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
    if log_channel:
        log_embed = discord.Embed(title="🔒 Ticket Closed", color=discord.Color.orange(), timestamp=datetime.utcnow())
        log_embed.add_field(name="Ticket", value=interaction.channel.name, inline=True)
        log_embed.add_field(name="Closed by", value=interaction.user.mention, inline=True)
        asyncio.create_task(log_channel.send(embed=log_embed))
    await asyncio.sleep(1)
    await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")


@bot.tree.command(name="add", description="Add a user to the ticket")
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(user="The user to add to this ticket")
async def add_user(interaction: discord.Interaction, user: discord.Member):
    ticket = await db.get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
        return
    has_permission = False
    if ticket['claimed_by'] == interaction.user.id:
        has_permission = True
    elif ticket['requester_id'] == interaction.user.id:
        has_permission = True
    elif has_middleman_role(interaction.user):
        has_permission = True
    if not has_permission:
        await interaction.response.send_message("❌ You don't have permission to add users to this ticket.", ephemeral=True)
        return
    if interaction.channel.permissions_for(user).view_channel:
        await interaction.response.send_message(f"❌ {user.mention} already has access to this ticket.", ephemeral=True)
        return
    try:
        await interaction.channel.set_permissions(user, view_channel=True, send_messages=True, read_message_history=True)
        asyncio.create_task(db.log_action(ticket['ticket_id'], f"user_added:{user.id}", interaction.user.id))
        embed = discord.Embed(description=f"✅ {user.mention} has been added to the ticket by {interaction.user.mention}", color=discord.Color.green())
        await interaction.response.send_message(embed=embed)
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(title="➕ User Added to Ticket", color=discord.Color.blue(), timestamp=datetime.utcnow())
            log_embed.add_field(name="Ticket", value=interaction.channel.mention, inline=True)
            log_embed.add_field(name="Added User", value=user.mention, inline=True)
            log_embed.add_field(name="Added By", value=interaction.user.mention, inline=True)
            asyncio.create_task(log_channel.send(embed=log_embed))
    except Exception as e:
        logger.error(f"Error adding user to ticket: {e}")
        await interaction.response.send_message("❌ An error occurred while adding the user.", ephemeral=True)


@bot.tree.command(name="remove", description="Remove a user from the ticket")
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(user="The user to remove from this ticket")
async def remove_user(interaction: discord.Interaction, user: discord.Member):
    ticket = await db.get_ticket_by_channel(interaction.channel.id)
    if not ticket:
        await interaction.response.send_message("❌ This command can only be used in ticket channels.", ephemeral=True)
        return
    has_permission = False
    if ticket['claimed_by'] == interaction.user.id:
        has_permission = True
    elif ticket['requester_id'] == interaction.user.id:
        has_permission = True
    elif has_middleman_role(interaction.user):
        has_permission = True
    if not has_permission:
        await interaction.response.send_message("❌ You don't have permission to remove users from this ticket.", ephemeral=True)
        return
    if user.id == ticket['requester_id']:
        await interaction.response.send_message("❌ You cannot remove the ticket requester.", ephemeral=True)
        return
    if user.id == ticket['claimed_by']:
        await interaction.response.send_message("❌ You cannot remove the assigned middleman.", ephemeral=True)
        return
    try:
        await interaction.channel.set_permissions(user, overwrite=None)
        asyncio.create_task(db.log_action(ticket['ticket_id'], f"user_removed:{user.id}", interaction.user.id))
        embed = discord.Embed(description=f"✅ {user.mention} has been removed from the ticket by {interaction.user.mention}", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)
        log_channel = interaction.guild.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(title="➖ User Removed from Ticket", color=discord.Color.orange(), timestamp=datetime.utcnow())
            log_embed.add_field(name="Ticket", value=interaction.channel.mention, inline=True)
            log_embed.add_field(name="Removed User", value=user.mention, inline=True)
            log_embed.add_field(name="Removed By", value=interaction.user.mention, inline=True)
            asyncio.create_task(log_channel.send(embed=log_embed))
    except Exception as e:
        logger.error(f"Error removing user from ticket: {e}")
        await interaction.response.send_message("❌ An error occurred while removing the user.", ephemeral=True)


@bot.tree.command(name="list_tickets", description="List all open tickets (Admin only)")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def list_tickets(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You need Administrator permissions to use this command.", ephemeral=True)
        return
    tickets = await db.get_open_tickets()
    if not tickets:
        await interaction.response.send_message("No open tickets found.", ephemeral=True)
        return
    embed = discord.Embed(title="📋 Open Tickets", color=discord.Color.blue(), timestamp=datetime.utcnow())
    for ticket in tickets[:25]:
        channel = interaction.guild.get_channel(ticket['channel_id'])
        channel_mention = channel.mention if channel else "Channel deleted"
        claimed_status = "✅ Claimed" if ticket['claimed_by'] else "⏳ Unclaimed"
        tier_info = f"Tier: {TIER_NAMES.get(ticket['tier'])}"
        embed.add_field(name=f"Ticket #{ticket['ticket_id']}", value=f"{channel_mention}\n{tier_info}\nStatus: {claimed_status}", inline=True)
    if len(tickets) > 25:
        embed.set_footer(text=f"Showing 25 of {len(tickets)} tickets")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="export_ticket", description="Export ticket transcript (Admin only)")
@app_commands.guilds(discord.Object(id=GUILD_ID))
@app_commands.describe(ticket_number="The ticket number to export")
async def export_ticket(interaction: discord.Interaction, ticket_number: int):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You need Administrator permissions to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    ticket = await db.get_ticket_by_id(ticket_number)
    if not ticket:
        await interaction.followup.send("❌ Ticket not found.", ephemeral=True)
        return
    channel = interaction.guild.get_channel(ticket['channel_id'])
    if not channel:
        await interaction.followup.send("❌ Ticket channel not found.", ephemeral=True)
        return
    try:
        transcript = f"TICKET #{ticket_number} TRANSCRIPT\n"
        transcript += f"{'='*50}\n"
        transcript += f"Requester: {ticket['requester_id']}\n"
        transcript += f"Trader: {ticket['trader_username']}\n"
        transcript += f"Tier: {TIER_NAMES.get(ticket['tier'])}\n"
        transcript += f"Giving: {ticket['giving']}\n"
        transcript += f"Receiving: {ticket['receiving']}\n"
        transcript += f"Created: {ticket['created_at']}\n"
        transcript += f"{'='*50}\n\n"
        messages = []
        async for message in channel.history(limit=None, oldest_first=True):
            messages.append(f"[{message.created_at}] {message.author}: {message.content}")
        transcript += "\n".join(messages)
        filename = f"ticket_{ticket_number}_transcript.txt"
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(transcript)
        await interaction.followup.send(f"✅ Transcript exported for Ticket #{ticket_number}", file=discord.File(filename), ephemeral=True)
        os.remove(filename)
    except Exception as e:
        logger.error(f"Error exporting ticket: {e}")
        await interaction.followup.send("❌ An error occurred while exporting the ticket.", ephemeral=True)


@bot.tree.command(name="stats", description="View middleman statistics (Admin only)")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def stats(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        await interaction.response.send_message("❌ You need Administrator permissions to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        open_tickets = await db.get_open_tickets()
        all_tickets = await db.get_all_tickets_count()
        embed = discord.Embed(title="📊 Middleman Bot Statistics", color=discord.Color.blue(), timestamp=datetime.utcnow())
        embed.add_field(name="Total Tickets", value=str(all_tickets), inline=True)
        embed.add_field(name="Open Tickets", value=str(len(open_tickets)), inline=True)
        embed.add_field(name="Closed Tickets", value=str(all_tickets - len(open_tickets)), inline=True)
        tier_counts = {}
        for ticket in open_tickets:
            tier = ticket['tier']
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        if tier_counts:
            tier_breakdown = "\n".join([f"{TIER_NAMES.get(tier, tier)}: {count}" for tier, count in tier_counts.items()])
            embed.add_field(name="Open Tickets by Tier", value=tier_breakdown, inline=False)
        embed.set_footer(text=f"Bot Uptime: {bot.user.name}")
        await interaction.followup.send(embed=embed, ephemeral=True)
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        await interaction.followup.send("❌ An error occurred while fetching statistics.", ephemeral=True)


@bot.tree.command(name="help", description="Display help information about the bot")
@app_commands.guilds(discord.Object(id=GUILD_ID))
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="🛡 Middleman Bot Help", description="Here are all the available commands:", color=discord.Color.blue())
    if is_admin(interaction.user):
        embed.add_field(name="Admin Commands", value=("/setup - Setup the ticket creation button\n/list_tickets - List all open tickets\n/export_ticket - Export a ticket transcript\n/stats - View bot statistics"), inline=False)
    if has_middleman_role(interaction.user):
        embed.add_field(name="Middleman Commands", value=("/proof - Mark trade as complete and send proof\n/close - Close the current ticket\n/add - Add a user to the ticket\n/remove - Remove a user from the ticket"), inline=False)
    embed.add_field(name="User Commands", value=("Click the Create Middleman Ticket button to start a trade\nSelect your tier based on trade value\nFill out the required information"), inline=False)
    embed.add_field(name="Tier Information", value=("🌱 Trial Middleman - Up to 2k Robux (No Fee)\n💼 Middleman - Up to 6k Robux (No Fee)\n⚡ Pro Middleman - Up to 10k Robux (No Fee)\n👑 Head Middleman - Up to 20k Robux (No Fee)\n💎 Owner - 20k+ Robux (Fee: 100 Robux or 20M Brainrot)"), inline=False)
    embed.set_footer(text="For support, contact an administrator")
    await interaction.response.send_message(embed=embed, ephemeral=True)


if __name__ == "__main__":
    bot.run(TOKEN)
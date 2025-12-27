import asyncpg
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None
        self.database_url = os.getenv('DATABASE_URL')
    
    async def connect(self):
        """Connect to Supabase PostgreSQL database"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            logger.info("✅ Connected to Supabase")
        except Exception as e:
            logger.error(f"❌ Failed to connect to Supabase: {e}")
            raise
    
    async def init_db(self):
        """Initialize database tables"""
        try:
            async with self.pool.acquire() as conn:
                # Create setup_messages table for persistent buttons
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS setup_messages (
                        id SERIAL PRIMARY KEY,
                        message_type TEXT NOT NULL UNIQUE,
                        channel_id BIGINT NOT NULL,
                        message_id BIGINT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"Error initializing database: {e}")
    
    # ==================== SETUP MESSAGES (PERSISTENT) ====================
    
    async def save_setup_message(self, message_type: str, channel_id: int, message_id: int):
        """Save or update setup message for persistence"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO setup_messages (message_type, channel_id, message_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (message_type) 
                DO UPDATE SET channel_id = $2, message_id = $3
            """, message_type, channel_id, message_id)
    
    async def get_setup_message(self, message_type: str):
        """Get setup message info"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT channel_id, message_id FROM setup_messages 
                WHERE message_type = $1
            """, message_type)
            return dict(row) if row else None
    
    # ==================== MM TICKETS ====================
    
    async def create_mm_ticket(self, channel_id, requester_id, trader_username, giving, receiving, can_join_links, tip, tier):
        """Create a new MM ticket"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO middleman_tickets (channel_id, requester_id, trader_username, giving, receiving, can_join_links, tip, tier)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING ticket_id
            """, channel_id, requester_id, trader_username, giving, receiving, can_join_links, tip, tier)
            return row['ticket_id']
    
    async def get_mm_ticket_by_channel(self, channel_id):
        """Get MM ticket by channel ID"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM middleman_tickets WHERE channel_id = $1
                """, channel_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting MM ticket: {e}")
            return None
    
    async def claim_mm_ticket(self, channel_id, user_id):
        """Mark MM ticket as claimed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE middleman_tickets SET claimed_by = $1 WHERE channel_id = $2
            """, user_id, channel_id)
    
    async def unclaim_mm_ticket(self, channel_id):
        """Mark MM ticket as unclaimed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE middleman_tickets SET claimed_by = NULL WHERE channel_id = $1
            """, channel_id)
    
    async def close_mm_ticket(self, channel_id):
        """Mark MM ticket as closed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE middleman_tickets SET status = 'closed', closed_at = NOW() WHERE channel_id = $1
            """, channel_id)
    
    async def get_open_mm_tickets(self):
        """Get all open MM tickets"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM middleman_tickets WHERE status = 'open' ORDER BY created_at DESC
            """)
            return [dict(row) for row in rows]
    
    async def get_all_mm_tickets_count(self):
        """Get total count of all MM tickets"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) FROM middleman_tickets")
            return row['count']
    
    # ==================== PVP TICKETS ====================
    
    async def create_pvp_ticket(self, channel_id, requester_id, opponent_username, betting, opponent_betting, can_join_links, pvp_type, tip, tier):
        """Create a new PvP ticket"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    INSERT INTO pvp_tickets (channel_id, requester_id, opponent_username, betting, opponent_betting, can_join_links, pvp_type, tip, tier)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING ticket_id
                """, channel_id, requester_id, opponent_username, betting, opponent_betting, can_join_links, pvp_type, tip, tier)
                return row['ticket_id']
        except Exception as e:
            logger.error(f"Error creating PvP ticket: {e}")
            raise
    
    async def get_pvp_ticket_by_channel(self, channel_id):
        """Get PvP ticket by channel ID"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("""
                    SELECT * FROM pvp_tickets WHERE channel_id = $1
                """, channel_id)
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error getting PvP ticket: {e}")
            return None
    
    async def claim_pvp_ticket(self, channel_id, user_id):
        """Mark PvP ticket as claimed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pvp_tickets SET claimed_by = $1 WHERE channel_id = $2
            """, user_id, channel_id)
    
    async def unclaim_pvp_ticket(self, channel_id):
        """Mark PvP ticket as unclaimed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pvp_tickets SET claimed_by = NULL WHERE channel_id = $1
            """, channel_id)
    
    async def close_pvp_ticket(self, channel_id):
        """Mark PvP ticket as closed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pvp_tickets SET status = 'closed', closed_at = NOW() WHERE channel_id = $1
            """, channel_id)
    
    async def get_open_pvp_tickets(self):
        """Get all open PvP tickets"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM pvp_tickets WHERE status = 'open' ORDER BY created_at DESC
                """)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting open PvP tickets: {e}")
            return []
    
    async def get_all_pvp_tickets_count(self):
        """Get total count of all PvP tickets"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow("SELECT COUNT(*) FROM pvp_tickets")
                return row['count']
        except Exception as e:
            logger.error(f"Error counting PvP tickets: {e}")
            return 0
    
    # ==================== CONFIRMATIONS ====================
    
    async def add_confirmation(self, ticket_id, ticket_type, user_id):
        """Add a confirmation for a ticket"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ticket_confirmations (ticket_id, ticket_type, user_id)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (ticket_id, ticket_type, user_id) DO NOTHING
                """, ticket_id, ticket_type, user_id)
        except Exception as e:
            logger.error(f"Error adding confirmation: {e}")
            raise
    
    async def get_confirmations(self, ticket_id, ticket_type):
        """Get all confirmations for a ticket"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT * FROM ticket_confirmations WHERE ticket_id = $1 AND ticket_type = $2
                """, ticket_id, ticket_type)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting confirmations: {e}")
            return []
    
    # ==================== PROOFS & STATS ====================
    
    async def add_proof(self, ticket_id, ticket_type, middleman_id):
        """Add a proof record for completed ticket"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO mm_proofs (ticket_id, ticket_type, middleman_id)
                    VALUES ($1, $2, $3)
                """, ticket_id, ticket_type, middleman_id)
        except Exception as e:
            logger.error(f"Error adding proof: {e}")
            raise
    
    async def get_mm_stats(self, middleman_id):
        """Get statistics for a specific middleman"""
        try:
            async with self.pool.acquire() as conn:
                mm_count = await conn.fetchrow("""
                    SELECT COUNT(*) FROM mm_proofs WHERE middleman_id = $1 AND ticket_type = 'mm'
                """, middleman_id)
                pvp_count = await conn.fetchrow("""
                    SELECT COUNT(*) FROM mm_proofs WHERE middleman_id = $1 AND ticket_type = 'pvp'
                """, middleman_id)
                total = (mm_count['count'] if mm_count else 0) + (pvp_count['count'] if pvp_count else 0)
                return {
                    'total': total,
                    'mm': mm_count['count'] if mm_count else 0,
                    'pvp': pvp_count['count'] if pvp_count else 0
                }
        except Exception as e:
            logger.error(f"Error getting MM stats: {e}")
            return {'total': 0, 'mm': 0, 'pvp': 0}
    
    async def get_mm_rankings(self):
        """Get rankings of all middlemen by total tickets completed"""
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT middleman_id, COUNT(*) as total_proofs
                    FROM mm_proofs
                    GROUP BY middleman_id
                    HAVING COUNT(*) >= 1
                    ORDER BY total_proofs DESC
                """)
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Error getting MM rankings: {e}")
            return []
    
    # ==================== LOGS ====================
    
    async def log_action(self, ticket_id, ticket_type, action, user_id):
        """Log an action on a ticket"""
        try:
            async with self.pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO ticket_logs (ticket_id, ticket_type, action, user_id)
                    VALUES ($1, $2, $3, $4)
                """, ticket_id, ticket_type, action, user_id)
        except Exception as e:
            logger.error(f"Error logging action: {e}")
    
    # ==================== HEALTH CHECK ====================
    
    async def health_check(self):
        """Check database health"""
        try:
            async with self.pool.acquire() as conn:
                await conn.fetchrow("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"Database health check failed: {e}")
            return False

# Add these methods to your Database class in database.py

# ==================== ANTI-NUKE: CHANNEL BACKUPS ====================

async def backup_channel(self, guild_id: int, channel_id: int, channel_data: dict):
    """Backup a channel's configuration"""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO channel_backups (
                guild_id, channel_id, channel_name, channel_type, position,
                parent_id, topic, nsfw, rate_limit_per_user, bitrate, 
                user_limit, permission_overwrites
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (channel_id) 
            DO UPDATE SET 
                channel_name = $3, position = $5, parent_id = $6,
                topic = $7, nsfw = $8, rate_limit_per_user = $9,
                permission_overwrites = $12, updated_at = NOW()
        """, 
        guild_id, channel_id, channel_data['name'], channel_data['type'],
        channel_data['position'], channel_data['parent_id'], channel_data['topic'],
        channel_data['nsfw'], channel_data['rate_limit_per_user'],
        channel_data.get('bitrate'), channel_data.get('user_limit'),
        channel_data['permission_overwrites'])

async def get_channel_backup(self, channel_id: int):
    """Get channel backup data"""
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM channel_backups WHERE channel_id = $1
        """, channel_id)
        return dict(row) if row else None

async def get_all_channel_backups(self, guild_id: int):
    """Get all channel backups for a guild"""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM channel_backups WHERE guild_id = $1
        """, guild_id)
        return [dict(row) for row in rows]

async def delete_channel_backup(self, channel_id: int):
    """Delete a channel backup"""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM channel_backups WHERE channel_id = $1
        """, channel_id)

async def clear_guild_channel_backups(self, guild_id: int):
    """Clear all channel backups for a guild"""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM channel_backups WHERE guild_id = $1
        """, guild_id)

# ==================== ANTI-NUKE: ROLE BACKUPS ====================

async def backup_role(self, guild_id: int, role_id: int, role_data: dict):
    """Backup a role's configuration"""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO role_backups (
                guild_id, role_id, role_name, color, hoist,
                position, permissions, mentionable
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (role_id)
            DO UPDATE SET
                role_name = $3, color = $4, hoist = $5,
                position = $6, permissions = $7, mentionable = $8,
                updated_at = NOW()
        """,
        guild_id, role_id, role_data['name'], role_data['color'],
        role_data['hoist'], role_data['position'], role_data['permissions'],
        role_data['mentionable'])

async def get_all_role_backups(self, guild_id: int):
    """Get all role backups for a guild"""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM role_backups WHERE guild_id = $1
        """, guild_id)
        return [dict(row) for row in rows]

# ==================== ANTI-NUKE: MENTION TRACKING ====================

async def add_mention_record(self, guild_id: int, user_id: int, action_taken: str = None):
    """Record an @everyone/@here mention"""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mention_tracker (guild_id, user_id, action_taken)
            VALUES ($1, $2, $3)
        """, guild_id, user_id, action_taken)

async def get_recent_mentions(self, guild_id: int, user_id: int, minutes: int = 1):
    """Get recent mentions by a user within X minutes"""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM mention_tracker
            WHERE guild_id = $1 AND user_id = $2
            AND mention_time > NOW() - INTERVAL '%s minutes'
            ORDER BY mention_time DESC
        """ % minutes, guild_id, user_id)
        return [dict(row) for row in rows]

async def cleanup_old_mentions(self, days: int = 7):
    """Clean up old mention records"""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            DELETE FROM mention_tracker
            WHERE mention_time < NOW() - INTERVAL '%s days'
        """ % days)

# ==================== ANTI-NUKE: LOGGING ====================

async def log_antinuke_action(self, guild_id: int, action_type: str, 
                              target_id: int = None, executor_id: int = None, 
                              details: dict = None):
    """Log an anti-nuke action"""
    async with self.pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO antinuke_logs (guild_id, action_type, target_id, executor_id, details)
            VALUES ($1, $2, $3, $4, $5)
        """, guild_id, action_type, target_id, executor_id, details)

async def get_antinuke_logs(self, guild_id: int, limit: int = 50):
    """Get recent anti-nuke logs"""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM antinuke_logs
            WHERE guild_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, guild_id, limit)
        return [dict(row) for row in rows]

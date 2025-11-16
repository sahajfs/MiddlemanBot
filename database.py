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
        """Initialize database tables (already created in Supabase)"""
        logger.info("✅ Database initialized")
    
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
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM middleman_tickets WHERE channel_id = $1
            """, channel_id)
            return dict(row) if row else None
    
    async def claim_mm_ticket(self, channel_id, user_id):
        """Mark MM ticket as claimed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE middleman_tickets SET claimed_by = $1 WHERE channel_id = $2
            """, user_id, channel_id)
    
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
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO pvp_tickets (channel_id, requester_id, opponent_username, betting, opponent_betting, can_join_links, pvp_type, tip, tier)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                RETURNING ticket_id
            """, channel_id, requester_id, opponent_username, betting, opponent_betting, can_join_links, pvp_type, tip, tier)
            return row['ticket_id']
    
    async def get_pvp_ticket_by_channel(self, channel_id):
        """Get PvP ticket by channel ID"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM pvp_tickets WHERE channel_id = $1
            """, channel_id)
            return dict(row) if row else None
    
    async def claim_pvp_ticket(self, channel_id, user_id):
        """Mark PvP ticket as claimed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pvp_tickets SET claimed_by = $1 WHERE channel_id = $2
            """, user_id, channel_id)
    
    async def close_pvp_ticket(self, channel_id):
        """Mark PvP ticket as closed"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE pvp_tickets SET status = 'closed', closed_at = NOW() WHERE channel_id = $1
            """, channel_id)
    
    async def get_open_pvp_tickets(self):
        """Get all open PvP tickets"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM pvp_tickets WHERE status = 'open' ORDER BY created_at DESC
            """)
            return [dict(row) for row in rows]
    
    async def get_all_pvp_tickets_count(self):
        """Get total count of all PvP tickets"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) FROM pvp_tickets")
            return row['count']
    
    # ==================== CONFIRMATIONS ====================
    
    async def add_confirmation(self, ticket_id, ticket_type, user_id):
        """Add a confirmation for a ticket"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ticket_confirmations (ticket_id, ticket_type, user_id)
                VALUES ($1, $2, $3)
            """, ticket_id, ticket_type, user_id)
    
    async def get_confirmations(self, ticket_id, ticket_type):
        """Get all confirmations for a ticket"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM ticket_confirmations WHERE ticket_id = $1 AND ticket_type = $2
            """, ticket_id, ticket_type)
            return [dict(row) for row in rows]
    
    # ==================== PROOFS & STATS ====================
    
    async def add_proof(self, ticket_id, ticket_type, middleman_id):
        """Add a proof record for completed ticket"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO mm_proofs (ticket_id, ticket_type, middleman_id)
                VALUES ($1, $2, $3)
            """, ticket_id, ticket_type, middleman_id)
    
    async def get_mm_stats(self, middleman_id):
        """Get statistics for a specific middleman"""
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
    
    async def get_mm_rankings(self):
        """Get rankings of all middlemen by total tickets completed"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT middleman_id, COUNT(*) as total_proofs
                FROM mm_proofs
                GROUP BY middleman_id
                HAVING COUNT(*) >= 1
                ORDER BY total_proofs DESC
            """)
            return [dict(row) for row in rows]
    
    # ==================== LOGS ====================
    
    async def log_action(self, ticket_id, ticket_type, action, user_id):
        """Log an action on a ticket"""
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO ticket_logs (ticket_id, ticket_type, action, user_id)
                VALUES ($1, $2, $3, $4)
            """, ticket_id, ticket_type, action, user_id)
    
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


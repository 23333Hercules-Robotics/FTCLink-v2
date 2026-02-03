"""Native PostgreSQL-based caching service for FTC Events API data using Dozer's existing database."""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from loguru import logger
from dozer.db import Pool
from dozer.cogs._db_models import FTCCacheTable


class NativeCacheService:
    """
    Native PostgreSQL-based caching service that prevents direct client polling of FTC Events API.
    Uses Dozer's existing database connection instead of requiring separate Supabase hosting.
    
    Cache refresh intervals:
    - Events: 60 minutes (hourly)
    - Matches: 1 minute (during active events)
    - Rankings: 1 minute (during active events)
    - Teams: 24 hours (daily)
    - OPR stats: 5 minutes (from FTCScout)
    """
    
    CACHE_INTERVALS = {
        'events': 3600,      # 1 hour in seconds
        'matches': 60,       # 1 minute
        'rankings': 60,      # 1 minute
        'teams': 86400,      # 24 hours
        'opr_stats': 300,    # 5 minutes
    }
    
    def __init__(self):
        """Initialize the native cache service."""
        logger.info("Native PostgreSQL cache service initialized")
    
    async def get_cached_data(self, cache_type: str, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve cached data if it exists and is not expired.
        
        Args:
            cache_type: Type of cache (events, matches, rankings, teams, opr_stats)
            cache_key: Unique identifier for the cached item
            
        Returns:
            Cached data dict or None if not found/expired
        """
        if not Pool:
            return None
            
        try:
            expiry_seconds = self.CACHE_INTERVALS.get(cache_type, 3600)
            
            async with Pool.acquire() as conn:
                result = await conn.fetchrow(
                    """
                    SELECT cache_data, last_updated 
                    FROM ftc_api_cache
                    WHERE cache_key = $1 
                    AND cache_type = $2
                    AND last_updated > NOW() - INTERVAL '1 second' * $3
                    """,
                    cache_key, cache_type, expiry_seconds
                )
                
                if result:
                    logger.debug(f"Cache HIT: {cache_type}/{cache_key}")
                    return result['cache_data']
            
            logger.debug(f"Cache MISS: {cache_type}/{cache_key}")
            return None
            
        except Exception as e:
            logger.error(f"Error retrieving from cache: {e}")
            return None
    
    async def set_cached_data(self, cache_type: str, cache_key: str, data: Any, 
                             season: Optional[int] = None) -> bool:
        """
        Store data in the PostgreSQL cache.
        
        Args:
            cache_type: Type of cache (events, matches, rankings, teams, opr_stats)
            cache_key: Unique identifier for the cached item
            data: Data to cache (will be JSON serialized)
            season: Optional season year
            
        Returns:
            True if successful, False otherwise
        """
        if not Pool:
            return False
            
        try:
            # Ensure data is JSON-serializable
            if not isinstance(data, (dict, list)):
                data = json.loads(json.dumps(data))
            
            async with Pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO ftc_api_cache (cache_key, cache_type, cache_data, season, last_updated)
                    VALUES ($1, $2, $3, $4, NOW())
                    ON CONFLICT (cache_key) 
                    DO UPDATE SET 
                        cache_data = $3, 
                        cache_type = $2,
                        season = $4,
                        last_updated = NOW()
                    """,
                    cache_key, cache_type, data, season
                )
            
            logger.debug(f"Cache SET: {cache_type}/{cache_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing to cache: {e}")
            return False
    
    async def invalidate_cache(self, cache_type: Optional[str] = None, 
                              cache_key: Optional[str] = None) -> bool:
        """
        Invalidate (delete) cache entries.
        
        Args:
            cache_type: Optional cache type to filter by
            cache_key: Optional specific cache key to delete
            
        Returns:
            True if successful, False otherwise
        """
        if not Pool:
            return False
            
        try:
            async with Pool.acquire() as conn:
                if cache_key:
                    await conn.execute(
                        "DELETE FROM ftc_api_cache WHERE cache_key = $1",
                        cache_key
                    )
                elif cache_type:
                    await conn.execute(
                        "DELETE FROM ftc_api_cache WHERE cache_type = $1",
                        cache_type
                    )
                else:
                    await conn.execute("TRUNCATE ftc_api_cache")
            
            logger.info(f"Cache invalidated: type={cache_type}, key={cache_key}")
            return True
            
        except Exception as e:
            logger.error(f"Error invalidating cache: {e}")
            return False
    
    async def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        if not Pool:
            return {'error': 'Database not initialized'}
            
        try:
            async with Pool.acquire() as conn:
                # Get count by cache type
                results = await conn.fetch(
                    """
                    SELECT 
                        cache_type,
                        COUNT(*) as count,
                        MAX(last_updated) as newest,
                        MIN(last_updated) as oldest
                    FROM ftc_api_cache
                    GROUP BY cache_type
                    """
                )
                
                stats = {
                    'total_entries': sum(r['count'] for r in results),
                    'by_type': {
                        r['cache_type']: {
                            'count': r['count'],
                            'newest': r['newest'].isoformat() if r['newest'] else None,
                            'oldest': r['oldest'].isoformat() if r['oldest'] else None
                        }
                        for r in results
                    },
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                return stats
            
        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {'error': str(e)}


class BackgroundCacheUpdater:
    """
    Background task manager that periodically refreshes cache data.
    Prevents API overload by respecting rate limits and using appropriate intervals.
    """
    
    def __init__(self, cache_service: NativeCacheService, ftc_client, scout_client):
        """
        Initialize the background cache updater.
        
        Args:
            cache_service: NativeCacheService instance
            ftc_client: FTCEventsClient instance
            scout_client: ScoutParser instance
        """
        self.cache_service = cache_service
        self.ftc_client = ftc_client
        self.scout_client = scout_client
        self.tasks = []
        self.active_events = set()  # Track active events for frequent updates
        logger.info("Background cache updater initialized")
    
    async def start(self):
        """Start all background caching tasks."""
        self.tasks.append(asyncio.create_task(self._cache_events_loop()))
        self.tasks.append(asyncio.create_task(self._cache_active_matches_loop()))
        self.tasks.append(asyncio.create_task(self._cache_active_rankings_loop()))
        logger.info("Background caching tasks started")
    
    async def stop(self):
        """Stop all background caching tasks."""
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Background caching tasks stopped")
    
    async def _cache_events_loop(self):
        """Cache events every hour."""
        while True:
            try:
                await self._refresh_events_cache()
                await asyncio.sleep(3600)  # 1 hour
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in events cache loop: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def _cache_active_matches_loop(self):
        """Cache matches for active events every minute."""
        while True:
            try:
                await self._refresh_matches_cache()
                await asyncio.sleep(60)  # 1 minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in matches cache loop: {e}")
                await asyncio.sleep(60)
    
    async def _cache_active_rankings_loop(self):
        """Cache rankings for active events every minute."""
        while True:
            try:
                await self._refresh_rankings_cache()
                await asyncio.sleep(60)  # 1 minute
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in rankings cache loop: {e}")
                await asyncio.sleep(60)
    
    async def _refresh_events_cache(self):
        """Refresh the events cache for current season."""
        try:
            from dozer.cogs.ftc import FTCEventsClient
            season = FTCEventsClient.get_season()
            
            # Get all events for the current season
            res = await self.ftc_client.req("events")
            async with res:
                if res.status == 200:
                    events_data = await res.json(content_type=None)
                    
                    if events_data and 'events' in events_data:
                        # Store the full events list
                        cache_key = f"season_{season}_all_events"
                        await self.cache_service.set_cached_data(
                            'events', cache_key, events_data, season
                        )
                        
                        # Update active events list (events happening now or recently)
                        now = datetime.utcnow()
                        for event in events_data['events']:
                            try:
                                event_date = FTCEventsClient.date_parse(event.get('dateStart', ''))
                                event_end = FTCEventsClient.date_parse(event.get('dateEnd', ''))
                                
                                # Consider event active if it's happening now or in the past week
                                if event_date <= now <= event_end + timedelta(days=1):
                                    self.active_events.add(event['code'])
                                elif event['code'] in self.active_events and now > event_end + timedelta(days=1):
                                    self.active_events.discard(event['code'])
                            except Exception:
                                pass
                        
                        logger.info(f"Cached {len(events_data['events'])} events, {len(self.active_events)} active")
        
        except Exception as e:
            logger.error(f"Error refreshing events cache: {e}")
    
    async def _refresh_matches_cache(self):
        """Refresh matches cache for active events."""
        for event_code in list(self.active_events):
            try:
                from dozer.cogs.ftc import FTCEventsClient
                season = FTCEventsClient.get_season()
                
                # Cache qualification matches
                res = await self.ftc_client.req(f"schedule/{event_code}/qual/hybrid", season=season)
                async with res:
                    if res.status == 200:
                        matches_data = await res.json(content_type=None)
                        cache_key = f"season_{season}_event_{event_code}_matches_qual"
                        await self.cache_service.set_cached_data(
                            'matches', cache_key, matches_data, season
                        )
                
                # Cache playoff matches
                res = await self.ftc_client.req(f"schedule/{event_code}/playoff/hybrid", season=season)
                async with res:
                    if res.status == 200:
                        matches_data = await res.json(content_type=None)
                        cache_key = f"season_{season}_event_{event_code}_matches_playoff"
                        await self.cache_service.set_cached_data(
                            'matches', cache_key, matches_data, season
                        )
                
                logger.debug(f"Cached matches for event {event_code}")
                
                # Small delay to avoid overwhelming the API
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error refreshing matches cache for {event_code}: {e}")
    
    async def _refresh_rankings_cache(self):
        """Refresh rankings cache for active events."""
        for event_code in list(self.active_events):
            try:
                from dozer.cogs.ftc import FTCEventsClient
                season = FTCEventsClient.get_season()
                
                res = await self.ftc_client.req(f"rankings/{event_code}", season=season)
                async with res:
                    if res.status == 200:
                        rankings_data = await res.json(content_type=None)
                        cache_key = f"season_{season}_event_{event_code}_rankings"
                        await self.cache_service.set_cached_data(
                            'rankings', cache_key, rankings_data, season
                        )
                        logger.debug(f"Cached rankings for event {event_code}")
                
                # Small delay to avoid overwhelming the API
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error refreshing rankings cache for {event_code}: {e}")
    
    async def cache_team_data(self, team_number: int, season: Optional[int] = None):
        """
        Cache team data on-demand.
        
        Args:
            team_number: Team number to cache
            season: Optional season year
        """
        try:
            from dozer.cogs.ftc import FTCEventsClient
            if season is None:
                season = FTCEventsClient.get_season()
            
            # Cache team info from FTC Events
            res = await self.ftc_client.req("teams?" + urlencode({'teamNumber': str(team_number)}), season=season)
            async with res:
                if res.status == 200:
                    team_data = await res.json(content_type=None)
                    cache_key = f"season_{season}_team_{team_number}"
                    await self.cache_service.set_cached_data(
                        'teams', cache_key, team_data, season
                    )
            
            # Cache OPR stats from FTCScout
            sres = await self.scout_client.req(f"teams/{team_number}/quick-stats")
            async with sres:
                if sres.status == 200:
                    opr_data = await sres.json(content_type=None)
                    cache_key = f"season_{season}_team_{team_number}_opr"
                    await self.cache_service.set_cached_data(
                        'opr_stats', cache_key, opr_data, season
                    )
            
            logger.debug(f"Cached data for team {team_number}")
            return True
            
        except Exception as e:
            logger.error(f"Error caching team data for {team_number}: {e}")
            return False
    
    def add_active_event(self, event_code: str):
        """Add an event to the active events list for frequent updates."""
        self.active_events.add(event_code)
        logger.info(f"Added {event_code} to active events")
    
    def remove_active_event(self, event_code: str):
        """Remove an event from the active events list."""
        self.active_events.discard(event_code)
        logger.info(f"Removed {event_code} from active events")

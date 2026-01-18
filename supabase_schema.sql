-- Supabase SQL Schema for FTC Events API Caching
-- This schema prevents direct client polling by caching API responses

-- Create the main cache table for all FTC Events API data
CREATE TABLE IF NOT EXISTS ftc_api_cache (
    cache_key TEXT PRIMARY KEY,
    cache_type TEXT NOT NULL,
    cache_data JSONB NOT NULL,
    season INTEGER,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_ftc_api_cache_type ON ftc_api_cache(cache_type);
CREATE INDEX IF NOT EXISTS idx_ftc_api_cache_season ON ftc_api_cache(season);
CREATE INDEX IF NOT EXISTS idx_ftc_api_cache_updated ON ftc_api_cache(last_updated);

-- Create a composite index for common queries
CREATE INDEX IF NOT EXISTS idx_ftc_api_cache_type_season ON ftc_api_cache(cache_type, season);

-- Create TBA webhook subscription table
CREATE TABLE IF NOT EXISTS tba_webhook_subscriptions (
    subscription_url TEXT PRIMARY KEY,
    event_key TEXT NOT NULL,
    notification_types TEXT[] NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_notification TIMESTAMP WITH TIME ZONE
);

-- Create TBA webhook events table
CREATE TABLE IF NOT EXISTS tba_webhook_events (
    id SERIAL PRIMARY KEY,
    message_type TEXT NOT NULL,
    event_key TEXT,
    event_data JSONB NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on event_key for efficient lookups
CREATE INDEX IF NOT EXISTS idx_tba_webhook_events_event_key ON tba_webhook_events(event_key);
CREATE INDEX IF NOT EXISTS idx_tba_webhook_events_received_at ON tba_webhook_events(received_at);

-- Create a function to clean up old cache entries (optional)
CREATE OR REPLACE FUNCTION cleanup_old_cache_entries(days_old INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM ftc_api_cache
    WHERE last_updated < NOW() - INTERVAL '1 day' * days_old;
    
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Create a function to get cache statistics
CREATE OR REPLACE FUNCTION get_cache_statistics()
RETURNS TABLE (
    cache_type TEXT,
    entry_count BIGINT,
    avg_age_hours NUMERIC,
    oldest_entry TIMESTAMP WITH TIME ZONE,
    newest_entry TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        ftc_api_cache.cache_type,
        COUNT(*) as entry_count,
        ROUND(AVG(EXTRACT(EPOCH FROM (NOW() - last_updated)) / 3600), 2) as avg_age_hours,
        MIN(last_updated) as oldest_entry,
        MAX(last_updated) as newest_entry
    FROM ftc_api_cache
    GROUP BY ftc_api_cache.cache_type
    ORDER BY entry_count DESC;
END;
$$ LANGUAGE plpgsql;

-- Enable Row Level Security (RLS) for Supabase
ALTER TABLE ftc_api_cache ENABLE ROW LEVEL SECURITY;
ALTER TABLE tba_webhook_subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tba_webhook_events ENABLE ROW LEVEL SECURITY;

-- Create policies for service role access (adjust as needed for your security requirements)
-- These policies allow the service role to perform all operations

CREATE POLICY "Service role can do everything on ftc_api_cache"
    ON ftc_api_cache
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role can do everything on tba_webhook_subscriptions"
    ON tba_webhook_subscriptions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role can do everything on tba_webhook_events"
    ON tba_webhook_events
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- Optional: Create policies for authenticated users (read-only access to cache)
CREATE POLICY "Authenticated users can read ftc_api_cache"
    ON ftc_api_cache
    FOR SELECT
    TO authenticated
    USING (true);

-- Comments for documentation
COMMENT ON TABLE ftc_api_cache IS 'Caches FTC Events API responses to prevent direct client polling';
COMMENT ON COLUMN ftc_api_cache.cache_key IS 'Unique identifier for the cached item (e.g., season_2024_event_USPACMP)';
COMMENT ON COLUMN ftc_api_cache.cache_type IS 'Type of cached data: events (1hr), matches (1min), rankings (1min), teams (24hr), opr_stats (5min)';
COMMENT ON COLUMN ftc_api_cache.cache_data IS 'JSON data from the API response';
COMMENT ON COLUMN ftc_api_cache.season IS 'FTC season year (e.g., 2024)';
COMMENT ON COLUMN ftc_api_cache.last_updated IS 'Timestamp of when this cache entry was last updated';

COMMENT ON TABLE tba_webhook_subscriptions IS 'Tracks active Blue Alliance webhook subscriptions';
COMMENT ON TABLE tba_webhook_events IS 'Stores received Blue Alliance webhook events for processing';

-- Evidence Repository Database Initialization
-- This script runs once when the PostgreSQL container is first created

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Grant privileges to evidence user (already owner, but explicit)
GRANT ALL PRIVILEGES ON DATABASE evidence_repository TO evidence;

-- Log successful initialization
DO $$
BEGIN
    RAISE NOTICE 'Evidence Repository database initialized successfully';
    RAISE NOTICE 'pgvector extension version: %', (SELECT extversion FROM pg_extension WHERE extname = 'vector');
END $$;

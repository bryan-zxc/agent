-- PostgreSQL Initialisation Script
-- This script runs automatically when the PostgreSQL container starts for the first time

-- Create a template database with standard settings
CREATE DATABASE template_agent WITH TEMPLATE = template0 ENCODING = 'UTF8' LC_COLLATE = 'en_US.utf8' LC_CTYPE = 'en_US.utf8';

-- Connect to the template database
\c template_agent

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- For UUID generation
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";  -- For query performance monitoring

-- Create a function to automatically create project databases
CREATE OR REPLACE FUNCTION create_project_database(project_name TEXT)
RETURNS VOID AS $$
BEGIN
    -- Check if database already exists
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = project_name) THEN
        -- Create the database using the template
        EXECUTE format('CREATE DATABASE %I WITH TEMPLATE = template_agent', project_name);
        RAISE NOTICE 'Database % created successfully', project_name;
    ELSE
        RAISE NOTICE 'Database % already exists', project_name;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Switch back to the main database to set up the function there too
\c agent_main

-- Create the same function in the main database
CREATE OR REPLACE FUNCTION create_project_database(project_name TEXT)
RETURNS VOID AS $$
BEGIN
    -- Check if database already exists
    IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = project_name) THEN
        -- Create the database using the template
        EXECUTE format('CREATE DATABASE %I WITH TEMPLATE = template_agent', project_name);
        RAISE NOTICE 'Database % created successfully', project_name;
    ELSE
        RAISE NOTICE 'Database % already exists', project_name;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- Grant execute permission to the agent user
GRANT EXECUTE ON FUNCTION create_project_database(TEXT) TO agent_user;

-- Project databases will be created on-demand by the application
-- using the project_name from settings

-- Optimised settings for small, low-latency workloads
ALTER SYSTEM SET random_page_cost = 1.1;
ALTER SYSTEM SET effective_io_concurrency = 200;
ALTER SYSTEM SET wal_buffers = '16MB';
ALTER SYSTEM SET default_statistics_target = 100;
ALTER SYSTEM SET checkpoint_completion_target = 0.9;
ALTER SYSTEM SET max_wal_size = '1GB';  -- Reduced for small tables
ALTER SYSTEM SET min_wal_size = '80MB';   -- Reduced for small tables
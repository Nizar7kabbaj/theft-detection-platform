\set ON_ERROR_STOP on

SELECT 'CREATE DATABASE auditdb'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'auditdb')
\gexec

SELECT format('CREATE ROLE audit_owner LOGIN PASSWORD %L', :'owner_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_owner')
\gexec

SELECT format('CREATE ROLE audit_app LOGIN PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'audit_app')
\gexec

\connect auditdb

ALTER DATABASE auditdb OWNER TO audit_owner;

REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO audit_app;
GRANT ALL ON SCHEMA public TO audit_owner;

ALTER DEFAULT PRIVILEGES FOR ROLE audit_owner IN SCHEMA public
  GRANT INSERT, SELECT ON TABLES TO audit_app;

ALTER DEFAULT PRIVILEGES FOR ROLE audit_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO audit_app;

\set ON_ERROR_STOP on

SELECT format('CREATE ROLE auth_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD %L', :'owner_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'auth_owner')
\gexec

SELECT format('CREATE ROLE auth_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT PASSWORD %L', :'app_password')
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'auth_app')
\gexec

SELECT format('ALTER ROLE auth_owner PASSWORD %L', :'owner_password')
\gexec

SELECT format('ALTER ROLE auth_app PASSWORD %L', :'app_password')
\gexec

REVOKE CONNECT ON DATABASE authdb FROM PUBLIC;
GRANT CONNECT ON DATABASE authdb TO auth_owner;
GRANT CONNECT ON DATABASE authdb TO auth_app;

\connect authdb

ALTER TABLE users OWNER TO auth_owner;
ALTER TABLE sessions OWNER TO auth_owner;
ALTER TABLE refresh_tokens OWNER TO auth_owner;
ALTER TABLE audit_outbox OWNER TO auth_owner;
ALTER TABLE audit_outbox_dead OWNER TO auth_owner;
ALTER TABLE alembic_version OWNER TO auth_owner;

ALTER SEQUENCE audit_outbox_id_seq OWNER TO auth_owner;
ALTER SEQUENCE audit_outbox_dead_id_seq OWNER TO auth_owner;

GRANT USAGE ON SCHEMA public TO auth_owner;
GRANT USAGE ON SCHEMA public TO auth_app;

GRANT SELECT, INSERT, UPDATE ON users TO auth_app;
GRANT SELECT, INSERT, UPDATE ON sessions TO auth_app;
GRANT SELECT, INSERT, UPDATE ON refresh_tokens TO auth_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON audit_outbox TO auth_app;
GRANT SELECT, INSERT ON audit_outbox_dead TO auth_app;

GRANT USAGE, SELECT ON SEQUENCE audit_outbox_id_seq TO auth_app;
GRANT USAGE, SELECT ON SEQUENCE audit_outbox_dead_id_seq TO auth_app;

ALTER DEFAULT PRIVILEGES FOR ROLE auth_owner IN SCHEMA public
  REVOKE DELETE ON TABLES FROM auth_app;
ALTER DEFAULT PRIVILEGES FOR ROLE auth_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE ON TABLES TO auth_app;
ALTER DEFAULT PRIVILEGES FOR ROLE auth_owner IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO auth_app;

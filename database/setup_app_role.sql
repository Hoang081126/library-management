-- Provision the unprivileged runtime role for an existing or new database.
-- The password is read from the container environment and never stored here.
\set ON_ERROR_STOP on
\getenv app_user APP_DB_USER
\getenv app_password APP_DB_PASSWORD

SELECT (
    :'app_user' = current_user
    OR :'app_user' = 'postgres'
    OR length(:'app_user') NOT BETWEEN 1 AND 63
    OR length(:'app_password') < 32
) AS invalid_app_role_config\gset
\if :invalid_app_role_config
\echo Invalid APP_DB_USER or APP_DB_PASSWORD configuration; use a distinct role and a password of at least 32 characters.
\quit 3
\endif

SELECT EXISTS (
    SELECT 1
    FROM pg_class rel
    JOIN pg_namespace ns ON ns.oid = rel.relnamespace
    JOIN pg_roles owner_role ON owner_role.oid = rel.relowner
    WHERE ns.nspname = 'public'
      AND owner_role.rolname = :'app_user'
    UNION ALL
    SELECT 1
    FROM pg_database dbrow
    JOIN pg_roles owner_role ON owner_role.oid = dbrow.datdba
    WHERE dbrow.datname = current_database()
      AND owner_role.rolname = :'app_user'
) AS app_role_owns_objects\gset
\if :app_role_owns_objects
\echo Runtime role owns database objects; choose a dedicated non-owner APP_DB_USER.
\quit 3
\endif

SELECT format('CREATE ROLE %I WITH LOGIN', :'app_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'app_user')\gexec

SELECT format(
    'ALTER ROLE %I WITH LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT 20',
    :'app_user',
    :'app_password'
)\gexec

-- Remove pre-existing memberships so the web role cannot inherit privileges.
SELECT format('REVOKE %I FROM %I', parent.rolname, :'app_user')
FROM pg_auth_members membership
JOIN pg_roles parent ON parent.oid = membership.roleid
JOIN pg_roles member ON member.oid = membership.member
WHERE member.rolname = :'app_user'\gexec

SELECT format('REVOKE ALL PRIVILEGES ON DATABASE %I FROM %I', current_database(), :'app_user')\gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', current_database(), :'app_user')\gexec
GRANT USAGE ON SCHEMA public TO :"app_user";
REVOKE CREATE ON SCHEMA public FROM :"app_user";
REVOKE ALL PRIVILEGES ON TABLE public.users, public.books, public.readers, public.loans FROM :"app_user";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.users, public.books, public.readers, public.loans TO :"app_user";
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM :"app_user";
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO :"app_user";

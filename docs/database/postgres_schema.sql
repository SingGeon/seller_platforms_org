-- LeadRadar PostgreSQL structure: seller accounts, lead stage/owner/notes and configuration.
-- Companies, documents, AI signals, alerts, scores, run logs and the LLM cache live in MongoDB
-- (README "Databases", backend/app/mongo.py).
--
-- Run it in DBeaver on the LDR database (SQL Editor -> Execute script, Alt+X). Everything goes into the
-- "LeadRadar" schema; the app then connects with
--   DATABASE_URL=postgresql+psycopg://<user>:<password>@localhost:5432/LDR?options=-csearch_path%3D%22LeadRadar%22
-- Equivalent to `alembic upgrade head` (the source of truth is backend/alembic/versions); the
-- alembic_version row at the end tells Alembic this schema is already at revision 0003.

BEGIN;

CREATE SCHEMA IF NOT EXISTS "LeadRadar";
SET LOCAL search_path TO "LeadRadar";

CREATE TABLE alembic_version (
    version_num character varying(32) NOT NULL
);

CREATE TABLE disqualification_rules (
    id integer NOT NULL,
    service_id integer,
    name character varying(200) NOT NULL,
    rule_type character varying(20) NOT NULL,
    field character varying(50),
    operator character varying(20),
    value jsonb,
    question text,
    keywords jsonb NOT NULL,
    min_confidence double precision NOT NULL,
    active boolean NOT NULL
);

CREATE SEQUENCE disqualification_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE disqualification_rules_id_seq OWNED BY disqualification_rules.id;

CREATE TABLE icp_criteria (
    id integer NOT NULL,
    service_id integer NOT NULL,
    markets jsonb NOT NULL,
    industries jsonb NOT NULL,
    countries jsonb NOT NULL,
    employee_min integer,
    employee_max integer,
    revenue_min double precision,
    revenue_max double precision,
    min_fit integer NOT NULL
);

CREATE SEQUENCE icp_criteria_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE icp_criteria_id_seq OWNED BY icp_criteria.id;

CREATE TABLE lead_assignments (
    company_id integer NOT NULL,
    seller_id integer,
    stage character varying(20) NOT NULL,
    notes jsonb NOT NULL,
    updated_at timestamp with time zone NOT NULL
);

CREATE TABLE scoring_config (
    id integer NOT NULL,
    icp_weight double precision NOT NULL,
    signal_weight double precision NOT NULL,
    hot_threshold double precision NOT NULL,
    warm_threshold double precision NOT NULL,
    weight_values jsonb NOT NULL,
    recency_buckets jsonb NOT NULL,
    undated_recency double precision NOT NULL,
    discovery_countries jsonb DEFAULT '["RO", "MD"]'::jsonb NOT NULL
);

CREATE SEQUENCE scoring_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE scoring_config_id_seq OWNED BY scoring_config.id;

CREATE TABLE seller_sessions (
    token_hash character varying(64) NOT NULL,
    seller_id integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL
);

CREATE TABLE sellers (
    id integer NOT NULL,
    email character varying(320) NOT NULL,
    full_name character varying(200) NOT NULL,
    password_hash character varying(300) NOT NULL,
    role character varying(20) NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    last_login_at timestamp with time zone
);

CREATE SEQUENCE sellers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE sellers_id_seq OWNED BY sellers.id;

CREATE TABLE services (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(100) NOT NULL,
    description text NOT NULL,
    value_proposition text NOT NULL,
    event_weights jsonb NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE services_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE services_id_seq OWNED BY services.id;

CREATE TABLE signal_questions (
    id integer NOT NULL,
    service_id integer NOT NULL,
    text text NOT NULL,
    weight character varying(10) NOT NULL,
    source_hint character varying(10) NOT NULL,
    lookback_days integer NOT NULL,
    is_negative boolean NOT NULL,
    keywords jsonb NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

CREATE SEQUENCE signal_questions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE signal_questions_id_seq OWNED BY signal_questions.id;

CREATE TABLE source_state (
    name character varying(50) NOT NULL,
    enabled boolean NOT NULL,
    interval_minutes integer,
    cursor jsonb NOT NULL,
    last_run_at timestamp with time zone,
    last_success_at timestamp with time zone,
    next_run_at timestamp with time zone,
    last_status character varying(20) NOT NULL,
    last_error text,
    last_stats jsonb NOT NULL,
    total_items integer NOT NULL,
    total_new_companies integer NOT NULL
);

ALTER TABLE ONLY disqualification_rules ALTER COLUMN id SET DEFAULT nextval('disqualification_rules_id_seq'::regclass);

ALTER TABLE ONLY icp_criteria ALTER COLUMN id SET DEFAULT nextval('icp_criteria_id_seq'::regclass);

ALTER TABLE ONLY scoring_config ALTER COLUMN id SET DEFAULT nextval('scoring_config_id_seq'::regclass);

ALTER TABLE ONLY sellers ALTER COLUMN id SET DEFAULT nextval('sellers_id_seq'::regclass);

ALTER TABLE ONLY services ALTER COLUMN id SET DEFAULT nextval('services_id_seq'::regclass);

ALTER TABLE ONLY signal_questions ALTER COLUMN id SET DEFAULT nextval('signal_questions_id_seq'::regclass);

ALTER TABLE ONLY alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);

ALTER TABLE ONLY disqualification_rules
    ADD CONSTRAINT disqualification_rules_pkey PRIMARY KEY (id);

ALTER TABLE ONLY icp_criteria
    ADD CONSTRAINT icp_criteria_pkey PRIMARY KEY (id);

ALTER TABLE ONLY icp_criteria
    ADD CONSTRAINT icp_criteria_service_id_key UNIQUE (service_id);

ALTER TABLE ONLY lead_assignments
    ADD CONSTRAINT lead_assignments_pkey PRIMARY KEY (company_id);

ALTER TABLE ONLY scoring_config
    ADD CONSTRAINT scoring_config_pkey PRIMARY KEY (id);

ALTER TABLE ONLY seller_sessions
    ADD CONSTRAINT seller_sessions_pkey PRIMARY KEY (token_hash);

ALTER TABLE ONLY sellers
    ADD CONSTRAINT sellers_pkey PRIMARY KEY (id);

ALTER TABLE ONLY services
    ADD CONSTRAINT services_name_key UNIQUE (name);

ALTER TABLE ONLY services
    ADD CONSTRAINT services_pkey PRIMARY KEY (id);

ALTER TABLE ONLY services
    ADD CONSTRAINT services_slug_key UNIQUE (slug);

ALTER TABLE ONLY signal_questions
    ADD CONSTRAINT signal_questions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY source_state
    ADD CONSTRAINT source_state_pkey PRIMARY KEY (name);

CREATE INDEX ix_disqualification_rules_service_id ON disqualification_rules USING btree (service_id);

CREATE INDEX ix_lead_assignments_seller_id ON lead_assignments USING btree (seller_id);

CREATE INDEX ix_seller_sessions_seller_id ON seller_sessions USING btree (seller_id);

CREATE UNIQUE INDEX ix_sellers_email ON sellers USING btree (email);

CREATE INDEX ix_signal_questions_service_id ON signal_questions USING btree (service_id);

ALTER TABLE ONLY disqualification_rules
    ADD CONSTRAINT disqualification_rules_service_id_fkey FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE;

ALTER TABLE ONLY icp_criteria
    ADD CONSTRAINT icp_criteria_service_id_fkey FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE;

ALTER TABLE ONLY lead_assignments
    ADD CONSTRAINT lead_assignments_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES sellers(id) ON DELETE SET NULL;

ALTER TABLE ONLY seller_sessions
    ADD CONSTRAINT seller_sessions_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES sellers(id) ON DELETE CASCADE;

ALTER TABLE ONLY signal_questions
    ADD CONSTRAINT signal_questions_service_id_fkey FOREIGN KEY (service_id) REFERENCES services(id) ON DELETE CASCADE;

INSERT INTO alembic_version (version_num) VALUES ('0003');

COMMIT;

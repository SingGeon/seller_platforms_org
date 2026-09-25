-- PostgreSQL schema of the LeadRadar "MT" database (structure only, no data).
-- Generated with: pg_dump --schema-only --no-owner --no-privileges; the source of truth is backend/alembic/versions.
-- MongoDB collections and indexes are described in README "Databases" and created by backend/app/mongo.py.

--
-- PostgreSQL database dump
--

\restrict tDx8U6WOMgypNvT9d4BHf5VTM0HeEXqLFrJ7ticOdgZsTuMXjbNI2m2RCZn0Rjf

-- Dumped from database version 15.19 (Debian 15.19-0+deb12u1)
-- Dumped by pg_dump version 15.19 (Debian 15.19-0+deb12u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: disqualification_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.disqualification_rules (
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


--
-- Name: disqualification_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.disqualification_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: disqualification_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.disqualification_rules_id_seq OWNED BY public.disqualification_rules.id;


--
-- Name: icp_criteria; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.icp_criteria (
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


--
-- Name: icp_criteria_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.icp_criteria_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: icp_criteria_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.icp_criteria_id_seq OWNED BY public.icp_criteria.id;


--
-- Name: lead_assignments; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.lead_assignments (
    company_id integer NOT NULL,
    seller_id integer,
    stage character varying(20) NOT NULL,
    notes jsonb NOT NULL,
    updated_at timestamp with time zone NOT NULL
);


--
-- Name: scoring_config; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scoring_config (
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


--
-- Name: scoring_config_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.scoring_config_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: scoring_config_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.scoring_config_id_seq OWNED BY public.scoring_config.id;


--
-- Name: seller_sessions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.seller_sessions (
    token_hash character varying(64) NOT NULL,
    seller_id integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL
);


--
-- Name: sellers; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sellers (
    id integer NOT NULL,
    email character varying(320) NOT NULL,
    full_name character varying(200) NOT NULL,
    password_hash character varying(300) NOT NULL,
    role character varying(20) NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    last_login_at timestamp with time zone
);


--
-- Name: sellers_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sellers_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sellers_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sellers_id_seq OWNED BY public.sellers.id;


--
-- Name: services; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.services (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    slug character varying(100) NOT NULL,
    description text NOT NULL,
    value_proposition text NOT NULL,
    event_weights jsonb NOT NULL,
    active boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);


--
-- Name: services_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.services_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: services_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.services_id_seq OWNED BY public.services.id;


--
-- Name: signal_questions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.signal_questions (
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


--
-- Name: signal_questions_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.signal_questions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: signal_questions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.signal_questions_id_seq OWNED BY public.signal_questions.id;


--
-- Name: source_state; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.source_state (
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


--
-- Name: disqualification_rules id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.disqualification_rules ALTER COLUMN id SET DEFAULT nextval('public.disqualification_rules_id_seq'::regclass);


--
-- Name: icp_criteria id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.icp_criteria ALTER COLUMN id SET DEFAULT nextval('public.icp_criteria_id_seq'::regclass);


--
-- Name: scoring_config id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scoring_config ALTER COLUMN id SET DEFAULT nextval('public.scoring_config_id_seq'::regclass);


--
-- Name: sellers id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sellers ALTER COLUMN id SET DEFAULT nextval('public.sellers_id_seq'::regclass);


--
-- Name: services id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services ALTER COLUMN id SET DEFAULT nextval('public.services_id_seq'::regclass);


--
-- Name: signal_questions id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_questions ALTER COLUMN id SET DEFAULT nextval('public.signal_questions_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: disqualification_rules disqualification_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.disqualification_rules
    ADD CONSTRAINT disqualification_rules_pkey PRIMARY KEY (id);


--
-- Name: icp_criteria icp_criteria_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.icp_criteria
    ADD CONSTRAINT icp_criteria_pkey PRIMARY KEY (id);


--
-- Name: icp_criteria icp_criteria_service_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.icp_criteria
    ADD CONSTRAINT icp_criteria_service_id_key UNIQUE (service_id);


--
-- Name: lead_assignments lead_assignments_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_assignments
    ADD CONSTRAINT lead_assignments_pkey PRIMARY KEY (company_id);


--
-- Name: scoring_config scoring_config_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scoring_config
    ADD CONSTRAINT scoring_config_pkey PRIMARY KEY (id);


--
-- Name: seller_sessions seller_sessions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.seller_sessions
    ADD CONSTRAINT seller_sessions_pkey PRIMARY KEY (token_hash);


--
-- Name: sellers sellers_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sellers
    ADD CONSTRAINT sellers_pkey PRIMARY KEY (id);


--
-- Name: services services_name_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_name_key UNIQUE (name);


--
-- Name: services services_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_pkey PRIMARY KEY (id);


--
-- Name: services services_slug_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.services
    ADD CONSTRAINT services_slug_key UNIQUE (slug);


--
-- Name: signal_questions signal_questions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_questions
    ADD CONSTRAINT signal_questions_pkey PRIMARY KEY (id);


--
-- Name: source_state source_state_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.source_state
    ADD CONSTRAINT source_state_pkey PRIMARY KEY (name);


--
-- Name: ix_disqualification_rules_service_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_disqualification_rules_service_id ON public.disqualification_rules USING btree (service_id);


--
-- Name: ix_lead_assignments_seller_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_lead_assignments_seller_id ON public.lead_assignments USING btree (seller_id);


--
-- Name: ix_seller_sessions_seller_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_seller_sessions_seller_id ON public.seller_sessions USING btree (seller_id);


--
-- Name: ix_sellers_email; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX ix_sellers_email ON public.sellers USING btree (email);


--
-- Name: ix_signal_questions_service_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_signal_questions_service_id ON public.signal_questions USING btree (service_id);


--
-- Name: disqualification_rules disqualification_rules_service_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.disqualification_rules
    ADD CONSTRAINT disqualification_rules_service_id_fkey FOREIGN KEY (service_id) REFERENCES public.services(id) ON DELETE CASCADE;


--
-- Name: icp_criteria icp_criteria_service_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.icp_criteria
    ADD CONSTRAINT icp_criteria_service_id_fkey FOREIGN KEY (service_id) REFERENCES public.services(id) ON DELETE CASCADE;


--
-- Name: lead_assignments lead_assignments_seller_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.lead_assignments
    ADD CONSTRAINT lead_assignments_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.sellers(id) ON DELETE SET NULL;


--
-- Name: seller_sessions seller_sessions_seller_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.seller_sessions
    ADD CONSTRAINT seller_sessions_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.sellers(id) ON DELETE CASCADE;


--
-- Name: signal_questions signal_questions_service_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.signal_questions
    ADD CONSTRAINT signal_questions_service_id_fkey FOREIGN KEY (service_id) REFERENCES public.services(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict tDx8U6WOMgypNvT9d4BHf5VTM0HeEXqLFrJ7ticOdgZsTuMXjbNI2m2RCZn0Rjf


--
-- PostgreSQL database dump
--

\restrict GLKhODaDLyPdMFf8DIYGCEos8EHGNS0WMdbZIop6xgWSp3fEn0jQtZDKWzqzdCk

-- Dumped from database version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)
-- Dumped by pg_dump version 16.11 (Ubuntu 16.11-0ubuntu0.24.04.1)

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

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: entries; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.entries (
    entry_id text NOT NULL,
    title text NOT NULL,
    summary_ai text,
    content text NOT NULL,
    project_code text,
    user_id text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    space_type text,
    parent_entry_id text,
    scene_tags jsonb DEFAULT '{}'::jsonb,
    extra_meta jsonb DEFAULT '{}'::jsonb,
    section_id text,
    section_version integer DEFAULT 1,
    is_latest boolean DEFAULT true,
    status text DEFAULT 'pending'::text,
    agent_id text,
    source_session_id text,
    importance numeric(3,2) DEFAULT 1.0,
    usage_count integer DEFAULT 0,
    last_seen_at timestamp with time zone,
    overridden_entry_ids text[]
);


ALTER TABLE public.entries OWNER TO postgres;

--
-- Data for Name: entries; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.entries (entry_id, title, summary_ai, content, project_code, user_id, created_at, space_type, parent_entry_id, scene_tags, extra_meta, section_id, section_version, is_latest, status, agent_id, source_session_id, importance, usage_count, last_seen_at, overridden_entry_ids) FROM stdin;
\.


--
-- Name: entries entries_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.entries
    ADD CONSTRAINT entries_pkey PRIMARY KEY (entry_id);


--
-- Name: idx_entries_agent_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_agent_id ON public.entries USING btree (agent_id);


--
-- Name: idx_entries_created_at; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_created_at ON public.entries USING btree (created_at DESC);


--
-- Name: idx_entries_importance; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_importance ON public.entries USING btree (importance);


--
-- Name: idx_entries_is_latest; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_is_latest ON public.entries USING btree (is_latest);


--
-- Name: idx_entries_overridden_entry_ids; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_overridden_entry_ids ON public.entries USING gin (overridden_entry_ids);


--
-- Name: idx_entries_parent_entry_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_parent_entry_id ON public.entries USING btree (parent_entry_id);


--
-- Name: idx_entries_project_code; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_project_code ON public.entries USING btree (project_code, created_at DESC);


--
-- Name: idx_entries_scene_tags; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_scene_tags ON public.entries USING gin (scene_tags);


--
-- Name: idx_entries_section_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_section_id ON public.entries USING btree (section_id);


--
-- Name: idx_entries_section_latest; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_section_latest ON public.entries USING btree (section_id, is_latest);


--
-- Name: idx_entries_section_version; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_section_version ON public.entries USING btree (section_id, section_version);


--
-- Name: idx_entries_source_session_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_source_session_id ON public.entries USING btree (source_session_id);


--
-- Name: idx_entries_space_type; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX idx_entries_space_type ON public.entries USING btree (space_type);


--
-- PostgreSQL database dump complete
--

\unrestrict GLKhODaDLyPdMFf8DIYGCEos8EHGNS0WMdbZIop6xgWSp3fEn0jQtZDKWzqzdCk


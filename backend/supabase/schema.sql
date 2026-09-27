-- Run this once in your Supabase project's SQL editor (Dashboard -> SQL Editor -> New query).
-- Deliberately a single JSONB-based table, not a fully normalized schema: the itinerary
-- graph is small and read/written as a whole every time, so there's no real query need
-- to split nodes/edges into their own tables, and this keeps the persistence layer simple.

create table if not exists trips (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,  -- null = anonymous/demo trip
  name text not null default 'My Trip',
  itinerary jsonb not null,      -- { "nodes": [...], "edges": [...] } - same shape as ItineraryGraph.to_dict()
  preferences jsonb not null default '{
    "cost_weight": 0.2, "time_weight": 0.3, "convenience_weight": 0.4,
    "disruption_weight": 0.1, "min_rating": 0, "avoid_next_day": false
  }'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table trips enable row level security;

-- Anonymous/demo trips (user_id is null) are readable/writable by anyone holding the
-- anon key - fine for a hackathon demo, NOT safe for a real multi-tenant deployment.
-- Once you wire up Supabase Auth in the frontend, every trip a signed-in user creates
-- gets user_id = auth.uid() automatically and this policy scopes it to them alone.
create policy "trips_owner_or_anonymous" on trips
  for all
  using (user_id = auth.uid() or user_id is null)
  with check (user_id = auth.uid() or user_id is null);

create index if not exists trips_user_id_idx on trips (user_id);

-- keep updated_at current on every write
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists trips_set_updated_at on trips;
create trigger trips_set_updated_at
  before update on trips
  for each row execute function set_updated_at();

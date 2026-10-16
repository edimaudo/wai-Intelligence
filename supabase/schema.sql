-- Wai Intelligence prototype state table.
-- The application uses the service-role key server-side only. Do not expose that key to clients.
create table if not exists public.wai_app_state (
  id text primary key check (id = 'default'),
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create or replace function public.set_wai_app_state_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists trg_wai_app_state_updated_at on public.wai_app_state;
create trigger trg_wai_app_state_updated_at
before update on public.wai_app_state
for each row execute function public.set_wai_app_state_updated_at();

alter table public.wai_app_state enable row level security;
-- Intentionally no anon/authenticated policies. Access is through the backend service-role key only.

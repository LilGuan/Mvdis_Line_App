create table if not exists records (
  id bigint primary key,
  type text not null check (type in ('income', 'expense')),
  description text not null,
  amount numeric not null check (amount > 0),
  category text not null,
  record_date date not null,
  note text default '',
  created_at timestamptz default now()
);

create table if not exists customers (
  id bigint primary key,
  name text not null,
  phone text default '',
  bike text default '',
  debt numeric default 0 check (debt >= 0),
  note text default '',
  created_at timestamptz default now()
);

create table if not exists inventory_items (
  id bigint primary key,
  name text not null,
  category text not null,
  quantity integer default 0 check (quantity >= 0),
  cost numeric default 0 check (cost >= 0),
  created_at timestamptz default now()
);

create table if not exists alerts (
  id bigint primary key,
  type text not null check (type in ('info', 'warn', 'danger')),
  text text not null,
  sub text default '',
  created_at timestamptz default now()
);

alter table records enable row level security;
alter table customers enable row level security;
alter table inventory_items enable row level security;
alter table alerts enable row level security;

drop policy if exists "public read records" on records;
create policy "public read records" on records for select using (true);
drop policy if exists "public insert records" on records;
create policy "public insert records" on records for insert with check (true);
drop policy if exists "public update records" on records;
create policy "public update records" on records for update using (true);
drop policy if exists "public delete records" on records;
create policy "public delete records" on records for delete using (true);

drop policy if exists "public read customers" on customers;
create policy "public read customers" on customers for select using (true);
drop policy if exists "public insert customers" on customers;
create policy "public insert customers" on customers for insert with check (true);
drop policy if exists "public update customers" on customers;
create policy "public update customers" on customers for update using (true);
drop policy if exists "public delete customers" on customers;
create policy "public delete customers" on customers for delete using (true);

drop policy if exists "public read inventory" on inventory_items;
create policy "public read inventory" on inventory_items for select using (true);
drop policy if exists "public insert inventory" on inventory_items;
create policy "public insert inventory" on inventory_items for insert with check (true);
drop policy if exists "public update inventory" on inventory_items;
create policy "public update inventory" on inventory_items for update using (true);
drop policy if exists "public delete inventory" on inventory_items;
create policy "public delete inventory" on inventory_items for delete using (true);

drop policy if exists "public read alerts" on alerts;
create policy "public read alerts" on alerts for select using (true);
drop policy if exists "public insert alerts" on alerts;
create policy "public insert alerts" on alerts for insert with check (true);
drop policy if exists "public update alerts" on alerts;
create policy "public update alerts" on alerts for update using (true);
drop policy if exists "public delete alerts" on alerts;
create policy "public delete alerts" on alerts for delete using (true);

-- MVDIS LINE bot: VIP users and daily manual query quota.
create table if not exists vip_users (
  line_id text primary key,
  display_name text default '',
  note text default '',
  is_active boolean not null default true,
  created_by text default '',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create table if not exists user_query_usage (
  line_id text not null,
  usage_date date not null,
  manual_query_count integer not null default 0 check (manual_query_count >= 0),
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  primary key (line_id, usage_date)
);

alter table vip_users enable row level security;
alter table user_query_usage enable row level security;

drop policy if exists "public read vip users" on vip_users;
create policy "public read vip users" on vip_users for select using (true);
drop policy if exists "public insert vip users" on vip_users;
create policy "public insert vip users" on vip_users for insert with check (true);
drop policy if exists "public update vip users" on vip_users;
create policy "public update vip users" on vip_users for update using (true);
drop policy if exists "public delete vip users" on vip_users;
create policy "public delete vip users" on vip_users for delete using (true);

drop policy if exists "public read query usage" on user_query_usage;
create policy "public read query usage" on user_query_usage for select using (true);
drop policy if exists "public insert query usage" on user_query_usage;
create policy "public insert query usage" on user_query_usage for insert with check (true);
drop policy if exists "public update query usage" on user_query_usage;
create policy "public update query usage" on user_query_usage for update using (true);
drop policy if exists "public delete query usage" on user_query_usage;
create policy "public delete query usage" on user_query_usage for delete using (true);

insert into vip_users (line_id, display_name, note, is_active, created_by)
values ('Uc033d76e142adb971941e27cd685856f', 'admin', 'owner', true, 'system')
on conflict (line_id) do update
set is_active = true,
    note = excluded.note,
    updated_at = now();

-- 55688 reservation monitor runtime settings.
create table if not exists reservation_monitor_settings (
  setting_key text primary key default 'default'
);

alter table reservation_monitor_settings add column if not exists active boolean not null default true;
alter table reservation_monitor_settings add column if not exists min_fare integer not null default 300;
alter table reservation_monitor_settings add column if not exists areas integer[] not null default array[124,127,128,151];
alter table reservation_monitor_settings add column if not exists date_mode text not null default 'all';
alter table reservation_monitor_settings add column if not exists date_value text default '';
alter table reservation_monitor_settings add column if not exists frequency_min_sec integer not null default 50;
alter table reservation_monitor_settings add column if not exists frequency_max_sec integer not null default 70;
alter table reservation_monitor_settings add column if not exists updated_by text default '';
alter table reservation_monitor_settings add column if not exists created_at timestamptz default now();
alter table reservation_monitor_settings add column if not exists updated_at timestamptz default now();
alter table reservation_monitor_settings drop constraint if exists reservation_monitor_min_fare;
alter table reservation_monitor_settings add constraint reservation_monitor_min_fare check (min_fare >= 0);
alter table reservation_monitor_settings drop constraint if exists reservation_monitor_date_mode;
alter table reservation_monitor_settings add constraint reservation_monitor_date_mode check (date_mode in ('all', 'today', 'date', 'range'));
alter table reservation_monitor_settings drop constraint if exists reservation_monitor_frequency;
alter table reservation_monitor_settings add constraint reservation_monitor_frequency check (
  frequency_min_sec >= 5
  and frequency_max_sec >= frequency_min_sec
);
alter table reservation_monitor_settings drop constraint if exists reservation_monitor_min_areas;
alter table reservation_monitor_settings add constraint reservation_monitor_min_areas check (array_length(areas, 1) >= 4);
alter table reservation_monitor_settings enable row level security;

drop policy if exists "public read reservation monitor settings" on reservation_monitor_settings;
create policy "public read reservation monitor settings"
on reservation_monitor_settings for select using (true);

drop policy if exists "public insert reservation monitor settings" on reservation_monitor_settings;
create policy "public insert reservation monitor settings"
on reservation_monitor_settings for insert with check (true);

drop policy if exists "public update reservation monitor settings" on reservation_monitor_settings;
create policy "public update reservation monitor settings"
on reservation_monitor_settings for update using (true);

insert into reservation_monitor_settings (
  setting_key, active, min_fare, areas, date_mode, date_value,
  frequency_min_sec, frequency_max_sec, updated_by
)
values ('default', true, 300, array[124,127,128,151], 'all', '', 50, 70, 'system')
on conflict (setting_key) do nothing;

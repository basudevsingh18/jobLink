-- 07_job_events_actor_int.sql
-- Goal: keep existing UUID history in job_events.actor_user_id,
--       add integer actor_user_int for new rows, and write to that.
--       This avoids unsafe type casting of historical UUIDs.

-- 1) Add new integer column if missing + FK to users(id)
do $$
begin
  if not exists (
    select 1
    from information_schema.columns
    where table_schema='public'
      and table_name='job_events'
      and column_name='actor_user_int'
  ) then
    alter table job_events
      add column actor_user_int integer;

    alter table job_events
      add constraint job_events_actor_user_int_fk
      foreign key (actor_user_int) references users(id);
  end if;
end$$;

-- 2) (Optional but recommended) allow old UUID column to be NULL for new events
--    so we don't have to populate it anymore
do $$
declare
  v_nullable boolean;
begin
  select is_nullable = 'YES'
  into v_nullable
  from information_schema.columns
  where table_schema='public' and table_name='job_events' and column_name='actor_user_id';

  if not v_nullable then
    alter table job_events
      alter column actor_user_id drop not null;
  end if;
end$$;

-- 3) Recreate acceptance trigger so new events write actor_user_int (integer)
create or replace function trg_accepted_jobs_enforce()
returns trigger
language plpgsql
as $$
declare
  v_status text;
begin
  select status
    into v_status
  from jobs
  where id = new.job_id
  for update;

  if v_status is null then
    raise exception 'Job % not found', new.job_id using errcode = 'P0001';
  end if;

  if v_status <> 'open' then
    raise exception 'Job % is not open (current status: %)', new.job_id, v_status using errcode = 'P0001';
  end if;

  -- Flip job to accepted
  update jobs set status = 'accepted' where id = new.job_id;

  -- Log event: write integer user id into actor_user_int.
  -- Keep actor_user_id (uuid) NULL for new rows.
  insert into job_events (job_id, actor_user_int, event_type, data)
  values (new.job_id, new.worker_id, 'JOB_ACCEPTED', jsonb_build_object('note','worker accepted'));

  return new;
end
$$;

drop trigger if exists trg_accepted_jobs_enforce on accepted_jobs;
create trigger trg_accepted_jobs_enforce
before insert on accepted_jobs
for each row execute function trg_accepted_jobs_enforce();

-- 4) (Optional) convenience view that exposes a single actor_user display field
--    preferring integer when present, otherwise uuid as text
create or replace view job_events_public as
select
  id,
  job_id,
  coalesce(actor_user_int::text, actor_user_id::text) as actor_user_display,
  event_type,
  data,
  created_at
from job_events;

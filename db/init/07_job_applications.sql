-- 07_job_applications.sql
-- Applications model + lifecycle automation for accept/decline + audit events.

------------------------------------------------------------
-- A) Job applications (one per worker per job; proposal optional)
------------------------------------------------------------
create table if not exists job_applications (
  id               serial primary key,
  job_id           integer not null references jobs(id) on delete cascade,
  worker_id        integer not null references users(id) on delete cascade,
  proposal         text,                                       -- optional pitch
  bid_cents        integer check (bid_cents is null or bid_cents >= 0),
  days_to_complete integer check (days_to_complete is null or days_to_complete > 0),
  status           text not null default 'pending' check (status in ('pending','accepted','declined','withdrawn')),
  created_at       timestamptz not null default now(),
  unique (job_id, worker_id)
);

create index if not exists job_applications_job_idx on job_applications(job_id);

------------------------------------------------------------
-- B) Optional: make sure job_events can store integer actor id
-- (We added actor_user_int earlier. Keep nullable to avoid data-mapping issues.)
------------------------------------------------------------
do $$
begin
  if not exists (
    select 1 from information_schema.columns
    where table_schema='public' and table_name='job_events' and column_name='actor_user_int'
  ) then
    alter table job_events
      add column actor_user_int integer;
    alter table job_events
      add constraint job_events_actor_user_int_fk
      foreign key (actor_user_int) references users(id);
  end if;
end$$;

------------------------------------------------------------
-- C) BEFORE INSERT on job_applications: ensure job is OPEN, log submit
------------------------------------------------------------
create or replace function trg_job_applications_before_ins()
returns trigger
language plpgsql
as $$
declare
  v_status text;
begin
  select status into v_status
  from jobs
  where id = new.job_id
  for update;

  if v_status is null then
    raise exception 'Job % not found', new.job_id using errcode = 'P0001';
  end if;

  if v_status <> 'open' then
    raise exception 'Job % not open for applications (current status: %)', new.job_id, v_status using errcode = 'P0001';
  end if;

  -- Audit: application submitted (actor = worker)
  insert into job_events (job_id, actor_user_int, event_type, data)
  values (new.job_id, new.worker_id, 'APPLICATION_SUBMITTED',
          jsonb_build_object('bid_cents', new.bid_cents, 'days', new.days_to_complete));

  return new;
end
$$;

drop trigger if exists trg_job_applications_before_ins on job_applications;
create trigger trg_job_applications_before_ins
before insert on job_applications
for each row execute function trg_job_applications_before_ins();

------------------------------------------------------------
-- D) AFTER UPDATE OF status: handle accept/decline/withdraw
--    * Accepting one application:
--       - jobs.status -> 'accepted'
--       - upsert into accepted_jobs
--       - auto-decline all other 'pending' apps for the job
--       - audit events for accepted/declined
------------------------------------------------------------
create or replace function trg_job_applications_after_upd()
returns trigger
language plpgsql
as $$
begin
  if tg_op = 'UPDATE' and old.status is distinct from new.status then
    -- ACCEPTED
    if new.status = 'accepted' then
      -- Lock job row and set to accepted
      update jobs set status = 'accepted' where id = new.job_id;

      -- Ensure accepted_jobs has the assignment (one per job)
      insert into accepted_jobs (job_id, worker_id, accepted_at)
      values (new.job_id, new.worker_id, now())
      on conflict (job_id) do update
        set worker_id = excluded.worker_id, accepted_at = excluded.accepted_at;

      -- Auto-decline other pending applications for this job
      update job_applications
      set status = 'declined'
      where job_id = new.job_id
        and id <> new.id
        and status = 'pending';

      -- Audit accepted (actor_user_int left NULL; your Flask endpoint can add customer actor if desired)
      insert into job_events (job_id, actor_user_int, event_type, data)
      values (new.job_id, NULL, 'APPLICATION_ACCEPTED',
              jsonb_build_object('application_id', new.id, 'worker_id', new.worker_id));

      -- Audit auto-declines (one aggregate event)
      insert into job_events (job_id, actor_user_int, event_type, data)
      values (new.job_id, NULL, 'APPLICATIONS_AUTO_DECLINED',
              jsonb_build_object('job_id', new.job_id));

      -- Also reflect job assignment event
      insert into job_events (job_id, actor_user_int, event_type, data)
      values (new.job_id, NULL, 'JOB_ACCEPTED', jsonb_build_object('worker_id', new.worker_id));

    -- DECLINED
    elsif new.status = 'declined' then
      insert into job_events (job_id, actor_user_int, event_type, data)
      values (new.job_id, NULL, 'APPLICATION_DECLINED',
              jsonb_build_object('application_id', new.id, 'worker_id', new.worker_id));

    -- WITHDRAWN (by worker)
    elsif new.status = 'withdrawn' then
      insert into job_events (job_id, actor_user_int, event_type, data)
      values (new.job_id, new.worker_id, 'APPLICATION_WITHDRAWN',
              jsonb_build_object('application_id', new.id));
    end if;
  end if;

  return new;
end
$$;

drop trigger if exists trg_job_applications_after_upd on job_applications;
create trigger trg_job_applications_after_upd
after update of status on job_applications
for each row execute function trg_job_applications_after_upd();

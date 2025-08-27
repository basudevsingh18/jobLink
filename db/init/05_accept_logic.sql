-- 1) One-shot acceptance table (one worker per job)
create table if not exists accepted_jobs (
  job_id      bigint primary key references jobs(id) on delete cascade,
  worker_id   uuid   not null references users(id),
  accepted_at timestamptz not null default now()
);

-- 2) Trigger function: enforce state + update + audit
create or replace function trg_accepted_jobs_enforce()
returns trigger
language plpgsql
as $$
declare
  v_status text;
begin
  -- Ensure job exists and lock the row
  select status into v_status from jobs where id = new.job_id for update;
  if v_status is null then
    raise exception 'Job % not found', new.job_id using errcode = 'P0001';
  end if;

  -- Only accept when open
  if v_status <> 'open' then
    raise exception 'Job % is not open (current status: %)', new.job_id, v_status using errcode = 'P0001';
  end if;

  -- Flip job status
  update jobs set status = 'accepted' where id = new.job_id;

  -- Audit trail
  insert into job_events (job_id,     actor_user_id,  event_type, data)
                  values (new.job_id, new.worker_id,  'accepted', jsonb_build_object('note','worker accepted'));

  return new;
end
$$;

-- 3) Hook it up
drop trigger if exists trg_accepted_jobs_enforce on accepted_jobs;
create trigger trg_accepted_jobs_enforce
before insert on accepted_jobs
for each row execute function trg_accepted_jobs_enforce();

-- 4) (Optional) If you already had a table named accept_jobs/accepted_jobs,
--    ensure the uniqueness rule exists:
-- alter table accepted_jobs add constraint accepted_jobs_job_unique unique(job_id);

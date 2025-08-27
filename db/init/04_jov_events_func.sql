CREATE OR REPLACE FUNCTION accept_job(p_job_id bigint, p_worker_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_job RECORD;
BEGIN
  SELECT * INTO v_job
  FROM jobs
  WHERE id = p_job_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'JOB_NOT_FOUND');
  END IF;

  IF v_job.status <> 'OPEN' OR v_job.assigned_worker_id IS NOT NULL THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'NOT_OPEN');
  END IF;

  UPDATE jobs
     SET status = 'ASSIGNED',
         assigned_worker_id = p_worker_id,
         accepted_at = now()
   WHERE id = p_job_id;

  INSERT INTO job_events (job_id, actor_user_id, event_type, data)
  VALUES (p_job_id, p_worker_id, 'JOB_ACCEPTED', jsonb_build_object('from','OPEN','to','ASSIGNED'));

  RETURN jsonb_build_object('ok', true);
END;
$$;

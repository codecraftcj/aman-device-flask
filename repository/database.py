from repository.database import db_session
from model.models import DeviceJob, FeederSchedule

# --- Device Job CRUD ---
def add_device_job(command):
    """Add a new command to the job queue."""
    job = DeviceJob(command=command)
    db_session.add(job)
    db_session.commit()
    return {"status": "success", "message": "Job added", "job_id": job.id}

def get_all_device_jobs():
    """Retrieve all device jobs."""
    return db_session.query(DeviceJob).order_by(DeviceJob.created_at.desc()).all()

def update_device_job(job_id, status):
    """Update the status of a job."""
    job = db_session.query(DeviceJob).filter_by(id=job_id).first()
    if job:
        job.status = status
        db_session.commit()
        return {"status": "success", "message": "Job updated"}
    return {"status": "error", "message": "Job not found"}

def delete_device_job(job_id):
    """Delete a job from the queue."""
    job = db_session.query(DeviceJob).filter_by(id=job_id).first()
    if job:
        db_session.delete(job)
        db_session.commit()
        return {"status": "success", "message": "Job deleted"}
    return {"status": "error", "message": "Job not found"}

# --- Feeder Schedule CRUD ---
def add_feeder_schedule(schedule_time, feed_amount):
    """Add a new feeder schedule."""
    schedule = FeederSchedule(schedule_time=schedule_time, feed_amount=feed_amount)
    db_session.add(schedule)
    db_session.commit()
    return {"status": "success", "message": "Feeder schedule added", "schedule_id": schedule.id}

def get_all_feeder_schedules():
    """Retrieve all feeder schedules."""
    return db_session.query(FeederSchedule).order_by(FeederSchedule.schedule_time.asc()).all()

def update_feeder_schedule(schedule_id, status):
    """Update the status of a feeder schedule."""
    schedule = db_session.query(FeederSchedule).filter_by(id=schedule_id).first()
    if schedule:
        schedule.status = status
        db_session.commit()
        return {"status": "success", "message": "Schedule updated"}
    return {"status": "error", "message": "Schedule not found"}

def delete_feeder_schedule(schedule_id):
    """Delete a feeder schedule."""
    schedule = db_session.query(FeederSchedule).filter_by(id=schedule_id).first()
    if schedule:
        db_session.delete(schedule)
        db_session.commit()
        return {"status": "success", "message": "Schedule deleted"}
    return {"status": "error", "message": "Schedule not found"}

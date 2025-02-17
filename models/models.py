import datetime

class DeviceJob:
    """Represents a job assigned to a device."""
    def __init__(self, id, command, status="pending", created_at=None):
        self.id = id
        self.command = command
        self.status = status
        self.created_at = created_at if created_at else datetime.datetime.utcnow()

    def to_dict(self):
        """Convert object to dictionary format."""
        return {
            "id": self.id,
            "command": self.command,
            "status": self.status,
            "created_at": self.created_at
        }

    def __repr__(self):
        return f"<DeviceJob id={self.id}, command={self.command}, status={self.status}>"

class FeederSchedule:
    """Represents a scheduled feeding operation."""
    def __init__(self, id, schedule_time, feed_amount, status="scheduled", created_at=None):
        self.id = id
        self.schedule_time = schedule_time
        self.feed_amount = feed_amount
        self.status = status
        self.created_at = created_at if created_at else datetime.datetime.utcnow()

    def to_dict(self):
        """Convert object to dictionary format."""
        return {
            "id": self.id,
            "schedule_time": self.schedule_time,
            "feed_amount": self.feed_amount,
            "status": self.status,
            "created_at": self.created_at
        }

    def __repr__(self):
        return f"<FeederSchedule id={self.id}, schedule_time={self.schedule_time}, feed_amount={self.feed_amount}, status={self.status}>"

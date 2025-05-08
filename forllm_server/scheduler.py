import datetime
import sqlite3
import time # Added time for consistency, though not directly used in these functions
from .config import DATABASE, DAY_MAP

def is_processing_time():
    """Checks if the current time is within ANY active scheduled processing window."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    cursor.execute('SELECT start_hour, end_hour, days_active, enabled FROM schedule WHERE enabled = TRUE')
    schedules = cursor.fetchall()
    db.close()

    if not schedules:
        return False # No enabled schedules

    now = datetime.datetime.now()
    current_time = now.time()
    current_day_str = DAY_MAP[now.weekday()] # Get 'Mon', 'Tue', etc.

    for schedule_row in schedules: # Renamed to avoid conflict with module name
        active_days = schedule_row['days_active'].split(',') if schedule_row['days_active'] else []
        if current_day_str not in active_days:
            continue # Skip if not active today

        start_hour, end_hour = schedule_row['start_hour'], schedule_row['end_hour']
        start_time = datetime.time(start_hour, 0)
        # Handle end_hour being 0 (midnight) as the end of the day, meaning up to 23:59:59.
        # If end_hour is 0, it means the schedule ends at the very end of the day (23:59:59.999999).
        # For comparison, if end_time is 00:00, it means it ends *before* 00:00 of the *next* day.
        # So, if end_hour is 0, we treat it as 24 for calculation, or more precisely, up to 23:59:59.
        
        # If end_hour is 0, it means the schedule runs until the end of the day.
        # For comparison, if end_time is 00:00, it means it ends *before* 00:00 of the *next* day.
        # So, if end_hour is 0, we treat it as 24 for calculation, or more precisely, up to 23:59:59.
        if end_hour == 0: # Represents end of day, so effectively 24:00 or 23:59:59.999...
            end_time = datetime.time(23, 59, 59, 999999)
        else:
            end_time = datetime.time(end_hour, 0)


        is_active = False
        if start_hour <= end_hour: # Standard case: 09:00-17:00 or 00:00-00:00 (24h)
            if start_hour == end_hour: # 24-hour schedule
                 is_active = True
            elif end_hour == 0: # Special case: 09:00-00:00 (means 09:00 till end of day)
                 is_active = start_time <= current_time
            else: # Normal non-crossing midnight: 09:00-17:00
                 is_active = start_time <= current_time < end_time
        else: # Crosses midnight: 22:00-06:00
            is_active = current_time >= start_time or current_time < end_time
        
        if is_active:
            return True # Active if any schedule matches

    return False # No active schedule found for the current time/day

def get_current_status():
    """Returns the current processing status."""
    return {"active": is_processing_time()}

def get_next_schedule_info():
    """Calculates the next upcoming schedule start time."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    cursor = db.cursor()
    cursor.execute('SELECT id, start_hour, end_hour, days_active, enabled FROM schedule WHERE enabled = TRUE ORDER BY id') # Order for consistency
    schedules = cursor.fetchall()
    db.close()

    if not schedules:
        return None

    now = datetime.datetime.now()
    next_start_dt = None
    next_schedule_details = None

    # Check for up to 7 days ahead
    for day_offset in range(8): # Check today + next 7 days
        check_date = (now + datetime.timedelta(days=day_offset)).date()
        check_day_str = DAY_MAP[check_date.weekday()]

        for schedule_row in schedules: # Renamed to avoid conflict
            active_days = schedule_row['days_active'].split(',') if schedule_row['days_active'] else []
            if check_day_str in active_days:
                start_time = datetime.time(schedule_row['start_hour'], 0)
                potential_start_dt = datetime.datetime.combine(check_date, start_time)

                # If this potential start is in the future compared to now
                if potential_start_dt > now:
                    # If it's the first one we found, or earlier than the current best
                    if next_start_dt is None or potential_start_dt < next_start_dt:
                        next_start_dt = potential_start_dt
                        next_schedule_details = dict(schedule_row) # Store the details of this schedule

    if next_start_dt:
        # Format the result
        return {
            "next_start_iso": next_start_dt.isoformat(),
            "next_start_day": DAY_MAP[next_start_dt.weekday()],
            "next_start_time": next_start_dt.strftime("%H:%M"),
            "schedule_id": next_schedule_details['id'],
            "schedule_details": f"{str(next_schedule_details['start_hour']).zfill(2)}:00-{str(next_schedule_details['end_hour']).zfill(2)}:00 ({next_schedule_details['days_active']})"
        }
    else:
        return None # No upcoming schedule found within the next week
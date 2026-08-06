from datetime import datetime, timedelta, time
import logging

logger = logging.getLogger(__name__)

def parse_time_str(t_str):
    """
    Parses 'HH:MM' or 'HH:MM:SS AM/PM' into standard datetime.time object.
    """
    if not t_str:
        return None
    t_str = t_str.strip()
    for fmt in ["%H:%M", "%H:%M:%S", "%I:%M:%S %p IST", "%I:%M:%S %p", "%I:%M %p"]:
        try:
            return datetime.strptime(t_str, fmt).time()
        except ValueError:
            pass
    return None

def calculate_time_difference_hours(start_t_str, end_t_str) -> float:
    """
    Calculates total hours between start and end time strings, correctly handling overnight shifts.
    """
    t_start = parse_time_str(start_t_str)
    t_end = parse_time_str(end_t_str)
    
    if not t_start or not t_end:
        return 0.0
        
    dt_start = datetime.combine(datetime.today(), t_start)
    dt_end = datetime.combine(datetime.today(), t_end)
    
    # Handle overnight shift (e.g. 20:00 to 05:00 next day)
    if dt_end <= dt_start:
        dt_end += timedelta(days=1)
        
    diff_seconds = (dt_end - dt_start).total_seconds()
    return round(diff_seconds / 3600.0, 2)

def evaluate_attendance_status(punch_in_str, punch_out_str, shift_cfg, leave_record=None) -> dict:
    """
    Evaluates attendance punch record against shift configuration.
    Returns status, working_hours, late_minutes, overtime_hours, early_exit_minutes.
    """
    if leave_record:
        leave_type = leave_record.get('leave_type', 'LEAVE')
        return {
            'status': 'LEAVE',
            'working_hours': 0.0,
            'late_minutes': 0,
            'overtime_hours': 0.0,
            'early_exit_minutes': 0,
            'summary': f"Leave ({leave_type})"
        }
        
    if not punch_in_str:
        return {
            'status': 'ABSENT',
            'working_hours': 0.0,
            'late_minutes': 0,
            'overtime_hours': 0.0,
            'early_exit_minutes': 0,
            'summary': 'Absent'
        }
        
    t_in = parse_time_str(punch_in_str)
    if not t_in:
        return {
            'status': 'PRESENT',
            'working_hours': 0.0,
            'late_minutes': 0,
            'overtime_hours': 0.0,
            'early_exit_minutes': 0,
            'summary': 'Present'
        }
        
    # Calculate working hours if punch out exists
    working_hours = 0.0
    if punch_out_str:
        working_hours = calculate_time_difference_hours(punch_in_str, punch_out_str)
        
    # Evaluate shift details
    shift_start_str = shift_cfg.get('start_time', '09:00')
    shift_end_str = shift_cfg.get('end_time', '18:00')
    grace_mins = int(shift_cfg.get('grace_period_mins', 15))
    full_day_hours = float(shift_cfg.get('full_day_hours', 8.0))
    half_day_hours = float(shift_cfg.get('half_day_hours', 4.0))
    overtime_threshold = float(shift_cfg.get('overtime_threshold', 9.0))
    
    t_shift_start = parse_time_str(shift_start_str) or time(9, 0)
    
    # Check late punch-in
    shift_start_mins = t_shift_start.hour * 60 + t_shift_start.minute + grace_mins
    punch_in_mins = t_in.hour * 60 + t_in.minute
    
    late_minutes = max(0, punch_in_mins - shift_start_mins)
    
    # Overtime calculation
    overtime_hours = max(0.0, round(working_hours - overtime_threshold, 2)) if working_hours > 0 else 0.0
    
    # Determine primary status
    if working_hours > 0 and working_hours < half_day_hours:
        status = 'HALF_DAY'
    elif late_minutes > 0:
        status = 'LATE'
    else:
        status = 'ON_TIME'
        
    return {
        'status': status,
        'working_hours': working_hours,
        'late_minutes': late_minutes,
        'overtime_hours': overtime_hours,
        'early_exit_minutes': 0,
        'summary': f"{status} ({working_hours} hrs)"
    }

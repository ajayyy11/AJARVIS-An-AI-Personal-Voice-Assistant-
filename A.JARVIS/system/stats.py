"""Read-only host telemetry for the AJARVIS local HUD."""
import os, platform, time
from datetime import datetime, timezone
import psutil
def _gb(value): return round(float(value)/(1024**3),2)
def _format_uptime(seconds):
    days,remainder=divmod(max(0,int(seconds)),86400)
    hours,remainder=divmod(remainder,3600); minutes,_=divmod(remainder,60)
    return f"{days}d {hours}h {minutes}m" if days else f"{hours}h {minutes}m"
def get_stats():
    memory=psutil.virtual_memory(); disk=psutil.disk_usage(os.path.abspath(os.sep))
    try:
        battery=psutil.sensors_battery()
        battery_data=None if battery is None else {"available":True,"percent":round(float(battery.percent),1),"plugged":bool(battery.power_plugged)}
    except (AttributeError,OSError,RuntimeError): battery_data=None
    try:
        frequency=psutil.cpu_freq(); frequency_mhz=round(float(frequency.current),1) if frequency else None
    except (AttributeError,OSError,RuntimeError): frequency_mhz=None
    try: process_memory=round(psutil.Process(os.getpid()).memory_info().rss/(1024**2),1)
    except (AttributeError,OSError,RuntimeError): process_memory=None
    try: uptime_seconds=max(0,int(time.time()-psutil.boot_time()))
    except (AttributeError,OSError,RuntimeError): uptime_seconds=0
    return {
        "cpu":round(float(psutil.cpu_percent(interval=None)),1),"cpu_cores":int(psutil.cpu_count(logical=True) or 1),
        "cpu_frequency_mhz":frequency_mhz,"memory":round(float(memory.percent),1),
        "memory_used_gb":_gb(memory.total-memory.available),"memory_total_gb":_gb(memory.total),
        "disk":round(float(disk.percent),1),"disk_used_gb":_gb(disk.used),"disk_total_gb":_gb(disk.total),
        "battery":battery_data,"uptime_seconds":uptime_seconds,"uptime":_format_uptime(uptime_seconds),
        "processor":str(platform.processor() or platform.machine() or platform.system())[:100],
        "platform":platform.system(),"process_memory_mb":process_memory,
        "timestamp":datetime.now(timezone.utc).isoformat(),
    }

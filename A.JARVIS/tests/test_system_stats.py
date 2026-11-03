from types import SimpleNamespace
from system import stats


def test_system_stats_contains_hud_metrics(monkeypatch):
    monkeypatch.setattr(stats.psutil,"cpu_percent",lambda interval=None:12.34)
    monkeypatch.setattr(stats.psutil,"cpu_count",lambda logical=True:8)
    monkeypatch.setattr(stats.psutil,"cpu_freq",lambda:SimpleNamespace(current=2400.0))
    monkeypatch.setattr(stats.psutil,"virtual_memory",lambda:SimpleNamespace(total=16*1024**3,available=8*1024**3,percent=50.0))
    monkeypatch.setattr(stats.psutil,"disk_usage",lambda _path:SimpleNamespace(total=500*1024**3,used=250*1024**3,percent=50.0))
    monkeypatch.setattr(stats.psutil,"sensors_battery",lambda:SimpleNamespace(percent=76.0,power_plugged=True))
    monkeypatch.setattr(stats.psutil,"boot_time",lambda:1000)
    monkeypatch.setattr(stats.time,"time",lambda:2000)
    monkeypatch.setattr(stats.psutil,"Process",lambda _pid:SimpleNamespace(memory_info=lambda:SimpleNamespace(rss=128*1024**2)))
    monkeypatch.setattr(stats.platform,"processor",lambda:"Test CPU")
    monkeypatch.setattr(stats.platform,"machine",lambda:"x86_64")
    monkeypatch.setattr(stats.platform,"system",lambda:"TestOS")
    result=stats.get_stats()
    assert result["cpu"]==12.3 and result["cpu_cores"]==8
    assert result["cpu_frequency_mhz"]==2400.0
    assert result["memory"]==50.0 and result["memory_used_gb"]==8.0 and result["memory_total_gb"]==16.0
    assert result["disk"]==50.0 and result["disk_used_gb"]==250.0
    assert result["battery"]=={"available":True,"percent":76.0,"plugged":True}
    assert result["uptime_seconds"]==1000 and result["uptime"]=="0h 16m"
    assert result["process_memory_mb"]==128.0 and result["platform"]=="TestOS"
    assert result["timestamp"].endswith("+00:00")


def test_system_stats_handles_missing_battery_and_cpu_frequency(monkeypatch):
    monkeypatch.setattr(stats.psutil,"cpu_percent",lambda interval=None:0)
    monkeypatch.setattr(stats.psutil,"cpu_count",lambda logical=True:1)
    monkeypatch.setattr(stats.psutil,"cpu_freq",lambda:None)
    monkeypatch.setattr(stats.psutil,"virtual_memory",lambda:SimpleNamespace(total=1024**3,available=512*1024**2,percent=50.0))
    monkeypatch.setattr(stats.psutil,"disk_usage",lambda _path:SimpleNamespace(total=1024**3,used=512*1024**2,percent=50.0))
    monkeypatch.setattr(stats.psutil,"sensors_battery",lambda:None)
    monkeypatch.setattr(stats.psutil,"boot_time",lambda:0)
    monkeypatch.setattr(stats.time,"time",lambda:1)
    monkeypatch.setattr(stats.psutil,"Process",lambda _pid:SimpleNamespace(memory_info=lambda:SimpleNamespace(rss=0)))
    result=stats.get_stats()
    assert result["battery"] is None
    assert result["cpu_frequency_mhz"] is None

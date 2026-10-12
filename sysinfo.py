"""حالة السيرفر (CPU، الذاكرة، swap، الديسك، البروسيسات) باش نشوفو من الواجهة بلا console."""
import os
import subprocess
import time


def _meminfo():
    out = {}
    try:
        for line in open("/proc/meminfo"):
            k, v = line.split(":", 1)
            out[k] = int(v.strip().split()[0]) * 1024
    except (OSError, ValueError):
        pass
    return out


def _cpu_sample():
    try:
        f = open("/proc/stat").readline().split()[1:]
        v = list(map(int, f))
        idle = v[3] + (v[4] if len(v) > 4 else 0)
        return idle, sum(v)
    except (OSError, ValueError, IndexError):
        return None


def cpu_percent(interval=0.4):
    a = _cpu_sample()
    if not a:
        return None
    time.sleep(interval)
    b = _cpu_sample()
    if not b or b[1] == a[1]:
        return None
    return round(100 * (1 - (b[0] - a[0]) / (b[1] - a[1])))


def top_processes(n=12):
    try:
        out = subprocess.run(["ps", "-eo", "pid,ni,pcpu,pmem,rss,etimes,comm,args", "--sort=-pcpu", "--no-headers"],
                             capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines()[:n]:
        parts = line.split(None, 7)
        if len(parts) < 7:
            continue
        pid, ni, cpu, mem, rss, et, comm = parts[:7]
        args = parts[7] if len(parts) > 7 else comm
        rows.append({"pid": pid, "nice": ni, "cpu": float(cpu), "mem": float(mem), "rss_mb": round(int(rss) / 1024),
                     "age": int(et), "name": comm, "cmd": args[:160]})
    return rows


def snapshot():
    m = _meminfo()
    tot, avail = m.get("MemTotal", 0), m.get("MemAvailable", 0)
    stot, sfree = m.get("SwapTotal", 0), m.get("SwapFree", 0)
    try:
        load = os.getloadavg()
    except OSError:
        load = (0, 0, 0)
    try:
        up = float(open("/proc/uptime").read().split()[0])
    except (OSError, ValueError):
        up = 0
    s = {"cpu": cpu_percent(), "cores": os.cpu_count() or 1, "load": [round(x, 2) for x in load],
         "mem_total_mb": tot // 2**20, "mem_used_mb": (tot - avail) // 2**20,
         "mem_pct": round(100 * (tot - avail) / tot) if tot else 0,
         "swap_total_mb": stot // 2**20, "swap_used_mb": (stot - sfree) // 2**20,
         "swap_pct": round(100 * (stot - sfree) / stot) if stot else 0,
         "uptime_h": round(up / 3600, 1), "procs": top_processes(), "t": time.time()}
    s["ffmpeg"] = [p for p in s["procs"] if p["name"].startswith("ffmpeg")]
    return s

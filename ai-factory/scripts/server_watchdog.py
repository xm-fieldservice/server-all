#!/usr/bin/env python3
import os
import sys
import json
import time
import shlex
import queue
import signal
import socket
import select
import logging
import threading
import subprocess
from logging.handlers import RotatingFileHandler


def getenv_list(name, default):
    v = os.getenv(name)
    if not v:
        return list(default)
    return [x.strip() for x in v.split(",") if x.strip()]


def getenv_int(name, default):
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default


def getenv_float(name, default):
    try:
        return float(os.getenv(name, str(default)))
    except Exception:
        return default


class Snapshot:
    def __init__(self, ts, data, reason=None, events=None):
        self.ts = ts
        self.data = data
        self.reason = reason
        self.events = events or []

    def to_json(self):
        o = {
            "ts": self.ts,
            "data": self.data,
        }
        if self.reason:
            o["reason"] = self.reason
        if self.events:
            o["events"] = self.events
        return o


class Ring:
    def __init__(self, maxlen):
        self.maxlen = maxlen
        self.buf = []

    def append(self, x):
        self.buf.append(x)
        if len(self.buf) > self.maxlen:
            self.buf.pop(0)

    def tail(self, n):
        if n <= 0:
            return []
        return self.buf[-n:]


class Watchdog:
    def __init__(self):
        self.interval = getenv_float("SW_INTERVAL_SEC", 5.0)
        self.log_path = os.getenv("SW_LOG_PATH", os.path.expanduser("~/server_watchdog.log"))
        self.ping_hosts = getenv_list("SW_PING_HOSTS", ["223.5.5.5", "8.8.8.8"])  # AliDNS, Google DNS
        self.ssh_port = getenv_int("SW_SSH_PORT", 22)
        self.glm_match = getenv_list("SW_GLM_MATCH", ["glm", "chatglm", "vllm", "model", "llm"])  # case-insensitive substring match
        self.context_window = getenv_int("SW_CONTEXT_SNAPSHOTS", 12)
        self.rotate_bytes = getenv_int("SW_ROTATE_BYTES", 10 * 1024 * 1024)
        self.rotate_backups = getenv_int("SW_ROTATE_BACKUPS", 5)
        self.loss_fail_thresh = getenv_int("SW_LOSS_FAILS", 2)
        self.high_load = getenv_float("SW_HIGH_LOAD", float(os.cpu_count() or 1) * 2.0)
        self.high_iowait = getenv_float("SW_HIGH_IOWAIT", 15.0)
        self.high_cpu_busy = getenv_float("SW_HIGH_CPU_BUSY", 95.0)
        self.low_mem_mb = getenv_int("SW_LOW_MEM_MB", 512)
        self.enable_journal = os.getenv("SW_ENABLE_JOURNAL", "1") == "1"
        self.enable_gpu = os.getenv("SW_ENABLE_GPU", "1") == "1"
        self.enable_top = os.getenv("SW_ENABLE_TOP", "1") == "1"
        self.enable_tasks = os.getenv("SW_ENABLE_TASKS", "1") == "1"
        self.task_shells = getenv_list("SW_TASK_SHELLS", ["bash", "zsh", "fish", "sh"])
        self.journal_patterns = getenv_list(
            "SW_JOURNAL_PATTERNS",
            [
                "sshd",
                "authentication failure",
                "Disconnected from",
                "pam_unix",
                "oom-killer",
                "Out of memory",
                "soft lockup",
                "blocked for more than",
            ],
        )
        self.stop_event = threading.Event()
        self.context = Ring(self.context_window)
        self._setup_logger()
        self._prev_cpu = None
        self._loss_streak = 0
        self._journal_q = queue.Queue(maxsize=1000)
        self._journal_thread = None

    def _setup_logger(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self.logger = logging.getLogger("server_watchdog")
        self.logger.setLevel(logging.INFO)
        handler = RotatingFileHandler(self.log_path, maxBytes=self.rotate_bytes, backupCount=self.rotate_backups)
        fmt = logging.Formatter("%(message)s")
        handler.setFormatter(fmt)
        self.logger.addHandler(handler)

    def _read_proc_stat(self):
        try:
            with open("/proc/stat", "r") as f:
                for line in f:
                    if line.startswith("cpu "):
                        parts = line.split()
                        vals = list(map(int, parts[1:]))
                        return vals
        except Exception:
            return None

    def _cpu_times_percent(self):
        cur = self._read_proc_stat()
        if cur is None:
            return {}
        if self._prev_cpu is None:
            self._prev_cpu = cur
            return {}
        prev = self._prev_cpu
        self._prev_cpu = cur
        diff = [c - p for c, p in zip(cur, prev)]
        total = max(sum(diff), 1)
        fields = [
            ("user", 0),
            ("nice", 1),
            ("system", 2),
            ("idle", 3),
            ("iowait", 4),
            ("irq", 5),
            ("softirq", 6),
            ("steal", 7),
        ]
        out = {}
        for name, idx in fields:
            if idx < len(diff):
                out[name] = round(100.0 * diff[idx] / total, 2)
        out["busy"] = round(100.0 - out.get("idle", 0.0), 2)
        return out

    def _meminfo(self):
        out = {}
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    val = v.strip().split()[0]
                    out[k] = int(val)
            total_kb = out.get("MemTotal", 0)
            avail_kb = out.get("MemAvailable", 0)
            return {
                "total_mb": round(total_kb / 1024.0, 1),
                "avail_mb": round(avail_kb / 1024.0, 1),
                "used_pct": round(100.0 * (total_kb - avail_kb) / max(total_kb, 1), 2),
            }
        except Exception:
            return {}

    def _loadavg(self):
        try:
            la1, la5, la15 = os.getloadavg()
            return {"1m": la1, "5m": la5, "15m": la15}
        except Exception:
            return {}

    def _net_dev(self):
        data = {}
        try:
            with open("/proc/net/dev", "r") as f:
                lines = f.readlines()[2:]
            for line in lines:
                if ":" not in line:
                    continue
                iface, rest = line.split(":", 1)
                iface = iface.strip()
                parts = rest.split()
                if len(parts) >= 16:
                    rx_bytes = int(parts[0])
                    tx_bytes = int(parts[8])
                    data[iface] = {"rx_bytes": rx_bytes, "tx_bytes": tx_bytes}
        except Exception:
            pass
        return data

    def _ping_once(self, host):
        try:
            p = subprocess.run(
                ["ping", "-n", "-c", "1", "-W", "1", host],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            ok = p.returncode == 0
            rtt_ms = None
            if ok:
                for line in p.stdout.splitlines():
                    if "time=" in line:
                        try:
                            rtt_ms = float(line.split("time=")[1].split()[0])
                        except Exception:
                            pass
                        break
            return ok, rtt_ms, p.stdout[-300:]
        except FileNotFoundError:
            return None, None, "ping not found"
        except Exception as e:
            return False, None, str(e)

    def _ssh_conn_count(self):
        try:
            p = subprocess.run(
                ["ss", "-H", "-tna"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True
            )
            cnt = 0
            for line in p.stdout.splitlines():
                if "ESTAB" in line and f":{self.ssh_port} " in line:
                    cnt += 1
            return cnt
        except Exception:
            return None

    def _top_processes(self):
        if not self.enable_top:
            return None
        try:
            cmd = "ps axo pid,ppid,pcpu,pmem,etimes,cmd --sort=-pcpu | head -n 25"
            p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            return p.stdout
        except Exception:
            return None

    def _gpu_state(self):
        if not self.enable_gpu:
            return None
        try:
            p = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=timestamp,name,uuid,utilization.gpu,utilization.memory,memory.total,memory.used,temperature.gpu,pstate",
                    "--format=csv,noheader,nounits",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=2,
            )
            if p.returncode != 0:
                return None
            return p.stdout.strip()
        except Exception:
            return None

    def _find_glm_activity(self):
        try:
            p = subprocess.run(
                "ps axo pid,cmd --no-header",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            hits = []
            names = [s.lower() for s in self.glm_match]
            for line in p.stdout.splitlines():
                low = line.lower()
                if any(n in low for n in names):
                    hits.append(line.strip())
            return hits[:50]
        except Exception:
            return []

    def _parse_pids_from_glm_hits(self, hits):
        pids = []
        for h in hits:
            try:
                pid = int(h.split()[0])
                pids.append(pid)
            except Exception:
                continue
        return pids

    def _glm_thread_top(self, pids, limit_per=20, max_pids=2):
        out = {}
        if not pids:
            return out
        for pid in pids[:max_pids]:
            try:
                cmd = f"ps -L -p {pid} -o pid,tid,pcpu,pmem,psr,stat,comm --sort=-pcpu | head -n {limit_per}"
                p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                out[str(pid)] = p.stdout
            except Exception:
                pass
        return out

    def _socket_summary(self):
        try:
            p = subprocess.run(["ss", "-s"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            return p.stdout
        except Exception:
            return None

    def _start_journal_tail(self):
        if not self.enable_journal:
            return

        def run():
            cmd = ["journalctl", "-f", "-n", "0", "-o", "short-iso"]
            try:
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
            except FileNotFoundError:
                return
            except Exception:
                return
            patterns = [s.lower() for s in self.journal_patterns]
            while not self.stop_event.is_set():
                if not p.stdout:
                    break
                line = p.stdout.readline()
                if not line:
                    if p.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                low = line.lower()
                if any(k in low for k in patterns):
                    try:
                        self._journal_q.put_nowait(line.strip())
                    except queue.Full:
                        pass
            try:
                if p and p.poll() is None:
                    p.terminate()
            except Exception:
                pass

        t = threading.Thread(target=run, daemon=True)
        t.start()
        self._journal_thread = t

    def _drain_journal(self, max_items=50):
        items = []
        try:
            while len(items) < max_items:
                items.append(self._journal_q.get_nowait())
        except queue.Empty:
            pass
        return items

    def _snapshot(self):
        cpu = self._cpu_times_percent()
        mem = self._meminfo()
        load = self._loadavg()
        net = self._net_dev()
        ssh_cnt = self._ssh_conn_count()
        glm = self._find_glm_activity()
        gpu = self._gpu_state()
        pings = []
        any_fail = False
        for host in self.ping_hosts:
            ok, rtt, tail = self._ping_once(host)
            pings.append({"host": host, "ok": ok, "rtt_ms": rtt})
            if ok is False:
                any_fail = True
        if any_fail:
            self._loss_streak += 1
        else:
            self._loss_streak = 0
        events = self._drain_journal()
        snap = {
            "hostname": socket.gethostname(),
            "cpu": cpu,
            "mem": mem,
            "load": load,
            "net": net,
            "ssh_established": ssh_cnt,
            "glm_hits": glm,
            "gpu": gpu,
            "pings": pings,
            "loss_streak": self._loss_streak,
            "interval_sec": self.interval,
        }
        return snap, events

    def _recent_processes(self, limit=30):
        try:
            cmd = "ps axo pid,ppid,etimes,pcpu,pmem,stat,tty,cmd --sort=etimes | head -n %d" % int(limit)
            p = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            return p.stdout
        except Exception:
            return None

    def _shell_children(self, limit_per=50):
        try:
            # list shells for current user
            p = subprocess.run(
                "ps -u $(id -u) -o pid,ppid,comm,cmd --no-headers",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            shells = []
            for line in p.stdout.splitlines():
                parts = line.split(None, 3)
                if len(parts) < 4:
                    continue
                pid, ppid, comm, cmd = parts[0], parts[1], parts[2], parts[3]
                if comm in self.task_shells:
                    shells.append((int(pid), cmd))
            out = {}
            for pid, cmdline in shells:
                try:
                    q = subprocess.run(
                        "ps --no-headers --ppid %d -o pid,ppid,tty,etimes,stat,pcpu,pmem,cmd | head -n %d" % (pid, int(limit_per)),
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                    )
                    out[str(pid)] = {"shell": cmdline, "children": q.stdout}
                except Exception:
                    continue
            return out
        except Exception:
            return None

    def _detect_reason(self, snap):
        reasons = []
        cpu = snap.get("cpu") or {}
        load = snap.get("load") or {}
        mem = snap.get("mem") or {}
        if snap.get("loss_streak", 0) >= self.loss_fail_thresh:
            reasons.append("network_packet_loss")
        if load.get("1m", 0) >= self.high_load:
            reasons.append("high_load")
        if cpu.get("iowait", 0) >= self.high_iowait:
            reasons.append("high_iowait")
        if cpu.get("busy", 0) >= self.high_cpu_busy:
            reasons.append("high_cpu_busy")
        if mem.get("avail_mb", 0) <= self.low_mem_mb:
            reasons.append("low_memory")
        return ",".join(reasons) if reasons else None

    def _log(self, record):
        try:
            self.logger.info(json.dumps(record, ensure_ascii=False))
        except Exception:
            try:
                self.logger.info(str(record))
            except Exception:
                pass

    def run(self):
        self._start_journal_tail()
        self._prev_cpu = self._read_proc_stat()
        if self._prev_cpu is None:
            pass
        time.sleep(0.2)
        while not self.stop_event.is_set():
            try:
                ts = time.time()
                data, events = self._snapshot()
                reason = self._detect_reason(data)
                snap = Snapshot(ts, data, reason, events)
                self.context.append(snap)
                rec = {"type": "snapshot", **snap.to_json()}
                self._log(rec)
                if reason:
                    ctx = [s.to_json() for s in self.context.tail(min(self.context_window, len(self.context.buf)))]
                    ev = {"type": "event", "ts": ts, "reason": reason, "context": ctx}
                    top = self._top_processes()
                    if top:
                        ev["top"] = top
                    # Add GLM thread-level information and socket summary for correlation
                    glm_hits = data.get("glm_hits") or []
                    pids = self._parse_pids_from_glm_hits(glm_hits)
                    threads = self._glm_thread_top(pids)
                    if threads:
                        ev["glm_threads"] = threads
                    ss_sum = self._socket_summary()
                    if ss_sum:
                        ev["sockets"] = ss_sum
                    if self.enable_tasks:
                        tasks = {"recent": self._recent_processes(), "shell_children": self._shell_children()}
                        ev["tasks"] = tasks
                    self._log(ev)
            except Exception as e:
                self._log({"type": "error", "ts": time.time(), "msg": str(e)})
            self.stop_event.wait(self.interval)

    def stop(self):
        self.stop_event.set()


def main():
    wd = Watchdog()
    stop = threading.Event()

    def handle(sig, frame):
        stop.set()
        wd.stop()

    signal.signal(signal.SIGINT, handle)
    signal.signal(signal.SIGTERM, handle)
    wd.run()


if __name__ == "__main__":
    main()

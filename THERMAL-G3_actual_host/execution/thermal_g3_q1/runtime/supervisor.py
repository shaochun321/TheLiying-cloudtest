"""Q1-R solver supervisor (INFRA): a separate process that owns the hard deadline.

    python -B runtime/supervisor.py <result.json> <deadline_s> <log> <cwd> -- <cmd...>

Windows: the solver is created suspended, assigned to a Job Object with
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (no breakaway), then resumed. At the monotonic deadline the
job is terminated and the supervisor waits until the job reports 0 active processes. If this
supervisor dies for any reason its job handle closes and the OS kills every process in the job.
If the coordinator that started it dies, the supervisor keeps running to the deadline.
Other platforms: a new session/process group, killed with SIGKILL at the deadline.
The result file records returncode, killed flag, wall time and the final active-process count.
"""
import json
import os
import subprocess
import sys
import time

if os.name == "nt":
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("ReadOperationCount", "WriteOperationCount",
                    "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class EXT_LIMIT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC_LIMIT), ("IoInfo", IO_COUNTERS),
                    ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                    ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]

    class BASIC_ACCOUNTING(ctypes.Structure):
        _fields_ = [("TotalUserTime", ctypes.c_longlong), ("TotalKernelTime", ctypes.c_longlong),
                    ("ThisPeriodTotalUserTime", ctypes.c_longlong), ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
                    ("TotalPageFaultCount", wintypes.DWORD), ("TotalProcesses", wintypes.DWORD),
                    ("ActiveProcesses", wintypes.DWORD), ("TotalTerminatedProcesses", wintypes.DWORD)]

    JobObjectBasicAccountingInformation = 1
    JobObjectExtendedLimitInformation = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    CREATE_SUSPENDED = 0x4
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    k32.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.QueryInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                              wintypes.DWORD, ctypes.c_void_p]

    def make_job():
        job = k32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObject")
        info = EXT_LIMIT()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k32.SetInformationJobObject(job, JobObjectExtendedLimitInformation,
                                           ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        return job

    def active(job):
        acc = BASIC_ACCOUNTING()
        k32.QueryInformationJobObject(job, JobObjectBasicAccountingInformation, ctypes.byref(acc),
                                      ctypes.sizeof(acc), None)
        return int(acc.ActiveProcesses)


def main(argv):
    res_path, deadline_s, log, cwd = argv[0], float(argv[1]), argv[2], argv[3]
    cmd = argv[argv.index("--") + 1:]
    out = {"cmd": cmd, "deadline_s": deadline_s, "killed": False}
    t0 = time.monotonic()
    with open(log, "w", encoding="utf-8", errors="replace") as lf:
        if os.name == "nt":
            job = make_job()
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT,
                                    creationflags=CREATE_SUSPENDED)
            if not k32.AssignProcessToJobObject(job, int(proc._handle)):
                proc.kill()
                raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
            ntdll.NtResumeProcess(int(proc._handle))
            out["pid"] = proc.pid
            try:
                rc = proc.wait(timeout=max(0.0, deadline_s - (time.monotonic() - t0)))
            except subprocess.TimeoutExpired:
                out["killed"] = True
                k32.TerminateJobObject(job, 1)
                rc = proc.wait()
            # children of the solver are in the job too: wait until the job is empty
            t_end = time.monotonic() + 10.0
            while active(job) > 0 and time.monotonic() < t_end:
                if out["killed"]:
                    k32.TerminateJobObject(job, 1)
                time.sleep(0.05)
            out["active_after"] = active(job)
        else:
            import signal
            proc = subprocess.Popen(cmd, cwd=cwd, stdout=lf, stderr=subprocess.STDOUT, start_new_session=True)
            out["pid"] = proc.pid
            try:
                rc = proc.wait(timeout=max(0.0, deadline_s - (time.monotonic() - t0)))
            except subprocess.TimeoutExpired:
                out["killed"] = True
                os.killpg(proc.pid, signal.SIGKILL)
                rc = proc.wait()
            out["active_after"] = 0
    out["returncode"] = rc
    out["wall_s"] = time.monotonic() - t0
    tmp = res_path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f)
    os.replace(tmp, res_path)


if __name__ == "__main__":
    main(sys.argv[1:])

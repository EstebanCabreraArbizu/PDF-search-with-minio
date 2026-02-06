import os
import signal
import sys
import glob

def get_pids_on_port(port):
    # 1. Convert port to hex (5000 -> 1388)
    hex_port = "{:04X}".format(port)
    
    # 2. Find inode in /proc/net/tcp
    inodes = set()
    try:
        with open("/proc/net/tcp", "r") as f:
            for line in f:
                fields = line.strip().split()
                if len(fields) > 1 and f":{hex_port}" in fields[1]:
                    # State 0A means LISTENING
                    if fields[3] == '0A':
                        inode = fields[9]
                        inodes.add(inode)
    except FileNotFoundError:
        print("❌ Cannot read /proc/net/tcp (Are you on Linux?)")
        return []

    if not inodes:
        print(f"ℹ️ No process found listening on port {port} (in TCP)")
        return []

    # 3. Scan /proc/[pid]/fd to match inode
    pids = set()
    # Only scan numeric directories in /proc
    proc_dirs = [d for d in os.listdir('/proc') if d.isdigit()]
    
    for pid in proc_dirs:
        try:
            fd_path = f"/proc/{pid}/fd"
            if not os.path.exists(fd_path): 
                continue
                
            for fd_file in os.listdir(fd_path):
                try:
                    link = os.readlink(f"{fd_path}/{fd_file}")
                    # Link format is usually 'socket:[12345]'
                    for inode in inodes:
                        if f"socket:[{inode}]" == link:
                            pids.add(int(pid))
                except (OSError, FileNotFoundError):
                    continue
        except (OSError, PermissionError):
            continue
            
    return list(pids)

def kill_pids(pids):
    for pid in pids:
        try:
            print(f"🔪 Killing PID {pid}...")
            os.kill(pid, signal.SIGKILL) # Force kill (-9)
            print(f"✅ PID {pid} killed.")
        except ProcessLookupError:
            print(f"ℹ️ PID {pid} already dead.")
        except PermissionError:
            print(f"❌ Permission denied killing PID {pid} (Are you root?)")

if __name__ == "__main__":
    port = 5000
    print(f"🔍 Scanning for processes on port {port}...")
    targets = get_pids_on_port(port)
    
    if targets:
        print(f"⚠️  Found PIDs: {targets}")
        kill_pids(targets)
    else:
        print("✅ Port 5000 seems free.")

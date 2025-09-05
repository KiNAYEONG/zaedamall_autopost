# tools/run_post_debug.py
import subprocess, sys
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"

def main():
    print("🐞 iframe 디버깅 실행")
    subprocess.run([sys.executable, str(TOOLS/"auto_write_debug.py"), 
                    "--url", "https://zae-da.com/bbs/write.php?boardid=41"])

if __name__ == "__main__":
    main()

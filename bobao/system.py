"""What differs between macOS and Windows: playing a file, the computer's own voice,
opening a link, turning audio into a clip, and starting at login.

macOS uses afplay, say, afconvert and launchd. Windows uses PowerShell (Windows Media
Player for mp3, System.Speech for the voice), ffmpeg for clips, and a shortcut in the
Startup folder that runs Bobao with pythonw (no console window).
"""

import os
import shutil
import subprocess
import sys

WINDOWS = os.name == "nt"
NO_WINDOW = 0x08000000 if WINDOWS else 0   # CREATE_NO_WINDOW: no console flashing up


def powershell(script, **env):
    """Runs a PowerShell script; values go in through the environment, so no quoting."""
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          env=dict(os.environ, **env), capture_output=True, text=True, creationflags=NO_WINDOW)


PLAY_PS = r"""
Add-Type -AssemblyName PresentationCore
$p = New-Object System.Windows.Media.MediaPlayer
$p.Open([uri]$env:BOBAO_FILE)
$n = 0; while (-not $p.NaturalDuration.HasTimeSpan -and $n -lt 100) { Start-Sleep -Milliseconds 50; $n++ }
$p.Play()
Start-Sleep -Milliseconds ([int]$p.NaturalDuration.TimeSpan.TotalMilliseconds + 150)
$p.Close()
"""

SPEAK_PS = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($env:BOBAO_VOICE) { try { $s.SelectVoice($env:BOBAO_VOICE) } catch {} }
else { try { $s.SelectVoiceByHints('NotSet', 'NotSet', 0, [Globalization.CultureInfo]'zh-CN') } catch {} }
$s.Rate = [int]$env:BOBAO_RATE
if ($env:BOBAO_OUT) { $s.SetOutputToWaveFile($env:BOBAO_OUT) }
$s.Speak($env:BOBAO_TEXT)
$s.Dispose()
"""

VOICES_PS = r"""
Add-Type -AssemblyName System.Speech
(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture }
"""


def play(path):
    """Plays a sound file and waits until it ends."""
    if not path or not os.path.exists(path):
        return
    if not WINDOWS:
        subprocess.run(["/usr/bin/afplay", path])
    elif path.lower().endswith(".wav"):
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    else:
        powershell(PLAY_PS, BOBAO_FILE=os.path.abspath(path))


def speak(text, cfg, out=None):
    """The computer's own voice. out: write a WAV file instead of playing (Windows: for tests)."""
    if not WINDOWS:
        args = ["/usr/bin/say", "-v", cfg["macVoice"], "-r", str(cfg["rate"]), text]
        subprocess.run(args + (["-o", out] if out else []))
        return
    # Windows' rate goes from -10 to 10; macOS words per minute 200 is about 0.
    rate = cfg.get("winRate", max(-10, min(10, round((cfg["rate"] - 200) / 20))))
    powershell(SPEAK_PS, BOBAO_TEXT=text, BOBAO_RATE=str(rate), BOBAO_VOICE=cfg.get("winVoice") or "",
               BOBAO_OUT=out or "")


def voices():
    """The computer's own voices: [(name, language)]."""
    if not WINDOWS:
        r = subprocess.run(["/usr/bin/say", "-v", "?"], capture_output=True, text=True)
        return [(line[:20].strip(), line[20:].split("#")[0].strip()) for line in r.stdout.splitlines()]
    r = powershell(VOICES_PS)
    return [tuple(line.split("|", 1)) for line in r.stdout.splitlines() if "|" in line]


def open_url(url):
    if WINDOWS:
        os.startfile(url)
    else:
        subprocess.run(["/usr/bin/open", url])


def ffmpeg():
    return shutil.which("ffmpeg") or next((p for p in ("/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg")
                                           if os.path.exists(p)), None)


def to_clip_wav(src, dest):
    """Any audio file -> 24 kHz mono 16-bit WAV."""
    if not WINDOWS:
        subprocess.run(["/usr/bin/afconvert", "-f", "WAVE", "-d", "LEI16@24000", "-c", "1", src, dest],
                       check=True, capture_output=True)
        return
    exe = ffmpeg()
    if not exe:
        raise SystemExit("Windows 上生成好听的声音需要 ffmpeg：winget install Gyan.FFmpeg，装好后重新打开终端再运行")
    subprocess.run([exe, "-y", "-loglevel", "error", "-i", src, "-ar", "24000", "-ac", "1", "-sample_fmt", "s16", dest],
                   check=True, capture_output=True, creationflags=NO_WINDOW)


# ---- starting at login (Windows; macOS uses launchd in __main__) -------------------

def startup_dir():
    return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def pythonw():
    exe = sys.executable
    w = os.path.join(os.path.dirname(exe), "pythonw.exe")
    return w if os.path.exists(w) else exe


SHORTCUT_PS = r"""
$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:BOBAO_LNK)
$s.TargetPath = $env:BOBAO_EXE
$s.Arguments = '"' + $env:BOBAO_ARG + '"'
$s.WorkingDirectory = $env:BOBAO_DIR
$s.WindowStyle = 7
$s.Save()
"""


def install_startup(launcher, workdir):
    """A shortcut in the Startup folder runs `launcher` at login, then starts it now."""
    lnk = os.path.join(startup_dir(), "Bobao.lnk")
    r = powershell(SHORTCUT_PS, BOBAO_LNK=lnk, BOBAO_EXE=pythonw(), BOBAO_ARG=launcher, BOBAO_DIR=workdir)
    if r.returncode:
        raise SystemExit(f"没能在启动文件夹里加上 Bobao：{r.stderr.strip()[:200]}")
    stop()
    subprocess.Popen([pythonw(), launcher], cwd=workdir, creationflags=0x00000008 | NO_WINDOW,   # DETACHED_PROCESS
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return lnk


def remove_startup():
    try:
        os.remove(os.path.join(startup_dir(), "Bobao.lnk"))
    except FileNotFoundError:
        pass
    stop()


def running_pid():
    from . import paths
    try:
        pid = int(open(paths.PID).read().strip())
    except (FileNotFoundError, ValueError):
        return None
    r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, creationflags=NO_WINDOW)
    return pid if str(pid) in r.stdout else None


def stop():
    pid = running_pid()
    if pid:
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, creationflags=NO_WINDOW)

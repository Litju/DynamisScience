# RES-636: drive the frozen DynamisScience.exe through import, data workspace, analysis and restart.
# Real keyboard input (SendKeys). SAFETY: keys are sent ONLY while the foreground window belongs to the
# application's own process (checked before every send, otherwise the script aborts), the window is made
# topmost, and each screenshot captures only the application's window rectangle, never the rest of the desktop.
#   powershell -File res636_frozen_drive.ps1 -Exe <DynamisScience.exe> -Work <dir from res636_frozen_prep.py> -Out <dir>
param([Parameter(Mandatory)][string]$Exe, [Parameter(Mandatory)][string]$Work, [Parameter(Mandatory)][string]$Out)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class W {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint f);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int cmd);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
}
"@
New-Item -ItemType Directory -Force $Out | Out-Null
$root = Join-Path $Work "private"; $inputs = Join-Path $Work "inputs"
$script:n = 0

function App-Pids { @(Get-Process -Name DynamisScience -ErrorAction SilentlyContinue | ForEach-Object { $_.Id }) }
function Foreground-Pid { $h = [W]::GetForegroundWindow(); $p = 0; [void][W]::GetWindowThreadProcessId($h, [ref]$p); return [int]$p }
function Assert-Ours { if ((App-Pids) -notcontains (Foreground-Pid)) { throw "Foreground window is not DynamisScience; aborting before sending any key." } }
function Focus-App {
  $deadline = (Get-Date).AddSeconds(60)
  while ((Get-Date) -lt $deadline) {
    $proc = Get-Process -Name DynamisScience -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
    if ($proc) {
      [void][W]::ShowWindow($proc.MainWindowHandle, 9)
      [void][W]::SetWindowPos($proc.MainWindowHandle, [IntPtr](-1), 0, 0, 0, 0, 0x0003)   # topmost, no move/size
      [void][W]::SetForegroundWindow($proc.MainWindowHandle)
      Start-Sleep -Milliseconds 800
      if ((Foreground-Pid) -eq $proc.Id) { return }
    }
    Start-Sleep -Milliseconds 700
  }
  throw "The application window could not be brought to the foreground; nothing was sent."
}
function Shot($name) {
  Ensure-Ours
  $script:n++
  $r = New-Object W+RECT; [void][W]::GetWindowRect([W]::GetForegroundWindow(), [ref]$r)
  $w = $r.R - $r.L; $h = $r.B - $r.T
  $bmp = New-Object System.Drawing.Bitmap $w, $h
  $g = [System.Drawing.Graphics]::FromImage($bmp)
  $g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size $w, $h))
  $bmp.Save((Join-Path $Out ("f{0:D2}-{1}.png" -f $script:n, $name)), [System.Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()
}
function Ensure-Ours { if ((App-Pids) -notcontains (Foreground-Pid)) { Focus-App }; Assert-Ours }
function Keys($k, $wait = 1.5) { Ensure-Ours; [System.Windows.Forms.SendKeys]::SendWait($k); Start-Sleep -Milliseconds ([int]($wait * 1000)) }
function Start-App { $null = Start-Process $Exe -ArgumentList '--data-root', $root; Start-Sleep 12; Focus-App }
function Stop-App { Get-Process -Name DynamisScience -ErrorAction SilentlyContinue | ForEach-Object { $null = $_.CloseMainWindow() }; Start-Sleep 4
                    Get-Process -Name DynamisScience -ErrorAction SilentlyContinue | Stop-Process -Force; Start-Sleep 2 }
function Load-File($file) { Keys '^i' 3; Keys '{ENTER}' 2; Keys ((Join-Path $inputs $file) + '{ENTER}') 6 }

try {
  Start-App
  Shot 'start'
  Load-File 'cmj_valid.csv'
  Shot 'preset-qc'            # saved preset applied, QC already run
  Keys '%i' 4                  # Import (Alt+I): the one click
  Shot 'admitted'
  Keys '{ESC}' 2
  Load-File 'cmj_invalid.csv'
  Shot 'invalid-qc'            # same schema, invalid values: rejected, Admit disabled
  Keys '%r' 4                  # Quarantine (Alt+R)
  Shot 'quarantined'
  Keys '{ESC}' 2
  Load-File 'trace.csv'
  Shot 'trace-qc'
  Keys '%i' 5
  Shot 'trace-admitted'
  Keys '{ESC}' 2
  Keys '^d' 5                  # Data workspace
  Keys '{TAB}{DOWN}{DOWN}{DOWN}{DOWN}' 4   # catalogue: dataset, logical, batch, logical, batch (force-time recording)
  Shot 'workspace-table'
  Keys '%c' 3; Shot 'workspace-columns'
  Keys '%r' 5; Shot 'workspace-traces'
  Keys '%q' 2; Keys '%s' 4; Shot 'workspace-query'
  Keys '%p' 3; Shot 'workspace-inspector'
  Keys '%a' 8                  # Analyze this dataset
  Shot 'analysis-selected'
  Stop-App
  Start-App                    # restart on the same root
  Keys '^d' 5
  Keys '{TAB}{DOWN}{DOWN}{DOWN}{DOWN}' 4
  Shot 'after-restart'
}
finally { Stop-App }
"done; screenshots in $Out"

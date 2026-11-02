# Bobao on Windows: watches for Feishu's message popup (its own small window, bottom right)
# and prints "POPUP<TAB>title" each time one appears. The popup shows only who or which
# group it is from; Bobao then reads the message itself through the Feishu API.
# (ASCII only: Windows PowerShell 5 reads a file without BOM in the local code page.)
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$root = [Windows.Automation.AutomationElement]::RootElement
$all = [Windows.Automation.Condition]::TrueCondition
$text = New-Object Windows.Automation.PropertyCondition ([Windows.Automation.AutomationElement]::ControlTypeProperty), ([Windows.Automation.ControlType]::Text)
$shown = @{}
while ($true) {
  $ids = @{}
  Get-Process -ErrorAction SilentlyContinue | Where-Object { $_.ProcessName -match '^(Feishu|Lark)' } | ForEach-Object { $ids[$_.Id] = 1 }
  $now = @{}
  if ($ids.Count) {
    foreach ($w in $root.FindAll([Windows.Automation.TreeScope]::Children, $all)) {
      try {
        $c = $w.Current
        $r = $c.BoundingRectangle
        if (-not $ids.ContainsKey($c.ProcessId) -or $c.Name -ne '' -or $r.IsEmpty -or $r.Height -gt 400 -or $r.Width -gt 800) { continue }
        $labels = @($w.FindAll([Windows.Automation.TreeScope]::Descendants, $text) | ForEach-Object { $_.Current.Name } | Where-Object { $_ })
        if (-not $labels.Count) { continue }
        $key = ($w.GetRuntimeId() -join '.') + '|' + ($labels -join '|')
        $now[$key] = 1
        if (-not $shown.ContainsKey($key)) { [Console]::WriteLine("POPUP`t" + $labels[0]); [Console]::Out.Flush() }
      } catch {}
    }
  }
  $shown = $now
  Start-Sleep -Milliseconds 400
}

param([string]$EvidenceDir = "C:/master's thesis/runs/M16-one-episode/20261123T091604Z-c6871ba4/traffic/20261123T091809Z-8f6caabe")
$ErrorActionPreference = 'Stop'
$rows = @()
$inputs = @()
$steps = @(Get-ChildItem -LiteralPath $EvidenceDir -Filter 'step-*.json' | Sort-Object Name)
foreach ($file in $steps) {
    $j = Get-Content -LiteralPath $file.FullName -Encoding UTF8 -Raw | ConvertFrom-Json
    $inputs += [ordered]@{file=$file.Name; sha256=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
    $pairs = @($j.calls[0].context.pairs)
    foreach ($call in $j.calls) {
        if ($call.stage -ne 'action') { continue }
        $txt = ($call.messages | ForEach-Object { $_.content }) -join "`n"
        $noConflict = $txt.Contains('Currently, ego vehicle do not have conflict')
        $suggestions = [regex]::Matches($txt, 'You have conflict with [^\r\n]+?passes (first|second)\.')
        $rows += [ordered]@{
            step_id=$j.step_id; vehicle_id=$call.context.vehicle_id; input_pair_count=$pairs.Count
            says_no_conflict=$noConflict; says_empty_info=$txt.Contains('Conflict info is empty')
            advice_count=$suggestions.Count
            advice=@($suggestions | ForEach-Object { $_.Value })
            contradictory_wording=($noConflict -and $suggestions.Count -gt 0)
            idle_current_speed=$txt.Contains('remain in the current lane with current speed')
        }
    }
}
$result = [ordered]@{
    scope='Saved prompts only; no model calls, simulation, TTCP recomputation, or production changes'
    step_count=$steps.Count; action_count=$rows.Count
    no_conflict_count=@($rows | Where-Object says_no_conflict).Count
    contradiction_count=@($rows | Where-Object contradictory_wording).Count
    idle_current_speed_count=@($rows | Where-Object idle_current_speed).Count
    contradictions=@($rows | Where-Object contradictory_wording)
    rows=$rows; inputs=$inputs
}
$result | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'audit.json') -Encoding UTF8
[pscustomobject]$result | Select-Object step_count,action_count,no_conflict_count,contradiction_count,idle_current_speed_count | ConvertTo-Json


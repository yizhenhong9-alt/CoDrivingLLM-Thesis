$ErrorActionPreference='Stop'
$workspace="C:/master's thesis"
$batch="$workspace/runs/M18-intersection-memory-off-20seeds"
$rows=@(); $hashes=@(); $issues=@(); $reference=$null
for($seed=0;$seed -lt 20;$seed++) {
    if($seed -eq 0){$runs=@(Get-Item "$workspace/runs/M16-one-episode/20261123T091604Z-c6871ba4")}
    else {$label='seed-{0:00}' -f $seed; $runs=@(Get-ChildItem "$batch/$label" -Directory | Where-Object {Test-Path -LiteralPath (Join-Path $_.FullName 'result.json')})}
    if($runs.Count -ne 1){throw "seed $seed has $($runs.Count) runs"}
    $run=$runs[0]; $outerPath=Join-Path $run.FullName 'result.json'
    $outer=Get-Content -LiteralPath $outerPath -Encoding UTF8 -Raw|ConvertFrom-Json
    $innerFiles=@(Get-ChildItem -Path "$($run.FullName)/traffic/*/result.json")
    if($innerFiles.Count -ne 1){throw "seed $seed inner report missing/ambiguous"}
    $innerPath=$innerFiles[0]; $inner=Get-Content $innerPath.FullName -Encoding UTF8 -Raw|ConvertFrom-Json
    if($null -eq $reference){$reference=$inner}
    foreach($property in $reference.source_sha256.PSObject.Properties){if($inner.source_sha256.($property.Name) -ne $property.Value){$issues+="seed $seed source differs: $($property.Name)"}}
    if($inner.seed -ne $seed -or $inner.git_status -ne '' -or $inner.parser_mode -ne 'strict' -or $inner.memory_mode -ne 'off' -or $inner.memory_module_imported -ne $false){$issues+="seed $seed metadata mismatch"}
    if(($inner.config|ConvertTo-Json -Depth 20 -Compress) -ne ($reference.config|ConvertTo-Json -Depth 20 -Compress)){$issues+="seed $seed config mismatch"}
    $paths=@($outerPath,$innerPath.FullName)
    $steps=@(Get-ChildItem -LiteralPath $innerPath.DirectoryName -Filter 'step-*.json'|Sort-Object Name)
    if($steps.Count -ne $inner.actual_environment_steps -or $steps.Count -ne @($inner.step_files).Count){$issues+="seed $seed step count mismatch"}
    $crashed=$false; $neg=0; $act=0; $parsed=0; $calls=0; $ticks=0; $seconds=0.0; $badFinish=0; $last=$null
    for($i=0;$i -lt $steps.Count;$i++) {
        $file=$steps[$i]; $paths+=$file.FullName
        $s=Get-Content -LiteralPath $file.FullName -Encoding UTF8 -Raw|ConvertFrom-Json
        if($s.step_id -ne $i -or $s.status -ne 'single_step_complete'){$issues+="seed $seed step $i incomplete/noncontiguous"}
        foreach($v in @($s.initial_vehicles)+@($s.final_vehicles)){if($v.crashed -eq $true){$crashed=$true}}
        if($s.info.cav_crashed -eq $true){$crashed=$true}
        $ticks+=$s.step_observation.physics_ticks; $seconds+=$s.step_observation.simulated_seconds
        $actionIndex=0
        foreach($call in $s.calls){
            $calls++; if($call.stage -eq 'negotiation'){$neg++}else{$act++}
            if($call.parsers.strict.status -eq 'parsed'){$parsed++}else{$issues+="seed $seed step $i strict failure"}
            if($call.api_response.choices[0].finish_reason -ne 'stop'){$badFinish++}
            if($call.raw_response -ne $call.api_response.choices[0].message.content){$issues+="seed $seed step $i raw/API mismatch"}
            if($call.stage -eq 'action'){
                $raw=$call.raw_response|ConvertFrom-Json; $value=$call.parsers.strict.value; $submitted=$s.submitted_vehicle_actions[$actionIndex]
                if($raw.vehicle_id -ne $call.context.vehicle_id -or $raw.vehicle_id -ne $value.vehicle_id -or $raw.decision -ne $value.decision -or $raw.decision -notin $call.context.available_actions -or $submitted.vehicle_id -ne $value.vehicle_id -or $submitted.action_id -ne $value.action_id -or $s.step_observation.environment_action[$actionIndex] -ne $value.action_id){$issues+="seed $seed step $i action mismatch"}
                $actionIndex++
            }
        }
        $last=$s
    }
    foreach($path in $paths){$hashes += [ordered]@{seed=$seed;path=$path;sha256=(Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()}}
    $limit=$inner.config.duration*$inner.config.policy_frequency-1
    $arrived=($inner.status -eq 'episode_terminal' -and $last.done -eq $true -and -not $crashed -and $steps.Count -lt $limit -and $inner.config.offroad_terminal -eq $false -and @($last.info.agents_dones).Count -eq 4 -and @($last.info.agents_dones|Where-Object {$_ -ne $true}).Count -eq 0)
    $console=Get-Content -LiteralPath (Join-Path $run.FullName 'traffic-console.txt') -Encoding UTF8 -Raw
    $rows += [pscustomobject][ordered]@{seed=$seed;steps=$steps.Count;terminal=($inner.status -eq 'episode_terminal');cav_crashed=$crashed;all_arrived_inferred=$arrived;negotiation=$neg;action=$act;strict_parsed=$parsed;calls=$calls;bad_finish=$badFinish;physics_ticks=$ticks;simulated_seconds=$seconds;outer_status=$outer.status;shutdown_clean=$outer.shutdown.clean_observation;shutdown_warnings=($outer.shutdown.warnings -join ',');divide_by_zero_warning=$console.Contains('divide by zero');git_commit=$inner.git_commit;run=$run.FullName}
}
[ordered]@{method='Offline saved-record audit; arrivals inferred from original terminal conditions, not directly recorded has_arrived';rows=$rows;issues=$issues;inputs=$hashes}|ConvertTo-Json -Depth 12|Set-Content -LiteralPath (Join-Path $PSScriptRoot 'audit.json') -Encoding UTF8
$rows|Export-Csv -LiteralPath (Join-Path $PSScriptRoot 'summary.csv') -NoTypeInformation -Encoding UTF8
$rows|Format-Table seed,steps,cav_crashed,all_arrived_inferred,calls,shutdown_clean,divide_by_zero_warning -AutoSize
"ISSUES: $($issues.Count)"
$issues

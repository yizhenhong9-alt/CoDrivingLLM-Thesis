[CmdletBinding()]
param(
    [string]$Repository = "E:\YiZhen\Thesis\CoDrivingLLM-Reproduction",
    [string]$FormalRoot = "E:\YiZhen\codriving_formal_runs\intersection",
    [string]$SeedManifest = "notes\phase4_seed_manifest.json"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repositoryPath = (Resolve-Path -LiteralPath $Repository -ErrorAction Stop).Path
$formalRootPath = (Resolve-Path -LiteralPath $FormalRoot -ErrorAction Stop).Path
$manifestPath = if ([System.IO.Path]::IsPathRooted($SeedManifest)) {
    (Resolve-Path -LiteralPath $SeedManifest -ErrorAction Stop).Path
} else {
    (Resolve-Path -LiteralPath (Join-Path $repositoryPath $SeedManifest) -ErrorAction Stop).Path
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
$seeds = @($manifest.seeds | ForEach-Object { [int]$_ })
if ($seeds.Count -ne 20 -or (@($seeds | Select-Object -Unique)).Count -ne 20) {
    throw "Seed manifest must contain exactly 20 unique seeds"
}

$allCases = @(Get-ChildItem -LiteralPath $formalRootPath -Filter "case.json" -File -Recurse)
if ($allCases.Count -ne 40) {
    throw "Expected exactly 40 case.json artifacts, found $($allCases.Count)"
}

$pairs = @()
$cases = @()
foreach ($seed in $seeds) {
    $records = @{}
    foreach ($mode in @("off", "on")) {
        $runId = "phase4g_formal_{0}_seed{1}" -f $mode, $seed
        $casePath = Join-Path $formalRootPath ("memory_{0}\seed_{1}\{2}\case.json" -f $mode, $seed, $runId)
        if (-not (Test-Path -LiteralPath $casePath -PathType Leaf)) {
            throw "Missing canonical case artifact: $casePath"
        }
        $case = Get-Content -LiteralPath $casePath -Raw | ConvertFrom-Json
        if ($case.schema_version -ne "phase4c.case.v1" -or
                $case.protocol_version -ne "phase4c-intersection-v1" -or
                $case.scenario -ne "intersection" -or
                $case.memory_mode -ne $mode -or
                [int]$case.seed.requested -ne $seed -or
                $case.artifact_complete -ne $true -or
                $case.status -ne "completed") {
            throw "Canonical case contract failed: $casePath"
        }
        $runDirectory = Split-Path -Parent $casePath
        foreach ($required in @("trajectory.jsonl", "llm_calls.jsonl")) {
            if (-not (Test-Path -LiteralPath (Join-Path $runDirectory $required) -PathType Leaf)) {
                throw "Missing $required for $runId"
            }
        }
        if ($mode -eq "on") {
            if (-not (Test-Path -LiteralPath (Join-Path $runDirectory "memory_events.jsonl") -PathType Leaf) -or
                    -not (Test-Path -LiteralPath (Join-Path $runDirectory "chroma") -PathType Container)) {
                throw "Memory ON artifacts are incomplete for $runId"
            }
        }
        $records[$mode] = $case
        $cases += $case
    }
    if ($records.off.initial_state_sha256 -ne $records.on.initial_state_sha256) {
        throw "OFF/ON initial-state hash mismatch for seed $seed"
    }
    $pairs += [ordered]@{
        seed = $seed
        initial_state_sha256 = $records.off.initial_state_sha256
        off_success = $records.off.success
        on_success = $records.on.success
    }
}

function Require-OneValue([object[]]$Values, [string]$Label) {
    $unique = @($Values | ForEach-Object { $_ | ConvertTo-Json -Depth 30 -Compress } | Select-Object -Unique)
    if ($unique.Count -ne 1) {
        throw "$Label is not identical across all 40 canonical cases"
    }
    return $unique[0]
}

$null = Require-OneValue @($cases | ForEach-Object { $_.git.commit }) "Git commit"
$null = Require-OneValue @($cases | ForEach-Object { $_.runtime.python_executable }) "Python executable"
$null = Require-OneValue @($cases | ForEach-Object { $_.runtime.python_version }) "Python version"
$null = Require-OneValue @($cases | ForEach-Object { $_.runtime.package_versions }) "Package versions"
$null = Require-OneValue @($cases | ForEach-Object { $_.environment.effective_config }) "Effective environment config"
$null = Require-OneValue @($cases | ForEach-Object { $_.ollama.version_response }) "Ollama version"
$null = Require-OneValue @($cases | ForEach-Object { $_.ollama.resolved_chat_model.digest }) "Chat model digest"
$onCases = @($cases | Where-Object { $_.memory_mode -eq "on" })
$null = Require-OneValue @($onCases | ForEach-Object { $_.memory.resolved_embedding_model.digest }) "Embedding model digest"

[ordered]@{
    status = "complete"
    protocol_version = "phase4c-intersection-v1"
    expected_seed_count = 20
    memory_off_case_count = 20
    memory_on_case_count = 20
    matched_initial_state_pairs = 20
    frozen_git_commit = $cases[0].git.commit
    frozen_chat_model_digest = $cases[0].ollama.resolved_chat_model.digest
    frozen_embedding_model_digest = $onCases[0].memory.resolved_embedding_model.digest
    seeds = $seeds
    pairs = $pairs
} | ConvertTo-Json -Depth 10

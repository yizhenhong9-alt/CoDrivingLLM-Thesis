[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("off", "on")]
    [string]$MemoryMode,

    [string]$Repository = "E:\YiZhen\Thesis\CoDrivingLLM-Reproduction",
    [string]$Python = "E:\YiZhen\conda_envs\codriving_repro\python.exe",
    [string]$FormalRoot = "E:\YiZhen\codriving_formal_runs\intersection",
    [string]$SeedManifest = "notes\phase4_seed_manifest.json",
    [string]$OllamaEndpoint = "http://127.0.0.1:11435",
    [string]$ChatModel = "qwen2.5:7b",
    [string]$EmbeddingModel = "nomic-embed-text:latest",
    [double]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Resolve-ExistingPath([string]$Value, [string]$Label) {
    $resolved = (Resolve-Path -LiteralPath $Value -ErrorAction Stop).Path
    if (-not [System.IO.Path]::IsPathRooted($resolved)) {
        throw "$Label must resolve to an absolute path"
    }
    return $resolved
}

function Write-JsonFile([string]$Path, [object]$Value) {
    $json = $Value | ConvertTo-Json -Depth 20
    [System.IO.File]::WriteAllText($Path, $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false))
}

function Append-JsonLine([string]$Path, [object]$Value) {
    $json = $Value | ConvertTo-Json -Depth 20 -Compress
    [System.IO.File]::AppendAllText($Path, $json + [Environment]::NewLine,
        [System.Text.UTF8Encoding]::new($false))
}

$repositoryPath = Resolve-ExistingPath $Repository "Repository"
$pythonPath = Resolve-ExistingPath $Python "Python"
$manifestPath = if ([System.IO.Path]::IsPathRooted($SeedManifest)) {
    Resolve-ExistingPath $SeedManifest "Seed manifest"
} else {
    Resolve-ExistingPath (Join-Path $repositoryPath $SeedManifest) "Seed manifest"
}
$formalRootPath = [System.IO.Path]::GetFullPath($FormalRoot)
if ((Split-Path -Leaf $formalRootPath) -ne "intersection") {
    throw "FormalRoot must be the intersection scenario root"
}
$runnerOutputRoot = Split-Path -Parent $formalRootPath

$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if ($manifest.schema_version -ne "phase4c.seed-manifest.v1" -or
        $manifest.protocol_version -ne "phase4c-intersection-v1") {
    throw "Seed manifest schema/protocol does not match the frozen Phase 4G contract"
}
$seeds = @($manifest.seeds | ForEach-Object { [int]$_ })
if ($seeds.Count -ne 20 -or (@($seeds | Select-Object -Unique)).Count -ne 20) {
    throw "Seed manifest must contain exactly 20 unique seeds"
}

Push-Location $repositoryPath
try {
    $gitStatus = (& git status --porcelain)
    if ($LASTEXITCODE -ne 0 -or $gitStatus) {
        throw "Formal execution requires a clean Git working tree"
    }
    $gitCommit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $gitCommit) {
        throw "Unable to resolve the formal Git commit"
    }

    $existingCases = @()
    if (Test-Path -LiteralPath $formalRootPath) {
        $existingCases = @(Get-ChildItem -LiteralPath $formalRootPath -Filter "case.json" -File -Recurse)
    }
    if ($MemoryMode -eq "off") {
        if ($existingCases.Count -ne 0) {
            throw "Formal OFF batch requires a root with no pre-existing case artifacts"
        }
    } else {
        $offCases = @($existingCases | Where-Object {
            $_.FullName -like (Join-Path $formalRootPath "memory_off\*")
        })
        $onCases = @($existingCases | Where-Object {
            $_.FullName -like (Join-Path $formalRootPath "memory_on\*")
        })
        if ($offCases.Count -ne 20 -or $onCases.Count -ne 0) {
            throw "Formal ON batch requires exactly 20 preserved OFF cases and no pre-existing ON cases"
        }
        foreach ($seed in $seeds) {
            $offRunId = "phase4g_formal_off_seed{0}" -f $seed
            $offCasePath = Join-Path $formalRootPath ("memory_off\seed_{0}\{1}\case.json" -f $seed, $offRunId)
            if (-not (Test-Path -LiteralPath $offCasePath -PathType Leaf)) {
                throw "Missing canonical OFF prerequisite: $offCasePath"
            }
            $offCase = Get-Content -LiteralPath $offCasePath -Raw | ConvertFrom-Json
            if ($offCase.status -ne "completed" -or $offCase.artifact_complete -ne $true -or
                    $offCase.memory_mode -ne "off" -or [int]$offCase.seed.requested -ne $seed) {
                throw "Canonical OFF prerequisite is incomplete or incompatible: $offCasePath"
            }
        }
    }

    [System.IO.Directory]::CreateDirectory($formalRootPath) | Out-Null
    $batchManifestPath = Join-Path $formalRootPath ("batch_manifest_{0}.json" -f $MemoryMode)
    $executionLogPath = Join-Path $formalRootPath ("batch_execution_{0}.jsonl" -f $MemoryMode)
    if ((Test-Path -LiteralPath $batchManifestPath) -or
            (Test-Path -LiteralPath $executionLogPath)) {
        throw "Batch manifest/log already exists; refusing overwrite"
    }

    Write-JsonFile $batchManifestPath ([ordered]@{
        schema_version = "phase4g.batch-manifest.v1"
        protocol_version = "phase4c-intersection-v1"
        scenario = "intersection"
        environment_id = "intersection-multi-agent-v0"
        memory_mode = $MemoryMode
        ordering = "all Memory OFF in manifest order, then all Memory ON in the same order"
        seeds = $seeds
        seed_manifest_path = $manifestPath
        seed_manifest_schema_version = $manifest.schema_version
        git_commit = $gitCommit
        repository = $repositoryPath
        python = $pythonPath
        formal_scenario_root = $formalRootPath
        runner_output_root = $runnerOutputRoot
        ollama_endpoint = $OllamaEndpoint
        chat_model = $ChatModel
        embedding_model = $EmbeddingModel
        timeout_seconds = $TimeoutSeconds
        retry_policy = "no automatic retry; stop on first runtime/infrastructure failure"
    })

    foreach ($seed in $seeds) {
        $runId = "phase4g_formal_{0}_seed{1}" -f $MemoryMode, $seed
        $startedUtc = [DateTime]::UtcNow.ToString("o")
        Append-JsonLine $executionLogPath ([ordered]@{
            event = "case_started"
            timestamp_utc = $startedUtc
            memory_mode = $MemoryMode
            seed = $seed
            run_id = $runId
        })

        & $pythonPath -m scripts.phase4_reproduction_experiment `
            --scenario intersection `
            --seed $seed `
            --memory-mode $MemoryMode `
            --output-root $runnerOutputRoot `
            --run-id $runId `
            --ollama-endpoint $OllamaEndpoint `
            --chat-model $ChatModel `
            --embedding-model $EmbeddingModel `
            --timeout $TimeoutSeconds
        $exitCode = $LASTEXITCODE

        Append-JsonLine $executionLogPath ([ordered]@{
            event = if ($exitCode -eq 0) { "case_finished" } else { "case_failed" }
            timestamp_utc = [DateTime]::UtcNow.ToString("o")
            memory_mode = $MemoryMode
            seed = $seed
            run_id = $runId
            exit_code = $exitCode
        })
        if ($exitCode -ne 0) {
            throw "Case $runId failed with exit code $exitCode; batch stopped without retry"
        }
    }
} finally {
    Pop-Location
}

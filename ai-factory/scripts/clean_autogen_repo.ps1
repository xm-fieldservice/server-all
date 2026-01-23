# 清理 D:\AI\ai-factory\autogen_repo 中与 docs\autogen_repo 完全重复的内容
# 使用方法：
# 1. 打开 PowerShell
# 2. cd 到 D:\AI\ai-factory
# 3. 执行：  powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\clean_autogen_repo.ps1

$docs = "D:\AI\ai-factory\docs\autogen_repo"
$old  = "D:\AI\ai-factory\autogen_repo"

Write-Host "docs 知识库目录 : $docs"
Write-Host "old  旧仓库目录 : $old"

if (!(Test-Path $docs) -or !(Test-Path $old)) {
    Write-Host "[ERROR] 路径不存在，请检查：" -ForegroundColor Red
    Write-Host "docs: $docs"
    Write-Host "old : $old"
    exit 1
}

Write-Host "开始比对并删除完全重复的文件..." -ForegroundColor Cyan

# 1) 删除内容完全相同的文件
$files   = Get-ChildItem $docs -Recurse -File
$deleted = 0

foreach ($f in $files) {
    # 计算相对路径
    $rel = $f.FullName.Substring($docs.Length).TrimStart('\\')
    $candidate = Join-Path $old $rel

    if (Test-Path $candidate) {
        # 比较 SHA256，确保内容完全一致才删除
        $h1 = (Get-FileHash -Algorithm SHA256 $f.FullName).Hash
        $h2 = (Get-FileHash -Algorithm SHA256 $candidate).Hash

        if ($h1 -eq $h2) {
            Write-Host "删除重复文件: $candidate" -ForegroundColor Yellow
            Remove-Item $candidate -Force
            $deleted++
        }
    }
}

Write-Host "重复文件删除总数: $deleted" -ForegroundColor Green

# 2) 清理空目录（从最深层往上删）
Write-Host "开始清理空目录..." -ForegroundColor Cyan

$dirs = Get-ChildItem $old -Recurse -Directory | Sort-Object FullName -Descending
$removedDirs = 0

foreach ($d in $dirs) {
    # 如果目录下没有任何文件/子目录，则认为是空目录
    $children = Get-ChildItem $d.FullName -Force | Where-Object { $_.Name -ne "." -and $_.Name -ne ".." }
    if (-not $children) {
        Write-Host "删除空目录: $($d.FullName)" -ForegroundColor Yellow
        Remove-Item $d.FullName -Force
        $removedDirs++
    }
}

Write-Host "空目录删除总数: $removedDirs" -ForegroundColor Green
Write-Host "清理完成。" -ForegroundColor Cyan

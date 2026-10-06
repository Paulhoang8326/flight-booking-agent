$ErrorActionPreference = 'Stop'
$taskReportRoot = Join-Path $PSScriptRoot 'report'
$taskDocx = Join-Path $taskReportRoot 'BTVN_03_24521176_HoangKhoiNguyen.docx'
$taskPdf = Join-Path $taskReportRoot 'BTVN_03_24521176_HoangKhoiNguyen.pdf'
$taskWord = $null
$taskDocument = $null
try {
    $taskWord = New-Object -ComObject Word.Application
    $taskWord.Visible = $false
    $taskWord.DisplayAlerts = 0
    $taskDocument = $taskWord.Documents.Open($taskDocx)
    $taskDocument.Fields.Update() | Out-Null
    $taskDocument.Repaginate()
    $taskDocument.Save()
    $taskDocument.ExportAsFixedFormat($taskPdf, 17)
    Write-Output $taskPdf
} finally {
    if ($null -ne $taskDocument) { $taskDocument.Close(0) }
    if ($null -ne $taskWord) { $taskWord.Quit() }
}

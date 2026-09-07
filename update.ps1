$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Python 가상환경 생성 실패' }
    & .\.venv\Scripts\python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '의존성 설치 실패' }
}
& .\.venv\Scripts\python.exe -m stock_signal.app
if ($LASTEXITCODE -ne 0) { throw '데이터 갱신 실패. site/index.html에 이전 결과 또는 오류가 표시됩니다.' }
Write-Host '완료: site/index.html을 브라우저로 여세요.'

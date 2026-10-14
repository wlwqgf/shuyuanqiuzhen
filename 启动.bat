@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PATH=C:\Users\ao wen wen\.workbuddy\binaries\python\envs\fincheck\Scripts;%PATH%

echo.
echo  ============================================
echo   数据一定队 - 研报纠错核查智能体
echo   环境已就绪，当前目录：%CD%
echo  ============================================
echo.
echo  常用命令（复制粘贴即可）：
echo.
echo    [1] 拆 PDF（文字 + 图片）
echo        python src\01_extract.py data\raw\你的文件.pdf
echo.
echo    [2] 图像识别 OCR
echo        python src\02_ocr.py output\某文件夹\images
echo.
echo    [3] 核查比对
echo        python src\03_check.py
echo.
echo  小提示：文件名可以打前几个字母后按 Tab 键自动补全
echo.
echo  ============================================
echo.

cmd /k

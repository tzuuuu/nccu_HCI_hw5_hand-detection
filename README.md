# HW5 — Vision-Based UI using Hand Detection

沿用 HW4 的 Tkinter 文件閱讀器、六個操作區與八張文件圖片，將輸入改為 MediaPipe Hand Landmarker。手腕關鍵點 #0 決定所在區域；連續 K 個處理影格停留後觸發，搭配冷卻時間與離區後重新啟用。

## 啟動

建議使用 Python 3.11。此資料夾已有獨立 `.venv` 與官方模型；可直接執行：

```bash
source .venv/bin/activate
python app.py
```

重新安裝環境時：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python download_model.py
python app.py
```

若攝影機編號不同：`python app.py --camera 1`。macOS 首次使用需允許啟動程式的應用程式取用攝影機。

- `python app.py --no-camera`：預覽介面，不開啟攝影機；可在診斷視窗按 Retry Camera 接上。
- `python app.py --check-runtime`：不開啟 GUI 或攝影機，以空白影像檢查模型推論。
- `python -m unittest discover -s tests -v`：測試區域邊界、停留、冷卻、排程與記錄。

## 操作

主閱讀器沿用原本上方 78% 與下方 22% 的配置：Z1 上一頁、Z2 下一頁、Z3 放大、Z4 縮小、Z5 選單、Z6 設定。

在診斷視窗伸出一隻手，以紅色 `WRIST #0` 對準操作區。相機影像先鏡像，再送入模型，因此預覽、手腕座標與閱讀器使用相同方向。手腕採正規化座標 `(x, y)`；閱讀區分界為 `y=0.78`，工具列每區寬度為 0.25。

預設 K=6、冷卻時間 1 秒。必須連續停留才觸發；換區、未偵測到手、雙手同時出現，或影格間隔超過 0.5 秒會中斷累積。觸發後須離開原區域且冷卻結束才可再次觸發；冷卻期間不累積影格。只使用一隻手，避免操作者身分交替。選單／設定內的子選項沿用 HW4 的滑鼠操作。

辨識使用 MediaPipe Tasks VIDEO 模式，並將 Detection、Presence、Tracking 三個門檻固定為 0.5；可於啟動時用 `--confidence` 設定三者，但正式實驗全程須保持一致。FPS 顯示實際處理速率，K 代表處理影格數，不是固定毫秒。

正式實驗操作步驟見 [DATA_COLLECTION_GUIDE.md](DATA_COLLECTION_GUIDE.md)。文件頁面保留 HW4 的背景減除主題內容作為相同閱讀素材，不代表 HW5 使用背景減除。

## 實驗與成果

已完成 75 次正式試驗，三組均為 100% 正確觸發。完整統計、時間分布與限制見 [實驗結果分析](results/analysis/RESULTS_ANALYSIS.md)。執行 `python analyze_experiments.py` 可重建驗證紀錄、摘要與圖表。

從 Experiment → Open Experiment Runner 開啟工具：實驗一 30 次、實驗二 27 次、實驗三 18 次。每筆結果完成後立即寫入 `results/`；Pilot 獨立寫入 `pilot-data/`。不會產生模擬的正式結果。

```bash
python analyze_results.py results/experiment1_時間.csv results/experiment2_時間.csv results/experiment3_時間.csv --output results/summary.md
```

請明確選取本次正式實驗的三份 CSV；省略路徑則讀取 `results/` 內所有正式 CSV，可能包含先前中斷或重做的 session。分析會標示各 session，拒絕重複試驗。

`REPORT_TEMPLATE.md` 提供報告架構。截圖由 Save Evidence Screenshot 手動保存；首次各區觸發、實驗三確認光線與錯誤試驗也會自動保存到 `screenshots/`。程式不會辨識環境光線的名稱，Normal／Dim 由操作者實際調整與確認。

## 模型與來源

實作參考 [MediaPipe 官方 Hand Landmarker 文件](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker?tab=Python)。採用 [Google 官方 float16 第 1 版模型](https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task)，SHA256：`fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1`。

正式 CSV 保存模型雜湊、MediaPipe 版本、三個 confidence、K、冷卻時間、處理 FPS 與時間戳記；`requirements-lock.txt` 記錄本次驗證環境。UI 與素材來自作業四，`document_pages.py` 與 `assets/pages/` 保持原樣。

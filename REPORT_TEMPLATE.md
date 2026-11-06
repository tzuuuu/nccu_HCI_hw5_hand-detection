# 作業五：Vision-Based UI using Hand Detection

> 實驗尚未執行；請用實際 CSV、截圖與觀察填寫下列內容。

## 一、目的

說明免持文件閱讀器、與 HW4 的延續關係及此次手部偵測實驗目的。

## 二、辨識原理與程式碼重點

- MediaPipe Hand Landmarker：手掌偵測、21 個關鍵點、VIDEO 追蹤。
- Detector 版本、模型 SHA256、Detection／Presence／Tracking confidence。
- 固定 Wrist #0、鏡像方向與正規化座標轉換。
- 六區 point-in-ROI、連續影格 K、冷卻時間與離區後重新啟用。
- 無手、雙手、失去追蹤及影格中斷的處理。
- 六個指令對應與共用 UI。

## 三、介面與實驗設計

引用 Touchless_Document_Reader_UI.md，保留六區與 78%／22% 配置。

填寫設備、攝影機解析度、操作距離、實際 FPS、光線條件、Pilot 選擇 K 的理由、baseline K、Short／Medium／Long K、冷卻時間、隨機排列方式、8 秒逾時與試驗計時起點。

列出三組實驗的 30／27／18 次設計與實際完成數。說明全程未偵測的操作性定義及其限制。

放入完整介面、Landmarks、Wrist、Previous／Next／工具列、正常／昏暗光線截圖。

## 四、結果與討論

由實際 CSV 產生摘要後填寫：

- 總體與各指令成功率。
- 全程未偵測次數、追蹤遺失與誤觸案例。
- Short／Medium／Long 的成功率與正確觸發平均時間。
- 正常與昏暗光線的比較。
- 手腕靠近邊界、遮擋、雙手歧義等實際錯誤。
- 相較 HW4 背景減除的實務差異；如引用 HW4 結果，說明兩次實驗條件差異，不視為額外正式比較實驗。
- 小樣本、光線量測與偵測失敗定義的限制。

## 參考資料

- [MediaPipe Hand Landmarker 官方文件](https://developers.google.com/edge/mediapipe/solutions/vision/hand_landmarker?tab=Python)
- HW5_Hand_Detection_Experiment_Plan.md
- Touchless_Document_Reader_UI.md

# 追蹤價格（其他）— GitHub Pages 靜態站

6 款空氣清淨機的比價頁，架構比照貓品比價站（cat-food-prices）：
單頁式、資料與畫面分離、瀏覽器端依 data.json 渲染。任何地區都能直接開連結查看。

## 結構

- `build.py`：讀價格資料（唯讀）→ 產生根目錄的 `index.html`（內嵌資料）與 `data.json`，並把 `web/` 的版型與圖示複製到位。不會寫入資料來源。
- `site.config.json`：站名、商品順序、品牌／中文名稱／規格說明、商品圖路徑、不寄荷蘭的平台（`blocked_platforms`，不列入最佳價）、返現邀請連結。
- `web/`：版型（`index.html`、`style.css`、`app.js`）與 `icons/`（favicon、apple-touch-icon、icon-192/512、manifest）。
- `images/<slug>.jpg`：商品圖（自行託管，不外連）。
- 資料來源（唯讀）：`~/workspace/price-tracker-handoff/<slug>/prices.csv` 與 `platforms.json`。
- 發布位置：GitHub Pages 設定為 main 分支**根目錄**（/），所以輸出固定在 repo 根目錄，不用 `docs/`。

## 版面與邏輯（比照貓站）

- 頁首：站名、副標、最後更新日期。
- 商品卡：商品圖、品牌／名稱／規格、目前最低淨總價（只計已核實、有貨可訂、可寄荷蘭者）、前往賣家按鈕、新低價徽章、價格水準膠囊（近 90 天每日最低價）、近 30 天降幅。
- 展開比較：每日最低可買淨價走勢圖、報價排名（缺貨／未核實／不寄荷蘭／舊紀錄收在「顯示其他」後面）、全部查價紀錄表（每一筆原始列，含日期、平台、賣家、價格、運費、淨總價、核實狀態、備註）。
- 側欄（桌機）／篩選面板（手機）：排序（最低價／降價最多／最近更新）、品牌篩選、關注商品勾選；設定存在瀏覽器 localStorage（`pricetracker.view.v1`、`pricetracker.hidden.v1`）。
- 可買判斷：CSV 沒有庫存欄，`build.py` 依每列備註文字判斷（缺貨／售罄／僅到貨通知等負面訊號，遇有貨／現貨／可訂等正面訊號以正面為準）；不寄荷蘭的平台在 `site.config.json` 的 `blocked_platforms` 明列排除。
- 補回（carried）：最新查價日未重查的（平台，賣家），取其最近一筆顯示並標日期，不參與最佳價排名。
- 返現邀請區：只列目前報價實際用到的返現網站（設定在 `site.config.json` 的 `cashback_invites`）。

## 每次更新（每日查價後）

```bash
# 1. 先把新列 append 進 ~/workspace/price-tracker-handoff/<slug>/prices.csv
cd ~/workspace/price-tracker
python3 build.py        # 重新產生 index.html + data.json；留意警告（缺圖等）
```

上傳到 GitHub repo `toocheepfordutch/price-tracker` 根目錄的檔案：

- 每次必傳：`index.html`、`data.json`
- 有變動才傳：`assets/style.css`、`assets/app.js`（改版型時）、`images/*.jpg`（換圖時）
- 只需傳一次：`favicon.ico`、`favicon-32.png`、`apple-touch-icon.png`、`icon-192.png`、`icon-512.png`、`manifest.webmanifest`、`.nojekyll`

上傳後確認 https://toocheepfordutch.github.io/price-tracker/ 已顯示本次日期。

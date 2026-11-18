# 追蹤價格（其他）— GitHub Pages 靜態站

6 款空氣清淨機的比價頁，純靜態 HTML（無 build 依賴、無外部 CDN），
任何地區都能直接開連結查看。

## 重新產生

```bash
cd ~/workspace/price-tracker
python3 build.py
```

build.py 只讀 `~/workspace/price-tracker-handoff/*/prices.csv` 與
`platforms.json`，產生 `index.html` 與每款商品一頁。重跑結果一致（idempotent）。

## 發布（GitHub Pages，待 GitHub 登入授權後執行）

```bash
git add -A && git commit -m "price check update" && git push
```

repo 的 Pages 設定指向 main 分支根目錄即可。

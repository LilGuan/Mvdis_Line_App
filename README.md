# 999R 廣昇車業 React / Supabase 帳務系統

這包已從單一 HTML 原型拆成 React 專案，功能分類放在 `src/features/*`，共用 UI 放在 `src/components/*`，資料庫連線放在 `src/lib/*`。

## 使用方式

1. 安裝套件

```bash
npm install
```

2. 建立 `.env`

```bash
cp .env.example .env
```

填入你的 Supabase 專案資訊：

```bash
VITE_SUPABASE_URL=你的 Supabase URL
VITE_SUPABASE_ANON_KEY=你的 anon key
```

3. 到 Supabase SQL Editor 執行：

```bash
supabase/schema.sql
```

4. 開發模式

```bash
npm run dev
```

如果 `.env` 還沒設定，畫面會用瀏覽器 localStorage 預覽資料；設定 Supabase 後會改讀寫雲端資料表。

## 分類結構

- `src/features/dashboard`：儀表板與近 7 日圖表
- `src/features/records`：收入 / 支出
- `src/features/customers`：常客與欠款
- `src/features/inventory`：零件庫存
- `src/features/invoice`：月結帳單與列印
- `src/features/tax`：營業稅估算
- `src/features/history`：歷史與 CSV 匯出
- `src/features/alerts`：提醒事項
- `supabase/schema.sql`：Supabase 資料表與 RLS policy
It's a Automated to Get Traffic ticket on Mvdis

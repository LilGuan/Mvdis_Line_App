import { useMemo, useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import RecordList from "../../components/ui/RecordList";
import StatCard from "../../components/ui/StatCard";
import { currentMonth, money, signedMoney } from "../../lib/formatters";

export default function HistoryPage({ records, onDeleteRecord }) {
  const [month, setMonth] = useState(currentMonth());
  const [type, setType] = useState("all");
  const filtered = records.filter((record) => {
    const monthMatch = !month || record.record_date.startsWith(month);
    const typeMatch = type === "all" || record.type === type;
    return monthMatch && typeMatch;
  });
  const income = filtered.filter((record) => record.type === "income").reduce((sum, record) => sum + Number(record.amount), 0);
  const expense = filtered.filter((record) => record.type === "expense").reduce((sum, record) => sum + Number(record.amount), 0);
  const net = income - expense;

  const csvUrl = useMemo(() => {
    if (!filtered.length) return "";
    const header = ["日期", "類型", "類別", "說明", "金額(NT$)", "備註"];
    const rows = filtered.map((record) => [
      record.record_date,
      record.type === "income" ? "收入" : "支出",
      record.category,
      record.description,
      record.amount,
      record.note || "",
    ]);
    const content = [header, ...rows].map((row) => row.map((cell) => `"${String(cell).replace(/"/g, '""')}"`).join(",")).join("\r\n");
    return URL.createObjectURL(new Blob([`\uFEFF${content}`], { type: "text/csv;charset=utf-8;" }));
  }, [filtered]);

  return (
    <>
      <PageHeader title="HISTORY" subtitle="歷史收支記錄" />
      <div className="filter-bar">
        <span className="filter-lbl">月份</span>
        <input className="month-input" type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
        <select className="type-select" value={type} onChange={(event) => setType(event.target.value)}>
          <option value="all">全部</option>
          <option value="income">收入</option>
          <option value="expense">支出</option>
        </select>
        <a className={`btn btn-yellow export-btn ${csvUrl ? "" : "disabled"}`} href={csvUrl || undefined} download={`999r廣昇車業_${month || "全部"}_記帳明細.csv`}>匯出 Excel</a>
      </div>
      <div className="stat-grid three">
        <StatCard label="期間收入" value={money(income)} tone="inc" />
        <StatCard label="期間支出" value={money(expense)} tone="exp" />
        <StatCard label="結餘" value={signedMoney(net)} tone={net >= 0 ? "pos" : "neg"} />
      </div>
      <Panel title="明細" aside={<span className="muted-mini">{filtered.length} 筆</span>}>
        <RecordList records={filtered} empty="// 無記錄" onDelete={onDeleteRecord} />
      </Panel>
    </>
  );
}

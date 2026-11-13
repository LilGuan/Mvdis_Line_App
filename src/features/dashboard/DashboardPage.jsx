import { useMemo, useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import RecordList from "../../components/ui/RecordList";
import StatCard from "../../components/ui/StatCard";
import { money, signedMoney, today } from "../../lib/formatters";

export default function DashboardPage({ records, inventory, onDeleteRecord }) {
  const [date, setDate] = useState(today());
  const dailyRecords = records.filter((record) => record.record_date === date);
  const income = dailyRecords.filter((record) => record.type === "income").reduce((sum, record) => sum + Number(record.amount), 0);
  const expense = dailyRecords.filter((record) => record.type === "expense").reduce((sum, record) => sum + Number(record.amount), 0);
  const net = income - expense;
  const estimatedTax = Math.max(0, Math.round((income * 5) / 105 - (expense * 5) / 105));
  const lowInventory = inventory.filter((item) => Number(item.quantity) <= 3);

  const chartGroups = useMemo(() => {
    const groups = [];
    for (let index = 6; index >= 0; index -= 1) {
      const itemDate = new Date();
      itemDate.setDate(itemDate.getDate() - index);
      const key = itemDate.toISOString().split("T")[0];
      const dayRecords = records.filter((record) => record.record_date === key);
      groups.push({
        label: key.slice(5),
        income: dayRecords.filter((record) => record.type === "income").reduce((sum, record) => sum + Number(record.amount), 0),
        expense: dayRecords.filter((record) => record.type === "expense").reduce((sum, record) => sum + Number(record.amount), 0),
      });
    }
    return groups;
  }, [records]);

  const maxChart = Math.max(...chartGroups.map((item) => Math.max(item.income, item.expense)), 1);

  return (
    <>
      <PageHeader title="DASHBOARD" subtitle="廣昇車業 · 營運概況" />
      <div className="filter-bar">
        <span className="filter-lbl">查詢日期</span>
        <input className="date-input" type="date" value={date} onChange={(event) => setDate(event.target.value)} />
        <button className="btn btn-ghost btn-tight" onClick={() => setDate(today())}>今天</button>
      </div>

      <div className="stat-grid">
        <StatCard label="收入" value={money(income)} tone="inc" />
        <StatCard label="支出" value={money(expense)} tone="exp" />
        <StatCard label="淨利" value={signedMoney(net)} tone={net >= 0 ? "pos" : "neg"} />
        <StatCard label="應繳稅（估）" value={money(estimatedTax)} tone="tax" />
      </div>

      <Panel
        title="近 7 日收支圖表"
        aside={<div className="chart-legend"><span className="legend-item"><i className="legend-dot income" />收入</span><span className="legend-item"><i className="legend-dot expense" />支出</span></div>}
      >
        <div className="chart-wrap">
          {chartGroups.map((group) => (
            <div className="bar-group" key={group.label}>
              <div className="bars">
                <div className="bar inc-bar" style={{ height: `${Math.max(2, Math.round((group.income / maxChart) * 130))}px` }} title={`收入 ${money(group.income)}`} />
                <div className="bar exp-bar" style={{ height: `${Math.max(2, Math.round((group.expense / maxChart) * 130))}px` }} title={`支出 ${money(group.expense)}`} />
              </div>
              <div className="bar-lbl">{group.label}</div>
            </div>
          ))}
        </div>
      </Panel>

      <div className="two-col">
        <Panel title="今日明細" aside={<span className="muted-mini">{dailyRecords.length} 筆</span>}>
          <RecordList records={dailyRecords} empty="// 當日無記錄" onDelete={onDeleteRecord} />
        </Panel>
        <Panel title="庫存警示（數量 <= 3）">
          {!lowInventory.length && <div className="empty">// 庫存充足</div>}
          {lowInventory.map((item) => (
            <div className="rec-row" key={item.id}>
              <div className="rec-dot warn" />
              <div className="rec-info">
                <div className="rec-desc">{item.name}</div>
                <div className="rec-meta">{item.category}</div>
              </div>
              <div className="inv-qty low">{item.quantity} 件</div>
            </div>
          ))}
        </Panel>
      </div>
    </>
  );
}

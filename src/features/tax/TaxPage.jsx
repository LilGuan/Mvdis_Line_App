import { useMemo, useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { money } from "../../lib/formatters";

const periods = ["01-02", "03-04", "05-06", "07-08", "09-10", "11-12"];

export default function TaxPage({ records }) {
  const year = new Date().getFullYear();
  const currentIndex = Math.floor(new Date().getMonth() / 2);
  const [period, setPeriod] = useState(`${year}-${periods[currentIndex]}`);
  const [start, end] = period.replace(`${year}-`, "").split("-");

  const summary = useMemo(() => {
    const months = [`${year}-${start}`, `${year}-${end}`];
    const scoped = records.filter((record) => months.includes(record.record_date.slice(0, 7)));
    const salesWithTax = scoped.filter((record) => record.type === "income").reduce((sum, record) => sum + Number(record.amount), 0);
    const purchaseWithTax = scoped.filter((record) => record.type === "expense" && record.category === "進貨").reduce((sum, record) => sum + Number(record.amount), 0);
    const salesNoTax = Math.round((salesWithTax * 100) / 105);
    const purchaseNoTax = Math.round((purchaseWithTax * 100) / 105);
    return {
      salesNoTax,
      salesTax: salesWithTax - salesNoTax,
      purchaseNoTax,
      purchaseTax: purchaseWithTax - purchaseNoTax,
      due: Math.max(0, salesWithTax - salesNoTax - (purchaseWithTax - purchaseNoTax)),
    };
  }, [end, records, start, year]);

  return (
    <>
      <PageHeader title="TAX ESTIMATE" subtitle="台灣 401 表 · 營業稅預估（每兩個月申報）" />
      <div className="filter-bar">
        <span className="filter-lbl">申報期間</span>
        <select className="period-select" value={period} onChange={(event) => setPeriod(event.target.value)}>
          {periods.map((item) => <option key={item} value={`${year}-${item}`}>{year} 年 {item.replace("-", "–")} 月</option>)}
        </select>
      </div>
      <div className="two-col">
        <Panel title="401 表試算">
          <div className="tax-period">申報期間：{year}-{start} ～ {year}-{end}</div>
          <div className="tax-row"><span className="tax-lbl">銷售額（不含稅）</span><span className="tax-val">{money(summary.salesNoTax)}</span></div>
          <div className="tax-row"><span className="tax-lbl green">銷項稅額（5%）</span><span className="tax-val green">{money(summary.salesTax)}</span></div>
          <div className="tax-row"><span className="tax-lbl">進貨金額（不含稅）</span><span className="tax-val">{money(summary.purchaseNoTax)}</span></div>
          <div className="tax-row"><span className="tax-lbl blue">進項稅額（5%）</span><span className="tax-val blue">{money(summary.purchaseTax)}</span></div>
          <div className="divider" />
          <div className="tax-row total"><span className="tax-lbl">應繳稅額</span><span className="tax-val yellow">{money(summary.due)}</span></div>
          <p className="note">此為估算值，正式申報請以會計師與實際憑證確認。</p>
        </Panel>
        <Panel title="申報時程提醒">
          {[
            ["01–02月", "3月15日"],
            ["03–04月", "5月15日"],
            ["05–06月", "7月15日"],
            ["07–08月", "9月15日"],
            ["09–10月", "11月15日"],
            ["11–12月", "隔年1月15日"],
          ].map(([label, deadline]) => (
            <div className={`tax-row ${period.includes(label.slice(0, 2)) ? "current" : ""}`} key={label}>
              <span className="tax-lbl">{year}年 {label} 申報</span><span className="tax-val">{deadline}</span>
            </div>
          ))}
        </Panel>
      </div>
    </>
  );
}

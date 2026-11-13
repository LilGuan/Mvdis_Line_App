import PageHeader from "../../components/ui/PageHeader";
import RecordList from "../../components/ui/RecordList";
import { money } from "../../lib/formatters";
import RecordForm from "./RecordForm";

export default function RecordsPage({ type, records, onAddRecord, onDeleteRecord }) {
  const list = records.filter((record) => record.type === type);
  const total = list.reduce((sum, record) => sum + Number(record.amount), 0);
  const isIncome = type === "income";

  return (
    <>
      <PageHeader title={isIncome ? "INCOME" : "EXPENSE"} subtitle={isIncome ? "收入記錄" : "支出記錄"} />
      <RecordForm type={type} onSubmit={onAddRecord} />
      <div className="sec-hd">
        <span className="sec-hd-lbl">全部{isIncome ? "收入" : "支出"}</span>
        <div className="sec-hd-line" />
        <span className={`mono-mini ${isIncome ? "green" : "red"}`}>{money(total)}</span>
      </div>
      <section className="panel no-padding">
        <RecordList records={list} empty={`// 尚無${isIncome ? "收入" : "支出"}記錄`} onDelete={onDeleteRecord} />
      </section>
    </>
  );
}

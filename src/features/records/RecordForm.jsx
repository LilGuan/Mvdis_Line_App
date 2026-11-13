import { useState } from "react";
import Panel from "../../components/ui/Panel";
import { expenseCategories, incomeCategories } from "../../data/options";
import { today } from "../../lib/formatters";

export default function RecordForm({ type, onSubmit }) {
  const categories = type === "income" ? incomeCategories : expenseCategories;
  const [form, setForm] = useState({
    description: "",
    amount: "",
    record_date: today(),
    category: categories[0],
    note: "",
  });

  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.description.trim() || Number(form.amount) <= 0) return;
    await onSubmit({
      type,
      description: form.description.trim(),
      amount: Number(form.amount),
      record_date: form.record_date,
      category: form.category,
      note: form.note.trim(),
    });
    setForm((current) => ({ ...current, description: "", amount: "", note: "" }));
  };

  return (
    <Panel title={type === "income" ? "新增收入" : "新增支出"}>
      <form onSubmit={submit}>
        <div className="form-row col3">
          <label className="fg">項目說明 *
            <input value={form.description} onChange={(event) => update("description", event.target.value)} placeholder={type === "income" ? "輪胎更換、改裝費..." : "進貨、店租、水電..."} />
          </label>
          <label className="fg">金額 NT$ *
            <input type="number" min="1" value={form.amount} onChange={(event) => update("amount", event.target.value)} placeholder="0" />
          </label>
          <label className="fg">日期 *
            <input type="date" value={form.record_date} onChange={(event) => update("record_date", event.target.value)} />
          </label>
        </div>
        <div className="form-row col2">
          <label className="fg">類別
            <select value={form.category} onChange={(event) => update("category", event.target.value)}>
              {categories.map((category) => <option key={category}>{category}</option>)}
            </select>
          </label>
          <label className="fg">備註
            <input value={form.note} onChange={(event) => update("note", event.target.value)} placeholder="選填" />
          </label>
        </div>
        <button className="btn btn-accent" type="submit">+ 新增{type === "income" ? "收入" : "支出"}</button>
      </form>
    </Panel>
  );
}

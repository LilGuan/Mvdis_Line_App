import { useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { money } from "../../lib/formatters";

export default function CustomersPage({ customers, onAddCustomer, onDebtChange, onDeleteCustomer }) {
  const [form, setForm] = useState({ name: "", phone: "", bike: "", debt: 0, note: "" });
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) return;
    await onAddCustomer({ ...form, name: form.name.trim(), debt: Number(form.debt) || 0 });
    setForm({ name: "", phone: "", bike: "", debt: 0, note: "" });
  };

  const changeDebt = (id, delta) => {
    const value = Number(window.prompt(delta > 0 ? "新增欠款 (NT$)：" : "還款金額 (NT$)：", "0"));
    if (value > 0) onDebtChange(id, delta, value);
  };

  return (
    <>
      <PageHeader title="CUSTOMERS" subtitle="常客帳款管理" />
      <Panel title="新增常客">
        <form onSubmit={submit}>
          <div className="form-row col4">
            <label className="fg">姓名/綽號 *<input value={form.name} onChange={(event) => update("name", event.target.value)} placeholder="阿明" /></label>
            <label className="fg">電話<input value={form.phone} onChange={(event) => update("phone", event.target.value)} placeholder="09xx-xxx-xxx" /></label>
            <label className="fg">車型<input value={form.bike} onChange={(event) => update("bike", event.target.value)} placeholder="JETS 125" /></label>
            <label className="fg">初始欠款<input type="number" value={form.debt} onChange={(event) => update("debt", event.target.value)} /></label>
          </div>
          <label className="fg form-gap">備註<input value={form.note} onChange={(event) => update("note", event.target.value)} placeholder="選填" /></label>
          <button className="btn btn-accent" type="submit">+ 新增常客</button>
        </form>
      </Panel>
      <div className="sec-hd"><span className="sec-hd-lbl">常客列表</span><div className="sec-hd-line" /><span className="muted-mini">{customers.length} 位</span></div>
      {!customers.length && <div className="empty">// 尚無常客</div>}
      {customers.map((customer) => (
        <article className="cust-card" key={customer.id}>
          <div className="cust-hd">
            <div className="cust-av">{customer.name[0]}</div>
            <div>
              <div className="cust-name">{customer.name} <span className={`bdg ${Number(customer.debt) > 0 ? "bdg-red" : "bdg-grn"}`}>{Number(customer.debt) > 0 ? "欠款" : "結清"}</span></div>
              <div className="cust-bike">{customer.bike || "未填車型"}</div>
            </div>
            <div className={`cust-bal ${Number(customer.debt) > 0 ? "owed" : "clear"}`}>{Number(customer.debt) > 0 ? "-" : ""}{money(customer.debt)}</div>
          </div>
          <div className="cust-body">
            <div className="cust-detail">{customer.phone}{customer.phone && customer.note ? " · " : ""}{customer.note}</div>
            <button className="btn btn-del" onClick={() => changeDebt(customer.id, 1)}>+ 欠款</button>
            <button className="btn btn-grn" onClick={() => changeDebt(customer.id, -1)}>− 還款</button>
            <button className="btn btn-ghost tiny" onClick={() => onDeleteCustomer(customer.id)}>刪除</button>
          </div>
        </article>
      ))}
    </>
  );
}

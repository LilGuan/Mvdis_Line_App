import { useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { inventoryCategories } from "../../data/options";
import { money } from "../../lib/formatters";

export default function InventoryPage({ inventory, onAddItem, onUpdateQty, onDeleteItem }) {
  const [form, setForm] = useState({ name: "", category: inventoryCategories[0], quantity: 1, cost: "" });
  const totalValue = inventory.reduce((sum, item) => sum + Number(item.quantity) * Number(item.cost), 0);
  const update = (field, value) => setForm((current) => ({ ...current, [field]: value }));

  const submit = async (event) => {
    event.preventDefault();
    if (!form.name.trim()) return;
    await onAddItem({
      name: form.name.trim(),
      category: form.category,
      quantity: Number(form.quantity) || 0,
      cost: Number(form.cost) || 0,
    });
    setForm({ name: "", category: inventoryCategories[0], quantity: 1, cost: "" });
  };

  return (
    <>
      <PageHeader title="INVENTORY" subtitle="零件庫存管理" />
      <Panel title="新增零件">
        <form onSubmit={submit}>
          <div className="form-row col4">
            <label className="fg">零件名稱 *<input value={form.name} onChange={(event) => update("name", event.target.value)} placeholder="馬吉斯輪胎 M6234" /></label>
            <label className="fg">類別<select value={form.category} onChange={(event) => update("category", event.target.value)}>{inventoryCategories.map((category) => <option key={category}>{category}</option>)}</select></label>
            <label className="fg">數量<input type="number" min="0" value={form.quantity} onChange={(event) => update("quantity", event.target.value)} /></label>
            <label className="fg">單位成本 NT$<input type="number" min="0" value={form.cost} onChange={(event) => update("cost", event.target.value)} placeholder="0" /></label>
          </div>
          <button className="btn btn-accent" type="submit">+ 新增零件</button>
        </form>
      </Panel>

      <div className="sec-hd"><span className="sec-hd-lbl">庫存列表</span><div className="sec-hd-line" /><span className="mono-mini orange">庫存總值 {money(totalValue)}</span></div>
      <section className="panel no-padding">
        <div className="inventory-head"><span>品名</span><span>數量</span><span>成本</span><span>庫存值</span><span /></div>
        {!inventory.length && <div className="empty">// 尚無庫存資料</div>}
        {inventory.map((item) => (
          <div className="inv-row" key={item.id}>
            <div className="inv-name-wrap"><div className="inv-name">{item.name}</div><div className="inv-cat">{item.category}</div></div>
            <div className="qty-control">
              <button className="btn btn-del square" onClick={() => onUpdateQty(item.id, -1)}>−</button>
              <span className={`inv-qty ${Number(item.quantity) <= 3 ? "low" : "ok"}`}>{item.quantity}</span>
              <button className="btn btn-grn square" onClick={() => onUpdateQty(item.id, 1)}>+</button>
            </div>
            <div className="inv-cost">{money(item.cost)}/件</div>
            <div className="inv-total">{money(Number(item.quantity) * Number(item.cost))}</div>
            <button className="btn btn-del" onClick={() => onDeleteItem(item.id)}>刪除</button>
          </div>
        ))}
      </section>
    </>
  );
}

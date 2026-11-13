import { useMemo, useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";
import { currentMonth, money, newId } from "../../lib/formatters";

export default function InvoicePage({ customers }) {
  const [settings, setSettings] = useState({ customerId: "", month: currentMonth(), remark: "", taxRate: 5 });
  const [lineForm, setLineForm] = useState({ description: "", quantity: 1, price: "" });
  const [items, setItems] = useState([]);
  const updateSettings = (field, value) => setSettings((current) => ({ ...current, [field]: value }));
  const updateLine = (field, value) => setLineForm((current) => ({ ...current, [field]: value }));

  const customer = customers.find((item) => String(item.id) === String(settings.customerId));
  const subtotal = items.reduce((sum, item) => sum + Number(item.quantity) * Number(item.price), 0);
  const tax = Math.round((subtotal * Number(settings.taxRate || 0)) / 100);
  const total = subtotal + tax;
  const invoiceNo = useMemo(() => `INV-${String(Date.now()).slice(-8)}`, [items.length]);

  const addItem = (event) => {
    event.preventDefault();
    if (!lineForm.description.trim() || Number(lineForm.price) <= 0) return;
    setItems((current) => [...current, { id: newId(), description: lineForm.description.trim(), quantity: Number(lineForm.quantity) || 1, price: Number(lineForm.price) }]);
    setLineForm({ description: "", quantity: 1, price: "" });
  };

  const print = () => window.print();

  return (
    <>
      <PageHeader title="INVOICE" subtitle="月結帳單產生" />
      <div className="invoice-layout">
        <div>
          <Panel title="帳單設定">
            <label className="fg form-gap">客戶名稱
              <select value={settings.customerId} onChange={(event) => updateSettings("customerId", event.target.value)}>
                <option value="">一般客戶</option>
                {customers.map((item) => <option key={item.id} value={item.id}>{item.name}（{item.bike || "無車型"}）</option>)}
              </select>
            </label>
            <label className="fg form-gap">帳單月份<input type="month" value={settings.month} onChange={(event) => updateSettings("month", event.target.value)} /></label>
            <label className="fg form-gap">帳單備註<textarea value={settings.remark} onChange={(event) => updateSettings("remark", event.target.value)} placeholder="付款期限：30 天內&#10;匯款帳號：..." /></label>
            <label className="fg form-gap">稅率 %<input type="number" min="0" max="100" value={settings.taxRate} onChange={(event) => updateSettings("taxRate", event.target.value)} /></label>
          </Panel>
          <Panel title="加入項目">
            <form onSubmit={addItem}>
              <label className="fg form-gap">說明<input value={lineForm.description} onChange={(event) => updateLine("description", event.target.value)} placeholder="維修項目說明" /></label>
              <div className="form-row col2">
                <label className="fg">數量<input type="number" min="1" value={lineForm.quantity} onChange={(event) => updateLine("quantity", event.target.value)} /></label>
                <label className="fg">單價 NT$<input type="number" min="0" value={lineForm.price} onChange={(event) => updateLine("price", event.target.value)} placeholder="0" /></label>
              </div>
              <button className="btn btn-ghost full" type="submit">+ 加入項目</button>
            </form>
            <div className="invoice-items">
              {items.map((item) => (
                <div className="invoice-item" key={item.id}>
                  <span>{item.description}</span><span>{item.quantity} x {money(item.price)}</span><strong>{money(item.quantity * item.price)}</strong>
                  <button className="btn btn-del square" onClick={() => setItems((current) => current.filter((row) => row.id !== item.id))}>x</button>
                </div>
              ))}
            </div>
          </Panel>
        </div>

        <div>
          <div className="print-actions"><button className="btn btn-yellow" onClick={print}>列印 / PDF</button></div>
          {!items.length && <div className="empty invoice-empty">// 請先加入帳單項目</div>}
          {!!items.length && (
            <article className="invoice-preview">
              <div className="inv-hd">
                <div><div className="inv-co">999R 廣昇車業</div><div className="inv-sub">機車改裝部品 · 維修服務</div></div>
                <div className="inv-no"><strong>月結帳單</strong><br />帳單編號：{invoiceNo}<br />帳單月份：{settings.month}<br />客戶：{customer?.name || "一般客戶"}{customer?.bike ? ` · ${customer.bike}` : ""}</div>
              </div>
              <table className="inv-table">
                <thead><tr><th>#</th><th>項目說明</th><th>數量</th><th>單價</th><th>小計</th></tr></thead>
                <tbody>{items.map((item, index) => <tr key={item.id}><td>{index + 1}</td><td>{item.description}</td><td>{item.quantity}</td><td>{money(item.price)}</td><td>{money(item.quantity * item.price)}</td></tr>)}</tbody>
              </table>
              <div className="inv-footer"><div className="inv-total-box"><div className="inv-total-label">小計 {money(subtotal)} + 稅 {settings.taxRate}% {money(tax)}</div><div className="inv-total-val">{money(total)}</div></div></div>
              {settings.remark && <div className="invoice-remark">{settings.remark}</div>}
            </article>
          )}
        </div>
      </div>
    </>
  );
}

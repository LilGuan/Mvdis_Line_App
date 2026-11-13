import { useState } from "react";
import PageHeader from "../../components/ui/PageHeader";
import Panel from "../../components/ui/Panel";

export default function AlertsPage({ alerts, onAddAlert, onDeleteAlert }) {
  const [text, setText] = useState("");
  const [type, setType] = useState("info");

  const submit = async (event) => {
    event.preventDefault();
    if (!text.trim()) return;
    await onAddAlert(text.trim(), type);
    setText("");
  };

  return (
    <>
      <PageHeader title="ALERTS" subtitle="提醒事項" />
      <Panel title="系統提醒" aside={<span className="muted-mini">{alerts.length} 則</span>}>
        {!alerts.length && <div className="empty">// 目前沒有提醒</div>}
        {alerts.map((alert) => (
          <div className="alert-item" key={alert.id}>
            <div className={`alert-dot ${alert.type}`} />
            <div className="alert-copy">
              <div className="alert-text">{alert.text}</div>
              {alert.sub && <div className="alert-sub">{alert.sub}</div>}
            </div>
            <button className="btn btn-del" onClick={() => onDeleteAlert(alert.id)}>刪除</button>
          </div>
        ))}
      </Panel>
      <Panel title="新增自訂提醒">
        <form onSubmit={submit}>
          <div className="form-row col3">
            <label className="fg span2">提醒內容<input value={text} onChange={(event) => setText(event.target.value)} placeholder="例：聯絡阿明確認前叉零件" /></label>
            <label className="fg">類型
              <select value={type} onChange={(event) => setType(event.target.value)}>
                <option value="info">一般</option>
                <option value="warn">注意</option>
                <option value="danger">緊急</option>
              </select>
            </label>
          </div>
          <button className="btn btn-accent" type="submit">+ 新增提醒</button>
        </form>
      </Panel>
    </>
  );
}

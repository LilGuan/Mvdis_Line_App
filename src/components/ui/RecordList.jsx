import { money } from "../../lib/formatters";

export default function RecordList({ records, empty = "// 尚無記錄", onDelete }) {
  if (!records.length) return <div className="empty">{empty}</div>;

  return (
    <div className="rec-list">
      {records.map((record) => {
        const tone = record.type === "income" ? "inc" : "exp";
        const sign = record.type === "income" ? "+" : "-";
        return (
          <div className="rec-row" key={record.id}>
            <div className={`rec-dot ${tone}`} />
            <div className="rec-info">
              <div className="rec-desc">{record.description}</div>
              <div className="rec-meta">
                {record.record_date}
                {record.note ? ` · ${record.note}` : ""}
              </div>
            </div>
            <span className="rec-cat">{record.category}</span>
            <div className={`rec-amt ${tone}`}>{sign}{money(record.amount)}</div>
            {onDelete && (
              <button className="btn btn-del" onClick={() => onDelete(record.id)}>刪除</button>
            )}
          </div>
        );
      })}
    </div>
  );
}

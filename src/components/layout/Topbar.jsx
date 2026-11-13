import { today } from "../../lib/formatters";

export default function Topbar({ alertCount, source, onAlerts }) {
  return (
    <header className="topbar">
      <div className="logo">999R</div>
      <div>
        <div className="brand-name">廣昇車業</div>
        <div className="logo-text">智慧帳務系統 · React / Supabase</div>
      </div>
      <div className="topbar-right">
        <button className="alert-btn" onClick={onAlerts}>
          🔔 提醒
          {alertCount > 0 && <span className="alert-badge">{alertCount}</span>}
        </button>
        <span className={`source-pill ${source}`}>{source === "supabase" ? "Supabase" : "Local Preview"}</span>
        <div className="online" />
        <div className="topbar-date">{today()}</div>
      </div>
    </header>
  );
}

export default function StatCard({ label, value, tone = "" }) {
  return (
    <div className={`stat ${tone}`}>
      <div className="stat-lbl">{label}</div>
      <div className={`stat-val ${tone}`}>{value}</div>
    </div>
  );
}

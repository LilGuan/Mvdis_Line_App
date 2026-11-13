export default function PageHeader({ title, subtitle }) {
  return (
    <div className="page-hd">
      <div className="page-title">{title}</div>
      <div className="page-sub">{subtitle}</div>
    </div>
  );
}
